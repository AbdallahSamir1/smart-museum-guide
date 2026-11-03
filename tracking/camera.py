"""Live camera: MediaPipe hand tracking + the gesture engine (gestures.py, DollarPy templates
recorded from real movements).

Run:  python -m tracking.camera                          (press q to quit, 1/2/3 = Adult / With children / Older visitor)
      python -m tracking.camera --server 127.0.0.1:5050  (also send every event to the hub)
      python -m tracking.camera --camera 1               (use the second camera)
      python -m tracking.camera --video clip.mp4         (a recorded video instead of the camera;
                                               add --mirror if it was not recorded mirrored)
Gestures: wave (start), swipe_left / swipe_right (previous / next), thumb up held (OK),
  thumb down (back), open palm (pause / play), fist held (finish).
The program also sends hand_found / hand_lost (the dot at the top of the screen), how
long a thumb up or fist has been held (the ring), and on screen 3 the camera picture
with the hand path.
"""
import argparse
import base64
import os
import sys
import threading
import time

import cv2

from tracking.gestures import GestureEngine
from tracking.hand_tracker import HandTracker
from network.protocol import no_quick_edit, parse_server

LOST_AFTER = 0.6   # seconds without a hand before the dot at the top turns grey
RING_EVERY = 0.04  # seconds: the ring is sent at most 25 times a second
FRAME_EVERY = 0.08 # seconds: camera pictures for screen 3, about 12 a second
FRAME_SIZE = (320, 240)
WINDOW = "Smart Museum Guide - gestures"
GREEN, YELLOW, GREY, WHITE = (112, 224, 112), (0, 215, 255), (170, 170, 170), (255, 255, 255)


client = None
hub = {"hand": False, "screen": 1, "pace": "normal"}   # what the hub shows now
shown = {"name": "", "t": 0.0}
ring_sent = {"pose": None, "value": 0.0, "t": 0.0}


def on_event(name):
    print(f"[{time.strftime('%H:%M:%S')}] {name}")
    if name not in ("hand_found", "hand_lost"):
        shown["name"], shown["t"] = name, time.time()
    if client:
        client.gesture(name)


def send_ring(pose, value, now):
    """Send how long a thumb up or fist has been held: only when it changed enough, at most 25 times a second."""
    last = ring_sent
    if not client or (pose == last["pose"] and value == last["value"]):
        return
    big = pose != last["pose"] or abs(value - last["value"]) >= 0.04 or value in (0.0, 1.0)
    if big and now - last["t"] >= RING_EVERY:
        client.progress(pose, value)
        last.update(pose=pose, value=value, t=now)


class FrameSender:
    """Sends the newest camera picture to the hub from its own thread, so a slow
    socket never slows down the camera. Older pictures are simply skipped."""

    def __init__(self):
        self.jpeg, self.cv = None, threading.Condition()
        threading.Thread(target=self._run, daemon=True).start()

    def put(self, frame):
        small = cv2.resize(frame, FRAME_SIZE, interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if ok:
            with self.cv:
                self.jpeg = base64.b64encode(buf.tobytes()).decode("ascii")
                self.cv.notify()

    def _run(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.jpeg is not None)
                jpeg, self.jpeg = self.jpeg, None
            if client:
                client.frame(jpeg)


def open_camera(index):
    """Open the camera. On Windows DirectShow opens most webcams faster, the
    default driver is tried next. Returns None if no picture comes."""
    apis = [cv2.CAP_DSHOW, cv2.CAP_ANY] if os.name == "nt" else [cv2.CAP_ANY]
    for api in apis:
        cap = cv2.VideoCapture(index, api)
        if cap.isOpened() and cap.read()[0]:
            return cap
        cap.release()
    return None


def open_log(here):
    """CSV log of every frame. If gesture_log.csv is open in Excel (locked), a new
    file is written instead of stopping the camera."""
    for name in ("gesture_log.csv", f"gesture_log_{time.strftime('%H%M%S')}.csv"):
        try:
            return open(os.path.join(here, name), "w", encoding="utf-8")
        except OSError:
            pass
    print("Cannot write the gesture log (is the folder read-only?); going on without it.")
    return None


def connect(host, port, engine):
    """Connect to the hub in the background and keep trying, so the camera can be
    started before the hub without starting it again."""
    from network.client import GuideClient

    def on_state(st):
        hub["hand"] = bool(st.get("hand"))
        hub["screen"] = st.get("screen", 1)
        pace = st.get("pace", "normal")
        if pace != hub["pace"]:
            hub["pace"] = pace
            engine.set_pace(pace)            # older visitors: more time for every movement
            print("pace:", engine.pace)

    def keep_trying():
        global client
        warned = False
        while client is None:
            try:
                client = GuideClient("gesture", host, port, on_state=on_state, wait=5)
                print(f"Connected to the guide hub at {host}:{port}")
            except OSError as e:
                if not warned:
                    warned = True
                    print(f"Cannot reach the guide hub at {host}:{port} yet ({e}).\n"
                          "Start the hub (run_full_system.bat, or: python -m network.server); this window "
                          "keeps trying. Until then gestures are only shown in the camera window.")

    threading.Thread(target=keep_trying, daemon=True).start()


def draw(frame, engine, lm, now):
    """The camera window (and the picture on screen 3): the hand, its path for the
    last second, whether the hand is ready for a movement, and why the last
    movement was not a command."""
    h, w = frame.shape[:2]
    state = engine.state
    colour = GREY if state == "no pose" else GREEN
    pts = [(int(x * w), int(y * h)) for x, y in engine.path(now, 1.0)]
    for a, b in zip(pts, pts[1:]):
        cv2.line(frame, a, b, YELLOW, 4, cv2.LINE_AA)
    if lm:
        HandTracker.draw(frame, lm)
        cv2.putText(frame, state.replace("_", " "), (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, colour, 2)
    else:
        cv2.putText(frame, "no hand", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, GREY, 2)
    pose, value = engine.ring(now)
    if pose:
        cv2.ellipse(frame, (w - 50, 50), (28, 28), -90, 0, 360 * value, GREEN, 6)
        cv2.putText(frame, pose, (w - 95, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2)
    cv2.putText(frame, f"pace: {engine.pace}", (20, h - 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
    if now - shown["t"] < 1.5 and shown["name"]:          # last gesture, big, for 1.5 s
        cv2.putText(frame, shown["name"], (20, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 1.4, YELLOW, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", help="hub address, for example 127.0.0.1:5050")
    ap.add_argument("--camera", type=int, default=0, help="camera number, 0 = the first camera")
    ap.add_argument("--video", help="use a video file instead of the camera")
    ap.add_argument("--mirror", action="store_true", help="mirror the video (a camera is always mirrored)")
    ap.add_argument("--no-window", action="store_true", help="do not show the camera window")
    args = ap.parse_args()
    if args.server:
        host, port = parse_server(args.server)
    if args.video and not os.path.isfile(args.video):
        print(f"Cannot find the video {args.video!r}")
        sys.exit(1)
    no_quick_edit()
    try:
        tracker = HandTracker()
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # the project folder
    log = open_log(here)
    engine = GestureEngine(log=log)
    stop_flag = os.path.join(here, "stop_camera.flag")
    frames, bad_reads = 0, 0
    if args.server:
        connect(host, port, engine)
    if args.video:
        cap = cv2.VideoCapture(args.video)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if args.server:
            time.sleep(1.0)                                # time to reach the hub before the video starts
    else:
        cap, fps = open_camera(args.camera), None
    if cap is None or not cap.isOpened():
        print(f"Cannot open camera {args.camera}. Close other apps that use the camera "
              "(an older 'Camera gestures' window, Zoom, Teams, the Camera app), "
              "check the camera privacy setting in Windows, "
              "or try another camera with --camera 1.")
        if log:
            log.close()
        tracker.close()
        sys.exit(1)
    sender = FrameSender()
    present, last_seen, found_at, frame_at = False, 0.0, 0.0, 0.0
    t_start = time.time()
    print("Press q in the camera window to quit." if not args.no_window else "Running without a window.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                if args.video:
                    break                                  # the end of the video
                bad_reads += 1
                if bad_reads > 30:                         # about a second with no picture
                    print("Cannot read the camera. Is another app using it?")
                    break
                time.sleep(0.03)
                continue
            bad_reads = 0
            if not args.video or args.mirror:
                frame = cv2.flip(frame, 1)                 # mirror: right swipe = user's right
            h, w = frame.shape[:2]
            engine.aspect = w / h
            lm, world = tracker.process(frame)
            frames += 1
            if args.video:                                 # the video's own clock, played in real time
                now = t_start + frames / fps
                wait = now - time.time()
                if wait > 0:
                    time.sleep(wait)
            else:
                now = time.time()
            if frames % 30 == 0 and os.path.exists(stop_flag):   # lets the project restart the camera
                os.remove(stop_flag)
                break
            if lm:
                # also when the hub shows no hand because this program was started again
                if not present or (not hub["hand"] and client and now - found_at > 1.0):
                    present, found_at = True, now
                    on_event("hand_found")
                last_seen = now
                events = engine.update(lm, now, world)
            else:
                events = engine.no_hand(now)
                if present and now - last_seen > LOST_AFTER:
                    present = False
                    on_event("hand_lost")
            for e in events:
                on_event(e)
            pose, value = engine.ring(now)
            send_ring(pose, value, now)
            draw(frame, engine, lm, now)
            if client and hub["screen"] == 3 and now - frame_at >= FRAME_EVERY:
                frame_at = now
                sender.put(frame)                          # the picture in the box on screen 3
            if args.no_window:
                continue
            cv2.imshow(WINDOW, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break                                       # q, or the window was closed
            if key in (ord("1"), ord("2"), ord("3")):
                engine.set_visitor_type({ord("1"): "adult", ord("2"): "children", ord("3"): "older"}[key])
                print("pace:", engine.pace)
    except KeyboardInterrupt:
        pass
    finally:
        if present:
            on_event("hand_lost")
        cap.release()
        cv2.destroyAllWindows()
        if log:
            log.close()
        tracker.close()
        if client:
            time.sleep(0.2)                                 # the last messages reach the hub
            client.close()


if __name__ == "__main__":
    main()
