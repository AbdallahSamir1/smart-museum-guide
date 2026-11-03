"""Tests the screen's web server (ui_web.py) without a hub, a camera or a browser:
the pages, the photos (also in parts, as browsers ask for them) and the live
event stream that moves the screen. Run: python -m tests.test_web"""
import http.client
import json
import os
import re
import socket
import threading
import time

from ui import ui_web

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)

ui_web.PING = 0.3                             # seconds; the real screen pings every 15 s
web = ui_web.WebServer(("127.0.0.1", 0), ui_web.Handler)
port = web.server_address[1]
threading.Thread(target=web.serve_forever, daemon=True).start()

def get(path, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r, body

def raw(request):
    """The whole answer, bytes as sent (the server closes the connection after it)."""
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(request.encode("ascii"))
    data = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()
    return data

def read_file(*parts):
    with open(os.path.join(ui_web.WEB, *parts), "rb") as f:
        return f.read()

# ---- the pages ----
for path, name in (("/", "index.html"), ("/index.html", "index.html"), ("/guide", "guide.html"),
                   ("/guide.html", "guide.html"), ("/guide?lang=ar", "guide.html")):
    r, body = get(path)
    page = read_file(name)
    check(f"{path} gives {name}", len(page) > 1000 and r.status == 200 and body == page
          and r.getheader("Content-Type") == "text/html; charset=utf-8"
          and r.getheader("Cache-Control") == "no-cache")
r, _ = get("/guide/?lang=ar")
check("/guide/ is sent on to /guide (so its links are found), the language is kept",
      r.status == 301 and r.getheader("Location") == "/guide?lang=ar")
r, body = get("/", {"Range": "bytes=0-9"})
check("a page is always sent whole", r.status == 200 and body == read_file("index.html"))
head = raw("HEAD / HTTP/1.0\r\n\r\n")
check("HEAD on a page: headers only", head.startswith(b"HTTP/1.0 200") and head.endswith(b"\r\n\r\n"))

# ---- photos, sent in parts as browsers ask for them ----
data = read_file("photos", "golden_mask.jpg")
size = len(data)
check("the photo exists (needed for the next checks)", size > 1000)
r, body = get("/photos/golden_mask.jpg")
check("a photo is sent whole as image/jpeg, says it can be read in parts, and is cached",
      r.status == 200 and body == data and r.getheader("Content-Type") == "image/jpeg"
      and r.getheader("Accept-Ranges") == "bytes" and r.getheader("Cache-Control") == "max-age=300")
r, body = get("/photos/golden_mask.jpg", {"Range": "bytes=0-99"})
check("Range bytes=0-99: 206 and the first 100 bytes",
      r.status == 206 and r.getheader("Content-Range") == f"bytes 0-99/{size}" and body == data[:100])
r, body = get("/photos/golden_mask.jpg", {"Range": "bytes=-500"})
check("Range bytes=-500: the last 500 bytes",
      r.status == 206 and r.getheader("Content-Range") == f"bytes {size - 500}-{size - 1}/{size}"
      and body == data[-500:])
r, body = get("/photos/golden_mask.jpg", {"Range": "bytes=100-"})
check("Range bytes=100-: from byte 100 to the end", r.status == 206 and body == data[100:])
r, body = get("/photos/golden_mask.jpg", {"Range": f"bytes={size}-"})
check("a range after the end of the file: 416 with the real size",
      r.status == 416 and r.getheader("Content-Range") == f"bytes */{size}" and body == b"")
r, body = get("/photos/golden_mask.jpg", {"Range": "bytes=50-10"})
check("a wrong range (end before start) is ignored: the whole video", r.status == 200 and body == data)
hdr, _, rest = raw("HEAD /photos/golden_mask.jpg HTTP/1.0\r\n\r\n").partition(b"\r\n\r\n")
check("HEAD on a photo: the headers with the size, no body",
      hdr.startswith(b"HTTP/1.0 200") and f"Content-Length: {size}".encode() in hdr and rest == b"")
guide = read_file("guide.html").decode("utf-8")
keys = re.search(r"const KEYS = \[([^\]]*)\]", guide).group(1)
names = re.findall(r'"([a-z_]+)"', keys)
check("the guide shows the seven gestures: wave, swipe left/right, thumb up/down, open palm, fist, and no moving up/down/circle",
      names == ["wave", "swipe_right", "swipe_left", "thumb_up", "thumb_down", "open_palm", "fist"]
      and not any(k in guide for k in ("swipe_up", "swipe_down", "circle", "<video")))
check("the guide has English, Arabic and French texts for every gesture",
      all(f'{k}: {{ name:' in guide for k in names) and guide.count("thumb_up: { name:") == 3)
br = ui_web.byte_range
check("byte_range reads the ranges browsers ask for",
      br(None, 1000) is None and br("bytes=0-99", 1000) == (0, 99) and br("bytes=990-5000", 1000) == (990, 999)
      and br("bytes=-500", 1000) == (500, 999) and br("bytes=-5000", 1000) == (0, 999)
      and br("bytes=1000-", 1000) == "bad" and br("bytes=-0", 1000) == "bad" and br("bytes=5-1", 1000) is None
      and br("bytes=0-1,5-9", 1000) is None and br("items=0-9", 1000) is None)

import json
credits = json.loads(read_file("photos", "CREDITS.json"))
r, body = get("/photos/golden_mask.jpg")
check("the exhibit photos are served, each with its licence and author in CREDITS.json",
      r.status == 200 and body[:2] == b"\xff\xd8" and len(credits) == 3
      and all(c["license"] and c["author"] and get(f"/photos/{n}")[0].status == 200 for n, c in credits.items()))
r, _ = get("/camera.jpg")
check("no camera picture yet: /camera.jpg is 404 (the page shows the drawing in the box)", r.status == 404)
ui_web.on_frame({"jpeg": "bm90IGEganBlZw=="})
check("a message that is not a JPEG is not shown", get("/camera.jpg")[0].status == 404)
import base64
jpeg = read_file("photos", "throne.jpg")
ui_web.on_frame({"jpeg": base64.b64encode(jpeg).decode()})
r, body = get("/camera.jpg")
check("a camera picture is shown in the box on screen 3 (/camera.jpg)",
      r.status == 200 and body == jpeg and r.getheader("Cache-Control") == "no-store")

# ---- nothing else can be read through the screen ----
bad = ("/photos/../ui_web.py", "/../server.py", "/photos/%2e%2e/ui_web.py", "/photos/x.exe",
       "/profiles.json", "/web/index.html", "/photos/nothing.jpg", "/photos/THRONE.JPG", "/events/x")
codes = [raw(f"GET {p} HTTP/1.0\r\n\r\n").split(b" ", 2)[1] for p in bad]
check("the code, the visitors' profiles.json and unknown paths give 404", codes == [b"404"] * len(bad))

# ---- the live event stream (what moves the screen) ----
def stream():
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(b"GET /events HTTP/1.0\r\n\r\n")
    return s

def read_until(s, *needles, wait=3.0):
    """What the stream sends until every needle has come (or the time is up)."""
    s.settimeout(0.1)
    text, end = "", time.time() + wait
    while time.time() < end and not all(n in text for n in needles):
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            break
        text += chunk.decode("utf-8")
    return text

check("nothing has come from the hub yet (the test starts clean)",
      ui_web.latest["state"] is None and not ui_web.latest["hub"] and ui_web.latest["progress"] is None)
a = stream()
first = read_until(a, "data: null")
check("the stream starts as an event stream that the page retries every 2 s",
      "Content-Type: text/event-stream" in first and "\r\n\r\nretry: 2000\n\n" in first)
check("a new page is told at once: hub not reached yet, no state yet",
      "event: hub\ndata: false\n\n" in first and "\n\ndata: null\n\n" in first
      and first.index("retry: 2000") < first.index("event: hub") < first.index("data: null"))
ui_web.on_progress({"pose": "thumb_up", "value": 0.5})
got = read_until(a, "event: progress")
check("how long a thumb up is held reaches the page (fills the ring)",
      'event: progress\ndata: {"pose": "thumb_up", "value": 0.5}\n\n' in got)
ui_web.on_link(True)
got = read_until(a, "event: hub")
check("the hub is reached: hub true", "event: hub\ndata: true\n\n" in got)
ui_web.on_link(False)
got = read_until(a, "event: hub")
check("the hub is lost: hub false (the page shows Reconnecting)", "event: hub\ndata: false\n\n" in got)
state = {"type": "state", "screen": 3, "highlight": "Throne"}
ui_web.on_state(state)
got = read_until(a, '"screen": 3')
check("a new state reaches the page", "data: " + json.dumps(state) + "\n\n" in got)
with ui_web.changed:                          # the last hold and the next screen come together
    ui_web.latest["progress"] = {"pose": "thumb_up", "value": 1.0}
    ui_web.latest["pversion"] += 1
    ui_web.latest["state"] = {"type": "state", "screen": 4}
    ui_web.latest["version"] += 1
    ui_web.changed.notify_all()
got = read_until(a, '"screen": 4', "event: progress")
check("hold and new screen together: the hold is sent first (no full ring on the new screen)",
      "event: progress" in got and '"screen": 4' in got and got.index("event: progress") < got.index('"screen": 4'))
got = read_until(a, ": ping", wait=2)
check("nothing new: a ping keeps the stream open", ": ping\n\n" in got)
b = stream()
got = read_until(b, '"screen": 4')
check("a page opened later gets the screen and the hub link at once, not an old hold",
      '"screen": 4' in got and "event: hub\ndata: false" in got and "event: progress" not in got)
ui_web.on_state({"type": "state", "screen": 5})
got_a, got_b = read_until(a, '"screen": 5'), read_until(b, '"screen": 5')
check("two pages open at once both get the new state", '"screen": 5' in got_a and '"screen": 5' in got_b)
before = threading.active_count()
a.close(); b.close()
end = time.time() + 3
while time.time() < end and threading.active_count() > before - 2:
    time.sleep(0.05)
check("closed pages free their threads within a few pings", threading.active_count() <= before - 2)

# ---- only one screen program per port ----
try:
    ui_web.WebServer(("127.0.0.1", port), ui_web.Handler).server_close()
    second = True
except OSError:
    second = False
check("a second screen program on the same port is refused", not second)
web.shutdown()
print("ALL PASS" if ok else "SOME FAILED")
