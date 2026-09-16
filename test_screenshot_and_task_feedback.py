import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import bot
import config
import ai_service

async def run_tests():
    print("=== TESTING SCREENSHOT, TASK AND PEDAGOGICAL FEEDBACK LOGIC ===")

    # 1. Test is_task_request
    assert bot.is_task_request("Pythonda sikllar bo'yicha masala ber") == True
    assert bot.is_task_request("Excelda VLOOKUP bo'yicha mashq ber") == True
    assert bot.is_task_request("Salom yaxshimisiz") == False
    print("[TEST 1] is_task_request detection: OK")

    # 2. Test is_task_submission
    assert bot.is_task_submission("Skrinshotni tekshirib bering") == True
    assert bot.is_task_submission("Kodim to'g'rimi?") == True
    assert bot.is_task_submission("Natija chiqdi, to'g'ri ekanmi?") == True
    assert bot.is_task_submission("Koddagi xatosi bormi?") == True
    assert bot.is_task_submission("Topshiriqni ishladim") == True
    assert bot.is_task_submission("Bugun havo yaxshi") == False
    print("[TEST 2] is_task_submission detection: OK")

    # 3. Test should_answer logic with photo and submissions
    mock_chat = MagicMock(type="supergroup", id=-1003865779918)
    mock_user = MagicMock(id=123456, first_name="Olim")
    mock_update = MagicMock()
    mock_update.effective_chat = mock_chat
    mock_update.effective_user = mock_user
    mock_update.message = MagicMock(reply_to_message=None)

    # Admin online holatida ham o'quvchi skrinshot tashlasa yoki masala/submission bo'lsa bot javob berishi kerak:
    with patch("bot.is_admin_online", return_value=True):
        # Oddiy gap - javob bermasligi kerak (ustoz onlayn)
        assert bot.should_answer(mock_update, "ha shunday", direct=False, photo=False) == False
        # Skrinshot (photo=True) - javob berishi kerak!
        assert bot.should_answer(mock_update, "to'g'rimi?", direct=False, photo=True) == True
        # Masala so'rash - javob berishi kerak!
        assert bot.should_answer(mock_update, "bitta topshiriq bering", direct=False, photo=False) == True
        # Yechim tekshirish - javob berishi kerak!
        assert bot.should_answer(mock_update, "kodimni tekshirib bering", direct=False, photo=False) == True
    print("[TEST 3] should_answer with photo and task submissions (even when teacher is online): OK")

    # 4. Test handle_photo with INCORRECT solution (No [VAZIFA_TOGRI], 0 XP, error explanation)
    mock_photo_update = MagicMock()
    mock_photo_update.effective_chat = mock_chat
    mock_photo_update.effective_user = mock_user
    mock_photo_msg = AsyncMock()
    mock_photo_msg.caption = "Skrinshotni tekshirib bering"
    mock_photo_msg.photo = [MagicMock(file_id="photo_123")]
    mock_photo_msg.message_id = 991
    mock_photo_msg.reply_to_message = None
    mock_photo_update.message = mock_photo_msg

    mock_status_msg = AsyncMock()
    mock_photo_msg.reply_text.return_value = mock_status_msg

    mock_tg_file = AsyncMock()
    mock_context = MagicMock()
    mock_bot = AsyncMock()
    mock_bot.username = "pibot"
    mock_bot.id = 99999
    mock_bot.get_me.return_value = MagicMock(username="pibot")
    mock_bot.get_file.return_value = mock_tg_file
    mock_context.bot = mock_bot

    fake_student = {"id": 1, "name": "Murod", "course_name": "Python dasturlash"}

    # Noto'g'ri yechim qaytargan Vision AI javobi
    wrong_ai_reply = (
        "Skrinshotdagi kodingizni ko'rib chiqdim.\n"
        "3-qatorda IndexError yuz bergan, chunki ro'yxat indekslari 0 dan boshlanadi.\n"
        "Buni to'g'rilash uchun sikl chegarasini qayta ko'rib chiqing.\n"
        "Kodingizni to'g'rilab, yangi skrinshot yuboring, yana tekshirib beraman!"
    )

    with patch("bot.find_student_by_user", return_value=fake_student), \
         patch("bot.analyze_image_with_ai", AsyncMock(return_value=wrong_ai_reply)), \
         patch("bot.add_student_xp") as mock_add_xp, \
         patch("bot.update_pinned_leaderboard") as mock_update_pin, \
         patch("bot.study_context.save_photo"), \
         patch("bot.study_context.link_message"), \
         patch("bot.log_student_activity"):

        await bot.handle_photo(mock_photo_update, mock_context)

        # Status xabarida xatolik tushuntirishi ko'rsatilgan
        mock_status_msg.edit_text.assert_awaited_once()
        first_call_text = mock_status_msg.edit_text.await_args[0][0]
        assert "IndexError" in first_call_text
        # Noto'g'ri bo'lgani uchun XP berilmagan!
        mock_add_xp.assert_not_called()
        mock_update_pin.assert_not_called()

    print("[TEST 4] handle_photo with INCORRECT solution: explained error, NO ready code given, 0 XP awarded: OK")

    # 5. Test handle_photo with CORRECT solution ([VAZIFA_TOGRI], +25 XP awarded, leaderboard updated)
    correct_ai_reply = (
        "[VAZIFA_TOGRI]\n"
        "Ajoyib! Skrinshotdagi kodingiz va konsoldagi natija 100% to'g'ri ishladi!\n"
        "Barcha shartlar to'liq bajarilgan, ofarin!"
    )

    mock_status_msg.reset_mock()
    mock_xp_result = {"new_xp": 25, "level": 1, "title": "Junior Coder 🚀", "level_up": False}

    with patch("bot.find_student_by_user", return_value=fake_student), \
         patch("bot.analyze_image_with_ai", AsyncMock(return_value=correct_ai_reply)), \
         patch("bot.add_student_xp", return_value=mock_xp_result) as mock_add_xp, \
         patch("bot.update_pinned_leaderboard", AsyncMock()) as mock_update_pin, \
         patch("bot.study_context.save_photo"), \
         patch("bot.study_context.link_message"), \
         patch("bot.log_student_activity"):

        await bot.handle_photo(mock_photo_update, mock_context)

        mock_status_msg.edit_text.assert_awaited_once()
        first_call_text = mock_status_msg.edit_text.await_args[0][0]
        # [VAZIFA_TOGRI] tegi foydalanuvchiga ko'rsatilmasdan tozalangan bo'lishi kerak
        assert "[VAZIFA_TOGRI]" not in first_call_text
        # +25 XP banner qo'shilgan
        assert "+25 XP" in first_call_text
        assert "Junior Coder" in first_call_text
        # add_student_xp chaqirilgan
        mock_add_xp.assert_called_once_with(1, "Murod", 25, is_task=True, course_name="Python dasturlash")

    print("[TEST 5] handle_photo with CORRECT solution: [VAZIFA_TOGRI] detected, +25 XP awarded: OK")

    # 6. Test Prompts Strictness (No direct code rule & continuous checking)
    assert "HECH QACHON TO'G'RIDAN-TO'G'RI TAYYOR KODNI YOKI TAYYOR FORMULANI YOZIB BERMANG" in config.AI_SYSTEM_PROMPT
    assert "[VAZIFA_TOGRI]" in config.AI_SYSTEM_PROMPT
    assert "HECH QACHON TO'G'RIDAN-TO'G'RI TAYYOR KODNI YOKI TAYYOR FORMULANI YOZIB BERMANG" in ai_service.AI_DECISION_PROMPT
    assert "[VAZIFA_TOGRI]" in ai_service.AI_DECISION_PROMPT
    print("[TEST 6] AI system prompts enforce strict pedagogical no-code-leak and XP rules: OK")

    print("\nALL SCREENSHOT, TASK AND GAMIFICATION TESTS PASSED SUCCESSFULLY! 100% OK")

if __name__ == "__main__":
    asyncio.run(run_tests())
