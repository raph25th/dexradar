import logging

from telegram import Bot
from telegram.error import TelegramError

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_telegram_message(text: str) -> bool:
    settings = get_settings()
    if not settings.telegram_enabled:
        logger.warning("Telegram credentials are not configured; skipping message")
        return False

    try:
        bot = Bot(token=settings.telegram_bot_token or "")
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text,
            disable_web_page_preview=False,
        )
        return True
    except TelegramError:
        logger.exception("Telegram API returned an error")
    except Exception:
        logger.exception("Unexpected Telegram send error")
    return False
