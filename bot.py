import os
import io
import re
import asyncio
import logging
import tempfile
import shutil
import time
from collections import OrderedDict, deque
from logging.handlers import RotatingFileHandler
from contextlib import suppress, closing
from operations import tashkent_now, backup_data, acquire_instance
from datetime import datetime, timedelta, date
from typing import Optional
from functools import wraps
from conversation_service import clear_history
import study_context
from book_service import send_requested_books
from member_service import (register_member, list_members, enroll_member, link_member,
                            parse_payment, find_students, apply_payment, normalize)

from telegram import (Update, BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats,
                      BotCommandScopeAllGroupChats, BotCommandScopeChat, BotCommandScopeChatMember,
                      InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Poll)
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, BASE_DIR, ADMIN_ID, OPENAI_API_KEY, OPENAI_MODEL
from database import (
    get_connection,
    set_setting,
    get_setting,
    get_all_students,
    get_lessons_for_day,
    get_lessons_for_date,
    set_payment,
    get_paid_students,
    change_lesson,
    get_students_due_for_reminder,
    mark_student_notified,
    get_student_learning_logs,
    log_student_activity,
    get_leaderboard,
    get_student_gamification,
    add_student_xp,
    create_quiz_session,
    add_quiz_question,
    get_active_quiz_session,
    get_active_quiz_sessions,
    get_quiz_session_by_id,
    get_quiz_question_by_poll,
    record_quiz_answer,
    get_quiz_session_results,
    finish_quiz_session,
    get_session_poll_message_ids,
    save_quiz_to_bank,
    get_random_quiz_from_bank,
    get_quiz_bank_stats
)
from excel_service import import_pi_academy_excel
from ai_service import ask_ai, analyze_image_with_ai
from quiz_service import generate_quiz_from_ai
from web_dashboard import start_web_dashboard

# Loglar
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# Telegram HTTP manzillarida bot tokeni bor; ularni logga chiqarmaymiz.
logging.getLogger("httpx").setLevel(logging.WARNING)

EXCEL_LOCAL_PATH = BASE_DIR / "dars jadvallari.xlsx"

# Admin oxirgi faollik vaqti (datetime)
last_admin_activity: Optional[datetime] = None

def update_admin_activity():
    """Admin guruhda xabar yozganda uning faollik vaqtini yangilash"""
    global last_admin_activity
    last_admin_activity = tashkent_now()

def is_admin_online() -> bool:
    """
    Admin hozir onlaynmi yoki yo'qmi aniqlash.
    1. Agar admin guruhda oxirgi 10 daqiqa ichida xabar yozgan bo'lsa -> Jismonan onlayn (ustoz hozir faol)
    2. Agar admin /online buyrug'ini bergan bo'lsa -> Onlayn
    3. Agar admin /offline buyrug'ini bergan bo'lsa -> Oflayn
    4. Standart avtomatik rejim: admin faol bo'lmasa -> Oflayn (bot kerakli hollarda yordam berishi mumkin)
    """
    global last_admin_activity
    manual_status = get_setting("admin_manual_status", "auto")
    if manual_status in ("online", "offline"):
        return manual_status == "online"
    if last_admin_activity is not None:
        diff_seconds = (tashkent_now() - last_admin_activity).total_seconds()
        if diff_seconds < 600:  # 10 daqiqa
            return True

    manual_status = get_setting("admin_manual_status", "auto")
    if manual_status == "online":
        return True
    if manual_status == "offline":
        return False
        
    return False

def admin_only(handler):
    @wraps(handler)
    async def wrapped(update, context):
        user = update.effective_user
        if not user or user.id != ADMIN_ID:
            if update.message:
                await update.message.reply_text("Bu amal faqat administrator uchun.")
            return
        return await handler(update, context)
    return wrapped


ADMIN_COMMANDS = [
    ("help", "Barcha buyruqlar"), ("azolar", "Telegram a'zolari"),
    ("oquvchi", "Yangi o'quvchi kartasi"), ("boglash", "Telegram IDni o'quvchiga bog'lash"),
    ("tolovlar", "Oylik to'lov holatlari"), ("tolandi", "To'lovni belgilash"),
    ("tolanmadi", "To'lovni bekor qilish"), ("darslar", "Darslarni boshqarish"),
    ("bugun", "Bugungi jadval"), ("ertaga", "Ertangi jadval"),
    ("jadval", "O'quvchi haftalik dars jadvali"),
    ("set_group", "Eslatma guruhini belgilash"), ("online", "Faqat botga murojaatlar"),
    ("offline", "Savollarga avtomatik javob"), ("auto", "Avtomatik rejim"),
    ("status", "Bot holati"), ("diagnostika", "Xato va sarf nazorati"),
    ("excel_yangilash", "Excelni qayta import qilish"),
    ("yangi_suhbat", "Suhbat xotirasini tozalash"), ("daraja", "Tushuntirish darajasi"),
]
ADMIN_HELP = """🎓 **CYBER TECH ACADEMY — ADMIN BOSHQARUVI** 🚀

Endi buyruqlarni "/" orqali emas, to'g'ridan-to'g'ri o'zbek tilida tabiiy yozib boshqarishingiz mumkin:

📊 **O'QUVCHI TAHLILI VA O'ZLASHTIRISHI:**
▸ `Murodning o'zlashtirishi qanday`
▸ `Murod nimalarni tushunmayapti?`
▸ `Murod nimada qiynalyapti?`
*(Bot o'quvchining barcha savollari va qiyinchiliklarini GPT-4o orqali pedagogik tahlil qilib beradi)*

💳 **TO'LOVLAR NAZORATI:**
▸ `Murodning to'lovi` yoki `Murod to'ladimi?`
▸ `Kimlar to'lamadi?` yoki `Qarzdorlar ro'yxati`
▸ `Murod to'ladi` yoki `Murod to'lamadi`
▸ `To'lovlar ro'yxati`

📅 **DARS JADVALLARI:**
▸ `Murodni dars jadvali` *(o'quvchining haftalik dars jadvali)*
▸ `Bugungi darslar` *(bugun kimda dars borligi)*
▸ `Ertangi darslar` *(ertangi kun darslari)*

👥 **O'QUVCHILAR VA BAZA:**
▸ `O'quvchilar ro'yxati` *(barcha o'quvchilar va telefon raqamlari)*
▸ `Excelni yangila` *(jadvalni qayta import qilish)*
▸ `Bot holati` *(onlayn/oflayn status va ma'lumotlar)*

🏆 **REYTING VA GAMIFIKATSIYA:**
▸ `Reyting` yoki `Leaderboard` *(top o'quvchilar ro'yxati)*
▸ `Reytingni pin qil` yoki `Reytingni guruhga chiqar` *(reytingni guruhda zaprepit qilish)*
▸ `Murodga 50 XP` yoki `Murodga 30 ball` *(o'quvchiga ball qo'shish)*

⚙️ **ADMIN REJIMLARI:**
▸ `Onlayn bo'l` *(faqat botga murojaatlarga javob beradi)*
▸ `Oflayn bo'l` *(guruhdagi barcha savollarga AI javob beradi)*
▸ `Avtomatik rejim` *(5 daqiqa faol bo'lmasangiz, bot javob beradi)*"""


PUBLIC_ALLOWED_COMMANDS = {"start", "help", "jadval", "dars_jadvali", "darsjadvali", "id", "myid"}

async def command_access_guard(update, context):
    if not update.effective_user:
        raise ApplicationHandlerStop
    if update.effective_user.id == ADMIN_ID:
        return
    if update.message and update.message.text:
        cmd = update.message.text.split()[0].lstrip("/").split("@")[0].lower()
        if cmd in PUBLIC_ALLOWED_COMMANDS:
            return
    raise ApplicationHandlerStop


async def capture_member(update, context):
    if update.effective_user and update.effective_chat:
        register_member(update.effective_user, update.effective_chat.id)


async def configure_command_menus(telegram_bot):
    scopes = [BotCommandScopeDefault(), BotCommandScopeAllPrivateChats(), BotCommandScopeAllGroupChats()]
    group_id = get_setting("main_group_id")
    if group_id:
        scopes.append(BotCommandScopeChat(int(group_id)))
    for scope in scopes:
        for language in (None, "uz", "ru", "en"):
            try:
                await telegram_bot.delete_my_commands(scope=scope, language_code=language)
            except Exception as error:
                logger.warning("Eski menyuni tozalash: %s", type(error).__name__)
    admin_scopes = [BotCommandScopeChat(ADMIN_ID)]
    if group_id:
        admin_scopes.append(BotCommandScopeChatMember(int(group_id), ADMIN_ID))
    commands = [BotCommand(command, description) for command, description in ADMIN_COMMANDS]
    for scope in admin_scopes:
        try:
            for language in (None, "uz", "ru", "en"):
                await telegram_bot.set_my_commands(commands, scope=scope, language_code=language)
        except Exception as error:
            logger.warning("Admin menyusini sozlash: %s", type(error).__name__)


@admin_only
async def members_command(update, context):
    if update.effective_chat.type != "private":
        await update.message.reply_text("A'zolarni botning shaxsiy chatida boshqaring.")
        return
    command = update.message.text.split()[0].split("@")[0]
    try:
        if command == "/azolar":
            members = list_members()
            await send_reply(update.message, "\n".join(
                f"{m['full_name']} | TG {m['telegram_id']} | "
                + (f"O'quvchi ID {m['student_id']} | {m['course_name']} | {m['due_day']}-sana"
                   if m['student_id'] else "Kurs va to'lov kuni hali kiritilmagan")
                for m in members) or "Hali Telegram a'zolari qayd etilmagan.")
        elif command == "/boglash":
            if len(context.args) != 2:
                raise ValueError("Namuna: /boglash TG_ID OQUVCHI_ID")
            link_member(int(context.args[0]), int(context.args[1]))
            await update.message.reply_text("Telegram a'zo mavjud o'quvchiga bog'landi.")
        else:
            raw = update.message.text.split(maxsplit=1)
            fields = [part.strip() for part in raw[1].split("|")] if len(raw) > 1 else []
            if len(fields) != 4:
                raise ValueError("Namuna: /oquvchi 123456 | Ali Valiyev | Python | 15")
            student_id = enroll_member(int(fields[0]), fields[1], fields[2], int(fields[3]))
            await update.message.reply_text(f"O'quvchi kartasi yaratildi. ID {student_id}.")
    except ValueError as error:
        await update.message.reply_text(str(error))


async def natural_payment(update, context):
    parsed = parse_payment(update.message.text)
    if not parsed:
        return False
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("To'lov holatini faqat administrator belgilaydi.")
        return True
    target, paid, period = parsed
    replied = update.message.reply_to_message
    telegram_id = None
    if not target and replied and replied.from_user and not replied.from_user.is_bot:
        telegram_id = replied.from_user.id
    if not target and telegram_id is None:
        await update.message.reply_text("Kim to'ladi? To'liq ism yoki ID yozing: ID 12 to'ladi")
        return True
    matches = find_students(target, telegram_id)
    if not matches:
        await update.message.reply_text("O'quvchi topilmadi yoki Telegram ID bog'lanmagan. Shaxsiy chatda /azolar, /oquvchi yoki /boglash orqali kartani to'ldiring.")
        return True
    if len(matches) > 1:
        choices = "; ".join(f"ID {s['id']}: {s['name']}" for s in matches)
        text = (f"Bir nechta o'quvchi mos keldi: {choices}. ID bilan yozing: ID 12 to'ladi"
                if update.effective_chat.type == "private" else
                "Bir nechta o'quvchi mos keldi. Shaxsiy chatda /tolovlar orqali IDni aniqlang.")
        await send_reply(update.message, text)
        return True
    student = matches[0]
    period = period or tashkent_now().strftime("%Y-%m")
    try:
        changed = apply_payment(student['id'], period, paid, update.effective_user.id,
                                update.effective_chat.id, update.message.message_id)
    except ValueError:
        await update.message.reply_text("Oy noto'g'ri. Namuna: Ali Valiyev to'ladi 2026-09")
        return True
    await update.message.reply_text(
        f"{student['name']} — {period}: " + ("to'langan ✅" if paid else "to'lanmagan")
        if changed else "Bu xabardagi to'lov avval qayd etilgan.")
    return True


UZ_WEEKDAYS = {
    0: "Dushanba",
    1: "Seshanba",
    2: "Chorshanba",
    3: "Payshanba",
    4: "Juma",
    5: "Shanba",
    6: "Yakshanba"
}
UZ_MONTHS = {
    1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
    7: "iyul", 8: "avgust", 9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr"
}


def direct_request(message, chat, bot_user, text):
    replied = getattr(message, "reply_to_message", None) if message else None
    replied_user = getattr(replied, "from_user", None) if replied else None
    bot_uname = getattr(bot_user, "username", None)
    has_mention = bool(isinstance(bot_uname, str) and bot_uname and re.search(r"(?<!\w)@" + re.escape(bot_uname) + r"(?!\w)", text, re.I))
    return (
        chat.type == "private"
        or has_mention
        or bool(re.search(r"\bpi\b", text, re.I))
        or bool(replied_user and getattr(replied_user, "id", None) == getattr(bot_user, "id", None))
    )



def is_schedule_request(text: str) -> bool:
    """Matnda haftalik yoki shaxsiy dars jadvali so'ralganini aniqlash (xato yozilishlar: jadavli, jadval)"""
    lower = text.lower().strip()
    patterns = [
        r"\bdars\s+(?:jadval\w*|jadav[al]\w*)",   # dars jadvali, dars jadavli, dars jadvalim, dars jadvallari
        r"\bhaftalik\s+(?:jadval\w*|jadav[al]\w*)", # haftalik jadval, haftalik dars jadvali
        r"\b(?:jadval\w*|jadav[al]\w*)\b",       # jadval, jadvali, jadavli, jadvalim, jadavlim
        r"\bmening\s+(?:jadval\w*|jadav[al]\w*)", # mening jadvalim, mening jadavlim
        r"\bmening\s+dars",                     # mening darsim, mening darslarim
        r"\bdarsim\s+qachon\b",                # darsim qachon
        r"\bdarslarim\s+qachon\b",             # darslarim qachon
        r"\bdars\s+qachon\b",                  # dars qachon
        r"\bqachon\s+dars\b",                  # qachon dars
        r"\bdars\s+kunlar",                    # dars kunlari, dars kunlarim
        r"\bdars\s+vaqt",                      # dars vaqti, dars vaqtlari
    ]
    return any(re.search(p, lower) for p in patterns)


def strip_uzbek_suffixes(word: str) -> str:
    """O'zbek tilidagi kelishik va egalik qo'shimchalarini tozalash (murodni -> murod, murodning -> murod)"""
    w = word.strip().lower()
    suffixes = ["ning", "niki", "dan", "dek", "day", "dir", "ga", "ka", "qa", "da", "ni", "si", "im", "ing", "imiz", "i"]
    for sfx in suffixes:
        if len(w) > len(sfx) + 2 and w.endswith(sfx):
            w = w[:-len(sfx)]
            break
    return w


def extract_target_student_name(text: str) -> Optional[str]:
    """Xabar ichidan o'quvchi ismini yoki ID raqamini ajratib olish (grammatik qo'shimchalarni tozalab)"""
    # 1. Aniq ID ko'rsatilgan bo'lsa: "id 12", "id: 12", "#12"
    id_match = re.search(r"(?:^|\s)(?:id[:\s]*|#)(\d+)(?:\s|$)", text, re.I)
    if id_match:
        return f"id {id_match.group(1)}"

    cleaned = text
    keywords = [
        "dars", "jadvali", "jadvalim", "jadval", "haftalik", "mening", "qachon", 
        "vaqti", "kunlari", "bormi", "iltimos", "tashla", "yubor", "ko'rsat", 
        "qanaqa", "bering", "kerak", "ayt", "aytib", "to'lovi", "tolovi", "to'lov", 
        "tolov", "to'lovim", "tolovim", "to'lovimni", "to'ladimi", "toladimi", 
        "to'laganmi", "tolaganmi", "o'zlashtirishi", "ozlashtirishi", "o'zlashtirish", 
        "o'zlashtirishini", "qanday", "nimalarni", "tushunmayapti", "tushunmadi", 
        "tushunyapti", "qiynalyapti", "haqida", "ma'lumot", "ahvoli", "qilyapti", 
        "darajasi", "kimlar", "to'lamadi", "qarzdorlar", "darslar", "bugungi", 
        "ertangi", "bugun", "ertaga"
    ]
    for kw in keywords:
        cleaned = re.sub(rf"\b{re.escape(kw)}\b", "", cleaned, flags=re.I)
    cleaned = cleaned.strip(" ?!.,:;-\t\n")
    if not cleaned or len(cleaned) < 2:
        return None
    words = cleaned.split()
    if len(words) > 3:
        return None
    stripped_words = [strip_uzbek_suffixes(w) for w in words]
    res = " ".join(stripped_words).strip(" ?!.,:;-\t\n")
    return res if len(res) >= 2 else None


def find_matching_students(target: str) -> List[Dict[str, Any]]:
    """
    Berilgan so'rov (ID, ism yoki matn ichidagi ism) bo'yicha bazadagi barcha mos o'quvchilarni topish.
    Bir xil ismli o'quvchilar bo'lsa, barchasini ro'yxat qilib qaytaradi (birinchisini tanlab ketmaydi).
    """
    if not target or not str(target).strip():
        return []

    target_str = str(target).strip()
    with closing(get_connection()) as conn:
        students = [dict(r) for r in conn.execute("SELECT * FROM students WHERE active = 1").fetchall()]

    # 1. Aniq raqamli ID or #ID or ID: 12
    id_match = re.search(r"(?:^|\s)(?:id[:\s]*|#)(\d+)(?:\s|$)", target_str.lower())
    if id_match:
        sid = int(id_match.group(1))
        return [s for s in students if s["id"] == sid]

    # 2. Username @username
    if "@" in target_str:
        u_match = re.search(r"@([a-zA-Z0-9_]+)", target_str)
        if u_match:
            clean_u = u_match.group(1).lower()
            u_matched = [s for s in students if (s.get("username") or "").lstrip("@").lower() == clean_u]
            if u_matched:
                return u_matched

    # 3. Aniq to'liq ism mosligi (Exact full name match)
    nt = normalize(target_str)
    exact = [s for s in students if normalize(s["name"]) == nt]
    if exact:
        return exact

    # 4. Bo'lak so'zlar / prefiks mosligi (agar target faqat ism bo'lsa)
    target_words = nt.split()
    matches = [s for s in students if target_words and all(
        len(word) >= 2 and any(token.startswith(word) for token in normalize(s["name"]).split())
        for word in target_words)]
    if matches:
        return matches

    # 5. Butun matn ichidan o'quvchi ismlarini qidirish (qo'shimchalar bilan: 'anvarni', 'anvarning' -> 'Mirzayev Anvar')
    clean = re.sub(r"['’‘ʻʼ`]", "", target_str.lower())
    words = re.findall(r"[a-zA-Z]+", clean)
    tokens = {strip_uzbek_suffixes(w) for w in words} | set(words)

    matched_by_token = []
    for s in students:
        s_clean = re.sub(r"['’‘ʻʼ`]", "", s["name"].lower())
        s_tokens = [strip_uzbek_suffixes(p) for p in s_clean.split()] + s_clean.split()
        for tok in s_tokens:
            if len(tok) >= 3 and tok in tokens:
                matched_by_token.append(s)
                break
    if matched_by_token:
        return matched_by_token

    return []


def find_student_by_user(user, target_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Foydalanuvchi yoki berilgan ism bo'yicha bazadagi o'quvchini topish.
    Bir xil ismli ikki odam bo'lsa, bot birinchisini tanlab ketmaydi (faqat bitta aniq moslik bo'lsa qaytaradi).
    Oddiy foydalanuvchi esa faqat o'zgarmas Telegram ID orqali aniqlanadi.
    """
    if target_name:
        matches = find_matching_students(target_name)
        return matches[0] if len(matches) == 1 else None

    if not user:
        return None

    # O'quvchi Telegramdagi ismini almashtirsa ham, uning Telegram ID raqami o'zgarmaydi!
    # Shuning uchun qidiruv faqat telegram_id bo'yicha olib boriladi.
    with closing(get_connection()) as conn:
        students = [dict(r) for r in conn.execute("SELECT * FROM students WHERE active = 1").fetchall()]

    linked = [s for s in students if s.get("telegram_id") is not None
              and str(s["telegram_id"]) == str(getattr(user, "id", None))]
    return linked[0] if len(linked) == 1 else None



def format_student_weekly_schedule(student: Dict[str, Any]) -> str:
    """O'quvchining haftalik dars jadvalini chiroyli formatda tayyorlash"""
    UZ_WEEKDAYS = {
        0: "Dushanba",
        1: "Seshanba",
        2: "Chorshanba",
        3: "Payshanba",
        4: "Juma",
        5: "Shanba",
        6: "Yakshanba"
    }
    UZ_MONTHS = {
        1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
        7: "iyul", 8: "avgust", 9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr"
    }

    now = tashkent_now()
    today = now.date()
    today_iso = today.isoformat()
    curr_time_str = now.strftime("%H:%M")

    with closing(get_connection()) as conn:
        lessons = [dict(r) for r in conn.execute(
            "SELECT * FROM daily_lessons WHERE student_name = ? AND cancelled = 0 ORDER BY lesson_date, lesson_time",
            (student["name"],)
        ).fetchall()]

    if not lessons:
        return (
            f"📅 **Hurmatli {student['name']}!**\n\n"
            f"📚 Kursingiz: **{student.get('course_name') or 'Nomaʼlum'}**\n"
            f"⚠️ Hozircha siz uchun dars jadvali kiritilmagan. Iltimos, ma'lumot uchun adminga murojaat qiling."
        )

    # Joriy hafta oralig'i (Dushanba - Yakshanba)
    curr_monday = today - timedelta(days=today.weekday())
    curr_sunday = curr_monday + timedelta(days=6)

    # Kelgusi hafta oralig'i
    next_monday = curr_monday + timedelta(days=7)
    next_sunday = curr_sunday + timedelta(days=7)

    this_week = [l for l in lessons if curr_monday.isoformat() <= l["lesson_date"] <= curr_sunday.isoformat()]
    next_week = [l for l in lessons if next_monday.isoformat() <= l["lesson_date"] <= next_sunday.isoformat()]

    # Navbatdagi darsni aniqlash
    upcoming = [
        l for l in lessons 
        if l["lesson_date"] > today_iso or (l["lesson_date"] == today_iso and l["lesson_time"] >= curr_time_str)
    ]
    next_lesson = upcoming[0] if upcoming else None

    lines = [
        "╔══════════════════════════════════╗",
        "║ 🎓 **CYBER TECH ACADEMY**",
        "║ 📅 **Haftalik dars jadvali**",
        "╚══════════════════════════════════╝",
        f"👤 **O'quvchi:** {student['name']}",
        f"📚 **Kurs:** {student.get('course_name') or 'Kurs'}",
        "──────────────────────────────────",
    ]

    # Joriy hafta
    m_from = f"{curr_monday.day}-{UZ_MONTHS[curr_monday.month]}"
    m_to = f"{curr_sunday.day}-{UZ_MONTHS[curr_sunday.month]}"
    lines.append(f"🗓 **Joriy hafta ({m_from} — {m_to}):**")
    if this_week:
        for l in this_week:
            d = date.fromisoformat(l["lesson_date"])
            day_name = UZ_WEEKDAYS[d.weekday()]
            day_str = f"{d.day}-{UZ_MONTHS[d.month]}"
            if l["lesson_date"] == today_iso:
                mark = " ⏳ *(Bugun)*"
            elif l["lesson_date"] < today_iso:
                mark = " ✅"
            else:
                mark = ""
            lines.append(f" ▸ **{day_name}** ({day_str}) ┆ soat **{l['lesson_time']}**{mark}")
    else:
        lines.append(" ▸ Ushbu haftada boshqa dars belgilanmagan.")

    lines.append("──────────────────────────────────")

    # Kelgusi hafta
    if next_week:
        n_from = f"{next_monday.day}-{UZ_MONTHS[next_monday.month]}"
        n_to = f"{next_sunday.day}-{UZ_MONTHS[next_sunday.month]}"
        lines.append(f"🗓 **Kelgusi hafta ({n_from} — {n_to}):**")
        for l in next_week:
            d = date.fromisoformat(l["lesson_date"])
            day_name = UZ_WEEKDAYS[d.weekday()]
            day_str = f"{d.day}-{UZ_MONTHS[d.month]}"
            lines.append(f" ▸ **{day_name}** ({day_str}) ┆ soat **{l['lesson_time']}**")
        lines.append("──────────────────────────────────")

    # Navbatdagi eng yaqin dars
    if next_lesson:
        nl_date = date.fromisoformat(next_lesson["lesson_date"])
        nl_day_name = UZ_WEEKDAYS[nl_date.weekday()]
        if next_lesson["lesson_date"] == today_iso:
            time_label = f"Bugun ({nl_day_name})"
        elif next_lesson["lesson_date"] == (today + timedelta(days=1)).isoformat():
            time_label = f"Ertaga ({nl_day_name})"
        else:
            time_label = f"{nl_date.day}-{UZ_MONTHS[nl_date.month]} ({nl_day_name})"
        lines.append(f"⏰ **Navbatdagi dars:** {time_label}, soat **{next_lesson['lesson_time']}** da.")
    else:
        lines.append("🎉 Joriy oy uchun barcha darslar yakunlangan.")

    return "\n".join(lines)


async def jadval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'quvchining haftalik dars jadvalini ko'rsatish (Maxfiylik himoyalangan)"""
    message = update.message
    if not message:
        return
    user = update.effective_user
    is_admin = user and user.id == ADMIN_ID
    target_name = " ".join(context.args).strip() if context.args else None

    # AGAR ODDIY FOYDALANUVCHI BO'LSA:
    if not is_admin:
        my_student = find_student_by_user(user)
        if target_name:
            if not my_student or not any(token in normalize(target_name) for token in normalize(my_student["name"]).split()):
                await message.reply_text(
                    "🔒 **Maxfiylik qoidasi:**\n"
                    "Siz faqat o'zingizga tegishli dars jadvalini ko'rishingiz mumkin. Boshqa o'quvchilar ma'lumotlari maxfiy hisoblanadi. 🛡",
                    parse_mode="Markdown"
                )
                return
        if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id != getattr(user, "id", None):
            await message.reply_text(
                "🔒 **Maxfiylik qoidasi:**\n"
                "Siz faqat o'zingizga tegishli dars jadvalini ko'rishingiz mumkin. Boshqa o'quvchilar ma'lumotlari maxfiy hisoblanadi. 🛡",
                parse_mode="Markdown"
            )
            return

        student = my_student
    else:
        if not target_name and message.reply_to_message and message.reply_to_message.from_user:
            replied_user = message.reply_to_message.from_user
            student = find_student_by_user(replied_user)
        elif target_name:
            matches = find_matching_students(target_name)
            if len(matches) > 1:
                choices = "\n".join([f"  • **ID #{s['id']}**: {s['name']} ({s.get('course_name') or 'Kurs'})" for s in matches])
                await send_reply(
                    message,
                    f"⚠️ **Bazada '{target_name}' bo'yicha bir nechta o'quvchi topildi:**\n{choices}\n\n"
                    f"Noaniqlik bo'lmasligi uchun aniq ID bilan so'rang: `/jadval ID {matches[0]['id']}`"
                )
                return
            student = matches[0] if len(matches) == 1 else None
        else:
            student = find_student_by_user(user)

    if student:
        schedule_text = format_student_weekly_schedule(student)
        await send_reply(message, schedule_text)
    elif is_admin:
        await message.reply_text(
            "👤 O'quvchini aniqlab bo'lmadi.\n"
            "Foydalanish: `/jadval O'quvchi_Ismi` yoki `/jadval ID 12` yoki o'quvchining xabariga reply qilib `/jadval` yozing."
        )
    else:
        await message.reply_text(
            f"🔒 **Profilingiz tasdiqlanmagan:**\n"
            f"Sizning Telegram profilingiz (TG ID: `{user.id}`) hali o'quvchilar bazasiga bog'lanmagan. ⚠️\n\n"
            f"Boshqa o'quvchilar ma'lumotlarini ko'rish taqiqlanadi. Dars jadvalingizni ko'rish uchun "
            f"markaz administratoriga ushbu Telegram ID raqamingizni (`{user.id}`) taqdim eting.",
            parse_mode="Markdown"
        )


def format_pinned_leaderboard_text() -> str:
    """Guruhda zaprepit qilinadigan o'quvchilar reytingi matni"""
    leaderboard = get_leaderboard(limit=12)
    now = tashkent_now()
    now_str = now.strftime("%d-%m-%Y %H:%M")

    lines = [
        "🏆 **CYBER TECH ACADEMY — O'QUVCHILAR REYTINGI** 🚀",
        "──────────────────────────────────",
        "💡 *O'quvchilar AI bilan masala yechgani, savol-javob qilgani va faolligi uchun XP to'playdi!*\n"
    ]

    medals = ["🥇", "🥈", "🥉"]
    for idx, row in enumerate(leaderboard, 1):
        m = medals[idx - 1] if idx <= 3 else f"`{idx:2d}.`"
        c_name = row.get("course_name") or ""
        c_lower = c_name.lower()
        if "python" in c_lower or "dastur" in c_lower:
            c_badge = "💻 Python"
        elif "savodxon" in c_lower or "kompyuter" in c_lower:
            c_badge = "🖥 Savodxonlik"
        elif "robot" in c_lower:
            c_badge = "🤖 Robotika"
        else:
            c_badge = f"📚 {c_name}" if c_name else "🎓 IT"

        lines.append(f"{m} **{row['student_name']}** — **{row['xp']} XP**")
        lines.append(f"   {row['title']} ┆ {c_badge} ┆ ✅ {row.get('tasks_solved', 0)} ta masala\n")

    lines.append("──────────────────────────────────")
    lines.append("⚡ **XP to'plash qoidalari:**")
    lines.append("• 🎯 AI masalasini to'g'ri yechish: **+25 XP**")
    lines.append("• 📸 Kod / vazifa rasmini tahlil qilish: **+15 XP**")
    lines.append("• 💡 Dars va ilm bo'yicha savol berish: **+5 XP**")
    lines.append("• 🎖 Ustoz tomonidan rag'batlantirish: **+10 ~ +100 XP**")
    lines.append(f"\n🔄 *Oxirgi yangilanish:* `{now_str}`")

    return "\n".join(lines)


def get_leaderboard_inline_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_leaderboard"),
            InlineKeyboardButton(text="📊 Mening profilim", callback_data="my_profile")
        ],
        [
            InlineKeyboardButton(text="⚡ Ball to'plash qoidalari", callback_data="xp_rules")
        ]
    ])


async def update_pinned_leaderboard(telegram_bot, group_id: Optional[int] = None, force_repin: bool = False):
    """Guruhdagi reyting xabarini avtomatik yangilash va zaprepit (pin) qilib qo'yish"""
    group_id_str = group_id or get_setting("main_group_id")
    if not group_id_str:
        logger.warning("Guruh ID topilmadi, reyting zaprepit qilinmadi.")
        return None
    try:
        chat_id = int(group_id_str)
    except (ValueError, TypeError):
        return None

    from leaderboard_service import update_board
    return await update_board(telegram_bot, chat_id, format_pinned_leaderboard_text(),
                              get_leaderboard_inline_keyboard(), force_repin)



async def leaderboard_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reyting tugmalari (Yangilash va Mening profilim) uchun ishlov beruvchi"""
    query = update.callback_query
    if not query:
        return
    data = query.data
    user = query.from_user

    if data == "refresh_leaderboard":
        await update_pinned_leaderboard(context.bot)
        try:
            await query.answer("Reyting jadvali yangilandi! 🚀", show_alert=False)
        except Exception:
            pass
        return

    if data == "my_profile":
        st = find_student_by_user(user)
        if st:
            g_data = get_student_gamification(student_id=st["id"])
            if g_data:
                c_name = st.get('course_name') or 'IT'
                c_lower = c_name.lower()
                icon = "💻" if "python" in c_lower else ("🖥" if "savodxon" in c_lower or "kompyuter" in c_lower else ("🤖" if "robot" in c_lower else "📚"))
                try:
                    await query.answer(
                        f"🏆 O'QUVCHI PROFILI: {st['name']}\n"
                        f"{icon} Yo'nalish: {c_name}\n"
                        f"⚡ To'plangan ball: {g_data['xp']} XP\n"
                        f"🎖 Unvon: {g_data['title']} (Level {g_data['level']})\n"
                        f"✅ Yechilgan masalalar: {g_data.get('tasks_solved', 0)} ta\n"
                        f"❓ Berilgan savollar: {g_data.get('questions_asked', 0)} ta",
                        show_alert=True
                    )
                except Exception:
                    pass
                return
        try:
            await query.answer(
                f"👤 {user.first_name}, siz hali o'quvchilar ro'yxatida emassiz yoki profilingiz bog'lanmagan. Adminga murojaat qiling!",
                show_alert=True
            )
        except Exception:
            pass
        return

    if data == "xp_rules":
        rules_text = (
            "⚡ CYBER TECH ACADEMY — XP VA UNVONLAR 🎯\n\n"
            "Ball to'plash:\n"
            "• 🎯 AI masalasini to'g'ri yechish: +25 XP\n"
            "• 📸 Kod / vazifa rasmi tahlili: +15 XP\n"
            "• 💡 Dars va ilm bo'yicha savol: +5 XP\n"
            "• 🎖 Ustoz rag'bati: +10 ~ +100 XP\n\n"
            "Yo'nalish unvonlari (1 -> 5-daraja):\n"
            "💻 Dasturchilar:\n"
            "  Junior Coder ➔ Python Dev ➔ Algoritm Ustasi ➔ Software Architect ➔ Cyber Code Ninja\n\n"
            "🖥 Savodxonlik:\n"
            "  IT Izquvar ➔ Windows Bilimdoni ➔ Office & Excel Master ➔ Tizim Administratori ➔ IT Mutaxassis Lider\n\n"
            "🤖 Robototexnika:\n"
            "  Yosh Konstruktor ➔ Sxema Ustasi ➔ Arduino Injeneri ➔ Kiber Mexatronik ➔ Cyber Robo Master"
        )
        try:
            await query.answer(rules_text, show_alert=True)
        except Exception:
            pass
        return


# ----------------- TELEGRAM QUIZ (TEST) VA POLL BOSHQARUVI -----------------

async def close_quiz_polls(chat_id: int, session_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Sessiyaga tegishli barcha ochiq polllarni xavfsiz yopish"""
    poll_items = get_session_poll_message_ids(session_id)
    for p in poll_items:
        try:
            await context.bot.stop_poll(chat_id=chat_id, message_id=p["message_id"])
            await asyncio.sleep(0.15)
        except Exception:
            pass


async def execute_finish_quiz_session(chat_id: int, session_id: int, context: ContextTypes.DEFAULT_TYPE, message=None, silent_cancel: bool = False) -> bool:
    """Aynan bitta test sessiyasini yakunlash, polllarni to'xtatish va natijalarni hisoblash"""
    session = get_quiz_session_by_id(session_id)
    if not session:
        return False

    topic = session.get("topic", "Mavzu")
    finish_quiz_session(session_id)
    await close_quiz_polls(chat_id, session_id, context)

    if silent_cancel:
        return True

    results = get_quiz_session_results(session_id)
    total_q = session.get("total_questions", 10)

    if not results:
        res_text = (
            f"🏁 **TEST YAKUNLANDI!**\n\n"
            f"📚 Mavzu: **{topic}** (ID #{session_id})\n\n"
            f"Ushbu testda hali hech bir o'quvchi javob belgilamagan edi."
        )
    else:
        medals = ["🥇", "🥈", "🥉"]
        resp = (
            f"🏁 **TEST YAKUNLANDI! NATIJALAR VA G'OLIBLAR:** 🏆\n\n"
            f"📚 **Mavzu:** {topic} (ID #{session_id})\n"
            f"❓ **Jami savollar:** {total_q} ta\n"
            f"👥 **Qatnashuvchilar:** {len(results)} nafar\n"
            f"────────────────────────\n\n"
        )
        for idx, row in enumerate(results, 1):
            m = medals[idx - 1] if idx <= 3 else f"{idx}."
            u_name = row["user_name"]
            correct = row["correct_count"] or 0
            xp_won = row["total_xp_earned"] or 0
            pct = int((correct / total_q) * 100) if total_q else 0
            resp += f"{m} **{u_name}** — **{correct}/{total_q}** to'g'ri ({pct}%) ┆ **+{xp_won} XP** ⚡\n"

        resp += "\n────────────────────────\n"
        resp += "💡 *Har bir to'g'ri javob uchun 1 XP o'quvchining umumiy reytingiga qo'shildi!*"
        res_text = resp

    if message:
        await send_reply(message, res_text)
    else:
        await context.bot.send_message(chat_id=chat_id, text=res_text, parse_mode="Markdown")

    asyncio.create_task(update_pinned_leaderboard(context.bot))
    return True


async def launch_quiz_session(chat_id: int, admin_id: int, quiz_data: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE, reply_to_message_id: Optional[int] = None, message_thread_id: Optional[int] = None):
    """AI tomonidan tuzilgan 10 talik testni Telegram Quiz Polllari sifatida guruhga chiqarish"""
    topic = quiz_data.get("topic") or "IT Viktorinasi"
    questions = quiz_data.get("questions") or []
    if not questions:
        return

    # O'tkazilgan barcha test savollarini doimiy testlar bazasiga (quiz_bank) saqlab boramiz
    if not quiz_data.get("from_bank"):
        try:
            save_quiz_to_bank(topic, questions)
        except Exception as e:
            logger.warning("Test savollarini bazaga saqlashda xatolik: %s", e)

    # Oldingi faol testlar bo'lsa, ularning polllarini ham to'xtatib yakunlaymiz
    active_sessions = get_active_quiz_sessions(chat_id)
    for s in active_sessions:
        finish_quiz_session(s["id"])
        await close_quiz_polls(chat_id, s["id"], context)

    session_id = create_quiz_session(chat_id, admin_id, topic, total_questions=len(questions))

    send_kwargs = {"chat_id": chat_id, "parse_mode": "Markdown"}
    if reply_to_message_id:
        send_kwargs["reply_to_message_id"] = reply_to_message_id
    if message_thread_id:
        send_kwargs["message_thread_id"] = message_thread_id

    await context.bot.send_message(
        text=(
            f"🚀 **YANGI TEST (VIKTORINA) BOSHLANDI!** 🎯\n\n"
            f"📚 **Mavzu:** {topic}\n"
            f"❓ **Savollar soni:** {len(questions)} ta\n"
            f"⚡ **Ball:** Har bir to'g'ri javob uchun **+1 XP** beriladi!\n\n"
            f"💡 *Barcha o'quvchilar javob variantlarini belgilashlari mumkin. Ustoz 'testni tugat' deb yozganida g'oliblar va to'liq natijalar e'lon qilinadi!*"
        ),
        **send_kwargs
    )

    for idx, q in enumerate(questions, 1):
        q_title = f"{idx}-savol: {q['question']}"
        if len(q_title) > 250:
            q_title = q_title[:247] + "..."

        poll_kwargs = {
            "chat_id": chat_id,
            "question": q_title,
            "options": q["options"],
            "type": Poll.QUIZ,
            "correct_option_id": q["correct_option_id"],
            "explanation": q.get("explanation") or None,
            "is_anonymous": False
        }
        if message_thread_id:
            poll_kwargs["message_thread_id"] = message_thread_id

        try:
            poll_msg = await context.bot.send_poll(**poll_kwargs)
            add_quiz_question(
                session_id=session_id,
                poll_id=poll_msg.poll.id,
                message_id=poll_msg.message_id,
                question_text=q_title,
                correct_option_id=q["correct_option_id"]
            )
            await asyncio.sleep(0.7)
        except RetryAfter as e:
            logger.warning("Telegram FloodControl, %s soniya kutilyapti...", e.retry_after)
            await asyncio.sleep(e.retry_after + 1)
            try:
                poll_msg = await context.bot.send_poll(**poll_kwargs)
                add_quiz_question(
                    session_id=session_id,
                    poll_id=poll_msg.poll.id,
                    message_id=poll_msg.message_id,
                    question_text=q_title,
                    correct_option_id=q["correct_option_id"]
                )
            except Exception as e2:
                logger.error("Qayta yuborishda xatolik: %s", e2)
        except Exception as e:
            logger.error("Poll yuborishda xatolik: %s", e)


async def handle_finish_quiz(chat_id: int, message, context: ContextTypes.DEFAULT_TYPE, target_session_id: Optional[int] = None) -> bool:
    """Faol testni to'xtatish, polllarni yopish va natijalar hisobotini chiqarish"""
    if target_session_id:
        return await execute_finish_quiz_session(chat_id, target_session_id, context, message=message)

    active_sessions = get_active_quiz_sessions(chat_id)
    if not active_sessions:
        await send_reply(message, "⚠️ Hozirda bu guruhda faol test mavjud emas.")
        return True

    if len(active_sessions) == 1:
        return await execute_finish_quiz_session(chat_id, active_sessions[0]["id"], context, message=message)

    # Bir nechta faol test bo'lsa, qaysi birini tugatish kerakligini so'raydi
    buttons = []
    text = (
        f"❓ **Qaysi testni yakunlamoqchisiz?**\n\n"
        f"Guruhda **{len(active_sessions)} ta** faol test topildi:\n"
    )
    for idx, s in enumerate(active_sessions, 1):
        text += f"{idx}. 📚 **{s['topic']}** (ID #{s['id']}, {s.get('total_questions', 10)} ta savol)\n"
        btn_label = f"🏁 #{s['id']}: {s['topic'][:22]}"
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"quiz_fin:{s['id']}")])

    buttons.append([InlineKeyboardButton("🏆 Barcha faol testlarni yakunlash", callback_data="quiz_fin:all")])
    buttons.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="quiz_act:keep_current")])

    await send_reply(message, text, reply_markup=InlineKeyboardMarkup(buttons))
    return True


async def prompt_existing_quiz_action(chat_id: int, active_sessions: List[Dict[str, Any]], message, context: ContextTypes.DEFAULT_TYPE):
    """Faol test bor bo'lgan paytda yangi test so'ralsa, bot qotib qolmasdan adminga aniq tanlov berishi"""
    if len(active_sessions) == 1:
        s = active_sessions[0]
        text = (
            f"⚠️ **Guruhda hozirda faol test davom etmoqda!**\n\n"
            f"📚 **Faol mavzu:** {s['topic']} (ID #{s['id']})\n"
            f"❓ **Savollar soni:** {s.get('total_questions', 10)} ta\n\n"
            f"Siz yangi test so'rovini yubordingiz. Qaysi amalni bajarishni xohlaysiz?"
        )
        keyboard = [
            [InlineKeyboardButton("🏁 Hozirgi testni yakunlab, yangisini boshlash", callback_data="quiz_act:finish_and_start")],
            [InlineKeyboardButton("❌ Hozirgi testni bekor qilib, yangisini boshlash", callback_data="quiz_act:cancel_and_start")],
            [InlineKeyboardButton("⏸ Bekor qilish (Hozirgi test davom etsin)", callback_data="quiz_act:keep_current")]
        ]
    else:
        topics_str = "\n".join([f"  {idx}. 📚 **{s['topic']}** (ID #{s['id']})" for idx, s in enumerate(active_sessions, 1)])
        text = (
            f"⚠️ **Guruhda bir nechta ({len(active_sessions)} ta) faol test mavjud!**\n\n"
            f"{topics_str}\n\n"
            f"Yangi test boshlashdan avval, qaysi amalni bajarishni xohlaysiz?"
        )
        keyboard = [
            [InlineKeyboardButton("🏁 Barchasini yakunlab, yangisini boshlash", callback_data="quiz_act:finish_all_and_start")],
            [InlineKeyboardButton("❌ Barchasini bekor qilib, yangisini boshlash", callback_data="quiz_act:cancel_all_and_start")],
            [InlineKeyboardButton("⏸ Bekor qilish (Testlar davom etsin)", callback_data="quiz_act:keep_current")]
        ]
    await send_reply(message, text, reply_markup=InlineKeyboardMarkup(keyboard))


async def generate_and_launch_pending_quiz(chat_id: int, pending: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE):
    """Navbatda turgan yangi testni (AI yoki testlar bazasidan) generatsiya qilib guruhga yuborish"""
    if pending.get("is_random_bank"):
        category = pending.get("category", "python")
        quiz_data = get_random_quiz_from_bank(category=category, count=10)
        if not quiz_data:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Testlar bazasida {category.capitalize()} yo'nalishi bo'yicha savollar yetarli emas.",
                message_thread_id=pending.get("message_thread_id")
            )
            return
        await launch_quiz_session(
            chat_id=chat_id,
            admin_id=pending.get("user_id", ADMIN_ID),
            quiz_data=quiz_data,
            context=context,
            reply_to_message_id=pending.get("reply_to_message_id"),
            message_thread_id=pending.get("message_thread_id")
        )
        return

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ Yangi 10 talik test (Quiz Poll) tayyorlanmoqda...",
        message_thread_id=pending.get("message_thread_id")
    )
    quiz_data = await generate_quiz_from_ai(
        text=pending.get("text"),
        image_bytes=pending.get("img_bytes"),
        caption_hint=pending.get("caption_hint", "")
    )
    if quiz_data.get("success"):
        with suppress(Exception):
            await status_msg.delete()
        await launch_quiz_session(
            chat_id=chat_id,
            admin_id=pending.get("user_id", ADMIN_ID),
            quiz_data=quiz_data,
            context=context,
            reply_to_message_id=pending.get("reply_to_message_id"),
            message_thread_id=pending.get("message_thread_id")
        )
    else:
        await status_msg.edit_text(f"⚠️ Test tuzishda xatolik: {quiz_data.get('error', 'AI test shakllantira olmadi')}")


async def quiz_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test boshqaruvi va faol testlarni yakunlash tugmalari uchun ishlov beruvchi"""
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    user = query.from_user
    chat = update.effective_chat
    chat_id = chat.id if chat else None

    # Xavfsizlik: test boshqaruvini faqat admin bajara oladi
    if not (user and user.id == ADMIN_ID):
        with suppress(Exception):
            await query.answer("⚠️ Faqat admin testlarni boshqarishi mumkin!", show_alert=True)
        return

    with suppress(Exception):
        await query.answer()

    if data == "quiz_act:keep_current":
        context.chat_data.pop("pending_quiz", None)
        with suppress(Exception):
            await query.edit_message_text("✅ Amaliyot bekor qilindi. Hozirgi faol test davom ettiriladi.")
        return

    if data == "quiz_act:finish_and_start":
        active_s = get_active_quiz_session(chat_id)
        if active_s:
            await execute_finish_quiz_session(chat_id, active_s["id"], context)
        with suppress(Exception):
            await query.edit_message_text("🏁 Hozirgi test yakunlandi! Yangi test generatsiya qilinmoqda...")
        pending = context.chat_data.pop("pending_quiz", None)
        if pending:
            await generate_and_launch_pending_quiz(chat_id, pending, context)
        return

    if data == "quiz_act:cancel_and_start":
        active_s = get_active_quiz_session(chat_id)
        if active_s:
            await execute_finish_quiz_session(chat_id, active_s["id"], context, silent_cancel=True)
        with suppress(Exception):
            await query.edit_message_text("❌ Hozirgi test bekor qilindi. Yangi test tayyorlanmoqda...")
        pending = context.chat_data.pop("pending_quiz", None)
        if pending:
            await generate_and_launch_pending_quiz(chat_id, pending, context)
        return

    if data == "quiz_act:finish_all_and_start":
        active_sessions = get_active_quiz_sessions(chat_id)
        for s in active_sessions:
            await execute_finish_quiz_session(chat_id, s["id"], context)
        with suppress(Exception):
            await query.edit_message_text("🏁 Barcha faol testlar yakunlandi! Yangi test generatsiya qilinmoqda...")
        pending = context.chat_data.pop("pending_quiz", None)
        if pending:
            await generate_and_launch_pending_quiz(chat_id, pending, context)
        return

    if data == "quiz_act:cancel_all_and_start":
        active_sessions = get_active_quiz_sessions(chat_id)
        for s in active_sessions:
            await execute_finish_quiz_session(chat_id, s["id"], context, silent_cancel=True)
        with suppress(Exception):
            await query.edit_message_text("❌ Barcha faol testlar bekor qilindi. Yangi test tayyorlanmoqda...")
        pending = context.chat_data.pop("pending_quiz", None)
        if pending:
            await generate_and_launch_pending_quiz(chat_id, pending, context)
        return

    if data.startswith("quiz_fin:"):
        target = data.split(":", 1)[1]
        with suppress(Exception):
            await query.delete_message()
        if target == "all":
            active_sessions = get_active_quiz_sessions(chat_id)
            for s in active_sessions:
                await execute_finish_quiz_session(chat_id, s["id"], context)
        else:
            try:
                sid = int(target)
                await execute_finish_quiz_session(chat_id, sid, context)
            except ValueError:
                pass
        return


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi Quiz Pollda javob belgilaganda ushlaydi va to'g'ri bo'lsa 1 XP beradi"""
    answer = update.poll_answer
    if not answer:
        return

    poll_id = answer.poll_id
    user = answer.user
    option_ids = answer.option_ids

    q_data = get_quiz_question_by_poll(poll_id)
    if not q_data:
        return

    if q_data.get("session_status") != "active":
        return

    session_id = q_data["session_id"]
    correct_opt = q_data["correct_option_id"]
    is_correct = bool(option_ids and option_ids[0] == correct_opt)

    st = find_student_by_user(user)
    student_id = st["id"] if st else None
    user_display = st["name"] if st else (getattr(user, "first_name", None) or "O'quvchi")

    is_new = record_quiz_answer(
        session_id=session_id,
        poll_id=poll_id,
        telegram_user_id=user.id,
        user_name=user_display,
        student_id=student_id,
        chosen_option_id=option_ids[0] if option_ids else -1,
        is_correct=is_correct,
        xp_awarded=1
    )

    if is_new and is_correct and st:
        add_student_xp(st["id"], st["name"], xp_delta=1, is_task=True, course_name=st.get("course_name"))
        asyncio.create_task(update_pinned_leaderboard(context.bot))


# Ustozga qaratilgan murojaat kalit so'zlari (bunday savollarga bot aralashmaydi)
TEACHER_KEYWORDS = [
    "ustoz", "domla", "muallim", "o'qituvchi", "oqituvchi", "teacher",
    "mentor", "admin", "shef", "boss", "shaxboz", "shahboz", "salomov"
]

def is_addressed_to_teacher(text: str) -> bool:
    """Savol ustoz/adminga yo'naltirilganligini tekshirish"""
    lower = text.lower()
    for kw in TEACHER_KEYWORDS:
        if re.search(rf"\b{kw}(?:im|ing|imiz|ga|ka|qa|dan|ni|cha|lar|bek|aka)?\b", lower):
            return True
    return False

CASUAL_PATTERNS = [
    r"^(?:salom|assalom|assalomu\s*alaykum|va\s*alaykum\s*assalom|privet|hello|hi|zdravstvuyte)\b",
    r"^(?:qalesiz|qalaysiz|qandaysiz|yaxshimisiz|tuzukmisiz|charchamayapsizmi|ishlar\s*qalay|nima\s*gap)\b",
    r"^(?:rahmat|katta\s*rahmat|tashakkur|spasibo|thanks|arzimaydi|salomat\s*bo'?ling)\b",
    r"^(?:ha|yo'?q|hop|xo'?p|ok|mayli|boldi|bo'?ldi|tushunarli|yaxshi|tushundim|keldim|kelyapman|yo'?ldaman)\b",
    r"^(?:kim\s*bor|qayerdasiz)\b",
]

def is_casual_group_chat(text: str) -> bool:
    """Guruhdagi o'zaro oddiy salom-alik va kundalik qisqa suhbatlarni aniqlash"""
    lower = text.strip().lower()
    for pat in CASUAL_PATTERNS:
        if re.search(pat, lower):
            return True
    words = lower.split()
    if len(words) <= 2 and not any(k in lower for k in ["python", "excel", "kod", "xato", "jadval", "dars", "masala"]):
        return True
    return False

def is_academic_question(text: str) -> bool:
    """Xabar aniq ta'limiy/dasturlash/masala so'rovi ekanligini aniqlash"""
    lower = text.lower()
    academic_terms = [
        "python", "excel", "kod", "vlookup", "vpr", "formula", "funksiya",
        "algoritm", "baza", "sql", "dastur", "xatolik", "error", "bug",
        "masala", "misol", "vazifa", "topshiriq", "yechish", "tushuntir",
        "o'rgat", "misol ber", "masala ber", "tekshir", "ishlamayapti",
        "qanday yoziladi", "qanday ishlaydi", "sintaksis", "loop", "sikil",
        "massiv", "list", "dict", "lug'at", "shart", "operator", "import"
    ]
    return any(term in lower for term in academic_terms)

def is_task_request(text: str) -> bool:
    """O'quvchi masala, misol, mashq yoki topshiriq so'raganini aniqlash"""
    lower = text.lower()
    task_triggers = [
        "masala", "misol", "mashq", "topshiriq", "vazifa", "amaliy",
        "savol ber", "test ber"
    ]
    action_triggers = [
        "ber", "bering", "qilib ber", "tuzib ber", "kerak", "tashla",
        "yubor", "bormi", "ishlaylik", "yechaylik", "ko'raylik", "olaylik"
    ]
    has_task_word = any(re.search(rf"\b{t}\b", lower) for t in task_triggers)
    if not has_task_word:
        return False
    if any(re.search(rf"\b{a}\b", lower) for a in action_triggers):
        return True
    topic_words = ["excel", "vlookup", "vpr", "python", "sikil", "loop", "funksiya", "shart", "formula"]
    if any(tw in lower for tw in topic_words):
        return True
    return False


def is_task_submission(text: str) -> bool:
    """O'quvchi yechim yuborganini, skrinshot tashlaganini yoki tekshirishni so'raganini aniqlash"""
    lower = text.lower()
    submission_triggers = [
        "tekshir", "tekshirib", "togrimi", "to'g'rimi", "to'g'ri ekanmi", "togri ekanmi",
        "ishladim", "yechdim", "yechim", "kodim", "kodimni", "natija", "natijam",
        "skrinshot", "skrin", "chiqdi", "chiqmadi", "ishlamayapti", "xatosi", "qarab ber"
    ]
    return any(st in lower for st in submission_triggers)


def is_translation_request(text: str) -> bool:
    """O'quvchi tarjima so'raganini aniqlash"""
    lower = text.lower()
    trans_words = [
        "tarjima", "translate", "perevod", "inglizchaga", "ruschaga",
        "o'zbekchaga", "uzbekchaga", "inglizchadan", "ruschadan", "o'zbekchadan",
        "o'girib ber", "o'gir"
    ]
    return any(tw in lower for tw in trans_words)


def should_answer(update, text, direct, photo=False):
    chat = update.effective_chat
    user = update.effective_user
    message = getattr(update, "message", None)
    replied = getattr(message, "reply_to_message", None) if message else None
    replied_user = getattr(replied, "from_user", None) if replied else None

    # 1. ADMIN (USTOZ) XABARLARI:
    # Shaxsiy chatda admin uchun doim javob beradi.
    # Guruhda esa agar admin botga to'g'ridan-to'g'ri murojaat qilgan bo'lsa (direct),
    # yoki admin test yaratish / yakunlash buyrug'ini bergan bo'lsa:
    if user and user.id == ADMIN_ID:
        if chat and chat.type == "private":
            return True
        if re.search(r"\b(?:test|viktorina)\b.*(?:qilib|tuz|yarat|ber)|\b(?:test\s*(?:qilib|tuz|yarat|boshla)|savol\s*tuz|testni\s*tugat|test\s*tugadi)\b", (text or "").lower()):
            return True
        if is_schedule_request(text):
            return True
        return direct

    # 2. Shaxsiy chatda (1-ga-1) har doim javob beriladi
    if chat and chat.type == "private":
        return True

    # 3. Guruhda botga to'g'ridan-to'g'ri murojaat ("Pi", @bot, botga reply) qilingan bo'lsa:
    if direct:
        return True

    # 4. Agar xabar ustozga yo'naltirilgan bo'lsa yoki ustozning xabariga reply qilingan bo'lsa — AI ARALASHMAYDI!
    if is_addressed_to_teacher(text):
        return False
    if replied_user and getattr(replied_user, "id", None) == ADMIN_ID:
        return False

    # 5. Dars jadvali so'rovi (o'quvchi o'z dars jadvalini so'rasa)
    if is_schedule_request(text):
        return True

    # 6. MASALA SO'ROVI, TOPSHIRIQ YECHIMI YOKI TARJIMA SO'ROVI:
    # "ai o'zi masala bersin va skrinshot qilib natijani o'quvchi tashasa tekshirib togri bo'lsa xp bersin"
    # "lekin o'quvchila masala so'rab turgan bo'lsa javob qilaversin yoki tarjima qilib ber desa qilib bersin"
    # Admin ONLAYN bo'lsa ham, OFLAYN bo'lsa ham, bot o'quvchiga darhol masala beradi, skrinshot/yechimni tekshiradi yoki tarjima qilib beradi!
    if is_task_request(text) or is_task_submission(text) or is_translation_request(text) or photo:
        return True

    # 6.1 ANIQ AKADEMIK / DASTURLASH SAVOLLARI ("algoritm nima?", "python nima?", "funksiya qanday ishlaydi?"):
    if is_academic_question(text) and ("?" in text or is_question_like(text)):
        return True

    # 7. AGAR USTOZ (ADMIN) ONLAYN / FAOL BO'LSA:
    # "onlayn bo'ldimi javob bermasin"
    # Ustoz o'zi o'quvchilarga javob berishi uchun bot jim turadi.
    if is_admin_online():
        return False

    # 8. AGAR USTOZ (ADMIN) OFLAYN BO'LSA:
    # "admin oflaynmi darrov bot javob beraversin"
    # Guruhdagi oddiy salom-alik / o'zaro suhbat ("salom", "rahmat", "ha", "yo'q", "ok") bo'lmasa:
    if is_casual_group_chat(text):
        return False

    # Rasm (vazifa/skrinshot) yoki topshiriqning davomi bo'lsa
    if photo and not text.strip():
        return True
    if study_context.is_followup(text):
        return True

    # Admin oflayn bo'lganda o'quvchining har qanday savol, yordam yoki o'quv so'roviga darhol javob beradi!
    return is_question_like(text) or is_academic_question(text) or ("?" in text)


async def track_admin_activity(update, context):
    if (update.effective_user and update.effective_user.id == ADMIN_ID
            and update.effective_chat and update.effective_chat.type in ("group", "supergroup")):
        update_admin_activity()


def split_reply(text, limit=3500):
    # Limit UTF-16 units too: Telegram counts emoji as two units.
    chunk, size = [], 0
    for char in text:
        units = 2 if ord(char) > 0xFFFF else 1
        if size + units > limit:
            yield "".join(chunk)
            chunk, size = [], 0
        chunk.append(char)
        size += units
    if chunk:
        yield "".join(chunk)


async def send_reply(message, text):
    sent = []
    for chunk in split_reply(text):
        try:
            sent.append(await message.reply_text(chunk, parse_mode="Markdown", do_quote=True))
        except Exception:
            sent.append(await message.reply_text(chunk, do_quote=True))
    return sent


def cache_photo(message, chat_id, topic):
    if not getattr(message, "photo", None) or not getattr(message, "from_user", None):
        return
    study_context.save_photo(chat_id, topic, message.message_id, message.from_user.id,
                             message.photo[-1].file_id, message.caption or "")


async def load_study_image(telegram_bot, file_id):
    tg_file = await telegram_bot.get_file(file_id)
    stream = io.BytesIO()
    await tg_file.download_to_memory(stream)
    return stream.getvalue()


_request_times = OrderedDict()


def request_allowed(user_id):
    now = time.monotonic()
    times = _request_times.pop(user_id, deque())
    while times and now - times[0] >= 60:
        times.popleft()
    allowed = len(times) < 6
    if allowed:
        times.append(now)
    _request_times[user_id] = times
    while len(_request_times) > 5000:
        _request_times.popitem(last=False)
    return allowed


@admin_only
async def level_command(update, context):
    if not update.effective_user:
        return
    level = " ".join(context.args).lower()
    if level not in ("boshlangich", "orta"):
        await update.message.reply_text("Darajani tanlang: /daraja boshlangich yoki /daraja orta")
        return
    set_setting(f"level_{update.effective_user.id}", level)
    await update.message.reply_text("Tushuntirish darajasi saqlandi.")


def learning_context(user_id):
    level = get_setting(f"level_{user_id}", "boshlangich")
    return (f"O'quvchi darajasi: {level}. Tushuntirish, misol va kerak bo'lsa kichik mashq bering. "
            "Vazifalarda avval yo'l-yo'riq bering, to'liq yechim so'ralsa tushuntirib bering.")


@admin_only
async def payment_command(update, context):
    from datetime import date
    if update.effective_chat.type != "private":
        await update.message.reply_text("To’lovni botning shaxsiy chatida belgilang.")
        return
    try:
        if not 1 <= len(context.args) <= 2:
            raise ValueError("Buyruq: /tolandi ID [YYYY-MM] yoki /tolanmadi ID [YYYY-MM]")
        student_id = int(context.args[0])
        period = context.args[1] if len(context.args) > 1 else tashkent_now().strftime("%Y-%m")
        if not re.fullmatch(r"\d{4}-\d{2}", period):
            raise ValueError("Oy formati YYYY-MM bo’lishi kerak")
        date.fromisoformat(period + "-01")
        paid = update.message.text.split()[0].split("@")[0] == "/tolandi"
        apply_payment(student_id, period, paid, update.effective_user.id,
                      update.effective_chat.id, update.message.message_id)
    except ValueError as error:
        await update.message.reply_text(str(error))
        return
    await update.message.reply_text(f"ID {student_id}, {period}: " + ("to’langan" if paid else "to’lanmagan"))


@admin_only
async def lessons_admin_command(update, context):
    from datetime import date
    if update.effective_chat.type != "private":
        await update.message.reply_text("Darslarni boshqarish uchun botning shaxsiy chatidan foydalaning.")
        return
    command = update.message.text.split()[0].split("@")[0]
    try:
        if command == "/darslar":
            target = date.fromisoformat(context.args[0]) if context.args else tashkent_now().date()
            lessons = get_lessons_for_date(target)
            await send_reply(update.message, "\n".join(
                f"ID {l['id']} | {l['lesson_date']} {l['lesson_time']} | {l['student_name']} | {l['course_name']}"
                for l in lessons) or "Bu sanaga faol dars yo’q.")
            return
        if command == "/dars_bekor" and len(context.args) == 1:
            change_lesson(int(context.args[0]))
        elif command == "/dars_kochirish" and len(context.args) == 3:
            change_lesson(int(context.args[0]), context.args[1], context.args[2])
        else:
            raise ValueError("Buyruqlar: /darslar [YYYY-MM-DD], /dars_bekor ID, /dars_kochirish ID YYYY-MM-DD HH:MM")
    except ValueError as error:
        await update.message.reply_text(str(error))
        return
    await update.message.reply_text("Dars yangilandi. Shu oy Excel jadvali qayta import qilinsa, Excel qiymatlari ustun keladi.")


@admin_only
async def diagnostics_command(update, context):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Diagnostikani botning shaxsiy chatida oching.")
        return
    from ai_service import last_ai_error, usage_today
    await update.message.reply_text(
        f"Bot ishlayapti. Model: {__import__('config').OPENAI_MODEL}\n"
        f"Eslatma guruhi: {get_setting('main_group_id', 'belgilanmagan')}\n"
        f"Oxirgi AI xatosi: {last_ai_error or 'qayd etilmagan'}\n"
        f"Bugungi API sarfi: {usage_today()}\n"
        f"Oxirgi Excel importi: {get_setting('last_excel_import', 'qayd etilmagan')}"
    )


@admin_only
async def new_conversation_command(update, context):
    if not update.effective_user or not update.message:
        return
    clear_history(update.effective_chat.id, update.effective_user.id)
    study_context.clear(update.effective_chat.id, update.effective_user.id)
    await update.message.reply_text("Shu chatdagi suhbat xotirangiz tozalandi. Yangi savol bering!")


# ----------------- ADMIN VA GURUH SOZLAMALARI -----------------

@admin_only
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchining shaxsiy Telegram ID raqamini ko'rsatish"""
    user = update.effective_user
    chat = update.effective_chat
    
    reply_msg = (
        f"👤 **Foydalanuvchi:** {user.full_name}\n"
        f"🆔 **Sizning Telegram ID:** `{user.id}`\n\n"
        "*(Raqam ustiga bossangiz, avtomatik nusxalanadi. Ushbu ID raqamni adminga bering)*"
    )
    if chat.type in ["group", "supergroup"]:
        reply_msg += f"\n\n👥 **Guruh ID:** `{chat.id}`"
        
    await update.message.reply_text(reply_msg, parse_mode="Markdown")

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot boshlanganda xush kelibsiz xabari"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type != "private":
        await update.message.reply_text("Buyruqlar ro'yxati botning shaxsiy chatida: /help")
        return
    await send_reply(update.message, ADMIN_HELP)


@admin_only
async def set_online_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin o'zini onlayn rejimiga o'tkazishi"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return
    set_setting("admin_manual_status", "online")
    update_admin_activity()
    await update.message.reply_text("🟢 **Siz ONLAYN holatdasiz.**\nBot faqat Pi deb chaqirilganda, mention yoki reply bo’lganda javob beradi.", parse_mode="Markdown")

@admin_only
async def set_offline_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin o'zini oflayn rejimiga o'tkazishi"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return
    set_setting("admin_manual_status", "offline")
    await update.message.reply_text("🔴 **Siz OFLAYN holatdasiz.**\nBot guruhdagi barcha savollarga AI orqali avtomatik javob berib turadi.", parse_mode="Markdown")

@admin_only
async def set_auto_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin holatini avtomatik rejimga o'tkazish"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return
    set_setting("admin_manual_status", "auto")
    await update.message.reply_text("🔄 **AVTOMATIK rejim yoqildi.**\nAgar 5 daqiqa guruhda xabar yozmasangiz, bot oflayn deb hisoblab savollarga javob beradi.", parse_mode="Markdown")

@admin_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Joriy rejim va admin holati"""
    online = is_admin_online()
    mode = get_setting("admin_manual_status", "auto")
    holat_str = "🟢 ONLAYN (Faqat botga murojaatlarga javob)" if online else "🔴 OFLAYN (Bot savollarga javob beradi)"
    
    await update.message.reply_text(
        f"📊 **Admin holati:** {holat_str}\n"
        f"⚙️ Rejim: `{mode}`\n\n"
        "Buyruqlar (faqat admin uchun):\n"
        "👉 /online - Onlayn qilish\n"
        "👉 /offline - Oflayn qilish\n"
        "👉 /auto - Avtomatik (5 daqiqa jim tursangiz bot ishlaydi)",
        parse_mode="Markdown"
    )

@admin_only
async def set_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhni asosiy eslatmalar guruhi qilib belgilash"""
    chat = update.effective_chat
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ Bu buyruqni faqat Telegram guruhda ishlatish kerak!")
        return
        
    set_setting("main_group_id", str(chat.id))
    set_setting("main_group_title", chat.title or "Pi Akademiya Guruhi")
    await configure_command_menus(context.bot)
    
    await update.message.reply_text(
        f"✅ Ushbu guruh (**{chat.title}**) asosiy eslatmalar guruhi sifatida muvaffaqiyatli saqlandi!\n"
        f"ID: `{chat.id}`\n\n"
        "Endi to'lov va dars eslatmalari avtomatik ravishda mana shu guruhga yuboriladi.",
        parse_mode="Markdown"
    )

@admin_only
async def bugun_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bugungi darslar jadvalini chiqarish"""
    today_day = tashkent_now().day
    lessons = get_lessons_for_date(tashkent_now().date())
    
    course = " ".join(context.args).casefold()
    if course:
        lessons = [l for l in lessons if course in (l["course_name"] or "").casefold()]

    if not lessons:
        await update.message.reply_text(f"Bugun ({today_day}-sana) uchun darslar jadvalda belgilanmagan yoki dam olish kuni.")
        return
        
    # Vaqtlar bo'yicha guruhlaymiz
    by_time = {}
    for l in lessons:
        t = l["lesson_time"]
        if t not in by_time:
            by_time[t] = []
        by_time[t].append(f"{l['student_name']} ({l['course_name'] or 'Kurs'})")
        
    text = f"📅 **Bugungi darslar jadvali ({today_day}-sana):**\n\n"
    for t in sorted(by_time.keys()):
        students_str = "\n   ▫️ " + "\n   ▫️ ".join(by_time[t])
        text += f"⏰ **Soat {t}:**\n{students_str}\n\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")

@admin_only
async def ertaga_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ertangi darslar jadvali"""
    tomorrow = tashkent_now() + timedelta(days=1)
    tomorrow_day = tomorrow.day
    lessons = get_lessons_for_date(tomorrow.date())
    
    course = " ".join(context.args).casefold()
    if course:
        lessons = [l for l in lessons if course in (l["course_name"] or "").casefold()]

    if not lessons:
        await update.message.reply_text(f"Ertaga ({tomorrow_day}-sana) uchun darslar jadvalda belgilanmagan.")
        return
        
    by_time = {}
    for l in lessons:
        t = l["lesson_time"]
        if t not in by_time:
            by_time[t] = []
        by_time[t].append(f"{l['student_name']} ({l['course_name'] or 'Kurs'})")
        
    text = f"📅 **Ertangi darslar jadvali ({tomorrow_day}-sana):**\n\n"
    for t in sorted(by_time.keys()):
        students_str = "\n   ▫️ " + "\n   ▫️ ".join(by_time[t])
        text += f"⏰ **Soat {t}:**\n{students_str}\n\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")

@admin_only
async def tolovlar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha o'quvchilarning to'lov sanalari"""
    if update.effective_chat.type != "private":
        await update.message.reply_text("To’lovlar ro’yxatini botning shaxsiy chatida oching: /tolovlar")
        return
    students = get_all_students()
    if not students:
        await update.message.reply_text("Hozircha bazada o'quvchilar yo'q.")
        return
        
    period = tashkent_now().strftime("%Y-%m")
    paid_ids = get_paid_students(period)
    text = f"💳 O’quvchilar to’lovlari ({period}):\n\n"
    for idx, s in enumerate(students, start=1):
        user_str = f" (@{s['username']})" if s.get("username") else ""
        text += f"{idx}. ID {s['id']} | {'To’langan' if s['id'] in paid_ids else 'To’lanmagan'} | **{s['name']}**{user_str}\n   📚 Kurs: {s.get('course_name') or '-'}\n   🗓 To'lov: har oyning **{s['due_day']}-sanasigacha**\n\n"
        
    await send_reply(update.message, text)

@admin_only
async def excel_yangilash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lokal Excel fayldan bazani qayta yangilash"""
    if not os.path.exists(EXCEL_LOCAL_PATH):
        await update.message.reply_text(f"⚠️ `{EXCEL_LOCAL_PATH}` fayli topilmadi!")
        return
        
    try:
        import_pi_academy_excel(str(EXCEL_LOCAL_PATH), dry_run=True)
        backup_data()
        res = import_pi_academy_excel(str(EXCEL_LOCAL_PATH))
        await update.message.reply_text(
            f"✅ **Excel ma'lumotlari muvaffaqiyatli yangilandi!**\n\n"
            f"👤 O'quvchilar soni: **{res['students_imported']} ta**\n"
            f"📖 Darslar dars jadvali soni: **{res['lessons_imported']} ta**\n"
            f"📊 Varaqlar: `{res['payment_sheet']}` va `{res['schedule_sheet']}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Excel o'qishda xatolik: {e}")

# ----------------- TELEGRAMDAN EXCEL FAYL QABUL QILISH -----------------

@admin_only
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin yoki foydalanuvchi Excel fayl yuborganida uni qabul qilib bazaga yuklash"""
    doc = update.message.document
    if not doc:
        return
        
    file_name = doc.file_name or ""
    if not file_name.lower().endswith(".xlsx"):
        await update.message.reply_text("Excel faylni .xlsx formatida yuboring.")
        return
    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        await update.message.reply_text("Excel fayl 10 MB dan kichik bo’lishi kerak.")
        return
    if file_name.lower().endswith(".xlsx"):
        msg = await update.message.reply_text("📥 Excel fayl qabul qilinmoqda va tahlil qilinmoqda...")
        try:
            tg_file = await context.bot.get_file(doc.file_id)
            file_bytes = io.BytesIO()
            await tg_file.download_to_memory(file_bytes)
            file_bytes.seek(0)
            
            with tempfile.TemporaryDirectory(dir=BASE_DIR) as temp_dir:
                staged = os.path.join(temp_dir, "jadval.xlsx")
                with open(staged, "wb") as f:
                    f.write(file_bytes.read())
                import_pi_academy_excel(staged, dry_run=True)
                backup = backup_data()
                # Both validation and backup finish before the live file changes.
                os.replace(staged, EXCEL_LOCAL_PATH)
                try:
                    res = import_pi_academy_excel(str(EXCEL_LOCAL_PATH))
                except Exception:
                    previous = backup / EXCEL_LOCAL_PATH.name
                    if previous.exists():
                        shutil.copy2(previous, EXCEL_LOCAL_PATH)
                    raise
            set_setting("last_excel_import", f"{tashkent_now().isoformat()} admin={update.effective_user.id}")
            await msg.edit_text(
                f"🎉 **Excel fayl muvaffaqiyatli yuklandi va bazaga kiritildi!**\n\n"
                f"👤 O'quvchilar: **{res['students_imported']} ta**\n"
                f"📅 Kiritilgan dars soatlari: **{res['lessons_imported']} ta**\n\n"
                f"Endi bot yangilangan to'lov va dars jadvali asosida eslatmalarni yuboradi!",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Excel yuklash xatoligi: {e}", exc_info=True)
            await msg.edit_text(f"❌ Excel faylni yuklashda xatolik yuz berdi: {e}")



def is_question_like(text: str) -> bool:
    """Matn savol, salomlashish yoki yordam so'rovi ekanligini aniqlash"""
    lower = text.lower()
    if "?" in text:
        return True
    triggers = [
        "qanday", "qanaqa", "nima", "qachon", "qayerda", "nechanchi",
        "tushuntir", "yechib", "yordam", "xato", "ishlamayapti", "kod",
        "misol", "vazifa", "savol", "masala", "funksiya", "dastur",
        "mumkinmi", "kerakmi", "bilasizmi", "aytib bering", "gapir",
        "salom", "assalom", "assalomu alaykum", "privet", "hello", "hi",
        "qalesiz", "qalaysiz", "qandaysiz", "yaxshimisiz", "tushunmadim",
        "o'rgat", "tavsiya", "maslahat", "ko'rib ber", "bormi", "bormikin",
        "o'qish", "kurs", "dars"
    ]
    return any(trig in lower for trig in triggers)

# ----------------- TIZIM XABARLARINI TOZALASH (SERVICE MESSAGES) -----------------

async def clean_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Guruhdagi 'qo'shildi', 'chiqib ketdi', 'zakrepil' (pinned) kabi barcha tizim xabarlarini
    avtomatik o'chirib tashlash. Guruh chatini doimo toza va professional saqlaydi.
    """
    message = update.message
    if not message:
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return

    # Yangi a'zolar kirganda Telegram profilini jimjit bazaga qayd qilib olamiz
    if message.new_chat_members:
        for new_user in message.new_chat_members:
            if not new_user.is_bot:
                register_member(new_user, chat.id)

    # Guruhdagi 'qo'shildi', 'chiqib ketdi', 'zakrepil' yozuvini darhol o'chirib tashlaymiz
    try:
        await message.delete()
        logger.info("Tizim xabari (service message) avtomatik o'chirildi (Chat: %s, Msg: %s)", chat.id, message.message_id)
    except Exception as e:
        logger.debug("Tizim xabarini o'chirishda xatolik: %s", e)

# ----------------- RASMLI SAVOLLARNI TAHLIL QILISH (VISION) -----------------

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy chat va guruhdagi rasmlarni OpenAI orqali tahlil qilish"""
    chat = update.effective_chat
    if not chat or chat.type not in ["private", "group", "supergroup"]:
        return

    message = update.message
    if not message or not message.photo:
        return
        
    user = update.effective_user
    topic = getattr(message, "message_thread_id", None) or 0
    if user and isinstance(getattr(message, "message_id", None), int):
        study_context.save_photo(chat.id, topic, message.message_id, user.id,
                                 message.photo[-1].file_id, message.caption or "")
    bot_username = (await context.bot.get_me()).username.lower()
    caption = (message.caption or "").strip()
    is_quiz_req = bool(re.search(r"\b(?:test|viktorina)\b.*(?:qilib|tuz|yarat|ber)|\b(?:test\s*(?:qilib|tuz|yarat|boshla)|savol\s*tuz)\b", caption.lower()))
    direct = direct_request(message, chat, context.bot, caption)

    if user and user.id == ADMIN_ID and is_quiz_req:
        is_addressed_to_bot = True
    else:
        is_addressed_to_bot = bool(user) and should_answer(update, caption, direct, photo=True)

    if is_addressed_to_bot:
        if not request_allowed(user.id):
            await message.reply_text("Bir daqiqada 6 ta AI so’roviga ruxsat beriladi. Biroz kuting.")
            return
        status_text = "⏳ Rasm tahlil qilinib, 10 talik test (Quiz Poll) tayyorlanmoqda..." if is_quiz_req else "👀 Rasmni ko'rib tahlil qilyapman, bir daqiqa..."
        status_msg = await message.reply_text(status_text, do_quote=True)
        try:
            photo = message.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            img_stream = io.BytesIO()
            await tg_file.download_to_memory(img_stream)
            img_bytes = img_stream.getvalue()
            
            clean_caption = caption.replace(f"@{bot_username}", "").strip()
            user_name = user.first_name if user else "Talaba"

            # Agar rasm yuborilib "test qilib ber" / "test tuz" deb yozilgan bo'lsa:
            if is_quiz_req:
                active_sessions = get_active_quiz_sessions(chat.id)
                if active_sessions:
                    context.chat_data["pending_quiz"] = {
                        "text": None,
                        "img_bytes": img_bytes,
                        "caption_hint": clean_caption,
                        "user_id": user.id if user else ADMIN_ID,
                        "reply_to_message_id": message.message_id,
                        "message_thread_id": topic
                    }
                    with suppress(Exception):
                        await status_msg.delete()
                    await prompt_existing_quiz_action(chat.id, active_sessions, message, context)
                    return

                quiz_data = await generate_quiz_from_ai(image_bytes=img_bytes, caption_hint=clean_caption)
                if quiz_data.get("success"):
                    await status_msg.delete()
                    await launch_quiz_session(chat.id, user.id, quiz_data, context, reply_to_message_id=message.message_id, message_thread_id=topic)
                    return
                else:
                    await status_msg.edit_text(f"⚠️ Test tuzishda xatolik: {quiz_data.get('error', 'AI test shakllantira olmadi')}")
                    return

            ai_reply = await analyze_image_with_ai(img_bytes, clean_caption, user_name,
                                                         conversation_key=(chat.id, user.id))

            # Gamifikatsiya — skrinshot / topshiriq to'g'ri yechilganini tekshirish
            is_task_correct = "[VAZIFA_TOGRI]" in ai_reply
            display_reply = ai_reply.replace("[VAZIFA_TOGRI]", "").strip()

            st_rec = find_student_by_user(user)
            xp_banner = ""
            if is_task_correct:
                if st_rec and not (user and user.id == ADMIN_ID):
                    xp_res = add_student_xp(st_rec["id"], st_rec["name"], 25, is_task=True, course_name=st_rec.get("course_name"))
                    congrats = f"\n🎉 **Yangi daraja ochildi:** {xp_res['title']}!" if xp_res.get("level_up") else ""
                    xp_banner = f"\n\n🎯 **+25 XP** topshiriq to'g'ri bajarilgani uchun berildi!\n🏆 Joriy balingiz: **{xp_res['new_xp']} XP** ({xp_res['title']}){congrats}"
                    asyncio.create_task(update_pinned_leaderboard(context.bot))
                elif not st_rec and not (user and user.id == ADMIN_ID):
                    xp_banner = "\n\n🎯 **Topshiriq to'g'ri bajarildi!** Ballar reytingiga qo'shilish uchun profilingizni adminga bog'lating."

            final_reply = display_reply + xp_banner
            chunks = list(split_reply(final_reply))
            await status_msg.edit_text(chunks[0])
            if isinstance(getattr(message, "message_id", None), int):
                study_context.link_message(chat.id, topic, getattr(status_msg, "message_id", None), message.message_id, final_reply, owner=user.id)
            for chunk in chunks[1:]:
                sent = await send_reply(message, chunk)
                if isinstance(getattr(message, "message_id", None), int):
                    for item in sent:
                        study_context.link_message(chat.id, topic, getattr(item, "message_id", None), message.message_id, final_reply, owner=user.id)
            try:
                log_student_activity(
                    student_id=st_rec["id"] if st_rec else None,
                    student_name=st_rec["name"] if st_rec else getattr(user, "full_name", "Talaba"),
                    telegram_id=getattr(user, "id", None),
                    question=f"[Rasm tahlili] {clean_caption}",
                    ai_response=final_reply
                )
            except Exception as e:
                logger.warning("Rasm savolini qayd etishda xatolik: %s", e)
        except Exception as e:
            logger.error(f"Rasm qayta ishlash xatoligi: {e}", exc_info=True)
            await status_msg.edit_text("Kechirasiz, rasmni tahlil qilishda xatolik yuz berdi.")


def is_admin_talking_to_student(message, text: str) -> bool:
    """
    Admin guruhda o'quvchiga yoki butun guruh o'quvchilariga murojaat qilayotganini aniqlash:
    - O'quvchining xabariga reply qilingan bo'lsa
    - O'quvchi @username'i ko'rsatilgan bo'lsa
    - Xabar ichida o'quvchi ismi zikr qilingan bo'lsa (boshida, o'rtasida yoki oxirida: masalan 'senga javob bermaydi anvar', 'Murod vazifang qani')
    - Butun guruh o'quvchilariga murojaat/ko'rsatma bo'lsa ('hammangiz', 'kechikmang', 'vazifangizni')
    """
    if not message or not text:
        return False

    replied = getattr(message, "reply_to_message", None)
    replied_user = getattr(replied, "from_user", None) if replied else None
    if replied_user and not getattr(replied_user, "is_bot", False):
        return True

    lower = text.lower().strip()
    for u in re.findall(r"@([a-zA-Z0-9_]+)", lower):
        if "bot" not in u and "pi" not in u:
            return True

    # O'quvchilar ro'yxatidagi ismlar zikr qilingan bo'lsa
    is_inquiry_about_student = bool(re.search(
        r"to'la|tola|to'lov|tolov|"
        r"o'zlashtir|ozlashtir|tushunm|tushuny|qiynal|ahvoli|o'qiy|oqiy|darajasi|bilimi|"
        r"jadval|dars|qarz|bog'la|bogla",
        lower
    ))

    words = re.findall(r"[a-zA-Z‘'ʻʼ]+", lower)
    tokens = {strip_uzbek_suffixes(w) for w in words} | set(words)

    students = get_all_students()
    for s in students:
        s_names = [p.lower() for p in s["name"].split() if len(p) >= 3]
        for name_part in s_names:
            if name_part in tokens:
                # Agar o'quvchi haqida botga so'rov berilayotgan bo'lsa (jadval, to'lov, o'zlashtirish) -> bu murojaat emas
                if is_inquiry_about_student:
                    continue
                return True

    if re.search(r"\b(?:hammangiz|hamma|bolalar|o'quvchilar|kechikmang|kechikmanglar|vazifangizni|vazifani topshiring|darsga keling|darsni boshlaymiz)\b", lower):
        return True

    return False


async def handle_admin_natural_query(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """
    Admin buyruqlarini "/" belgisiz, to'g'ridan-to'g'ri tabiiy tilda qayta ishlash.
    Misol:
    - 'murodni dars jadvali'
    - 'murodning to'lovi' yoki 'murod to'ladimi?'
    - 'murodning o'zlashtirishi qanday' yoki 'murod nimalarni tushunmayapti'
    - 'kimlar to'lamadi?' yoki 'qarzdorlar ro'yxati'
    - 'bugungi darslar' / 'ertangi darslar'
    - 'o'quvchilar ro'yxati'
    - 'excelni yangila'
    - 'bot holati', 'onlayn bo'l', 'oflayn bo'l', 'avtomatik rejim'
    """
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        return False

    message = update.message
    chat = update.effective_chat
    is_group = bool(chat and chat.type in ("group", "supergroup"))
    replied = getattr(message, "reply_to_message", None) if message else None
    replied_user = getattr(replied, "from_user", None) if replied else None
    is_reply_to_human = bool(is_group and replied_user and not getattr(replied_user, "is_bot", False))

    lower = text.lower().strip()

    # Agar guruhda ustoz o'quvchining xabariga reply qilayotgan bo'lsa:
    # Faqat "bog'la" yoki manual XP berish ("+10 xp") buyruqlari ishlaydi.
    # Boshqa hollarda ustoz o'quvchisi bilan gaplashmoqda, bot aslo aralashmaydi!
    if is_reply_to_human:
        is_binding = any(k in lower for k in ["bog'la", "bogla", "bog'lash", "boglash"])
        is_manual_xp = bool(re.search(r"\b(?:\+?\d+)\s*(?:xp|ball)\b", lower))
        if not is_binding and not is_manual_xp:
            return False

    period = tashkent_now().strftime("%Y-%m")

    # 0. TESTNI YAKUNLASH YOKI FAOL TESTLARNI SO'RASH ("testni tugat", "qaysi testni tugatish kerak", "faol testlar")
    if re.search(r"\btest(?:ni)?\s*(?:tugat|to'xtat|toxtat|yakunla|yop)|\btest\s*tugadi\b|\bqaysi\s*test\b|\btestlar\s*ro'yxati\b|\bfaol\s*test\b", lower):
        if await handle_finish_quiz(chat.id, message, context):
            return True

    # 0.01 TESTLAR BAZASI STATISTIKASI ("testlar bazasi", "bazada nechta test", "testlar soni")
    if re.search(r"\btest(?:lar)?\s*bazas?i?\b|\bbazada\s*nechta\s*test\b|\btestlar\s*soni\b", lower):
        stats = get_quiz_bank_stats()
        total_q = stats["total"]
        cat_lines = []
        for cat, cnt in stats["categories"].items():
            icon = "🐍" if cat == "python" else ("📊" if cat == "excel" else ("🤖" if cat == "robototexnika" else "🖥"))
            cat_lines.append(f"  • {icon} **{cat.capitalize()}:** {cnt} ta savol")
        cats_str = "\n".join(cat_lines) if cat_lines else "  Hozircha savollar mavjud emas."
        resp = (
            f"📚 **DOIMIY TESTLAR BAZASI (QUESTION BANK)** 🎯\n\n"
            f"Jami eslab qolingan savollar: **{total_q} ta**\n\n"
            f"Yo'nalishlar bo'yicha:\n{cats_str}\n\n"
            f"💡 *Bazada to'plangan savollardan tasodifiy test olish uchun:\n"
            f"👉 'random test tashla' yoki 'pythondan random test ber' deb yozing!*"
        )
        await send_reply(message, resp)
        return True

    # 0.02 RANDOM TEST SO'ROVI ("random test tashla", "pythonda random test", "tasodifiy test", "bazadan test")
    is_random_req = bool(re.search(r"\b(?:random|tasodifiy|baza(?:dan)?)\s*test\b|\btest\s*(?:tashla|ber|qil|boshla)\b.*\b(?:random|tasodifiy)\b|\b(?:random|tasodifiy)\b.*\btest\b", lower))
    if is_random_req:
        active_sessions = get_active_quiz_sessions(chat.id)
        topic_id = getattr(message, "message_thread_id", None)

        if "excel" in lower:
            cat = "excel"
        elif "robot" in lower:
            cat = "robototexnika"
        elif "kompyuter" in lower or "savodxonlik" in lower or "word" in lower:
            cat = "kompyuter"
        else:
            cat = "python" # Foydalanuvchi so'raganidek odatiy Python yo'nalishi

        if active_sessions:
            context.chat_data["pending_quiz"] = {
                "is_random_bank": True,
                "category": cat,
                "user_id": user.id if user else ADMIN_ID,
                "reply_to_message_id": message.message_id,
                "message_thread_id": topic_id
            }
            await prompt_existing_quiz_action(chat.id, active_sessions, message, context)
            return True

        quiz_data = get_random_quiz_from_bank(category=cat, count=10)
        if not quiz_data:
            await send_reply(message, f"⚠️ Testlar bazasida {cat.capitalize()} yo'nalishi bo'yicha hozircha savollar yetarli emas.")
            return True

        await launch_quiz_session(chat.id, user.id, quiz_data, context, reply_to_message_id=message.message_id, message_thread_id=topic_id)
        return True

    # 0.1 MATNDAN YOKI REPLY QILINGAN RASMDAN TEST TUZISH ("test qilib ber", "test tuz", "test yarat")
    if re.search(r"\btest\s*(?:qilib\s*ber|tuz|yarat|boshla|qil)\b|\bmavzudan\s*test\b|\bviktorina\s*tuz\b|\b10\s*talik\s*test\b", lower):
        active_sessions = get_active_quiz_sessions(chat.id)
        replied_photo = getattr(replied, "photo", None) if replied else None
        img_bytes = None
        if replied_photo:
            photo = replied_photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            img_stream = io.BytesIO()
            await tg_file.download_to_memory(img_stream)
            img_bytes = img_stream.getvalue()

        content_text = text
        if replied and (getattr(replied, "text", None) or getattr(replied, "caption", None)):
            content_text = (getattr(replied, "text", None) or getattr(replied, "caption", None)) + "\n" + text

        topic_id = getattr(message, "message_thread_id", None)

        # Agar oldin boshlangan faol test bo'lsa, adminga avval uni nima qilishni so'raymiz
        if active_sessions:
            context.chat_data["pending_quiz"] = {
                "text": content_text,
                "img_bytes": img_bytes,
                "caption_hint": text,
                "user_id": user.id if user else ADMIN_ID,
                "reply_to_message_id": message.message_id,
                "message_thread_id": topic_id
            }
            await prompt_existing_quiz_action(chat.id, active_sessions, message, context)
            return True

        status_msg = await message.reply_text("⏳ Mavzu tahlil qilinib, 10 talik test (Quiz Poll) tayyorlanmoqda...")
        quiz_data = await generate_quiz_from_ai(text=content_text, image_bytes=img_bytes, caption_hint=text)
        if quiz_data.get("success"):
            await status_msg.delete()
            await launch_quiz_session(chat.id, user.id, quiz_data, context, reply_to_message_id=message.message_id, message_thread_id=topic_id)
            return True
        else:
            await status_msg.edit_text(f"⚠️ Test tuzishda xatolik: {quiz_data.get('error', 'AI javob bermadi')}")
            return True

    # 1. O'QUVCHI O'ZLASHTIRISHI VA DIAGNOSTIKA
    if re.search(r"o'zlashtir|ozlashtir|tushunmayapti|tushunmadi|tushunyapti|qiynalyapti|ahvoli|o'qiyapti|oqiyapti|darajasi|bilimi", lower):
        target = extract_target_student_name(text)
        matches = find_matching_students(target) if target else []
        if not matches:
            matches = find_matching_students(text)
        if len(matches) > 1:
            choices = "\n".join([f"  • **ID #{s['id']}**: {s['name']} ({s.get('course_name') or 'Kurs'})" for s in matches])
            await send_reply(
                message,
                f"⚠️ **Bazada bir nechta o'quvchi mavjud:**\n{choices}\n\n"
                f"Noaniqlik bo'lmasligi uchun aniq ID raqami orqali so'rang (masalan: `ID {matches[0]['id']} o'zlashtirishi qanday?`)."
            )
            return True

        student = matches[0] if len(matches) == 1 else None
        if not student and target:
            await send_reply(message, f"👤 **'{target}'** ismli o'quvchi bazadan topilmadi.\nBarcha o'quvchilarni ko'rish uchun *'o'quvchilar ro'yxati'* deb yozing.")
            return True

        if student:
            paid_ids = get_paid_students(period)
            is_paid = student["id"] in paid_ids
            logs = get_student_learning_logs(student_id=student["id"], student_name=student["name"], limit=15)

            # Agar ustoz dars jadvalini ham birga so'ragan bo'lsa (masalan: "anvarni dars jadvalini o'zlashtirishini ko'rsat ayt"):
            schedule_prefix = ""
            if re.search(r"dars jadval|jadval", lower):
                schedule_prefix = format_student_weekly_schedule(student) + "\n\n────────────────────────\n\n"

            if logs:
                status_msg = await message.reply_text(f"⏳ **{student['name']}**ning so'nggi faolligi va savollari GPT-4o orqali tahlil qilinmoqda...")
                logs_text = "\n".join([
                    f"- [{l.get('created_at','')[:16]}] Savol: {l['question']}\n  AI javobi: {l.get('ai_response','')[:200]}..."
                    for l in logs
                ])
                analysis_prompt = (
                    f"Siz 'Cyber Tech Academy' o'quv markazining bosh o'qituvchisi va ta'lim tahlilchisisiz.\n"
                    f"Admin (rahbar) sizdan o'quvchi haqida so'ramoqda: '{text}'\n\n"
                    f"O'QUVCHI PROFILI:\n"
                    f"- Ismi: {student['name']}\n"
                    f"- Kursi: {student.get('course_name') or 'Nomaʼlum'}\n"
                    f"- To'lov kuni: Har oyning {student.get('due_day')}-sanasi ({'Toʻlangan' if is_paid else 'Toʻlanmagan/Qarzdor'})\n\n"
                    f"O'QUVCHINING SO'NGGI SAVOL-JAVOBLARI (BOT BILAN FAOLIYATI):\n"
                    f"{logs_text}\n\n"
                    f"Quyidagi tuzilmada lo'nda, aniq, pedagogik va tushunarli hisobot taqdim eting:\n"
                    f"📊 **O'QUVCHI TAHLILI: {student['name']}**\n"
                    f"📚 **Kurs:** {student.get('course_name') or 'Kurs'}\n\n"
                    f"1. 📌 **Qaysi mavzular ustida ishlagan:** (qisqacha)\n"
                    f"2. ⚠️ **Nimalarni tushunmayapti / qiynalmoqda:** (aniq muammolari)\n"
                    f"3. 📈 **O'zlashtirish va faollik darajasi:**\n"
                    f"4. 💡 **O'qituvchiga tavsiya:**"
                )
                ai_reply = await ask_ai(analysis_prompt, user_name="Admin", direct=True)
                if ai_reply:
                    await status_msg.edit_text(schedule_prefix + ai_reply, parse_mode="Markdown")
                    return True
                else:
                    await status_msg.delete()

            # Tarix hali bo'lmasa:
            due_day = student.get("due_day", "-")
            phone = student.get("phone") or "Kiritilmagan"
            text_resp = (
                f"📊 **O'QUVCHI MA'LUMOTI VA TAHLILI**\n\n"
                f"👤 **O'quvchi:** {student['name']}\n"
                f"📚 **Kurs:** {student.get('course_name') or 'Kiritilmagan'}\n"
                f"🗓 **To'lov sanasi:** Har oyning {due_day}-sanasi\n"
                f"💳 **To'lov holati ({period}):** {'✅ To‘langan' if is_paid else '⚠️ To‘lanmagan'}\n"
                f"📞 **Telefon:** {phone}\n"
                f"🆔 **ID:** {student['id']}\n\n"
                f"ℹ️ **O'zlashtirish tahlili:**\n"
                f"Ushbu o'quvchi hozircha bot orqali savol yoki vazifa yo'llamagan (yangi qo'shilgan yoki dars bo'yicha savol bermagan).\n"
                f"O'quvchi dasturlash (Python), Excel yoki kompyuter savodxonligi bo'yicha botga savol berishi bilan barcha tushunmagan mavzulari va qiyinchiliklari bu yerda tahlil qilib boriladi."
            )
            await send_reply(message, schedule_prefix + text_resp)
            return True

        # Umumiy o'quvchilar tahlili so'ralgan bo'lsa:
        all_logs = get_student_learning_logs(limit=25)
        if all_logs:
            status_msg = await message.reply_text("⏳ O'quvchilarning umumiy faolligi tahlil qilinmoqda...")
            default_student_name = "O'quvchi"
            logs_text = "\n".join([f"- {l.get('student_name', default_student_name)}: {l['question']}" for l in all_logs])
            summary_prompt = (
                f"Siz Cyber Tech Academy ta'lim tahlilchisisiz. Admin so'radi: '{text}'.\n"
                f"O'quvchilarning oxirgi savollari:\n{logs_text}\n\n"
                f"O'quvchilar asosan qaysi mavzularda savol berayotgani, nimalarda qiynalayotgani haqida adminga qisqa va aniq xulosa bering."
            )
            ai_reply = await ask_ai(summary_prompt, user_name="Admin", direct=True)
            if ai_reply:
                await status_msg.edit_text(ai_reply, parse_mode="Markdown")
                return True
            else:
                await status_msg.delete()

    # 2. TO'LOVLAR NAZORATI VA QARZDORLAR
    if re.search(r"to'lov|tolov|to'ladimi|toladimi|to'laganmi|tolaganmi|qarzdor|to'lamadi|tolamadi", lower):
        # A. Qarzdorlar ro'yxati yoki "kimlar to'lamadi"
        if re.search(r"kimlar|kim\b|hamma|ro'yxat|royxat|qarzdor", lower):
            students = get_all_students()
            paid_ids = get_paid_students(period)
            unpaid = [s for s in students if s["id"] not in paid_ids]

            if not unpaid:
                await send_reply(message, f"🎉 **Ajoyib!** Barcha {len(students)} nafar o'quvchi {period} oyi uchun to'lov qilgan.")
                return True

            text_resp = f"⚠️ **TO'LOV QILMAGANLAR RO'YXATI ({period}):**\n"
            text_resp += f"Jami qarzdorlar: **{len(unpaid)} nafar** (jami {len(students)} ta o'quvchidan)\n\n"
            for idx, s in enumerate(unpaid, 1):
                phone_str = f" ┆ 📞 {s['phone']}" if s.get("phone") else ""
                text_resp += f"{idx}. **{s['name']}**\n   📚 {s.get('course_name') or 'Kurs'} ┆ 🗓 {s.get('due_day')}-sana{phone_str}\n"
            text_resp += "\n💡 *To'lovni kiritish uchun: 'Ism to'ladi' deb yozing (masalan: Murod to'ladi).*"
            await send_reply(message, text_resp)
            return True

        # B. Muayyan o'quvchi to'lovi ("murodning to'lovi", "murod to'ladimi?", "murod to'laganmi?")
        target = extract_target_student_name(text)
        matches = find_matching_students(target) if target else []
        if not matches:
            matches = find_matching_students(text)
        if len(matches) > 1:
            choices = "\n".join([f"  • **ID #{s['id']}**: {s['name']} ({s.get('course_name') or 'Kurs'})" for s in matches])
            await send_reply(
                message,
                f"⚠️ **Bazada bir nechta o'quvchi mavjud:**\n{choices}\n\n"
                f"Noaniqlik bo'lmasligi uchun aniq ID raqami orqali so'rang (masalan: `ID {matches[0]['id']} to'ladimi?`)."
            )
            return True
        student = matches[0] if len(matches) == 1 else None
        if student:
            paid_ids = get_paid_students(period)
            is_paid = student["id"] in paid_ids
            due_day = student.get("due_day", "-")
            phone = student.get("phone") or "Kiritilmagan"
            status_icon = "✅ To'langan" if is_paid else "❌ To'lanmagan (Qarzdor)"
            resp = (
                f"💳 **TO'LOV HOLATI**\n\n"
                f"👤 **O'quvchi:** {student['name']}\n"
                f"📚 **Kurs:** {student.get('course_name') or 'Kurs'}\n"
                f"🗓 **To'lov sanasi:** Har oyning {due_day}-sanasi\n"
                f"💵 **Holat ({period}):** {status_icon}\n"
                f"📞 **Telefon:** {phone}\n"
                f"🆔 **ID:** {student['id']}\n\n"
                f"💡 *To'lov holatini o'zgartirish uchun: '{student['name']} to'ladi' yoki '{student['name']} to'lamadi' deb yozishingiz mumkin.*"
            )
            await send_reply(message, resp)
            return True

        # C. Agar ism topilmasa, umumiy to'lovlar hisoboti
        students = get_all_students()
        paid_ids = get_paid_students(period)
        paid_count = len([s for s in students if s["id"] in paid_ids])
        unpaid_count = len(students) - paid_count
        resp = (
            f"💳 **UMUMIY TO'LOV HISOBOTI ({period})**\n"
            f"✅ To'laganlar: **{paid_count} ta**\n"
            f"❌ To'lamaganlar: **{unpaid_count} ta**\n"
            f"────────────────────────\n\n"
        )
        for idx, s in enumerate(students, 1):
            is_p = s["id"] in paid_ids
            mark = "✅" if is_p else "❌"
            resp += f"{idx}. {mark} **{s['name']}** ({s.get('course_name') or '-'})\n   🗓 {s.get('due_day')}-sana ┆ {'To‘langan' if is_p else 'To‘lanmagan'}\n"
        await send_reply(message, resp)
        return True

    # 3. DARS JADVALLARI
    # A. Muayyan o'quvchi dars jadvali ("murodni dars jadvali", "muhayyo dars jadvali") yoki umumiy dars jadvali
    if re.search(r"dars\s+(?:jadval\w*|jadav[al]\w*)|(?:jadval\w*|jadav[al]\w*)|darslari|darsi|dars qachon", lower):
        if not re.search(r"bugun|erta", lower):
            target = extract_target_student_name(text)
            matches = find_matching_students(target) if target else []
            if not matches and target:
                matches = find_matching_students(text)
            if len(matches) > 1:
                choices = "\n".join([f"  • **ID #{s['id']}**: {s['name']} ({s.get('course_name') or 'Kurs'})" for s in matches])
                await send_reply(
                    message,
                    f"⚠️ **Bazada bir nechta o'quvchi topildi:**\n{choices}\n\n"
                    f"Iltimos, aniq ID raqami bilan so'rang (masalan: `ID {matches[0]['id']} dars jadvali`)."
                )
                return True
            student = matches[0] if len(matches) == 1 else None
            if student:
                schedule_text = format_student_weekly_schedule(student)
                await send_reply(message, schedule_text)
                return True
            elif target:
                is_explicit_lookup = bool(re.search(r"\b(?:jadvali|jadvalim|darsi|jadvalini|darslari)\b|qachon|ko'rsat|tashla|ber|ayt", lower))
                if len(target.split()) <= 3 and is_explicit_lookup:
                    await send_reply(message, f"👤 **'{target}'** ismli o'quvchi bazadan topilmadi. O'quvchilar ro'yxatini ko'rish uchun *'o'quvchilar ro'yxati'* deb yozing.")
                    return True
            else:
                # Agar o'quvchi ismi ko'rsatilmagan bo'lsa (masalan: "dars jadvali", "dars jadavli", "jadval"):
                now = tashkent_now()
                today_lessons = get_lessons_for_date(now.date())
                if today_lessons:
                    by_time = {}
                    for l in today_lessons:
                        by_time.setdefault(l["lesson_time"], []).append(f"{l['student_name']} ({l['course_name'] or 'Kurs'})")
                    lessons_str = "\n".join([f"⏰ **Soat {t}:**\n" + "\n".join([f"   ▫️ {st}" for st in by_time[t]]) for t in sorted(by_time.keys())])
                else:
                    lessons_str = f"Bugun ({now.day}-sana) uchun rejalashtirilgan darslar yo'q."
                resp = (
                    f"📅 **CYBER TECH ACADEMY — DARS JADVALI** 📚\n\n"
                    f"📍 **Bugungi darslar ({now.day}-sana):**\n{lessons_str}\n\n"
                    f"────────────────────────\n"
                    f"💡 *Muayyan o'quvchining haftalik jadvalini ko'rish uchun:*\n"
                    f"  • `[O'quvchi ismi] dars jadvali` (masalan: *Murodni dars jadvali*)\n"
                    f"  • Yoki `/jadval [Ism]`\n"
                    f"  • *'Ertangi darslar'* — ertangi darslar ro'yxati"
                )
                await send_reply(message, resp)
                return True

    # B. Bugungi darslar
    if re.search(r"bugung?i? dars", lower) or (re.search(r"dars jadval|jadval", lower) and "bugun" in lower):
        now = tashkent_now()
        today_lessons = get_lessons_for_date(now.date())
        if not today_lessons:
            await send_reply(message, f"📅 Bugun ({now.day}-sana) uchun rejalashtirilgan darslar yo'q.")
            return True
        by_time = {}
        for l in today_lessons:
            by_time.setdefault(l["lesson_time"], []).append(f"{l['student_name']} ({l['course_name'] or 'Kurs'})")
        resp = f"📅 **Bugungi darslar jadvali ({now.day}-sana):**\n\n"
        for t in sorted(by_time.keys()):
            resp += f"⏰ **Soat {t}:**\n" + "\n".join([f"   ▫️ {st}" for st in by_time[t]]) + "\n\n"
        await send_reply(message, resp)
        return True

    # C. Ertangi darslar
    if re.search(r"ertang?i? dars", lower) or (re.search(r"dars jadval|jadval", lower) and "erta" in lower):
        tomorrow = tashkent_now().date() + timedelta(days=1)
        lessons = get_lessons_for_date(tomorrow)
        if not lessons:
            await send_reply(message, f"📅 Ertaga ({tomorrow.day}-sana) uchun darslar belgilanmagan.")
            return True
        by_time = {}
        for l in lessons:
            by_time.setdefault(l["lesson_time"], []).append(f"{l['student_name']} ({l['course_name'] or 'Kurs'})")
        resp = f"📅 **Ertangi darslar jadvali ({tomorrow.day}-sana):**\n\n"
        for t in sorted(by_time.keys()):
            resp += f"⏰ **Soat {t}:**\n" + "\n".join([f"   ▫️ {st}" for st in by_time[t]]) + "\n\n"
        await send_reply(message, resp)
        return True

    # 4. O'QUVCHILAR RO'YXATI / A'ZOLAR
    if re.search(r"o'quvchilar ro'yxati|oquvchilar royxati|o'quvchilar|oquvchilar|a'zolar|azolar|talabalar", lower):
        students = get_all_students()
        if not students:
            await send_reply(message, "Hozircha bazada o'quvchilar yo'q.")
            return True
        resp = f"👥 **CYBER TECH ACADEMY O'QUVCHILARI ({len(students)} nafar):**\n\n"
        for idx, s in enumerate(students, 1):
            ph = f" ┆ 📞 {s['phone']}" if s.get("phone") else ""
            tg = f" ┆ @{s['username']}" if s.get("username") else ""
            resp += f"{idx}. **{s['name']}**\n   📚 {s.get('course_name') or 'Kurs'} ┆ 🗓 {s.get('due_day')}-sana{tg}{ph}\n"
        await send_reply(message, resp)
        return True

    # 5. EXCEL YANGILASH
    if "excel" in lower and ("yangila" in lower or "baza" in lower or "qayta" in lower):
        if not os.path.exists(EXCEL_LOCAL_PATH):
            await send_reply(message, f"⚠️ `{EXCEL_LOCAL_PATH}` fayli topilmadi!")
            return True
        try:
            import_pi_academy_excel(str(EXCEL_LOCAL_PATH), dry_run=True)
            backup_data()
            res = import_pi_academy_excel(str(EXCEL_LOCAL_PATH))
            await send_reply(
                message,
                f"✅ **Excel ma'lumotlari muvaffaqiyatli yangilandi!**\n\n"
                f"👤 O'quvchilar soni: **{res['students_imported']} ta**\n"
                f"📖 Kiritilgan dars soatlari: **{res['lessons_imported']} ta**\n"
                f"📊 Varaqlar: `{res['payment_sheet']}` va `{res['schedule_sheet']}`"
            )
        except Exception as e:
            await send_reply(message, f"❌ Excel yangilashda xatolik: {e}")
        return True

    # 6. BOT VA ADMIN HOLATI (STATUS)
    if re.search(r"bot holati|admin holati|status\b|tizim holati", lower):
        online = is_admin_online()
        mode = get_setting("admin_manual_status", "auto")
        holat_str = "🟢 ONLAYN (Faqat botga murojaatlarga javob beradi)" if online else "🔴 OFLAYN (Barcha savollarga AI javob beradi)"
        await send_reply(
            message,
            f"📊 **CYBER TECH ACADEMY — TIZIM HOLATI**\n\n"
            f"▫️ Admin holati: {holat_str}\n"
            f"▫️ Joriy rejim: `{mode}`\n"
            f"▫️ AI Model: `{OPENAI_MODEL}`\n"
            f"▫️ Eslatma guruhi ID: `{get_setting('main_group_id', 'belgilanmagan')}`\n\n"
            f"💡 *Rejimni o'zgartirish uchun to'g'ridan-to'g'ri yozing:*\n"
            f"▸ 'Onlayn bo'l'\n"
            f"▸ 'Oflayn bo'l'\n"
            f"▸ 'Avtomatik rejim'"
        )
        return True

    # 7. REJIMLARNI O'ZGARTIRISH
    if re.search(r"onlayn bo'l|onlayn qil|online bo'l", lower):
        set_setting("admin_manual_status", "online")
        update_admin_activity()
        await send_reply(message, "🟢 **Siz ONLAYN holatdasiz.**\nBot faqat 'Pi' deb chaqirilganda, mention yoki reply bo'lganda javob beradi.")
        return True

    if re.search(r"oflayn bo'l|oflayn qil|offline bo'l", lower):
        set_setting("admin_manual_status", "offline")
        await send_reply(message, "🔴 **Siz OFLAYN holatdasiz.**\nBot guruhdagi barcha savollarga AI orqali avtomatik javob beradi.")
        return True

    if re.search(r"avtomatik rejim|avto rejim|auto rejim", lower):
        set_setting("admin_manual_status", "auto")
        await send_reply(message, "🔄 **AVTOMATIK rejim yoqildi.**\nAgar 5 daqiqa guruhda faol bo'lmasangiz, bot oflayn deb hisoblab savollarga javob beradi.")
        return True

    # 8. ADMIN YORDAM VA BUYRUQLAR YO'RIQNOMASI
    if re.search(r"yordam|buyruqlar|admin buyruqlari|nima qila olasan", lower):
        await send_reply(message, ADMIN_HELP)
        return True

    # 9. REYTING VA GAMIFIKATSIYA (LEADERBOARD)
    if re.search(r"reyting.*(?:pin|zaprepit|qada|joyla|chiqar)|(?:pin|zaprepit|qada).*reyting", lower):
        pinned_id = await update_pinned_leaderboard(context.bot, force_repin=True)
        if pinned_id:
            await send_reply(message, f"📌 **O'quvchilar reytingi guruhga yuborildi va muvaffaqiyatli zaprepit (pin) qilindi!**\n(Xabar ID: `{pinned_id}`)")
        else:
            await send_reply(message, "⚠️ Guruhga reytingni pin qilishda muammo yuz berdi. Botning guruhda xabarlarni pin qilish huquqini tekshiring.")
        return True

    if re.search(r"reyting|leaderboard|top o'quvchilar|top oquvchilar|ballar|xp reyting", lower):
        leaderboard = get_leaderboard(limit=10)
        if not leaderboard:
            await send_reply(message, "Hozircha reyting ma'lumotlari mavjud emas.")
            return True
        resp = "🏆 **CYBER TECH ACADEMY — O'QUVCHILAR REYTINGI** 🚀\n"
        resp += "*(O'quvchilar masalalar yechgani va darsdagi faolligi uchun XP to'playdi)*\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(leaderboard, 1):
            m = medals[idx - 1] if idx <= 3 else f"{idx}."
            resp += f"{m} **{row['student_name']}** — **{row['xp']} XP**\n   {row['title']} ┆ ✅ {row.get('tasks_solved',0)} masala ┆ ❓ {row.get('questions_asked',0)} savol\n\n"
        resp += "💡 *O'quvchiga ball qo'shish uchun: 'Murodga 50 XP' deb yozishingiz mumkin.*\n*Guruhda zaprepit qilish uchun: 'Reytingni pin qil'* deb yozing."
        await send_reply(message, resp)
        return True

    # 10. O'QUVCHIGA MANUAL XP BERISH ("Murodga 50 XP", "Murodga 30 ball")
    xp_match = re.search(r"(?:(\w+)(?:ga|ka|qa)?\s+)?(\+?\d+)\s*(?:xp|ball)(?:\s+ber)?", lower)
    if xp_match and ("xp" in lower or "ball" in lower):
        target_word = xp_match.group(1)
        amount = int(xp_match.group(2).lstrip("+"))
        target = extract_target_student_name(target_word) if target_word else None
        if not target and message.reply_to_message and message.reply_to_message.from_user:
            student = find_student_by_user(message.reply_to_message.from_user)
        else:
            matches = find_matching_students(target) if target else []
            if len(matches) > 1:
                choices = "\n".join([f"  • **ID #{s['id']}**: {s['name']} ({s.get('course_name') or 'Kurs'})" for s in matches])
                await send_reply(
                    message,
                    f"⚠️ **Bazada bir nechta o'quvchi mos keldi:**\n{choices}\n\n"
                    f"Iltimos, aniq ID orqali bering (masalan: `ID {matches[0]['id']}ga {amount} XP`)."
                )
                return True
            student = matches[0] if len(matches) == 1 else None

        if student and amount > 0:
            res = add_student_xp(student["id"], student["name"], amount, is_task=True)
            congrats = ""
            if res.get("level_up"):
                congrats = f"\n🎉 **Yangi daraja ochildi:** {res['title']}!"
            await send_reply(
                message,
                f"⚡ **{student['name']}**ga **+{amount} XP** muvaffaqiyatli berildi! 🎯\n"
                f"Joriy ball: **{res['new_xp']} XP** ({res['title']}){congrats}"
            )
            asyncio.create_task(update_pinned_leaderboard(context.bot))
            return True

    # 11. WEB DASHBOARD
    if re.search(r"dashboard|mini app|web app|veb panel|boshqaruv paneli|sayt", lower):
        await message.reply_text(
            "🌐 **CYBER TECH ACADEMY — BOSHQARUV PANELI** 🚀\n\n"
            "Barcha o'quvchilar statistikasi, to'lovlar, dars jadvallari va reyting ma'lumotlari tez kunda rasmiy veb-manzilda ishga tushiriladi!",
            parse_mode="Markdown"
        )
        return True

    # 12. PROFILNI ID ORQALI BOG'LASH (Tabiiy buyruq)
    # Misollar:
    # 1) Admin o'quvchining xabariga reply qilib: "bog'la 12" yoki "bog'lash 12" yoki "bog'la ID 12"
    # 2) Admin to'g'ridan-to'g'ri yozib: "bog'lash 12345678 12" yoki "bog'la 12345678 12"
    if any(k in lower for k in ["bog'la", "bogla", "bog'lash", "boglash"]):
        link_m = re.search(r"(?:bog'la|bogla|bog'lash|boglash)\s*(?:(\d{5,15})\s+)?(?:id[:\s]*|#)?(\d+)", lower)
        tg_id = None
        sid = None
        if link_m:
            g1, g2 = link_m.groups()
            if g1 and g2:
                tg_id = int(g1)
                sid = int(g2)
            elif g2:
                sid = int(g2)

        replied = message.reply_to_message
        if not tg_id and replied and replied.from_user and not replied.from_user.is_bot:
            tg_id = replied.from_user.id

        if tg_id and sid:
            try:
                from member_service import link_member
                if replied and replied.from_user and replied.from_user.id == tg_id:
                    register_member(replied.from_user, update.effective_chat.id)
                link_member(tg_id, sid)

                with closing(get_connection()) as conn:
                    st_row = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
                st_name = st_row["name"] if st_row else f"ID #{sid}"

                await send_reply(
                    message,
                    f"✅ **Muvaffaqiyatli bog'landi!** 🎯\n\n"
                    f"👤 O'quvchi: **{st_name}** (ID: #{sid})\n"
                    f"📱 Telegram ID: `{tg_id}`\n\n"
                    f"Endi ushbu profil egasi o'z dars jadvalini ko'rishi, masalalar yechib XP to'plashi mumkin. "
                    f"Telegramdagi ismini almashtirsa ham, uning barcha tarixi va reytingdagi ballari to'liq saqlanadi! 🛡"
                )
                asyncio.create_task(update_pinned_leaderboard(context.bot))
                return True
            except ValueError as ve:
                await send_reply(message, f"⚠️ Bog'lashda xatolik: {ve}")
                return True

    # 13. O'QUVCHILARNING SAVOLLARI VA FAOLIYATI ("kimlar savol berdi?", "bugun kimlar senga savol berdi?")
    if re.search(r"(?:kimlar|kim|qaysi o'quvchi|qaysi talaba).*savol|(?:savol.*(?:berdi|so'radi|yozdi))|bugungi savollar|savollar ro'yxati|nimalar so'radi|nima so'radi", lower):
        now = tashkent_now()
        today_str = now.strftime("%Y-%m-%d")
        all_logs = get_student_learning_logs(limit=50)

        is_today_asked = "bugun" in lower or "hozir" in lower
        month_name = UZ_MONTHS.get(now.month, "oy")
        if is_today_asked:
            logs = [l for l in all_logs if str(l.get("created_at", "")).startswith(today_str)]
            header_title = f"📅 **BUGUN BOTGA SAVOL BERGAN O'QUVCHILAR ({now.day}-{month_name}):**"
        else:
            logs = all_logs[:15]
            header_title = f"📋 **BOTGA SO'NGGI SAVOL BERGAN O'QUVCHILAR:**"

        if not logs:
            if is_today_asked:
                resp = f"📅 Bugun ({now.day}-{month_name}) hali hech bir o'quvchi botga savol yoki topshiriq yo'llagani yo'q, ustoz."
                if all_logs:
                    last_log = all_logs[0]
                    created_short = str(last_log.get('created_at', ''))[:16]
                    last_student_name = last_log.get('student_name', "O'quvchi")
                    resp += f"\n\n💡 *Oxirgi savol:* **{last_student_name}** tomonidan yuborilgan (`{created_short}`):\n❓ *\"{last_log['question'][:100]}\"*"
                await send_reply(message, resp)
                return True
            else:
                await send_reply(message, "Hozircha o'quvchilar savol-javoblar tarixi mavjud emas.")
                return True

        by_student = {}
        for l in logs:
            name = l.get("student_name") or "Talaba"
            by_student.setdefault(name, []).append(l)

        resp = f"{header_title}\n"
        resp += f"Jami: **{len(by_student)} nafar o'quvchi** ({len(logs)} ta savol/topshiriq)\n"
        resp += "────────────────────────\n\n"

        for idx, (sname, s_logs) in enumerate(by_student.items(), 1):
            resp += f"{idx}. 👤 **{sname}** ({len(s_logs)} ta savol):\n"
            for sl in s_logs[:3]:
                q_text = sl["question"].strip()
                created = str(sl.get("created_at", ""))
                time_part = created[11:16] if len(created) >= 16 else ""
                time_str = f" ┆ ⏰ {time_part}" if time_part else ""
                resp += f"   ❓ *\"{q_text[:90]}\"*{time_str}\n"
            if len(s_logs) > 3:
                resp += f"   *(yana {len(s_logs) - 3} ta savol...)*\n"
            resp += "\n"

        resp += "💡 *Har bir o'quvchi o'zlashtirishini chuqur tahlil qilish uchun: '[Ism]ning o'zlashtirishi qanday' deb yozishingiz mumkin.*"
        await send_reply(message, resp)
        return True

    # 14. ADMINNING BOSHQA BARCHA SAVOL VA MUROJAATLARI (SUHBAT / AI)
    # Agar admin o'quvchisiga gapirayotgan bo'lmasa (reply qilmagan, ismini aytmagan)
    chat = update.effective_chat
    is_group = bool(chat and chat.type in ("group", "supergroup"))
    is_talking_to_student = is_admin_talking_to_student(message, text) if is_group else False
    if is_talking_to_student:
        return False

    # Guruhda yoki shaxsiy chatda admin savol berganda ("algoritm nima?", "?" belgisi, ta'limiy/texnik savol yoki botga murojaat):
    is_direct_to_bot = direct_request(message, chat, context.bot, text) if is_group else True
    is_question = bool(is_question_like(text) or is_academic_question(text) or ("?" in text) or is_task_request(text))

    if is_direct_to_bot or is_question:
        admin_prompt = (
            f"Siz 'Cyber Tech Academy' zamonaviy IT markazining 'Pi' nomli aqlli AI yordamchisisiz.\n"
            f"Sizga akademiyaning Bosh Ustozi va Rahbari (Shaxboz Salomov) murojaat qilmoqda: '{text}'\n\n"
            f"Adminingizga yuksak hurmat, samimiyat, pedagogik va professional bilim bilan eng to'g'ri, lo'nda va amaliy javob bering!"
        )
        ai_reply = await ask_ai(admin_prompt, user_name="Shaxboz Salomov (Admin)", direct=True, is_admin=True)
        if ai_reply:
            await send_reply(message, ai_reply)
            return True

    return False


# ----------------- MATNLI SAVOLLARGA JAVOB BERISH (AI) -----------------

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy chat va guruhdagi matnli savollarga javob berish"""
    chat = update.effective_chat
    if not chat or chat.type not in ["private", "group", "supergroup"]:
        return

    message = update.message
    if not message or not message.text:
        return
        
    user = update.effective_user
    text = message.text.strip()
    if await send_requested_books(message):
        return
    if await natural_payment(update, context):
        return
    if user and user.id == ADMIN_ID:
        if await handle_admin_natural_query(update, context, text):
            return
        # Guruhda ustoz (admin) boshqa biror narsa yozsa (o'quvchilariga javob, ko'rsatma, suhbat),
        # bot guruhda aslo o'quvchi savoli kabi aralashmasligi yoki javob yozmasligi shart!
        if chat.type in ("group", "supergroup") and not direct_request(message, chat, context.bot, text):
            return
    bot_username = (await context.bot.get_me()).username.lower()
    
    topic = getattr(message, "message_thread_id", None) or 0
    replied = message.reply_to_message
    reply_id = getattr(replied, "message_id", None)
    if replied and (getattr(replied, "message_thread_id", None) or 0) == topic:
        cache_photo(replied, chat.id, topic)
    else:
        reply_id = None
    followup = study_context.is_followup(text)
    photo, ambiguous, quoted = (None, False, "")
    if user and (followup or reply_id is not None):
        photo, ambiguous, quoted = study_context.resolve(chat.id, topic, user.id, reply_id)
    if replied and reply_id is not None:
        quoted = getattr(replied, "text", None) or getattr(replied, "caption", None) or quoted
    direct = direct_request(message, chat, context.bot, text)
    # A follow-up to an identified task is addressed to the bot even when admin is online.
    direct = direct or bool(followup and (photo or ambiguous) and not is_addressed_to_teacher(text))
    if not user or not should_answer(update, text, direct):
        return

    if ambiguous:
        await message.reply_text("Qaysi rasmni nazarda tutdingiz? Kerakli rasmga reply qilib savolingizni yozing.")
        return
    if followup and not photo and reply_id is None:
        if re.search(r"rasmdagi|shu rasm|\d+\s*[-–]\s*\d+\s*[-–]?\s*masala", text.casefold()):
            await message.reply_text("Qaysi topshiriq ekanini ko'rishim uchun rasmni yuboring yoki masala shartini yozing.")
            return

    lower_text = text.lower()
    
    # 0. Gamifikatsiya — O'quvchilar uchun shaxsiy ball va reyting
    if re.search(r"^(?:mening\s+)?(?:ballarim|ballim|reytingim|profilim|darajam|xp)\b", lower_text):
        st = find_student_by_user(user)
        if st:
            g_data = get_student_gamification(student_id=st["id"])
            if g_data:
                await send_reply(
                    message,
                    f"🏆 **O'QUVCHI PROFILI: {st['name']}**\n\n"
                    f"📚 Kurs: **{st.get('course_name') or 'Kurs'}**\n"
                    f"⚡ To'plangan ball: **{g_data['xp']} XP**\n"
                    f"🎖 Daraja: **{g_data['title']}** (Level {g_data['level']})\n"
                    f"✅ Yechilgan masalalar: **{g_data.get('tasks_solved', 0)} ta**\n"
                    f"❓ Berilgan savollar: **{g_data.get('questions_asked', 0)} ta**\n\n"
                    f"💡 *Ko'proq masala yeching va faol savol bering, XP to'plab yangi darajalarga ko'tariling!*"
                )
                return
    if re.search(r"^(?:top\s+o'quvchilar|reyting|leaderboard)\b", lower_text):
        leaderboard = get_leaderboard(limit=10)
        resp = "🏆 **CYBER TECH ACADEMY — REYTING JADVALI** 🚀\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(leaderboard, 1):
            m = medals[idx - 1] if idx <= 3 else f"{idx}."
            resp += f"{m} **{row['student_name']}** — **{row['xp']} XP** ┆ {row['title']}\n"
        await send_reply(message, resp)
        return

    # 1. Haftalik dars jadvali yoki so'ragan odamning dars jadvali (Maxfiylik himoyalangan)
    if is_schedule_request(lower_text):
        is_admin = user and user.id == ADMIN_ID
        target_name = extract_target_student_name(text)

        # AGAR ODDIY FOYDALANUVCHI BO'LSA:
        if not is_admin:
            my_student = find_student_by_user(user)
            if target_name:
                if not my_student or not any(token in normalize(target_name) for token in normalize(my_student["name"]).split()):
                    await send_reply(
                        message,
                        "🔒 **Maxfiylik qoidasi:**\n"
                        "Siz faqat o'zingizga tegishli dars jadvalini ko'rishingiz mumkin. Boshqa o'quvchilar ma'lumotlari maxfiy hisoblanadi. 🛡"
                    )
                    return
            if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id != getattr(user, "id", None):
                await send_reply(
                    message,
                    "🔒 **Maxfiylik qoidasi:**\n"
                    "Siz faqat o'zingizga tegishli dars jadvalini ko'rishingiz mumkin. Boshqa o'quvchilar ma'lumotlari maxfiy hisoblanadi. 🛡"
                )
                return
            student = my_student
        else:
            # ADMIN bo'lsa:
            if not target_name and message.reply_to_message and message.reply_to_message.from_user:
                student = find_student_by_user(message.reply_to_message.from_user)
            else:
                student = find_student_by_user(user, target_name)

        if student:
            schedule_text = format_student_weekly_schedule(student)
            await send_reply(message, schedule_text)
            return
        elif is_admin:
            await message.reply_text(
                "👤 O'quvchi profilini aniqlab bo'lmadi.\n"
                "Muayyan o'quvchi jadvalini ko'rish uchun: `Ism dars jadvali` deb yozing (masalan: Murodni dars jadvali).\n"
                "Bugungi yoki ertangi umumiy jadval: 'Bugungi darslar' yoki 'Ertangi darslar'"
            )
            return
        else:
            await message.reply_text(
                f"🔒 **Profilingiz tasdiqlanmagan:**\n"
                f"Sizning Telegram profilingiz (TG ID: `{user.id}`) hali o'quvchilar bazasiga bog'lanmagan. ⚠️\n\n"
                f"Xavfsizlik qoidasiga ko'ra boshqa o'quvchilar ma'lumotlari maxfiy hisoblanadi. O'z dars jadvalingizni "
                f"ko'rish uchun markaz administratoriga ushbu Telegram ID raqamingizni (`{user.id}`) taqdim eting.",
                parse_mode="Markdown"
            )
            return

    # 2. Maxsus tezkor dars jadvali savollari ("bugun dars bormi?")
    if any(q in lower_text for q in ["bugun dars", "dars bormi", "bugungi dars"]):
        student = find_student_by_user(user)
        today = tashkent_now().date()
        today_iso = today.isoformat()
        if student:
            with closing(get_connection()) as conn:
                s_lessons = [dict(r) for r in conn.execute(
                    "SELECT * FROM daily_lessons WHERE student_name=? AND lesson_date=? AND cancelled=0",
                    (student["name"], today_iso)
                ).fetchall()]
            if s_lessons:
                times = ", ".join([l["lesson_time"] for l in s_lessons])
                await send_reply(message, f"Ha, {student['name']}! Bugun soat **{times}** da darsingiz bor. 📚 ({student.get('course_name') or 'Kurs'})")
            else:
                with closing(get_connection()) as conn:
                    next_l = conn.execute(
                        "SELECT * FROM daily_lessons WHERE student_name=? AND lesson_date > ? AND cancelled=0 ORDER BY lesson_date, lesson_time LIMIT 1",
                        (student["name"], today_iso)
                    ).fetchone()
                if next_l:
                    nl_d = date.fromisoformat(next_l["lesson_date"])
                    nl_name = {0: "Dushanba", 1: "Seshanba", 2: "Chorshanba", 3: "Payshanba", 4: "Juma", 5: "Shanba", 6: "Yakshanba"}[nl_d.weekday()]
                    await send_reply(message, f"Bugun sizda dars yo'q, {student['name']}. Navbatdagi darsingiz: **{nl_d.day}-sana ({nl_name})**, soat **{next_l['lesson_time']}** da.")
                else:
                    await send_reply(message, f"Bugun sizda dars yo'q, {student['name']}.")
            return
        elif user and user.id == ADMIN_ID:
            lessons = get_lessons_for_date(today)
            if lessons:
                by_time = {}
                for l in lessons:
                    t = l["lesson_time"]
                    by_time.setdefault(t, []).append(l["student_name"])
                resp = f"Bugun ({today.day}-sana) darslarimiz bor:\n" + "\n".join([f"⏰ Soat {t} da: {', '.join(by_time[t])}" for t in sorted(by_time.keys())])
                await send_reply(message, resp)
            else:
                await message.reply_text("Bugun uchun jadvalda dars topilmadi.")
            return
        else:
            await send_reply(
                message,
                "Kechirasiz, profilingiz o'quvchilar ro'yxatida topilmadi. ⚠️\n"
                "O'z dars jadvalingizni bilish uchun profilingizni bazaga bog'lash lozim. Adminga murojaat qiling yoki to'liq ism-familiyangizni yozing."
            )
            return

    # 3. Maxfiylik himoyasi: Oddiy foydalanuvchilar boshqa o'quvchilar haqida ma'lumot so'raganda
    is_admin = user and user.id == ADMIN_ID
    if not is_admin:
        my_student = find_student_by_user(user)

        # A. Boshqa o'quvchining to'lovi yoki qarzdorligi so'ralsa:
        if any(w in lower_text for w in ["to'lov", "tolov", "to'ladimi", "toladimi", "to'lamadi", "tolamadi", "to'lagan", "tolagan", "to'lash", "tolash", "qarzdor", "qarz"]):
            target_name = extract_target_student_name(text)
            if target_name and (not my_student or not any(tok in normalize(target_name) for tok in normalize(my_student["name"]).split())):
                await send_reply(
                    message,
                    "🔒 **Maxfiylik qoidasi:**\n"
                    "O'quv markazi xavfsizlik siyosatiga ko'ra, boshqa o'quvchilarning to'lov, qarz yoki shaxsiy ma'lumotlari berilmaydi. 🛡"
                )
                return

            if any(w in lower_text for w in ["kimlar", "ro'yxat", "royxat", "hamma", "barcha", "qarzdorlar"]):
                await send_reply(
                    message,
                    "🔒 **Maxfiylik qoidasi:**\n"
                    "Umumiy to'lovlar va qarzdorlik hisoboti faqat markaz rahbariyati uchun ochiq. 🛡"
                )
                return

            # O'zining to'lovini so'ragan bo'lsa:
            if my_student:
                period = tashkent_now().strftime("%Y-%m")
                paid_ids = get_paid_students(period)
                is_p = my_student["id"] in paid_ids
                st_icon = "to'langan ✅" if is_p else f"to'lanmagan (har oyning {my_student.get('due_day', 10)}-sanasigacha to'lanadi) ⏳"
                await send_reply(
                    message,
                    f"💳 **Hurmatli {my_student['name']}!**\n"
                    f"📚 Kursingiz: **{my_student.get('course_name') or 'IT'}**\n"
                    f"🗓 To'lov kuningiz: Har oyning **{my_student.get('due_day', '-')}-sanasi**\n"
                    f"💵 Joriy oy ({period}) uchun to'lov holatingiz: **{st_icon}**"
                )
                return

        # B. Boshqa o'quvchining shaxsiy ma'lumoti yoki o'zlashtirishi so'ralsa:
        if any(w in lower_text for w in ["o'zlashtir", "ozlashtir", "telefon", "nomer", "ahvoli", "tushunmayapti", "haqida ma'lumot"]):
            target_name = extract_target_student_name(text)
            if target_name and (not my_student or not any(tok in normalize(target_name) for tok in normalize(my_student["name"]).split())):
                await send_reply(
                    message,
                    "🔒 **Maxfiylik qoidasi:**\n"
                    "O'quv markazi xavfsizlik siyosatiga ko'ra, boshqa o'quvchilarning shaxsiy ma'lumotlari yoki o'zlashtirish ko'rsatkichlari berilmaydi. 🛡"
                )
                return

        # C. Barcha o'quvchilar ro'yxati so'ralsa:
        if any(w in lower_text for w in ["o'quvchilar ro'yxati", "oquvchilar royxati", "barcha o'quvchilar", "talabalar ro'yxati"]):
            await send_reply(
                message,
                "🔒 **Maxfiylik qoidasi:**\n"
                "Akademiya o'quvchilari to'liq ro'yxati maxfiy hisoblanadi va faqat rahbariyatga beriladi. Guruhdagi umumiy reytingni ko'rish uchun zaprepit qilingan reyting xabariga qarang. 🏆"
            )
            return

        # To'liq OpenAI fikrlashi orqali javob olish:
    prompt_text = text.replace(f"@{bot_username}", "").strip()
    user_name = user.first_name if user else "Talaba"
    
    if not request_allowed(user.id):
        await message.reply_text("Bir daqiqada 6 ta AI so’roviga ruxsat beriladi. Biroz kuting.")
        return
    image_bytes = None
    if photo:
        try:
            image_bytes = await load_study_image(context.bot, photo["file_id"])
        except Exception as error:
            logger.warning("Oldingi rasmni olish: %s", type(error).__name__)
            await message.reply_text("Oldingi rasmni ochib bo'lmadi. Rasmni qayta yuboring, keyin masalani tushuntiraman.")
            return
        study_context.select_photo(chat.id, topic, user.id, photo["message"])
    ai_reply = await ask_ai(prompt_text, user_name=user_name, direct=direct,
                            context=learning_context(user.id),
                            conversation_key=(chat.id, user.id),
                            image_bytes=image_bytes,
                            source_caption=photo["caption"] if photo else "",
                            quoted_text=quoted)
    if ai_reply:
        logger.info("AI javobi tayyor")

        # Gamifikatsiya — topshiriq to'g'ri yechilganini tekshirish
        is_task_correct = "[VAZIFA_TOGRI]" in ai_reply
        display_reply = ai_reply.replace("[VAZIFA_TOGRI]", "").strip()

        st_rec = find_student_by_user(user)
        xp_banner = ""
        if is_task_correct:
            if st_rec and not (user and user.id == ADMIN_ID):
                xp_res = add_student_xp(st_rec["id"], st_rec["name"], 25, is_task=True, course_name=st_rec.get("course_name"))
                congrats = f"\n🎉 **Yangi daraja ochildi:** {xp_res['title']}!" if xp_res.get("level_up") else ""
                xp_banner = f"\n\n🎯 **+25 XP** topshiriq to'g'ri bajarilgani uchun berildi!\n🏆 Joriy balingiz: **{xp_res['new_xp']} XP** ({xp_res['title']}){congrats}"
                asyncio.create_task(update_pinned_leaderboard(context.bot))
            elif not st_rec and not (user and user.id == ADMIN_ID):
                xp_banner = "\n\n🎯 **Topshiriq to'g'ri bajarildi!** Ballar reytingiga qo'shilish uchun profilingizni adminga bog'lating."

        final_reply = display_reply + xp_banner
        sent = await send_reply(message, final_reply)
        source = photo["message"] if photo else None
        study_context.link_message(chat.id, topic, getattr(message, "message_id", None), source, text, owner=user.id)
        for item in sent:
            study_context.link_message(chat.id, topic, getattr(item, "message_id", None), source, final_reply, owner=user.id)
        try:
            log_student_activity(
                student_id=st_rec["id"] if st_rec else None,
                student_name=st_rec["name"] if st_rec else getattr(user, "full_name", "Talaba"),
                telegram_id=getattr(user, "id", None),
                question=prompt_text,
                ai_response=final_reply
            )
        except Exception as e:
            logger.warning("Talaba savolini qayd etishda xatolik: %s", e)
    else:
        logger.info("AI bu xabarga javob bermaslikni tanladi")

# ----------------- AVTOMATIK ESLATMALAR (SCHEDULER) -----------------

async def check_and_send_reminders(bot):
    """
    1. To'lov eslatmalari: Ertaga to'lov kuni bo'lgan o'quvchilarga 1 kun oldin eslatish
    2. Dars eslatmalari: Bugungi darslar va dars boshlanishidan oldingi eslatmalar
    """
    group_id_str = get_setting("main_group_id")
    if not group_id_str:
        logger.info("Asosiy guruh ID hali belgilanmagan. Guruhda /set_group buyrug'ini yuboring.")
        return
        
    group_id = int(group_id_str)
    now = tashkent_now()
    today_str = now.strftime("%Y-%m-%d")
    
    # 1. TO'LOV ESLATMASI (Ertaga to'lov kuni bo'lganlarga)
    tomorrow = now + timedelta(days=1)
    tomorrow_day = tomorrow.day
    
    due_students = get_students_due_for_reminder(tomorrow_day, today_str)
    if due_students:
        for s in due_students:
            # Telegram ID orqali ko'k havola yoki username
            if s.get("telegram_id"):
                user_mention = f"[{s['name']}](tg://user?id={s['telegram_id']})"
            elif s.get("username"):
                user_mention = f"@{s['username']}"
            else:
                user_mention = f"**{s['name']}**"
                
            course = s.get("course_name") or "kursimiz"
            
            reminder_text = (
                f"🔔 **Hurmatli {user_mention}!**\n\n"
                f"Eslatib o'tamiz, ertaga (**{tomorrow_day}-sana**) **Cyber Tech Academy**dagi **{course}** bo'yicha navbatdagi oylik to'lov kuningiz.\n\n"
                f"Iltimos, darslar uzluksiz davom etishi uchun to'lovni o'z vaqtida amalga oshirishingizni so'raymiz. 😊\n"
                f"Savollaringiz bo'lsa bemalol murojaat qilishingiz mumkin!"
            )
            try:
                await bot.send_message(chat_id=group_id, text=reminder_text, parse_mode="Markdown")
                # Agar shaxsiy telegram_id si ham bo'lsa, shaxsiyiga ham yuboramiz
                if s.get("telegram_id"):
                    try:
                        await bot.send_message(chat_id=s["telegram_id"], text=reminder_text, parse_mode="Markdown")
                    except Exception:
                        pass
                mark_student_notified(s["id"], today_str)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"To'lov eslatmasi yuborishda xatolik ({s['name']}): {e}")

    # 2. BUGUNGI KUNLIK DARSLAR ANANSI (Har kuni ertalab soat 08:30 da bir marta)
    morning_sent_key = f"morning_schedule_sent_{today_str}"
    if now.hour == 8 and now.minute >= 30 and not get_setting(morning_sent_key):
        today_lessons = get_lessons_for_date(now.date())
        if today_lessons:
            by_time = {}
            for l in today_lessons:
                t = l["lesson_time"]
                if t not in by_time:
                    by_time[t] = []
                by_time[t].append(f"{l['student_name']} ({l['course_name'] or 'Kurs'})")
                
            announcement = f"☀️ **Xayrli tong, Cyber Tech Academy a'zolari!**\n\n📅 **Bugungi darslar jadvali ({now.day}-sana):**\n\n"
            for t in sorted(by_time.keys()):
                announcement += f"⏰ **Soat {t}:**\n" + "\n".join([f"   ▫️ {st}" for st in by_time[t]]) + "\n\n"
            announcement += "Barchangizga bugungi darslarda muvaffaqiyat tilaymiz! 🚀"
            
            try:
                await bot.send_message(chat_id=group_id, text=announcement, parse_mode="Markdown")
                set_setting(morning_sent_key, "1")
            except Exception as e:
                logger.error(f"Ertalabki jadval yuborishda xatolik: {e}")

    # 3. DARSGA 30 DAQIQA QOLGANDA ESLATMA
    # Bugungi dars vaqtlarini tekshiramiz
    today_lessons = get_lessons_for_date(now.date())
    for l in today_lessons:
        try:
            t_parts = l["lesson_time"].split(":")
            lesson_hour = int(t_parts[0])
            lesson_minute = int(t_parts[1])
            lesson_dt = now.replace(hour=lesson_hour, minute=lesson_minute, second=0, microsecond=0)
            
            # Farq daqiqalarda
            diff_minutes = (lesson_dt - now).total_seconds() / 60.0
            
            lesson_key = f"lesson_alert_{today_str}_{l['lesson_time']}_{l['student_name']}"
            if 0 < diff_minutes <= 35 and not get_setting(lesson_key):
                alert_text = (
                    f"⏰ **Dars eslatmasi!**\n\n"
                    f"Hurmatli **{l['student_name']}**, soat **{l['lesson_time']}** da **{l['course_name']}** darsingiz boshlanadi!\n"
                    f"Darsga kechikmasdan qatnashishingizni so'raymiz. 🚀"
                )
                try:
                    await bot.send_message(chat_id=group_id, text=alert_text, parse_mode="Markdown")
                    set_setting(lesson_key, "1")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Dars eslatmasi yuborishda xatolik: {e}")
        except Exception as e:
            continue

async def reminder_background_task(app):
    """Har 60 soniyada tekshirib turuvchi fon jarayoni"""
    logger.info("Eslatmalar fon jarayoni ishga tushdi...")
    reminder_count = 0
    while True:
        try:
            today = tashkent_now().date().isoformat()
            if get_setting("last_backup_date") != today:
                backup_data()
                set_setting("last_backup_date", today)
            await check_and_send_reminders(app.bot)
            
            # Har 30 daqiqada zaprepit reyting xabarini yangilaymiz
            reminder_count += 1
            if reminder_count % 30 == 0:
                await update_pinned_leaderboard(app.bot)
        except Exception as e:
            logger.error(f"Fon tekshiruvida xatolik: {e}", exc_info=True)
        await asyncio.sleep(60)

@admin_only
async def test_eslatma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sinov tariqasida to'lov va dars eslatmalarini darhol yuborish"""
    chat = update.effective_chat
    await update.message.reply_text("🔄 Jadval va to’lov ma’lumotlari tekshirilmoqda...")
    
    # Diagnostika sozlamalarni o’zgartirmaydi.
    
    now = tashkent_now()
    today_day = now.day
    
    # Bugungi darslar
    lessons = get_lessons_for_date(tashkent_now().date())
    lessons_summary = f"{len(lessons)} ta o'quvchida dars bor." if lessons else "Bugun dars yo'q."
    
    # Ertangi to'lovlar (yoki eng yaqin to'lovlar)
    tomorrow_day = (now + timedelta(days=1)).day
    all_students = get_all_students()
    
    msg = (
        f"✅ **Sinov muvaffaqiyatli o'tdi!**\n\n"
        f"📍 Eslatmalar guruhi ID: `{get_setting('main_group_id', 'belgilanmagan')}`\n"
        f"📅 Bugun: {today_day}-sana. ({lessons_summary})\n"
        f"💳 Ertaga ({tomorrow_day}-sana) to'lov kuni bo'lgan talabalar avtomatik xabarnoma oladi.\n\n"
        f"Jami ro'yxatdagi o'quvchilar: {len(all_students)} nafar."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ----------------- BOTNI ISHGA TUSHIRISH -----------------

async def post_init(application):
    """Bot ishga tushganda fon vazifasini ishga tushirish"""
    await configure_command_menus(application.bot)
    backup_data()
    set_setting("last_backup_date", tashkent_now().date().isoformat())
    application.bot_data["reminder_task"] = asyncio.create_task(reminder_background_task(application))
    application.bot_data["pinned_leaderboard_task"] = asyncio.create_task(update_pinned_leaderboard(application.bot))
    port_env = os.getenv("PORT")
    if port_env:
        try:
            application.bot_data["web_runner"] = await start_web_dashboard(host="0.0.0.0", port=int(port_env))
        except Exception as e:
            logger.warning("Web dashboard start error: %s", e)

async def post_shutdown(application):
    task = application.bot_data.get("reminder_task")
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    web_runner = application.bot_data.get("web_runner")
    if web_runner:
        await web_runner.cleanup()
    from ai_service import client
    await client.close()


async def error_handler(update, context):
    logger.error("Telegram ishlov berish xatosi: %s", type(context.error).__name__)


def main():
    if not BOT_TOKEN or not OPENAI_API_KEY:
        raise RuntimeError("Bot tokeni yoki OpenAI kaliti yo’q. secrets.local.json sozlamalarini tekshiring.")
    file_log = RotatingFileHandler(BASE_DIR / "bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_log.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_log)
    print("==================================================")
    print("Pi Akademiya Telegram Yordamchi Boti ishga tushmoqda...")
    print("==================================================")
    
    # Mavjud bazani har ishga tushishda eski Excel bilan qayta yozmaymiz.
    if os.path.exists(EXCEL_LOCAL_PATH) and not get_all_students(active_only=False):
        try:
            res = import_pi_academy_excel(str(EXCEL_LOCAL_PATH))
            print(f"[EXCEL] {res['students_imported']} ta talaba va {res['lessons_imported']} ta dars bazaga yuklandi.")
        except Exception as e:
            print(f"[EXCEL XATO] {e}")

    asyncio.set_event_loop(asyncio.new_event_loop())
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_error_handler(error_handler)
    app.add_handler(MessageHandler(filters.ALL, capture_member), group=-3)
    app.add_handler(MessageHandler(filters.COMMAND, command_access_guard), group=-2)
    app.add_handler(CommandHandler(["azolar", "oquvchi", "boglash"], members_command))
    app.add_handler(CommandHandler(["darslar", "dars_bekor", "dars_kochirish"], lessons_admin_command))
    app.add_handler(CommandHandler("daraja", level_command))
    app.add_handler(CommandHandler("tolandi", payment_command))
    app.add_handler(CommandHandler("tolanmadi", payment_command))
    app.add_handler(CommandHandler("diagnostika", diagnostics_command))

    app.add_handler(MessageHandler(filters.ALL, track_admin_activity), group=-1)
    app.add_handler(CommandHandler("yangi_suhbat", new_conversation_command))

    # Buyruqlar
    app.add_handler(CommandHandler("online", set_online_command))
    app.add_handler(CommandHandler("offline", set_offline_command))
    app.add_handler(CommandHandler("auto", set_auto_status_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("myid", id_command))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("set_group", set_group_command))
    app.add_handler(CommandHandler(["jadval", "dars_jadvali", "darsjadvali"], jadval_command))
    app.add_handler(CommandHandler("bugun", bugun_command))
    app.add_handler(CommandHandler("ertaga", ertaga_command))
    app.add_handler(CommandHandler("tolovlar", tolovlar_command))
    app.add_handler(CommandHandler("excel_yangilash", excel_yangilash_command))
    app.add_handler(CommandHandler("test_eslatma", test_eslatma_command))

    # Tizim xabarlarini (qo'shildi, chiqib ketdi, zakrepil va h.k.) avtomatik o'chirish
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, clean_service_messages))

    # Hujjatlar (Excel fayl yuklash)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Rasmlar (Vision tahlil)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Matnli xabarlar (Savol-javob AI)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Test boshqaruvi tugmalari
    app.add_handler(CallbackQueryHandler(quiz_callback_handler, pattern=r"^quiz_"))

    # Tugmalar (Reyting yangilash, Mening profilim)
    app.add_handler(CallbackQueryHandler(leaderboard_callback_handler))

    # Viktorina / Test javoblari (Har bir to'g'ri javobga 1 XP berish)
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    print("Bot muvaffaqiyatli ulandi va xabarlarni tinglamoqda...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        instance_lock = acquire_instance()
    except RuntimeError as error:
        print(error)
        raise SystemExit(2)
    try:
        main()
    finally:
        instance_lock.close()
