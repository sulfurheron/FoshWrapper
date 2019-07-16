from dialog_iot import FoshWrapper
import time
import struct
import sys
import signal

##subscribed functions
def accel_callback(handle, data):
    #ok handle of commands will be store in "handle"
    #and accelerometer data will be store in "data" as bytearray
    #_, sensor_state, sensor_event, x, y, z = struct.unpack('!3B3h', data)
    print("{}-> x:{} y:{} z:{}".format(device_id, float.fromhex(str(data[3])),
                                                  float.fromhex(str(data[4])),
                                                  float.fromhex(str(data[5]))))

device_id = str(sys.argv[1])

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
    fosh.disconnect()
    sys.exit(0)


