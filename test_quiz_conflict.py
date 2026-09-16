import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import bot
import database
from config import ADMIN_ID
from telegram import InlineKeyboardMarkup

def make_mock_update(user_id, chat_type, text, reply_to_user=None):
    update = MagicMock()
    user = MagicMock()
    user.id = user_id
    user.username = "shaxboz_salomov" if user_id == ADMIN_ID else "anvar_python"
    user.first_name = "Shaxboz" if user_id == ADMIN_ID else "Anvar"
    user.is_bot = False

    chat = MagicMock()
    chat.id = -100555444333
    chat.type = chat_type

    message = MagicMock()
    message.message_id = 901
    message.text = text
    message.from_user = user
    message.chat = chat
    message.message_thread_id = None
    message.reply_to_message = None
    message.reply_text = AsyncMock()

    update.effective_user = user
    update.effective_chat = chat
    update.message = message
    return update

async def run_conflict_tests():
    print("=== TESTING QUIZ CONFLICT & ACTIVE PROMPT RESOLUTION ===")
    chat_id = -100555444333
    admin_id = ADMIN_ID

    # Clear previous sessions for this test chat
    with database.closing(database.get_connection()) as conn, conn:
        conn.execute("DELETE FROM quiz_questions WHERE session_id IN (SELECT id FROM quiz_sessions WHERE chat_id = ?)", (chat_id,))
        conn.execute("DELETE FROM quiz_answers WHERE session_id IN (SELECT id FROM quiz_sessions WHERE chat_id = ?)", (chat_id,))
        conn.execute("DELETE FROM quiz_sessions WHERE chat_id = ?", (chat_id,))

    mock_bot = MagicMock()
    mock_bot.id = 777777
    mock_bot.username = "pi_yordamchi_bot"
    mock_bot.send_message = AsyncMock()

    poll_counter = [0]
    async def mock_send_poll(*args, **kwargs):
        poll_counter[0] += 1
        msg = MagicMock()
        msg.message_id = 2000 + poll_counter[0]
        msg.poll = MagicMock()
        msg.poll.id = f"poll_conf_{poll_counter[0]}"
        return msg

    mock_bot.send_poll = AsyncMock(side_effect=mock_send_poll)
    mock_bot.stop_poll = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()
    mock_bot.pin_chat_message = AsyncMock()
    mock_bot.unpin_chat_message = AsyncMock()

    mock_context = MagicMock()
    mock_context.bot = mock_bot
    mock_context.chat_data = {}

    quiz_1 = {
        "success": True,
        "topic": "Python 1-Mavzu",
        "questions": [
            {"question": f"Savol {i}?", "options": ["A", "B", "C", "D"], "correct_option_id": 0, "explanation": "Izoh"}
            for i in range(1, 11)
        ]
    }

    quiz_2 = {
        "success": True,
        "topic": "Python 2-Mavzu",
        "questions": [
            {"question": f"Savol {i}?", "options": ["A", "B", "C", "D"], "correct_option_id": 1, "explanation": "Izoh"}
            for i in range(1, 11)
        ]
    }

    # 1. 1-testni boshlaymiz
    print("\n--- 1. Launching Initial Quiz (Python 1-Mavzu) ---")
    await bot.launch_quiz_session(chat_id, admin_id, quiz_1, mock_context)
    active = database.get_active_quiz_sessions(chat_id)
    assert len(active) == 1, "There should be 1 active quiz session"
    assert active[0]["topic"] == "Python 1-Mavzu"
    print("[PASSED] Quiz 1 successfully started and active.")

    # 2. Test tugatilmasdan boshqa test so'ralganda bot so'rashi kerak:
    print("\n--- 2. Requesting New Quiz While Active Quiz Exists ---")
    u_req = make_mock_update(admin_id, "supergroup", "Python 2-Mavzudan yangi test qilib ber")
    with patch("bot.send_reply", new_callable=AsyncMock) as mock_send_reply:
        handled = await bot.handle_admin_natural_query(u_req, mock_context, "Python 2-Mavzudan yangi test qilib ber")
        assert handled == True, "Request must be intercepted and handled"
        assert "pending_quiz" in mock_context.chat_data, "Pending quiz must be saved in chat_data"
        assert mock_send_reply.called, "Bot must send prompt message with options"
        args, kwargs = mock_send_reply.call_args
        assert "faol test davom etmoqda" in args[1].lower() or "faol test" in args[1].lower(), "Must mention active test"
        assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup), "Must provide inline buttons"
        print("[PASSED] Bot intercepted request and asked user what to do with active test!")

    # 3. "keep_current" callback testi (Bekor qilish, hozirgi test davom etsin)
    print("\n--- 3. Testing 'keep_current' callback ---")
    q_cb = MagicMock()
    q_cb.data = "quiz_act:keep_current"
    q_cb.from_user = MagicMock(id=admin_id)
    q_cb.answer = AsyncMock()
    q_cb.edit_message_text = AsyncMock()
    u_cb = MagicMock(callback_query=q_cb, effective_chat=MagicMock(id=chat_id))
    await bot.quiz_callback_handler(u_cb, mock_context)
    assert "pending_quiz" not in mock_context.chat_data, "Pending quiz must be cleared"
    active_now = database.get_active_quiz_sessions(chat_id)
    assert len(active_now) == 1, "Current quiz should still be active"
    print("[PASSED] 'keep_current' cleanly kept the current quiz active and cleared pending.")

    # 4. "qaysi testni tugatish kerak" so'rovi testi
    print("\n--- 4. Testing 'qaysi testni tugatish kerak' natural query ---")
    u_inq = make_mock_update(admin_id, "supergroup", "qaysi testni tugatish kerak")
    with patch("bot.send_reply", new_callable=AsyncMock) as mock_reply_inq:
        handled_inq = await bot.handle_admin_natural_query(u_inq, mock_context, "qaysi testni tugatish kerak")
        assert handled_inq == True
        print("[PASSED] Natural query 'qaysi testni tugatish kerak' handled cleanly!")

    # 5. "finish_and_start" callback testi (Eski testni yakunlab, yangisini boshlash)
    print("\n--- 5. Testing 'finish_and_start' callback ---")
    mock_context.chat_data["pending_quiz"] = {
        "text": "Python 2-Mavzu",
        "img_bytes": None,
        "caption_hint": "Python 2-Mavzu",
        "user_id": admin_id,
        "reply_to_message_id": 901,
        "message_thread_id": None
    }
    with patch("bot.generate_quiz_from_ai", new_callable=AsyncMock) as mock_ai_gen:
        mock_ai_gen.return_value = quiz_2
        q_cb_fin = MagicMock()
        q_cb_fin.data = "quiz_act:finish_and_start"
        q_cb_fin.from_user = MagicMock(id=admin_id)
        q_cb_fin.answer = AsyncMock()
        q_cb_fin.edit_message_text = AsyncMock()
        u_cb_fin = MagicMock(callback_query=q_cb_fin, effective_chat=MagicMock(id=chat_id))
        await bot.quiz_callback_handler(u_cb_fin, mock_context)

        active_after_switch = database.get_active_quiz_sessions(chat_id)
        assert len(active_after_switch) == 1
        assert active_after_switch[0]["topic"] == "Python 2-Mavzu", "New quiz must now be active"
        print("[PASSED] Old quiz was cleanly finished with results, and new quiz was launched!")

    # 6. Bir nechta faol test bo'lganda "testni tugat" so'ralishi
    print("\n--- 6. Multiple active tests disambiguation ---")
    # Manually insert another active test to simulate multiple active tests
    sid_extra = database.create_quiz_session(chat_id, admin_id, "Python 3-Mavzu Extra", 10)
    multiple_active = database.get_active_quiz_sessions(chat_id)
    assert len(multiple_active) == 2, "Should now have 2 active sessions"

    u_multi_fin = make_mock_update(admin_id, "supergroup", "testni tugat")
    with patch("bot.send_reply", new_callable=AsyncMock) as mock_multi_reply:
        handled_multi = await bot.handle_admin_natural_query(u_multi_fin, mock_context, "testni tugat")
        assert handled_multi == True
        args, kwargs = mock_multi_reply.call_args
        assert "qaysi testni yakunlamoqchisiz" in args[1].lower()
        print("[PASSED] When multiple tests are active, bot asks which one to finish with inline buttons!")

    # 7. "Barchasini yakunlash" (quiz_fin:all) callback testi
    print("\n--- 7. Testing 'quiz_fin:all' callback ---")
    q_cb_all = MagicMock()
    q_cb_all.data = "quiz_fin:all"
    q_cb_all.from_user = MagicMock(id=admin_id)
    q_cb_all.answer = AsyncMock()
    q_cb_all.delete_message = AsyncMock()
    u_cb_all = MagicMock(callback_query=q_cb_all, effective_chat=MagicMock(id=chat_id))
    await bot.quiz_callback_handler(u_cb_all, mock_context)

    active_final = database.get_active_quiz_sessions(chat_id)
    assert len(active_final) == 0, "All sessions must now be finished"
    print("[PASSED] 'quiz_fin:all' successfully closed all remaining active sessions!")

    print("\n>>> ALL CONFLICT & MULTI-TEST QUIZ TESTS PASSED 100%! <<<")

if __name__ == "__main__":
    asyncio.run(run_conflict_tests())
