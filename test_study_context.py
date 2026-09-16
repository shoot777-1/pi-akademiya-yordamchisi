import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
import study_context as study
import ai_service
import bot


class StudyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patcher = patch.object(study, "DB_PATH", Path(self.temp.name) / "test.db")
        self.patcher.start()
        bot._request_times.clear()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def update(self, text="2-3 masalani chunmadim", user=5, reply=None):
        message = NS(text=text, message_id=100, message_thread_id=None,
                     reply_to_message=reply, reply_text=AsyncMock(return_value=NS(message_id=101)))
        update = NS(message=message, effective_user=NS(id=user, first_name="Test"),
                    effective_chat=NS(id=1, type="group"))
        context = NS(bot=NS(id=999, username="pi_bot", get_me=AsyncMock(return_value=NS(username="pi_bot"))))
        return update, context

    def test_owner_chat_topic_and_ambiguity(self):
        study.save_photo(1, 0, 10, 5, "one")
        self.assertEqual(study.resolve(1, 0, 5)[0]["file_id"], "one")
        self.assertIsNone(study.resolve(2, 0, 5)[0])
        self.assertIsNone(study.resolve(1, 7, 5)[0])
        self.assertIsNone(study.resolve(1, 0, 6)[0])
        study.save_photo(1, 0, 11, 5, "two")
        self.assertTrue(study.resolve(1, 0, 5)[1])
        self.assertEqual(study.resolve(1, 0, 5, 10)[0]["file_id"], "one")

    def test_explicit_reply_can_reference_another_students_public_image(self):
        study.save_photo(1, 0, 10, 5, "one")
        study.link_message(1, 0, 20, 10, "Ikkinchi masala", owner=5)
        result = study.resolve(1, 0, 6, 20)
        self.assertEqual(result[0]["file_id"], "one")
        self.assertEqual(result[2], "Ikkinchi masala")
        study.select_photo(1, 0, 6, 10)
        self.assertEqual(study.resolve(1, 0, 6)[0]["file_id"], "one")

    def test_expiry_and_reset_remove_photo_references(self):
        with patch.object(study.time, "time", return_value=100):
            study.save_photo(1, 0, 10, 5, "one")
        with patch.object(study.time, "time", return_value=100 + study.TTL + 1):
            self.assertIsNone(study.resolve(1, 0, 5)[0])
        study.save_photo(1, 0, 11, 5, "two")
        study.link_message(1, 0, 20, 11, "answer")
        study.clear(1, 5)
        self.assertIsNone(study.resolve(1, 0, 5, 20)[0])

    def test_unrelated_reply_does_not_attach_latest_photo(self):
        study.save_photo(1, 0, 10, 5, "one")
        self.assertIsNone(study.resolve(1, 0, 5, 88)[0])

    def test_followup_typo_and_number_recognition(self):
        for text in ("2-3 masala chunmadim", "2–3-masalani tushunmadim", "shu joyi nega?", "yana sodda tushuntir"):
            self.assertTrue(study.is_followup(text))
        self.assertFalse(study.is_followup("ha"))

    async def test_followup_downloads_original_image_and_passes_it_to_ai(self):
        study.save_photo(1, 0, 10, 5, "original-file", "Uchta masala")
        update, context = self.update()
        with patch.object(bot, "load_study_image", AsyncMock(return_value=b"jpeg")) as download, \
             patch.object(bot, "ask_ai", AsyncMock(return_value="2-masala yechimi")) as ai, \
             patch.object(bot, "learning_context", return_value="Sodda"):
            await bot.handle_text_message(update, context)
        download.assert_awaited_once_with(context.bot, "original-file")
        self.assertEqual(ai.await_args.kwargs["image_bytes"], b"jpeg")
        self.assertEqual(ai.await_args.args[0], "2-3 masalani chunmadim")
        self.assertEqual(study.resolve(1, 0, 5)[2], "2-masala yechimi")
        self.assertEqual(study.resolve(1, 0, 7, 101)[0]["file_id"], "original-file")

    async def test_ambiguous_photos_ask_instead_of_calling_ai(self):
        study.save_photo(1, 0, 10, 5, "one")
        study.save_photo(1, 0, 11, 5, "two")
        update, context = self.update()
        with patch.object(bot, "ask_ai", AsyncMock()) as ai:
            await bot.handle_text_message(update, context)
        ai.assert_not_awaited()
        self.assertIn("Qaysi rasm", update.message.reply_text.await_args.args[0])

    async def test_file_download_failure_does_not_invent_a_solution(self):
        study.save_photo(1, 0, 10, 5, "one")
        update, context = self.update()
        with patch.object(bot, "load_study_image", AsyncMock(side_effect=RuntimeError())), \
             patch.object(bot, "ask_ai", AsyncMock()) as ai:
            await bot.handle_text_message(update, context)
        ai.assert_not_awaited()
        self.assertIn("qayta yuboring", update.message.reply_text.await_args.args[0])

    async def test_ai_request_contains_pixels_not_only_text_summary(self):
        response = NS(choices=[NS(message=NS(content="Yechim"))])
        with patch.object(ai_service.client.chat.completions, "create", AsyncMock(return_value=response)) as create:
            await ai_service.ask_ai("2-3 masala", direct=True, image_bytes=b"jpeg",
                                    quoted_text="Oldingi tushuntirish", source_caption="Uy vazifasi")
        messages = create.await_args.kwargs["messages"]
        self.assertEqual(messages[-1]["content"][1]["type"], "image_url")
        self.assertTrue(messages[-1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertIn("Oldingi tushuntirish", messages[-2]["content"])

    async def test_teacher_addressed_followup_stays_silent(self):
        study.save_photo(1, 0, 10, 5, "one")
        update, context = self.update("Ustoz 2-3 masalani tushunmadim")
        with patch.object(bot, "is_admin_online", return_value=False), \
             patch.object(bot, "ask_ai", AsyncMock()) as ai:
            await bot.handle_text_message(update, context)
        ai.assert_not_awaited()
        update.message.reply_text.assert_not_awaited()

    async def test_photo_is_saved_even_while_admin_is_online(self):
        update, context = self.update()
        update.message.photo = [NS(file_id="saved-photo")]
        update.message.caption = ""
        with patch.object(bot, "is_admin_online", return_value=True), \
             patch.object(bot, "analyze_image_with_ai", AsyncMock()) as ai:
            await bot.handle_photo(update, context)
        ai.assert_not_awaited()
        self.assertEqual(study.resolve(1, 0, 5)[0]["file_id"], "saved-photo")


if __name__ == "__main__":
    unittest.main()
