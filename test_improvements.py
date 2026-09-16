import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import bot
import ai_service
import conversation_service as memory


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = patch.object(memory, "DB_PATH", Path(self.tmp.name) / "test.db")
        self.db.start()

    def tearDown(self):
        self.db.stop()
        self.tmp.cleanup()

    def test_isolation_retention_and_clear(self):
        for i in range(10):
            memory.remember(1, 2, str(i), "answer")
        self.assertEqual(len(memory.get_history(1, 2)), 12)
        self.assertEqual(memory.get_history(1, 2)[0]["content"], "4")
        self.assertEqual(memory.get_history(1, 3), [])
        self.assertEqual(memory.get_history(9, 2), [])
        memory.remember(1, 3, "other", "answer")
        memory.clear_history(1, 2)
        self.assertEqual(memory.get_history(1, 2), [])
        self.assertEqual(len(memory.get_history(1, 3)), 2)

    def test_expiry_and_size_limit(self):
        with patch.object(memory.time, "time", return_value=100):
            memory.remember(1, 2, "x" * 9000, "y" * 9000)
            self.assertEqual(len(memory.get_history(1, 2)[0]["content"]), 2000)
        with patch.object(memory.time, "time", return_value=100 + memory.TTL_SECONDS + 1):
            self.assertEqual(memory.get_history(1, 2), [])


class AccessTests(unittest.IsolatedAsyncioTestCase):
    def update(self, admin=False, chat_type="group"):
        return NS(effective_user=NS(id=bot.ADMIN_ID if admin else -1),
                  effective_chat=NS(id=12, type=chat_type),
                  message=NS(reply_text=AsyncMock()))

    async def test_all_sensitive_handlers_reject_nonadmin_before_side_effects(self):
        for name in ("handle_document", "excel_yangilash_command", "set_group_command",
                     "test_eslatma_command", "tolovlar_command", "set_online_command",
                     "set_offline_command", "set_auto_status_command"):
            update = self.update()
            with patch.object(bot, "set_setting") as setting, \
                 patch.object(bot, "import_pi_academy_excel") as importer:
                await getattr(bot, name)(update, NS())
            update.message.reply_text.assert_awaited_once()
            setting.assert_not_called()
            importer.assert_not_called()

    async def test_payment_list_is_not_posted_in_group_even_by_admin(self):
        update = self.update(admin=True)
        with patch.object(bot, "get_all_students") as students:
            await bot.tolovlar_command(update, NS())
        students.assert_not_called()

    def test_reply_policy(self):
        group = self.update()
        private = self.update(chat_type="private")
        with patch.object(bot, "is_admin_online", return_value=True):
            self.assertFalse(bot.should_answer(group, "Python qanday ishlaydi?", False))
            self.assertTrue(bot.should_answer(group, "Pi yordam ber", True))
            self.assertTrue(bot.should_answer(private, "salom", False))
        with patch.object(bot, "is_admin_online", return_value=False):
            self.assertTrue(bot.should_answer(group, "Python qanday ishlaydi?", False))
            self.assertFalse(bot.should_answer(group, "Ustoz tekshirib bering", False))
            self.assertFalse(bot.should_answer(group, "ha", False))
            self.assertFalse(bot.should_answer(group, "rahmat", False))

    def test_direct_mentions_and_replies(self):
        message = NS(reply_to_message=None)
        group = NS(type="group")
        target = NS(id=5, username="pi_bot")
        for text in ("Pi yordam ber", "@PI_BOT salom"):
            self.assertTrue(bot.direct_request(message, group, target, text))
        for text in ("python", "@pi_bot_fake", "kompilyator"):
            self.assertFalse(bot.direct_request(message, group, target, text))
        message.reply_to_message = NS(from_user=None)
        self.assertFalse(bot.direct_request(message, group, target, "ha"))
        message.reply_to_message = NS(from_user=NS(id=5))
        self.assertTrue(bot.direct_request(message, group, target, "ha"))

    async def test_only_main_group_admin_activity_counts(self):
        with patch.object(bot, "get_setting", return_value="12"), \
             patch.object(bot, "update_admin_activity") as activity:
            await bot.track_admin_activity(self.update(admin=True), NS())
            await bot.track_admin_activity(self.update(), NS())
            await bot.track_admin_activity(self.update(admin=True, chat_type="private"), NS())
        activity.assert_called_once()

    def test_emoji_and_long_answers_fit_telegram(self):
        text = "Salom 🚀\n" * 3000
        chunks = list(bot.split_reply(text))
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(c.encode("utf-16-le")) // 2 <= 3500 for c in chunks))

    async def test_history_is_sent_to_ai_and_success_saved(self):
        history = [{"role": "user", "content": "Oldingi savol"},
                   {"role": "assistant", "content": "Oldingi javob"}]
        response = NS(choices=[NS(message=NS(content="Davomi"))])
        with patch.object(ai_service, "get_history", return_value=history), \
             patch.object(ai_service, "remember") as remember, \
             patch.object(ai_service.client.chat.completions, "create", AsyncMock(return_value=response)) as create:
            await ai_service.ask_ai("Soddaroq tushuntir", direct=True, conversation_key=(1, 2))
        self.assertEqual(create.call_args.kwargs["messages"][1:3], history)
        remember.assert_called_once_with(1, 2, "Soddaroq tushuntir", "Davomi")

    async def test_api_failure_does_not_pollute_memory(self):
        with patch.object(ai_service, "get_history", return_value=[]), \
             patch.object(ai_service, "remember") as remember, \
             patch.object(ai_service.client.chat.completions, "create", AsyncMock(side_effect=RuntimeError("test"))):
            reply = await ai_service.ask_ai("Salom", conversation_key=(1, 2))
        self.assertIn("xatolik", reply)
        remember.assert_not_called()


if __name__ == "__main__":
    unittest.main()
