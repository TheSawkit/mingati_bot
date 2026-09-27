import asyncio
import logging
import signal
import sys

import discord
from pydantic import ValidationError

from mingati.bot import MingatiBot
from mingati.config import Settings, describe_config_error
from mingati.database import Database
from mingati.utils.logging import LastErrorHandler, setup_logging

log = logging.getLogger("mingati")


async def run(settings: Settings, last_error: LastErrorHandler) -> None:
    """Open the database, run the bot until it stops or receives SIGTERM/SIGINT, then clean up."""
    database = Database(settings.database_path)
    await database.connect()
    try:
        async with MingatiBot(settings, database, last_error) as bot:
            loop = asyncio.get_running_loop()
            for signum in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(signum, lambda: asyncio.create_task(bot.close()))
            await bot.start(settings.discord_token.get_secret_value())
    finally:
        await database.close()
        log.info("Shutdown complete")


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as error:
        setup_logging("INFO")
        log.critical(
            "Invalid configuration, check your .env file:\n%s", describe_config_error(error)
        )
        sys.exit(1)
    last_error = setup_logging(settings.log_level)
    try:
        asyncio.run(run(settings, last_error))
    except discord.LoginFailure:
        log.critical("Discord rejected DISCORD_TOKEN, generate a new one in the Developer Portal")
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        log.critical("A privileged intent is enabled in code but not in the Developer Portal")
        sys.exit(1)


if __name__ == "__main__":
    main()
