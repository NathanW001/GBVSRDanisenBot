import os

# Project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')
DB_PATH = os.path.join(CONFIG_DIR, 'danisen.db')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
LOG_FILE = os.path.join(PROJECT_ROOT, 'bot.log')

# Default configuration
DEFAULT_CONFIG = {
    "bot_token": "",
    "ACTIVE_MATCHES_CHANNEL_ID": "0",
    "REPORTED_MATCHES_CHANNEL_ID": "0",
    "total_dans": 7,
    "minimum_derank": 2,
    "maximum_rank_difference": 1,
    "rank_gap_for_more_points": 1,
    "recent_opponents_limit": 2,
    "point_rollover": True,
    "queue_status": True,
    "special_rank_up_rules": False,
    "max_active_matches": 3
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
GUI_WINDOW_TITLE = "Danisen Bot"
GUI_MIN_WIDTH = 600
GUI_MIN_HEIGHT = 400

# Ensure config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)