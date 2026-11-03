"""Remembers what a returning visitor chose, keyed by the Bluetooth user id."""
import json
import os
import sys


class ProfileStore:
    def __init__(self, path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.json")):
        self.path = path
        self.data = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("the file does not hold a list of visitors")
                self.data = data
            except (OSError, ValueError) as e:
                # keep the damaged file for a person to look at, and start with no profiles
                bad = path + ".bad"
                try:
                    os.replace(path, bad)
                except OSError:
                    bad = None
                print(f"profiles: cannot read {path} ({e}); "
                      + (f"it was kept as {bad}; " if bad else "")
                      + "starting with no saved visitors", file=sys.stderr)

    def get(self, user_id):
        return self.data.get(user_id)

    def save(self, user_id, language, visitor_type, gender):
        self.data[user_id] = {"language": language, "visitor_type": visitor_type,
                              "gender": gender}
        if not self.path:
            return True
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)          # closing the hub while saving never leaves half a file
            return True
        except OSError as e:                    # read-only folder, file open in another program ...
            print(f"profiles: cannot save {self.path} ({e}); the visit goes on and the "
                  "choices are kept until the hub is closed", file=sys.stderr)
            return False
