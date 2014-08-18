# Robert Jordens <jordens@gmail.com> 2014

from migen.fhdl.std import *
from migen.genlib.record import *
from migen.bus import wishbone

# https://github.com/RedPitaya/RedPitaya/blob/master/FPGA/release1/fpga/code/rtl/red_pitaya_daisy.v

from .delta_sigma import DeltaSigma
from .pid import Pid


sys_layout = [
    ("rstn", 1),
    ("clk", 1),
    ("addr", 32),
    ("wdata", 32),
    ("sel", 4),
    ("wen", 1),
    ("ren", 1),
    ("rdata", 32),
    ("err", 1),
    ("ack", 1),
]


class SysInterconnect(Module):
    def __init__(self, master, *slaves):
        for s in slaves:
            self.comb += [
                    s.clk.eq(master.clk),
                    s.rstn.eq(master.rstn),
                    s.addr.eq(master.addr),
                    s.wdata.eq(master.wdata),
                    s.sel.eq(master.sel),
            ]
        cs = Signal(max=len(slaves))
        self.comb += [
                cs.eq(master.addr[20:23]),
                Array([Cat(s.wen, s.ren) for s in slaves])[cs].eq(
                    Cat(master.wen, master.ren)),
                Cat(master.rdata, master.err, master.ack).eq(
                    Array([Cat(s.rdata, s.err, s.ack) for s in slaves])[cs]),
        ]


class Sys2Wishbone(Module):
    def __init__(self):
        self.wishbone = wb = wishbone.Interface()
        self.sys = Record(sys_layout)

        ###

        adr = Signal.like(self.sys.addr)
        re = Signal()

        self.specials += Instance("bus_clk_bridge",
                i_sys_clk_i=self.sys.clk, i_sys_rstn_i=self.sys.rstn,
                i_sys_addr_i=self.sys.addr, i_sys_wdata_i=self.sys.wdata,
                i_sys_sel_i=self.sys.sel, i_sys_wen_i=self.sys.wen,
                i_sys_ren_i=self.sys.ren, o_sys_rdata_o=self.sys.rdata,
                o_sys_err_o=self.sys.err, o_sys_ack_o=self.sys.ack,
                i_clk_i=ClockSignal(), i_rstn_i=ResetSignal(),
                o_addr_o=adr, o_wdata_o=wb.dat_w, o_wen_o=wb.we,
                o_ren_o=re, i_rdata_i=wb.dat_r, i_err_i=wb.err,
                i_ack_i=wb.ack,
        )
        self.comb += [
                wb.stb.eq(re | wb.we),
                wb.cyc.eq(wb.stb),
                wb.adr.eq(adr[2:]),
        ]



class CRG(Module):
    def __init__(self, clk125, rst):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_sys2 = ClockDomain()
        self.clock_domains.cd_sys2p = ClockDomain()
        self.clock_domains.cd_ser = ClockDomain()

        i, b = Signal(), Signal()
        clk, clkb = Signal(7), Signal(7)
        locked = Signal()
        self.specials += [
                Instance("IBUFDS", i_I=clk125.p, i_IB=clk125.n, o_O=i),
                Instance("BUFG", i_I=i, o_O=b),
                Instance("PLLE2_BASE",
                    p_BANDWIDTH="OPTIMIZED",
                    p_DIVCLK_DIVIDE=1,
                    p_CLKFBOUT_MULT=8,
                    p_CLKFBOUT_PHASE=0.,
                    p_CLKIN1_PERIOD=8.,
                    p_REF_JITTER1=0.01,
                    p_STARTUP_WAIT="FALSE",
                    i_CLKIN1=b, i_PWRDWN=0, i_RST=rst,
                    o_CLKFBOUT=clk[6], i_CLKFBIN=clkb[6],
                    p_CLKOUT0_DIVIDE=8, p_CLKOUT0_PHASE=0.,
                    p_CLKOUT0_DUTY_CYCLE=0.5, o_CLKOUT0=clk[0],
                    p_CLKOUT1_DIVIDE=4, p_CLKOUT1_PHASE=0.,
                    p_CLKOUT1_DUTY_CYCLE=0.5, o_CLKOUT1=clk[1],
                    p_CLKOUT2_DIVIDE=4, p_CLKOUT2_PHASE=-45.,
                    p_CLKOUT2_DUTY_CYCLE=0.5, o_CLKOUT2=clk[2],
                    p_CLKOUT3_DIVIDE=4, p_CLKOUT3_PHASE=0.,
                    p_CLKOUT3_DUTY_CYCLE=0.5, o_CLKOUT3=clk[3],
                    p_CLKOUT4_DIVIDE=4, p_CLKOUT4_PHASE=0.,
                    p_CLKOUT4_DUTY_CYCLE=0.5, o_CLKOUT4=clk[4],
                    p_CLKOUT5_DIVIDE=4, p_CLKOUT5_PHASE=0.,
                    p_CLKOUT5_DUTY_CYCLE=0.5, o_CLKOUT5=clk[5],
                    o_LOCKED=locked,
                )
        ]
        rst = Signal.like(clk)
        for i, o, r in zip(clk, clkb, rst):
            self.specials += [
                    Instance("BUFG", i_I=i, o_O=o),
                    Instance("FD", p_INIT=1, i_D=~locked, i_C=o, o_Q=r)
            ]
        for c, r, d in zip(clkb, rst,
                [self.cd_sys, self.cd_sys2, self.cd_sys2p, self.cd_ser]):
            self.comb += d.clk.eq(c), d.rst.eq(r)



cpu_layout = [
       ("FIXED_IO_mio", 54),
       ("FIXED_IO_ps_clk", 1),
       ("FIXED_IO_ps_porb", 1),
       ("FIXED_IO_ps_srstb", 1),
       ("FIXED_IO_ddr_vrn", 1),
       ("FIXED_IO_ddr_vrp", 1),
       ("DDR_addr", 15),
       ("DDR_ba",  3),
       ("DDR_cas_n", 1),
       ("DDR_ck_n", 1),
       ("DDR_ck_p", 1),
       ("DDR_cke", 1),
       ("DDR_cs_n", 1),
       ("DDR_dm",  4),
       ("DDR_dq", 32),
       ("DDR_dqs_n",  4),
       ("DDR_dqs_p",  4),
       ("DDR_odt", 1),
       ("DDR_ras_n", 1),
       ("DDR_reset_n", 1),
       ("DDR_we_n", 1),
]


#     tcl.append("read_xdc ../verilog/dont_touch.xdc")
#     tcl.append("read_xdc -ref processing_system7_v5_4_processing_system7 ../verilog/ system_processing_system7_0_0.xdc")

class RedPid(Module):
    def __init__(self, platform):

        ps_io = platform.request("cpu")
        ps_sys = Record(sys_layout)
        fclk = Signal(4)
        frstn = Signal(4)
        self.specials.ps = Instance("red_pitaya_ps",
            io_FIXED_IO_mio=ps_io.FIXED_IO_mio,
            io_FIXED_IO_ps_clk=ps_io.FIXED_IO_ps_clk,
            io_FIXED_IO_ps_porb=ps_io.FIXED_IO_ps_porb,
            io_FIXED_IO_ps_srstb=ps_io.FIXED_IO_ps_srstb,
            io_FIXED_IO_ddr_vrn=ps_io.FIXED_IO_ddr_vrn,
            io_FIXED_IO_ddr_vrp=ps_io.FIXED_IO_ddr_vrp,
            io_DDR_addr=ps_io.DDR_addr,
            io_DDR_ba=ps_io.DDR_ba,
            io_DDR_cas_n=ps_io.DDR_cas_n,
            io_DDR_ck_n=ps_io.DDR_ck_n,
            io_DDR_ck_p=ps_io.DDR_ck_p,
            io_DDR_cke=ps_io.DDR_cke,
            io_DDR_cs_n=ps_io.DDR_cs_n,
            io_DDR_dm=ps_io.DDR_dm,
            io_DDR_dq=ps_io.DDR_dq,
            io_DDR_dqs_n=ps_io.DDR_dqs_n,
            io_DDR_dqs_p=ps_io.DDR_dqs_p,
            io_DDR_odt=ps_io.DDR_odt,
            io_DDR_ras_n=ps_io.DDR_ras_n,
            io_DDR_reset_n=ps_io.DDR_reset_n,
            io_DDR_we_n=ps_io.DDR_we_n,

            o_fclk_clk_o=fclk,
            o_fclk_rstn_o=frstn,

            o_sys_clk_o=ps_sys.clk,
            o_sys_rstn_o=ps_sys.rstn,
            o_sys_addr_o=ps_sys.addr,
            o_sys_wdata_o=ps_sys.wdata,
            o_sys_sel_o=ps_sys.sel,
            o_sys_wen_o=ps_sys.wen,
            o_sys_ren_o=ps_sys.ren,
            i_sys_rdata_i=ps_sys.rdata,
            i_sys_err_i=ps_sys.err,
            i_sys_ack_i=ps_sys.ack,

            #o_spi_ss_o=spim.ss,
            #o_spi_ss1_o=spim.ss1,
            #o_spi_ss2_o=spim.ss2,
            #o_spi_sclk_o=spim.sclk,
            #o_spi_mosi_o=spim.mosi,
            #i_spi_miso_i=spim.miso,
            i_spi_miso_i=0,

            #i_spi_ss_i=spis.ss,
            #i_spi_sclk_i=spis.sclk,
            #i_spi_mosi_i=spis.mosi,
            #o_spi_miso_o=spis.miso,
            i_spi_ss_i=0,
            i_spi_sclk_i=0,
            i_spi_mosi_i=0,
        )

        self.submodules.crg = CRG(platform.request("clk125"), frstn[0])

        adc_clk = platform.request("adc_clk")
        adc_clk.cdcs.reset = 1
        adc_clk.clk.reset = 0b10


        io = Record([
            ("ia", (14, True)), ("ib", (14, True)),
            ("oa", (14, True)), ("ob", (14, True))
        ])
        adca, adcb = [platform.request("adc", i) for i in range(2)]
        dac = platform.request("dac")
        daca, dacb = Signal(flen(dac.data)), Signal(flen(dac.data))
        self.sync += [ # signed and negative amplifier gain
                io.ia.eq(Cat(~adca[:-1], adca[-1])),
                io.ib.eq(Cat(~adcb[:-1], adcb[-1])),
                daca.eq(Cat(~io.oa[:-1], io.oa[-1])),
                dacb.eq(Cat(~io.ob[:-1], io.ob[-1])),
        ]
        self.specials += [
                Instance("ODDR", i_D1=0, i_D2=1, i_C=ClockSignal("sys2p"),
                    o_Q=platform.request("dac_clk")),
                Instance("ODDR", i_D1=0, i_D2=1, i_C=ClockSignal("sys2"),
                    o_Q=dac.wrt),
                Instance("ODDR", i_D1=1, i_D2=0, i_C=ClockSignal(),
                    o_Q=dac.sel),
                Instance("ODDR", i_D1=~ResetSignal(), i_D2=~ResetSignal(),
                    i_C=ClockSignal(), o_Q=dac.rst),
                [Instance("ODDR", i_D1=bi, i_D2=ai, i_C=ClockSignal(),
                    o_Q=di) for ai, bi, di in zip(daca, dacb, dac.data)]
        ]

        pwm = []
        for i in range(4):
            ds = DeltaSigma(width=24)
            self.submodules += ds
            self.comb += platform.request("dac_pwm", i).eq(ds.out)
            pwm.append(ds.data)

        exp_q = platform.request("exp")
        n = flen(exp_q.p)
        exp = Record([
            ("pi", n), ("ni", n),
            ("po", n), ("no", n),
            ("pt", n), ("nt", n),
        ])
        for i in range(n):
            self.specials += Instance("IOBUF",
                    o_O=exp.pi[i], io_IO=exp_q.p[i], i_I=exp.po[i], i_T=exp.pt[i])
            self.specials += Instance("IOBUF",
                    o_O=exp.ni[i], io_IO=exp_q.n[i], i_I=exp.no[i], i_T=exp.nt[i])
        leds = Cat(*(platform.request("user_led", i) for i in range(n)))

        hk_sys = Record(sys_layout)
        self.specials.hk = Instance("red_pitaya_hk",
                i_clk_i=ClockSignal(),
                i_rstn_i=~ResetSignal(),
                o_led_o=leds,
                i_exp_p_dat_i=exp.pi,
                i_exp_n_dat_i=exp.ni,
                o_exp_p_dir_o=exp.pt,
                o_exp_n_dir_o=exp.nt,
                o_exp_p_dat_o=exp.po,
                o_exp_n_dat_o=exp.no,

                i_sys_clk_i=hk_sys.clk,
                i_sys_rstn_i=hk_sys.rstn,
                i_sys_addr_i=hk_sys.addr,
                i_sys_wdata_i=hk_sys.wdata,
                i_sys_sel_i=hk_sys.sel,
                i_sys_wen_i=hk_sys.wen,
                i_sys_ren_i=hk_sys.ren,
                o_sys_rdata_o=hk_sys.rdata,
                o_sys_err_o=hk_sys.err,
                o_sys_ack_o=hk_sys.ack,
        )

        asg_trig = Signal()
        scope_sys = Record(sys_layout)
        self.specials.scope = Instance("red_pitaya_scope",
                i_adc_a_i=io.ia,
                i_adc_b_i=io.ib,
                i_adc_clk_i=ClockSignal(),
                i_adc_rstn_i=~ResetSignal(),
                i_trig_ext_i=exp.pi[0],
                i_trig_asg_i=asg_trig,

                i_sys_clk_i=scope_sys.clk,
                i_sys_rstn_i=scope_sys.rstn,
                i_sys_addr_i=scope_sys.addr,
                i_sys_wdata_i=scope_sys.wdata,
                i_sys_sel_i=scope_sys.sel,
                i_sys_wen_i=scope_sys.wen,
                i_sys_ren_i=scope_sys.ren,
                o_sys_rdata_o=scope_sys.rdata,
                o_sys_err_o=scope_sys.err,
                o_sys_ack_o=scope_sys.ack,
        )

        asg = [Signal((14, True)) for i in range(2)]

        asg_sys = Record(sys_layout)
        self.specials.asg = Instance("red_pitaya_asg",
                o_dac_a_o=asg[0],
                o_dac_b_o=asg[1],
                i_dac_clk_i=ClockSignal(),
                i_dac_rstn_i=~ResetSignal(),
                i_trig_a_i=exp.pi[0],
                i_trig_b_i=exp.pi[0],
                o_trig_out_o=asg_trig,

                i_sys_clk_i=asg_sys.clk,
                i_sys_rstn_i=asg_sys.rstn,
                i_sys_addr_i=asg_sys.addr,
                i_sys_wdata_i=asg_sys.wdata,
                i_sys_sel_i=asg_sys.sel,
                i_sys_wen_i=asg_sys.wen,
                i_sys_ren_i=asg_sys.ren,
                o_sys_rdata_o=asg_sys.rdata,
                o_sys_err_o=asg_sys.err,
                o_sys_ack_o=asg_sys.ack,
        )

        self.submodules.pid = Pid()
        self.submodules.sys2wb = Sys2Wishbone()
        self.submodules.wbcon = wishbone.InterconnectPointToPoint(
                self.sys2wb.wishbone, self.pid.wishbone)
        self.comb += [
                self.pid.ins[0].eq(io.ia),
                self.pid.ins[1].eq(io.ib),
                io.oa.eq(asg[0] + self.pid.outs[0]),
                io.ob.eq(asg[1] + self.pid.outs[1])
        ]

        self.submodules.intercon = SysInterconnect(ps_sys,
                hk_sys, scope_sys, asg_sys, self.sys2wb.sys)
