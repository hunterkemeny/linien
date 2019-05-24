import os
import sys
import pickle
import _thread
import threading
from time import sleep, time
from rpyc import Service
from rpyc.utils.server import OneShotServer
from PyRedPitaya.board import RedPitaya

sys.path += ['../../']
from linie.config import ACQUISITION_PORT


class DataAcquisitionService(Service):
    def __init__(self):
        self.r = RedPitaya()

        self.data = pickle.dumps(None)
        self.data_retrieval_time = None

        super(DataAcquisitionService, self).__init__()

        self.set_ramp_speed(0)
        self.run()

    def run(self, trigger_delay=16384):
        self.r.scope.trigger_delay = trigger_delay

        def run_acquiry_loop():
            while True:
                # copied from https://github.com/RedPitaya/RedPitaya/blob/14cca62dd58f29826ee89f4b28901602f5cdb1d8/api/src/oscilloscope.c#L115
                # check whether scope was triggered
                if (self.r.scope.read(0x1<<2) & 0x4) > 0:
                    sleep(.05)
                    continue

                data = [
                    [float(i) for i in channel[:]]
                    for channel in
                    (self.r.scope.data_ch1, self.r.scope.data_ch2)
                ]
                self.r.scope.rearm(trigger_source=6)
                self.r.scope.data_decimation = 2 ** self.ramp_speed
                self.data = pickle.dumps(data)

                if self.data_retrieval_time is not None:
                    if time() - self.data_retrieval_time > 2:
                        # the parent process died, shut down this child process, too
                        _thread.interrupt_main()
                        os._exit(0)

        self.t = threading.Thread(target=run_acquiry_loop, args=())
        self.t.daemon = True
        self.t.start()

    def return_data(self):
        self.data_retrieval_time = time()
        return self.data[:]

    def set_asg_offset(self, idx, value):
        asg = getattr(self.r, ['asga', 'asgb'][idx])
        asg.offset = value

    def set_ramp_speed(self, speed):
        self.ramp_speed = speed

if __name__ == '__main__':
    t = OneShotServer(DataAcquisitionService(), port=ACQUISITION_PORT, protocol_config={
        'allow_all_attrs': True,
        'allow_setattr': True
    })
    t.start()