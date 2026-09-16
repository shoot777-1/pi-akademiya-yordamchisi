import re
from datetime import datetime, date
from database import get_connection, get_all_students, get_paid_students
from operations import tashkent_now
from member_service import normalize

def strip_uzbek_suffixes(word: str) -> str:
    w = word.strip().lower()
    # Common case & possessive suffixes in Uzbek
    suffixes = ["ning", "niki", "dan", "dek", "day", "dir", "ga", "ka", "qa", "da", "ni", "si", "i"]
    for sfx in suffixes:
        if len(w) > len(sfx) + 2 and w.endswith(sfx):
            w = w[:-len(sfx)]
            break
    return w

def extract_target_student_name(text: str):
    cleaned = text
    # Stop words / action keywords
    keywords = [
        "dars", "jadvali", "jadvalim", "jadval", "haftalik", "mening", "qachon", 
        "vaqti", "kunlari", "bormi", "iltimos", "tashla", "yubor", "ko'rsat", 
        "qanaqa", "bering", "kerak", "ayt", "aytib", "to'lovi", "tolovi", "to'lov", 
        "tolov", "to'ladimi", "toladimi", "to'laganmi", "tolaganmi", "o'zlashtirishi", 
        "ozlashtirishi", "o'zlashtirish", "o'zlashtirishini", "qanday", "nimalarni", 
        "tushunmayapti", "tushunmadi", "tushunyapti", "qiynalyapti", "haqida", 
        "ma'lumot", "ahvoli", "qilyapti", "darajasi", "kimlar", "to'lamadi", "qarzdorlar"
    ]
    for kw in keywords:
        cleaned = re.sub(rf"\b{re.escape(kw)}\b", "", cleaned, flags=re.I)
    cleaned = cleaned.strip(" ?!.,:;-\t\n")
    if not cleaned or len(cleaned) < 3:
        return None
    
    # Check words and strip Uzbek grammatical suffixes
    words = cleaned.split()
    stripped_words = [strip_uzbek_suffixes(w) for w in words]
    res = " ".join(stripped_words).strip(" ?!.,:;-\t\n")
    return res if len(res) >= 3 else None

def find_student_by_name_or_user(user, target_name=None):
    students = get_all_students(active_only=False)
    if target_name:
        nt = normalize(target_name)
        target_words = nt.split()
        
        # 1. Exact full name match
        for s in students:
            if normalize(s["name"]) == nt:
                return s
                
        # 2. Match whole word exact (e.g. "murod" matches "Yarashov Murod" exact token)
        for s in students:
            s_tokens = normalize(s["name"]).split()
            for tw in target_words:
                if len(tw) >= 3 and tw in s_tokens:
                    return s
                    
        # 3. Match token prefix (e.g. "sardor" matches "Sardorbek")
        for s in students:
            s_tokens = normalize(s["name"]).split()
            for tw in target_words:
                if len(tw) >= 3 and any(st.startswith(tw) for st in s_tokens):
                    return s
                    
        # 4. Fallback substring
        for s in students:
            sn = normalize(s["name"])
            if nt in sn:
                return s
    return None

test_queries = [
    "murodni dars jadvali",
    "murodning to'lovi",
    "murod to'ladimi?",
    "murodning o'zlashtirishi qanday",
    "murod nimalarni tushunmayapti",
    "sardorbek to'laganmi",
    "muhayyo dars jadvali",
    "kimlar to'lamadi?",
    "qarzdorlar ro'yxati",
    "bugungi darslar",
    "ertangi darslar",
    "o'quvchilar ro'yxati",
    "excelni yangila",
    "bot holati",
    "onlayn bo'l",
    "oflayn bo'l"
]

def classify_admin_query(text: str):
    lower = text.lower()
    
    # 1. Diagnostic / Progress
    if re.search(r"o'zlashtir|ozlashtir|tushunmayapti|tushunmadi|tushunyapti|qiynalyapti|ahvoli|o'qiyapti|darajasi", lower):
        target = extract_target_student_name(text)
        student = find_student_by_name_or_user(None, target)
        return "STUDENT_PROGRESS", student, target
        
    # 2. Payments
    if re.search(r"to'lov|tolov|to'ladimi|toladimi|to'laganmi|tolaganmi|qarzdor|to'lamadi|tolamadi", lower):
        if re.search(r"kimlar|kim\b|hamma|ro'yxat|royxat", lower) or "qarzdor" in lower:
            return "DEBTORS_LIST", None, None
        target = extract_target_student_name(text)
        student = find_student_by_name_or_user(None, target)
        if student:
            return "STUDENT_PAYMENT", student, target
        return "GENERAL_PAYMENTS", None, target

    # 3. Schedule
    if re.search(r"dars jadval|jadvali|jadval|darslari|darsi|dars qachon", lower):
        if "bugun" in lower:
            return "TODAY_LESSONS", None, None
        if "erta" in lower:
            return "TOMORROW_LESSONS", None, None
        target = extract_target_student_name(text)
        student = find_student_by_name_or_user(None, target)
        if student:
            return "STUDENT_SCHEDULE", student, target
        return "GENERAL_SCHEDULE", None, target

    # 4. General Today / Tomorrow
    if re.search(r"bugung?i? dars", lower):
        return "TODAY_LESSONS", None, None
    if re.search(r"ertang?i? dars", lower):
        return "TOMORROW_LESSONS", None, None

    # 5. Members / Students
    if re.search(r"o'quvchi|oquvchi|a'zolar|azolar|talabalar", lower):
        return "STUDENTS_LIST", None, None

    # 6. Management actions
    if "excel" in lower and ("yangila" in lower or "baza" in lower):
        return "EXCEL_REFRESH", None, None
    if re.search(r"bot holati|status|holat", lower):
        return "STATUS", None, None
    if re.search(r"onlayn bo'l|onlayn qil|online", lower):
        return "SET_ONLINE", None, None
    if re.search(r"oflayn bo'l|oflayn qil|offline", lower):
        return "SET_OFFLINE", None, None

    return "UNKNOWN_AI", None, None

print("=== ADMIN NATURAL QUERY CLASSIFICATION TEST ===")
for q in test_queries:
    action, s, t = classify_admin_query(q)
    s_name = s["name"] if s else "None"
    print(f"{q!r:35} -> Action: {action:18} -> Student: {s_name} (Target: {t})")

import asyncio
from unittest.mock import AsyncMock, MagicMock
from config import ADMIN_ID
from bot import handle_admin_natural_query

async def test_bot_admin_queries():
    print("\n=== INTEGRATION TEST: handle_admin_natural_query ===")
    queries_to_test = [
        "murodni dars jadvali",
        "murodning to'lovi",
        "murod to'ladimi?",
        "murodning o'zlashtirishi qanday",
        "kimlar to'lamadi?",
        "bugungi darslar",
        "ertangi darslar",
        "o'quvchilar ro'yxati",
        "bot holati",
        "onlayn bo'l",
        "oflayn bo'l",
        "reyting",
        "murodga 50 xp",
        "dashboard",
        "yordam"
    ]
    
    for q in queries_to_test:
        update = MagicMock()
        update.effective_user.id = ADMIN_ID
        update.message = MagicMock()
        update.message.text = q
        update.message.reply_text = AsyncMock()
        update.message.reply_markdown = AsyncMock()
        
        context = MagicMock()
        context.bot = MagicMock()
        context.bot.send_message = AsyncMock()
        
        handled = await handle_admin_natural_query(update, context, q)
        print(f"[QUERY] {q!r:32} -> Handled: {handled}")
        assert handled is True, f"Failed to handle: {q}"
    print("ALL ADMIN NATURAL QUERIES TEST PASSED! [OK]")

asyncio.run(test_bot_admin_queries())


