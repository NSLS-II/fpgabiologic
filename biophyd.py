from collections import OrderedDict

from ophyd import Component as Cpt
from ophyd import Device, EpicsPathSignal, EpicsSignal, EpicsSignalRO

class DATA(Device):
    hdf_directory = Cpt(EpicsSignal, "HDFDirectory", string=True)
    hdf_file_name = Cpt(EpicsSignal, "HDFFileName", string=True)
    num_capture = Cpt(EpicsSignal, "NumCapture")
    flush_period = Cpt(EpicsSignal, "FlushPeriod")
    capture = Cpt(EpicsSignal, "Capture")
    capture_mode = Cpt(EpicsSignal, "CaptureMode", string=True)
    status = Cpt(EpicsSignal, "Status", string=True)

    def prepare(self, dirPath, fileName):
        self.hdf_directory.put(dirPath)
        self.hdf_file_name.put(fileName)
        self.flush_period.put(0.5)
        self.capture_mode.set("FOREVER")
    
    def trigger(self):
        self.capture.put(1)

    def endCapture(self):
        self.capture.put(0)


class BioLogic(Device):
    ewe = Cpt(EpicsSignalRO, "EWE")
    i = Cpt(EpicsSignalRO, "I")
    lastEwe = Cpt(EpicsSignalRO, "EWE:LAST")
    lastI = Cpt(EpicsSignalRO, "I:LAST")

    cycleStatus = Cpt(EpicsSignalRO, "CYCLE:STATUS", string=True)
    currentCycleNum = Cpt(EpicsSignalRO, "CYCLE:NUM")

    experimentStatus = Cpt(EpicsSignalRO, "EXP:STATUS", string=True)
    numTotalCycles = Cpt(EpicsSignal, "EXP:NUM_CYCLES")

    triggerIn = Cpt(EpicsSignalRO, "TRIG:IN")
    triggerOut = Cpt(EpicsSignal, "TRIG:OUT")
    clockFreq = Cpt(EpicsSignalRO, "FREQ")
    clockFreqSet = Cpt(EpicsSignal, "FREQ:SET")

    resetSgl = Cpt(EpicsSignal, "RESET")

    def trigger(self):
        self.triggerOut.put(1)
    
    def read(self):
        od = OrderedDict()
        od["Ewe"] = {"value": self.lastEwe.get(), "timestamp": self.lastEwe.timestamp}
        od["I"] = {"value": self.lastI.get(), "timestamp": self.lastI.timestamp}
        return od
    
    def reset(self):
        self.resetSgl.put(1)

class BioLogicData(Device):
    data = Cpt(DATA, r"{PANDA:1}:DATA:")
    biologic = Cpt(BioLogic, r"{BIOLOGIC}:")

    def handleCycleChange(self, value, old_value, timestamp, **kwargs):
        if value != old_value:
            if value == self.biologic.numTotalCycles.get():
                self.data.endCapture()

    def __init__(self, dirPath, fileName, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.biologic.currentCycleNum.subscribe(self.handleCycleChange)
        self.data.prepare(dirPath, fileName)

    def trigger(self):
        self.biologic.trigger()
        self.data.trigger()
    
    def read(self):
        return self.biologic.read()
    
    def reset(self):
        self.data.endCapture()
        self.biologic.reset()

vsp300 = BioLogicData("/nsls2/data/tst/legacy/mock-proposals/2024-1/pass-000000", "test1.hdf", r"XF:31ID1-ES", name="vsp300")