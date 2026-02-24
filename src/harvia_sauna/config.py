"""Configuration loading for Harvia Sauna."""

import json
import logging
import os

logger = logging.getLogger("harvia_sauna")

DEFAULT_CONFIG_PATHS = [
    os.path.expanduser("~/.config/harvia-homekit/config.json"),
    "/etc/harvia-homekit/config.json",
]


def get_config(config_path=None):
    """Load configuration from file.

    Searches default paths if *config_path* is not given.
    Returns the parsed dict or ``None`` on failure.
    """
    if config_path is None:
        for path in DEFAULT_CONFIG_PATHS:
            if os.path.exists(path):
                config_path = path
                break

        if config_path is None:
            logger.error("No configuration file found")
            return None

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return None
