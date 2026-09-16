import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
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
    print("=== TESTING EXACT USER QUERIES ===")
    mock_bot = MagicMock()
    mock_bot.id = 777777
    mock_bot.username = "pi_yordamchi_bot"
    mock_context = MagicMock()
    mock_context.bot = mock_bot

    # Test 1: "anvarni dars jadvalini ko'rsat"
    u1 = make_mock_update(ADMIN_ID, "supergroup", "anvarni dars jadvalini ko'rsat")
    handled1 = await bot.handle_admin_natural_query(u1, mock_context, u1.message.text)
    assert handled1 == True, "Should handle 'anvarni dars jadvalini ko'rsat'"
    print("[TEST 1 PASSED] 'anvarni dars jadvalini ko'rsat' -> Handled!")

    # Test 2: "anvarni dars jadvalini ayt"
    u2 = make_mock_update(ADMIN_ID, "supergroup", "anvarni dars jadvalini ayt")
    handled2 = await bot.handle_admin_natural_query(u2, mock_context, u2.message.text)
    assert handled2 == True, "Should handle 'anvarni dars jadvalini ayt'"
    print("[TEST 2 PASSED] 'anvarni dars jadvalini ayt' -> Handled!")

    # Test 3: "anvarni o'zlashtirishini ko'rsat"
    u3 = make_mock_update(ADMIN_ID, "supergroup", "anvarni o'zlashtirishini ko'rsat")
    handled3 = await bot.handle_admin_natural_query(u3, mock_context, u3.message.text)
    assert handled3 == True, "Should handle 'anvarni o'zlashtirishini ko'rsat'"
    print("[TEST 3 PASSED] 'anvarni o'zlashtirishini ko'rsat' -> Handled!")

    # Test 4: "anvarni o'zlashtirishini ayt"
    u4 = make_mock_update(ADMIN_ID, "supergroup", "anvarni o'zlashtirishini ayt")
    handled4 = await bot.handle_admin_natural_query(u4, mock_context, u4.message.text)
    assert handled4 == True, "Should handle 'anvarni o'zlashtirishini ayt'"
    print("[TEST 4 PASSED] 'anvarni o'zlashtirishini ayt' -> Handled!")

    # Test 5: "anvarni dars jadvalini o'zlashtirishini ko'rsat ayt"
    u5 = make_mock_update(ADMIN_ID, "supergroup", "anvarni dars jadvalini o'zlashtirishini ko'rsat ayt")
    handled5 = await bot.handle_admin_natural_query(u5, mock_context, u5.message.text)
    assert handled5 == True, "Should handle combined 'anvarni dars jadvalini o'zlashtirishini ko'rsat ayt'"
    print("[TEST 5 PASSED] 'anvarni dars jadvalini o'zlashtirishini ko'rsat ayt' -> Handled!")

    # Test 6: Silence when talking to student in group: "senga javob bermaydi anvar"
    u6 = make_mock_update(ADMIN_ID, "supergroup", "senga javob bermaydi anvar")
    is_talking6 = bot.is_admin_talking_to_student(u6.message, u6.message.text)
    assert is_talking6 == True, "Should detect talking to student"
    handled6 = await bot.handle_admin_natural_query(u6, mock_context, u6.message.text)
    assert handled6 == False, "Bot must NOT answer when teacher talks to student!"
    print("[TEST 6 PASSED] 'senga javob bermaydi anvar' -> Silent!")

    # Test 7: Silence when replying to student in group: "dars jadvalli deb so'rasen senikini ko'rsatadi"
    student_user = MagicMock()
    student_user.id = 555555
    student_user.is_bot = False
    u7 = make_mock_update(ADMIN_ID, "supergroup", "dars jadvalli deb so'rasen senikini ko'rsatadi", reply_to_user=student_user)
    is_talking7 = bot.is_admin_talking_to_student(u7.message, u7.message.text)
    assert is_talking7 == True, "Should detect reply to student"
    handled7 = await bot.handle_admin_natural_query(u7, mock_context, u7.message.text)
    assert handled7 == False, "Bot must NOT answer when teacher replies to student!"
    print("[TEST 7 PASSED] 'dars jadvalli deb so'rasen senikini ko'rsatadi' (reply) -> Silent!")

    print("\n>>> ALL 7 TESTS PASSED PERFECTLY! [OK] <<<")

if __name__ == "__main__":
    asyncio.run(run_tests())
