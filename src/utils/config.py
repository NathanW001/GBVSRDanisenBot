import json
import os
import logging

def save_config(file_path, config):
    """Save configuration to file"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save config: {e}")

def load_config(file_path, default_config=None):
    """Load configuration from file"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
    return default_config if default_config is not None else {}