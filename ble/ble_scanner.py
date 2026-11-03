"""Bluetooth: discover visitors nearby and capture their user id.

A visitor's phone advertises over Bluetooth Low Energy with a local name like
"MG-U042" (MG = Museum Guide, U042 = user id). Any BLE advertiser app works,
for example nRF Connect, or our own visitor app later.
The scanner picks the NEAREST phone (strongest signal), ignores weak signals,
and waits for two sightings before it announces someone, so a person walking
past the hall does not trigger the guide.

Run:  python -m ble.ble_scanner [--server 127.0.0.1:5050]
      python -m ble.ble_scanner --list       the Bluetooth names heard nearby for 5 s (to check a phone)
"""
import argparse
import asyncio
import time

from network.protocol import no_quick_edit, parse_server

PREFIX = "MG-"
MIN_RSSI = -70          # dBm, weaker than this is too far from the screen
SEEN_TWICE = 2          # sightings needed before "arrived"
LEAVE_AFTER = 6.0       # seconds without a sighting before "left"
# An iPhone often hides its name in the advertisement. A phone that advertises this service
# (181C, "User Data": nRF Connect > Peripheral > This Device) is accepted too, as visitor PHONE_ID.
PHONE_SERVICE = "0000181c-0000-1000-8000-00805f9b34fb"
PHONE_ID = "U042"


def visitor_name(name, uuids=(), phone_id=PHONE_ID):
    """The name the tracker should see: the real MG- name, or MG-<phone_id> for a phone with the service."""
    if VisitorTracker.user_id(name):
        return name
    if PHONE_SERVICE in [u.lower() for u in uuids or ()]:
        return PREFIX + phone_id
    return name


class VisitorTracker:
    """Pure logic, no Bluetooth needed. Feed it (name, rssi) lists."""

    def __init__(self, min_rssi=MIN_RSSI, seen_twice=SEEN_TWICE, leave_after=LEAVE_AFTER):
        self.min_rssi, self.seen_twice, self.leave_after = min_rssi, seen_twice, leave_after
        self.current = None
        self.candidate, self.count = None, 0
        self.last_seen = 0.0

    @staticmethod
    def user_id(name):
        return name[len(PREFIX):] if name and name.startswith(PREFIX) and len(name) > len(PREFIX) else None

    def nearest(self, adverts):
        best = None
        for name, rssi in adverts:
            uid = self.user_id(name)
            if uid and rssi >= self.min_rssi and (best is None or rssi > best[1]):
                best = (uid, rssi)
        return best[0] if best else None

    def update(self, adverts, now=None):
        """Returns ('arrived', id), ('left', None) or None."""
        now = time.time() if now is None else now
        uid = self.nearest(adverts)
        if uid:
            self.last_seen = now
            if uid == self.current:
                return None
            if uid == self.candidate:
                self.count += 1
            else:
                self.candidate, self.count = uid, 1
            if self.count >= self.seen_twice:
                self.current, self.candidate, self.count = uid, None, 0
                return ("arrived", uid)
        elif self.current and now - self.last_seen > self.leave_after:
            self.current = None
            return ("left", None)
        return None


async def scan(on_change, interval=1.0, phone_id=PHONE_ID):
    from bleak import BleakScanner          # imported here so tests need no Bluetooth
    tracker = VisitorTracker()
    seen = {}

    def cb(device, adv):
        seen[device.address] = (visitor_name(adv.local_name or device.name, adv.service_uuids, phone_id), adv.rssi)

    async with BleakScanner(cb):
        while True:
            await asyncio.sleep(interval)
            ev = tracker.update(list(seen.values()))
            seen.clear()
            if ev:
                on_change(*ev)


async def list_nearby(seconds=5.0):
    """Print every Bluetooth name heard for a few seconds, strongest first."""
    from bleak import BleakScanner
    found = {}

    def cb(device, adv):
        found[device.address] = (visitor_name(adv.local_name or device.name or "(no name)", adv.service_uuids), adv.rssi)

    print(f"Listening for {seconds:.0f} seconds ...")
    async with BleakScanner(cb):
        await asyncio.sleep(seconds)
    if not found:
        print("Nothing heard. Is the phone advertising (nRF Connect > Advertiser) and close to the PC?")
    for name, rssi in sorted(found.values(), key=lambda x: -x[1]):
        uid = VisitorTracker.user_id(name)
        note = ""
        if uid:
            note = f"   <- visitor {uid}" + ("" if rssi >= MIN_RSSI else " (too far: move the phone closer)")
        print(f"{rssi:5d} dBm  {name}{note}")


def run_ble(job):
    try:
        asyncio.run(job)
    except KeyboardInterrupt:
        pass
    except Exception as e:                  # Bluetooth off, no adapter, or a driver problem
        raise SystemExit(f"Bluetooth cannot scan ({e}).\n"
                         "Turn Bluetooth on: Windows Settings > Bluetooth & devices > Bluetooth = On.\n"
                         "No Bluetooth on this PC? Test the same thing without it: python -m ble.fake_phone U042")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", help="hub address, for example 127.0.0.1:5050")
    ap.add_argument("--phone-id", default=PHONE_ID, help="visitor id for a phone that advertises the 181C service")
    ap.add_argument("--list", action="store_true", help="only show the Bluetooth names heard nearby")
    args = ap.parse_args()
    no_quick_edit()
    try:
        import bleak  # noqa: F401
    except ImportError:
        raise SystemExit("The Bluetooth library (bleak) is not installed: run setup_and_test.bat once.")
    if args.list:
        return run_ble(list_nearby())
    client = None
    if args.server:
        from network.client import GuideClient
        host, port = parse_server(args.server)
        try:
            while client is None:             # started together with the hub: wait for it, however long
                try:
                    client = GuideClient("bluetooth", host, port)
                except ConnectionError as e:
                    print(f"{e} Trying again ... (run_full_system.bat starts it)")
        except KeyboardInterrupt:
            return

    def changed(kind, uid):
        print(f"[{time.strftime('%H:%M:%S')}] {kind} {uid or ''}")
        if client:
            client.visitor(uid)

    print("Looking for visitors' phones (Bluetooth names that start with MG-) ...")
    run_ble(scan(changed, phone_id=args.phone_id))


if __name__ == "__main__":
    main()
