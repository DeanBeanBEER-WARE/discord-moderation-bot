"""Logging functionalities for the bot."""
import logging
import sys
import discord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def get_logger(name: str):
    """Returns a logger instance with the specified name."""
    return logging.getLogger(name)

app_logger = get_logger("DiscordModBot")
discord_event_logger = get_logger("utils.discord_event_logger")

async def log_event_to_discord(client: discord.Client, log_channel_id: int, embed: discord.Embed):
    """
    Sends a formatted embed message to a specific Discord channel.

    Args:
        client: The discord.Client instance of the bot.
        log_channel_id: The ID of the Discord channel to log to.
        embed: The discord.Embed object to be sent.
    """
    if not log_channel_id:
        discord_event_logger.debug("No log_channel_id configured. Skipping Discord log.")
        return

    try:
        channel = client.get_channel(log_channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)
            discord_event_logger.debug(f"Event successfully logged to channel {log_channel_id}.")
        elif not channel:
            discord_event_logger.warning(f"Discord log channel with ID {log_channel_id} not found.")
        else:
            discord_event_logger.warning(f"Channel with ID {log_channel_id} is not a text channel. Type: {type(channel)}")
    except discord.Forbidden:
        discord_event_logger.error(f"Missing permissions to write to channel {log_channel_id}.")
    except discord.HTTPException as e:
        discord_event_logger.error(f"HTTP error while sending log message to channel {log_channel_id}: {e}")
    except Exception as e:
        discord_event_logger.error(f"Unexpected error while logging to Discord channel {log_channel_id}: {e}")

if __name__ == "__main__":
    app_logger.info("Logger initialized and a test message was sent.")
    app_logger.debug("This is a debug message.")
    app_logger.warning("This is a warning.")