from dialog_iot import FoshWrapper
import time
import struct
import sys
import signal
from statistics import mean

ACCELEROMETER_SCALE = 2048


def littleEndianToInt8(data, offset):
    x = littleEndianToUint8(data, offset)
    if x & 0x80:
        x = x - 256
    return x

def littleEndianToUint8(data, offset):
    return data[offset]

def littleEndianToInt16(data, offset):
    return (littleEndianToInt8(data, offset + 1) << 8) + littleEndianToUint8(data, offset)

##subscribed functions
def accel_callback(handle, data):
    #ok handle of commands will be store in "handle"
    #and accelerometer data will be store in "data" as bytearray
    #_, sensor_state, sensor_event, x, y, z = struct.unpack('!3B3h', data)
    x, y, z = struct.unpack("<3xhhh", data)
    x, y, z = x / ACCELEROMETER_SCALE, y / ACCELEROMETER_SCALE, z / ACCELEROMETER_SCALE
    magnitude = ((x ** 2) + (y ** 2) + (z ** 2)) ** 0.5
    print("[%s] %0.2f (%0.2f, %0.2f, %0.2f)" % (device_id, magnitude, x, y, z))
    # global FIRST_PRINT, ax_rec, ay_rec, az_rec
    # if FIRST_PRINT:
    #     print("Receiving data from {}".format(device_id))
    #     FIRST_PRINT = False
    # if abs(ax)>=MOVEMENT_THRESHOLD and abs(ay)>=MOVEMENT_THRESHOLD:
    #     print("Device {} is moving".format(device_id))
    #     ax_rec.append(abs(ax))
    #     ay_rec.append(abs(ay))
    #     az_rec.append(abs(az))
    #     #print("{}-> x:{} y:{} z:{}".format(device_id, ax, ay, az))

MAP={"8B":1, "60":2, "54":3, "ED":4, "9F":5}
#Averages are ax:3.943337180397727 ay:4.521883877840909 az:4.1067116477272725
MOVEMENT_THRESHOLD = 3.5
FIRST_PRINT = True
device_id = str(sys.argv[1])
ax_rec, ay_rec, az_rec = [], [], []

try:
    print("Connecting to {}".format(device_id))
    fosh = FoshWrapper()
    fosh.connect(device_id)

    #load configuration from Iot device
    config = fosh.getConfig()
    #sensor_combination is accelerometer and Gyroscope
    fosh.config['sensor_combination'] = 3
    #accelerometer rate to 100Hz
    fosh.config['accelerometer_rate'] = 0x08
    #accelerometer range to +-8G
    fosh.config['accelerometer_range'] = 0x08

    #if config is not equal to the fosh.config just send it to the device
    if config != fosh.config:
        fosh.setConfig()    #set config and also store this configuration in eeprom
        fosh.setConfig(False) #set config without storing it in eeprom

    #now we wants to get accelerometer data and response will be in f
    fosh.subscribe('accelerometer', accel_callback)
    #send command for start!!!
    fosh.start()

    #ok we have to w8 for accelerometer data which will be
    #in accelerometer_data_callback
    while True:
        time.sleep(0.5)
except Exception as e:
    print(e) #error time :D
    fosh.disconnect()
    sys.exit(0)
except KeyboardInterrupt as ke:
    print("\nCleaning up connection on device {}!".format(device_id))
    #print("Averages are ax:{} ay:{} az:{}".format(mean(ax_rec), mean(ay_rec), mean(az_rec)))
    fosh.disconnect()
    sys.exit(0)

