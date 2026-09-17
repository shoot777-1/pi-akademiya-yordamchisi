"""
Cyber Tech Academy - Sinov darsiga yozilish va IT moyillik testi xizmati.
Ota-onalarni jalb qilish (Lead Generation) va test orqali yo'nalish aniqlash moduli.
"""
from contextlib import closing
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from database import get_connection
from operations import tashkent_now

def init_leads_db():
    with closing(get_connection()) as conn, conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            user_full_name TEXT,
            username TEXT,
            child_age TEXT,
            chosen_course TEXT,
            phone_number TEXT,
            quiz_result TEXT,
            status TEXT DEFAULT 'yangi', -- yangi, bog'lanildi, qatnashdi
            created_at TEXT
        );
        """)

# Test savollari
IT_QUIZ_QUESTIONS = [
    {
        "id": 1,
        "question": "1️⃣ Farzandingiz bo‘sh vaqtida kompyuter yoki telefonda ko‘proq nima qilishni yoqtiradi?",
        "options": [
            ("🎮 O‘yinlar qanday ishlashiga qiziqadi", "python"),
            ("🤖 Konstruktor va texnikalarni buzib-yig‘adi", "robot"),
            ("🎨 Chizish, fotolar va videolarga qiziqadi", "design"),
            ("💻 Endi kompyuterni mustaqil o‘rganmoqda", "basic")
        ]
    },
    {
        "id": 2,
        "question": "2️⃣ Maktabda qaysi fanlarni ko‘proq qiziqish bilan o‘rganadi?",
        "options": [
            ("🔢 Matematika va mantiqiy misollar", "python"),
            ("⚙️ Fizika va mehnat ta’limi", "robot"),
            ("📐 Tasviriy san’at va adabiyot", "design"),
            ("📚 Barcha fanlarni teng o‘zlashtiradi", "basic")
        ]
    },
    {
        "id": 3,
        "question": "3️⃣ Farzandingiz qanday xarakterga ega?",
        "options": [
            ("🧐 Diqqatli, jumboqlarni oxirigacha yechadi", "python"),
            ("🛠 Qo‘li bilan narsalar yasashni yaxshi ko‘radi", "robot"),
            ("💡 Tasavvuri boy, ijodkor va kreativ", "design"),
            ("🗣 Tez muloqotga kirishuvchan va faol", "basic")
        ]
    },
    {
        "id": 4,
        "question": "4️⃣ Kelajakda uning qaysi sohada yetuk mutaxassis bo‘lishini xohlaysiz?",
        "options": [
            ("💻 Dasturchi yoki Sun’iy Intellekt muhandisi", "python"),
            ("🤖 Robototexnika yoki Kiberxavfsizlik mutaxassisi", "robot"),
            ("🎨 Grafik dizayner yoki Video montaj ustasi", "design"),
            ("📊 Zamonaviy IT va ofis dasturlari yetakchisi", "basic")
        ]
    }
]

def save_lead(telegram_id, full_name, username, child_age, chosen_course, phone, quiz_result=""):
    now = tashkent_now().isoformat()
    with closing(get_connection()) as conn, conn:
        cursor = conn.execute("""
            INSERT INTO leads (telegram_id, user_full_name, username, child_age, chosen_course, phone_number, quiz_result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (telegram_id, full_name, username, child_age, chosen_course, phone, quiz_result, now))
        return cursor.lastrowid
