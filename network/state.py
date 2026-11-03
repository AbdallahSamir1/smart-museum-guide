"""The guide's logic: which screen is shown and what each gesture does.
Pure Python with no sockets, so it is easy to test."""

LANGS = ["English", "Arabic", "French"]
TYPES = ["adult", "children", "older"]
GENDERS = ["woman", "man", "skip"]
DEFAULT_EXHIBITS = ["Throne", "Golden Funerary Mask", "Sarcophagus"]


class GuideState:
    def __init__(self, profiles=None, resolver=None):
        self.profiles = profiles         # optional ProfileStore
        self.resolver = resolver         # optional ContextResolver (content for the screen)
        self.ble_user = None             # phone Bluetooth sees now; used on screen 1 only
        self.hand = False                # the camera sees a hand now (the dot at the top)
        self.gestures = 0                # how many gestures came (the screen shows each one)
        self.last_gesture = None
        self.reset()

    def reset(self):
        self.screen = 1                  # 1 wave, 2 who, 3 find, 4 confirm, 5 story
        self.started = False             # waved yet?
        self.lang_i = 0
        self.type_i = 0
        self.gender_i = 0
        self.who_step = "type"           # "type" then "gender" on screen 2
        self.language = None
        self.visitor_type = None
        self.gender = None
        self.exhibits = list(DEFAULT_EXHIBITS)
        self.conf = {}                   # how sure the camera is about each exhibit, 0..1
        self.closest_name = DEFAULT_EXHIBITS[1]
        self.closest = 1                 # index of the exhibit nearest the visitor
        self.sel = 1                     # highlighted exhibit
        self.exhibit = None              # chosen exhibit
        self.paused = False
        self.detail = False
        self.user_id = None              # the visitor of this visit (from Bluetooth)
        self.returning = False
        self.known = False               # the phone's visitor has all three choices saved
        self.view = "day"

    # ----- inputs from other parts -----
    def set_exhibits(self, items):
        """The camera saw these exhibits: [{"name", "conf", "distance"}, ...]."""
        if not isinstance(items, list):
            return
        items = [i for i in items if isinstance(i, dict) and isinstance(i.get("name"), str) and i["name"]]
        if not items:
            return
        far = lambda i: i["distance"] if isinstance(i.get("distance"), (int, float)) else 99
        items.sort(key=far)
        moved = items[0]["name"] != self.closest_name              # the visitor walked to another exhibit
        chosen = self.exhibits[self.sel] if 0 <= self.sel < len(self.exhibits) else None
        self.closest_name = items[0]["name"]
        names = list(dict.fromkeys(i["name"] for i in items))      # each exhibit once
        self.conf = {}
        for i in items:                  # shown on screens 3 and 4 ("Throne 88%", "94% sure")
            c = i.get("conf")
            if isinstance(c, (int, float)) and not isinstance(c, bool):
                c = c / 100 if 1 < c <= 100 else c                 # 88 means 88 %
                if 0 <= c <= 1:
                    self.conf.setdefault(i["name"], round(float(c), 3))
        # keep a stable left-to-right list order, highlight the closest one
        self.exhibits = sorted(names, key=lambda n: DEFAULT_EXHIBITS.index(n)
                               if n in DEFAULT_EXHIBITS else 99)
        self.closest = self.exhibits.index(self.closest_name)
        if self.screen == 3:
            # the camera sends what it sees again and again: the highlight follows the visitor
            # when they walk to another exhibit, but a swipe is not undone by the same picture
            self.sel = self.closest if moved or chosen not in self.exhibits else self.exhibits.index(chosen)
        elif self.exhibit in self.exhibits:
            self.sel = self.exhibits.index(self.exhibit)       # a swipe on screen 5 goes to its neighbour
        else:
            self.sel = min(self.sel, len(self.exhibits) - 1)

    def set_context(self, view):
        if view in ("day", "evening"):
            self.view = view

    def set_user(self, user_id):
        """Bluetooth found (or lost) a visitor's phone. On screen 1 it is used at once;
        during a visit it waits for the next visit, so the choices of the person who is
        using the guide are never saved under the phone of somebody who walked past."""
        if user_id is not None and not isinstance(user_id, str):
            return
        self.ble_user = user_id or None
        if self.screen == 1:
            self._apply_user(self.ble_user)
            if self.known and not self.started:
                self._enter_known()          # a known visitor goes straight to screen 3

    def _apply_user(self, user_id):
        """A returning visitor gets the language, visitor type and Woman/Man choice
        pre-highlighted."""
        self.user_id, self.returning, self.known = user_id, False, False
        prof = self.profiles.get(user_id) if (self.profiles and user_id) else None
        if not isinstance(prof, dict):
            return
        for key, values, attr in (("language", LANGS, "lang_i"), ("visitor_type", TYPES, "type_i"),
                                  ("gender", GENDERS, "gender_i")):
            if prof.get(key) in values:          # an old or hand-edited profile may hold anything
                setattr(self, attr, values.index(prof[key]))
                self.returning = True
        self.known = all(prof.get(k) in v for k, v in (("language", LANGS), ("visitor_type", TYPES),
                                                      ("gender", GENDERS)))

    def _enter_known(self):
        """The saved choices of a known visitor are used as they are: screens 1 and 2 are skipped.
        Thumb down on screen 3 goes back to screen 2 to change them."""
        self.started = True
        self.language, self.visitor_type = LANGS[self.lang_i], TYPES[self.type_i]
        self.gender = GENDERS[self.gender_i]
        self.screen, self.sel = 3, self.closest

    @property
    def pace(self):
        """Older visitors get more time for every movement (gestures.PACES)."""
        return "slow" if self.visitor_type == "older" else "normal"

    # ----- gestures -----
    def gesture(self, name):
        if not isinstance(name, str):
            return
        if name in ("hand_lost", "hand_found"):
            self.hand = name == "hand_found"     # only the dot at the top of the screen changes
            return
        self.hand = True
        self.gestures += 1
        self.last_gesture = name                 # the screen shows which movement it saw
        step = {1: self._s1, 2: self._s2, 3: self._s3, 4: self._s4, 5: self._s5}[self.screen]
        step(name)

    def idle(self):
        """Nobody has used the guide for a while (the hub's timer): end the visit so the
        next visitor starts on the welcome screen. Returns True if something changed."""
        if self.screen == 1 and not self.started:
            return False
        self._end_visit()
        return True

    def _end_visit(self):
        keep = (self.exhibits, self.closest, self.view, self.conf)
        self.reset()
        self.exhibits, self.closest, self.view, self.conf = keep
        self.closest_name = self.exhibits[self.closest]
        self._apply_user(self.ble_user)  # the phone in front of the screen now, for the next visit

    def _move(self, i, n, name):
        if name == "swipe_right":
            return (i + 1) % n
        if name == "swipe_left":
            return (i - 1) % n
        return i

    def _s1(self, g):
        if g == "wave":
            if self.known and not self.started:
                self._enter_known()          # the phone is still in front of the screen: no questions
            else:
                self.started = True
        elif not self.started:
            return
        elif g in ("swipe_left", "swipe_right"):
            self.lang_i = self._move(self.lang_i, len(LANGS), g)
        elif g == "confirm":
            self.language = LANGS[self.lang_i]
            self.screen = 2
            self.who_step = "type"

    def _s2(self, g):
        if g in ("swipe_left", "swipe_right"):
            if self.who_step == "type":
                self.type_i = self._move(self.type_i, len(TYPES), g)
            else:
                self.gender_i = self._move(self.gender_i, len(GENDERS), g)
        elif g == "confirm":
            if self.who_step == "type":
                self.visitor_type = TYPES[self.type_i]
                self.who_step = "gender"
            else:
                self.gender = GENDERS[self.gender_i]
                if self.profiles and self.user_id:
                    self.profiles.save(self.user_id, self.language,
                                       self.visitor_type, self.gender)
                self.screen = 3
                self.sel = self.closest
        elif g == "back":
            if self.who_step == "gender":
                self.who_step = "type"
            else:
                self.screen = 1

    def _s3(self, g):
        if g in ("swipe_left", "swipe_right"):
            self.sel = self._move(self.sel, len(self.exhibits), g)
        elif g == "confirm":
            self.exhibit = self.exhibits[self.sel]
            self.screen = 4
        elif g == "back":
            self.screen = 2
            self.who_step = "gender"

    def _s4(self, g):
        if g == "confirm":
            self.screen, self.paused, self.detail = 5, False, False
        elif g == "back":
            self.screen = 3

    def _s5(self, g):
        if g == "pause_toggle":
            self.paused = not self.paused
        elif g in ("swipe_left", "swipe_right"):
            self.sel = self._move(self.sel, len(self.exhibits), g)
            self.exhibit, self.detail, self.paused = self.exhibits[self.sel], False, False
        elif g == "confirm":
            self.detail = True
        elif g == "finish":
            self._end_visit()

    # ----- output -----
    def snapshot(self):
        snap = self._snapshot()
        if self.resolver:
            snap["content"] = self.resolver.resolve(snap)
        return snap

    def _snapshot(self):
        return {
            "type": "state",
            "screen": self.screen,
            "hand": self.hand,
            "started": self.started,
            "language": self.language or LANGS[self.lang_i],
            "who_step": self.who_step,
            "highlight": {"1": LANGS[self.lang_i],
                          "2": (TYPES if self.who_step == "type" else GENDERS)[
                              self.type_i if self.who_step == "type" else self.gender_i],
                          "3": self.exhibits[self.sel] if self.screen == 3 else None}.get(
                              str(self.screen)),
            "exhibits": self.exhibits,
            "confidence": self.conf,
            "exhibit": self.exhibit,
            "visitor_type": self.visitor_type,
            "gender": self.gender,
            "view": self.view,
            "paused": self.paused,
            "detail": self.detail,
            "pace": self.pace,
            "last_gesture": {"name": self.last_gesture, "n": self.gestures} if self.last_gesture else None,
            "user_id": self.user_id,
            "returning": self.returning,
        }
