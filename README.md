# Smart Museum Guide: gestures + sockets

## Start here (Windows, no typing)

| File (double-click) | What it does |
|---|---|
| `setup_and_test.bat` | Once: makes the `.venv` folder, installs the libraries, runs all the tests |
| `run_full_system.bat` | The whole guide: hub, screen, Bluetooth, camera. The screen opens by itself |
| `run_demo_mona.bat` | No camera needed: plays Mona's visit, then Omar's, on the screen |
| `run_camera_test.bat` | Only the camera window, to try the gestures |
| `run_camera_on_screen.bat` | Only the camera, connected to a hub that is already running |
| `install_log.bat` | Same as `setup_and_test.bat`, but everything goes to `install_log.txt` |

`find_python.bat` (finds a Python that has the libraries), `open_screen.bat` (opens the screen in
its own Edge or Chrome window, allowed to read the story aloud) and `already_running.py` (stops a
second copy while an older one is still open) are used by the files above.

## Folders, one per Phase 2 requirement

| Phase 2 item | Folder | Main files |
|---|---|---|
| Figma interface | `ui/` | `ui_web.py` (screen server), `web/index.html` (the 5 screens), `web/guide.html`, `web/photos/` |
| MediaPipe + DollarPy | `tracking/` | `hand_tracker.py`, `gestures.py`, `camera.py`, `templates/swipes.json`, `make_templates.py`, `models/` |
| Bluetooth UserID | `ble/` | `ble_scanner.py`, `profiles.py`, `profiles.json`, `fake_phone.py` |
| Sockets | `network/` | `server.py` (hub), `client.py`, `protocol.py`, `state.py` |
| Context content | `context/` | `resolver.py`, `sensor.py`, `content/ui.json`, `content/exhibits.json` |
| Tests and demo | `tests/`, `demo/` | `test_*.py`, `demo_users.py` |
| Reports | `docs/` | review PDFs (`docs/screenshots` are old, from an earlier version) |

Scenario, PACT and the survey are in Phase1.pdf, not in the code.

## By hand

    pip install -r requirements.txt        # Python 3.9 to 3.13
    python -m tests.test_gestures                # gesture tests (no camera)
    python -m tests.test_sockets                 # full visit through the hub (no camera)
    python -m tests.test_ble                     # Bluetooth tests (no phone)
    python -m tests.test_context                 # content chosen from the context
    python -m tests.test_web                     # the screen's web server

Live run, one terminal each:

    python -m network.server                          # the hub
    python -m ui.ui_web --server 127.0.0.1:5050  # the screen: open http://127.0.0.1:8000 (F11 for full screen)
    python -m tracking.camera --server 127.0.0.1:5050    # camera, MediaPipe + DollarPy, sends gestures to the hub
    python -m ble.ble_scanner --server 127.0.0.1:5050      # Bluetooth visitor id (optional)
    python -m context.sensor --server 127.0.0.1:5050   # Day or Evening view from the hall light (optional)

The parts can be started in any order: the screen, the camera and the Bluetooth scanner keep trying
until the hub answers, and every part connects again by itself when the hub is started again.
No camera at hand? `python -m demo.demo_users mona` plays Mona's whole visit on the screen
(also `sara`, `omar`, `brown`; add `--stop 2` to stop on screen 2).
`ui/ui_console.py` prints the same screens in the terminal.

Parts talk over TCP sockets, one JSON object per line (see network/protocol.py):
camera (object detection) -> exhibits, gesture client -> gestures, Bluetooth -> visitor id,
clock/light sensor -> context, hub -> state to every UI screen.
network/state.py holds the flow of the five screens, so the same logic is used by the tests and the live system.

## Gestures

| Gesture | How | What it does |
|---|---|---|
| 👋 Wave | hand left and right 3 times or more | Starts the visit (screen 1) |
| ← → Swipe left / right | one quick move of the open hand across the picture | Moves the highlight; on the story screen, the next or previous exhibit |
| 👍 Thumb up, held 1 s (2 s for an older visitor) | thumb up, hand still | Choose, yes, more detail |
| 👎 Thumb down | thumb down | Back, no |
| ✋ Open palm | hold the open hand still | Pause / play the story |
| ✊ Fist, held 1.5 s | closed hand | Finish the visit |

`tracking/gestures.py` reads the hand shape from the 21 MediaPipe landmarks (thumb up / down, open palm, fist)
and names the moving gestures (swipe left, swipe right, wave) with DollarPy.
**The DollarPy templates are recorded, not drawn.** `tracking/templates/swipes.json` holds 9 right and 7 left
swipes taken from real recordings of people (the imsparsh *Gesture-Recognition-Dataset*, MIT licence):
the wrist path was tracked with MediaPipe in every clip. The wave templates are real swipes chained
left, right, left, right. `tracking/make_templates.py` builds the file again from the clips kept in `tracking/recordings/` (26 clips, source in its README.txt): `python -m tracking.make_templates tracking/recordings`.
Checked by leave-one-out (each recording against the templates without it): 16 of 16 swipes
recognised, scores 0.77 to 0.90; `python -m tests.test_gestures` repeats this check.
For an Older visitor every hold and every movement gets more time.
The round-2 movements (swipe up / down, circle, tips) were drawn from mathematical curves and were removed.

The gesture guide (the seven gestures, in English, Arabic and French) is at
http://127.0.0.1:8000/guide (or double-click `ui/web/guide.html`); the screen links to it ("Gesture guide", bottom right).
With no hand in the picture for 1 minute (3 minutes while a story plays) the visit ends by itself,
and the welcome screen waits for the next visitor.

## The screen

`ui/web/index.html` draws the five screens of the Phase 1 Figma design (screen 6 is now the dot at the top), with the colours, texts and sizes
chosen by `context/resolver.py`:

- A small dot at the top of every screen is green while the camera sees a hand and grey when it does not
  (there is no "cannot see your hand" screen any more: the story keeps playing).
- Screen 3 shows the live camera picture in its box, with how sure the camera is about each exhibit
  (for example "Throne 88%"); screen 4 "94% sure". Without the camera a drawing is shown in the box.
- Screens 4 and 5 show a real photo of the exhibit (Wikimedia Commons, credits in `ui/web/photos/CREDITS.json`),
  and screen 5 three short facts.
- While a thumb up or a fist is held, its ring fills up; the gesture the camera saw is shown briefly.
- The story is read aloud by the browser's own voices, in the visitor's language, with a woman's or a
  man's voice, slower for older visitors; the bar under the story shows the time.
  "Voice off: click 🔊 once" means the browser wants one click first (`open_screen.bat` avoids it).
  "No voice for this language on this computer" means Windows has no voice for it: Settings → Time & language →
  Speech → Add voices.
- If the hub or `ui/ui_web.py` stops, the screen keeps the last picture under "Reconnecting to the guide…"
  and goes on by itself when it is back.

## If something goes wrong

| Problem | What to do |
|---|---|
| A black window stops moving after a click in it | Windows "QuickEdit": the programs now switch it off; if it still happens, press Esc in that window |
| The camera does not open | Close an older "Camera gestures" window, Zoom, Teams or the Camera app; try `python -m tracking.camera --camera 1` |
| No Python with the libraries | Run `setup_and_test.bat` once |
| "The guide is already running" | An older copy is still open: close its black windows (Guide hub, Guide screen, Bluetooth visitors, Camera gestures), then double-click the file again |
| A port is already used | The program is already running in another window: close that window first |
| No phone is found | `python -m ble.ble_scanner --list` shows the Bluetooth names heard nearby; without Bluetooth: `python -m ble.fake_phone U042` |
| Try the Evening view | `python -m context.sensor --force evening` |
| `gesture_log.csv` is open in Excel | The camera writes a new `gesture_log_HHMMSS.csv` instead |

## Bluetooth (step 6)

    python -m ble.ble_scanner --server 127.0.0.1:5050    # scans for phones advertising "MG-<id>"
    python -m ble.ble_scanner --list                     # only lists the names heard nearby
    python -m ble.fake_phone U042                        # same thing without Bluetooth hardware
    python -m tests.test_ble                               # offline tests

A visitor's phone advertises over BLE with a local name such as `MG-U042` (the free app nRF Connect can do this).
The scanner chooses the nearest phone (signal stronger than -70 dBm), needs two sightings before it
announces someone and waits 6 s after the signal is gone before it says the visitor left.
The hub saves the language, visitor type and Woman/Man choice under that user id in profiles.json,
so a returning visitor (like Mona at the evening openings) is known the moment the phone is seen: screens 1 and 2 are skipped and the visit starts on screen 3 with the saved choices (thumb down goes back to change them). After a finished visit, while the phone is still there, a wave goes straight to screen 3. An unknown phone starts on screen 1 as usual. The phone of a visitor is the one named MG-<id>, or one that advertises the 181C service (`ble_scanner --phone-id U101` sets which id that is; run_full_system.bat uses U101).
A phone that arrives during somebody else's visit is used for the next visit.

## Load different content based on context (step 7)

    python -m tests.test_context

`context/resolver.py` turns the context into the content of the screen:

| Context | Where it comes from | What changes |
|---|---|---|
| Language | screen 1 (or the Bluetooth profile) | all text and the narrator's voice, Arabic right to left |
| Visitor type | screen 2 | Adult: full story, normal text, 4 gestures. With children: short story, large text, 3 short gestures. Older visitor: full story, extra large text, 3 gestures, more time for every movement, slower voice |
| Woman / Man / Skip | screen 2 | plum or teal accent, feminine, masculine or neutral wording (Arabic and French), female or male narrator |
| Day / Evening | the clock, or the hall light (`context/sensor.py`) | light or dark view |
| More detail | swipe up on screen 5 | the detail sentence is added to the story |

Texts live in `context/content/ui.json` and `context/content/exhibits.json`, so the museum can edit them without code.
`docs/screenshots/` shows screens of Sara, Omar, Mr. Brown and Mona produced by this code.
