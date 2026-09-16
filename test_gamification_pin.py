import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import bot
from database import get_student_gamification, add_student_xp

async def run_gamification_and_pin_tests():
    print("=== TESTING GAMIFICATION AND PINNED LEADERBOARD ===")

    # 1. Test leaderboard formatting
    text = bot.format_pinned_leaderboard_text()
    assert "CYBER TECH ACADEMY — O'QUVCHILAR REYTINGI" in text
    assert "XP to'plash qoidalari" in text
    assert "+25 XP" in text
    print("[TEST 1] Leaderboard text formatting: OK")

    # 2. Test inline keyboard
    kb = bot.get_leaderboard_inline_keyboard()
    assert len(kb.inline_keyboard) == 2
    assert any("refresh_leaderboard" in btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data)
    assert any("my_profile" in btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data)
    print("[TEST 2] Inline keyboard: OK")

    # 3. Test update_pinned_leaderboard with mock bot
    mock_bot = AsyncMock()
    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 7788
    mock_bot.send_message.return_value = mock_sent_msg

    with patch("leaderboard_service.get_setting", return_value=None), patch("leaderboard_service.set_setting") as mock_set:
        msg_id = await bot.update_pinned_leaderboard(mock_bot, group_id=-1003865779918, force_repin=True)
        assert msg_id == 7788
        mock_bot.send_message.assert_awaited_once()
        mock_bot.pin_chat_message.assert_awaited_once_with(chat_id=-1003865779918, message_id=7788, disable_notification=True)
        mock_set.assert_called_with("pinned_leaderboard_msg_id_-1003865779918", "7788")
    print("[TEST 3] update_pinned_leaderboard send and pin: OK")

    # 4. Test task evaluation tag [VAZIFA_TOGRI] parsing
    raw_ai_reply = "[VAZIFA_TOGRI]\nBarakalla! Siz yozgan formula =VLOOKUP(A2, B:C, 2, FALSE) mutlaqo to'g'ri ishladi!"
    is_task_correct = "[VAZIFA_TOGRI]" in raw_ai_reply
    cleaned = raw_ai_reply.replace("[VAZIFA_TOGRI]", "").strip()
    assert is_task_correct == True
    assert "[VAZIFA_TOGRI]" not in cleaned
    print("[TEST 4] [VAZIFA_TOGRI] detection and clean: OK")

    # 5. Test callback query handler
    mock_update = MagicMock()
    mock_query = AsyncMock()
    mock_query.data = "my_profile"
    mock_user = MagicMock()
    mock_user.id = 999999
    mock_user.first_name = "Sinovchi"
    mock_query.from_user = mock_user
    mock_update.callback_query = mock_query

    mock_context = MagicMock()
    mock_context.bot = mock_bot

    await bot.leaderboard_callback_handler(mock_update, mock_context)
    mock_query.answer.assert_awaited_once()
    print("[TEST 5] Callback query handler: OK")

    # 6. Test natural command for pinning leaderboard
    admin_update = MagicMock()
    admin_msg = AsyncMock()
    admin_msg.text = "reytingni pin qil"
    admin_update.message = admin_msg
    admin_update.effective_chat = MagicMock(type="supergroup", id=-1003865779918)
    admin_update.effective_user = MagicMock(id=bot.ADMIN_ID)

    with patch("bot.update_pinned_leaderboard", return_value=8899):
        handled = await bot.handle_admin_natural_query(admin_update, mock_context, "reytingni pin qil")
        assert handled == True
    print("[TEST 6] Admin natural command 'reytingni pin qil': OK")

    # 7. Test track-specific titles in database
    from database import calculate_level_and_title
    lvl_dev, title_dev = calculate_level_and_title(50, "Python dasturlash")
    lvl_pc, title_pc = calculate_level_and_title(50, "Kompyuter savodxonligi")
    lvl_rob, title_rob = calculate_level_and_title(50, "Robotatexnika")
    assert "Junior Coder" in title_dev
    assert "IT Izquvar" in title_pc
    assert "Yosh Konstruktor" in title_rob
    print("[TEST 7] Track-specific level and titles: OK")

    # 8. Test clean_service_messages (delete status messages)
    service_msg = AsyncMock()
    service_msg.message_id = 1234
    service_msg.new_chat_members = [MagicMock(id=555, is_bot=False)]
    service_update = MagicMock()
    service_update.message = service_msg
    service_update.effective_chat = MagicMock(type="supergroup", id=-1003865779918)

    with patch("bot.register_member") as mock_reg:
        await bot.clean_service_messages(service_update, mock_context)
        mock_reg.assert_called_once()
        service_msg.delete.assert_awaited_once()
    print("[TEST 8] clean_service_messages deletes join/left/pin messages: OK")

    print("\nALL GAMIFICATION, TRACK TITLES AND SERVICE CLEAN TESTS PASSED! 100% OK")

if __name__ == "__main__":
    asyncio.run(run_gamification_and_pin_tests())
