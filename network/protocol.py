"""Tiny message protocol shared by every part of the project.
One JSON object per line over a TCP socket.

Client -> server
  {"type": "hello", "role": "gesture" | "ui" | "camera" | "bluetooth" | "context" | "demo"}
  {"type": "gesture", "name": "wave" | "swipe_left" | "swipe_right" | "confirm" | "back" |
                              "pause_toggle" | "finish" | "hand_lost" | "hand_found"}
                   (confirm = thumb up held, back = thumb down, pause_toggle = open palm,
                    finish = fist held)
  {"type": "progress", "pose": "thumb_up" | "fist" | None, "value": 0..1}
                                                   (how long a thumb up / fist has been held, from the camera)
  {"type": "frame", "jpeg": base64}                (camera picture for screen 3, role "gesture")
  {"type": "exhibits", "items": [{"name": str, "conf": float, "distance": float}, ...]}
  {"type": "visitor", "user_id": str}              (from Bluetooth, step 6)
  {"type": "context", "view": "day" | "evening"}   (clock / light level)
  {"type": "get"}                                  (send me the state now)
Server -> clients
  {"type": "state", ...}   the full state of the guide, sent after every change
  {"type": "progress", ...} / {"type": "tip", ...}  passed on to the "ui" clients only
  {"type": "frame", ...}   passed on to the "video" clients only
"""
import json
import os
import socket

MAX_LINE = 1_000_000          # bytes; a longer line without a newline is thrown away


def send(sock, msg):
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))


def read_lines(sock):
    """Generator yielding decoded messages (JSON objects) until the socket closes."""
    buf = b""
    while True:
        try:
            chunk = sock.recv(65536)
        except OSError:
            return
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line.strip():
                try:
                    msg = json.loads(line.decode("utf-8"))
                except ValueError:
                    continue
                if isinstance(msg, dict):            # [1, 2] or "text" is not a message
                    yield msg
        if len(buf) > MAX_LINE:
            buf = b""


def parse_server(text):
    """'127.0.0.1:5050' -> ("127.0.0.1", 5050). A wrong value stops the program with a
    message that says how it should look, instead of a Python error."""
    host, _, port = (text or "").strip().rpartition(":")
    if not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise SystemExit(f"--server must look like 127.0.0.1:5050 (got {text!r})")
    return host, int(port)


def no_quick_edit():
    """Windows: a click inside a black console window starts selecting text ("QuickEdit")
    and pauses the program until Esc is pressed, so the camera or the hub looks frozen.
    This turns QuickEdit off for the window. Nothing happens elsewhere or without a console."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.WinDLL("kernel32")
        k.GetStdHandle.restype = ctypes.c_void_p
        h = ctypes.c_void_p(k.GetStdHandle(-10))     # the console input
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, (mode.value | 0x80) & ~0x40)   # extended flags on, QuickEdit off
    except Exception:
        pass


def exclusive(sock):
    """Only one program may listen on the port. On Windows SO_REUSEADDR lets a second
    hub (or screen) start on a port that is already used, and the clients are then
    split between the two, so the port is reserved with SO_EXCLUSIVEADDRUSE there.
    A restart right after closing still works on Windows."""
    if os.name == "nt":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
