import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import bot
import database
from config import ADMIN_ID
from telegram import Poll

def make_mock_update(user_id, chat_type, text, reply_to_user=None):
    update = MagicMock()
    user = MagicMock()
    user.id = user_id
    user.username = "shaxboz_salomov" if user_id == ADMIN_ID else "anvar_python"
    user.first_name = "Shaxboz" if user_id == ADMIN_ID else "Anvar"
    user.is_bot = False

    chat = MagicMock()
    chat.id = -100999888777
    chat.type = chat_type

    message = MagicMock()
    message.message_id = 501
    message.text = text
    message.from_user = user
    message.chat = chat
    message.message_thread_id = None
    message.reply_text = AsyncMock()

    if reply_to_user:
        replied_msg = MagicMock()
        replied_msg.from_user = reply_to_user
        replied_msg.message_id = 500
        replied_msg.text = "Python mavzusi"
        replied_msg.photo = None
        replied_msg.message_thread_id = None
        message.reply_to_message = replied_msg
    else:
        message.reply_to_message = None

    update.effective_user = user
    update.effective_chat = chat
    update.message = message
    return update

async def run_tests():
    print("=== TESTING QUIZ GENERATION & INTERACTIVE SCORING ===")
    chat_id = -100999888777
    admin_id = ADMIN_ID

    for s in database.get_active_quiz_sessions(chat_id):
        database.finish_quiz_session(s["id"])

    mock_bot = MagicMock()
    mock_bot.id = 777777
    mock_bot.username = "pi_yordamchi_bot"
    mock_bot.send_message = AsyncMock()
    
    # Mock send_poll to return mock message with poll
    poll_counter = [0]
    async def mock_send_poll(*args, **kwargs):
        poll_counter[0] += 1
        msg = MagicMock()
        msg.message_id = 1000 + poll_counter[0]
        msg.poll = MagicMock()
        msg.poll.id = f"poll_test_{poll_counter[0]}"
        return msg

    mock_bot.send_poll = AsyncMock(side_effect=mock_send_poll)
    mock_bot.stop_poll = AsyncMock()
    mock_bot.edit_message_text = AsyncMock()
    mock_bot.pin_chat_message = AsyncMock()
    mock_bot.unpin_chat_message = AsyncMock()

    mock_context = MagicMock()
    mock_context.bot = mock_bot

    # Sample 10 quiz questions data
    sample_quiz = {
        "success": True,
        "topic": "Python Ro'yxatlar (Lists)",
        "questions": [
            {
                "question": f"Python ro'yxatlariga yangi element qo'shish uchun qaysi metod ishlatiladi? ({i})",
                "options": ["append()", "add()", "insert_end()", "push()"],
                "correct_option_id": 0,
                "explanation": "append() metodi ro'yxat oxiriga yangi element qo'shadi."
            }
            for i in range(1, 11)
        ]
    }

    # 1. TEST LAUNCH QUIZ SESSION
    print("\n--- 1. Testing launch_quiz_session ---")
    await bot.launch_quiz_session(chat_id, admin_id, sample_quiz, mock_context)
    active_s = database.get_active_quiz_session(chat_id)
    assert active_s is not None, "Active quiz session must be in DB"
    assert active_s["topic"] == "Python Ro'yxatlar (Lists)"
    assert mock_bot.send_poll.call_count == 10, "Must have sent 10 polls"
    session_id = active_s["id"]
    print(f"[TEST 1 PASSED] 10 quiz polls successfully launched for session #{session_id}!")

    # 2. TEST POLL ANSWER & XP AWARDING
    print("\n--- 2. Testing PollAnswerHandler with +1 XP ---")
    # Link student Anvar (id 12) to telegram id 555111
    database.add_or_update_student("Mirzayev Anvar", 15, "Python", "anvar_python", telegram_id=555111)
    st_gam_before = database.get_student_gamification(student_id=12)
    xp_before = st_gam_before["xp"] if st_gam_before else 0

    # User Anvar answers Question 1 correctly (option 0)
    update_ans = MagicMock()
    ans = MagicMock()
    ans.poll_id = "poll_test_1"
    ans.user = MagicMock()
    ans.user.id = 555111
    ans.user.first_name = "Anvar"
    ans.option_ids = [0]
    update_ans.poll_answer = ans

    await bot.handle_poll_answer(update_ans, mock_context)

    st_gam_after = database.get_student_gamification(student_id=12)
    assert st_gam_after["xp"] == xp_before + 1, "Student Anvar must receive +1 XP for correct answer!"
    print(f"[TEST 2A PASSED] Correct answer awarded +1 XP! (From {xp_before} to {st_gam_after['xp']} XP)")

    # Test Duplicate voting prevention: Anvar votes on Question 1 again
    await bot.handle_poll_answer(update_ans, mock_context)
    st_gam_dup = database.get_student_gamification(student_id=12)
    assert st_gam_dup["xp"] == xp_before + 1, "Duplicate vote must NOT award extra XP!"
    print("[TEST 2B PASSED] Duplicate vote correctly prevented from awarding duplicate XP!")

    # Anvar answers Question 2 incorrectly (option 2)
    update_ans2 = MagicMock()
    ans2 = MagicMock()
    ans2.poll_id = "poll_test_2"
    ans2.user = MagicMock()
    ans2.user.id = 555111
    ans2.user.first_name = "Anvar"
    ans2.option_ids = [2]
    update_ans2.poll_answer = ans2

    await bot.handle_poll_answer(update_ans2, mock_context)
    st_gam_inc = database.get_student_gamification(student_id=12)
    assert st_gam_inc["xp"] == xp_before + 1, "Incorrect answer must not award XP!"
    print("[TEST 2C PASSED] Incorrect answer correctly recorded without adding XP!")

    # Another student (Murod id 2, tg 555222) answers Question 1 and Question 2 correctly
    database.add_or_update_student("Yarashov Murod", 10, "Python", "murod_tg", telegram_id=555222)
    update_m1 = MagicMock()
    m_ans1 = MagicMock()
    m_ans1.poll_id = "poll_test_1"
    m_ans1.user = MagicMock()
    m_ans1.user.id = 555222
    m_ans1.user.first_name = "Murod"
    m_ans1.option_ids = [0]
    update_m1.poll_answer = m_ans1
    await bot.handle_poll_answer(update_m1, mock_context)

    # 3. TEST FINISH QUIZ ("testni tugat")
    print("\n--- 3. Testing 'testni tugat' & Leaderboard Summary ---")
    u_finish = make_mock_update(admin_id, "supergroup", "testni tugat")
    handled_finish = await bot.handle_admin_natural_query(u_finish, mock_context, "testni tugat")
    assert handled_finish == True, "Admin 'testni tugat' must be handled!"
    assert mock_bot.stop_poll.call_count == 10, "All 10 polls must be stopped!"
    active_after = database.get_active_quiz_session(chat_id)
    assert active_after is None, "Quiz session must be finished and no longer active"
    print("[TEST 3 PASSED] 'testni tugat' successfully stopped polls and generated leaderboard results!")

    # 4. NATURAL TRIGGER TEST FOR CREATING QUIZ
    print("\n--- 4. Testing natural query trigger for quiz creation ---")
    with patch("bot.generate_quiz_from_ai", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = sample_quiz
        u_create = make_mock_update(admin_id, "supergroup", "Python mavzusidan test qilib ber")
        handled_create = await bot.handle_admin_natural_query(u_create, mock_context, "Python mavzusidan test qilib ber")
        assert handled_create == True, "Natural query 'test qilib ber' must be handled"
        assert mock_gen.called, "generate_quiz_from_ai must have been called"
        print("[TEST 4 PASSED] Natural trigger 'Python mavzusidan test qilib ber' launched quiz!")

    print("\n>>> ALL QUIZ FEATURE INTEGRATION TESTS PASSED! 100% OK <<<")

if __name__ == "__main__":
    asyncio.run(run_tests())
