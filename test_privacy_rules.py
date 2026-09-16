# -*- coding: utf-8 -*-
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import bot

async def run_privacy_tests():
    print("=== TESTING STRICT STUDENT PRIVACY RULES ===")

    mock_bot = AsyncMock()
    mock_bot.username = "pi_academy_bot"
    mock_bot.get_me = AsyncMock(return_value=MagicMock(username="pi_academy_bot"))

    bot.set_setting("admin_manual_status", "offline")

    # 1. Test jadval_command: Regular student trying to see another student's schedule
    update_other = MagicMock()
    msg_other = AsyncMock()
    msg_other.reply_to_message = None
    update_other.message = msg_other
    update_other.effective_user = MagicMock(id=999991, full_name="Oddiy O'quvchi")
    update_other.effective_chat = MagicMock(type="supergroup", id=-1003865779918)
    context_other = MagicMock()
    context_other.args = ["Murod"]

    with patch("bot.find_student_by_user", return_value={"id": 1, "name": "Sardorbek"}):
        await bot.jadval_command(update_other, context_other)
        # Should reply with privacy warning
        msg_other.reply_text.assert_awaited_once()
        args = msg_other.reply_text.await_args[0][0]
        assert "Maxfiylik qoidasi" in args
        assert "Boshqa o'quvchilar" in args
    print("[TEST 1] jadval_command blocks looking up another student: OK")

    # 2. Test jadval_command: Regular student looking up their own schedule
    update_self = MagicMock()
    msg_self = AsyncMock()
    msg_self.reply_to_message = None
    update_self.message = msg_self
    update_self.effective_user = MagicMock(id=999992, full_name="Murod")
    update_self.effective_chat = MagicMock(type="supergroup", id=-1003865779918)
    context_self = MagicMock()
    context_self.args = []

    murod_student = {"id": 2, "name": "Yarashov Murod", "course_name": "Python dasturlash"}
    with patch("bot.find_student_by_user", return_value=murod_student), \
         patch("bot.send_reply") as mock_send_reply:
        await bot.jadval_command(update_self, context_self)
        mock_send_reply.assert_awaited_once()
        reply_content = mock_send_reply.await_args[0][1]
        assert "Yarashov Murod" in reply_content
        assert "dars jadvali" in reply_content.lower()
    print("[TEST 2] jadval_command allows student to see their OWN schedule: OK")

    # 3. Test text message: Regular student asking another student's schedule
    update_text = MagicMock()
    msg_text = AsyncMock()
    msg_text.text = "Murodni dars jadvali qanaqa?"
    msg_text.reply_to_message = None
    update_text.message = msg_text
    update_text.effective_user = MagicMock(id=999993, full_name="Ali")
    update_text.effective_chat = MagicMock(type="private", id=999993)
    context_text = MagicMock()
    context_text.bot = mock_bot

    with patch("bot.find_student_by_user", return_value={"id": 3, "name": "Ali Valiyev"}), \
         patch("bot.send_reply") as mock_send:
        await bot.handle_text_message(update_text, context_text)
        mock_send.assert_awaited_once()
        args = mock_send.await_args[0][1]
        assert "Maxfiylik qoidasi" in args
    print("[TEST 3] Text query 'Murodni dars jadvali' blocked for regular user: OK")

    # 4. Test text message: Regular student asking another student's payment
    msg_text.text = "Murod to'ladimi?"
    with patch("bot.find_student_by_user", return_value={"id": 3, "name": "Ali Valiyev"}), \
         patch("bot.send_reply") as mock_send:
        await bot.handle_text_message(update_text, context_text)
        mock_send.assert_awaited_once()
        args = mock_send.await_args[0][1]
        assert "Maxfiylik qoidasi" in args
        assert "boshqa o'quvchilarning to'lov" in args
    print("[TEST 4] Text query 'Murod to'ladimi?' blocked for regular user: OK")

    # 5. Test text message: Regular student asking general debt / payment list
    msg_text.text = "Kimlar to'lamadi?"
    with patch("bot.find_student_by_user", return_value={"id": 3, "name": "Ali Valiyev"}), \
         patch("bot.send_reply") as mock_send:
        await bot.handle_text_message(update_text, context_text)
        mock_send.assert_awaited_once()
        args = mock_send.await_args[0][1]
        assert "Maxfiylik qoidasi" in args
        assert "rahbariyat" in args
    print("[TEST 5] Text query 'Kimlar to'lamadi?' blocked for regular user: OK")

    # 6. Test text message: Regular student asking another student's phone / performance
    msg_text.text = "Murodning telefon raqami nima?"
    with patch("bot.find_student_by_user", return_value={"id": 3, "name": "Ali Valiyev"}), \
         patch("bot.send_reply") as mock_send:
        await bot.handle_text_message(update_text, context_text)
        mock_send.assert_awaited_once()
        args = mock_send.await_args[0][1]
        assert "Maxfiylik qoidasi" in args
        assert "shaxsiy ma'lumotlari" in args
    print("[TEST 6] Text query 'Murodning telefon raqami' blocked for regular user: OK")

    # 7. Test text message: Regular student asking for all students list
    msg_text.text = "O'quvchilar ro'yxatini ber"
    with patch("bot.find_student_by_user", return_value={"id": 3, "name": "Ali Valiyev"}), \
         patch("bot.send_reply") as mock_send:
        await bot.handle_text_message(update_text, context_text)
        mock_send.assert_awaited_once()
        args = mock_send.await_args[0][1]
        assert "Maxfiylik qoidasi" in args
        assert "to'liq ro'yxati maxfiy" in args
    print("[TEST 7] Text query 'O'quvchilar ro'yxati' blocked for regular user: OK")

    # 8. Test text message: Regular student asking their OWN payment info
    msg_text.text = "Mening to'lovim qachon?"
    ali_student = {"id": 3, "name": "Ali Valiyev", "course_name": "Python", "due_day": 15}
    with patch("bot.find_student_by_user", return_value=ali_student), \
         patch("bot.get_paid_students", return_value=[3]), \
         patch("bot.send_reply") as mock_send:
        await bot.handle_text_message(update_text, context_text)
        mock_send.assert_awaited_once()
        args = mock_send.await_args[0][1]
        assert "Ali Valiyev" in args
        assert "15-sanasi" in args
        assert "to'langan" in args
    print("[TEST 8] Text query for OWN payment answered safely: OK")

    # 9. Test text message: Unlinked user asking 'bugun dars bormi?' -> Does NOT reveal other students
    msg_text.text = "Bugun dars bormi?"
    with patch("bot.find_student_by_user", return_value=None), \
         patch("bot.send_reply") as mock_send:
        await bot.handle_text_message(update_text, context_text)
        mock_send.assert_awaited_once()
        args = mock_send.await_args[0][1]
        # Should NEVER contain other students' names
        assert "profilingiz o'quvchilar ro'yxatida topilmadi" in args
        assert "Qudratov" not in args
        assert "Murod" not in args
    print("[TEST 9] 'Bugun dars bormi?' for unlinked user does NOT leak student names: OK")

    print("\nALL PRIVACY & INFORMATION SECURITY TESTS PASSED! 100% OK")

if __name__ == "__main__":
    asyncio.run(run_privacy_tests())
