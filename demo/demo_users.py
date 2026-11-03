"""Drive the hub through the visit of one of the four PACT users, no camera needed.
Useful for the discussion: run server.py and ui_web.py, open the browser, then
    python -m demo.demo_users sara | omar | brown | mona [--stop 1..5] [--server 127.0.0.1:5050]
"""
import argparse
import time

from network.client import GuideClient
from network.protocol import parse_server

USERS = {   # language, visitor type, Woman/Man, Day/Evening, Bluetooth id
    "sara":  dict(lang="English", vtype="adult", gender="woman", view="day", uid="U101"),
    "omar":  dict(lang="Arabic", vtype="children", gender="man", view="day", uid="U102"),
    "brown": dict(lang="English", vtype="older", gender="man", view="day", uid="U103"),
    "mona":  dict(lang="Arabic", vtype="adult", gender="woman", view="evening", uid="U104"),
}


# the same movements the camera sends: wave, swipe_right, confirm (thumb up)
def run(name, server="127.0.0.1:5050", stop=5, pause=0.6):
    u = USERS[name]
    host, port = parse_server(server)
    try:
        c = GuideClient("demo", host, port)
    except ConnectionError as e:
        raise SystemExit(f"{e} (run_full_system.bat starts it)")
    def g(*names):
        for n in names:
            c.gesture(n)
            time.sleep(pause)

    def swipe_to(target):
        # a returning visitor may already have the right option highlighted
        for _ in range(4):
            if c.last_state and c.last_state["highlight"] == target:
                return
            g("swipe_right")

    c.context(u["view"]); c.visitor(u["uid"]); c.gesture("hand_found"); time.sleep(pause)
    c.exhibits([{"name": "Throne", "conf": .88, "distance": 2.0},
                {"name": "Golden Funerary Mask", "conf": .94, "distance": 1.1},
                {"name": "Sarcophagus", "conf": .81, "distance": 2.5}])
    time.sleep(pause)
    if c.last_state and c.last_state["screen"] == 3:      # a known visitor (saved choices) skips screens 1 and 2
        pass
    else:
        g("wave"); swipe_to(u["lang"])
        if stop == 1: return c
        g("confirm"); swipe_to(u["vtype"]); g("confirm"); swipe_to(u["gender"])
        if stop == 2: return c
        g("confirm")
    if stop == 3: return c
    g("confirm")
    if stop == 4: return c
    g("confirm")
    return c


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("user", choices=USERS)
    ap.add_argument("--stop", type=int, default=5, help="screen to stop on")
    ap.add_argument("--server", default="127.0.0.1:5050")
    a = ap.parse_args()
    client = run(a.user, a.server, a.stop)
    time.sleep(0.5)
    client.close()      # before Python exits: a client thread still printing while Python closes can crash it
