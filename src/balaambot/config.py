# This file holds all global config variables
# Import the whole file if you need to access any of these
import os
import pathlib

# Docker volume to hold all persistent data
_persistent_dir_path = os.getenv("PERSISTENT_DATA_DIR", default="persistent")
PERSISTENT_DATA_DIRECTORY = pathlib.Path(_persistent_dir_path).resolve()
PERSISTENT_DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
