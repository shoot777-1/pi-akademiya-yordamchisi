import sqlite3
import json
from typing import List, Dict, Optional, Any
from datetime import datetime, date, timedelta
import calendar
from contextlib import closing
from config import DB_PATH

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Talabalar jadvali
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        course_name TEXT,
        username TEXT,
        telegram_id INTEGER,
        phone TEXT,
        due_day INTEGER NOT NULL, -- Har oyning qaysi kuni to'lov (1-31)
        september_paid TEXT,      -- Sentabr oyi to'lov holati
        last_notified_date TEXT,  -- Oxirgi marta qachon to'lov eslatildi (YYYY-MM-DD)
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Har kungi dars jadvali (oy, kun, vaqt, talaba ismi, kurs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        month_name TEXT NOT NULL,
        day_number INTEGER NOT NULL,
        student_name TEXT NOT NULL,
        course_name TEXT,
        lesson_time TEXT NOT NULL
    );
    """)
    
    # Sozlamalar
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)
    
    columns = {r[1] for r in cursor.execute("PRAGMA table_info(daily_lessons)")}
    if "lesson_date" not in columns:
        cursor.execute("ALTER TABLE daily_lessons ADD COLUMN lesson_date TEXT")
        from operations import tashkent_now
        for row in cursor.execute("SELECT id, month_name, day_number FROM daily_lessons").fetchall():
            try:
                import re
                match = re.search(r"\b(20\d{2})\b", row["month_name"])
                year = int(match.group(1)) if match else tashkent_now().year
                value = date(year, month_number(row["month_name"]), row["day_number"]).isoformat()
                cursor.execute("UPDATE daily_lessons SET lesson_date=? WHERE id=?", (value, row["id"]))
            except (ValueError, TypeError):
                pass
    cursor.execute("""CREATE TABLE IF NOT EXISTS payments (
        student_id INTEGER NOT NULL, period TEXT NOT NULL, paid_at TEXT NOT NULL,
        PRIMARY KEY(student_id, period))""")
    if "cancelled" not in columns:
        cursor.execute("ALTER TABLE daily_lessons ADD COLUMN cancelled INTEGER NOT NULL DEFAULT 0")
    if not cursor.execute("SELECT 1 FROM settings WHERE key='legacy_payments_migrated'").fetchone():
        periods = [r[0] for r in cursor.execute(
            "SELECT DISTINCT substr(lesson_date,1,7) FROM daily_lessons WHERE substr(lesson_date,6,2)='09'")]
        if len(periods) == 1:
            for student in cursor.execute("SELECT id, september_paid FROM students").fetchall():
                if is_paid_value(student["september_paid"]):
                    cursor.execute("INSERT OR IGNORE INTO payments VALUES (?, ?, ?)",
                                   (student["id"], periods[0], datetime.now().isoformat()))
        cursor.execute("INSERT INTO settings VALUES ('legacy_payments_migrated', '1')")
    cursor.execute("""CREATE TABLE IF NOT EXISTS telegram_members (
        telegram_id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, username TEXT,
        first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS member_chats (
        telegram_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, joined_at TEXT NOT NULL,
        PRIMARY KEY (telegram_id, chat_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS payment_events (
        id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, period TEXT NOT NULL,
        paid INTEGER NOT NULL, actor_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(chat_id, message_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS student_learning_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        student_name TEXT,
        telegram_id INTEGER,
        question TEXT NOT NULL,
        ai_response TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS student_gamification (
        student_id INTEGER PRIMARY KEY,
        student_name TEXT NOT NULL,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        title TEXT DEFAULT 'Apprentice',
        tasks_solved INTEGER DEFAULT 0,
        questions_asked INTEGER DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS quiz_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        admin_id INTEGER NOT NULL,
        topic TEXT NOT NULL,
        total_questions INTEGER DEFAULT 10,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS quiz_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        poll_id TEXT UNIQUE NOT NULL,
        message_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        correct_option_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS quiz_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        poll_id TEXT NOT NULL,
        telegram_user_id INTEGER NOT NULL,
        user_name TEXT NOT NULL,
        student_id INTEGER,
        chosen_option_id INTEGER NOT NULL,
        is_correct INTEGER NOT NULL,
        xp_awarded INTEGER DEFAULT 0,
        answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(session_id, poll_id, telegram_user_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS quiz_bank (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_category TEXT NOT NULL DEFAULT 'python',
        topic TEXT NOT NULL,
        question_text TEXT UNIQUE NOT NULL,
        options_json TEXT NOT NULL,
        correct_option_id INTEGER NOT NULL,
        explanation TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def add_or_update_student(name: str, due_day: int, course_name: Optional[str] = None, 
                          username: Optional[str] = None, phone: Optional[str] = None, 
                          telegram_id: Optional[int] = None, september_paid: Optional[str] = None, *, connection=None) -> int:
    conn = connection if connection is not None else get_connection()
    cursor = conn.cursor()
    
    clean_username = username.strip().replace("@", "") if (username and username.strip() != "@") else None
    
    cursor.execute("SELECT id FROM students WHERE LOWER(name) = LOWER(?)", (name.strip(),))
    existing = cursor.fetchone()
        
    if existing:
        student_id = existing["id"]
        cursor.execute("""
            UPDATE students 
            SET name = ?, course_name = COALESCE(?, course_name), due_day = ?, 
                username = COALESCE(?, username), phone = COALESCE(?, phone), 
                telegram_id = COALESCE(?, telegram_id), september_paid = COALESCE(?, september_paid),
                active = 1
            WHERE id = ?
        """, (name.strip(), course_name, due_day, clean_username, phone, telegram_id, september_paid, student_id))
    else:
        cursor.execute("""
            INSERT INTO students (name, course_name, username, phone, due_day, telegram_id, september_paid, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (name.strip(), course_name, clean_username, phone, due_day, telegram_id, september_paid))
        student_id = cursor.lastrowid
        
    if connection is None:
        conn.commit()
        conn.close()
    return student_id

def get_all_students(active_only: bool = True) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT * FROM students WHERE active = 1 ORDER BY due_day ASC, name ASC")
    else:
        cursor.execute("SELECT * FROM students ORDER BY due_day ASC, name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_students_due_for_reminder(target_day: int, today_str: str) -> List[Dict[str, Any]]:
    """Next-day dues, clamped to month end, excluding paid months."""
    target = date.fromisoformat(today_str) + timedelta(days=1)
    if target.day != target_day:
        raise ValueError("Eslatma kuni ertangi sana bilan mos emas")
    last_day = calendar.monthrange(target.year, target.month)[1]
    with closing(get_connection()) as conn:
        rows = conn.execute("""
            SELECT s.* FROM students s WHERE active=1
            AND MIN(due_day, ?) = ?
            AND (last_notified_date IS NULL OR last_notified_date != ?)
            AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.student_id=s.id AND p.period=?)
            """, (last_day, target.day, today_str, target.strftime("%Y-%m"))).fetchall()
        return [dict(row) for row in rows]


def set_payment(student_id, period, paid=True):
    date.fromisoformat(period + "-01")
    with closing(get_connection()) as conn, conn:
        if not conn.execute("SELECT id FROM students WHERE id=?", (student_id,)).fetchone():
            raise ValueError("Bunday o'quvchi ID topilmadi")
        if paid:
            conn.execute("INSERT OR REPLACE INTO payments VALUES (?, ?, ?)",
                         (student_id, period, datetime.now().isoformat()))
        else:
            conn.execute("DELETE FROM payments WHERE student_id=? AND period=?", (student_id, period))


def get_paid_students(period):
    with closing(get_connection()) as conn:
        return {r[0] for r in conn.execute("SELECT student_id FROM payments WHERE period=?", (period,))}


def mark_student_notified(student_id: int, today_str: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET last_notified_date = ? WHERE id = ?", (today_str, student_id))
    conn.commit()
    conn.close()

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
          "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]


def is_paid_value(value):
    normalized = str(value or "").strip().lower().replace("’", "'").replace("‘", "'").replace("ʻ", "'")
    return normalized in {"to'landi", "tolandi", "to'langan", "tolangan", "paid"}


def month_number(name):
    import re
    normalized = name.lower().replace("sentyabr", "sentabr").replace("oktyabr", "oktabr")
    for number, month in enumerate(MONTHS, 1):
        if re.search(r"\b" + month + r"\b", normalized):
            return number
    raise ValueError("Jadval varag'i nomida oy ko'rsatilishi kerak (masalan: Sentabr 2026)")


def save_daily_lessons(lessons: List[Dict[str, Any]], *, connection=None):
    conn = connection if connection is not None else get_connection()
    try:
        # Only replace the imported months, preserving other months.
        periods = {item["lesson_date"][:7] for item in lessons}
        for period in periods:
            conn.execute("DELETE FROM daily_lessons WHERE substr(lesson_date,1,7)=?", (period,))
        for item in lessons:
            conn.execute("""INSERT INTO daily_lessons
                (month_name, day_number, student_name, course_name, lesson_time, lesson_date)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (item["month_name"], item["day_number"], item["student_name"],
                 item.get("course_name"), item["lesson_time"], item["lesson_date"]))
        if connection is None:
            conn.commit()
    except Exception:
        if connection is None:
            conn.rollback()
        raise
    finally:
        if connection is None:
            conn.close()


def get_lessons_for_date(target: date) -> List[Dict[str, Any]]:
    with closing(get_connection()) as conn:
        rows = conn.execute("SELECT * FROM daily_lessons WHERE lesson_date=? AND cancelled=0 ORDER BY lesson_time, student_name",
                            (target.isoformat(),)).fetchall()
        return [dict(row) for row in rows]


def change_lesson(lesson_id, target=None, lesson_time=None):
    with closing(get_connection()) as conn, conn:
        if not conn.execute("SELECT id FROM daily_lessons WHERE id=?", (lesson_id,)).fetchone():
            raise ValueError("Dars ID topilmadi")
        if target is None:
            conn.execute("UPDATE daily_lessons SET cancelled=1 WHERE id=?", (lesson_id,))
        else:
            target = date.fromisoformat(target)
            from datetime import time
            parsed = time.fromisoformat(lesson_time)
            conn.execute("""UPDATE daily_lessons SET lesson_date=?, day_number=?, month_name=?,
                lesson_time=?, cancelled=0 WHERE id=?""",
                (target.isoformat(), target.day, MONTHS[target.month - 1], parsed.strftime("%H:%M"), lesson_id))


def get_lessons_for_day(day_number: int, month_name=None) -> List[Dict[str, Any]]:
    today = datetime.now()
    month = month_number(month_name) if month_name else today.month
    return get_lessons_for_date(date(today.year, month, day_number))


def log_student_activity(student_id: Optional[int], student_name: Optional[str], 
                         telegram_id: Optional[int], question: str, ai_response: Optional[str] = None):
    with closing(get_connection()) as conn, conn:
        conn.execute("""
            INSERT INTO student_learning_logs (student_id, student_name, telegram_id, question, ai_response)
            VALUES (?, ?, ?, ?, ?)
        """, (student_id, student_name, telegram_id, question[:3000], (ai_response or "")[:3000]))


def get_student_learning_logs(student_id: Optional[int] = None, student_name: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]:
    with closing(get_connection()) as conn:
        if student_id:
            rows = conn.execute("""
                SELECT * FROM student_learning_logs 
                WHERE student_id = ? ORDER BY id DESC LIMIT ?
            """, (student_id, limit)).fetchall()
        elif student_name:
            rows = conn.execute("""
                SELECT * FROM student_learning_logs 
                WHERE LOWER(student_name) LIKE LOWER(?) ORDER BY id DESC LIMIT ?
            """, (f"%{student_name.strip()}%", limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM student_learning_logs ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_track_from_course(course_name: Optional[str]) -> str:
    """Kurs nomiga qarab yo'nalishni aniqlash: dev (dasturlash), pc (kompyuter savodxonligi), robot (robototexnika)"""
    if not course_name:
        return "general"
    c = course_name.lower()
    if any(k in c for k in ["python", "dastur", "kod", "developer", "backend", "frontend"]):
        return "dev"
    elif any(k in c for k in ["kompyuter", "savodxon", "ofis", "office", "excel"]):
        return "pc"
    elif any(k in c for k in ["robot", "arduino", "mexatron", "muhandis"]):
        return "robot"
    return "general"


def calculate_level_and_title(xp: int, course_name: Optional[str] = None) -> tuple[int, str]:
    """O'quvchining yo'nalishiga va to'plagan XP miqdoriga mos unvon va darajani hisoblash"""
    track = get_track_from_course(course_name)

    TITLES = {
        "dev": [
            (100, 1, "🥉 Junior Coder"),
            (300, 2, "🥈 Python Dev"),
            (600, 3, "🥇 Algoritm Ustasi"),
            (1000, 4, "💎 Software Architect"),
            (float("inf"), 5, "🚀 Cyber Code Ninja"),
        ],
        "pc": [
            (100, 1, "🥉 IT Izquvar"),
            (300, 2, "🥈 Windows Bilimdoni"),
            (600, 3, "🥇 Office & Excel Master"),
            (1000, 4, "💎 Tizim Administratori"),
            (float("inf"), 5, "👑 IT Mutaxassis Lider"),
        ],
        "robot": [
            (100, 1, "🥉 Yosh Konstruktor"),
            (300, 2, "🥈 Sxema Ustasi"),
            (600, 3, "🥇 Arduino Injeneri"),
            (1000, 4, "💎 Kiber Mexatronik"),
            (float("inf"), 5, "🦾 Cyber Robo Master"),
        ],
        "general": [
            (100, 1, "🥉 Boshlang'ich (Apprentice)"),
            (300, 2, "🥈 Yosh Izlanuvchi"),
            (600, 3, "🥇 Ilg'or Bilimdon"),
            (1000, 4, "💎 Katta Mutaxassis"),
            (float("inf"), 5, "🚀 Cyber Tech Lideri"),
        ]
    }

    tier_list = TITLES.get(track, TITLES["general"])
    for threshold, lvl, title in tier_list:
        if xp < threshold:
            return lvl, title

    return 5, tier_list[-1][2]


def add_student_xp(student_id: int, student_name: str, xp_delta: int, is_task: bool = False, is_question: bool = False, course_name: Optional[str] = None) -> Dict[str, Any]:
    with closing(get_connection()) as conn, conn:
        if not course_name:
            st = conn.execute("SELECT course_name FROM students WHERE id = ?", (student_id,)).fetchone()
            if st and st["course_name"]:
                course_name = st["course_name"]

        row = conn.execute("SELECT * FROM student_gamification WHERE student_id = ?", (student_id,)).fetchone()
        if row:
            curr_xp = row["xp"] + xp_delta
            old_level = row["level"]
            tasks = row["tasks_solved"] + (1 if is_task else 0)
            questions = row["questions_asked"] + (1 if is_question else 0)
            new_level, title = calculate_level_and_title(curr_xp, course_name)
            conn.execute("""
                UPDATE student_gamification
                SET xp = ?, level = ?, title = ?, tasks_solved = ?, questions_asked = ?, updated_at = CURRENT_TIMESTAMP
                WHERE student_id = ?
            """, (curr_xp, new_level, title, tasks, questions, student_id))
            return {
                "student_id": student_id,
                "name": student_name,
                "old_xp": row["xp"],
                "new_xp": curr_xp,
                "xp_added": xp_delta,
                "old_level": old_level,
                "new_level": new_level,
                "level_up": new_level > old_level,
                "title": title
            }
        else:
            curr_xp = max(0, xp_delta)
            new_level, title = calculate_level_and_title(curr_xp, course_name)
            tasks = 1 if is_task else 0
            questions = 1 if is_question else 0
            conn.execute("""
                INSERT INTO student_gamification (student_id, student_name, xp, level, title, tasks_solved, questions_asked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (student_id, student_name, curr_xp, new_level, title, tasks, questions))
            return {
                "student_id": student_id,
                "name": student_name,
                "old_xp": 0,
                "new_xp": curr_xp,
                "xp_added": xp_delta,
                "old_level": 1,
                "new_level": new_level,
                "level_up": False,
                "title": title
            }


def get_student_gamification(student_id: Optional[int] = None, student_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with closing(get_connection()) as conn:
        if student_id:
            row = conn.execute("SELECT * FROM student_gamification WHERE student_id = ?", (student_id,)).fetchone()
        elif student_name:
            row = conn.execute("SELECT * FROM student_gamification WHERE LOWER(student_name) LIKE LOWER(?)", (f"%{student_name.strip()}%",)).fetchone()
        else:
            return None
        return dict(row) if row else None


def get_leaderboard(limit: int = 15) -> List[Dict[str, Any]]:
    with closing(get_connection()) as conn:
        rows = conn.execute("""
            SELECT g.*, s.course_name 
            FROM student_gamification g
            LEFT JOIN students s ON g.student_id = s.id
            ORDER BY g.xp DESC, g.level DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def reset_all_gamification_to_zero():
    """Barcha o'quvchilar reytingini 0 dan toza boshlash va yo'nalishiga mos unvon berish"""
    with closing(get_connection()) as conn, conn:
        students = conn.execute("SELECT id, course_name FROM students").fetchall()
        for s in students:
            lvl, title = calculate_level_and_title(0, s["course_name"])
            conn.execute("""
                UPDATE student_gamification
                SET xp = 0, level = ?, title = ?, tasks_solved = 0, questions_asked = 0, updated_at = CURRENT_TIMESTAMP
                WHERE student_id = ?
            """, (lvl, title, s["id"]))


def seed_initial_gamification():
    with closing(get_connection()) as conn, conn:
        students = conn.execute("SELECT id, name, course_name FROM students WHERE active = 1").fetchall()
        existing_ids = {r[0] for r in conn.execute("SELECT student_id FROM student_gamification").fetchall()}
        for s in students:
            lvl, title = calculate_level_and_title(0, s["course_name"])
            if s["id"] not in existing_ids:
                conn.execute("""
                    INSERT INTO student_gamification (student_id, student_name, xp, level, title, tasks_solved, questions_asked)
                    VALUES (?, ?, 0, ?, ?, 0, 0)
                """, (s["id"], s["name"], lvl, title))
            else:
                # Mavjud bo'lsa va hali 0 XP bo'lsa, unvonini yo'nalishiga moslab qo'yamiz
                conn.execute("""
                    UPDATE student_gamification
                    SET title = ?
                    WHERE student_id = ? AND xp = 0
                """, (title, s["id"]))


def create_quiz_session(chat_id: int, admin_id: int, topic: str, total_questions: int = 10) -> int:
    """Yangi test/viktorina sessiyasini yaratish"""
    with closing(get_connection()) as conn, conn:
        cur = conn.execute("""
            INSERT INTO quiz_sessions (chat_id, admin_id, topic, total_questions, status)
            VALUES (?, ?, ?, ?, 'active')
        """, (chat_id, admin_id, topic, total_questions))
        return cur.lastrowid


def add_quiz_question(session_id: int, poll_id: str, message_id: int, question_text: str, correct_option_id: int):
    """Sessiyaga tegishli savolni poll_id bilan saqlash"""
    with closing(get_connection()) as conn, conn:
        conn.execute("""
            INSERT OR REPLACE INTO quiz_questions (session_id, poll_id, message_id, question_text, correct_option_id)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, str(poll_id), message_id, question_text, correct_option_id))


def get_active_quiz_session(chat_id: int) -> Optional[Dict[str, Any]]:
    """Guruh yoki chatdagi hozirgi faol test sessiyasini olish (eng so'nggi)"""
    with closing(get_connection()) as conn:
        row = conn.execute("""
            SELECT * FROM quiz_sessions
            WHERE chat_id = ? AND status = 'active'
            ORDER BY id DESC LIMIT 1
        """, (chat_id,)).fetchone()
        return dict(row) if row else None


def get_active_quiz_sessions(chat_id: int) -> List[Dict[str, Any]]:
    """Guruh yoki chatdagi barcha faol test sessiyalarini olish"""
    with closing(get_connection()) as conn:
        rows = conn.execute("""
            SELECT * FROM quiz_sessions
            WHERE chat_id = ? AND status = 'active'
            ORDER BY id DESC
        """, (chat_id,)).fetchall()
        return [dict(r) for r in rows]


def get_quiz_session_by_id(session_id: int) -> Optional[Dict[str, Any]]:
    """Sessiya ID bo'yicha ma'lumotni olish"""
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def get_quiz_question_by_poll(poll_id: str) -> Optional[Dict[str, Any]]:
    """Poll ID bo'yicha savol va sessiyani topish"""
    with closing(get_connection()) as conn:
        row = conn.execute("""
            SELECT q.*, s.status as session_status, s.chat_id, s.topic
            FROM quiz_questions q
            JOIN quiz_sessions s ON q.session_id = s.id
            WHERE q.poll_id = ?
        """, (str(poll_id),)).fetchone()
        return dict(row) if row else None


def record_quiz_answer(session_id: int, poll_id: str, telegram_user_id: int, user_name: str,
                       student_id: Optional[int], chosen_option_id: int, is_correct: bool,
                       xp_awarded: int = 1) -> bool:
    """O'quvchining test javobini qayd etish. Agar birinchi marta javob berayotgan bo'lsa True qaytaradi"""
    with closing(get_connection()) as conn, conn:
        existing = conn.execute("""
            SELECT id FROM quiz_answers
            WHERE session_id = ? AND poll_id = ? AND telegram_user_id = ?
        """, (session_id, str(poll_id), telegram_user_id)).fetchone()
        if existing:
            return False

        conn.execute("""
            INSERT INTO quiz_answers (session_id, poll_id, telegram_user_id, user_name, student_id, chosen_option_id, is_correct, xp_awarded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, str(poll_id), telegram_user_id, user_name, student_id, chosen_option_id, 1 if is_correct else 0, xp_awarded if is_correct else 0))
        return True


def get_quiz_session_results(session_id: int) -> List[Dict[str, Any]]:
    """Sessiya bo'yicha barcha qatnashuvchilar natijalari va to'plagan ballarini saralab olish"""
    with closing(get_connection()) as conn:
        rows = conn.execute("""
            SELECT 
                telegram_user_id,
                user_name,
                student_id,
                COUNT(*) as total_answered,
                SUM(is_correct) as correct_count,
                SUM(xp_awarded) as total_xp_earned
            FROM quiz_answers
            WHERE session_id = ?
            GROUP BY telegram_user_id
            ORDER BY correct_count DESC, total_answered ASC
        """, (session_id,)).fetchall()
        return [dict(r) for r in rows]


def finish_quiz_session(session_id: int) -> Optional[Dict[str, Any]]:
    """Test sessiyasini yakunlash va tugatish"""
    with closing(get_connection()) as conn, conn:
        conn.execute("""
            UPDATE quiz_sessions
            SET status = 'finished', finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session_id,))
        row = conn.execute("SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def get_session_poll_message_ids(session_id: int) -> List[Dict[str, Any]]:
    """Sessiyaga tegishli barcha poll message_id larini olish (pollni to'xtatish uchun)"""
    with closing(get_connection()) as conn:
        rows = conn.execute("SELECT poll_id, message_id FROM quiz_questions WHERE session_id = ?", (session_id,)).fetchall()
        return [dict(r) for r in rows]


def save_quiz_to_bank(topic: str, questions: List[Dict[str, Any]], course_category: Optional[str] = None) -> int:
    """Test savollarini doimiy testlar bazasiga (quiz_bank) eslab qolish"""
    if not questions:
        return 0

    topic_lower = topic.lower()
    if not course_category:
        if "excel" in topic_lower or "formula" in topic_lower:
            course_category = "excel"
        elif "robot" in topic_lower or "arduino" in topic_lower:
            course_category = "robototexnika"
        elif "savodxon" in topic_lower or "kompyuter" in topic_lower or "word" in topic_lower or "windows" in topic_lower:
            course_category = "kompyuter"
        else:
            course_category = "python"

    inserted = 0
    with closing(get_connection()) as conn, conn:
        for q in questions:
            q_text = str(q.get("question", "")).strip()
            opts = q.get("options") or []
            if not q_text or len(opts) < 2:
                continue
            corr = q.get("correct_option_id", 0)
            expl = str(q.get("explanation", "")).strip()
            opts_json = json.dumps(opts, ensure_ascii=False)
            try:
                cur = conn.execute("""
                    INSERT OR IGNORE INTO quiz_bank (course_category, topic, question_text, options_json, correct_option_id, explanation)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (course_category, topic, q_text, opts_json, corr, expl))
                if cur.rowcount > 0:
                    inserted += 1
            except Exception:
                pass
    return inserted


def get_random_quiz_from_bank(category: Optional[str] = None, count: int = 10) -> Optional[Dict[str, Any]]:
    """Testlar bazasidan tasodifiy savollarni tanlab olish"""
    with closing(get_connection()) as conn:
        if category:
            rows = conn.execute("""
                SELECT * FROM quiz_bank
                WHERE course_category = ?
                ORDER BY RANDOM()
                LIMIT ?
            """, (category, count)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM quiz_bank
                ORDER BY RANDOM()
                LIMIT ?
            """, (count)).fetchall()

        # Agar so'ralgan kategoriyada yetarli bo'lmasa, umuman bazadan to'ldiramiz
        if len(rows) < count:
            needed = count - len(rows)
            existing_ids = [r["id"] for r in rows]
            placeholders = ",".join(["?"] * len(existing_ids)) if existing_ids else "-1"
            extra_rows = conn.execute(f"""
                SELECT * FROM quiz_bank
                WHERE id NOT IN ({placeholders})
                ORDER BY RANDOM()
                LIMIT ?
            """, (*existing_ids, needed) if existing_ids else (needed,)).fetchall()
            rows = list(rows) + list(extra_rows)

        if not rows:
            return None

        questions = []
        for r in rows:
            raw_opts = r["options_json"]
            opts = json.loads(raw_opts) if isinstance(raw_opts, str) else raw_opts
            questions.append({
                "question": r["question_text"],
                "options": opts,
                "correct_option_id": r["correct_option_id"],
                "explanation": r["explanation"] or ""
            })

        cat_title = (category or "Python").capitalize()
        return {
            "success": True,
            "topic": f"{cat_title} (Tasodifiy testlar bazasidan)",
            "questions": questions,
            "from_bank": True
        }


def get_quiz_bank_stats() -> Dict[str, Any]:
    """Testlar bazasi statistikasini olish"""
    with closing(get_connection()) as conn:
        total = conn.execute("SELECT COUNT(*) FROM quiz_bank").fetchone()[0]
        cat_counts = conn.execute("""
            SELECT course_category, COUNT(*) as cnt
            FROM quiz_bank
            GROUP BY course_category
        """).fetchall()
        categories = {r["course_category"]: r["cnt"] for r in cat_counts}
        return {
            "total": total,
            "categories": categories
        }


def seed_initial_quiz_bank():
    """Bazada savollar bo'lmasa, dastlabki Python savollarini kiritish"""
    with closing(get_connection()) as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM quiz_bank").fetchone()[0]
        if cnt > 0:
            return

    initial_python_questions = [
        {
            "question": "Python ro'yxatiga (list) yangi elementni oxiriga qo'shish uchun qaysi metod ishlatiladi?",
            "options": ["append()", "add()", "insert()", "push()"],
            "correct_option_id": 0,
            "explanation": "append() metodi yangi elementni ro'yxatning eng oxiriga qo'shadi."
        },
        {
            "question": "Python-da funksiya e'lon qilish uchun qaysi kalit so'z ishlatiladi?",
            "options": ["func", "function", "def", "define"],
            "correct_option_id": 2,
            "explanation": "def kalit so'zi 'define' so'zidan olingan bo'lib, funksiya yaratishda ishlatiladi."
        },
        {
            "question": "Python-da butun sonli bo'lish (qoldiqsiz bo'lish) operatori qaysi?",
            "options": ["/", "//", "%", "div"],
            "correct_option_id": 1,
            "explanation": "// operatori faqat butun qismini qaytaradi, masalan 7 // 2 = 3."
        },
        {
            "question": "Python-da qoldiqni topish operatori qaysi?",
            "options": ["mod", "%", "//", "rem"],
            "correct_option_id": 1,
            "explanation": "% operatori bo'linmaning qoldig'ini hisoblaydi, masalan 7 % 3 = 1."
        },
        {
            "question": "Python-da darajaga ko'tarish operatori qaysi?",
            "options": ["^", "**", "pow", "^^"],
            "correct_option_id": 1,
            "explanation": "** operatori sonni darajaga ko'taradi, masalan 2 ** 3 = 8."
        },
        {
            "question": "Python-da o'zgarmas (immutable) ketma-ketlik turi qaysi?",
            "options": ["list", "dict", "tuple", "set"],
            "correct_option_id": 2,
            "explanation": "tuple (kortej) yaratilgandan keyin uning elementlarini o'zgartirib bo'lmaydi."
        },
        {
            "question": "Lug'atdan (dict) berilgan kalit bo'yicha xatosiz xavfsiz qiymat olish metodi qaysi?",
            "options": ["find()", "get()", "fetch()", "lookup()"],
            "correct_option_id": 1,
            "explanation": "get() metodi agar kalit mavjud bo'lmasa KeyError bermasdan None qaytaradi."
        },
        {
            "question": "Satr yoki ro'yxat uzunligini aniqlash uchun qaysi o'rnatilgan funksiya ishlatiladi?",
            "options": ["size()", "count()", "length()", "len()"],
            "correct_option_id": 3,
            "explanation": "len() funksiyasi obyektning elementlari sonini qaytaradi."
        },
        {
            "question": "Takrorlanmas yagona elementlardan tashkil topgan to'plam turi qaysi?",
            "options": ["list", "set", "tuple", "array"],
            "correct_option_id": 1,
            "explanation": "set to'plamida elementlar dublikat bo'lmaydi va tartiblanmagan bo'ladi."
        },
        {
            "question": "Python-da input() funksiyasi orqali kiritilgan ma'lumot qaysi ma'lumot turida bo'ladi?",
            "options": ["int", "str", "float", "auto"],
            "correct_option_id": 1,
            "explanation": "input() foydalanuvchi kiritgan har qanday ma'lumotni satr (str) sifatida qabul qiladi."
        },
        {
            "question": "Satrdagi barcha harflarni katta harfga aylantirish uchun qaysi metod ishlatiladi?",
            "options": ["capitalize()", "upper()", "title()", "toUpper()"],
            "correct_option_id": 1,
            "explanation": "upper() satrdagi barcha harflarni bosh harfga o'tkazadi."
        },
        {
            "question": "Siklni (loop) muddatidan oldin to'xtatish uchun qaysi kalit so'z ishlatiladi?",
            "options": ["stop", "break", "exit", "return"],
            "correct_option_id": 1,
            "explanation": "break operatori siklni darhol yakunlaydi."
        },
        {
            "question": "Siklda joriy iteratsiyani o'tkazib yuborib, keyingisiga o'tish uchun nima ishlatiladi?",
            "options": ["skip", "pass", "continue", "next"],
            "correct_option_id": 2,
            "explanation": "continue siklning joriy qadamini to'xtatib, keyingi qadamiga o'tadi."
        },
        {
            "question": "Kvadrat ildizni hisoblash uchun math kutubxonasining qaysi funksiyasi chaqiriladi?",
            "options": ["math.sqr()", "math.root()", "math.sqrt()", "math.power()"],
            "correct_option_id": 2,
            "explanation": "math.sqrt() kvadrat ildizni hisoblaydi (Square Root)."
        },
        {
            "question": "Obyektning ma'lumot turini aniqlash uchun qaysi funksiya ishlatiladi?",
            "options": ["type()", "typeof()", "kind()", "class()"],
            "correct_option_id": 0,
            "explanation": "type(x) berilgan o'zgaruvchi yoki qiymatning turini qaytaradi."
        },
        {
            "question": "Ro'yxatning oxirgi elementini sug'urib olib o'chirish qaysi metod orqali bajariladi?",
            "options": ["remove()", "del()", "pop()", "discard()"],
            "correct_option_id": 2,
            "explanation": "pop() metodi ro'yxatdan oxirgi (yoki indeksdagi) elementni olib tashlaydi va qaytaradi."
        },
        {
            "question": "range(2, 10, 2) qanday sonlar ketma-ketligini hosil qiladi?",
            "options": ["[2, 3, 4, 5, 6, 7, 8, 9]", "[2, 4, 6, 8]", "[2, 4, 6, 8, 10]", "[4, 6, 8]"],
            "correct_option_id": 1,
            "explanation": "Boshlanishi 2, qadami 2 va 10 kirmaydi: 2, 4, 6, 8."
        },
        {
            "question": "Python-da satrlarni bo'lib, ro'yxatga aylantirish uchun qaysi metod ishlatiladi?",
            "options": ["divide()", "slice()", "split()", "partition()"],
            "correct_option_id": 2,
            "explanation": "split() satrni bo'sh joy yoki ajratuvchi bo'yicha bo'laklarga ajratib ro'yxat beradi."
        },
        {
            "question": "Quyidagi qiymatlardan qaysi biri mantiqiy False hisoblanadi?",
            "options": ["0", "[]", "''", "Barchasi to'g'ri"],
            "correct_option_id": 3,
            "explanation": "Python-da 0, bo'sh ro'yxat [], bo'sh satr '' va None mantiqiy jihatdan False qiymatiga teng."
        },
        {
            "question": "Python-da xatoliklarni ushlash va qayta ishlash qaysi blok orqali amalga oshiriladi?",
            "options": ["try / catch", "try / except", "do / rescue", "test / fail"],
            "correct_option_id": 1,
            "explanation": "Python-da xatolar 'try' va 'except' bloklari orqali ushlanadi."
        }
    ]

    save_quiz_to_bank("Python Asoslari", initial_python_questions, course_category="python")


init_db()
seed_initial_gamification()
seed_initial_quiz_bank()
