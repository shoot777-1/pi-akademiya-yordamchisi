import datetime
from unittest.mock import MagicMock
import bot
from config import ADMIN_ID

def test_modes():
    print("=== TESTING ADMIN ONLINE/OFFLINE MODES & TASK/TRANSLATION EXCEPTIONS ===")

    mock_bot = MagicMock()
    mock_bot.id = 999999
    mock_bot.username = "pi_academy_bot"

    group_chat = MagicMock()
    group_chat.id = -100123456
    group_chat.type = "supergroup"

    admin_user = MagicMock()
    admin_user.id = ADMIN_ID

    student_user = MagicMock()
    student_user.id = 556677

    def make_update(text):
        update = MagicMock()
        update.effective_user = student_user
        update.effective_chat = group_chat
        message = MagicMock()
        message.text = text
        message.from_user = student_user
        message.reply_to_message = None
        update.message = message
        return update

    # 1. Test helper functions
    assert bot.is_task_request("VLOOKUP bo'yicha masala ber") == True
    assert bot.is_task_request("Pythonda sikllarga bitta misol bering") == True
    assert bot.is_task_request("Topshiriq kerak ishlaylik") == True
    assert bot.is_task_request("Uyga vazifa bering") == True
    assert bot.is_task_request("Salom yaxshimisiz") == False

    assert bot.is_translation_request("Shu so'zni inglizchaga tarjima qilib ber") == True
    assert bot.is_translation_request("O'zbekchaga tarjima qil") == True
    assert bot.is_translation_request("Please translate this text") == True
    assert bot.is_translation_request("Ruschaga o'girib ber") == True
    assert bot.is_translation_request("Dars qachon bo'ladi") == False
    print("[TEST 1] Helper detectors: OK")

    # 2. SCENARIO A: Admin is ONLINE
    bot.set_setting("admin_manual_status", "auto")
    bot.last_admin_activity = bot.tashkent_now() # Active right now!
    assert bot.is_admin_online() == True

    # A1: General student question when admin is online -> Bot stays silent!
    u_gen = make_update("Kompyuterim qotib qoldi, nima qilsam bo'ladi?")
    direct = bot.direct_request(u_gen.message, group_chat, mock_bot, u_gen.message.text)
    ans = bot.should_answer(u_gen, u_gen.message.text, direct)
    assert ans == False, "Admin is online, bot should stay silent on general questions"
    print("[TEST 2] Admin online -> General question ignored: OK")

    # A2: Casual talk when admin is online -> Bot stays silent!
    u_cas = make_update("Salom hammaga")
    direct = bot.direct_request(u_cas.message, group_chat, mock_bot, u_cas.message.text)
    ans = bot.should_answer(u_cas, u_cas.message.text, direct)
    assert ans == False, "Admin is online, bot should stay silent on casual chatter"
    print("[TEST 3] Admin online -> Casual talk ignored: OK")

    # A3: Student asks for TASK when admin is online -> Bot answers!
    u_task1 = make_update("Menga Excelda VLOOKUP ga bitta amaliy masala bering")
    direct = bot.direct_request(u_task1.message, group_chat, mock_bot, u_task1.message.text)
    ans = bot.should_answer(u_task1, u_task1.message.text, direct)
    assert ans == True, "Admin is online, but student asked for TASK -> Bot MUST answer!"

    u_task2 = make_update("Pythonda sikllarga misol bering yechaylik")
    direct = bot.direct_request(u_task2.message, group_chat, mock_bot, u_task2.message.text)
    ans = bot.should_answer(u_task2, u_task2.message.text, direct)
    assert ans == True, "Admin is online, but student asked for Python task -> Bot MUST answer!"
    print("[TEST 4] Admin online -> Student asks for task -> Bot answers: OK")

    # A4: Student asks for TRANSLATION when admin is online -> Bot answers!
    u_trans = make_update("Shu xabarni inglizchaga tarjima qilib ber")
    direct = bot.direct_request(u_trans.message, group_chat, mock_bot, u_trans.message.text)
    ans = bot.should_answer(u_trans, u_trans.message.text, direct)
    assert ans == True, "Admin is online, but student asked for translation -> Bot MUST answer!"
    print("[TEST 5] Admin online -> Student asks for translation -> Bot answers: OK")

    # 3. SCENARIO B: Admin is OFFLINE
    bot.last_admin_activity = bot.tashkent_now() - datetime.timedelta(minutes=20) # Offline!
    assert bot.is_admin_online() == False

    # B1: General student question when admin is offline -> Bot IMMEDIATELY answers!
    u_gen_off = make_update("Kompyuterim qotib qoldi, qanday tozalash mumkin?")
    direct = bot.direct_request(u_gen_off.message, group_chat, mock_bot, u_gen_off.message.text)
    ans = bot.should_answer(u_gen_off, u_gen_off.message.text, direct)
    assert ans == True, "Admin is offline -> Bot MUST answer student question immediately!"

    # B2: Academic question when admin is offline -> Bot answers!
    u_acad_off = make_update("Excelda SUMIF qanday ishlaydi?")
    direct = bot.direct_request(u_acad_off.message, group_chat, mock_bot, u_acad_off.message.text)
    ans = bot.should_answer(u_acad_off, u_acad_off.message.text, direct)
    assert ans == True, "Admin is offline -> Bot answers academic question!"

    # B3: Casual small talk when admin is offline -> Bot still ignores small talk!
    u_cas_off = make_update("Salom")
    direct = bot.direct_request(u_cas_off.message, group_chat, mock_bot, u_cas_off.message.text)
    ans = bot.should_answer(u_cas_off, u_cas_off.message.text, direct)
    assert ans == False, "Admin is offline, but pure casual talk 'Salom' should still be ignored"
    print("[TEST 6] Admin offline -> General & academic questions answered immediately, casual ignored: OK")

    print("\nALL ONLINE/OFFLINE & TASK/TRANSLATION TESTS PASSED! 100% OK")

if __name__ == "__main__":
    test_modes()
