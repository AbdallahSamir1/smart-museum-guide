"""Client used by any part of the project to talk to the hub.

The parts can be started in any order: a new client waits up to `wait` seconds
for the hub, and if the hub is closed and started again the client connects
again by itself. While the hub cannot be reached, messages are dropped (with
one warning) instead of crashing the program that sends them.
"""
import socket
import sys
import threading
import time

from network.protocol import read_lines, send


class GuideClient:
    def __init__(self, role, host="127.0.0.1", port=5050, on_state=None, wait=10.0,
                 reconnect=True, on_progress=None, on_link=None, on_tip=None, on_frame=None):
        self.role, self.addr = role, (host, port)
        self.on_state = on_state
        self.on_progress = on_progress               # hold progress, only sent to "ui" clients
        self.on_link = on_link                       # told True / False when the hub is reached / lost
        self.on_tip = on_tip                         # why a movement was not a command ("ui" clients)
        self.on_frame = on_frame                     # camera pictures ("video" clients)
        self.last_state = None
        self.reconnect = reconnect
        self.closed = False
        self.warned = False
        self.lock = threading.Lock()                 # one message at a time on the socket
        self.sock = self._connect(wait)
        if self.sock is None:
            raise ConnectionError(f"cannot reach the guide hub at {host}:{port}. "
                                  "Start server.py first.")
        self._link(True)
        threading.Thread(target=self._listen, daemon=True).start()

    def _link(self, up):
        if self.on_link:
            try:
                self.on_link(up)
            except Exception as e:
                print(f"[{self.role}] error while showing the link to the hub: {e!r}", file=sys.stderr)

    def _connect(self, wait):
        end = time.time() + wait
        while not self.closed:
            try:
                sock = socket.create_connection(self.addr, timeout=2)
                sock.settimeout(None)
                send(sock, {"type": "hello", "role": self.role})
                return sock
            except OSError:
                if time.time() >= end:
                    return None
                time.sleep(0.5)
        return None

    def _listen(self):
        while True:
            for msg in read_lines(self.sock):
                kind = msg.get("type")
                if kind == "state":
                    self.last_state = msg
                    if self.on_state:
                        try:
                            self.on_state(msg)
                        except Exception as e:      # a bad callback must not stop the client
                            print(f"[{self.role}] error while showing a state: {e!r}", file=sys.stderr)
                else:
                    call = {"progress": self.on_progress, "tip": self.on_tip, "frame": self.on_frame}.get(kind)
                    if call:
                        try:
                            call(msg)
                        except Exception as e:
                            print(f"[{self.role}] error while showing {kind}: {e!r}", file=sys.stderr)
            if self.closed:
                return
            self._link(False)
            if not self.reconnect:
                return
            print(f"[{self.role}] lost the hub at {self.addr[0]}:{self.addr[1]}, trying again ...",
                  file=sys.stderr)
            sock = None
            while sock is None and not self.closed:
                sock = self._connect(5.0)
            if sock is None:
                return
            with self.lock:
                old, self.sock = self.sock, sock
            try:
                old.close()
            except OSError:
                pass
            self.warned = False
            self._link(True)
            print(f"[{self.role}] connected to the hub again", file=sys.stderr)

    def _send(self, msg):
        try:
            with self.lock:
                send(self.sock, msg)
            return True
        except OSError:
            if not self.warned:
                self.warned = True
                print(f"[{self.role}] the hub cannot be reached, messages are not sent until it is back",
                      file=sys.stderr)
            return False

    def gesture(self, name):
        return self._send({"type": "gesture", "name": name})

    def progress(self, pose, value):
        """How far the visitor has held a pose (0..1), shown as a filling ring."""
        return self._send({"type": "progress", "pose": pose, "value": round(value, 3)})

    def tip(self, key):
        """Why the last movement was not a command, e.g. "too_slow" (a tip on the screen)."""
        return self._send({"type": "tip", "key": key})

    def frame(self, jpeg_b64):
        """A small camera picture (JPEG, base64) for the box on screen 3."""
        return self._send({"type": "frame", "jpeg": jpeg_b64})

    def exhibits(self, items):
        return self._send({"type": "exhibits", "items": items})

    def visitor(self, user_id):
        return self._send({"type": "visitor", "user_id": user_id})

    def context(self, view):
        return self._send({"type": "context", "view": view})

    def get(self):
        """Ask the hub to send the current state now."""
        return self._send({"type": "get"})

    def close(self):
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)     # wakes the listening thread
        except OSError:
            pass
        self.sock.close()
