import json
import os

# ROOT_DIR = os.path.expanduser("~/.pl")
ROOT_DIR = os.path.expanduser(".")
os.makedirs(ROOT_DIR, exist_ok=True)

INIT_SCREEN = "overview"
APP_DIR = os.path.dirname(os.path.realpath(__file__))
CRASH_FILE = os.path.join(ROOT_DIR, "crash.dump")