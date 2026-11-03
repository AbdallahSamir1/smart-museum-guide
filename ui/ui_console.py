"""Stand-in for the Figma screens: prints the screen the visitor should see.
Run:  python -m ui.ui_console     (the real UI will use the same socket messages)"""
import time

from network.client import GuideClient

NAMES = {1: "Wave to start", 2: "Who is visiting", 3: "Find your exhibit",
         4: "Is this the one?", 5: "Exhibit story", 6: "We cannot see your hand"}


def show(s):
    extra = f"  highlight={s['highlight']}" if s["highlight"] else ""
    if s["screen"] == 5:
        extra = f"  {s['exhibit']}  {'PAUSED' if s['paused'] else 'playing'}{'  +detail' if s['detail'] else ''}"
    print(f"Screen {s['screen']}: {NAMES[s['screen']]}{extra}  [{s['view']} view, {s['language']}]")


if __name__ == "__main__":
    try:
        GuideClient("ui", on_state=show)
    except ConnectionError as e:
        raise SystemExit(f"{e} (run_full_system.bat starts it)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:                 # Ctrl+C: stop without a Python error
        pass
