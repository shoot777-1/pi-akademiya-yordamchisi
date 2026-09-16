"""Serialize updates and retain one leaderboard message per chat."""
import asyncio
import logging
from telegram.error import BadRequest, TelegramError
from database import get_setting, set_setting

_locks = {}
logger = logging.getLogger(__name__)


async def update_board(bot, chat_id, text, markup, force_repin=False):
    async with _locks.setdefault(chat_id, asyncio.Lock()):
        key = f"pinned_leaderboard_msg_id_{chat_id}"
        message_id = get_setting(key)
        if not message_id and str(get_setting("main_group_id")) == str(chat_id):
            message_id = get_setting("pinned_leaderboard_msg_id")
        if message_id:
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=int(message_id),
                                            text=text, parse_mode="Markdown", reply_markup=markup)
            except BadRequest as error:
                reason = str(error).lower()
                if "message is not modified" not in reason:
                    if "message to edit not found" in reason:
                        message_id = None
                    else:
                        logger.warning("Reytingni tahrirlash rad etildi: %s", type(error).__name__)
                        return None
            except TelegramError as error:
                logger.warning("Reytingni yangilash vaqtincha ishlamadi: %s", type(error).__name__)
                return None
        created = not message_id
        if created:
            try:
                message = await bot.send_message(chat_id=chat_id, text=text,
                                                 parse_mode="Markdown", reply_markup=markup)
                message_id = message.message_id
            except TelegramError as error:
                logger.warning("Reyting yuborilmadi: %s", type(error).__name__)
                return None
        # Save before pinning; a failed pin must never cause a duplicate send.
        set_setting(key, str(message_id))
        if created or force_repin:
            try:
                await bot.pin_chat_message(chat_id=chat_id, message_id=int(message_id),
                                           disable_notification=True)
            except TelegramError as error:
                logger.warning("Reytingni mahkamlab bo'lmadi: %s", type(error).__name__)
        return int(message_id)
