Training recordings for the DollarPy templates (tracking/templates/swipes.json).

Source: github.com/imsparsh/Gesture-Recognition-Dataset (MIT licence), val folder.
Webcam clips of a hand swipe, one folder per clip, ~30 PNG pictures each (30 fps).
"Left_Swipe" / "Right_Swipe" in the folder name is the direction.
26 clips (13 left, 13 right). MediaPipe found a usable swipe in 16 of them: 9 right, 7 left templates.

Rebuild the templates from them (MediaPipe takes the wrist of every picture):
    python -m tracking.make_templates tracking/recordings /tmp/swipes_check.json
The waves are chained from real swipes, they are not in the data set.
