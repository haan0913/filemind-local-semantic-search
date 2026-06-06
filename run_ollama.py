import os
import sys

os.chdir("C:/AI_STATION/filemind")
sys.path.insert(0, "C:/AI_STATION/filemind")

import config
config.OPENROUTER_API_KEY = ""
config.config.openrouter_api_key = ""

from run import main

sys.argv = ["run_ollama.py", "scan", "--full"]
main()
