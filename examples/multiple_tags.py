from pprint import pprint
import subprocess
import time

from dialog_iot import FoshWrapper


DIALOG_MAC_PREFIX = "80:EA:CA:"

procs = {}


def scan_and_connect():
    global procs

    fosh = FoshWrapper(reset=True)

    while True:
        for address, proc in list(procs.items()):
            proc.poll()
            if proc.returncode is not None:
                print("[%s] Removing expired listener." % address)
                procs.pop(address)

        devices = fosh.find(timeout=5)
        fosh.disconnect()

        for dev in devices:
            address = dev["address"]
            
            if not address.startswith(DIALOG_MAC_PREFIX):
                continue

            if address in procs:
                print("[%s] Found device but already listening." % address)
                procs[address].terminate()
            else:
                print("[%s] Found device we're not yet listening to." % address)
            
            cmd = "python -u listener.py " + address
            p = subprocess.Popen(cmd, shell=True)
            procs[address] = p
            print("[%s] Starting listener." % address)

        time.sleep(6)


def main():
    try:
        scan_and_connect()
    except KeyboardInterrupt:
        print("Killing all processes.")
        for p in procs.values():
            p.terminate()


if __name__ == "__main__":
    main()
