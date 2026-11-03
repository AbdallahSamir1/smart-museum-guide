"""The guide's screen in a web browser, fed live by the hub over a socket.

    python -m ui.ui_web --server 127.0.0.1:5050 --port 8000
then open http://127.0.0.1:8000 (full screen with F11 on the hall screen).
The page redraws itself every time the hub sends a new state, using the
content chosen by context.py (language, visitor type, Woman/Man, Day/Evening).
The gesture guide is at http://127.0.0.1:8000/guide
(web/guide.html, which also opens by double-clicking the file).
The live camera picture (with the hand path) for the box on screen 3 is at
/camera.mjpg (a stream) and /camera.jpg (the newest picture).
"""
import argparse
import base64
import binascii
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from network.client import GuideClient
from network.protocol import exclusive, no_quick_edit, parse_server

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
PAGES = {"/": "index.html", "/index.html": "index.html",
         "/guide": "guide.html", "/guide.html": "guide.html"}
MEDIA = re.compile(r"^/(videos|photos|icons)/([a-z0-9_]+\.(mp4|jpg|png|svg))$")
TYPES = {"html": "text/html; charset=utf-8", "mp4": "video/mp4",
         "jpg": "image/jpeg", "png": "image/png", "svg": "image/svg+xml"}
CAMERA_GONE = 2.0    # seconds without a picture: the box on screen 3 shows its drawing again
PING = 15            # seconds; a comment line keeps the event stream open and finds closed tabs
latest = {"state": None, "version": 0, "progress": None, "pversion": 0, "hub": False, "hversion": 0,
          "tip": None, "tversion": 0, "camera": False, "cversion": 0}
changed = threading.Condition()
camera = {"jpeg": None, "n": 0, "t": 0.0}       # newest camera picture (bytes)
camera_cv = threading.Condition()


def on_state(st):
    with changed:
        latest["state"] = st
        latest["version"] += 1
        changed.notify_all()


def on_progress(msg):
    """How far the visitor has held the current pose, 0..1 (fills the ring on the screen)."""
    with changed:
        latest["progress"] = {"pose": msg.get("pose"), "value": msg.get("value", 0)}
        latest["pversion"] += 1
        changed.notify_all()


def on_tip(msg):
    """Why the last movement was not a command ("too_slow", ...): a short tip on the page."""
    key = msg.get("key")
    if isinstance(key, str) and key.isidentifier():
        with changed:
            latest["tip"] = key
            latest["tversion"] += 1
            changed.notify_all()


def set_camera(on):
    with changed:
        if latest["camera"] != on:
            latest["camera"] = on
            latest["cversion"] += 1
            changed.notify_all()


def on_frame(msg):
    try:
        jpeg = base64.b64decode(msg.get("jpeg", ""), validate=True)
    except (binascii.Error, ValueError, TypeError):
        return
    if not jpeg.startswith(b"\xff\xd8"):
        return                                   # not a JPEG
    with camera_cv:
        camera.update(jpeg=jpeg, n=camera["n"] + 1, t=time.monotonic())
        camera_cv.notify_all()
    set_camera(True)


def camera_watch():
    """No picture for CAMERA_GONE seconds (the camera program stopped, or the guide left
    screen 3): the page shows the drawing in the box again."""
    while True:
        time.sleep(0.5)
        if latest["camera"] and time.monotonic() - camera["t"] > CAMERA_GONE:
            set_camera(False)


def on_link(up):
    """The hub was reached (True) or lost (False). While it is lost the page keeps the
    last picture and shows "Reconnecting to the guide…" over it."""
    with changed:
        latest["hub"] = bool(up)
        latest["hversion"] += 1
        changed.notify_all()


def byte_range(header, size):
    """(start, end) asked by a Range header, None for the whole file, "bad" when the
    range is outside the file. Browsers ask for ranges to seek in and loop the videos."""
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", (header or "").strip())
    if not m or m.group(1) == m.group(2) == "":
        return None                          # no header, or one we do not read: whole file
    a, b = m.groups()
    if a:
        start = int(a)
        if b and int(b) < start:
            return None                      # invalid, so the header is ignored (RFC 7233)
        if start >= size:
            return "bad"
        end = min(int(b), size - 1) if b else size - 1
        return start, end
    n = int(b)                               # "bytes=-500": the last 500 bytes
    if n == 0:
        return "bad"
    return max(size - n, 0), size - 1


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.route(head=False)

    def do_HEAD(self):
        self.route(head=True)

    def route(self, head):
        url = urlsplit(self.path)            # "/guide?lang=ar" -> "/guide"
        if url.path == "/events" and not head:
            return self.events()
        if url.path == "/guide/":            # the page links to "videos/...", relative to /guide
            self.send_response(301)
            self.send_header("Location", "/guide" + ("?" + url.query if url.query else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if url.path in PAGES:
            return self.send_file(PAGES[url.path], head)
        if url.path == "/camera.mjpg" and not head:
            return self.camera_stream()
        if url.path == "/camera.jpg":
            return self.camera_still(head)
        m = MEDIA.match(url.path)
        if m:
            return self.send_file(os.path.join(m.group(1), m.group(2)), head)
        self.send_error(404)

    def send_file(self, name, head):
        file = os.path.join(WEB, name)
        if not os.path.isfile(file):
            self.send_error(404)
            return
        ext = name.rsplit(".", 1)[1]
        media = ext != "html"
        size = os.path.getsize(file)
        rng = byte_range(self.headers.get("Range"), size) if media else None
        if rng == "bad":
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        start, end = rng or (0, size - 1)
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", TYPES[ext])
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "max-age=300" if media else "no-cache")
        if media:
            self.send_header("Accept-Ranges", "bytes")
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head:
            return
        try:
            with open(file, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except ConnectionError:              # the browser stopped reading (seek, page closed)
            pass

    def camera_still(self, head):
        jpeg = camera["jpeg"]
        if jpeg is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpeg)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(jpeg)

    def camera_stream(self):
        """The camera pictures as an MJPEG stream (an <img> shows it like a video)."""
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        seen = -1
        try:
            while True:
                with camera_cv:
                    camera_cv.wait_for(lambda: camera["n"] != seen and camera["jpeg"] is not None, timeout=PING)
                    jpeg, n = camera["jpeg"], camera["n"]
                if jpeg is None or n == seen:
                    continue
                seen = n
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                self.wfile.flush()
        except (ConnectionError, OSError):
            return

    def events(self):
        """Server-sent events: the state after every change, the hold progress
        as "progress" events, "hub" events (true/false) when the hub is reached or lost,
        "camera" events (true/false) when the camera picture starts or stops, "tip"
        events, and a ping when nothing happens. When the last hold and a new state arrive
        together, the hold goes first: it belongs to the old screen (the page empties
        the ring when the screen changes), so it is not painted on the new one."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with changed:
            pseen = latest["pversion"]       # an old hold is not news for a page opened now
            tseen = latest["tversion"]       # nor an old tip
        seen = hseen = cseen = -1
        try:
            self.wfile.write(b"retry: 2000\n\n")      # if this program stops, the page tries again every 2 s
            while True:
                with changed:
                    changed.wait_for(lambda: latest["version"] != seen or latest["pversion"] != pseen
                                     or latest["hversion"] != hseen or latest["tversion"] != tseen
                                     or latest["cversion"] != cseen, timeout=PING)
                    st, version = latest["state"], latest["version"]
                    prog, pversion = latest["progress"], latest["pversion"]
                    hub, hversion = latest["hub"], latest["hversion"]
                tip, tversion = latest["tip"], latest["tversion"]
                cam, cversion = latest["camera"], latest["cversion"]
                out = ""
                if cversion != cseen:
                    out += f"event: camera\ndata: {'true' if cam else 'false'}\n\n"
                    cseen = cversion
                if tversion != tseen:
                    out += f"event: tip\ndata: {json.dumps(tip)}\n\n"
                    tseen = tversion
                if hversion != hseen:
                    out += f"event: hub\ndata: {'true' if hub else 'false'}\n\n"
                    hseen = hversion
                if pversion != pseen:
                    out += f"event: progress\ndata: {json.dumps(prog)}\n\n"
                    pseen = pversion
                if version != seen:
                    out += f"data: {json.dumps(st) if st else 'null'}\n\n"
                    seen = version
                self.wfile.write((out or ": ping\n\n").encode("utf-8"))
                self.wfile.flush()
        except (ConnectionError, OSError):
            return


class WebServer(ThreadingHTTPServer):
    allow_reuse_address = False              # exclusive() decides, see protocol.py

    def server_bind(self):
        exclusive(self.socket)
        super().server_bind()


def connect_hub(host, port):
    """Keep trying until the hub answers, so the page can be opened before the hub.
    A second connection ("video") brings the camera pictures, so they never hold up
    the state."""
    while True:
        try:
            client = GuideClient("ui", host, port, on_state=on_state, on_progress=on_progress,
                                 on_link=on_link, on_tip=on_tip, wait=5)
            client.get()                                  # ask for the current state now
            print("Connected to the guide hub")
            break
        except OSError:
            print(f"Waiting for the guide hub at {host}:{port} (start server.py) ...")
    while True:
        try:
            video = GuideClient("video", host, port, on_frame=on_frame, wait=5)
            return client, video
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="127.0.0.1:5050")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    host, port = parse_server(args.server)
    no_quick_edit()
    try:
        web = WebServer(("127.0.0.1", args.port), Handler)
    except OSError:
        print(f"Port {args.port} is already used: the guide screen may already be running "
              f"(open http://127.0.0.1:{args.port}), or start this one with --port 8001.")
        raise SystemExit(1)
    threading.Thread(target=connect_hub, args=(host, port), daemon=True).start()
    threading.Thread(target=camera_watch, daemon=True).start()
    print(f"Open http://127.0.0.1:{args.port}   (gesture guide: http://127.0.0.1:{args.port}/guide)")
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
