# This file holds all global config variables
# Import the whole file if you need to access any of these
import os

from discord.ext import voice_recv

DISCORD_VOICE_CLIENT = voice_recv.VoiceRecvClient

# Docker volume to hold all persistent data
PERSISTENT_DATA_DIR = os.getenv("PERSISTENT_DATA_DIR", default="persistent")
