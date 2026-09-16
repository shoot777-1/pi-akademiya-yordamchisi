import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import closing
import bot
import member_service
from database import get_connection, add_student_xp, get_student_gamification

async def run_tests():
    print("=== TESTING RELIABLE PROFILE ID BINDING AND ANTI-IMPERSONATION ===")

    with closing(get_connection()) as conn, conn:
        # Create test students
        conn.execute("DELETE FROM students WHERE id IN (9001, 9002)")
        conn.execute("DELETE FROM student_gamification WHERE student_id IN (9001, 9002)")
        conn.execute("DELETE FROM daily_lessons WHERE student_name IN ('Sinovchi Aliyev', 'Sinovchi Karimov')")

        # 1. Two students with same first name "Sinovchi"
        conn.execute("INSERT INTO students (id, name, course_name, due_day, telegram_id, active) VALUES (9001, 'Sinovchi Aliyev', 'Python dasturlash', 10, 111111, 1)")
        conn.execute("INSERT INTO students (id, name, course_name, due_day, telegram_id, active) VALUES (9002, 'Sinovchi Karimov', 'Robototexnika', 15, NULL, 1)")
        
        # Add gamification history for Sinovchi Aliyev
        conn.execute("INSERT INTO student_gamification (student_id, student_name, xp, level, title, tasks_solved, questions_asked) VALUES (9001, 'Sinovchi Aliyev', 150, 2, 'Python Dev 🐍', 6, 2)")
        
        # Add daily lessons
        conn.execute("INSERT INTO daily_lessons (month_name, day_number, student_name, course_name, lesson_time, lesson_date, cancelled) VALUES ('sentabr', 14, 'Sinovchi Aliyev', 'Python dasturlash', '14:00', '2026-09-14', 0)")
        conn.execute("INSERT INTO daily_lessons (month_name, day_number, student_name, course_name, lesson_time, lesson_date, cancelled) VALUES ('sentabr', 14, 'Sinovchi Karimov', 'Robototexnika', '16:00', '2026-09-14', 0)")

    # ----------------------------------------------------
    # TEST 1: Telegram ismini almashtirsa ham tarixi saqlanishi
    # ----------------------------------------------------
    # O'quvchi Telegramdagi ismini "Sinovchi" dan "Hacker 999" ga o'zgartirdi
    changed_user = MagicMock()
    changed_user.id = 111111
    changed_user.first_name = "Hacker 999"
    changed_user.last_name = "Anonim"
    changed_user.username = "super_unknown_coder"

    # Bot uni ismiga qarab emas, ishonchli Telegram ID si orqali aniqlaydi:
    st = bot.find_student_by_user(changed_user)
    assert st is not None
    assert st["id"] == 9001
    assert st["name"] == "Sinovchi Aliyev"

    # Tarixi (XP va ballari) to'liq saqlangan:
    g = get_student_gamification(student_id=st["id"])
    assert g["xp"] == 150
    assert g["tasks_solved"] == 6
    assert "Python Dev" in g["title"]
    print("[TEST 1] Telegram display name change does NOT break student profile or history: OK")

    # ----------------------------------------------------
    # TEST 2: Bir xil ismli ikki odam bo'lsa, bot birinchisini tanlab ketmasligi
    # ----------------------------------------------------
    matches = bot.find_matching_students("Sinovchi")
    assert len(matches) == 2
    match_ids = {m["id"] for m in matches}
    assert match_ids == {9001, 9002}

    # find_student_by_user bir xil ismli ikki kishi bo'lganda birinchisini tanlab ketmasdan None qaytaradi
    single_match = bot.find_student_by_user(None, "Sinovchi")
    assert single_match is None # Birinchisini tanlab ketmadi!

    # Admin "Sinovchini dars jadvali" deb so'raganda bot adashib birinchisini chiqarmasdan, ikkalasining ID sini ko'rsatib tanlashni so'raydi
    admin_update = MagicMock()
    admin_msg = AsyncMock()
    admin_msg.text = "Sinovchini dars jadvali"
    admin_update.message = admin_msg
    admin_update.effective_chat = MagicMock(type="supergroup", id=-1003865779918)
    admin_update.effective_user = MagicMock(id=bot.ADMIN_ID)

    mock_context = MagicMock()
    handled = await bot.handle_admin_natural_query(admin_update, mock_context, "Sinovchini dars jadvali")
    assert handled == True
    admin_msg.reply_text.assert_awaited()
    sent_text = admin_msg.reply_text.await_args[0][0]
    assert "bir nechta o'quvchi topildi" in sent_text.lower()
    assert "9001" in sent_text
    assert "9002" in sent_text
    print("[TEST 2] Duplicate name does NOT pick the first one blindly, shows ID disambiguation: OK")

    # ----------------------------------------------------
    # TEST 3: Aniq ID orqali so'ralganda to'g'ri o'quvchini topish
    # ----------------------------------------------------
    id_matches = bot.find_matching_students("ID 9002")
    assert len(id_matches) == 1
    assert id_matches[0]["id"] == 9002
    assert id_matches[0]["name"] == "Sinovchi Karimov"

    admin_msg.reset_mock()
    handled = await bot.handle_admin_natural_query(admin_update, mock_context, "ID 9002 dars jadvali")
    assert handled == True
    admin_msg.reply_text.assert_awaited()
    sent_sched = admin_msg.reply_text.await_args[0][0]
    assert "Sinovchi Karimov" in sent_sched
    assert "Robototexnika" in sent_sched
    print("[TEST 3] Explicit ID lookup (ID 9002) finds exact student accurately: OK")

    # ----------------------------------------------------
    # TEST 4: Boshqa foydalanuvchi ismini o'zgartirib birovning ma'lumotini o'ziniki qilib ololmasligi
    # ----------------------------------------------------
    # Begona foydalanuvchi Telegram ismini "Sinovchi Aliyev" deb qo'ydi
    imposter_user = MagicMock()
    imposter_user.id = 888888 # Begona Telegram ID
    imposter_user.first_name = "Sinovchi"
    imposter_user.last_name = "Aliyev"

    # Bot uni Sinovchi Aliyev deb qabul qilmaydi!
    imposter_st = bot.find_student_by_user(imposter_user)
    assert imposter_st is None # Begonaga kirish berilmaydi!

    # Begona user /jadval yuborsa, unga o'zining TG ID si ko'rsatiladi va rad etiladi
    imposter_update = MagicMock()
    imposter_msg = AsyncMock()
    imposter_msg.reply_to_message = None
    imposter_update.message = imposter_msg
    imposter_update.effective_chat = MagicMock(type="private", id=888888)
    imposter_update.effective_user = imposter_user
    imposter_context = MagicMock()
    imposter_context.args = []

    await bot.jadval_command(imposter_update, imposter_context)
    imposter_msg.reply_text.assert_awaited()
    reject_text = imposter_msg.reply_text.await_args[0][0]
    assert "Profilingiz tasdiqlanmagan" in reject_text
    assert "888888" in reject_text # Unikal TG ID ko'rsatiladi
    print("[TEST 4] Impersonation blocked: unlinked user cannot steal another student's data: OK")

    # ----------------------------------------------------
    # TEST 5: Profilni ID orqali bog'lash (Admin natural link: bog'la 888888 9002)
    # ----------------------------------------------------
    admin_link_update = MagicMock()
    admin_link_msg = AsyncMock()
    admin_link_msg.reply_to_message = None
    admin_link_update.message = admin_link_msg
    admin_link_update.effective_chat = MagicMock(type="supergroup", id=-1003865779918)
    admin_link_update.effective_user = MagicMock(id=bot.ADMIN_ID)

    link_handled = await bot.handle_admin_natural_query(admin_link_update, mock_context, "bog'la 888888 9002")
    assert link_handled == True
    admin_link_msg.reply_text.assert_awaited()
    link_confirm_text = admin_link_msg.reply_text.await_args[0][0]
    assert "Muvaffaqiyatli bog'landi" in link_confirm_text
    assert "Sinovchi Karimov" in link_confirm_text
    assert "888888" in link_confirm_text

    # Endi 888888 ID li o'quvchi o'z profilini ko'ra oladi:
    linked_now = bot.find_student_by_user(imposter_user)
    assert linked_now is not None
    assert linked_now["id"] == 9002
    assert linked_now["name"] == "Sinovchi Karimov"
    print("[TEST 5] Admin natural profile linking via ID (bog'la 888888 9002): OK")

    # Clean up test rows
    with closing(get_connection()) as conn, conn:
        conn.execute("DELETE FROM students WHERE id IN (9001, 9002)")
        conn.execute("DELETE FROM student_gamification WHERE student_id IN (9001, 9002)")
        conn.execute("DELETE FROM daily_lessons WHERE student_name IN ('Sinovchi Aliyev', 'Sinovchi Karimov')")

    print("\nALL 5 RELIABLE PROFILE ID BINDING TESTS PASSED PERFECTLY! 100% OK")

if __name__ == "__main__":
    asyncio.run(run_tests())
