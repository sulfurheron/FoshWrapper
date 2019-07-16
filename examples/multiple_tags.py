import subprocess
from dialog_iot import FoshWrapper
import sys
import time

try:
  #connect to the device
  fosh = FoshWrapper()

  #show found devices, without connect
  #if someone wants to connect directly, just connect = True
  devices = fosh.find(device_name='IoT-DK-SFL', timeout=5)
  fosh.disconnect()

  if not devices:
      print("No Dialog BLE devices found!!!")
      exit()

  processes = []
  for device in devices:
    cmd = "python -u accelerometer.py " + device['address']
    p = subprocess.Popen(cmd, shell=True)
    processes.append(p)
    print("Connected to {}".format(device['address']))

  while True:
    time.sleep(0.5)

except KeyboardInterrupt as ke:
  print("Killing all processes")
  for p in processes:
    p.terminate()
  sys.exit(0)

