"""The hub. Every part of the project connects to it with a TCP socket:
camera (object detection), gesture client, Bluetooth, the Day/Evening sensor
and the UI screens.

Run:  python -m network.server [port]        (default port 5050)

The hub also ends a visit that nobody is using any more (no hand for IDLE_AFTER
seconds, STORY_IDLE_AFTER while a story is playing), and while no sensor reports
the Day/Evening view it follows the clock between visits.
"""
import os
import socket
import sys
import threading
import time

from context.resolver import ContextResolver, decide_view
from ble.profiles import ProfileStore
from network.protocol import exclusive, no_quick_edit, read_lines, send
from network.state import GuideState

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_FRAME = 400_000        # characters of base64: a camera picture for screen 3 is about 15 000
IDLE_AFTER = 60            # seconds without a hand before the visit ends by itself
STORY_IDLE_AFTER = 180     # while a story plays: the visitor may lower the hand to listen


class PortInUse(OSError):
    pass


def local_hour():
    return time.localtime().tm_hour


class Hub:
    def __init__(self, host="127.0.0.1", port=5050, profiles=os.path.join(os.path.dirname(HERE), "ble", "profiles.json"),
                 idle_after=IDLE_AFTER, story_idle_after=STORY_IDLE_AFTER, tick=1.0,
                 hour=local_hour):
        self.state = GuideState(ProfileStore(profiles), ContextResolver())
        self.hour = hour
        self.state.view = decide_view(hour())       # the clock decides until a client reports it
        self.clock_view = True
        self.idle_after, self.story_idle_after, self.tick = idle_after, story_idle_after, tick
        self.away_since = None                      # when the hand was lost (time.monotonic())
        self.lock = threading.Lock()
        self.clients = {}                 # socket -> role
        self.frame, self.frame_n = None, 0          # newest camera picture, for the "video" clients
        self.frame_cv = threading.Condition()       # its own lock: pictures never wait for the state
        self.srv = socket.socket()
        exclusive(self.srv)
        try:
            self.srv.bind((host, port))
        except OSError as e:
            self.srv.close()
            raise PortInUse(f"port {port} is already used") from e
        self.srv.listen()
        self.port = self.srv.getsockname()[1]
        self.running = True

    def serve_forever(self):
        threading.Thread(target=self._ticker, daemon=True).start()
        while self.running:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                if not self.running:
                    break
                time.sleep(0.1)                     # a passing error must not stop the hub
                continue
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.running = False
        self.srv.close()
        with self.frame_cv:
            self.frame_cv.notify_all()
        with self.lock:
            socks = list(self.clients)
        for c in socks:
            try:
                c.shutdown(socket.SHUT_RDWR)
                c.close()
            except OSError:
                pass

    def broadcast(self):
        snap = self.state.snapshot()
        for c, role in list(self.clients.items()):
            if role == "video":
                continue                            # only pictures go to them (from their own thread)
            try:
                send(c, snap)
            except OSError:
                self.clients.pop(c, None)

    def relay(self, msg):
        """From the camera, passed on to the screens only (not a change of state):
        "progress" how long a thumb up or fist has been held (up to about 25 a second), and "tip"
        (kept for older clients; the camera does not send tips any more)."""
        if msg.get("type") == "tip":
            key = msg.get("key")
            if not isinstance(key, str) or not key.isidentifier() or len(key) > 40:
                return
            out = {"type": "tip", "key": key}
        else:
            value = msg.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return
            pose = msg.get("pose") if isinstance(msg.get("pose"), str) else None
            out = {"type": "progress", "pose": pose, "value": max(0.0, min(1.0, float(value)))}
        for c, role in list(self.clients.items()):
            if role == "ui":
                try:
                    send(c, out)
                except OSError:
                    self.clients.pop(c, None)

    def new_frame(self, msg):
        """A camera picture from the gesture program (about 12 a second on screen 3)."""
        jpeg = msg.get("jpeg")
        if not isinstance(jpeg, str) or not 0 < len(jpeg) <= MAX_FRAME:
            return
        with self.frame_cv:
            self.frame = {"type": "frame", "jpeg": jpeg}
            self.frame_n += 1
            self.frame_cv.notify_all()

    def video_sender(self, conn):
        """One thread for each "video" client: it always gets the newest picture, a slow
        one simply misses some, and nobody else waits for it."""
        seen = self.frame_n
        while self.running and self.clients.get(conn) == "video":
            with self.frame_cv:
                self.frame_cv.wait_for(lambda: self.frame_n != seen or not self.running, timeout=2)
                msg, n = self.frame, self.frame_n
            if n == seen or msg is None:
                continue
            seen = n
            try:
                send(conn, msg)
            except OSError:
                return

    def on_message(self, conn, msg):
        """Apply one message. Returns True if the clients must get the new state."""
        st = self.state
        kind = msg.get("type")
        if kind == "hello":
            role = str(msg.get("role", "unknown"))
            if role == "video" and self.clients.get(conn) != "video":
                self.clients[conn] = role
                threading.Thread(target=self.video_sender, args=(conn,), daemon=True).start()
                return False
            self.clients[conn] = role
        elif kind == "gesture":
            st.gesture(msg.get("name", ""))
            if st.hand or (st.screen == 1 and not st.started):
                self.away_since = None
            elif self.away_since is None:
                self.away_since = time.monotonic()
        elif kind in ("progress", "tip"):
            self.relay(msg)
            return False
        elif kind == "exhibits":
            st.set_exhibits(msg.get("items", []))
        elif kind == "visitor":
            st.set_user(msg.get("user_id"))
        elif kind == "context":
            if msg.get("view") in ("day", "evening"):
                st.set_context(msg["view"])
                self.clock_view = False             # a sensor (or the demo) decides from now on
        elif kind != "get":                         # "get": just send the current state
            return False
        return True

    def handle(self, conn):
        with self.lock:
            self.clients[conn] = "unknown"
        try:
            for msg in read_lines(conn):
                if msg.get("type") == "frame":
                    self.new_frame(msg)                 # not under the lock: pictures are many
                    continue
                with self.lock:
                    try:
                        if self.on_message(conn, msg):
                            self.broadcast()
                    except Exception as e:          # one bad message must not stop the hub
                        print(f"hub: message {str(msg)[:200]} failed: {e!r}", file=sys.stderr)
        finally:
            with self.lock:
                role = self.clients.pop(conn, None)
                if role == "gesture" and self.running and "gesture" not in self.clients.values():
                    # the camera program was closed or crashed: the hand dot turns grey
                    try:
                        if self.on_message(conn, {"type": "gesture", "name": "hand_lost"}):
                            self.broadcast()
                    except Exception as e:
                        print(f"hub: {e!r}", file=sys.stderr)
            conn.close()

    def _ticker(self):
        """Every `tick` seconds: end a visit nobody is using any more, and follow the
        clock for Day/Evening while no sensor reports it."""
        while self.running:
            time.sleep(self.tick)
            ended = False
            with self.lock:
                try:
                    ended = self._idle_check()
                    turned = self._clock_check()
                    if ended or turned:
                        self.broadcast()
                except Exception as e:
                    print(f"hub: timer failed: {e!r}", file=sys.stderr)
            if ended:
                print(f"[{time.strftime('%H:%M:%S')}] nobody in front of the screen: "
                      "the visit ended, back to the welcome screen")

    def _idle_check(self):
        if self.away_since is None:
            return False
        st = self.state
        story = st.screen == 5 and not st.paused
        limit = self.story_idle_after if story else self.idle_after
        if time.monotonic() - self.away_since < limit:
            return False
        self.away_since = None
        return st.idle()

    def _clock_check(self):
        st = self.state
        if not self.clock_view or st.started or st.screen != 1:
            return False                            # never change the look during a visit
        view = decide_view(self.hour())
        if view == st.view:
            return False
        st.set_context(view)
        return True


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "5050"
    if not arg.isdigit() or not 0 < int(arg) < 65536:
        raise SystemExit(f"The port must be a number, for example: python -m network.server 5050 (got {arg!r})")
    port = int(arg)
    no_quick_edit()
    try:
        hub = Hub(port=port)
    except PortInUse:
        print(f"Port {port} is already used: the guide hub is probably already running in "
              "another window. Close that window first, or use another port: python -m network.server 5051")
        raise SystemExit(1)
    print(f"Guide hub listening on 127.0.0.1:{hub.port}")
    try:
        hub.serve_forever()
    except KeyboardInterrupt:
        pass
