"""Implementation of moderation rules and actions."""
import discord
import datetime
from utils.logger import get_logger, log_event_to_discord
from utils import config_loader
from . import prompts
from .gpt_integration import detect_language_with_gpt, translate_text_with_gpt
from . import moderation_actions

mod_logger = get_logger(__name__)

ACTIONS_FOR_RESULT_CONFIG = config_loader.ACTIONS_FOR_RESULT_CONFIG
CUSTOM_ACTIONS_FOR_RESULT_CONFIG = config_loader.CUSTOM_ACTIONS_FOR_RESULT_CONFIG
TIMEOUT_DURATIONS_CONFIG = config_loader.get_config("moderation_rules.timeout_durations", {})
DEFAULT_WARN_LANGUAGE = config_loader.get_config("moderation_rules.default_warn_language", "en")
LOG_CHANNEL_ID = config_loader.get_config("log_channel_id")

async def handle_moderation_action(client: discord.Client, message: discord.Message, gpt_analysis_result: str, leniency_level: int = 0):
    """
    Führt Moderationsaktionen basierend auf dem GPT-Analyseergebnis und dem Leniency-Level aus.
    Berücksichtigt die neue Trennung zwischen Standard- und Custom-Flags.
    """
    normalized_gpt_result = gpt_analysis_result.strip().upper()
    performed_actions_summary = []

    # Prüfe, ob Custom Rules aktiv sind
    CUSTOM_RULES_ENABLED = config_loader.CUSTOM_RULES_PROMPT_CONFIG.get("enabled", False)

    actions_to_take = None
    if CUSTOM_RULES_ENABLED and normalized_gpt_result in CUSTOM_ACTIONS_FOR_RESULT_CONFIG:
        actions_to_take = CUSTOM_ACTIONS_FOR_RESULT_CONFIG.get(normalized_gpt_result, ["log_action"])
        mod_logger.info(f"Custom-Flag erkannt: {normalized_gpt_result}, Aktionen: {actions_to_take}")
    else:
        actions_to_take = ACTIONS_FOR_RESULT_CONFIG.get(normalized_gpt_result, ["log_action"])
        mod_logger.info(f"Standard-Flag oder Custom Rules nicht aktiv. Aktionen: {actions_to_take}")

    # Load insult_deletion_threshold from config (default 70)
    LENIENCY_CONFIG = config_loader.get_config("membership_moderation_leniency", {})
    INSULT_DELETION_THRESHOLD = LENIENCY_CONFIG.get("insult_deletion_threshold", 70)

    mod_logger.info(f"For GPT result '{normalized_gpt_result}', actions loaded from config: {actions_to_take}")
    mod_logger.info(f"Full ACTIONS_FOR_RESULT_CONFIG: {ACTIONS_FOR_RESULT_CONFIG}")

    timeout_info = None
    for action in actions_to_take:
        if action == "delete_message":
            if message.guild:
                try:
                    await message.delete()
                    mod_logger.info(f"Message {message.id} by {message.author} deleted. GPT: {gpt_analysis_result}. (Leniency: {leniency_level})")
                    performed_actions_summary.append("Message deleted")
                except discord.Forbidden:
                    mod_logger.warning(f"Could not delete message {message.id}: Missing permissions.")
                    performed_actions_summary.append("Failed to delete message (Forbidden)")
                except discord.NotFound:
                    mod_logger.warning(f"Could not delete message {message.id}: Not found.")
                    performed_actions_summary.append("Failed to delete message (Not Found)")
                except Exception as e:
                    mod_logger.error(f"Error deleting message {message.id}: {e}")
                    performed_actions_summary.append(f"Failed to delete message (Exception: {e})")
            else:
                mod_logger.info(f"Message {message.id} (DM) not deleted. GPT: {gpt_analysis_result}")
                performed_actions_summary.append("Message (DM) not deleted")
        elif action == "warn_user_eph_public":
            try:
                user_to_warn = message.author
                detected_language = await detect_language_with_gpt(message.content)
                target_lang_for_translation = DEFAULT_WARN_LANGUAGE
                if detected_language and detected_language != "unknown" and detected_language != DEFAULT_WARN_LANGUAGE:
                    target_lang_for_translation = detected_language
                gpt_flag_en = normalized_gpt_result
                prompt_kwargs = {
                    "user_mention": user_to_warn.mention,
                    "channel_name": str(message.channel),
                    "guild_name": str(message.guild.name if message.guild else "Unknown Server"),
                    "reason": gpt_flag_en
                }
                final_warn_message = ""
                if target_lang_for_translation != DEFAULT_WARN_LANGUAGE:
                    translated_warn_text = await translate_text_with_gpt(
                        text_to_translate=prompts.BASE_WARN_MESSAGE_ENGLISH.format(**prompt_kwargs),
                        target_language=target_lang_for_translation,
                        base_system_prompt=prompts.TRANSLATE_WARN_MESSAGE_SYSTEM_PROMPT,
                        **prompt_kwargs
                    )
                    if translated_warn_text:
                        final_warn_message = translated_warn_text
                        warn_dm_sent_lang = target_lang_for_translation
                    else:
                        final_warn_message = prompts.BASE_WARN_MESSAGE_ENGLISH.format(**prompt_kwargs)
                        warn_dm_sent_lang = DEFAULT_WARN_LANGUAGE
                        performed_actions_summary.append(f"DM warning (translation failed, fallback to {DEFAULT_WARN_LANGUAGE})")
                else:
                    final_warn_message = prompts.BASE_WARN_MESSAGE_ENGLISH.format(**prompt_kwargs)
                    warn_dm_sent_lang = DEFAULT_WARN_LANGUAGE
                if hasattr(user_to_warn, 'send'):
                    await user_to_warn.send(final_warn_message)
                    mod_logger.info(f"Warning ('{warn_dm_sent_lang}') sent via DM to {user_to_warn} for GPT: {gpt_analysis_result}.")
                    performed_actions_summary.append(f"DM warning sent (language: {warn_dm_sent_lang})")
                else:
                    mod_logger.warning(f"Could not send DM to {user_to_warn}.")
                    performed_actions_summary.append("Failed to send DM warning (user has no send method)")
            except discord.Forbidden:
                mod_logger.warning(f"Could not send DM warning to {message.author} (Forbidden).")
                performed_actions_summary.append("Failed to send DM warning (Forbidden)")
            except Exception as e:
                mod_logger.error(f"Error sending DM warning to {message.author}: {e}.")
                performed_actions_summary.append(f"Failed to send DM warning (Exception: {e})")
        elif action.startswith("timeout_user_"):
            duration_key = action.split("timeout_user_")[-1]
            duration_seconds = TIMEOUT_DURATIONS_CONFIG.get(duration_key)
            if duration_seconds and message.guild and isinstance(message.author, discord.Member):
                try:
                    member_to_timeout = message.author
                    timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                    await member_to_timeout.timeout(timeout_until, reason=f"Autom. Moderation: {gpt_analysis_result}")
                    timeout_info = f"{duration_seconds}s (until {timeout_until.strftime('%Y-%m-%d %H:%M:%S UTC')})"
                    mod_logger.info(f"User {member_to_timeout} timed out: {timeout_info}. Reason: {gpt_analysis_result}.")
                    performed_actions_summary.append(f"User timed out ({timeout_info})")
                    try:
                        dm_message_timeout = f"You have been muted on the server '{message.guild.name}' for {duration_seconds} seconds (until {timeout_until.strftime('%Y-%m-%d %H:%M:%S UTC')}). Reason: Your message was classified as '{gpt_analysis_result}'."
                        await member_to_timeout.send(dm_message_timeout)
                    except Exception as e_dm:
                        mod_logger.warning(f"Could not send info DM about timeout to {member_to_timeout}: {e_dm}")
                        performed_actions_summary.append("Failed to send timeout info DM")
                except discord.Forbidden:
                    mod_logger.warning(f"Could not time out {message.author} (Forbidden). Reason: {gpt_analysis_result}")
                    performed_actions_summary.append("Timeout failed (Forbidden)")
                except Exception as e:
                    mod_logger.error(f"Error timing out {message.author}: {e}. Reason: {gpt_analysis_result}")
                    performed_actions_summary.append(f"Timeout failed (Exception: {e})")
            else:
                mod_logger.warning(f"Unknown timeout duration '{duration_key}' oder ungültiger User. Timeout skipped.")
                performed_actions_summary.append(f"Timeout skipped (unknown duration: {duration_key})")
        elif action == "timeout_user":
            # Standard-Timeout (z.B. für Custom-Flags ohne Zeitangabe)
            duration_seconds = TIMEOUT_DURATIONS_CONFIG.get("short", 60)
            if message.guild and isinstance(message.author, discord.Member):
                try:
                    member_to_timeout = message.author
                    timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
                    await member_to_timeout.timeout(timeout_until, reason=f"Autom. Moderation: {gpt_analysis_result}")
                    timeout_info = f"{duration_seconds}s (until {timeout_until.strftime('%Y-%m-%d %H:%M:%S UTC')})"
                    mod_logger.info(f"User {member_to_timeout} timed out: {timeout_info}. Reason: {gpt_analysis_result}.")
                    performed_actions_summary.append(f"User timed out ({timeout_info})")
                    try:
                        dm_message_timeout = f"You have been muted on the server '{message.guild.name}' for {duration_seconds} seconds (until {timeout_until.strftime('%Y-%m-%d %H:%M:%S UTC')}). Reason: Your message was classified as '{gpt_analysis_result}'."
                        await member_to_timeout.send(dm_message_timeout)
                    except Exception as e_dm:
                        mod_logger.warning(f"Could not send info DM about timeout to {member_to_timeout}: {e_dm}")
                        performed_actions_summary.append("Failed to send timeout info DM")
                except discord.Forbidden:
                    mod_logger.warning(f"Could not time out {message.author} (Forbidden). Reason: {gpt_analysis_result}")
                    performed_actions_summary.append("Timeout failed (Forbidden)")
                except Exception as e:
                    mod_logger.error(f"Error timing out {message.author}: {e}. Reason: {gpt_analysis_result}")
                    performed_actions_summary.append(f"Timeout failed (Exception: {e})")
            else:
                mod_logger.warning(f"timeout_user: Kein gültiger Member oder keine Guild. Timeout skipped.")
                performed_actions_summary.append("Timeout skipped (invalid member/guild)")
        elif action == "log_action":
            # Logge die Moderationsaktion IMMER als Embed in den Log-Channel
            if LOG_CHANNEL_ID:
                embed = discord.Embed(
                    title="Moderation Action (log_action)",
                    color=discord.Color.orange(),
                    timestamp=message.created_at
                )
                embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
                embed.add_field(name="Channel", value=f"{message.channel.mention}" if message.guild else "Direct Message", inline=True)
                embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)
                embed.add_field(name="GPT Classification", value=normalized_gpt_result, inline=True)
                original_message_content = message.content
                if len(original_message_content) > 1020:
                    original_message_content = original_message_content[:1020] + "..."
                embed.add_field(name="Original Message", value=f"```{original_message_content}```" if original_message_content else "_No text content_", inline=False)
                actions_str = ", ".join(performed_actions_summary) if performed_actions_summary else "No explicit actions taken"
                embed.add_field(name="Actions Taken", value=actions_str, inline=False)
                if message.guild:
                    embed.set_footer(text=f"Server: {message.guild.name} ({message.guild.id})")
                try:
                    await log_event_to_discord(client, LOG_CHANNEL_ID, embed)
                    mod_logger.info(f"Moderationsaktion als Embed im Log-Channel dokumentiert (log_action).")
                except Exception as e:
                    mod_logger.error(f"Fehler beim Loggen der Moderationsaktion im Log-Channel: {e}")
            performed_actions_summary.append("log_action (embed logged)")
        elif action == "delete_all_messages_in_channel":
            # Lösche alle Nachrichten im Channel (Standard-Limit 100)
            if hasattr(message.channel, 'history'):
                result = await moderation_actions.delete_all_messages_in_channel(message.channel, limit=100)
                performed_actions_summary.append(result)
                mod_logger.info(result)
            else:
                msg = f"delete_all_messages_in_channel: Channel {getattr(message.channel, 'name', str(message.channel))} unterstützt keine history()."
                performed_actions_summary.append(msg)
                mod_logger.warning(msg)
        elif action == "send_dm_warning":
            try:
                user_to_warn = message.author
                gpt_flag_en = normalized_gpt_result
                result = await moderation_actions.send_dm_warning(user_to_warn, message, gpt_flag_en, DEFAULT_WARN_LANGUAGE)
                performed_actions_summary.append(result)
            except Exception as e:
                mod_logger.error(f"Error sending DM warning to {message.author}: {e}.")
                performed_actions_summary.append(f"Failed to send DM warning (Exception: {e})")
        else:
            mod_logger.warning(f"Unbekannte Moderationsaktion: {action}")
            performed_actions_summary.append(f"Unknown action: {action}")

    final_log_message_console = (
        f"Moderation event: User: {message.author} ({message.author.id}), "
        f"Guild: {message.guild.id if message.guild else 'DM'}, "
        f"GPT: {gpt_analysis_result}, "
        f"Actions: {', '.join(performed_actions_summary) if performed_actions_summary else 'No actions performed/logged'}, "
        f"Message: '{message.content[:100]}...'"
    )
    mod_logger.info(final_log_message_console)

    # Discord channel log via Embed (now for [INSULT] and [SPAM])
    if LOG_CHANNEL_ID and normalized_gpt_result in ("[INSULT]", "[SPAM]"):
        # gpt_flag_en_for_embed is directly normalized_gpt_result
        gpt_flag_en_for_embed = normalized_gpt_result
        embed = discord.Embed(
            title="Automatic Moderation Action",
            color=discord.Color.red() if normalized_gpt_result in ("[INSULT]", "[SPAM]") or timeout_info else discord.Color.orange(),
            timestamp=message.created_at
        )
        embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name="Channel", value=f"{message.channel.mention}" if message.guild else "Direct Message", inline=True)
        embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)
        embed.add_field(name="GPT Classification", value=gpt_flag_en_for_embed, inline=True)
        
        original_message_content = message.content
        if len(original_message_content) > 1020:
            original_message_content = original_message_content[:1020] + "..."
        embed.add_field(name="Original Message", value=f"```{original_message_content}```" if original_message_content else "_No text content_", inline=False)

        actions_str = ", ".join(performed_actions_summary) if performed_actions_summary else "No explicit actions taken"
        embed.add_field(name="Actions Taken", value=actions_str, inline=False)

        if message.guild:
            embed.set_footer(text=f"Server: {message.guild.name} ({message.guild.id})")

        await log_event_to_discord(client, LOG_CHANNEL_ID, embed) 