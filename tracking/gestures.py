"""Smart Museum Guide: gesture recognition.

Static poses (thumb up, thumb down, open palm, fist) are classified from the
21 MediaPipe hand landmarks. Moving gestures (swipe left, swipe right, wave)
are classified with DollarPy ($P point-cloud recogniser) on the wrist path.
The DollarPy templates are RECORDED hand movements (templates/swipes.json, made by
make_templates.py from real webcam clips), not drawn curves.
Hold times and repeat guards live in GestureEngine and emit simple events.
"""
import json
import math
import os
import time
from collections import deque

from dollarpy import Point, Recognizer, Template

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates", "swipes.json")

WRIST, THUMB_MCP, THUMB_IP, THUMB_TIP = 0, 2, 3, 4
INDEX_MCP, MIDDLE_MCP, PINKY_MCP = 5, 9, 17
FINGER_TIPS = (8, 12, 16, 20)
FINGER_PIPS = (6, 10, 14, 18)

GESTURES = ("wave", "swipe_right", "swipe_left", "thumb_up", "thumb_down", "open_palm", "fist")
EVENTS = ("wave", "swipe_right", "swipe_left", "confirm", "back", "pause_toggle", "finish")
SWIPE_SCORE = 0.5   # DollarPy scores (0..1) a movement needs
WAVE_SCORE = 0.3
PACES = {           # "slow" for the Older visitor type: more time for every gesture
    "normal": {"hold": 1.0, "swipe_time": 1.0, "wave_window": 1.3},
    "slow": {"hold": 2.0, "swipe_time": 1.6, "wave_window": 2.0},
}
NOTES = {}          # why a movement gave no gesture (not used: the old gestures give no tips)
TIPS = ()


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _fix(lm, aspect):
    """MediaPipe gives x and y as fractions of width and height. On a 640x480
    camera one unit of x is longer than one unit of y, so x is stretched by the
    aspect ratio before measuring distances."""
    return [(p[0] * aspect, p[1]) for p in lm]


def finger_states(lm, aspect=1.0):
    """Returns (thumb_extended, [index, middle, ring, pinky] extended)."""
    lm = _fix(lm, aspect)
    wrist = lm[WRIST]
    fingers = [_d(lm[t], wrist) > 1.1 * _d(lm[p], wrist)
               for t, p in zip(FINGER_TIPS, FINGER_PIPS)]
    thumb = _d(lm[THUMB_TIP], lm[PINKY_MCP]) > 1.1 * _d(lm[THUMB_IP], lm[PINKY_MCP])
    return thumb, fingers


def classify_static(lm, aspect=1.0):
    """Return 'thumb_up', 'thumb_down', 'open_palm', 'fist' or None.
    Thumb up and down are judged by where the thumb tip is compared with the
    rest of the hand (highest or lowest point), so the hand can be turned."""
    pts = _fix(lm, aspect)
    scale = _d(pts[WRIST], pts[MIDDLE_MCP]) or 1e-6
    thumb, fingers = finger_states(lm, aspect)
    n_ext = sum(fingers)
    if n_ext >= 4:
        return "open_palm"
    if n_ext == 0:
        tip_y = pts[THUMB_TIP][1]
        others = [p[1] for i, p in enumerate(pts) if i not in (THUMB_IP, THUMB_TIP)]
        margin = 0.15 * scale
        if tip_y < min(others) - margin and pts[THUMB_MCP][1] - tip_y > 0.3 * scale:
            return "thumb_up"
        if tip_y > max(others) + margin and tip_y - pts[THUMB_MCP][1] > 0.3 * scale:
            return "thumb_down"
        return "fist"
    return None


# ---------- DollarPy ----------
class SafeRecognizer(Recognizer):
    """DollarPy's $P recogniser (its resampling and greedy cloud matching), with four
    problems of dollarpy 0.1.1 fixed:
      * recognize() adds points to the list it is given and to the stored templates,
        so the templates grew (and got slower) every time: here it works on copies and
        the templates are normalised once,
      * a path without length (a still hand) or with one point crashed it,
      * the resampling can give one point too few, which crashed the matching,
      * the scaling was wrong for negative coordinates (its max started at 0)."""

    def __init__(self, templates, n=32):
        super().__init__(templates)
        self.n = n
        self.ready = [(t.name, q) for t in templates for q in [self.normalize(t)] if q]

    def _greedy_cloud_match(self, points, template, n):
        """DollarPy's greedy cloud match: the same start points (every sqrt(n)-th), both
        ways round, each point matched to the nearest free point and weighted 1 - k/n,
        so the same result, but the distances are worked out once instead of 14 times
        (about 5 times faster, so a camera frame is not held up)."""
        rows = [[math.hypot(p.x - q.x, p.y - q.y) for q in template] for p in points]
        cols = [list(c) for c in zip(*rows)]
        step = int(math.floor(n ** 0.5))
        best = float("inf")
        for i in range(0, n, step):
            best = min(best, self._greedy(rows, n, i), self._greedy(cols, n, i))
        return best

    @staticmethod
    def _greedy(dist, n, start):
        free = list(range(n))
        total, i = 0.0, start
        for k in range(n):
            row = dist[i]
            j = min(free, key=row.__getitem__)       # first nearest, like DollarPy
            free.remove(j)
            total += (1 - k / n) * row[j]
            i = (i + 1) % n
        return total

    def normalize(self, points):
        pts = [Point(float(p.x), float(p.y), 1) for p in points]   # a copy, all one stroke
        if len(pts) < 2 or self._path_length(pts) <= 1e-9:
            return None
        pts = self._resample(pts, self.n)[:self.n]
        while len(pts) < self.n:
            pts.append(Point(pts[-1].x, pts[-1].y, 1))
        x0, x1 = min(p.x for p in pts), max(p.x for p in pts)
        y0, y1 = min(p.y for p in pts), max(p.y for p in pts)
        s = max(x1 - x0, y1 - y0) or 1e-9
        pts = [Point((p.x - x0) / s, (p.y - y0) / s, 1) for p in pts]
        mx, my = sum(p.x for p in pts) / self.n, sum(p.y for p in pts) / self.n
        return [Point(p.x - mx, p.y - my, 1) for p in pts]

    def recognize(self, points, n=None):
        """(name, score 0..1) of the nearest template, (None, 0.0) for no movement."""
        q = self.normalize(points)
        if q is None:
            return None, 0.0
        best, name = float("inf"), None
        for tname, t in self.ready:
            d = self._greedy_cloud_match(q, t, self.n)
            if d < best:
                best, name = d, tname
        score = max((2 - best) / 2, 0.0)
        return (name, score) if score > 0 else (None, 0.0)


def load_templates(path=TEMPLATES, skip=()):
    """The recorded movements as DollarPy templates: swipe_right, swipe_left, wave.
    skip: names of recorded clips to leave out (to test on a clip that is not a template)."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"The recorded templates are missing: {path}\n"
            "Make them with: python -m tracking.make_templates <folder of recorded clips>")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for name in ("swipe_right", "swipe_left"):
        for s in data[name]:
            if s["clip"] not in skip:
                out.append(Template(name, [Point(x, t, 1) for x, t in s["pts"]]))
    for pts in data["wave"]:
        out.append(Template("wave", [Point(x, t, 1) for x, t in pts]))
    return out


def build_recognizer(path=TEMPLATES, skip=()):
    return SafeRecognizer(load_templates(path, skip))


def x_time_points(trail):
    """(t, x, y) wrist path -> DollarPy points (x, time), both scaled to 0..1."""
    xs = [p[1] for p in trail]
    t0, t1 = trail[0][0], trail[-1][0]
    lo, hi = min(xs), max(xs)
    span, dt = (hi - lo) or 1e-6, (t1 - t0) or 1e-6
    return [Point((x - lo) / span, (t - t0) / dt, 1) for t, x, _ in trail]


class GestureEngine:
    """Feed it one hand per frame with update(landmarks, now).
    It returns a list of events like 'swipe_right' or 'confirm'."""

    def __init__(self, hold_time=1.0, fist_hold=1.5, aspect=1.0,
                 swipe_min_dx=0.22, swipe_max_time=1.0, swipe_cooldown=0.8,
                 wave_window=1.3, min_score=SWIPE_SCORE, wave_score=WAVE_SCORE, stable_frames=3,
                 log=None, recognizer=None):
        self.rec = recognizer or build_recognizer()
        self.hold_time = hold_time          # 1.0 s, or 2.0 s for Older visitor
        self.fist_hold = fist_hold
        self.aspect = aspect                # camera width / height
        self.swipe_min_dx = swipe_min_dx    # fraction of the frame width
        self.swipe_max_time = swipe_max_time
        self.swipe_cooldown = swipe_cooldown
        self.wave_window = wave_window
        self.min_score = min_score
        self.wave_score = wave_score
        self.stable_frames = stable_frames  # a pose must last this many frames
        self.log = log                      # optional open file for a CSV log
        self.pace = "normal"
        self.note, self.note_t, self.detail, self.tip = None, 0.0, None, None   # kept for main.py
        self.trail = deque()                # (t, x, y) wrist positions, 0..1
        self.pose = None
        self.pose_since = 0.0
        self.cand, self.cand_n = None, 0
        self.fired = set()
        self.last_move = -9.0
        self.pending = None                 # (name, time, x) swipe waiting for confirmation
        self.palm_armed = True
        self.progress = 0.0                 # 0..1 for the filling ring on screen
        if self.log:
            self.log.write("t,raw_pose,pose,index,middle,ring,pinky,thumb,wrist_x,wrist_y,events\n")

    def set_visitor_type(self, kind):
        self.set_pace("slow" if kind == "older" else "normal")

    def set_pace(self, pace):
        """'slow' (Older visitor): holds are 2 s, a swipe may take longer, a wave is judged over more time."""
        self.pace = pace if pace in PACES else "normal"
        p = PACES[self.pace]
        self.hold_time, self.swipe_max_time, self.wave_window = p["hold"], p["swipe_time"], p["wave_window"]

    @property
    def state(self):
        """What the camera window shows: the pose now, or that there is no clear pose."""
        return self.pose or "no pose"

    def path(self, now, secs=1.0):
        """The wrist path of the last `secs` seconds, to draw it."""
        return [(p[1], p[2]) for p in self.trail if now - p[0] <= secs]

    def ring(self, now=None):
        """(pose, 0..1): how long a thumb up or a fist has been held, for the filling ring."""
        if self.pose in ("thumb_up", "fist") and self.progress > 0:
            return self.pose, self.progress
        return None, 0.0

    def no_hand(self, now=None):
        """Call on frames without a hand. A swipe that ended outside the
        camera view is still reported."""
        now = time.time() if now is None else now
        if self.pending and now - self.pending[1] >= 0.2:
            name = self.pending[0]
            return [self._fire(name, now)]
        return []

    def lost(self):
        self.trail.clear()
        self.pose, self.cand, self.cand_n = None, None, 0
        self.progress = 0.0
        self.fired.clear()
        self.pending = None

    def _stable_pose(self, raw):
        if raw == self.cand:
            self.cand_n += 1
        else:
            self.cand, self.cand_n = raw, 1
        return self.cand if self.cand_n >= self.stable_frames else self.pose

    def update(self, lm, now=None, world=None):
        now = time.time() if now is None else now
        events = []
        raw = classify_static(lm, self.aspect)
        pose = self._stable_pose(raw)

        # --- held poses ---
        if pose != self.pose:
            self.pose, self.pose_since = pose, now
            self.fired.clear()
            self.progress = 0.0
            if pose == "thumb_down":
                events.append("back")
            if pose != "open_palm":
                self.palm_armed = True
        held = now - self.pose_since
        need = {"thumb_up": self.hold_time, "fist": self.fist_hold}.get(pose)
        self.progress = min(held / need, 1.0) if need else 0.0
        if need and held >= need and pose not in self.fired:
            self.fired.add(pose)
            events.append("confirm" if pose == "thumb_up" else "finish")

        # --- moving gestures from the wrist path ---
        self.trail.append((now, lm[WRIST][0], lm[WRIST][1]))
        while self.trail and now - self.trail[0][0] > self.wave_window:
            self.trail.popleft()
        if pose in ("open_palm", None) or raw in ("open_palm", None):
            moving = self._moving(now)
            if moving:
                self.palm_armed = False     # no pause right after a swipe or wave
                events.append(moving)
        if (pose == "open_palm" and held >= 0.4 and self.palm_armed
                and self._still(now) and now - self.last_move > 1.0):
            self.palm_armed = False
            events.append("pause_toggle")

        if self.log:
            thumb, f = finger_states(lm, self.aspect)
            self.log.write(f"{now:.3f},{raw},{pose},{int(f[0])},{int(f[1])},{int(f[2])},{int(f[3])},"
                           f"{int(thumb)},{lm[WRIST][0]:.3f},{lm[WRIST][1]:.3f},{'|'.join(events)}\n")
        return events

    def _still(self, now, secs=0.4, limit=0.04):
        recent = [p[1] for p in self.trail if now - p[0] <= secs]
        return len(recent) < 2 or max(recent) - min(recent) < limit

    @staticmethod
    def _flips(xs, jitter=0.006):
        flips, last = 0, 0
        for a, b in zip(xs, xs[1:]):
            dx = b - a
            if abs(dx) < jitter:
                continue
            sign = 1 if dx > 0 else -1
            if last and sign != last:
                flips += 1
            last = sign
        return flips

    def _moving(self, now):
        # a swipe is only reported after the hand does not come back for 0.2 s,
        # otherwise the first swing of a wave would look like a swipe
        if self.pending:
            name, t0, x0 = self.pending
            x = self.trail[-1][1]
            back = (x0 - x) if name == "swipe_right" else (x - x0)
            if back > 0.05:
                self.pending = None          # it came back: probably a wave
            elif now - t0 >= 0.2:
                self.pending = None
                return self._fire(name, now)
        if now - self.last_move < self.swipe_cooldown or len(self.trail) < 6:
            return None
        # wave: the hand goes left and right several times
        xs = [p[1] for p in self.trail]
        if self._flips(xs) >= 3 and max(xs) - min(xs) > 0.06:
            name, score = self.rec.recognize(x_time_points(list(self.trail)))
            if name == "wave" and score >= self.wave_score:
                self.pending = None
                return self._fire("wave", now)
        # swipe: one quick move across the frame, only the last second counts,
        # so a slow movement never becomes a swipe
        recent = [p for p in self.trail if now - p[0] <= self.swipe_max_time]
        if len(recent) < 4:
            return None
        rx = [p[1] for p in recent]
        ry = [p[2] for p in recent]
        x_now = rx[-1]
        i_far = max(range(len(rx)), key=lambda i: abs(x_now - rx[i]))
        dx = x_now - rx[i_far]
        part = recent[i_far:]
        if (abs(dx) >= self.swipe_min_dx and len(part) >= 3
                and self._flips([p[1] for p in part]) == 0
                and abs(ry[-1] - ry[i_far]) < abs(dx)):
            name, score = self.rec.recognize(x_time_points(part))
            want = "swipe_right" if dx > 0 else "swipe_left"
            if name == want and score >= self.min_score and not self.pending:
                self.pending = (want, now, x_now)
        return None

    def _fire(self, name, now):
        self.last_move = now
        self.pending = None
        self.trail.clear()
        return name
