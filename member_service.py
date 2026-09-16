"""Telegram profiles and explicit enrollment; names never auto-link identities."""
from contextlib import closing
import re
from database import get_connection
from operations import tashkent_now


def normalize(text):
    return " ".join(str(text).casefold().translate(str.maketrans({"’": "'", "‘": "'", "ʻ": "'", "`": "'", "ʼ": "'"})).split())


def register_member(user, chat_id):
    if user.is_bot:
        return
    now = tashkent_now().isoformat()
    with closing(get_connection()) as conn, conn:
        conn.execute("""INSERT INTO telegram_members VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,
            username=excluded.username, last_seen=excluded.last_seen""",
            (user.id, user.full_name, user.username, now, now))
        conn.execute("INSERT OR IGNORE INTO member_chats VALUES (?, ?, ?)", (user.id, chat_id, now))


def list_members():
    with closing(get_connection()) as conn:
        return [dict(r) for r in conn.execute("""SELECT m.*, s.id student_id, s.course_name, s.due_day
            FROM telegram_members m LEFT JOIN students s ON s.telegram_id=m.telegram_id
            ORDER BY m.full_name""")]


def link_member(telegram_id, student_id):
    with closing(get_connection()) as conn, conn:
        if not conn.execute("SELECT 1 FROM telegram_members WHERE telegram_id=?", (telegram_id,)).fetchone():
            now = tashkent_now().isoformat()
            conn.execute("INSERT INTO telegram_members VALUES (?, ?, ?, ?, ?)",
                         (telegram_id, f"TG {telegram_id}", None, now, now))
        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
        if not student:
            raise ValueError(f"ID #{student_id} bo'yicha o'quvchi topilmadi")
        if student["telegram_id"] not in (None, telegram_id):
            raise ValueError(f"Bu o'quvchi (ID #{student_id}) allaqachon boshqa Telegram ID ({student['telegram_id']}) bilan bog'langan")
        if conn.execute("SELECT 1 FROM students WHERE telegram_id=? AND id!=?", (telegram_id, student_id)).fetchone():
            existing = conn.execute("SELECT name FROM students WHERE telegram_id=? AND id!=?", (telegram_id, student_id)).fetchone()
            ex_name = existing["name"] if existing else "boshqa o'quvchi"
            raise ValueError(f"Ushbu Telegram ID ({telegram_id}) allaqachon '{ex_name}' profiliga bog'langan")
        conn.execute("UPDATE students SET telegram_id=? WHERE id=?", (telegram_id, student_id))


def enroll_member(telegram_id, name, course, due_day):
    if not name.strip() or not course.strip() or not 1 <= due_day <= 31:
        raise ValueError("Ism, kurs va 1–31 oralig'idagi to'lov kuni kerak")
    with closing(get_connection()) as conn, conn:
        if not conn.execute("SELECT 1 FROM telegram_members WHERE telegram_id=?", (telegram_id,)).fetchone():
            raise ValueError("A'zo hali bazada yo'q. U guruhga qo'shilsin yoki xabar yozsin")
        if conn.execute("SELECT 1 FROM students WHERE telegram_id=?", (telegram_id,)).fetchone():
            raise ValueError("Bu Telegram ID allaqachon o'quvchiga bog'langan")
        if any(normalize(r[0]) == normalize(name) for r in conn.execute("SELECT name FROM students")):
            raise ValueError("Bu ism bazada bor. Mavjud o'quvchi bo'lsa /boglash TG_ID OQUVCHI_ID dan foydalaning; boshqa odam bo'lsa to'liq farqli ism kiriting")
        cursor = conn.execute("""INSERT INTO students(name, course_name, due_day, telegram_id, active)
            VALUES (?, ?, ?, ?, 1)""", (name.strip(), course.strip(), due_day, telegram_id))
        return cursor.lastrowid


def parse_payment(text):
    text = normalize(text).rstrip(".!")
    match = re.fullmatch(r"(?:(.+?)\s+)?(to'ladi|toladi|to'landi|tolandi|to'lagan|tolagan|to'lamadi|tolamadi|to'lanmagan|tolanmagan)(?:\s+(20\d{2}-\d{2}))?", text)
    if not match:
        return None
    target, action, period = match.groups()
    return target, action not in {"to'lamadi", "tolamadi", "to'lanmagan", "tolanmagan"}, period


def find_students(target=None, telegram_id=None):
    with closing(get_connection()) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM students WHERE active=1")]
        if telegram_id is not None:
            return [r for r in rows if r["telegram_id"] == telegram_id]
        target = normalize(target or "")
        if re.fullmatch(r"id\s+\d+", target):
            return [r for r in rows if r["id"] == int(target.split()[1])]
        if target.startswith("@"):
            return [r for r in rows if normalize(r["username"] or "").lstrip("@") == target[1:]]
        exact = [r for r in rows if normalize(r["name"]) == target]
        if exact:
            return exact
        # Whole-name prefix allows 'Ali' but does not match 'Alisher'.
        return [r for r in rows if normalize(r["name"]).startswith(target + " ")] if target else []


def apply_payment(student_id, period, paid, actor_id, chat_id, message_id):
    from datetime import date
    date.fromisoformat(period + "-01")
    now = tashkent_now().isoformat()
    with closing(get_connection()) as conn, conn:
        if not conn.execute("SELECT 1 FROM students WHERE id=?", (student_id,)).fetchone():
            raise ValueError("O'quvchi topilmadi")
        if conn.execute("SELECT 1 FROM payment_events WHERE chat_id=? AND message_id=?", (chat_id, message_id)).fetchone():
            return False
        if paid:
            conn.execute("INSERT OR REPLACE INTO payments VALUES (?, ?, ?)", (student_id, period, now))
        else:
            conn.execute("DELETE FROM payments WHERE student_id=? AND period=?", (student_id, period))
        conn.execute("INSERT INTO payment_events(student_id,period,paid,actor_id,chat_id,message_id,created_at) VALUES (?,?,?,?,?,?,?)",
                     (student_id, period, paid, actor_id, chat_id, message_id, now))
        return True
