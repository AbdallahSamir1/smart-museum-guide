"""Tests that each of the four PACT users gets the right content. Run: python -m tests.test_context"""
from context.resolver import ContextResolver, decide_view
from network.state import GuideState

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)

# ---- Day or Evening view from clock and hall light ----
check("10:00 -> day", decide_view(10) == "day")
check("15:00 dim display case -> still day (Mr. Brown)", decide_view(15, light=0.2) == "day")
check("20:00 -> evening (Mona)", decide_view(20) == "evening")
check("18:00 dark hall -> evening", decide_view(18, light=0.2) == "evening")
check("18:00 bright hall -> day", decide_view(18, light=0.7) == "day")
check("02:00 -> evening", decide_view(2) == "evening")

r = ContextResolver()
def visit(lang, vtype, gender, view, detail=False, screen=5):
    s = GuideState(resolver=r)
    s.lang_i = ["English", "Arabic", "French"].index(lang); s.language = lang
    s.visitor_type, s.gender, s.view = vtype, gender, view
    s.exhibit, s.screen, s.detail = "Golden Funerary Mask", screen, detail
    return s.snapshot()

sara = visit("English", "adult", "woman", "day")
c = sara["content"]
check("Sara: plum accent", c["theme"]["accent"] == "#a2457e")
check("Sara: Day view (light background)", c["theme"]["bg"] == "#f4f1ea")
check("Sara: standard text, full story", c["text_scale"] == 1.0 and c["exhibit"]["length"] == "full")
check("Sara: four gestures on the story bar", len(c["gesture_bar"]) == 4)
check("Sara: female voice, left to right", c["voice"] == "female" and c["dir"] == "ltr")

omar = visit("Arabic", "children", "man", "day")
c = omar["content"]
check("Omar: teal accent", c["theme"]["accent"] == "#1f8f86")
check("Omar: Arabic right to left", c["dir"] == "rtl")
check("Omar: short story in Arabic", c["exhibit"]["story"] == "قناع ذهبي لملك صغير.")
check("Omar: large text", c["text_scale"] == 1.3)
check("Omar: three short gesture labels", c["gesture_bar"] == ["سحب = التالي", "كف = قف", "قبضة = انتهى"])
check("Omar: masculine wording", c["labels"]["s3_hint"].endswith("اسحب للتنقل."))
check("Omar: male voice and audio file", c["voice"] == "male" and c["audio"] == "audio/golden_mask_arabic_short_male.mp3")
check("Omar: the hall letter in Arabic, like the design (Hall B = the letter Baa)",
      c["exhibit"]["hall"] == "ب" and sara["content"]["exhibit"]["hall"] == "B")
check("Sara: the line inside the story photo is plum", sara["content"]["theme"]["frame"] == "#a2457e")

brown = visit("English", "older", "man", "day", detail=True)
c = brown["content"]
check("Mr. Brown: extra large text", c["text_scale"] == 1.6)
check("Mr. Brown: slow pace (more time for every movement)", brown["pace"] == "slow" and sara["pace"] == "normal")
check("Mr. Brown: three gestures incl. more detail", c["gesture_bar"] == ["Open palm = pause", "Thumb up = more detail", "Hold fist = finish visit"])
check("Mr. Brown: thumb up adds the detail", "blue stripes" in c["exhibit"]["story"])

mona = visit("Arabic", "adult", "woman", "evening")
c = mona["content"]
check("Mona: Evening view (dark background)", c["theme"]["bg"] == "#0f1726")
check("Mona: plum accent", c["theme"]["accent"] == "#a2457e")
check("Mona: feminine wording", c["gesture_bar"][1] == "اسحبي = القطعة التالية"
      and c["gesture_bar"][0] == "افتحي كفكِ = إيقاف")
check("Mona: full Arabic story", c["exhibit"]["length"] == "full" and "الحياة الأخرى" in c["exhibit"]["story"])
check("Mona: light pink line inside the photo and on the camera preview",
      c["theme"]["frame"] == c["theme"]["accent_text"] == c["theme"]["accent_light"] == "#f0b6d9")
check("Every look has the gold and the warning colours",
      all({"gold", "warn_bg", "warn_text", "accent_light", "frame"} <= set(r.theme(v, g))
          for v in ("day", "evening") for g in ("woman", "man", "skip", None)))

skip = visit("Arabic", "adult", "skip", "day", screen=3)["content"]
check("Skip: neutral Arabic wording", skip["labels"]["s3_hint"] == "القطعة الأقرب مظللة. السحب للتنقل.")
check("Skip: teal accent and female voice", skip["theme"]["accent"] == "#1f8f86" and skip["voice"] == "female")
fr = visit("French", "adult", "woman", "day", screen=1)["content"]
check("French woman: Bienvenue", fr["labels"]["welcome"] == "Bienvenue")
check("Before gender is chosen: neutral wording", GuideState(resolver=r).snapshot()["content"]["labels"]["s1_title"] == "Wave to start")

# ---- the narrator and the hold ring ----
check("Narrator speed: Sara normal, Omar a little slower, Mr. Brown slower",
      (sara["content"]["speech_rate"], omar["content"]["speech_rate"], brown["content"]["speech_rate"]) == (1.0, 0.95, 0.85))
check("Each chip says which gesture it is (for the hold ring)",
      omar["content"]["gesture_keys"] == ["gk_next", "gk_stop", "gk_done"]
      and len(sara["content"]["gesture_keys"]) == len(sara["content"]["gesture_bar"]))
girl = visit("Arabic", "children", "woman", "day")["content"]
check("With children: the short bar has the same simple words for every child",
      girl["gesture_bar"] == omar["content"]["gesture_bar"]
      == visit("Arabic", "children", "skip", "day")["content"]["gesture_bar"])
check("Narrator messages in the visitor's language",
      mona["content"]["labels"]["story_end"] == "انتهت القصة"
      and fr["labels"]["no_voice"].startswith("Pas de voix") and "🔊" in sara["content"]["labels"]["voice_blocked"])

# ---- the texts of the Figma screens ----
check("Hand lost: no screen of its own any more, only the small dot ('raise your hand' for Mona)",
      mona["content"]["labels"]["no_hand"] == "ارفعي يدكِ" and not any(k.startswith("s6") for k in r.ui))
check("Confirm screen: '94% sure' in each language",
      [visit(l, "adult", "man", "day", screen=4)["content"]["labels"]["sure"].replace("{n}", "94")
       for l in ("English", "Arabic", "French")] == ["94% sure", "نسبة التأكد 94%", "sûr à 94 %"])
check("Mr. Brown: 'Slower pace is on'", brown["content"]["labels"]["slow_pace"].startswith("Slower pace is on"))
check("Gesture names (for the toast) in the visitor's language",
      mona["content"]["labels"]["mv_pause_toggle"] == "كف مفتوح: إيقاف / تشغيل"
      and all("mv_" + k in sara["content"]["labels"] for k in ("wave", "swipe_right", "swipe_left", "confirm", "back", "pause_toggle", "finish")))
ex = mona["content"]["exhibit"]
check("Story screen: a real photo with its credit, and three short facts",
      ex["photo"] == "photos/golden_mask.jpg" and "CC BY" in ex["credit"] and len(ex["facts"]) == 3
      and all(len(sara["content"]["exhibit"]["facts"]) == 3 for _ in [0]))
import os
check("Every exhibit photo is in web/photos",
      all(os.path.isfile(os.path.join("ui", "web", e["photo"])) for e in r.exhibits.values() if e.get("photo")))
check("Welcome screen: privacy note and language hint", fr["labels"]["s1_privacy"].startswith("La caméra")
      and sara["content"]["labels"]["s1_lang"].startswith("Language:"))
check("Welcome screen after the wave: 'Hand detected'; the dot at the top says 'Hand seen' / 'Raise your hand'",
      sara["content"]["labels"]["hand_seen"] == "Hand detected" and sara["content"]["labels"]["hand_ok"] == "Hand seen"
      and sara["content"]["labels"]["no_hand"] == "Raise your hand")
no_tag = ContextResolver()
no_tag.exhibits["throne"].pop("tag", None)        # an exhibit added without a short name
check("Screen 3: short names on the camera boxes like the design (Golden Mask 94%), full names in the list",
      sara["content"]["exhibit_tags"]["Golden Funerary Mask"] == "Golden Mask"
      and sara["content"]["exhibit_names"]["Golden Funerary Mask"] == "Golden Funerary Mask"
      and omar["content"]["exhibit_tags"]["Throne"] == "العرش"
      and GuideState(resolver=no_tag).snapshot()["content"]["exhibit_tags"]["Throne"] == "Royal Throne")

# ---- every text exists in the three languages, and every Woman/Man/Skip text has the three forms ----
missing = [f"{k}/{lang}" for k, v in r.ui.items() if not k.startswith("_")
           for lang in ("English", "Arabic", "French")
           if not v.get(lang) or (isinstance(v[lang], dict) and set(v[lang]) != {"f", "m", "n"})]
check("All texts in English, Arabic and French" + (f" (missing: {missing})" if missing else ""), not missing)
check("precondition: the texts file has the narrator and Figma texts",
      {"story_end", "no_voice", "voice_blocked", "s1_lang", "s1_privacy", "gx_yes", "gx_no", "sure",
       "ex_ok", "hand_ok", "hand_seen", "slow_pace", "no_hand", "camera_off"} <= set(r.ui))
print("ALL PASS" if ok else "SOME FAILED")
