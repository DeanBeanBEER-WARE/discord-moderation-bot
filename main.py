# Entry point for the Discord bot
import asyncio
from core.bot import start_bot

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("Bot is shutting down...")
    except Exception as e:
        print(f"An error occurred: {e}") 