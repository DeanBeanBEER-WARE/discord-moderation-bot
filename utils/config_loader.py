"""Loads configuration (tokens, settings) from environment variables and config.json (as fallback for settings)."""
import os
import json
from utils.logger import get_logger

config_logger = get_logger(__name__)

# --- Secrets: ALWAYS from environment variables (Cloud Run best practice) ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not DISCORD_BOT_TOKEN:
    config_logger.error("DISCORD_BOT_TOKEN not found in environment variables!")
if not OPENAI_API_KEY:
    config_logger.error("OPENAI_API_KEY not found in environment variables!")

# --- Settings: Try environment variable first, then config.json ---
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CONFIG_DIR)
CONFIG_FILE_PATH = os.path.join(PROJECT_ROOT, "config.json")
config_logger.info(f"Expected path for config.json: {CONFIG_FILE_PATH}")

config_data = {}
try:
    with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    config_logger.info(f"{CONFIG_FILE_PATH} loaded successfully.")
except FileNotFoundError:
    config_logger.error(f"{CONFIG_FILE_PATH} not found. Default settings will be used or need to be set manually.")
except json.JSONDecodeError:
    config_logger.error(f"Error parsing {CONFIG_FILE_PATH}. Please check the JSON syntax.")
except Exception as e:
    config_logger.error(f"An unexpected error occurred while loading {CONFIG_FILE_PATH}: {e}")

def get_config(key_path: str, default=None):
    """
    Access nested config values using a path (e.g., "moderation_rules.timeout_durations.short").
    Tries environment variable first (uppercased, underscores), then config.json, then default.
    """
    # Try environment variable first
    env_key = key_path.upper().replace('.', '_')
    env_value = os.environ.get(env_key)
    if env_value is not None:
        return env_value
    # Fallback: config.json
    keys = key_path.split('.')
    value = config_data
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        config_logger.warning(f"Configuration key '{key_path}' not found or invalid path. Default value '{default}' will be used.")
        return default

BOT_PREFIX = get_config("bot_prefix", "!")
LOG_CHANNEL_ID = get_config("log_channel_id")
MODERATION_RULES_CONFIG = get_config("moderation_rules", {})
GPT_SETTINGS = get_config("gpt_settings", {})
RULES_CHANNEL_CONFIG = get_config("rules_channel", {"enabled": False, "channel_id": ""})
CUSTOM_RULES_PROMPT_CONFIG = get_config("custom_rules_prompt", {"enabled": False, "prompt": ""})
MAX_LENIENCY_LEVEL = get_config("membership_moderation_leniency.max_leniency_level", 100)
CUSTOM_RULES_PROMPT_EXCLUSIVE = CUSTOM_RULES_PROMPT_CONFIG.get("exclusive", False)
MODERATION_ACTIONS_CONFIG = get_config("moderation_actions", {})
ACTIONS_FOR_RESULT_CONFIG = MODERATION_ACTIONS_CONFIG.get("actions_for_result", {})
CUSTOM_ACTIONS_FOR_RESULT_CONFIG = MODERATION_ACTIONS_CONFIG.get("custom_actions_for_result", {})

if __name__ == "__main__":
    config_logger.info(f"Bot Token: {'Present' if DISCORD_BOT_TOKEN else 'Missing'}")
    config_logger.info(f"OpenAI Key: {'Present' if OPENAI_API_KEY else 'Missing'}")
    config_logger.info(f"Bot Prefix: {BOT_PREFIX}")
    config_logger.info(f"Log Channel ID: {LOG_CHANNEL_ID}")
    config_logger.info(f"Moderation Rules: {json.dumps(MODERATION_RULES_CONFIG, indent=2)}")
    config_logger.info(f"GPT Settings: {json.dumps(GPT_SETTINGS, indent=2)}")
    config_logger.info(f"Rules Channel Config: {json.dumps(RULES_CHANNEL_CONFIG, indent=2)}")
    config_logger.info(f"Custom Rules Prompt Config: {json.dumps(CUSTOM_RULES_PROMPT_CONFIG, indent=2)}")
    config_logger.info(f"Specific action for [INSULT]: {get_config('moderation_rules.actions_for_result.[INSULT]')}") 