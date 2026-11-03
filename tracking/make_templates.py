"""Builds templates/swipes.json, the DollarPy templates of the moving gestures, from RECORDED hand movements
(no maths curves). Needs the clips once; the engine only reads the JSON.

Recordings: github.com/imsparsh/Gesture-Recognition-Dataset (MIT licence), val folder: webcam clips of a
left swipe and a right swipe, 30 pictures each. MediaPipe gives the wrist of every picture; the movement
from the leftmost to the rightmost point (or back) is one real swipe. The clips were not mirrored, the
camera of the guide is, so x is turned (1 - x) here.
A wave is not in the data set: it is built from real swipes, right, left, right ... one after the other.

Usage: python -m tracking.make_templates <folder with one sub-folder of .png pictures per clip> [out.json]
"""
import glob
import json
import os
import re
import sys

FPS = 30.0
MIN_SPAN = 0.2         # a swipe crosses at least this much of the picture
MIN_FRAMES = 12        # pictures with a hand a clip needs
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "templates", "swipes.json")


def stroke(frames):
    """frames: [(frame number, x or None)] of one clip, x already mirrored like the guide's camera.
    Returns {"dir": "swipe_left" | "swipe_right", "pts": [[x, t], ...] (x 0..1 along the movement,
    t 0..1), "secs", "span"} for the main movement of the clip, or None."""
    seen = [(n, x) for n, x in frames if x is not None]
    if len(seen) < MIN_FRAMES:
        return None
    # missing pictures: a straight line between the pictures around them
    pts = []
    for n, x in frames:
        if n < seen[0][0] or n > seen[-1][0]:
            continue
        if x is None:
            a = max((s for s in seen if s[0] < n), key=lambda s: s[0])
            b = min((s for s in seen if s[0] > n), key=lambda s: s[0])
            x = a[1] + (b[1] - a[1]) * (n - a[0]) / (b[0] - a[0])
        pts.append((n / FPS, x))
    xs = [p[1] for p in pts]
    i_lo, i_hi = xs.index(min(xs)), xs.index(max(xs))
    a, b = sorted((i_lo, i_hi))
    part = pts[a:b + 1]
    span = abs(xs[i_hi] - xs[i_lo])
    if span < MIN_SPAN or len(part) < 4:
        return None
    path = sum(abs(q[1] - p[1]) for p, q in zip(part, part[1:]))
    if path > 1.4 * span:                          # it went back and forth: not one swipe
        return None
    right = i_lo < i_hi
    lo, secs = min(xs), part[-1][0] - part[0][0]
    t0 = part[0][0]
    return {"dir": "swipe_right" if right else "swipe_left", "span": round(span, 3), "secs": round(secs, 3),
            "pts": [[round((x - lo) / span, 4), round((t - t0) / secs, 4)] for t, x in part]}


def wave(strokes):
    """One wave from real swipes: [right, left, right, ...] each given as its normalised points and
    duration; they are joined end to start, so the path goes 0 -> 1 -> 0 -> 1 ... in x."""
    pts, t = [], 0.0
    for s in strokes:
        for x, u in s["pts"]:
            if pts and u == 0.0:
                continue                           # the first point is the last one of the swipe before
            pts.append([x, round(t + u * s["secs"], 4)])
        t += s["secs"]
    total = pts[-1][1] or 1.0
    return [[x, round(tt / total, 4)] for x, tt in pts]


def waves(rights, lefts):
    """Waves of 3 to 6 swings (swipes in a row) from the recorded right and left swipes, starting with
    either side; every one uses other recordings, so they differ like real waves do."""
    out = []
    for k, n in enumerate((3, 4, 5, 6, 3, 4, 5, 6)):
        first_right = k % 2 == 0
        seq = []
        for i in range(n):
            right = first_right == (i % 2 == 0)
            pool = rights if right else lefts
            seq.append(pool[(k * 3 + i) % len(pool)])
        out.append(wave(seq))
    return out


def build(clips):
    """clips: {name: [(frame number, wrist x or None)]} -> the JSON data."""
    found = {}
    for name, frames in clips.items():
        s = stroke(frames)
        if s:
            found[name] = s
    rights = [s for s in found.values() if s["dir"] == "swipe_right"]
    lefts = [s for s in found.values() if s["dir"] == "swipe_left"]
    return {
        "source": "github.com/imsparsh/Gesture-Recognition-Dataset (MIT), val folder, wrist path from MediaPipe Hands",
        "swipe_right": [{"clip": n, **{k: v for k, v in s.items() if k != "dir"}} for n, s in found.items() if s["dir"] == "swipe_right"],
        "swipe_left": [{"clip": n, **{k: v for k, v in s.items() if k != "dir"}} for n, s in found.items() if s["dir"] == "swipe_left"],
        "wave": waves(rights, lefts) if rights and lefts else [],
    }


def read_clips(folder):
    sys.path.insert(0, os.path.dirname(HERE))
    import cv2
    from tracking.hand_tracker import HandTracker
    tracker = HandTracker(video=False)
    clips = {}
    for clip in sorted(os.listdir(folder)):
        pics = sorted(glob.glob(os.path.join(folder, clip, "*.png")))
        frames = []
        for f in pics:
            n = int(re.search(r"_(\d+)\.png$", f).group(1))
            img = cv2.resize(cv2.imread(f), None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)   # small pictures
            lm, _ = tracker.process(img)
            frames.append((n, 1.0 - lm[0][0] if lm else None))        # 1 - x: the guide's camera is mirrored
        if frames:
            clips[clip] = frames
    tracker.close()
    return clips


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data = build(read_clips(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    print(out, len(data["swipe_right"]), "right,", len(data["swipe_left"]), "left,", len(data["wave"]), "waves")
