"""Starts the hub, connects fake clients and walks a whole visit. Run: python -m tests.test_sockets"""
import os
import tempfile
import time
from network.client import GuideClient
from network.server import Hub, PortInUse

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)

tmp = tempfile.mkdtemp()                      # test visitors never go into the real profiles.json
hub = Hub(port=0, profiles=os.path.join(tmp, "profiles.json")).start()
ui_log, ui_prog, cam_prog, ui_tip, frames = [], [], [], [], []
ui = GuideClient("ui", port=hub.port, on_state=ui_log.append, on_progress=ui_prog.append, on_tip=ui_tip.append)
video = GuideClient("video", port=hub.port, on_frame=frames.append)
cam = GuideClient("camera", port=hub.port, on_progress=cam_prog.append)
gest = GuideClient("gesture", port=hub.port)
bt = GuideClient("bluetooth", port=hub.port)

def step(name=None):
    if name: gest.gesture(name)
    time.sleep(0.05)
    return ui.last_state

time.sleep(0.1)
s = step(); check("UI gets state on connect or first message", s is None or s["screen"] == 1)
s = step("hand_found")
check("hand seen: the dot at the top turns green, the screen stays", s["screen"] == 1 and s["hand"] is True)
s = step("hand_lost")
check("hand lost before anybody waved: the welcome screen stays, the dot turns grey",
      s["screen"] == 1 and s["hand"] is False)
check("swipe before wave ignored", step("swipe_right")["screen"] == 1 and step()["language"] == "English")
step("wave"); step("swipe_right"); s = step()
check("wave then swipe moves language", s["highlight"] == "Arabic")
s = step("confirm"); check("thumb up confirms the language -> screen 2", s["screen"] == 2 and s["language"] == "Arabic")
step("swipe_right"); step("swipe_right"); s = step("confirm")
check("choose Older visitor: slow pace", s["visitor_type"] == "older" and s["pace"] == "slow")
s = step("back"); check("thumb down: back from gender goes to type step", s["screen"] == 2 and s["who_step"] == "type")
s = step("confirm"); step("swipe_right"); s = step("confirm")
check("choose Man... screen 3", s["screen"] == 3 and s["gender"] == "man")
scene = [{"name": "Throne", "conf": .88, "distance": 2.0},
         {"name": "Golden Funerary Mask", "conf": .94, "distance": 1.1},
         {"name": "Sarcophagus", "conf": .81, "distance": 2.5}]
cam.exhibits(scene); time.sleep(0.05)
check("closest exhibit auto-highlighted", ui.last_state["highlight"] == "Golden Funerary Mask")
check("how sure the camera is reaches the screen (Throne 88%)",
      ui.last_state["confidence"] == {"Throne": 0.88, "Golden Funerary Mask": 0.94, "Sarcophagus": 0.81})
s = step("swipe_right"); check("swipe moves highlight", s["highlight"] == "Sarcophagus")
cam.exhibits(scene); time.sleep(0.05)
check("the camera sends the same picture again: the visitor's swipe is kept", ui.last_state["highlight"] == "Sarcophagus")
cam.exhibits([dict(e, distance=0.8) if e["name"] == "Throne" else e for e in scene]); time.sleep(0.05)
check("the visitor walks to another exhibit: the new nearest one is highlighted", ui.last_state["highlight"] == "Throne")
cam.exhibits(scene); time.sleep(0.05); s = step("swipe_right")
check("precondition: back at the mask, one swipe to the sarcophagus", s["highlight"] == "Sarcophagus")
step("confirm"); s = ui.last_state
check("thumb up -> screen 4", s["screen"] == 4 and s["exhibit"] == "Sarcophagus")
s = step("back"); check("thumb down: back to screen 3", s["screen"] == 3)
step("swipe_left"); step("confirm"); s = step("confirm")
check("thumb up twice -> story screen 5", s["screen"] == 5 and s["exhibit"] == "Golden Funerary Mask")
check("open palm pauses", step("pause_toggle")["paused"] is True)
check("open palm again plays on", step("pause_toggle")["paused"] is False)
check("thumb up gives more detail", step("confirm")["detail"] is True)
check("the screen is told which movement came", ui.last_state["last_gesture"]["name"] == "confirm")
s = step("hand_lost")
check("hand lost: the story stays on screen 5 (only the dot turns grey)",
      s["screen"] == 5 and s["hand"] is False and s["exhibit"] == "Golden Funerary Mask" and s["detail"] is True)
s = step("hand_found"); check("hand found: the dot is green again, same story", s["screen"] == 5 and s["hand"] is True)
check("no Bluetooth phone at the start of this visit", s["user_id"] is None)
bt.visitor("user-42"); time.sleep(0.05)
check("a phone that arrives during a visit does not take over the visit",
      ui.last_state["user_id"] is None and hub.state.ble_user == "user-42")
gest.sock.sendall(b'{"type":"context","view":"evening"}\n'); time.sleep(0.05)
check("context sets evening view", ui.last_state["view"] == "evening")
s = step("finish"); check("fist (finish) on the story screen -> screen 1", s["screen"] == 1 and s["started"] is False)
check("after the visit the phone in front of the screen is used for the next one", s["user_id"] == "user-42")
check("evening view kept for the next visit", s["view"] == "evening")
check("the exhibits the camera sees are kept for the next visit", s["confidence"].get("Golden Funerary Mask") == 0.94)
check("UI received many updates", len(ui_log) >= 15)

# hold progress: passed on to the screens only, and it is not a new state
states = len(ui_log)
gest.progress("thumb_up", 0.5); time.sleep(0.05)
check("the hold ring reaches the UI", ui_prog and ui_prog[-1] == {"type": "progress", "pose": "thumb_up", "value": 0.5})
check("progress is not sent to other parts", cam_prog == [])
check("progress does not send a new state", len(ui_log) == states)

gest.tip("too_slow"); gest.tip("not a key!"); time.sleep(0.05)
check("a tip reaches the UI, a broken tip is dropped",
      ui_tip == [{"type": "tip", "key": "too_slow"}] and len(ui_log) == states)
gest.frame("/9j/AAAA"); time.sleep(0.1)
check("a camera picture reaches the video client (the box on screen 3), not the UI or the state",
      frames and frames[-1]["jpeg"] == "/9j/AAAA" and len(ui_log) == states)

# broken messages must not stop the hub or drop the connection
sock = gest.sock
gest.sock.sendall(b'[1, 2]\n"text"\nnot json\n{"type":"gesture","name":["x"]}\n'
                  b'{"type":"exhibits","items":"abc"}\n{"type":"exhibits","items":[{"distance":1}]}\n'
                  b'{"type":"visitor","user_id":["x"]}\n{"type":"progress","value":"high"}\n'
                  b'{"type":"context","view":"night"}\n'
                  b'{"type":"exhibits","items":[{"name":"Throne","conf":true,"distance":2},'
                  b'{"name":"Golden Funerary Mask","conf":94,"distance":1.1},{"name":"Sarcophagus","conf":"high"}]}\n')
time.sleep(0.1)
s = step("wave")
check("broken messages ignored: same connection, hub still answers",
      gest.sock is sock and s["started"] is True and s["user_id"] == "user-42" and s["view"] == "evening"
      and s["exhibits"] == ["Throne", "Golden Funerary Mask", "Sarcophagus"])
check("a wrong 'how sure' value is dropped, 94 is read as 94 %", s["confidence"] == {"Golden Funerary Mask": 0.94})

# only one hub per port (on Windows a second one used to start and take part of the clients)
try:
    Hub(port=hub.port, profiles=os.path.join(tmp, "x.json")); refused = False
except PortInUse:
    refused = True
check("a second hub on the same port is refused", refused)

# the camera program is closed during a visit
gest.close(); time.sleep(0.1)
check("camera program closed during a visit -> the dot turns grey, the screen stays",
      ui.last_state["hand"] is False and ui.last_state["screen"] == 1 and ui.last_state["started"] is True)
gest = GuideClient("gesture", port=hub.port); gest.gesture("hand_found"); time.sleep(0.05)
check("camera back -> the visit goes on", ui.last_state["screen"] == 1 and ui.last_state["started"] is True)
for c in (ui, cam, gest, bt, video): c.close()
hub.stop()

# ---- nobody in front of the screen: the visit ends by itself (short timers for the test) ----
hub = Hub(port=0, profiles=os.path.join(tmp, "p2.json"), idle_after=0.3, story_idle_after=0.9,
          tick=0.05).start()
ui = GuideClient("ui", port=hub.port); g = GuideClient("gesture", port=hub.port)
def go(*names):
    for n in names: g.gesture(n); time.sleep(0.03)
    time.sleep(0.05); return ui.last_state
s = go("wave", "confirm", "confirm", "confirm")
check("idle test starts on screen 3", s["screen"] == 3)
s = go("hand_lost"); check("hand lost -> grey dot", s["screen"] == 3 and s["hand"] is False)
time.sleep(0.5); s = ui.last_state
check("no hand for a while -> visit ended, welcome screen for the next visitor",
      s["screen"] == 1 and s["started"] is False and s["visitor_type"] is None)
s = go("wave", "confirm", "confirm", "confirm", "confirm", "confirm")
check("story playing on screen 5", s["screen"] == 5 and s["paused"] is False)
go("hand_lost"); time.sleep(0.5)
check("while a story plays, a short absence does not end the visit",
      ui.last_state["screen"] == 5 and ui.last_state["started"] is True)
time.sleep(0.6)
check("... a long one does", ui.last_state["screen"] == 1 and ui.last_state["started"] is False)
s = go("wave", "confirm", "confirm", "confirm", "confirm", "confirm", "hand_lost")
time.sleep(0.2); go("hand_found"); time.sleep(0.4)
check("hand back in time -> the visit goes on", ui.last_state["screen"] == 5)
go("pause_toggle", "hand_lost"); time.sleep(0.5)
check("a paused story ends after the short time", ui.last_state["screen"] == 1)
for c in (ui, g): c.close()
hub.stop()

# ---- Day/Evening from the clock while no sensor reports it ----
hour = {"now": 12}
hub = Hub(port=0, profiles=os.path.join(tmp, "p3.json"), idle_after=0.3, tick=0.05,
          hour=lambda: hour["now"]).start()
ui = GuideClient("ui", port=hub.port); g = GuideClient("gesture", port=hub.port)
time.sleep(0.1)
check("clock 12:00 -> day view", ui.last_state["view"] == "day")
hour["now"] = 20; time.sleep(0.2)
check("clock 20:00 with nobody at the screen -> evening view", ui.last_state["view"] == "evening")
go("wave"); hour["now"] = 10; time.sleep(0.2)
check("the look does not change in the middle of a visit", ui.last_state["view"] == "evening")
go("hand_lost"); time.sleep(0.5)
check("after the visit the clock is followed again", ui.last_state["screen"] == 1 and ui.last_state["view"] == "day")
sensor = GuideClient("context", port=hub.port); sensor.context("evening"); time.sleep(0.1)
check("a sensor report sets the view", ui.last_state["view"] == "evening")
time.sleep(0.2)
check("the clock never overrides the sensor", ui.last_state["view"] == "evening")
for c in (ui, g, sensor): c.close()
hub.stop()

# ---- the screen is told when the hub is lost and when it is back ("Reconnecting…" on the page) ----
links, states = [], []
hub = Hub(port=0, profiles=os.path.join(tmp, "p4.json")).start()
port = hub.port
ui = GuideClient("ui", port=port, on_state=states.append, on_link=links.append)
time.sleep(0.1)
check("the screen knows the hub is reached", links == [True] and states)
hub.stop(); time.sleep(0.3)
check("the hub is closed -> the screen is told", links == [True, False])
before = len(states)
for _ in range(50):                          # Windows may keep the port busy for a moment
    try:
        hub = Hub(port=port, profiles=os.path.join(tmp, "p4.json")).start(); break
    except PortInUse:
        time.sleep(0.2)
for _ in range(80):
    if links[-1] is True and len(states) > before: break
    time.sleep(0.1)
check("the hub is started again -> the screen connects by itself and gets the state",
      links == [True, False, True] and len(states) > before and ui.last_state["screen"] == 1)
ui.close(); hub.stop()

# ---- a wrong --server value gives a clear message, not a Python error ----
from network.protocol import parse_server
def bad(text):
    try:
        parse_server(text); return False
    except SystemExit as e:
        return "127.0.0.1:5050" in str(e)
check("--server 127.0.0.1:5050 is read", parse_server("127.0.0.1:5050") == ("127.0.0.1", 5050))
check("--server without a port, with letters or a port too big: clear message",
      bad("127.0.0.1") and bad("localhost:abc") and bad(":5050") and bad("127.0.0.1:99999") and bad(""))
print("ALL PASS" if ok else "SOME FAILED")
