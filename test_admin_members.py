import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from telegram.ext import ApplicationHandlerStop
import database as db
import member_service as members
import bot


class AdminMemberTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temp.name) / "test.db")
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def user(self, user_id=100, name="Ali Valiyev"):
        return NS(id=user_id, full_name=name, username="ali", is_bot=False)

    def update(self, text, admin=True, message_id=1):
        return NS(effective_user=self.user(bot.ADMIN_ID if admin else 99),
                  effective_chat=NS(id=10, type="private"),
                  message=NS(text=text, message_id=message_id, reply_to_message=None,
                             reply_text=AsyncMock()))

    def enroll(self, user_id=100, name="Ali Valiyev"):
        members.register_member(self.user(user_id, name), -10)
        return members.enroll_member(user_id, name, "Python", 15)

    async def test_any_nonadmin_command_is_stopped(self):
        with self.assertRaises(ApplicationHandlerStop):
            await bot.command_access_guard(self.update("/start", admin=False), NS())
        await bot.command_access_guard(self.update("/start"), NS())

    async def test_all_command_callbacks_are_admin_protected(self):
        for name in ("start_command", "id_command", "status_command", "bugun_command",
                     "ertaga_command", "level_command", "new_conversation_command", "members_command"):
            update = self.update("/help", admin=False)
            await getattr(bot, name)(update, NS())
            update.message.reply_text.assert_awaited_once_with("Bu amal faqat administrator uchun.")

    def test_profile_join_is_idempotent_and_does_not_invent_finances(self):
        user = self.user()
        members.register_member(user, -10)
        user.full_name = "Ali Yangilangan"
        members.register_member(user, -10)
        rows = members.list_members()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["full_name"], "Ali Yangilangan")
        self.assertIsNone(rows[0]["student_id"])
        self.assertEqual(db.get_all_students(), [])

    def test_enrollment_and_link_conflicts(self):
        student = self.enroll()
        self.assertEqual(members.list_members()[0]["student_id"], student)
        with self.assertRaises(ValueError):
            members.enroll_member(100, "Other name", "Python", 10)
        second = db.add_or_update_student("Other", 12)
        with self.assertRaises(ValueError):
            members.link_member(100, second)

    async def test_natural_payment_reversal_and_audit(self):
        student = self.enroll()
        self.assertTrue(await bot.natural_payment(self.update("Ali to‘ladi 2026-09"), NS()))
        self.assertIn(student, db.get_paid_students("2026-09"))
        await bot.natural_payment(self.update("Ali to'lamadi 2026-09", message_id=2), NS())
        self.assertNotIn(student, db.get_paid_students("2026-09"))
        # Replaying the older message must not reverse the newer operation.
        await bot.natural_payment(self.update("Ali to‘ladi 2026-09"), NS())
        self.assertNotIn(student, db.get_paid_students("2026-09"))
        conn = db.get_connection()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payment_events").fetchone()[0], 2)
        finally:
            conn.close()

    async def test_nonadmin_text_cannot_mark_payment(self):
        self.enroll()
        await bot.natural_payment(self.update("Ali to'ladi 2026-09", admin=False), NS())
        self.assertEqual(db.get_paid_students("2026-09"), set())

    async def test_ambiguous_names_do_not_write(self):
        self.enroll(100, "Ali Valiyev")
        self.enroll(101, "Ali Karimov")
        update = self.update("Ali to'ladi 2026-09")
        await bot.natural_payment(update, NS())
        self.assertEqual(db.get_paid_students("2026-09"), set())
        self.assertIn("Bir nechta", update.message.reply_text.await_args.args[0])

    async def test_reply_uses_telegram_id(self):
        student = self.enroll()
        update = self.update("to'ladi 2026-09")
        update.message.reply_to_message = NS(from_user=self.user())
        await bot.natural_payment(update, NS())
        self.assertIn(student, db.get_paid_students("2026-09"))

    def test_questions_and_quotes_are_not_payment_instructions(self):
        for text in ("Ali to'ladimi?", "Ali to'ladi?", "Ali to'lasa kerak", '"Ali to\'ladi"'):
            self.assertIsNone(members.parse_payment(text))

    async def test_menus_only_grant_admin_scopes(self):
        telegram_bot = NS(delete_my_commands=AsyncMock(), set_my_commands=AsyncMock())
        with patch.object(bot, "get_setting", return_value="-123"):
            await bot.configure_command_menus(telegram_bot)
        for call in telegram_bot.set_my_commands.await_args_list:
            scope = call.kwargs["scope"]
            if scope.type == "chat":
                self.assertEqual(scope.chat_id, bot.ADMIN_ID)
            else:
                self.assertEqual(scope.user_id, bot.ADMIN_ID)

    async def test_new_member_event_creates_profile(self):
        update = self.update("joined")
        update.effective_chat.type = "supergroup"
        update.message.new_chat_members = [self.user()]
        await bot.welcome_new_members(update, NS(bot=NS(id=555)))
        self.assertEqual(members.list_members()[0]["telegram_id"], 100)
        self.assertEqual(db.get_all_students(), [])

    async def test_payment_is_handled_before_ai(self):
        student = self.enroll()
        with patch.object(bot, "ask_ai", AsyncMock()) as ai:
            await bot.handle_text_message(self.update("Ali to'ladi 2026-09"), NS())
        self.assertIn(student, db.get_paid_students("2026-09"))
        ai.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
