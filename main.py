#!/usr/bin/env python3

from caproto.server import PVGroup, pvproperty, run
from caproto.asyncio.client import Context
import caproto as ca

# The value multiplied to the raw integer ADC output
# This number should be updated to a more accurate value when possible
PANDA_FMC_SCALE_VALUE = -0.000000005

class ScalerIOC(PVGroup):
    """
    IOC That primarily handles scaling the raw ADC outputs from the PandA IOC,
    as well as handling the starting and counting of parts of the experiment
    being run by EC-Labs
    """
    
    # Keeps track of the current multiplier on the current value in order
    # to keep it at a consistent value
    currentCurrentScale = 0.01
    # Tracks scale of current as the power of 10
    currentCurrentScaleDebug = -2

    # Experiment status
    isExperimentRunning = False
    isCycleRunning = False
    numCycles = 0

    # Array values to enable using a graph in CS Studio
    eweValues = []
    currentValues = []
    debugValues = []

    currentIndex = 0

    #Array PVs for graph, used as a circular buffer. 
    ewe = pvproperty(value=0.0, name="EWE", doc="EWE values", max_length=60000)
    current = pvproperty(value=0.0, name="I", doc="current values", max_length=60000)
    lastEWE = pvproperty(value=0.0, name="EWE:LAST", doc="EWE values")
    lastCurrent = pvproperty(value=0.0, name="I:LAST", doc="current values")

    debug = pvproperty(value=0, name="I:DEBUG", doc="current values debug", max_length=60000)

    # Experimental status PVs
    cycleStatus = pvproperty(dtype=str, name="CYCLE:STATUS", doc="Current status of experiment", max_length=10)
    expStatus = pvproperty(dtype=str, name="EXP:STATUS", doc="Current status of experiment", max_length=10)
    cycleNum = pvproperty(value=0, name="EXP:NUM_CYCLES", doc="Number of cycles in experiment")
    cycleCounter = pvproperty(value=0, name="CYCLE:NUM", doc="Current cycle count")
    
    # Trigger PVs
    triggerIn = pvproperty(value=0, name="TRIG:IN", doc="Trigger In")
    triggerOut = pvproperty(value=0, name="TRIG:OUT", doc="Trigger Out")

    # PVs to control data saving frequency
    clockFreq = pvproperty(value=0.0, name="FREQ", doc="Data aquisition frequency (Hz)")
    clockFreqSet = pvproperty(value=0.0, name="FREQ:SET", doc="Data aquisition frequency (Hz)")

    reset = pvproperty(value=0, name="RESET", doc="Reset IOC")

    def __init__(self, panda_prefix, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.panda_prefix = panda_prefix
    
    async def __ainit__(self, async_lib):
        print("Async init called they want their sink back")

        ctx = Context()

        self.ttlout, self.clkPeriod, self.clkWidth, self.counterReset = await ctx.get_pvs(f"{self.panda_prefix}BITS:A",
                                                                       f"{self.panda_prefix}CLOCK1:PERIOD", f"{self.panda_prefix}CLOCK1:WIDTH",
                                                                       f"{self.panda_prefix}BITS:B")
        
        await self.cycleStatus.write("Idle")
        await self.expStatus.write("Idle")
        await self.counterReset.write(0)
        await self.counterReset.write(1)

        # what even is an async for loop what
        # this feels so detached from the original concept of a for loop
        async for event, context, data in ctx.monitor(f"{self.panda_prefix}CALC1:OUT", f"{self.panda_prefix}CALC2:OUT",
                                                      f"{self.panda_prefix}TTLIN1:VAL", f"{self.panda_prefix}COUNTER1:OUT",
                                                      f"{self.panda_prefix}CLOCK1:PERIOD"):
            if event == "subscription":
                if context.pv.name == f"{self.panda_prefix}CALC1:OUT": # ewe

                    self.eweValues[self.currentIndex] = data.data[0] * PANDA_FMC_SCALE_VALUE
                    await self.ewe.write(self.eweValues, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                    await self.lastEWE.write(data.data[0] * PANDA_FMC_SCALE_VALUE, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                elif context.pv.name == f"{self.panda_prefix}CALC2:OUT": # I
                    scaledValue = data.data[0] * PANDA_FMC_SCALE_VALUE * self.currentCurrentScale
                    if self.currentIndex > 1:
                        lastValue = self.currentValues[self.currentIndex - 1]
                        if abs(scaledValue) > 0.01 * self.currentCurrentScale and abs(lastValue) > 0.01 * self.currentCurrentScale \
                              and abs(self.eweValues[self.currentIndex]) > 0.01:
                            changeValue2 = abs(scaledValue / lastValue)
                            if changeValue2 > 5:
                                self.currentCurrentScale /= 10
                                self.currentCurrentScaleDebug -= 1
                                print(f"Current scale decreased to {self.currentCurrentScaleDebug}")
                                scaledValue = data.data[0] * PANDA_FMC_SCALE_VALUE * self.currentCurrentScale
                            elif changeValue2 < 0.2:
                                self.currentCurrentScale *= 10
                                self.currentCurrentScaleDebug += 1
                                print(f"Current scale increased to {self.currentCurrentScaleDebug}")
                                scaledValue = data.data[0] * PANDA_FMC_SCALE_VALUE * self.currentCurrentScale
                    self.currentValues[self.currentIndex] = scaledValue
                    self.debugValues[self.currentIndex] = self.currentCurrentScaleDebug
                    self.currentIndex += 1
                    if currentIndex >= 60000:
                        currentIndex = 0
                    await self.current.write(self.currentValues, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                    await self.lastCurrent.write(scaledValue, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                    await self.debug.write(self.debugValues, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                    
                elif context.pv.name == f"{self.panda_prefix}TTLIN1:VAL": # ttlin
                    if data.data[0] == 1:
                        self.isCycleRunning = False
                        await self.cycleStatus.write("Idle", timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                    await self.triggerIn.write(data.data[0], timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                elif context.pv.name == f"{self.panda_prefix}COUNTER1:OUT": # experiment counter
                    if data.data[0] >= self.numCycles:
                        self.isExperimentRunning = False
                        await self.expStatus.write("Idle")
                        await self.counterReset.write(0)
                    await self.cycleCounter.write(data.data[0], timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                elif context.pv.name == f"{self.panda_prefix}CLOCK1:PERIOD": # clock period
                    await self.clockFreq.write(1.0 / data.data[0])
            elif event == "connection":
                print(f"Client connection state changed: {data}")
                if data == "disconnected":
                    await self.ewe.write(self.ewe.value, status=ca.AlarmStatus.LINK, severity=ca.AlarmSeverity.MAJOR_ALARM)
    
    @triggerOut.putter
    async def triggerOut(self, instance, value):
        print(value)
        if not self.isCycleRunning:
            self.isExperimentRunning = True
            self.isCycleRunning = True
            await self.counterReset.write(1)
            await self.expStatus.write("Running")
            await self.cycleStatus.write("Running")
            await self.ttlout.write(value)
            await self.ttlout.write(0)
    
    @clockFreqSet.putter
    async def clockFreqSet(self, instance, value):
        await self.clkPeriod.write(1.0 / value)
        await self.clkWidth.write(1.0 / value / 2.0)

    @cycleNum.putter
    async def cycleNum(self, instance, value):
        self.numCycles = value
    
    @reset.putter
    async def reset(self, instance, value):
        if value == 1:
            self.currentCurrentScale = 0.01
            self.currentCurrentScaleDebug = -2
            self.isExperimentRunning = False
            self.isCycleRunning = False
            await self.cycleCounter.write(0)
            await self.counterReset.write(0)
            await self.cycleStatus.write("Idle")
            await self.expStatus.write("Idle")


import argparse

def parse_args():
    parser = argparse.ArgumentParser(description = "Helper caproto IOC to run the BioLogic potentiostat w/ a PandABox")
    parser.add_argument("ioc_prefix", help = "PV Prefix for the helper IOC")
    parser.add_argument("panda_prefix", help = "PV Prefix for the PandABox")
    return parser.parse_args()


def main():
    args = vars(parse_args())

    print(args)

    ioc = ScalerIOC(f"{args['panda_prefix']}", prefix=f"{args['ioc_prefix']}")
    print(dict(ioc.pvdb))
    run(ioc.pvdb, startup_hook=ioc.__ainit__)

if __name__ == "__main__":
    main()
