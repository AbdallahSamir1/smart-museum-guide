"""Tells the hub whether the hall should be in Day view or Evening view.

It reads the clock and, if a camera index is given, the light level in the hall
(average brightness of the camera image, 0 = dark, 1 = bright).
    python -m context.sensor --server 127.0.0.1:5050             clock only
    python -m context.sensor --server 127.0.0.1:5050 --camera 1  clock + hall light
    python -m context.sensor --server 127.0.0.1:5050 --force evening   for a demo
"""
import argparse
import time

from context.resolver import decide_view


def light_level(cap):
    import cv2
    ok, frame = cap.read()
    if not ok:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(gray.mean()) / 255.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="127.0.0.1:5050")
    ap.add_argument("--camera", type=int)
    ap.add_argument("--force", choices=["day", "evening"])
    ap.add_argument("--every", type=float, default=30.0, help="seconds between readings")
    args = ap.parse_args()
    from network.client import GuideClient
    from network.protocol import no_quick_edit, parse_server
    host, port = parse_server(args.server)
    no_quick_edit()
    try:
        client = GuideClient("context", host, port)
    except ConnectionError as e:
        raise SystemExit(f"{e} (run_full_system.bat starts it)")
    cap = None
    if args.camera is not None:
        import cv2
        cap = cv2.VideoCapture(args.camera)
    last = None
    while True:
        light = light_level(cap) if cap else None
        view = args.force or decide_view(time.localtime().tm_hour, light)
        if view != last:
            client.context(view)
            print(f"[{time.strftime('%H:%M')}] {view} view (light={light})")
            last = view
        if args.force:
            time.sleep(1)
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
