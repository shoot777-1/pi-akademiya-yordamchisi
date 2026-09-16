"""Durable source, attempt and teacher approval records in the academy database."""
import json
from contextlib import closing
from database import get_connection, calculate_level_and_title
from config import ADMIN_ID


def schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS book_assignments (
      id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, topic INTEGER NOT NULL,
      telegram_id INTEGER NOT NULL, source_id TEXT NOT NULL, source_json TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(chat_id,topic,telegram_id,source_id));
    CREATE TABLE IF NOT EXISTS book_assignment_messages (
      chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, assignment_id INTEGER NOT NULL,
      PRIMARY KEY(chat_id,message_id));
    CREATE TABLE IF NOT EXISTS book_attempts (
      id INTEGER PRIMARY KEY, assignment_id INTEGER NOT NULL, student_id INTEGER,
      telegram_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
      submission TEXT NOT NULL, file_id TEXT, ai_status TEXT NOT NULL,
      feedback TEXT NOT NULL, errors_json TEXT NOT NULL, teacher_status TEXT,
      teacher_id INTEGER, teacher_note TEXT, reviewed_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(chat_id,message_id));
    CREATE TABLE IF NOT EXISTS book_rewards (
      student_id INTEGER NOT NULL, source_id TEXT NOT NULL, attempt_id INTEGER NOT NULL,
      xp INTEGER NOT NULL, PRIMARY KEY(student_id,source_id));
    """)


def assign(chat_id, topic, telegram_id, source):
    with closing(get_connection()) as conn:
        schema(conn)
        with conn:
            conn.execute("INSERT OR IGNORE INTO book_assignments(chat_id,topic,telegram_id,source_id,source_json) VALUES(?,?,?,?,?)",
                         (chat_id, topic, telegram_id, source['id'], json.dumps(source, ensure_ascii=False)))
            row = conn.execute("SELECT * FROM book_assignments WHERE chat_id=? AND topic=? AND telegram_id=? AND source_id=?",
                               (chat_id, topic, telegram_id, source['id'])).fetchone()
            return dict(row)


def link(assignment_id, chat_id, message_id):
    if not isinstance(message_id, int):
        return
    with closing(get_connection()) as conn:
        schema(conn)
        with conn:
            conn.execute("INSERT OR IGNORE INTO book_assignment_messages VALUES(?,?,?)", (chat_id, message_id, assignment_id))


def resolve(chat_id, topic, user_id, reply_id):
    if not isinstance(reply_id, int):
        return None
    with closing(get_connection()) as conn:
        schema(conn)
        row = conn.execute("""SELECT a.* FROM book_assignments a JOIN book_assignment_messages m ON m.assignment_id=a.id
                            WHERE m.chat_id=? AND m.message_id=? AND a.topic=? AND a.telegram_id=?""",
                           (chat_id, reply_id, topic, user_id)).fetchone()
        return dict(row) if row else None


def record_attempt(assignment, student, message_id, submission, result, file_id=None):
    with closing(get_connection()) as conn:
        schema(conn)
        with conn:
            conn.execute("""INSERT OR IGNORE INTO book_attempts
                (assignment_id,student_id,telegram_id,chat_id,message_id,submission,file_id,ai_status,feedback,errors_json)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (assignment['id'], student['id'] if student else None,
                assignment['telegram_id'], assignment['chat_id'], message_id, submission[:12000], file_id,
                result['status'], result['feedback'], json.dumps(result['errors'], ensure_ascii=False)))
            row = conn.execute("SELECT * FROM book_attempts WHERE chat_id=? AND message_id=?",
                               (assignment['chat_id'], message_id)).fetchone()
            return dict(row)


def review(attempt_id, actor_id, accepted, note=""):
    if actor_id != ADMIN_ID:
        raise ValueError("Bu amal faqat administrator uchun.")
    with closing(get_connection()) as conn:
        schema(conn)
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""SELECT t.*,a.source_id,a.source_json FROM book_attempts t
                JOIN book_assignments a ON a.id=t.assignment_id WHERE t.id=?""", (attempt_id,)).fetchone()
            if not row:
                raise ValueError("Urinish topilmadi.")
            if row['teacher_status']:
                return "Bu urinish avval ko'rib chiqilgan. Qayta ball berilmadi."
            if row['ai_status'] in ('error', 'not_submission'):
                raise ValueError("Bu urinish baholanmagan yoki yechim emas. O'quvchi yechimini qayta yuborsin.")
            # Identity must still match the approved binding at review time.
            student = conn.execute("SELECT * FROM students WHERE id=? AND telegram_id=? AND active=1",
                                   (row['student_id'], row['telegram_id'])).fetchone()
            if not student:
                raise ValueError("Urinishda ishonchli o'quvchi ID yo'q. Profilni bog'lang va yechimni qayta yubortiring.")
            conn.execute("UPDATE book_attempts SET teacher_status=?,teacher_id=?,teacher_note=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
                         ('accepted' if accepted else 'rejected', actor_id, note[:2000], attempt_id))
            if not accepted:
                return "Qayta ishlash kerak deb belgilandi. Ball qo'shilmadi."
            source = json.loads(row['source_json'])
            if source['kind'] != 'exercise':
                return "Sahifa bo'yicha javob tasdiqlandi. XP faqat raqamli kitob masalasiga beriladi."
            inserted = conn.execute("INSERT OR IGNORE INTO book_rewards VALUES(?,?,?,25)",
                                    (student['id'], row['source_id'], attempt_id)).rowcount
            if not inserted:
                return "Tasdiqlandi. Bu masala uchun oldin ball berilgan; takror qo'shilmadi."
            old = conn.execute("SELECT * FROM student_gamification WHERE student_id=?", (student['id'],)).fetchone()
            xp = (old['xp'] if old else 0) + 25
            level, title = calculate_level_and_title(xp, student['course_name'])
            conn.execute("""INSERT INTO student_gamification(student_id,student_name,xp,level,title,tasks_solved)
                 VALUES(?,?,?,?,?,1) ON CONFLICT(student_id) DO UPDATE SET xp=excluded.xp,level=excluded.level,
                 title=excluded.title,tasks_solved=student_gamification.tasks_solved+1,updated_at=CURRENT_TIMESTAMP""",
                 (student['id'], student['name'], xp, level, title))
            return f"{student['name']}: tasdiqlandi, +25 XP. Jami {xp} XP."


def attempt_detail(attempt_id):
    with closing(get_connection()) as conn:
        schema(conn)
        row = conn.execute("SELECT t.*,a.source_json FROM book_attempts t JOIN book_assignments a ON a.id=t.assignment_id WHERE t.id=?", (attempt_id,)).fetchone()
        if not row:
            return "Urinish topilmadi."
        source = json.loads(row['source_json'])
        return (f"Urinish #{row['id']} · O'quvchi ID: {row['student_id']}\n{source['label']}\n"
                f"Sana (UTC): {row['created_at']} · Xabar: {row['chat_id']}/{row['message_id']}\n"
                f"Shart: {source['text']}\n\nYechim: {row['submission']}\n"
                f"Rasm: {'bor' if row['file_id'] else 'yo‘q'}\n\nAI dastlabki bahosi: {row['ai_status']}\n"
                f"{row['feedback']}\nUstoz: {row['teacher_status'] or 'kutilmoqda'}\n"
                f"/tasdiq {row['id']} yoki /rad {row['id']} sabab")


def report(student_id=None):
    with closing(get_connection()) as conn:
        schema(conn)
        params = (student_id,) if student_id is not None else ()
        where = " WHERE t.student_id=?" if params else ""
        total = conn.execute("SELECT COUNT(*) FROM book_attempts t" + where, params).fetchone()[0]
        rows = conn.execute("""SELECT t.*,a.source_json,s.name FROM book_attempts t
             JOIN book_assignments a ON a.id=t.assignment_id LEFT JOIN students s ON s.id=t.student_id"""
             + where + " ORDER BY t.id DESC LIMIT 15", params).fetchall()
    lines = [f"Kitob bo'yicha dalilli hisobot · O'quvchi ID: {student_id or 'barcha'}",
             f"Jami qayd etilgan urinish: {total}. Quyida oxirgi {len(rows)} tasi.",
             "AI bahosi dastlabki tahlil; o'zlashtirishning yakuniy bahosi emas."]
    if not rows:
        lines.append("Hali baholash dalili yo'q. Oddiy savol-javoblardan o'zlashtirish darajasi chiqarilmadi.")
    for row in rows:
        source = json.loads(row['source_json'])
        lines.append(f"\n#{row['id']} · {row['name'] or 'Profil bog‘lanmagan'} · {source['label']}\n"
                     f"Mavzu: {source['topic']}\nAI: {row['ai_status']}; ustoz: {row['teacher_status'] or 'kutilmoqda'}. "
                     f"Sana (UTC): {row['created_at']}\n"
                     + "Xato dalillari (AI): " + ("; ".join(json.loads(row['errors_json'])) or "qayd etilmagan")[:600]
                     + (f"\nUstoz izohi: {row['teacher_note']}" if row['teacher_note'] else ""))
    lines.append("\nTo'liq shart, yechim va fikr: /urinish ID. Tasdiqlash: /tasdiq ID. Qayta ishlash: /rad ID sabab.")
    return "\n".join(lines)
