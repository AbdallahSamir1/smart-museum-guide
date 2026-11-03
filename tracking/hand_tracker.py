"""Hand tracking with MediaPipe. Works with both MediaPipe APIs:
  - new versions (Python 3.13, mediapipe 0.10.20 and later): Tasks API + models/hand_landmarker.task
  - old versions (mediapipe 0.10.14 and earlier): mp.solutions.hands
process(frame_bgr) returns (landmarks, world_landmarks) or (None, None) when no hand is seen.
landmarks: 21 (x, y, z) points, x and y in 0..1 of the picture, z the depth from the wrist.
world_landmarks: the same 21 points in metres, a 3D hand that does not change with the
camera angle, so a tilted or turned hand keeps the same shape.
"""
import os
import time

import cv2
import mediapipe as mp

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "models", "hand_landmarker.task")
CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
               (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
               (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]


class HandTracker:
    def __init__(self, min_conf=0.5, video=True):
        # 0.5 (the MediaPipe default) keeps tracking a hand that is tilted or turned
        self.legacy = hasattr(mp, "solutions")
        if self.legacy:
            self.hands = mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=min_conf,
                                                  min_tracking_confidence=min_conf,
                                                  static_image_mode=not video)
        else:
            if not os.path.exists(MODEL):
                raise FileNotFoundError(
                    f"The hand model is missing: {MODEL}\n"
                    "Download hand_landmarker.task from\n"
                    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                    "hand_landmarker/float16/latest/hand_landmarker.task\n"
                    "and put it in the models folder.")
            from mediapipe.tasks.python import BaseOptions, vision
            mode = vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE
            opts = vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=MODEL), running_mode=mode, num_hands=1,
                min_hand_detection_confidence=min_conf, min_hand_presence_confidence=min_conf,
                min_tracking_confidence=min_conf)
            self.hands = vision.HandLandmarker.create_from_options(opts)
        self.video = video
        self.t0 = time.time()
        self.last_ms = -1

    def process(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if self.legacy:
            res = self.hands.process(rgb)
            if not res.multi_hand_landmarks:
                return None, None
            lm = res.multi_hand_landmarks[0].landmark
            world = res.multi_hand_world_landmarks[0].landmark if res.multi_hand_world_landmarks else None
        else:
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            if self.video:
                ms = max(int((time.time() - self.t0) * 1000), self.last_ms + 1)
                self.last_ms = ms
                res = self.hands.detect_for_video(image, ms)
            else:
                res = self.hands.detect(image)
            if not res.hand_landmarks:
                return None, None
            lm = res.hand_landmarks[0]
            world = res.hand_world_landmarks[0] if res.hand_world_landmarks else None
        points = [(p.x, p.y, p.z) for p in lm]
        world = [(p.x, p.y, p.z) for p in world] if world else None
        return points, world

    def close(self):
        self.hands.close()

    @staticmethod
    def draw(frame, lm):
        h, w = frame.shape[:2]
        pts = [(int(p[0] * w), int(p[1] * h)) for p in lm]
        for a, b in CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], (112, 224, 192), 2)
        for p in pts:
            cv2.circle(frame, p, 4, (255, 255, 255), -1)
