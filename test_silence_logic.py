import asyncio
import datetime
from unittest.mock import MagicMock
import bot
from config import ADMIN_ID

def test_silence_and_answering_rules():
    bot.set_setting("admin_manual_status", "auto")
    print("--- TESTING SILENCE & ANSWERING RULES ---")

    # Mock Bot, Chat, User, Message, Update
    mock_bot = MagicMock()
    mock_bot.id = 999999
    mock_bot.username = "pi_academy_bot"

    group_chat = MagicMock()
    group_chat.id = -100123456
    group_chat.type = "supergroup"

    private_chat = MagicMock()
    private_chat.id = ADMIN_ID
    private_chat.type = "private"

    admin_user = MagicMock()
    admin_user.id = ADMIN_ID
    admin_user.first_name = "Shaxboz"

    student_user = MagicMock()
    student_user.id = 11223344
    student_user.first_name = "Murod"

    # Helper to build Update
    def make_update(user, chat, text, reply_to_user=None):
        update = MagicMock()
        update.effective_user = user
        update.effective_chat = chat
        message = MagicMock()
        message.text = text
        message.from_user = user
        if reply_to_user:
            replied = MagicMock()
            replied.from_user = reply_to_user
            message.reply_to_message = replied
        else:
            message.reply_to_message = None
        update.message = message
        return update

    # 1. Casual chat filter
    assert bot.is_casual_group_chat("Salom") == True, "Salom should be casual"
    assert bot.is_casual_group_chat("Assalomu alaykum") == True, "Greeting should be casual"
    assert bot.is_casual_group_chat("Qalesizlar") == True, "Small talk should be casual"
    assert bot.is_casual_group_chat("Rahmat ustoz") == True, "Thanks should be casual"
    assert bot.is_casual_group_chat("Ha, keldim") == True, "Short check-in should be casual"
    assert bot.is_casual_group_chat("Python da loop qanday ishlaydi?") == False, "Academic question is not casual"

    # 2. Teacher address filter
    assert bot.is_addressed_to_teacher("Ustoz, vazifani qildim") == True, "Addressed to teacher"
    assert bot.is_addressed_to_teacher("Assalomu alaykum ustozim") == True, "Addressed to teacher"
    assert bot.is_addressed_to_teacher("Shaxboz aka, dars qachon?") == True, "Addressed to teacher"
    assert bot.is_addressed_to_teacher("Python da kod yozdim") == False, "General question"

    # 3. Admin typing in group:
    # A) Admin chatting/answering students (NOT calling bot)
    u_admin_reply = make_update(admin_user, group_chat, "Ha, to'g'ri qildingiz, =VLOOKUP(...) ishlatish kerak")
    direct = bot.direct_request(u_admin_reply.message, group_chat, mock_bot, u_admin_reply.message.text)
    assert direct == False, "Admin reply without bot tag is NOT direct"
    ans = bot.should_answer(u_admin_reply, u_admin_reply.message.text, direct)
    assert ans == False, "Bot MUST NOT answer when Admin is answering students in group!"

    # B) Admin answering with casual text
    u_admin_chat = make_update(admin_user, group_chat, "Ertaga soat 15:00 da hammangiz keling")
    direct = bot.direct_request(u_admin_chat.message, group_chat, mock_bot, u_admin_chat.message.text)
    ans = bot.should_answer(u_admin_chat, u_admin_chat.message.text, direct)
    assert ans == False, "Bot MUST NOT answer when Admin gives instructions in group!"

    # C) Admin mentions a student by @username
    u_admin_mention = make_update(admin_user, group_chat, "@murod vazifangni tashla")
    direct = bot.direct_request(u_admin_mention.message, group_chat, mock_bot, u_admin_mention.message.text)
    ans = bot.should_answer(u_admin_mention, u_admin_mention.message.text, direct)
    assert ans == False, "Bot MUST NOT answer when Admin mentions student @username in group!"

    # D) Admin directly invokes bot in group: "Pi, ..."
    u_admin_pi = make_update(admin_user, group_chat, "Pi, Python decorator nima?")
    direct = bot.direct_request(u_admin_pi.message, group_chat, mock_bot, u_admin_pi.message.text)
    assert direct == True, "Admin saying Pi IS direct"
    ans = bot.should_answer(u_admin_pi, u_admin_pi.message.text, direct)
    assert ans == True, "Bot should answer admin when directly asked!"

    # 4. Student in group:
    # A) Student replies to Admin's message
    u_st_reply_admin = make_update(student_user, group_chat, "Ustoz, men bu kodni tushunmadim", reply_to_user=admin_user)
    direct = bot.direct_request(u_st_reply_admin.message, group_chat, mock_bot, u_st_reply_admin.message.text)
    ans = bot.should_answer(u_st_reply_admin, u_st_reply_admin.message.text, direct)
    assert ans == False, "Bot MUST NOT answer when Student replies to Teacher!"

    # B) Student addresses teacher by name/title
    u_st_ask_teacher = make_update(student_user, group_chat, "Ustoz, 5-misolda xatolik berdi")
    direct = bot.direct_request(u_st_ask_teacher.message, group_chat, mock_bot, u_st_ask_teacher.message.text)
    ans = bot.should_answer(u_st_ask_teacher, u_st_ask_teacher.message.text, direct)
    assert ans == False, "Bot MUST NOT answer when Student addresses Ustoz!"

    # C) Student sends casual chat
    u_st_casual = make_update(student_user, group_chat, "Salom hammaga, bugun dars bormi?")
    # Wait, 'bugun dars bormi' is schedule request, let's test purely casual:
    u_st_pure_casual = make_update(student_user, group_chat, "Assalomu alaykum, yaxshimisizlar?")
    direct = bot.direct_request(u_st_pure_casual.message, group_chat, mock_bot, u_st_pure_casual.message.text)
    ans = bot.should_answer(u_st_pure_casual, u_st_pure_casual.message.text, direct)
    assert ans == False, "Bot MUST NOT answer pure casual small talk in group!"

    # D) Teacher is online (recently wrote in group):
    bot.last_admin_activity = bot.tashkent_now() # Active right now!
    assert bot.is_admin_online() == True, "Admin is online because of recent activity"

    u_st_task = make_update(student_user, group_chat, "Python da dict ga qanday yangi element qo'shiladi?")
    direct = bot.direct_request(u_st_task.message, group_chat, mock_bot, u_st_task.message.text)
    ans = bot.should_answer(u_st_task, u_st_task.message.text, direct)
    assert ans == False, "Bot MUST NOT answer in group when Teacher is ONLINE!"

    # E) Student explicitly calls bot: "Pi, ..."
    u_st_call_pi = make_update(student_user, group_chat, "Pi, Python da dict ga qanday element qo'shiladi?")
    direct = bot.direct_request(u_st_call_pi.message, group_chat, mock_bot, u_st_call_pi.message.text)
    ans = bot.should_answer(u_st_call_pi, u_st_call_pi.message.text, direct)
    assert ans == True, "Bot SHOULD answer when Student explicitly calls Pi!"

    # F) Teacher is offline (>10 min ago) and student asks academic question:
    bot.last_admin_activity = bot.tashkent_now() - datetime.timedelta(minutes=15)
    assert bot.is_admin_online() == False, "Admin is offline after 15 mins"
    ans = bot.should_answer(u_st_task, u_st_task.message.text, direct=False)
    assert ans == True, "Bot should help with academic question when teacher is offline!"

    print("ALL 10 SILENCE AND ANSWERING TESTS PASSED PERFECTLY! 100% OK")

if __name__ == "__main__":
    test_silence_and_answering_rules()
