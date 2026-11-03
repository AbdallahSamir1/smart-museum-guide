"""Offline tests with synthetic landmarks (no camera needed) and with the recorded movements the
DollarPy templates are made of. Run: python -m tests.test_gestures"""
import json
import math
from dollarpy import Point
from tracking.gestures import (GestureEngine, SafeRecognizer, TEMPLATES, build_recognizer, classify_static,
                      load_templates, x_time_points)

def hand(pose, shift=0.0):
    lm = [(0.5, 0.8)] * 21
    lm = list(lm)
    bases = {5: .44, 9: .50, 13: .56, 17: .62}
    ext = pose in ("open_palm",)
    for mcp, x in bases.items():
        lm[mcp] = (x, 0.6)
        lm[mcp + 1] = (x, 0.5 if ext else 0.52)
        lm[mcp + 2] = (x, 0.44 if ext else 0.57)
        lm[mcp + 3] = (x, 0.38 if ext else 0.62)
    th = {"thumb_up": ((.42, .72), (.38, .64), (.35, .46)),
          "thumb_down": ((.42, .72), (.38, .84), (.35, .98)),
          "fist": ((.42, .72), (.46, .68), (.50, .66)),
          "open_palm": ((.42, .72), (.36, .68), (.30, .62))}[pose]
    lm[1] = (.45, .76); lm[2], lm[3], lm[4] = th
    return [(x + shift, y) for x, y in lm]

def run(seq, hold=1.0, rec=None):
    eng = GestureEngine(hold_time=hold, recognizer=rec); out = []
    for t, lm in seq:
        for e in eng.update(lm, t): out.append((round(t, 2), e))
    return out

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)

# ---- the static poses ----
for p in ("thumb_up", "thumb_down", "fist", "open_palm"):
    check(f"static {p}", classify_static(hand(p)) == p)

fps = 30
def still(pose, secs, t0=0.0):
    return [(t0 + i / fps, hand(pose)) for i in range(int(secs * fps))]

ev = [e for _, e in run(still("thumb_up", 1.3))]
check("thumb up held 1.0 s -> confirm", ev == ["confirm"])
ev = [e for _, e in run(still("thumb_up", 0.6))]
check("thumb up held 0.6 s -> nothing", ev == [])
ev = [e for _, e in run(still("thumb_up", 1.5), hold=2.0)]
check("older visitor 2 s hold: 1.5 s -> nothing", ev == [])
ev = [e for _, e in run(still("thumb_up", 2.2), hold=2.0)]
check("older visitor 2 s hold: 2.2 s -> confirm", ev == ["confirm"])
check("thumb down -> back", [e for _, e in run(still("thumb_down", 0.5))] == ["back"])
check("fist held 1.5 s -> finish", [e for _, e in run(still("fist", 1.8))] == ["finish"])
check("open palm -> pause_toggle once", [e for _, e in run(still("open_palm", 1.5))] == ["pause_toggle"])
check("tilted thumb up", classify_static([(x * 0.9 + y * 0.1, y) for x, y in hand("thumb_up")]) == "thumb_up")

# ---- the moving gestures (synthetic wrist paths) ----
def moving(xs, dur, hold_end=0.0):
    n = int(dur * fps)
    seq = [(i / fps, hand("open_palm", xs(i / n) - 0.5)) for i in range(n)]
    seq += [(dur + i / fps, hand("open_palm", xs(1) - 0.5)) for i in range(int(hold_end * fps))]
    return seq
check("fast swipe right", [e for _, e in run(moving(lambda u: 0.25 + 0.5 * u, 0.4, 0.3))
      if e != "pause_toggle"] == ["swipe_right"])
check("fast swipe left", [e for _, e in run(moving(lambda u: 0.75 - 0.5 * u, 0.4, 0.3))
      if e != "pause_toggle"] == ["swipe_left"])
check("slow movement ignored", [e for _, e in run(moving(lambda u: 0.25 + 0.5 * u, 2.5))
      if e not in ("pause_toggle",)] == [])
check("wave", "wave" in [e for _, e in run(moving(lambda u: 0.5 + 0.15 * math.sin(2 * math.pi * 3 * u), 0.8))])
check("wave is not a swipe", not any(e.startswith("swipe") for _, e in run(
      moving(lambda u: 0.5 + 0.15 * math.sin(2 * math.pi * 3 * u), 0.8))))
eng = GestureEngine(); out = []
for tt, lm in moving(lambda u: 0.25 + 0.5 * u, 0.4): out += eng.update(lm, tt)
out += eng.no_hand(0.45) + eng.no_hand(0.7)
check("swipe out of the camera view still counts", [e for e in out if e.startswith("swipe")] == ["swipe_right"])
seq = still("open_palm", 1.5) + [(1.5 + t, lm) for t, lm in moving(lambda u: 0.25 + 0.5 * u, 0.4)] \
      + [(1.9 + t, lm) for t, lm in still("open_palm", 0.5)]
ev = [e for _, e in run(seq) if e.startswith("swipe")]
check("swipe after the hand was already visible 1.5 s", ev == ["swipe_right"])
slow_wave = moving(lambda u: 0.5 + 0.08 * math.sin(2 * math.pi * 2.5 * u), 1.2)
ev = [e for _, e in run(slow_wave)]
check("smaller, slower wave (2 swings per second)", "wave" in ev and not any(e.startswith("swipe") for e in ev))
check("a swipe up or down does nothing any more (only the old gestures exist)",
      [e for _, e in run([(i / fps, hand("open_palm") and [(x, y - 0.5 * (i / 12)) for x, y in hand("open_palm")])
                          for i in range(12)])] == [])

# ---- the templates: recorded movements, not drawn curves ----
with open(TEMPLATES, encoding="utf-8") as f:
    data = json.load(f)
rights, lefts, waves = data["swipe_right"], data["swipe_left"], data["wave"]
check("the templates file holds recorded swipes and waves built from them (source named)",
      len(rights) >= 5 and len(lefts) >= 5 and len(waves) >= 5 and "Gesture-Recognition-Dataset" in data["source"]
      and set(data) == {"source", "swipe_right", "swipe_left", "wave"})
check("every recorded swipe is real: a clip name, 12+ points, goes 0 -> 1 in x (right) or 1 -> 0 (left)",
      all(s["clip"] and len(s["pts"]) >= 12 and abs(s["pts"][0][0]) < 1e-6 and abs(s["pts"][-1][0] - 1) < 1e-6 for s in rights)
      and all(s["clip"] and len(s["pts"]) >= 12 and abs(s["pts"][0][0] - 1) < 1e-6 and abs(s["pts"][-1][0]) < 1e-6 for s in lefts))
check("the recorded paths are uneven like real hands (not a smooth maths curve)",
      all(len({round(x, 3) for x, _ in s["pts"]}) >= 10 for s in rights + lefts))
check("a wave has 3 or more swings (it crosses the picture at least 3 times)",
      all(sum(1 for a, b in zip(w, w[1:]) if (a[0] - 0.5) * (b[0] - 0.5) < 0) >= 3 for w in waves))
check("load_templates gives one template per recording and per wave",
      len(load_templates()) == len(rights) + len(lefts) + len(waves)
      and len(load_templates(skip={rights[0]["clip"]})) == len(rights) + len(lefts) + len(waves) - 1)
try:
    load_templates("no_such_file.json"); missing = False
except FileNotFoundError as e:
    missing = "make_templates" in str(e)
check("a missing templates file says how to make it", missing)

# leave one out: each recorded swipe against templates that do not contain it
hit = 0
for lab, group in (("swipe_right", rights), ("swipe_left", lefts)):
    for s in group:
        name, score = build_recognizer(skip={s["clip"]}).recognize([Point(x, t, 1) for x, t in s["pts"]])
        hit += name == lab and score >= 0.5
check(f"recorded swipes not in the templates are still read right ({hit}/{len(rights) + len(lefts)})",
      hit == len(rights) + len(lefts))
rec = build_recognizer()
check("recorded waves are read as waves", all(rec.recognize([Point(x, t, 1) for x, t in w])[0] == "wave" for w in waves))
check("a still hand (no path) gives no movement, not a crash",
      rec.recognize([Point(0.5, 0, 1), Point(0.5, 1, 1)]) == (None, 0.0) and rec.recognize([Point(0.5, 0, 1)]) == (None, 0.0))
n0 = len(rec.ready)
for _ in range(3):
    rec.recognize(x_time_points([(0, 0.2, 0.5), (0.2, 0.4, 0.5), (0.4, 0.7, 0.5)]))
check("recognising does not grow the templates", len(rec.ready) == n0)

# the engine on a recorded movement it has not seen (that clip is left out of the templates)
def replay(s, x0=0.25, span=0.5, secs=0.45):
    """The recorded shape of the swipe (without the hand resting before and after it),
    played as a quick swipe across half the picture."""
    xs, ts = [x for x, _ in s["pts"]], [t for _, t in s["pts"]]
    lo = max(i for i, x in enumerate(xs) if abs(x - xs[0]) < 0.08)
    hi = min(i for i, x in enumerate(xs) if abs(x - xs[-1]) < 0.08)
    lo, hi = (lo, hi) if lo < hi else (0, len(xs) - 1)
    t0, t1 = ts[lo], ts[hi]
    right = xs[hi] > xs[lo]
    out = []
    for i in range(lo, hi + 1):
        frac = (xs[i] - xs[lo]) / (xs[hi] - xs[lo])          # 0 -> 1 along the swipe
        out.append(((ts[i] - t0) / (t1 - t0) * secs,
                    hand("open_palm", x0 + span * (frac if right else 1 - frac) - 0.5)))
    return out
passed = tried = 0
for lab, group in (("swipe_right", rights), ("swipe_left", lefts)):
    for s in group:
        seq = replay(s)
        end = seq[-1][0]
        seq += [(end + i / fps, seq[-1][1]) for i in range(1, 12)]
        ev = [e for _, e in run(seq, rec=build_recognizer(skip={s["clip"]})) if e != "pause_toggle"]
        tried += 1
        passed += ev == [lab]
check(f"the engine reads real recorded swipes that were left out of the templates ({passed}/{tried})",
      tried == len(rights) + len(lefts) and passed >= tried - 2)

# ---- pace, state, ring ----
eng = GestureEngine()
eng.set_pace("slow")
check("older visitor pace: longer holds and more time", eng.hold_time == 2.0 and eng.swipe_max_time > 0.6 and eng.wave_window > 1.3)
eng.set_visitor_type("adult")
check("adult pace is normal again", eng.pace == "normal" and eng.hold_time == 1.0)
eng = GestureEngine()
for t, lm in still("thumb_up", 0.6):
    eng.update(lm, t)
pose, value = eng.ring(0.6)
check("the ring fills while a thumb up is held", pose == "thumb_up" and 0.3 < value < 0.9 and eng.state == "thumb_up")
eng.lost()
check("a lost hand resets the ring", eng.ring(0.7) == (None, 0.0) and eng.state == "no pose")
print("ALL PASS" if ok else "SOME FAILED")
