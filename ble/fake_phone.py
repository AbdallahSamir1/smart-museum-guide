"""Pretend a visitor's phone was detected (no Bluetooth hardware needed).
Run:  python -m ble.fake_phone U042 [127.0.0.1:5050]"""
import sys
import time

from network.client import GuideClient
from network.protocol import parse_server

uid = sys.argv[1] if len(sys.argv) > 1 else "U042"
host, port = parse_server(sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1:5050")
try:
    c = GuideClient("bluetooth", host, port)
except ConnectionError as e:
    raise SystemExit(f"{e} (run_full_system.bat starts it)")
c.visitor(uid)
print("arrived", uid)
time.sleep(1)
