"""Contains individual moderation action functions for the bot."""
import discord
import datetime
from utils.logger import get_logger
from .gpt_integration import detect_language_with_gpt, translate_text_with_gpt
from . import prompts

modact_logger = get_logger(__name__)

async def delete_message(message: discord.Message) -> str:
    """Deletes a message if possible."""
    try:
        await message.delete()
        modact_logger.info(f"Message {message.id} deleted.")
        return "Message deleted"
    except discord.Forbidden:
        modact_logger.warning(f"Failed to delete message {message.id}: Forbidden.")
        return "Failed to delete message (Forbidden)"
    except discord.NotFound:
        modact_logger.warning(f"Failed to delete message {message.id}: Not found.")
        return "Failed to delete message (Not Found)"
    except Exception as e:
        modact_logger.error(f"Failed to delete message {message.id}: {e}")
        return f"Failed to delete message (Exception: {e})"

async def send_dm_warning(user: discord.User, message: discord.Message, reason: str, default_language: str = "en") -> str:
    """Sends a DM warning to the user, translated into the language of the original message."""
    try:
        detected_language = await detect_language_with_gpt(message.content)
        target_lang = detected_language if detected_language and detected_language != "unknown" else default_language
        prompt_kwargs = {
            "user_mention": user.mention,
            "channel_name": str(message.channel),
            "guild_name": str(message.guild.name if message.guild else "Unknown Server"),
            "reason": reason
        }
        base_warn = prompts.BASE_WARN_MESSAGE_ENGLISH.format(**prompt_kwargs)
        if target_lang != default_language:
            translated = await translate_text_with_gpt(
                text_to_translate=base_warn,
                target_language=target_lang,
                base_system_prompt=prompts.TRANSLATE_WARN_MESSAGE_SYSTEM_PROMPT,
                **prompt_kwargs
            )
            warn_text = translated if translated else base_warn
        else:
            warn_text = base_warn
        await user.send(warn_text)
        modact_logger.info(f"DM warning sent to {user} (lang: {target_lang}).")
        return f"DM warning sent (language: {target_lang})"
    except discord.Forbidden:
        modact_logger.warning(f"Failed to send DM warning to {user}: Forbidden.")
        return "Failed to send DM warning (Forbidden)"
    except Exception as e:
        modact_logger.error(f"Failed to send DM warning to {user}: {e}")
        return f"Failed to send DM warning (Exception: {e})"

async def timeout_user(member: discord.Member, duration_seconds: int, reason: str, guild_name: str) -> str:
    """Times out a user for a specified duration and informs them via DM."""
    try:
        timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
        await member.timeout(timeout_until, reason=reason)
        try:
            dm_message = f"You have been muted on the server '{guild_name}' for {duration_seconds} seconds (until {timeout_until.strftime('%Y-%m-%d %H:%M:%S UTC')}). Reason: {reason}"
            await member.send(dm_message)
        except Exception as e_dm:
            modact_logger.warning(f"Failed to send timeout info DM to {member}: {e_dm}")
        modact_logger.info(f"User {member} timed out for {duration_seconds}s.")
        return f"User timed out ({duration_seconds}s)"
    except discord.Forbidden:
        modact_logger.warning(f"Failed to timeout user {member}: Forbidden.")
        return "Timeout failed (Forbidden)"
    except Exception as e:
        modact_logger.error(f"Failed to timeout user {member}: {e}")
        return f"Timeout failed (Exception: {e})"

async def delete_all_messages_in_channel(channel: discord.TextChannel, limit: int = 100) -> str:
    """
    Deletes all messages in the specified channel (up to the specified limit, default: 100).
    CAUTION: Be aware of Discord API limitations! For large channels, consider calling multiple times or adjusting the limit.
    """
    deleted_count = 0
    try:
        async for msg in channel.history(limit=limit):
            try:
                await msg.delete()
                modact_logger.info(f"Message {msg.id} by {msg.author} deleted in channel {channel.name}.")
                deleted_count += 1
            except Exception as e:
                modact_logger.warning(f"Failed to delete message {msg.id} in channel {channel.name}: {e}")
        return f"Deleted {deleted_count} messages in channel {channel.name}."
    except Exception as e:
        modact_logger.error(f"Failed to iterate messages in channel {channel.name}: {e}")
        return f"Failed to delete all messages in channel {channel.name}: {e}"