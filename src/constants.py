import os
import sys

if  hasattr(sys, '_MEIPASS'):  # Running as bundled EXE
    PROJECT_ROOT = os.path.dirname(sys.executable)
    CONFIG_DIR = PROJECT_ROOT
else:  # Running from source
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')
# Project paths

DB_PATH = os.path.join(CONFIG_DIR, 'ranked.db')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
LOG_FILE = os.path.join(PROJECT_ROOT, 'bot.log')

# Default configuration
DEFAULT_CONFIG = {
    "ACTIVE_MATCHES_CHANNEL_ID": "0",
    "REPORTED_MATCHES_CHANNEL_ID": "0",
    "ONGOING_MATCHES_CHANNEL_ID": "0",
    "WELCOME_CHANNEL_ID": "0",
    "recent_opponents_limit": 3,
    "queue_status": True,
    "max_active_matches": 5,
    "characters": [],
    "character_limit": 3,
    "emoji_mapping": {},
    "character_aliases": {},
    "glicko_tau": 0.3,
    "glicko_default_rating": 1500,
    "glicko_default_rd": 350,
    "glicko_default_volatility": 0.06,
    "glicko_rating_period_length": 3
}
# Logging colors
LOG_COLORS = {
    'DEBUG': 'black',
    'INFO': 'blue',
    'WARNING': 'orange',
    'ERROR': 'red',
    'CRITICAL': 'purple'
}

# GUI constants
GUI_WINDOW_TITLE = "Ranked Bot"
GUI_MIN_WIDTH = 600
GUI_MIN_HEIGHT = 400


#Danisen Constants
MAX_FIELDS_PER_EMBED = 10
DEFAULT_RATING = 1500.0
DEFAULT_RATING_DEVIATION = 350.0

# Ensure config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)