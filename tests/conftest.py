import os

# GUI tests never open windows on the real desktop.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
