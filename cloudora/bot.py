import logging
import random
from typing import Optional
from telegram import Bot
from telegram.error import TimedOut, NetworkError
from . import settings

logger = logging.getLogger(__name__)


class BotCluster:
    """Manages multiple Telegram bots for load-balanced file uploads."""

    def __init__(self):
        self.bots: list[Bot] = []
        self._healthy: set[int] = set()

    async def start_all(self):
        tokens = settings.bot_token_list
        if not tokens:
            logger.warning("No bot tokens configured. Add BOT_TOKENS or tokens.txt")
            return
        for i, token in enumerate(tokens):
            try:
                bot = Bot(token=token)
                me = await bot.get_me()
                self.bots.append(bot)
                self._healthy.add(i)
                logger.info(f"Bot {i}: @{me.username} connected")
            except Exception as e:
                logger.error(f"Bot {i}: Failed - {e}")

        if self.bots:
            logger.info(f"Cluster ready: {len(self.bots)} bots, "
                        f"{len(self._healthy)} healthy")

    async def get_healthy_bot(self) -> Optional[Bot]:
        if not self._healthy:
            return None
        idx = random.choice(list(self._healthy))
        return self.bots[idx]

    async def mark_unhealthy(self, bot: Bot):
        for i, b in enumerate(self.bots):
            if b == bot:
                self._healthy.discard(i)
                break

    async def delete_messages(self, channel_id: int, message_id: int):
        for bot in self.bots:
            try:
                await bot.delete_message(chat_id=channel_id, message_id=message_id)
                return
            except Exception:
                continue


cluster = BotCluster()
