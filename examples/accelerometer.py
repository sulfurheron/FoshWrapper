from dialog_iot import FoshWrapper
import time
import struct


##subscribed functions
def accel_1_callback(handle, data):
    #ok handle of commands will be store in "handle"
    #and accelerometer data will be store in "data" as bytearray
    _, sensor_state, sensor_event, x, y, z = struct.unpack('>3B3H', data)
    print("1-> x:{} y:{} z:{}".format(x, y, z))

def accel_2_callback(handle, data):
    #ok handle of commands will be store in "handle"
    #and accelerometer data will be store in "data" as bytearray
    _, sensor_state, sensor_event, x, y, z = struct.unpack('>3B3H', data)
    print("2-> x:{} y:{} z:{}".format(x, y, z))

#connect to the device
fosh = FoshWrapper()

#show found devices, without connect
#if someone wants to connect directly, just connect = True
devices = fosh.find(device_name='IoT-DK-SFL')

if not devices:
    print("No Dialog BLE devices found!!!")
    exit()

#ok connect to the specific device via mac address
fosh_connections = []
try:
    for d in devices:
        fosh = FoshWrapper()
        fosh.connect(d['address'])
        fosh_connections.append(fosh)
except Exception as e:
    print(e) #error time :D
    exit()

callbacks = [accel_1_callback, accel_2_callback]

#load configuration from Iot device
for num, fosh in enumerate(fosh_connections):
    config = fosh.getConfig()
    #sensor_combination is accelerometer and Gyroscope
    fosh.config['sensor_combination'] = 3
    #accelerometer rate to 100Hz
    fosh.config['accelerometer_rate'] = 0x08

    #if config is not equal to the fosh.config just send it to the device
    if config != fosh.config:
        fosh.setConfig()    #set config and also store this configuration in eeprom
        #fosh.setConfig(False) #set config without storing it in eeprom

    #now we wants to get accelerometer data and response will be in f
    fosh.subscribe('accelerometer', callbacks[num])
    #send command for start!!!
    fosh.start()

#ok we have to w8 for accelerometer data which will be 
#in accelerometer_data_callback
while 1:
    time.sleep(2)
