# (C) Roberr Jordens <jordens@gmail.com> 2014, 2015

from migen.fhdl.std import *
from migen.bank.description import *


class XADC(Module, AutoCSR):
    def __init__(self, xadc):
        self.alarm = Signal(8)
        self.ot = Signal()
        self.adc = [Signal((12, True)) for i in range(4)]

        self.r_temp = CSRStatus(12)
        self.r_v = CSRStatus(12)
        self.r_a = CSRStatus(12)
        self.r_b = CSRStatus(12)
        self.r_c = CSRStatus(12)
        self.r_d = CSRStatus(12)

        ###

        self.comb += [
                self.adc[0].eq(self.r_a.status),
                self.adc[1].eq(self.r_b.status),
                self.adc[2].eq(self.r_c.status),
                self.adc[3].eq(self.r_d.status),
        ]

        busy = Signal()
        channel = Signal(5)
        eoc = Signal()
        eos = Signal()
        data = Signal(16)
        drdy = Signal()

        vin = Cat(xadc.n[:2], Replicate(0, 6), xadc.n[2:4], Replicate(0, 6), xadc.n[4])
        vip = Cat(xadc.p[:2], Replicate(0, 6), xadc.p[2:4], Replicate(0, 6), xadc.p[4])
        self.specials += Instance("XADC",
            p_INIT_40=0x0000, p_INIT_41=0x2f0f, p_INIT_42=0x0400, # config
            p_INIT_48=0x0900, p_INIT_49=0x0303, # channels VpVn, Temp
            p_INIT_4A=0x47e0, p_INIT_4B=0x0000, # avg VpVn, temp
            p_INIT_4C=0x0800, p_INIT_4D=0x0303, # bipolar
            p_INIT_4E=0x0000, p_INIT_4F=0x0000, # acq time
            p_INIT_50=0xb5ed, p_INIT_51=0x57e4, # temp trigger, vccint upper alarms
            p_INIT_52=0xa147, p_INIT_53=0xca33, # vccaux upper, temp over upper
            p_INIT_54=0xa93a, p_INIT_55=0x52c6, # temp reset, vccint lower
            p_INIT_56=0x9555, p_INIT_57=0xae4e, # vccaux lower, temp over reset
            p_INIT_58=0x5999, p_INIT_5C=0x5111, # vbram uppper, vbram lower
            p_INIT_59=0x5555, p_INIT_5D=0x5111, # vccpint upper lower
            p_INIT_5A=0x9999, p_INIT_5E=0x91eb, # vccpaux upper lower
            p_INIT_5B=0x6aaa, p_INIT_5F=0x6666, # vccdro upper lower
            o_ALM=self.alarm, o_OT=self.ot,
            o_BUSY=busy, o_CHANNEL=channel, o_EOC=eoc, o_EOS=eos,
            i_VAUXN=vin[:16], i_VAUXP=vip[:16], i_VN=vin[16], i_VP=vip[16],
            i_CONVST=0, i_CONVSTCLK=0, i_RESET=ResetSignal(),
            o_DO=data, o_DRDY=drdy, i_DADDR=channel, i_DCLK=ClockSignal(),
            i_DEN=eoc, i_DI=0, i_DWE=0,
            # o_JTAGBUSY=, o_JTAGLOCKED=, o_JTAGMODIFIED=, o_MUXADDR=,
        )

        channels = {
                0: self.r_temp,
                3: self.r_v,
                16: self.r_b,
                17: self.r_c,
                24: self.r_a,
                25: self.r_d,
        }

        self.sync += [
                If(drdy,
                    Case(channel, dict(
                        (k, v.status.eq(data >> 4))
                    for k, v in channels.items()))
                )
        ]
