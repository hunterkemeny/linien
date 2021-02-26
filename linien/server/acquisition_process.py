import os
import sys
import pickle
import _thread
import numpy as np
import threading
from rpyc import Service
from time import sleep
from random import random
from rpyc.utils.server import OneShotServer
from PyRedPitaya.board import RedPitaya

sys.path += ["../../"]
from csr import PythonCSR
from linien.config import ACQUISITION_PORT
from linien.common import DECIMATION, MAX_N_POINTS, N_POINTS


# the maximum decimation supported by the FPGA image
MAX_FPGA_DECIMATION = 65536


def shutdown():
    _thread.interrupt_main()
    os._exit(0)


def decimate(array, factor):
    if factor == 1:
        return array

    dtype = array.dtype
    return np.round(array.reshape(-1, factor).mean(axis=1)).astype(dtype)


class DataAcquisitionService(Service):
    def __init__(self):
        self.r = RedPitaya()
        self.csr = PythonCSR(self.r)
        self.csr_queue = []
        self.csr_iir_queue = []

        self.data = pickle.dumps(None)
        self.data_was_raw = False
        self.data_hash = None
        self.data_uuid = None
        self.additional_decimation = 1

        super(DataAcquisitionService, self).__init__()

        self.exposed_set_ramp_speed(9)
        self.locked = False
        # when self.locked is set to True, this doesn't mean that the lock is
        # really on. It just means that the lock is requested and that the
        # gateware waits until the sweep is at the correct position for the lock.
        # Therefore, when self.locked is set, the acquisition process waits for
        # confirmation from the gateware that the lock is actually running.
        self.confirmed_that_in_lock = False

        self.fetch_quadratures = True
        self.raw_acquisition_enabled = False
        self.raw_acquisition_decimation = 0

        self.acquisition_paused = False
        self.skip_next_data = False

        self.run()

    def run(self):
        def run_acquiry_loop():
            while True:
                while self.csr_queue:
                    key, value = self.csr_queue.pop(0)
                    self.csr.set(key, value)

                while self.csr_iir_queue:
                    args = self.csr_iir_queue.pop(0)
                    self.csr.set_iir(*args)

                if self.locked and not self.confirmed_that_in_lock:
                    self.confirmed_that_in_lock = self.csr.get(
                        "logic_autolock_lock_running"
                    )
                    if not self.confirmed_that_in_lock:
                        sleep(0.05)
                        continue

                if self.acquisition_paused:
                    sleep(0.05)
                    continue

                # copied from https://github.com/RedPitaya/RedPitaya/blob/14cca62dd58f29826ee89f4b28901602f5cdb1d8/api/src/oscilloscope.c#L115
                # check whether scope was triggered
                not_triggered = (self.r.scope.read(0x1 << 2) & 0x4) > 0
                if not_triggered:
                    sleep(0.05)
                    continue

                data, is_raw = self.read_data()

                if self.acquisition_paused:
                    # it may seem strange that we check this here a second time.
                    # Reason: `read_data` takes some time and if in the mean time
                    # acquisition was paused, we do not want to send the data
                    continue

                if self.skip_next_data:
                    self.skip_next_data = False
                else:
                    self.data = pickle.dumps(data)
                    self.data_was_raw = is_raw
                    self.data_hash = random()

                self.program_acquisition_and_rearm()

        self.t = threading.Thread(target=run_acquiry_loop, args=())
        self.t.daemon = True
        self.t.start()

    def program_acquisition_and_rearm(self, trigger_delay=16384):
        """Programs the acquisition settings and rearms acquisition."""
        if not self.locked:
            # we use decimation of the FPGA scope for two reasons:
            # - we want to record at lower scan rates
            # - we want to record less data points than 16384 data points.
            #   We could do this by additionally averaging in software, but
            #   this turned out to be too slow on the RP. Therefore, we
            #   let the FPGA do this.
            # With high values of DECIMATION and low scan rates, the required
            # decimation value exceeds the maximum value supported by the FPGA
            # image. Therefore, we perform additional software averaging in
            # these cases. As this happens for slow ramps only, the performance
            # hit doesn't matter.
            target_decimation = 2 ** (self.ramp_speed + int(np.log2(DECIMATION)))
            if target_decimation > MAX_FPGA_DECIMATION:
                self.additional_decimation = int(
                    target_decimation / MAX_FPGA_DECIMATION
                )
                target_decimation = MAX_FPGA_DECIMATION
            else:
                self.additional_decimation = 1

            self.r.scope.data_decimation = target_decimation
            self.r.scope.trigger_delay = (
                int(trigger_delay / DECIMATION * self.additional_decimation) - 1
            )

        elif self.raw_acquisition_enabled:
            self.r.scope.data_decimation = 2 ** self.raw_acquisition_decimation
            print("SET DEC", self.raw_acquisition_decimation)
            self.additional_decimation = 1
            self.r.scope.trigger_delay = trigger_delay

        else:
            self.r.scope.data_decimation = 1
            self.additional_decimation = 1
            self.r.scope.trigger_delay = int(trigger_delay / DECIMATION) - 1

        # trigger_source=6 means external trigger positive edge
        self.r.scope.rearm(trigger_source=6)

    def exposed_return_data(self, last_hash):
        no_data_available = self.data_hash is None
        data_not_changed = self.data_hash == last_hash
        if data_not_changed or no_data_available or self.acquisition_paused:
            return False, None, None, None, None
        else:
            return True, self.data_hash, self.data_was_raw, self.data, self.data_uuid

    def exposed_set_ramp_speed(self, speed):
        self.ramp_speed = speed

    def exposed_set_lock_status(self, locked):
        self.locked = locked
        self.confirmed_that_in_lock = False

    def exposed_set_fetch_quadratures(self, fetch):
        self.fetch_quadratures = fetch

    def exposed_set_raw_acquisition(self, data):
        self.raw_acquisition_enabled = data[0]
        self.raw_acquisition_decimation = data[1]

    def exposed_set_csr(self, key, value):
        self.csr_queue.append((key, value))

    def exposed_set_iir_csr(self, *args):
        self.csr_iir_queue.append(args)

    def exposed_pause_acquisition(self):
        self.acquisition_paused = True
        self.data_hash = None
        self.data = None

    def exposed_continue_acquisition(self, uuid):
        self.program_acquisition_and_rearm()
        sleep(0.01)
        # resetting data here is not strictly required but we want to be on the
        # safe side
        self.data_hash = None
        self.data = None
        self.acquisition_paused = False
        self.data_uuid = uuid
        self.skip_next_data = True

    def read_data(self):
        write_pointer = self.r.scope.write_pointer_trigger

        if self.raw_acquisition_enabled:
            return self.read_data_raw(0x10000, write_pointer, MAX_N_POINTS), True

        else:
            signals = []

            channel_offsets = [0x10000]
            if self.fetch_quadratures:
                channel_offsets.append(0x20000)

            for channel_offset in channel_offsets:
                channel_data = self.read_data_raw(
                    channel_offset, write_pointer, N_POINTS * self.additional_decimation
                )

                for sub_channel_idx in range(2):
                    signals.append(
                        decimate(
                            channel_data[sub_channel_idx], self.additional_decimation
                        )
                    )

            signals_named = {}

            if not self.locked:
                signals_named["error_signal_1"] = signals[0]
                signals_named["error_signal_2"] = signals[1]

                if self.fetch_quadratures and len(signals) >= 3:
                    signals_named["error_signal_1_quadrature"] = signals[2]
                    signals_named["error_signal_2_quadrature"] = signals[3]

            else:
                signals_named["error_signal"] = signals[0]
                signals_named["control_signal"] = signals[1]

            slow_out = self.csr.get("logic_slow_value")
            slow_out = slow_out if slow_out <= 8191 else slow_out - 16384
            signals_named["slow"] = slow_out

            return signals_named, False

    def read_data_raw(self, offset, addr, data_length):
        max_data_length = 16383
        if data_length + addr > max_data_length:
            to_read_later = data_length + addr - max_data_length
            data_length -= to_read_later
        else:
            to_read_later = 0

        # raw data contains two signals:
        #   2'h0,adc_b_rd,2'h0,adc_a_rd
        #   i.e.: 2 zero bits, channel b (14 bit), 2 zero bits, channel a (14 bit)
        # .copy() is required, because np.frombuffer returns a readonly array
        raw_data = self.r.scope.reads(offset + (4 * addr), data_length).copy()

        # raw_data is an array of 32-bit ints
        # we cast it to 16 bit --> each original int is split into two ints
        raw_data.dtype = np.int16

        # sign bit is at position 14, but we have 16 bit ints
        raw_data[raw_data >= 2 ** 13] -= 2 ** 14

        # order is such that we have first the signal a then signal b
        signals = tuple(raw_data[signal_idx::2] for signal_idx in (0, 1))

        if to_read_later > 0:
            additional_raw_data = self.read_data_raw(offset, 0, to_read_later)
            signals = tuple(
                np.append(signals[signal_idx], additional_raw_data[signal_idx])
                for signal_idx in range(2)
            )

        return signals


if __name__ == "__main__":
    t = OneShotServer(DataAcquisitionService(), port=ACQUISITION_PORT)
    t.start()
