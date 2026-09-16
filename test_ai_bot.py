import inspect
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import httpx
from openai import RateLimitError
from telegram import Message

import ai_service
import bot


class BotReplyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot._request_times.clear()

    def update(self, chat_type="private"):
        async def reply(text, **kwargs):
            # Validate against the installed Telegram API without sending anything.
            inspect.signature(Message.reply_text).bind(None, text, **kwargs)
        message = NS(text="Salom", reply_to_message=None,
                     reply_text=AsyncMock(side_effect=reply))
        update = NS(effective_chat=NS(type=chat_type, id=123, title="Test"),
                    effective_user=NS(id=789, first_name="Test"), message=message)
        context = NS(bot=NS(id=456, username="test_bot", get_me=AsyncMock(return_value=NS(username="test_bot"))))
        return update, context

    async def test_private_chat_replies_without_saving_reminder_group(self):
        update, context = self.update()
        with patch.object(bot, "ask_ai", AsyncMock(return_value="Salom!")) as ask, \
             patch.object(bot, "get_setting", return_value=None), \
             patch.object(bot, "set_setting") as setting:
            await bot.handle_text_message(update, context)
        self.assertEqual(ask.await_args.args, ("Salom",))
        self.assertTrue(ask.await_args.kwargs["direct"])
        self.assertEqual(ask.await_args.kwargs["conversation_key"], (123, 789))
        update.message.reply_text.assert_awaited_once_with("Salom!", do_quote=True)
        setting.assert_not_called()

    async def test_group_reply_uses_supported_telegram_parameter(self):
        update, context = self.update("supergroup")
        update.message.text = "Pi salom"
        with patch.object(bot, "ask_ai", AsyncMock(return_value="Salom!")), \
             patch.object(bot, "get_setting", return_value="123"):
            await bot.handle_text_message(update, context)
        update.message.reply_text.assert_awaited_once()

    async def test_group_ignore_stays_silent(self):
        update, context = self.update("group")
        with patch.object(bot, "ask_ai", AsyncMock(return_value=None)), \
             patch.object(bot, "get_setting", return_value="123"):
            await bot.handle_text_message(update, context)
        update.message.reply_text.assert_not_awaited()

    async def test_ai_success_and_ignore(self):
        for content, expected in [("Salom!", "Salom!"), ("IGNORE", None)]:
            response = NS(choices=[NS(message=NS(content=content))])
            with patch.object(ai_service.client.chat.completions, "create", AsyncMock(return_value=response)):
                self.assertEqual(await ai_service.ask_ai("Salom"), expected)

    async def test_credit_error_is_visible_for_text_and_image(self):
        response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
        error = RateLimitError("Credits exhausted", response=response,
                               body={"code": "credit_balance_exhausted"})
        with patch.object(ai_service.client.chat.completions, "create", AsyncMock(side_effect=error)):
            self.assertIn("krediti", await ai_service.ask_ai("Salom"))
            self.assertIn("krediti", await ai_service.analyze_image_with_ai(b"test"))

    async def test_private_photo_reaches_ai(self):
        update, context = self.update()
        update.message.photo = [NS(file_id="photo")]
        update.message.caption = "Ustoz yozgan kod"
        status = NS(edit_text=AsyncMock())
        update.message.reply_text = AsyncMock(return_value=status)
        context.bot.get_file = AsyncMock(return_value=NS(download_to_memory=AsyncMock()))
        with patch.object(bot, "analyze_image_with_ai", AsyncMock(return_value="Tahlil")) as analyze:
            await bot.handle_photo(update, context)
        analyze.assert_awaited_once()
        status.edit_text.assert_awaited_once_with("Tahlil")


if __name__ == "__main__":
    unittest.main()
