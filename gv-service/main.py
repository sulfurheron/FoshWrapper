import argparse
import collections
from concurrent import futures
import copy
from datetime import datetime
from enum import Enum
import logging
import multiprocessing
import os
from pprint import pprint
import queue
import struct
import time
import threading

from dialog_iot import FoshWrapper
from google.protobuf.timestamp_pb2 import Timestamp
import grpc
from orb.gv_stubs import gv_stubs_pb2
from orb.gv_stubs import gv_stubs_pb2_grpc


DEFAULTS = dict(
    GRPC_PORT="5065",
    AGGREGATE_PERIOD_SECONDS="0.25")

Config = collections.namedtuple(
    "Config",
    "grpc_port aggregate_period_seconds")


TIMEOUT_SECONDS = 5.0
ACCELEROMETER_SCALE = 2048

DIALOG_MAC_PREFIX = "80:EA:CA:"


class Sensor(Enum):
    ACCELEROMETER = 1
    BAROMETER = 2


class Scanner(multiprocessing.Process):
    def __init__(self, timeout_seconds, sensor_queue):
        super().__init__()

        self.timeout_seconds = timeout_seconds
        self.sensor_queue = sensor_queue
        self.procs = {}

    def run(self):
        fosh = FoshWrapper(reset=True)

        try:
            while True:
                for address, proc in list(self.procs.items()):
                    if not proc.is_alive():
                        print("[%s] Removing expired listener." % address)
                        self.procs.pop(address)

                devices = fosh.find(timeout=self.timeout_seconds)
                fosh.disconnect()

                for dev in devices:
                    address = dev["address"]

                    if not address.startswith(DIALOG_MAC_PREFIX):
                        continue

                    if address in self.procs:
                        print("[%s] Found device but already listening, recycling old listener." % address)
                        self.procs[address].terminate()
                    else:
                        print("[%s] Found device we're not yet listening to." % address)

                    p = Listener(
                        address=address,
                        timeout_seconds=self.timeout_seconds,
                        sensor_queue=self.sensor_queue)
                    self.procs[address] = p
                    print("[%s] Starting listener." % address)
                    p.start()

                time.sleep(6)
        except KeyboardInterrupt:
            pass

    def cleanup(self):
        print("Killing all processes.")
        for p in self.procs.values():
            p.terminate()

        
class Listener(multiprocessing.Process):
    def __init__(self, address, timeout_seconds, sensor_queue):
        super().__init__()

        self.address = address
        self.timeout_seconds = timeout_seconds
        self.sensor_queue = sensor_queue
        
    def run(self):
        try:
            print("[%s] Connecting." % self.address)
            fosh = FoshWrapper()
            fosh.connect(self.address)

            config = fosh.getConfig()
            #sensor_combination is accelerometer and Gyroscope
            fosh.config["sensor_combination"] = 3
            #accelerometer rate to 100Hz
            fosh.config["accelerometer_rate"] = 0x08
            #accelerometer range to +-8G
            fosh.config["accelerometer_range"] = 0x08

            #if config is not equal to the fosh.config just send it to the device
            if config != fosh.config:
                fosh.setConfig()

            #now we wants to get accelerometer data and response will be in f
            fosh.subscribe("accelerometer", self.accelerometer_callback)
            fosh.subscribe("barometer", self.barometer_callback)
            #send command for start!!!
            fosh.start()

            self.last_read = datetime.now()
            while True:
                time.sleep(1)

                if (datetime.now() - self.last_read).total_seconds() > self.timeout_seconds:
                    print("[%s] Timed out after no readings." % self.address)
                    break
        except Exception as ex:
            print("[%s] Exception occurred while listening: %s" % (self.address, ex))
        except KeyboardInterrupt:
            print("[%s] Cleaning up connection." % self.address)
        finally:
            fosh.disconnect()

    def accelerometer_callback(self, handle, data):
        self.last_read = datetime.now()

        x, y, z = struct.unpack("<3xhhh", data)
        x, y, z = x / ACCELEROMETER_SCALE, y / ACCELEROMETER_SCALE, z / ACCELEROMETER_SCALE
        magnitude = ((x ** 2) + (y ** 2) + (z ** 2)) ** 0.5
        logging.debug("[%s] %0.2f (%0.2f, %0.2f, %0.2f)" % (self.address, magnitude, x, y, z))
        # self.sensor_queue.put((self.address, Sensor.ACCELEROMETER, magnitude))
        self.sensor_queue.put((self.address, Sensor.ACCELEROMETER, (x, y, z)))

    def barometer_callback(self, handle, data):
        self.last_read = datetime.now()

        pressure = struct.unpack("<3xI", data)[0] / 100.0
        self.sensor_queue.put((self.address, Sensor.BAROMETER, pressure))


class Aggregator(threading.Thread):
    def __init__(self, sensor_queue):
        super().__init__()

        self.sensor_queue = sensor_queue
        self.state = {}
        self.state_lock = threading.Lock()
        self.stop_flag = False

    def run(self):
        while not self.stop_flag:
            event = None
            try:
                event = self.sensor_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            with self.state_lock:
                address, sensor, reading = event
                if address in self.state:
                    self.state[address][sensor] = reading
                else:
                    self.state[address] = {sensor: reading}

    def get_state(self):
        with self.state_lock:
            old_state = copy.copy(self.state)
            self.state.clear()
            return old_state

    def stop(self):
        self.stop_flag = True


class GraspVerificationServicer(gv_stubs_pb2_grpc.GraspVerificationServiceServicer):
    def __init__(self):
        self._event_queues = []
        self._stop_event = threading.Event()

        self.events_lock = threading.Lock()

    def add_event(self, event):
        logging.debug("Adding event: %s.", event)
        with self.events_lock:
            for event_queue in self._event_queues:
                event_queue.put_nowait(event)

    def stop(self):
        self._stop_event.set()

    def ReadSensorStream(self, _, __):
        # TODO Remove old queues when the client disconnects.
        my_queue = queue.Queue()
        with self.events_lock:
            self._event_queues.append(my_queue)

        while not self._stop_event.is_set():
            try:
                yield my_queue.get(timeout=1)
            except queue.Empty:
                # We'll retry, just giving ourselves a chance to check
                # for the stop event.
                pass


def broadcast_events(aggregator, servicer, aggregate_period_seconds):
    while True:
        time.sleep(aggregate_period_seconds)

        timestamp = Timestamp()
        timestamp.GetCurrentTime()
        event = gv_stubs_pb2.ReadSensorStreamResponse(
            timestamp=timestamp)

        all_states = aggregator.get_state()

        for address in sorted(all_states):
            dev_state = all_states[address]
            
            response_device = event.device.add()
            response_device.address = address

            if Sensor.ACCELEROMETER in dev_state:
                response_device.acceleration.x = dev_state[Sensor.ACCELEROMETER][0]
                response_device.acceleration.y = dev_state[Sensor.ACCELEROMETER][1]
                response_device.acceleration.z = dev_state[Sensor.ACCELEROMETER][2]

            if Sensor.BAROMETER in dev_state:
                response_device.pressure = dev_state[Sensor.BAROMETER]

        servicer.add_event(event)



def _get_env(name, cast):
    val = cast(os.environ.get(name, DEFAULTS[name]))
    logging.debug("%s=%s", name, val)
    return val


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="increase verbosity")

    logging.getLogger("pygatt").setLevel(logging.WARNING)
    
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    config = Config(
        grpc_port=_get_env("GRPC_PORT", int),
        aggregate_period_seconds=_get_env("AGGREGATE_PERIOD_SECONDS", float))

    sensor_queue = multiprocessing.Queue()

    aggregator = Aggregator(sensor_queue)
    aggregator.start()

    scanner = Scanner(timeout_seconds=TIMEOUT_SECONDS, sensor_queue=sensor_queue)
    scanner.start()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = GraspVerificationServicer()
    gv_stubs_pb2_grpc.add_GraspVerificationServiceServicer_to_server(
        servicer, server)
    server.add_insecure_port("[::]:%d" % config.grpc_port)
    server.start()

    try:
        broadcast_events(aggregator, servicer, config.aggregate_period_seconds)
    except KeyboardInterrupt:
        server.stop(0)
        servicer.stop()
        scanner.cleanup()
        aggregator.stop()


if __name__ == "__main__":
    main()
