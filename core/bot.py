"""Main logic of the Discord bot, event handling."""
import discord
import datetime
import re
from utils import config_loader
from utils.logger import get_logger, log_event_to_discord
from .gpt_integration import analyze_text_with_gpt
from .moderation import handle_moderation_action
from . import prompts
from utils.config_loader import CUSTOM_RULES_PROMPT_CONFIG, MAX_LENIENCY_LEVEL
import asyncio

bot_logger = get_logger(__name__)
LOG_CHANNEL_ID = config_loader.get_config("log_channel_id")
LENIENCY_CONFIG = config_loader.get_config("membership_moderation_leniency", {})
LENIENCY_ENABLED = LENIENCY_CONFIG.get("enabled", False)
DEFAULT_LENIENCY_LEVEL = LENIENCY_CONFIG.get("default_leniency_level", 0)
MAX_LENIENCY_AT_DAYS = LENIENCY_CONFIG.get("max_leniency_at_days", 365)
CONTEXT_MESSAGE_COUNT = config_loader.get_config("context_message_count", 5)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)

_user_custom_rule_text_loaded = ""
_exclusive_response_categories_loaded = "[OK]"
_base_response_categories_loaded = "[OK], [WARNING], [SPAM], [INSULT], [LINK], [EXCESSIVE CAPS]"

if CUSTOM_RULES_PROMPT_CONFIG.get("enabled") and CUSTOM_RULES_PROMPT_CONFIG.get("prompt"):
    _raw_prompt_config = CUSTOM_RULES_PROMPT_CONFIG["prompt"]
    if isinstance(_raw_prompt_config, list):
        _user_custom_rule_text_loaded = "\n".join(_raw_prompt_config).strip()
        bot_logger.debug(f"Loaded custom rules from list. Combined text length: {len(_user_custom_rule_text_loaded)}")
    elif isinstance(_raw_prompt_config, str):
        _user_custom_rule_text_loaded = _raw_prompt_config.strip()
        bot_logger.debug(f"Loaded custom rules from string. Text length: {len(_user_custom_rule_text_loaded)}")
    else:
        _user_custom_rule_text_loaded = "" 
        bot_logger.warning("Custom rules prompt in config.json is not a string or a list of strings. No custom rules will be applied.")

    if _user_custom_rule_text_loaded: # Nur wenn Regeln geladen wurden
        if CUSTOM_RULES_PROMPT_CONFIG.get("exclusive", False):
            found_flags = re.findall(r"(\[[A-Z\s]+\])", _user_custom_rule_text_loaded)
            if found_flags:
                _exclusive_response_categories_loaded = ", ".join(sorted(list(set(found_flags))))
            # _exclusive_response_categories_loaded hat bereits einen Defaultwert [OK]
            bot_logger.debug(f"Exclusive mode ready: Extracted flags for custom prompt: '{_exclusive_response_categories_loaded}'")
        # _base_response_categories_loaded ist bereits oben definiert und bleibt für non-exclusive
    else:
        bot_logger.info("Custom rules enabled but no rule text was loaded.")
else:
    bot_logger.info("Custom rules not enabled or no prompt configured.")

@client.event
async def on_ready():
    """Called when the bot is successfully connected to Discord."""
    bot_logger.info(f'{client.user} has successfully connected to Discord!')
    bot_logger.info(f"Using GPT Moderation System Prompt Template: {prompts.MODERATION_GENERAL_SYSTEM_PROMPT}")
    bot_logger.info(f"Membership Leniency Enabled: {LENIENCY_ENABLED}, Default Level: {DEFAULT_LENIENCY_LEVEL}, Max Leniency at Days: {MAX_LENIENCY_AT_DAYS}")
    bot_logger.info(f'User ID: {client.user.id}')
    bot_logger.info('------')

@client.event
async def on_message(message: discord.Message):
    """Called when a message is sent on the server."""
    if message.author == client.user:
        return

    if not message.guild:
        bot_logger.info(f"Ignored direct message from {message.author} ({message.author.id}): '{message.content[:50]}...'")
        return

    if message.mention_everyone and isinstance(message.author, discord.Member) and not message.author.guild_permissions.administrator:
        action_summary = []
        try:
            await message.delete()
            bot_logger.info(f"@everyone mention by {message.author} ({message.author.id}) in message {message.id} deleted.")
            action_summary.append("Message deleted")
            dm_text = (
                f"Hello {message.author.mention}, your message in channel #{message.channel} "
                f"(Server: {message.guild.name}) was deleted because it contained an @everyone mention. "
                f"This type of mention is only allowed for specific roles. Please observe our server rules."
            )
            await message.author.send(dm_text)
            bot_logger.info(f"DM warning regarding @everyone sent to {message.author}.")
            action_summary.append("DM warning sent to user")

            if LOG_CHANNEL_ID:
                embed = discord.Embed(
                    title="Rule-based Moderation Action (@everyone)",
                    color=discord.Color.blue(),
                    timestamp=message.created_at
                )
                embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
                embed.add_field(name="Channel", value=f"{message.channel.mention}", inline=True)
                embed.add_field(name="Rule Violation", value="@everyone mention by non-admin", inline=False)
                original_message_content = message.content
                if len(original_message_content) > 1020:
                    original_message_content = original_message_content[:1020] + "..."
                embed.add_field(name="Original Message (now deleted)", value=f"```{original_message_content}```" if original_message_content else "_No text content_", inline=False)
                embed.add_field(name="Actions Taken", value=", ".join(action_summary), inline=False)
                if message.guild:
                    embed.set_footer(text=f"Server: {message.guild.name} ({message.guild.id})")
                await log_event_to_discord(client, LOG_CHANNEL_ID, embed)

            mod_event_logger = get_logger("core.bot.everyone_handler")
            mod_event_logger.info(
                f"@everyone moderation event: User: {message.author} ({message.author.id}), Guild: {message.guild.id}, "
                f"Action: everyone_mention_deleted_and_warned, Message: '{message.content[:100]}...'"
            )

        except discord.Forbidden:
            bot_logger.warning(f"Could not delete @everyone message {message.id} or send DM: Missing permissions.")
        except Exception as e:
            bot_logger.error(f"Error handling @everyone mention: {e}")
        return

    guild_name = message.guild.name

    bot_logger.info(
        f"Message from {message.author} ({message.author.id}) in #{message.channel} (Server: {guild_name}): "
        f'{message.content}'
    )

    if message.content:
        current_leniency_level = DEFAULT_LENIENCY_LEVEL
        if LENIENCY_ENABLED and isinstance(message.author, discord.Member) and message.author.joined_at and MAX_LENIENCY_AT_DAYS > 0:
            join_date = message.author.joined_at
            now = datetime.datetime.now(datetime.timezone.utc)
            membership_duration_days = (now - join_date).days
            
            if membership_duration_days >= MAX_LENIENCY_AT_DAYS:
                current_leniency_level = MAX_LENIENCY_LEVEL
            elif membership_duration_days > 0:
                current_leniency_level = min(MAX_LENIENCY_LEVEL, int((membership_duration_days / MAX_LENIENCY_AT_DAYS) * MAX_LENIENCY_LEVEL))
            else:
                current_leniency_level = 0
            bot_logger.info(f"User {message.author} ({message.author.id}) membership: {membership_duration_days} days. Calculated leniency: {current_leniency_level}")
        elif LENIENCY_ENABLED:
            bot_logger.warning(f"Leniency enabled, but could not determine membership duration for {message.author}. Using default_leniency_level: {DEFAULT_LENIENCY_LEVEL}")
            current_leniency_level = DEFAULT_LENIENCY_LEVEL
        else:
            bot_logger.info(f"Leniency disabled. Using default_leniency_level: {DEFAULT_LENIENCY_LEVEL}")
            current_leniency_level = DEFAULT_LENIENCY_LEVEL

        analysis_result = None
        system_prompt_to_use = None

        # NEU: Kontext der letzten X Nachrichten sammeln (dynamisch)
        recent_messages_context = ""
        if hasattr(message.channel, 'history'):
            try:
                messages = []
                async for msg in message.channel.history(limit=CONTEXT_MESSAGE_COUNT, oldest_first=True):
                    # Format: [username]: message
                    messages.append(f"[{msg.author.display_name}]: {msg.content}")
                recent_messages_context = "\n".join(messages)
            except Exception as e:
                bot_logger.warning(f"Could not fetch recent messages for context: {e}")
                recent_messages_context = "(context unavailable)"
        else:
            recent_messages_context = "(context unavailable)"

        if CUSTOM_RULES_PROMPT_CONFIG.get("enabled") and _user_custom_rule_text_loaded:
            is_exclusive = CUSTOM_RULES_PROMPT_CONFIG.get("exclusive", False)
            casual_language_friendly = CUSTOM_RULES_PROMPT_CONFIG.get("casual_language_friendly", False)
            channel_name_for_prompt = message.channel.name if hasattr(message.channel, 'name') else str(message.channel)
            current_template_string = None
            format_args = {}

            # Dynamischer Zusatz für Umgangssprache
            casual_language_block = ""
            if casual_language_friendly:
                casual_language_block = (
                    "When evaluating if a message is an insult or offensive, you MUST distinguish between genuinely offensive, personal attacks and friendly, colloquial, or playful language (banter, jokes, or teasing) that is common in some communities. "
                    "If the recent message context suggests a friendly or humorous tone, do NOT flag such language as an insult. "
                    "Always consider the recent message context to help you decide if the language is meant as a joke or as a real attack. "
                    "If you are unsure, prefer [OK] over [INSULT].\n"
                )

            if is_exclusive:
                # Prompt dynamisch zusammensetzen
                base_template = prompts.EXCLUSIVE_CUSTOM_RULES_TEMPLATE
                # Entferne ggf. alten Block, falls vorhanden (für Robustheit)
                base_template = base_template.replace(
                    "When evaluating if a message is an insult or offensive, you MUST distinguish between genuinely offensive, personal attacks and friendly, colloquial, or playful language (banter, jokes, or teasing) that is common in some communities. If the recent message context suggests a friendly or humorous tone, do NOT flag such language as an insult. Always consider the recent message context to help you decide if the language is meant as a joke or as a real attack. If you are unsure, prefer [OK] over [INSULT].\n",
                    ""
                )
                # Füge Block ggf. ein
                base_template = base_template.replace(
                    "---\n",
                    f"---\n{casual_language_block}"
                )
                current_template_string = base_template
                format_args = {
                    "user_custom_rule_text": _user_custom_rule_text_loaded,
                    "channel_name_placeholder": channel_name_for_prompt,
                    "leniency_level": current_leniency_level,
                    "exclusive_response_categories": _exclusive_response_categories_loaded,
                    "recent_messages_context": recent_messages_context,
                    "context_message_count": CONTEXT_MESSAGE_COUNT
                }
            else:
                current_template_string = prompts.NON_EXCLUSIVE_CUSTOM_RULES_TEMPLATE
                format_args = {
                    "user_custom_rule_text": _user_custom_rule_text_loaded,
                    "channel_name_placeholder": channel_name_for_prompt,
                    "leniency_level": current_leniency_level,
                    "base_response_categories": _base_response_categories_loaded
                }
            
            if current_template_string:
                custom_system_prompt = current_template_string.format(**format_args)
                system_prompt_to_use = custom_system_prompt
                
                bot_logger.info(f"--- GPT PROMPT FOR CUSTOM RULE CHECK ({message.id}) ---")
                bot_logger.info(custom_system_prompt)
                bot_logger.info(f"--- END GPT PROMPT --- ")

                analysis_result = await analyze_text_with_gpt(message.content, custom_system_prompt, current_leniency_level)
                bot_logger.info(f"Custom rules GPT analysis (exclusive={is_exclusive}): {analysis_result}")

                if not is_exclusive and (not analysis_result or analysis_result.strip().upper() == "[OK]"):
                    bot_logger.info(f"Custom rules (non-exclusive) returned [OK]/None. Falling back to general moderation prompt.")
                    general_system_prompt = prompts.MODERATION_GENERAL_SYSTEM_PROMPT.format(leniency_level=current_leniency_level) # MODERATION_GENERAL_SYSTEM_PROMPT aus prompts verwenden
                    system_prompt_to_use = general_system_prompt
                    analysis_result = await analyze_text_with_gpt(message.content, general_system_prompt, current_leniency_level)
                    bot_logger.info(f"General moderation GPT analysis after custom rules: {analysis_result}")
            else:
                 bot_logger.warning("Custom rules enabled but no specific prompt template (exclusive/non-exclusive) was identified. Using general moderation prompt.")
                 general_system_prompt = prompts.MODERATION_GENERAL_SYSTEM_PROMPT.format(leniency_level=current_leniency_level)
                 system_prompt_to_use = general_system_prompt
                 analysis_result = await analyze_text_with_gpt(message.content, general_system_prompt, current_leniency_level)
        else: # Custom rules nicht aktiviert oder keine Regeln geladen
            if CUSTOM_RULES_PROMPT_CONFIG.get("enabled"):
                 bot_logger.info(f"Custom rules enabled, but no rule text was loaded. Using general moderation prompt.")
            else:
                bot_logger.info(f"Custom rules not enabled. Using general moderation prompt.")
            general_system_prompt = prompts.MODERATION_GENERAL_SYSTEM_PROMPT.format(leniency_level=current_leniency_level)
            system_prompt_to_use = general_system_prompt
            analysis_result = await analyze_text_with_gpt(message.content, general_system_prompt, current_leniency_level)
        
        if system_prompt_to_use and not CUSTOM_RULES_PROMPT_CONFIG.get("enabled"): # Nur den allgemeinen Prompt loggen, wenn Custom Rules aus sind
             bot_logger.debug(f"Final system prompt used (general): {system_prompt_to_use[:500]}...")

        if analysis_result:
            bot_logger.info(f"GPT analysis for message '{message.id}' from '{message.author}' (Leniency: {current_leniency_level}): {analysis_result}")
            await handle_moderation_action(client, message, analysis_result, leniency_level=current_leniency_level)
        else:
            bot_logger.warning(f"No analysis received from GPT for message '{message.id}' from '{message.author}' (Leniency: {current_leniency_level}). Content: '{message.content[:100]}...'")
            if LOG_CHANNEL_ID:
                embed = discord.Embed(
                    title="GPT Analysis Failed / No Result",
                    description="Could not get a moderation analysis from GPT for a message, or the result was empty.",
                    color=discord.Color.dark_orange(),
                    timestamp=message.created_at
                )
                embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
                embed.add_field(name="Channel", value=f"{message.channel.mention}", inline=True)
                embed.add_field(name="Message ID", value=f"`{message.id}`", inline=False)
                embed.add_field(name="Applied Leniency Level", value=str(current_leniency_level), inline=False)
                original_message_content = message.content
                if len(original_message_content) > 1020:
                    original_message_content = original_message_content[:1020] + "..."
                embed.add_field(name="Original Message Content", value=f"```{original_message_content}```" if original_message_content else "_No text content_", inline=False)
                if message.guild:
                    embed.set_footer(text=f"Server: {message.guild.name} ({message.guild.id})")
                try:
                    await log_event_to_discord(client, LOG_CHANNEL_ID, embed)
                    bot_logger.info(f"Logged GPT analysis failure/empty result to Discord for message {message.id}.")
                except Exception as e_log:
                    bot_logger.error(f"Failed to log GPT analysis failure/empty result to Discord: {e_log}")

@client.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """Called when a message is edited."""
    if after.author == client.user:
        return

    if before.content == after.content:
        return

    if not after.guild:
        bot_logger.info(f"Ignored edited direct message from {after.author} ({after.author.id}): '{after.content[:50]}...'")
        return

    bot_logger.info(
        f"Message edited by {after.author} ({after.author.id}) in #{after.channel} (Server: {after.guild.name}).\n"
        f"  Before: '{before.content[:100]}...'\n"
        f"  After: '{after.content[:100]}...'"
    )

    if after.mention_everyone and isinstance(after.author, discord.Member) and not after.author.guild_permissions.administrator:
        action_summary_edit = []
        try:
            await after.delete()
            bot_logger.info(f"@everyone mention in edited message {after.id} by {after.author} deleted.")
            action_summary_edit.append("Edited message deleted due to @everyone")
            
            dm_text = (
                f"Hello {after.author.mention}, your edited message in channel #{after.channel} "
                f"(Server: {after.guild.name}) was deleted because it contained an @everyone mention. "
                f"This type of mention is only allowed for specific roles."
            )
            await after.author.send(dm_text)
            bot_logger.info(f"DM warning regarding edited @everyone sent to {after.author}.")
            action_summary_edit.append("DM warning sent to user")

            if LOG_CHANNEL_ID:
                embed = discord.Embed(
                    title="Rule-based Moderation Action (Edited @everyone)",
                    color=discord.Color.blue(),
                    timestamp=after.edited_at if after.edited_at else discord.utils.utcnow()
                )
                embed.add_field(name="User", value=f"{after.author.mention} (`{after.author.id}`)", inline=True)
                embed.add_field(name="Channel", value=f"{after.channel.mention}", inline=True)
                embed.add_field(name="Rule Violation", value="@everyone mention in edited message", inline=False)
                embed.add_field(name="Original Content (before edit)", value=f"```{before.content[:1000]}...```" if before.content else "_No text content_", inline=False)
                embed.add_field(name="New Content (edited, now deleted)", value=f"```{after.content[:1000]}...```" if after.content else "_No text content_", inline=False)
                embed.add_field(name="Actions Taken", value=", ".join(action_summary_edit), inline=False)
                if after.guild:
                    embed.set_footer(text=f"Server: {after.guild.name} ({after.guild.id})")
                await log_event_to_discord(client, LOG_CHANNEL_ID, embed)
            
        except discord.Forbidden:
            bot_logger.warning(f"Could not delete edited @everyone message {after.id} or send DM: Missing permissions.")
        except Exception as e:
            bot_logger.error(f"Error handling edited @everyone mention: {e}")
        return

    if after.content:
        current_leniency_level_edit = DEFAULT_LENIENCY_LEVEL
        if LENIENCY_ENABLED and isinstance(after.author, discord.Member) and after.author.joined_at and MAX_LENIENCY_AT_DAYS > 0:
            join_date_edit = after.author.joined_at
            now_edit = datetime.datetime.now(datetime.timezone.utc)
            membership_duration_days_edit = (now_edit - join_date_edit).days

            if membership_duration_days_edit >= MAX_LENIENCY_AT_DAYS:
                current_leniency_level_edit = MAX_LENIENCY_LEVEL
            elif membership_duration_days_edit > 0:
                current_leniency_level_edit = min(MAX_LENIENCY_LEVEL, int((membership_duration_days_edit / MAX_LENIENCY_AT_DAYS) * MAX_LENIENCY_LEVEL))
            else:
                current_leniency_level_edit = 0 
            bot_logger.info(f"User {after.author} ({after.author.id}) membership (for edit): {membership_duration_days_edit} days. Calculated leniency: {current_leniency_level_edit}")
        elif LENIENCY_ENABLED:
            bot_logger.warning(f"Leniency enabled, but could not determine membership duration for {after.author} (edit). Using default_leniency_level: {DEFAULT_LENIENCY_LEVEL}")
            current_leniency_level_edit = DEFAULT_LENIENCY_LEVEL
        else:
            bot_logger.info(f"Leniency disabled (for edit). Using default_leniency_level: {DEFAULT_LENIENCY_LEVEL}")
            current_leniency_level_edit = DEFAULT_LENIENCY_LEVEL

        analysis_result_edit = await analyze_text_with_gpt(after.content, prompts.MODERATION_GENERAL_SYSTEM_PROMPT, current_leniency_level_edit)
        if analysis_result_edit:
            bot_logger.info(f"GPT analysis for edited message '{after.id}' from '{after.author}' (Leniency: {current_leniency_level_edit}): {analysis_result_edit}")
            actions_taken_summary_edit = await handle_moderation_action(client, after, analysis_result_edit, leniency_level=current_leniency_level_edit)

            if LOG_CHANNEL_ID and analysis_result_edit.strip().upper() in ("[INSULT]", "[SPAM]"):
                embed_edit_log = discord.Embed(
                    title="Moderation Action on Edited Message",
                    color=discord.Color.purple(),
                    timestamp=after.edited_at if after.edited_at else discord.utils.utcnow()
                )
                embed_edit_log.add_field(name="User", value=f"{after.author.mention} (`{after.author.id}`)", inline=True)
                embed_edit_log.add_field(name="Channel", value=f"{after.channel.mention}", inline=True)
                embed_edit_log.add_field(name="Message ID", value=f"`{after.id}`", inline=True)
                embed_edit_log.add_field(name="Applied Leniency Level", value=str(current_leniency_level_edit), inline=False)
                embed_edit_log.add_field(name="GPT Classification (Edit)", value=analysis_result_edit, inline=False)
                
                before_content_display = before.content
                if len(before_content_display) > 450:
                    before_content_display = before_content_display[:450] + "..."
                embed_edit_log.add_field(name="Original Content (Before Edit)", value=f"```{before_content_display}```" if before_content_display else "_No text content_", inline=False)
                
                after_content_display = after.content
                if len(after_content_display) > 450:
                    after_content_display = after_content_display[:450] + "..."
                embed_edit_log.add_field(name="Edited Content (Analyzed)", value=f"```{after_content_display}```" if after_content_display else "_No text content_", inline=False)

                actions_display = f"Actions based on classification: {analysis_result_edit}"
                if isinstance(actions_taken_summary_edit, list) and actions_taken_summary_edit:
                    actions_display = ", ".join(actions_taken_summary_edit)
                elif isinstance(actions_taken_summary_edit, str):
                    actions_display = actions_taken_summary_edit

                embed_edit_log.add_field(name="Actions Taken", value=actions_display, inline=False)

                if after.guild:
                    embed_edit_log.set_footer(text=f"Server: {after.guild.name} ({after.guild.id})")
                
                try:
                    await log_event_to_discord(client, LOG_CHANNEL_ID, embed_edit_log)
                except Exception as e_log_edit:
                    bot_logger.error(f"Failed to log edited message moderation to Discord: {e_log_edit}")
        else:
            bot_logger.warning(f"No GPT analysis received for edited message '{after.id}' from '{after.author}' (Leniency: {current_leniency_level_edit}).")
            if LOG_CHANNEL_ID:
                embed_edit_fail_log = discord.Embed(
                    title="GPT Analysis Failed / No Result (Edited Message)",
                    description="Could not get a moderation analysis from GPT for an edited message, or the result was empty.",
                    color=discord.Color.dark_grey(),
                    timestamp=after.edited_at if after.edited_at else discord.utils.utcnow()
                )
                embed_edit_fail_log.add_field(name="User", value=f"{after.author.mention} (`{after.author.id}`)", inline=True)
                embed_edit_fail_log.add_field(name="Channel", value=f"{after.channel.mention}", inline=True)
                embed_edit_fail_log.add_field(name="Message ID", value=f"`{after.id}`", inline=False)
                embed_edit_fail_log.add_field(name="Applied Leniency Level", value=str(current_leniency_level_edit), inline=False)
                embed_edit_fail_log.add_field(name="Original Content (Before Edit)", value=f"```{before.content[:1000]}...```" if before.content else "_No text content_", inline=False)
                embed_edit_fail_log.add_field(name="Edited Content", value=f"```{after.content[:1000]}...```" if after.content else "_No text content_", inline=False)
                if after.guild:
                    embed_edit_fail_log.set_footer(text=f"Server: {after.guild.name} ({after.guild.id})")
                try:
                    await log_event_to_discord(client, LOG_CHANNEL_ID, embed_edit_fail_log)
                except Exception as e_log_edit_fail:
                    bot_logger.error(f"Failed to log GPT analysis failure for edited message to Discord: {e_log_edit_fail}")

@client.event
async def on_message_delete(message: discord.Message):
    """Called when a message is deleted."""
    if message.author == client.user:
        return

    if not message.guild:
        bot_logger.debug(f"Deleted direct message from {message.author} ({message.author.id}) not logged further: '{message.content[:50]}...'")
        return

    if LOG_CHANNEL_ID and message.channel.id == LOG_CHANNEL_ID:
        bot_logger.debug(f"Message deleted in log channel {LOG_CHANNEL_ID} by {message.author}. Not creating a Discord log entry.")
        return

    bot_logger.info(
        f"Message {message.id} deleted by {message.author} ({message.author.id}) in #{message.channel} (Server: {message.guild.name}). "
        f"Content: '{message.content[:100]}...'"
    )

def start_bot():
    """Initializes and starts the Discord bot."""
    if config_loader.DISCORD_BOT_TOKEN:
        bot_logger.info("Attempting to start the bot...")
        try:
            client.run(config_loader.DISCORD_BOT_TOKEN)
        except discord.PrivilegedIntentsRequired:
            bot_logger.error(
                "Privileged Intents (Server Members or Message Content) are not enabled for the bot. "
                "Please enable them in the Discord Developer Portal: "
                "https://discord.com/developers/applications/<YOUR_BOT_ID>/bot"
            )
        except discord.LoginFailure:
            bot_logger.error(
                "Failed to log in to Discord. Please check if the DISCORD_BOT_TOKEN is correct."
            )
        except Exception as e:
            bot_logger.critical(f"An critical error occurred while trying to run the bot: {e}", exc_info=True)
    else:
        bot_logger.error("DISCORD_BOT_TOKEN is not set. Bot cannot start.")