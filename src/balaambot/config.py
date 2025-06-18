# This file holds all global config variables
# Import the whole file if you need to access any of these
import os

from discord.ext import voice_recv

DISCORD_VOICE_CLIENT = voice_recv.VoiceRecvClient

# Docker volume to hold all persistent data
PERSISTENT_DATA_DIR = os.getenv("PERSISTENT_DATA_DIR", default="persistent")

USE_REDIS = os.getenv("USE_REDIS", "false").lower() == "true"
REDIS_KEY = os.getenv("BALAAMBOT_REDIS_HASH_KEY", "balaambot")
ADDRESS = os.getenv("REDIS_ADDRESS", "localhost")
PORT = int(os.getenv("REDIS_PORT", "6379"))
DB = int(os.getenv("REDIS_DB", "0"))
USERNAME = os.getenv("REDIS_USERNAME", None)
PASSWORD = os.getenv("REDIS_PASSWORD", None)
