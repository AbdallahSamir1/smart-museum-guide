"""Offline tests for the Bluetooth logic and visitor profiles. Run: python -m tests.test_ble"""
import os, tempfile, time
from ble.ble_scanner import VisitorTracker, visitor_name, PHONE_SERVICE
from network.client import GuideClient
from network.server import Hub

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)

t = VisitorTracker()
check("ignores other devices", t.update([("iPhone", -40), ("JBL Speaker", -50)], 0) is None)
check("first sighting is not enough", t.update([("MG-U042", -55)], 1) is None)
check("second sighting -> arrived", t.update([("MG-U042", -52)], 2) == ("arrived", "U042"))
check("same visitor again -> no repeat", t.update([("MG-U042", -50)], 3) is None)
check("picks the nearest phone", t.nearest([("MG-A", -65), ("MG-B", -45), ("MG-C", -60)]) == "B")
check("too far (weak signal) ignored", VisitorTracker().nearest([("MG-U9", -85)]) is None)
check("not left yet after 3 s", t.update([], 6) is None)
check("left after 6 s without signal", t.update([], 10) == ("left", None))
t2 = VisitorTracker(); t2.update([("MG-U1", -50)], 0)
check("walking past (one sighting) never announced", t2.update([], 1) is None and t2.current is None)
check("empty id ignored", VisitorTracker.user_id("MG-") is None)

check("phone with the 181C service and no name -> MG-U042", visitor_name(None, [PHONE_SERVICE.upper()]) == "MG-U042")
check("phone with its own MG- name keeps it", visitor_name("MG-U7", [PHONE_SERVICE]) == "MG-U7")
check("other device without the service ignored", VisitorTracker.user_id(visitor_name("JBL", ["0000180f-0000-1000-8000-00805f9b34fb"])) is None)

# profiles through the hub
path = os.path.join(tempfile.mkdtemp(), "profiles.json")
hub = Hub(port=0, profiles=path).start()
ui = GuideClient("ui", port=hub.port); g = GuideClient("gesture", port=hub.port)
bt = GuideClient("bluetooth", port=hub.port)
def go(*names):
    for n in names: g.gesture(n); time.sleep(0.03)
    time.sleep(0.05); return ui.last_state
bt.visitor("U042"); time.sleep(0.05)
check("new visitor is not returning", ui.last_state["returning"] is False)
go("wave", "swipe_right", "confirm", "swipe_right", "confirm", "swipe_right", "confirm")
s = ui.last_state
check("choices saved after screen 2", s["screen"] == 3 and hub.state.profiles.get("U042") ==
      {"language": "Arabic", "visitor_type": "children", "gender": "man"})
go("confirm", "confirm"); s = go("finish")
check("visit ended", s["screen"] == 1)
bt.visitor(None); time.sleep(0.05); bt.visitor("U042"); time.sleep(0.05)
s = ui.last_state
check("known visitor goes straight to screen 3 with the saved choices",
      s["screen"] == 3 and s["returning"] is True and s["language"] == "Arabic"
      and s["visitor_type"] == "children" and s["gender"] == "man")
s = go("back")
check("thumb down on screen 3 goes back to screen 2 (change the choices)", s["screen"] == 2)
go("confirm", "confirm", "confirm"); s = go("finish")
check("visit ended, welcome screen again", s["screen"] == 1 and s["started"] is False)
s = go("wave")
check("phone still there: the wave goes straight to screen 3", s["screen"] == 3 and s["language"] == "Arabic")
go("confirm", "confirm"); go("finish")
bt.visitor("U777"); time.sleep(0.05)
check("unknown visitor still starts on screen 1", ui.last_state["screen"] == 1 and ui.last_state["returning"] is False)
for c in (ui, g, bt): c.close()            # first, so no client is still talking while Python closes
hub.stop()
print("ALL PASS" if ok else "SOME FAILED")
