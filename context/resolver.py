"""Load different content based on context.

Context = who is in front of the screen and where/when:
  language       chosen on screen 1 (or remembered from the Bluetooth profile)
  visitor type   Adult / With children / Older visitor, chosen on screen 2
  Woman/Man/Skip chosen on screen 2
  Day/Evening    from the clock and the light level in the hall
resolve(state) turns that context into everything the screen needs:
colours, text direction, text size, wording, gesture bar, story text and narrator voice.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- the look ----------
VIEWS = {   # Day view = light background, dark text. Evening view = dark background, light text.
    "day": {"bg": "#f4f1ea", "card": "#ffffff", "border": "#d9d3c7", "text": "#1d2433", "muted": "#5d6678",
            "gold": "#b07a1a", "warn_bg": "#f3e3bf", "warn_text": "#7a5310"},
    "evening": {"bg": "#0f1726", "card": "#1b2a41", "border": "#2c3d5a", "text": "#ffffff", "muted": "#8ea0b8",
                "gold": "#e3b55a", "warn_bg": "#3a2f17", "warn_text": "#e3b55a"},
}
ACCENTS = {  # Woman = plum, Man and Skip = teal
    "woman": {"accent": "#a2457e", "accent_soft": "#f1dcea", "accent_dark": "#5e2349"},
    "man": {"accent": "#1f8f86", "accent_soft": "#d5efec", "accent_dark": "#145c56"},
    "skip": {"accent": "#1f8f86", "accent_soft": "#d5efec", "accent_dark": "#145c56"},
}
EVENING_ACCENT_TEXT = {"woman": "#f0b6d9", "man": "#6fe0c0", "skip": "#6fe0c0"}
VOICE = {"woman": "female", "man": "male", "skip": "female"}
FORM = {"woman": "f", "man": "m", "skip": "n", None: "n"}
HALL_LETTER = {"Arabic": {"A": "أ", "B": "ب", "C": "ج", "D": "د"}}   # "Hall B" is «القاعة ب» in the design

# ---------- what each visitor type gets ----------
VISITOR = {   # speech_rate: how fast the narrator reads the story (1.0 = normal)
              # pace: how much time every movement gets (gestures.PACES)
    "adult":    {"text_scale": 1.0, "story": "full",  "pace": "normal", "speech_rate": 1.0,
                 "story_bar": ["gx_pause", "gx_next", "gx_detail", "gx_finish"]},
    "children": {"text_scale": 1.3, "story": "short", "pace": "normal", "speech_rate": 0.95,
                 "story_bar": ["gk_next", "gk_stop", "gk_done"]},
    "older":    {"text_scale": 1.6, "story": "full",  "pace": "slow", "speech_rate": 0.85,
                 "story_bar": ["gx_pause", "gx_detail", "gx_finish"]},
}
SCREEN_BAR = {1: ["gx_wave", "gx_swipe", "gx_choose"], 2: ["gx_swipe", "gx_choose", "gx_back"],
              3: ["gx_swipe", "gx_choose", "gx_back"], 4: ["gx_yes", "gx_no"]}
TIPS = ()
MOVES = ("wave", "swipe_right", "swipe_left", "confirm", "back", "pause_toggle", "finish")   # gestures.EVENTS
SHORT_BAR = {2: ["gx_swipe", "gx_choose", "gx_back"], 3: ["gk_next", "gx_choose", "gx_back"]}


def decide_view(hour, light=None, dark_below=0.35):
    """Day or Evening view. The clock decides most of the day; in the hours
    around sunrise and sunset the light level in the hall decides.
    hour: 0..23, light: 0..1 (None if no light reading)."""
    if 7 <= hour < 17:
        return "day"
    if hour >= 19 or hour < 6:
        return "evening"
    if light is None:
        return "day" if hour < 12 else "evening"
    return "evening" if light < dark_below else "day"


class ContextResolver:
    def __init__(self, folder=os.path.join(HERE, "content")):
        with open(os.path.join(folder, "ui.json"), encoding="utf-8") as f:
            self.ui = json.load(f)
        with open(os.path.join(folder, "exhibits.json"), encoding="utf-8") as f:
            self.exhibits = json.load(f)
        self.by_label = {v["label"]: k for k, v in self.exhibits.items()}

    def text(self, key, lang, gender=None):
        val = self.ui[key].get(lang) or self.ui[key]["English"]
        if isinstance(val, dict):
            return val[FORM[gender]]
        return val

    def theme(self, view, gender):
        g = gender or "skip"
        t = dict(VIEWS[view])
        t.update(ACCENTS[g])
        t["accent_text"] = EVENING_ACCENT_TEXT[g] if view == "evening" else ACCENTS[g]["accent_dark"]
        t["accent_light"] = EVENING_ACCENT_TEXT[g]      # highlights on the dark camera preview
        t["frame"] = t["accent_text"] if view == "evening" else t["accent"]   # line inside the story photo
        return t

    def exhibit(self, label, lang, visitor_type, detail=False):
        if not label or label not in self.by_label:
            return None
        ex_id = self.by_label[label]
        ex = self.exhibits[ex_id]
        kind = VISITOR.get(visitor_type or "adult")["story"]
        story = ex[kind][lang]
        if detail:
            story += " " + ex["detail"][lang]
        return {"id": ex_id, "name": ex["name"][lang], "hall": HALL_LETTER.get(lang, {}).get(ex["hall"], ex["hall"]),
                "story": story, "length": kind, "detail": detail,
                # a real photo of the piece (web/photos/CREDITS.json) and three short true facts
                "photo": ex.get("photo"), "credit": ex.get("credit"), "facts": ex.get("facts", {}).get(lang, [])}

    def resolve(self, s):
        """s: the state snapshot dict (from GuideState). Returns the content block."""
        lang = s["language"]
        gender = s.get("gender")
        vtype = s.get("visitor_type")
        prof = VISITOR.get(vtype or "adult")
        screen = s["screen"]
        if screen == 5:
            bar = prof["story_bar"]
        elif vtype == "children" and screen in SHORT_BAR:
            bar = SHORT_BAR[screen]
        else:
            bar = SCREEN_BAR.get(screen, [])
        tx = lambda k: self.text(k, lang, gender)
        content = {
            "dir": "rtl" if lang == "Arabic" else "ltr",
            "theme": self.theme(s.get("view", "day"), gender),
            "text_scale": prof["text_scale"],
            "speech_rate": prof["speech_rate"],
            "voice": VOICE.get(gender or "skip"),
            "gesture_bar": [tx(k) for k in bar],
            "gesture_keys": list(bar),            # which gesture each chip is, for the hold ring
            "labels": {k: tx(k) for k in (
                "app", "welcome", "back_welcome", "gestures", "playing", "paused",
                "story_end", "no_voice", "voice_blocked", "guide_link",
                "s1_title", "s1_sub", "s1_lang", "s1_privacy", "s2_title", "s2_type", "s2_gender",
                "t_adult", "t_children", "t_older", "g_woman", "g_man", "g_skip",
                "s3_title", "s3_hint", "s4_title", "s4_yes", "s4_no", "gx_yes", "gx_no", "sure",
                "v_day", "v_evening", "hand_ok", "hand_seen", "ex_ok", "slow_pace", "camera_off",
                "no_hand", "you_chose", "nearest", "you_here", "d_adult", "d_children", "d_older",
                "s2_sub", "hall", "voice_female", "voice_male", "exhibits_found")}
                | {"tip_" + k: tx("tip_" + k) for k in TIPS} | {"mv_" + k: tx("mv_" + k) for k in MOVES},
            "exhibit": self.exhibit(s.get("exhibit"), lang, vtype, s.get("detail", False)),
            "exhibit_names": {lbl: self.exhibits[i]["name"][lang] for lbl, i in self.by_label.items()},
            # the short name on the camera box of screen 3 ("Golden Mask 94%" in the design)
            "exhibit_tags": {lbl: self.exhibits[i].get("tag", {}).get(lang) or self.exhibits[i]["name"][lang]
                             for lbl, i in self.by_label.items()},
        }
        if content["exhibit"]:
            ex = content["exhibit"]
            content["audio"] = f"audio/{ex['id']}_{lang.lower()}_{ex['length']}{'_detail' if ex['detail'] else ''}_{content['voice']}.mp3"
        return content
