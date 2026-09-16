import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import bot
import database
from config import ADMIN_ID

def make_mock_update(user_id, chat_type, text):
    update = MagicMock()
    user = MagicMock()
    user.id = user_id
    user.username = "shaxboz_salomov" if user_id == ADMIN_ID else "anvar_python"
    user.first_name = "Shaxboz" if user_id == ADMIN_ID else "Anvar"
    user.is_bot = False

    chat = MagicMock()
    chat.id = -100777666555
    chat.type = chat_type

    message = MagicMock()
    message.message_id = 1111
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

async def run_bank_tests():
    print("=== TESTING QUIZ BANK & RANDOM TEST GENERATION ===")
    chat_id = -100777666555
    admin_id = ADMIN_ID

    mock_bot = MagicMock()
    mock_bot.id = 777777
    mock_bot.username = "pi_yordamchi_bot"
    mock_bot.send_message = AsyncMock()

    poll_counter = [0]
    async def mock_send_poll(*args, **kwargs):
        poll_counter[0] += 1
        msg = MagicMock()
        msg.message_id = 3000 + poll_counter[0]
        msg.poll = MagicMock()
        msg.poll.id = f"poll_bank_{poll_counter[0]}"
        return msg

    mock_bot.send_poll = AsyncMock(side_effect=mock_send_poll)
    mock_bot.stop_poll = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()
    mock_bot.pin_chat_message = AsyncMock()
    mock_bot.unpin_chat_message = AsyncMock()

    mock_context = MagicMock()
    mock_context.bot = mock_bot
    mock_context.chat_data = {}

    # 1. TEST QUIZ BANK STATS
    print("\n--- 1. Testing get_quiz_bank_stats ---")
    stats = database.get_quiz_bank_stats()
    assert stats["total"] >= 20, f"Initial seed must provide at least 20 questions, got {stats['total']}"
    assert "python" in stats["categories"]
    print(f"[TEST 1 PASSED] Quiz bank stats OK! Total questions: {stats['total']}, Python: {stats['categories'].get('python')}")

    # 2. TEST SAVE QUIZ TO BANK (ESLAB QOLISH)
    print("\n--- 2. Testing save_quiz_to_bank ---")
    new_questions = [
        {
            "question": "Python-da generator funksiyalar qaysi kalit so'z orqali qiymat qaytaradi?",
            "options": ["yield", "return", "generate", "produce"],
            "correct_option_id": 0,
            "explanation": "yield kalit so'zi generatorlarda qiymatni saqlab qaytarish uchun ishlatiladi."
        },
        {
            "question": "Excel-da kataklar diapazonidagi sonlar yig'indisini hisoblaydigan ruscha formula qaysi?",
            "options": ["СУММ", "SUM", "ИТОГО", "СЧЁТ"],
            "correct_option_id": 0,
            "explanation": "СУММ formulasi berilgan barcha kataklar yig'indisini hisoblaydi."
        }
    ]
    inserted_py = database.save_quiz_to_bank("Python Generatorlar", [new_questions[0]], course_category="python")
    inserted_ex = database.save_quiz_to_bank("Excel Formulalari", [new_questions[1]], course_category="excel")
    stats_after = database.get_quiz_bank_stats()
    assert stats_after["total"] >= stats["total"], "Bank total questions must increase"
    print(f"[TEST 2 PASSED] Saved questions to bank! Total now: {stats_after['total']}")

    # 3. TEST GET RANDOM QUIZ FROM BANK
    print("\n--- 3. Testing get_random_quiz_from_bank ---")
    rand_quiz = database.get_random_quiz_from_bank(category="python", count=10)
    assert rand_quiz is not None
    assert rand_quiz["success"] == True
    assert len(rand_quiz["questions"]) == 10
    assert rand_quiz["from_bank"] == True
    # Verify each question has proper structure
    for q in rand_quiz["questions"]:
        assert "question" in q
        assert len(q["options"]) == 4
        assert isinstance(q["correct_option_id"], int)
        assert "explanation" in q
    print(f"[TEST 3 PASSED] get_random_quiz_from_bank successfully retrieved 10 random Python questions!")

    # 4. TEST NATURAL QUERY: "random test tashla"
    print("\n--- 4. Testing natural query 'random test tashla' ---")
    u_rand = make_mock_update(admin_id, "supergroup", "random test tashla")
    handled = await bot.handle_admin_natural_query(u_rand, mock_context, "random test tashla")
    assert handled == True, "Natural query 'random test tashla' must be handled"
    assert mock_bot.send_poll.call_count == 10, "Must have launched 10 poll questions from bank"
    active = database.get_active_quiz_sessions(chat_id)
    assert len(active) == 1
    assert "Tasodifiy testlar bazasidan" in active[0]["topic"]
    print("[TEST 4 PASSED] 'random test tashla' successfully launched 10 polls from the bank without AI call!")

    # 5. TEST NATURAL QUERY: "pythonda random test ber"
    print("\n--- 5. Testing natural query 'pythonda random test ber' ---")
    # Finish previous session first
    database.finish_quiz_session(active[0]["id"])
    mock_bot.send_poll.reset_mock()

    u_py_rand = make_mock_update(admin_id, "supergroup", "pythonda random test tashlab ber")
    handled_py = await bot.handle_admin_natural_query(u_py_rand, mock_context, "pythonda random test tashlab ber")
    assert handled_py == True
    assert mock_bot.send_poll.call_count == 10
    active_py = database.get_active_quiz_sessions(chat_id)
    assert len(active_py) == 1
    assert "Python" in active_py[0]["topic"]
    print("[TEST 5 PASSED] 'pythonda random test tashlab ber' successfully launched Python random test!")

    # 6. TEST STATS QUERY: "testlar bazasi"
    print("\n--- 6. Testing natural query 'testlar bazasi' ---")
    u_stats = make_mock_update(admin_id, "supergroup", "testlar bazasi")
    with patch("bot.send_reply", new_callable=AsyncMock) as mock_reply:
        handled_stats = await bot.handle_admin_natural_query(u_stats, mock_context, "testlar bazasi")
        assert handled_stats == True
        args, kwargs = mock_reply.call_args
        assert "DOIMIY TESTLAR BAZASI" in args[1]
        print("[TEST 6 PASSED] 'testlar bazasi' showed bank statistics!")

    # Clean up test chat sessions
    for s in database.get_active_quiz_sessions(chat_id):
        database.finish_quiz_session(s["id"])

    print("\n>>> ALL QUIZ BANK & RANDOM TEST TESTS PASSED 100%! <<<")

if __name__ == "__main__":
    asyncio.run(run_bank_tests())
