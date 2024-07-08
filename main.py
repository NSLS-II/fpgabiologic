from caproto.server import PVGroup, pvproperty, run
from caproto.asyncio.client import Context
import caproto as ca

PANDA_FMC_SCALE_VALUE = -0.000000005

#XF:31ID1-ES{PANDA:1}:CALC1:OUT
class ScalerIOC(PVGroup):
    currentCurrentScale = 0.01
    currentCurrentScaleDebug = -2

    eweValues = []
    currentValues = []
    debugValues = []
    #this will allow for 100 minutes of data at 10Hz
    ewe = pvproperty(value=0.0, name="EWE", doc="EWE values", max_length=60000)
    current = pvproperty(value=0.0, name="I", doc="current values", max_length=60000)
    lastEWE = pvproperty(value=0.0, name="EWE:LAST", doc="EWE values")
    lastCurrent = pvproperty(value=0.0, name="I:LAST", doc="current values")

    debug = pvproperty(value=0, name="I:DEBUG", doc="current values debug", max_length=60000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    async def __ainit__(self, async_lib):
        print("Async init called they want their sink back")

        ctx = Context()

        # what even is an async for loop what
        # this feels so detached from the original concept of a for loop
        async for event, context, data in ctx.monitor("XF:31ID1-ES{PANDA:1}:CALC1:OUT", "XF:31ID1-ES{PANDA:1}:CALC2:OUT"):
            if event == "subscription":
                if context.pv.name == "XF:31ID1-ES{PANDA:1}:CALC1:OUT": # ewe

                    self.eweValues.append(data.data[0] * PANDA_FMC_SCALE_VALUE)
                    await self.ewe.write(self.eweValues, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                    await self.lastEWE.write(data.data[0] * PANDA_FMC_SCALE_VALUE, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                elif context.pv.name == "XF:31ID1-ES{PANDA:1}:CALC2:OUT": # I
                    scaledValue = data.data[0] * PANDA_FMC_SCALE_VALUE * self.currentCurrentScale
                    if len(self.currentValues) > 1:
                        lastLastValue = self.currentValues[-2]
                        lastValue = self.currentValues[-1]
                        if abs(scaledValue) > 0.01 * self.currentCurrentScale and abs(lastValue) > 0.01 * self.currentCurrentScale \
                              and abs(self.eweValues[-1]) > 0.01:
                            changeValue2 = abs(scaledValue / lastValue)
                            if changeValue2 > 5 or changeValue2 < 0.2:
                                print(f"{scaledValue} {lastValue} at {self.eweValues[-1]}")
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
                    self.currentValues.append(scaledValue)
                    self.debugValues.append(self.currentCurrentScaleDebug)
                    await self.current.write(self.currentValues, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                    await self.lastCurrent.write(scaledValue, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
                    await self.debug.write(self.debugValues, timestamp=data.metadata.timestamp, status=data.metadata.status, 
                                        severity=data.metadata.severity)
            elif event == "connection":
                print(f"Client connection state changed: {data}")
                if data == "disconnected":
                    await self.ewe.write(self.ewe.value, status=ca.AlarmStatus.LINK, severity=ca.AlarmSeverity.MAJOR_ALARM)

ioc = ScalerIOC(prefix="XF:31ID1-ES{{BIOLOGIC}}:")
print(dict(ioc.pvdb))
run(ioc.pvdb, startup_hook=ioc.__ainit__)