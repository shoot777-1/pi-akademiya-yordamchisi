import asyncio
from unittest.mock import MagicMock, AsyncMock
import bot
from config import ADMIN_ID

def make_mock_update(user_id, chat_type, text, reply_to_user=None):
    update = MagicMock()
    user = MagicMock()
    user.id = user_id
    user.username = "shaxboz_salomov" if user_id == ADMIN_ID else "anvar_python"
    user.first_name = "Shaxboz" if user_id == ADMIN_ID else "Anvar"
    user.is_bot = False

    chat = MagicMock()
    chat.id = -1001234567890
    chat.type = chat_type

    message = MagicMock()
    message.text = text
    message.from_user = user
    message.chat = chat
    message.message_thread_id = None
    message.reply_text = AsyncMock()

    if reply_to_user:
        replied_msg = MagicMock()
        replied_msg.from_user = reply_to_user
        replied_msg.message_id = 999
        replied_msg.text = "10:00 ga yuqmi dars"
        replied_msg.message_thread_id = None
        message.reply_to_message = replied_msg
    else:
        message.reply_to_message = None

    update.effective_user = user
    update.effective_chat = chat
    update.message = message
    return update

async def run_tests():
    print("=== TESTING TEACHER-STUDENT INTERACTION SILENCE ===")
    mock_bot = MagicMock()
    mock_bot.id = 777777
    mock_bot.username = "pi_yordamchi_bot"
    mock_context = MagicMock()
    mock_context.bot = mock_bot

    student_user = MagicMock()
    student_user.id = 555555
    student_user.username = "anvar_python"
    student_user.is_bot = False

    # Scenario 1: Teacher says "senga javob bermaydi anvar" in group chat (addressing Anvar by name)
    u1 = make_mock_update(ADMIN_ID, "supergroup", "senga javob bermaydi anvar")
    is_talking1 = bot.is_admin_talking_to_student(u1.message, u1.message.text)
    assert is_talking1 == True, "Should detect talking to student Anvar"
    direct1 = bot.direct_request(u1.message, u1.effective_chat, mock_bot, u1.message.text)
    assert direct1 == False, "'senga' must not trigger direct_request!"
    handled1 = await bot.handle_admin_natural_query(u1, mock_context, u1.message.text)
    assert handled1 == False, "Bot must not answer teacher talking to student!"
    ans1 = bot.should_answer(u1, u1.message.text, direct1)
    assert ans1 == False, "should_answer must be False for teacher in group without direct tag"
    print("[TEST 1 PASSED] 'senga javob bermaydi anvar' -> Bot is completely silent!")

    # Scenario 2: Teacher replies to student: "dars jadvalli deb so'rasen senikini ko'rsatadi"
    u2 = make_mock_update(ADMIN_ID, "supergroup", "dars jadvalli deb so'rasen senikini ko'rsatadi", reply_to_user=student_user)
    is_talking2 = bot.is_admin_talking_to_student(u2.message, u2.message.text)
    assert is_talking2 == True, "Reply to human is talking to student"
    direct2 = bot.direct_request(u2.message, u2.effective_chat, mock_bot, u2.message.text)
    assert direct2 == False, "Reply to student is not direct request to bot"
    handled2 = await bot.handle_admin_natural_query(u2, mock_context, u2.message.text)
    assert handled2 == False, "Bot must not parse 'jadval' as command when replying to student!"
    ans2 = bot.should_answer(u2, u2.message.text, direct2)
    assert ans2 == False, "Bot must not answer!"
    print("[TEST 2 PASSED] 'dars jadvalli deb so'rasen senikini ko'rsatadi' (reply to student) -> Bot is completely silent!")

    # Scenario 3: Teacher directly asks bot about student's schedule: "anvar dars jadvali"
    u3 = make_mock_update(ADMIN_ID, "supergroup", "anvar dars jadvali")
    is_talking3 = bot.is_admin_talking_to_student(u3.message, u3.message.text)
    assert is_talking3 == False, "Explicit schedule query is NOT talking to student, it is inquiry"
    handled3 = await bot.handle_admin_natural_query(u3, mock_context, u3.message.text)
    assert handled3 == True, "Bot MUST handle teacher query 'anvar dars jadvali'!"
    print("[TEST 3 PASSED] 'anvar dars jadvali' -> Handled by bot as schedule query!")

    # Scenario 4: Teacher asks bot: "kimlar savol berdi"
    u4 = make_mock_update(ADMIN_ID, "supergroup", "kimlar savol berdi")
    handled4 = await bot.handle_admin_natural_query(u4, mock_context, u4.message.text)
    assert handled4 == True, "Bot MUST answer 'kimlar savol berdi'!"
    print("[TEST 4 PASSED] 'kimlar savol berdi' -> Handled by bot correctly!")

    print("\n>>> ALL TEACHER-STUDENT SCENARIO TESTS PASSED SUCCESSFULLY! [OK] <<<")

if __name__ == "__main__":
    asyncio.run(run_tests())
