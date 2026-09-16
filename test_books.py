import inspect
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from telegram import Message
from telegram.error import BadRequest
import book_service
import bot


class BookTests(unittest.IsolatedAsyncioTestCase):
    def test_request_selection(self):
        for text in ("kitob", "Kitoblar", "kitob tashlab ber", "menga kitobni yuboring", "Pi kitob kerak"):
            self.assertEqual(book_service.requested_books(text), ["office", "html", "python"])
        self.assertEqual(book_service.requested_books("HTML kitob"), ["html"])
        self.assertEqual(book_service.requested_books("Word Excel kitob kerak"), ["office"])
        self.assertEqual(book_service.requested_books("Python kitob"), ["python"])
        self.assertEqual(book_service.requested_books("Excel kitobi bormi?"), ["office"])
        for text in ("kitobdagi 2-masala", "kitob kerak emas", "bu kitob yaxshi", "kitob haqida tushuntir", "salom"):
            self.assertEqual(book_service.requested_books(text), [])

    async def test_both_real_pdf_files_are_attached(self):
        seen = []
        async def send(**kwargs):
            inspect.signature(Message.reply_document).bind(None, **kwargs)
            self.assertEqual(kwargs["document"].read(5), b"%PDF-")
            seen.append(kwargs["filename"])
        message = NS(text="kitob", reply_document=AsyncMock(side_effect=send), reply_text=AsyncMock())
        self.assertTrue(await book_service.send_requested_books(message))
        self.assertEqual(len(seen), 3)
        message.reply_text.assert_not_awaited()

    async def test_regular_student_can_request_books_without_ai_or_admin_checks(self):
        update = NS(effective_chat=NS(id=1, type="group"), effective_user=NS(id=-100),
                    message=NS(text="kitob", reply_document=AsyncMock(), reply_text=AsyncMock()))
        with patch.object(bot, "ask_ai", AsyncMock()) as ai, patch.object(bot, "is_admin_online", return_value=True):
            await bot.handle_text_message(update, NS())
        self.assertEqual(update.message.reply_document.await_count, 3)
        ai.assert_not_awaited()

    async def test_only_selected_book_is_sent(self):
        message = NS(text="HTML kitob", reply_document=AsyncMock(), reply_text=AsyncMock())
        await book_service.send_requested_books(message)
        self.assertEqual(message.reply_document.await_count, 1)
        self.assertEqual(message.reply_document.await_args.kwargs["filename"], "HTML_By_Example_UZ.pdf")

    async def test_python_book_is_sent(self):
        message = NS(text="Python kitob", reply_document=AsyncMock(), reply_text=AsyncMock())
        await book_service.send_requested_books(message)
        self.assertEqual(message.reply_document.await_count, 1)
        self.assertEqual(message.reply_document.await_args.kwargs["filename"], "Python_By_Example_UZ.pdf")

    async def test_telegram_failure_is_reported(self):
        message = NS(text="HTML kitob", reply_document=AsyncMock(side_effect=BadRequest("Cannot send")), reply_text=AsyncMock())
        self.assertTrue(await book_service.send_requested_books(message))
        self.assertIn("yuborib bo'lmadi", message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
