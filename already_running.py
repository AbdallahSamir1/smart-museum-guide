"""Stops a second copy of the guide. run_full_system.bat and run_demo_mona.bat call this first:
if the hub (port 5050) or the screen (port 8000) already answers, an older copy is still running
in its black windows, and a new copy would only half start and mix with it (the new screen
would show the old hub). Exit code 1 in that case. Run: python already_running.py"""
import socket
import sys

PORTS = (5050, 8000)          # the default ports of server.py and ui_web.py

busy = []
for port in PORTS:
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            busy.append(str(port))
if busy:
    print(f"The guide is already running: port {' and '.join(busy)} is in use.")
    print("Close its black windows first (Guide hub, Guide screen, Bluetooth visitors, Camera gestures),")
    print("then double-click this file again.")
    sys.exit(1)
