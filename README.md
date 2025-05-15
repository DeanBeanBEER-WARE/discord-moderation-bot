# Discord Moderation Bot – Codebase Documentation

## Overview

This project implements an advanced Discord moderation bot that leverages the OpenAI GPT API for intelligent, context-aware message analysis and moderation. The bot is highly configurable, supports multilingual warnings, and allows for both general and channel-specific moderation rules. It is designed for extensibility, transparency, and robust error handling.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Configuration](#configuration)
3. [Core Components](#core-components)
    - [Bot Logic (`core/bot.py`)](#bot-logic-corebotpy)
    - [Moderation Actions (`core/moderation.py` & `core/moderation_actions.py`)](#moderation-actions-coremoderationpy--coremoderation_actionspy)
    - [GPT Integration (`core/gpt_integration.py`)](#gpt-integration-coregpt_integrationpy)
    - [Prompt Management (`core/prompts.py`)](#prompt-management-corepromptspy)
4. [Utilities](#utilities)
    - [Configuration Loader (`utils/config_loader.py`)](#configuration-loader-utilsconfig_loaderpy)
    - [Logger (`utils/logger.py`)](#logger-utilsloggerpy)
5. [Entry Point](#entry-point-mainpy)
6. [Extending and Customizing](#extending-and-customizing)
7. [Error Handling and Logging](#error-handling-and-logging)
8. [Best Practices](#best-practices)
9. [Deployment Notes](#deployment-notes)
10. [Deployment with Google Cloud Build & Artifact Registry](#deployment-with-google-cloud-build--artifact-registry)

---

## Project Structure

```
discord-moderation-bot/
│
├── core/
│   ├── bot.py
│   ├── moderation.py
│   ├── moderation_actions.py
│   ├── gpt_integration.py
│   └── prompts.py
│
├── utils/
│   ├── config_loader.py
│   └── logger.py
│
├── config.json
├── .env
├── main.py
├── README.md
└── requirements.txt
```

---

## Configuration

### `.env`
Stores sensitive tokens:
- `DISCORD_BOT_TOKEN`: Discord bot token.
- `OPENAI_API_KEY`: OpenAI API key.

### `config.json`
Holds all runtime configuration, including:
- Bot prefix, log channel ID
- Moderation rules and actions
- GPT model and parameters
- Membership leniency settings
- Custom moderation rules (per channel or global)

---

## Core Components

### Bot Logic (`core/bot.py`)

**Responsibilities:**
- Initializes the Discord client with required intents.
- Handles all Discord events:
  - `on_ready`: Logs bot startup and configuration.
  - `on_message`: Main moderation logic for new messages.
  - `on_message_edit`: Re-analyzes and moderates edited messages.
  - `on_message_delete`: Logs deleted messages.
- Integrates with GPT for message analysis.
- Applies custom and general moderation rules.
- Calculates user leniency based on membership duration.
- Logs all moderation actions to both console and a dedicated Discord channel.

**Key Features:**
- Special handling for `@everyone` mentions by non-admins (immediate deletion and DM warning).
- Custom rules can be exclusive (override all general moderation) or non-exclusive (layered with general rules).
- All moderation actions are transparent and logged.

---

### Moderation Actions (`core/moderation.py` & `core/moderation_actions.py`)

#### `core/moderation.py`
- Central function: `handle_moderation_action`
  - Decides and executes actions based on GPT analysis and configuration.
  - Actions include: message deletion, DM warning, user timeout.
  - Handles multilingual warnings (auto-detects user language and translates warning).
  - Logs all actions to Discord and console.

#### `core/moderation_actions.py`
- Contains atomic moderation action functions:
  - `delete_message`: Deletes a message.
  - `send_dm_warning`: Sends a DM warning, translated if needed.
  - `timeout_user`: Times out a user and notifies them via DM.

---

### GPT Integration (`core/gpt_integration.py`)

- Handles all communication with the OpenAI GPT API.
- Functions:
  - `analyze_text_with_gpt`: Analyzes messages for moderation.
  - `detect_language_with_gpt`: Detects the language of a message.
  - `translate_text_with_gpt`: Translates warning messages.
- Uses configuration for model, temperature, and token limits.
- Robust error handling for API failures and rate limits.

---

### Prompt Management (`core/prompts.py`)

- Centralizes all system prompts for GPT.
- Contains:
  - General moderation prompt (with leniency factor).
  - Language detection prompt.
  - Warning message templates.
  - Translation prompt.
  - Templates for exclusive and non-exclusive custom rules.

---

## Standard Moderation Flags & Actions

### Standard Moderation Flags
These are the built-in flags that the bot can assign to messages (as detected by GPT or rule logic):

- `[INSULT]` – Insulting or offensive content
- `[SPAM]` – Spam or repeated/unwanted content
- `[WARNING]` – Content that triggers a warning (but not deletion)
- `[LINK]` – Suspicious or unwanted link
- `[EXCESSIVE CAPS]` – Excessive use of capital letters
- `[OK]` – Message is acceptable (no action required)

### Available Moderation Actions
These actions can be mapped to flags in the configuration:

- `delete_message` – Deletes the offending message
- `send_dm_warning` – Sends a warning to the user via DM (translated if possible)
- `timeout_user_short` / `timeout_user_medium` / `timeout_user_long` – Temporarily mutes the user for a configurable duration
- `timeout_user` – Temporarily mutes the user for the default short duration
- `log_action` – Logs the moderation event as an embed in the configured log channel
- `delete_all_messages_in_channel` – Deletes all messages in the affected channel (up to a limit, default 100)

> **Note:** Custom flags and actions can be defined in the configuration, but only the above are considered standard and are always available.

### Context Message Count

- The number of context messages sent to GPT for evaluation can be configured via the `context_message_count` variable in `config.json`.

---

## Utilities

### Configuration Loader (`utils/config_loader.py`)

- Loads `.env` and `config.json`.
- Provides `get_config` for nested config access.
- Exposes key configuration values as module-level variables.
- Logs configuration loading status and errors.

### Logger (`utils/logger.py`)

- Sets up Python logging for the entire bot.
- Provides `get_logger` for module-specific loggers.
- `log_event_to_discord`: Sends log messages as embeds to a Discord channel.

---

## Entry Point (`main.py`)

- Starts the bot using `asyncio` and the `start_bot` function from `core/bot.py`.
- Handles shutdown and startup errors gracefully.

---

## Extending and Customizing

- **Custom Rules:**  
  Define in `config.json` under `custom_rules_prompt`.  
  - `enabled`: Toggle custom rules.
  - `exclusive`: If true, only custom rules are used.
  - `prompt`: List or string of rules, with explicit moderation flags (e.g., `[INSULT]`).

- **Moderation Actions:**  
  Map GPT result flags to actions in `moderation_rules.actions_for_result`.

- **Timeouts:**  
  Configure durations in `moderation_rules.timeout_durations`.

- **Leniency System:**  
  Adjust how user membership duration affects moderation strictness in `membership_moderation_leniency`.

---

## Error Handling and Logging

- All critical actions and errors are logged to both the console and a Discord channel (if configured).
- API errors, permission issues, and unexpected exceptions are handled gracefully and logged.
- User-facing errors (e.g., failed DM) are logged but do not interrupt bot operation.

---

## Best Practices

- **Keep your `.env` and `config.json` secure.**
- **Review and test custom rules for exclusivity and coverage.**
- **Monitor the log channel for moderation and error events.**
- **Update dependencies regularly (see `requirements.txt`).**
- **Use the leniency system to balance strictness and community trust.**

---

## Deployment Notes

- Ensure all required environment variables and configuration files are present.
- The bot requires Discord privileged intents (`MESSAGE CONTENT`, `MEMBERS`) to function fully.
- For production, consider running the bot in a managed environment and securing your tokens.

### Quickstart (English)

**How to start the bot correctly:**

1. Create a virtual environment (only needed once):
   ```bash
   python3 -m venv .venv
   ```
2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```
3. Install the dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
4. Start the bot:
   ```bash
   python3 main.py
   ```

**Note:**
- You must activate the virtual environment before every start (`source .venv/bin/activate`).
- If you are on a Mac with Homebrew and PEP 668, using a venv is mandatory!
- The terminal log output will show if the bot has connected successfully.

---

## Deployment with Google Cloud Build & Artifact Registry

This section describes how to build and deploy the Discord Moderation Bot using Google Cloud Build and Artifact Registry, so you can run the bot fully managed on Google Cloud Run.

### Prerequisites
- You have a Google Cloud project (e.g. `discordgpt-459908`).
- You have enabled the Artifact Registry and Cloud Build APIs.
- You have created a Docker repository in Artifact Registry (e.g. `gcr.io` in region `us`).
- Your Google account has sufficient permissions (Owner/Editor or Cloud Build Editor, Artifact Registry Writer, Storage Object Viewer).

### 1. Set the correct project
```bash
gcloud config set project YOUR_PROJECT_ID
# Example:
gcloud config set project discordgpt-459908
```

### 2. Authenticate with your Google account
```bash
gcloud auth login
```

### 3. Grant required IAM roles
- The Cloud Build service account (`[PROJECT_NUMBER]@cloudbuild.gserviceaccount.com`) must have the following roles:
  - Artifact Registry Writer (`roles/artifactregistry.writer`)
  - Storage Object Viewer (`roles/storage.objectViewer`)
  - (Optional) Logs Writer (`roles/logging.logWriter`)
- You can add these roles in the IAM & Admin section of the Google Cloud Console.

### 4. Build and push the Docker image
```bash
gcloud builds submit --tag us-docker.pkg.dev/YOUR_PROJECT_ID/gcr.io/discord-bot:latest
# Example:
gcloud builds submit --tag us-docker.pkg.dev/discordgpt-459908/gcr.io/discord-bot:latest
```

### 5. Deploy to Cloud Run
```bash
gcloud run deploy discord-bot \
  --image us-docker.pkg.dev/YOUR_PROJECT_ID/gcr.io/discord-bot:latest \
  --region us-central1 \
  --min-instances=1 --max-instances=1 --no-cpu-throttling
```

- You can adjust the region and instance settings as needed.
- Make sure to set environment variables (e.g. `DISCORD_BOT_TOKEN`, `OPENAI_API_KEY`) in the Cloud Run service configuration, not in the Docker image.

### 6. Troubleshooting
- If you see permission errors, double-check the IAM roles for the Cloud Build service account and your user account.
- If the build uses the wrong project, set the project again with `gcloud config set project ...`.
- If the Artifact Registry repository is not found, ensure it exists in the correct region and with the correct name.

---

## How to activate (start) the bot on Cloud Run

After deploying, the bot will start automatically on Cloud Run. You can check the status in the Google Cloud Console under Cloud Run. If the bot is not online in Discord:

1. **Check Environment Variables:**
   - Make sure you have set `DISCORD_BOT_TOKEN` and `OPENAI_API_KEY` as environment variables in the Cloud Run service settings.
2. **Check Logs:**
   - Go to Cloud Run → Your Service → Logs. Look for startup errors or authentication issues.
3. **Check Discord Developer Portal:**
   - Ensure the bot token is correct and the bot is invited to your server with the required permissions.
4. **Restart the Service:**
   - You can trigger a redeploy or restart from the Cloud Run console if needed.

If all settings are correct, the bot will come online automatically after deployment.

---

**This documentation provides a complete overview for developers and maintainers to understand, extend, and operate the Discord Moderation Bot.** 