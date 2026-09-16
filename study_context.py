"""Telegram file references and reply chains, scoped to chat and forum topic."""
import sqlite3
import time
import re
from contextlib import closing, contextmanager
from config import DB_PATH

TTL = 24 * 60 * 60


@contextmanager
def database():
    with closing(sqlite3.connect(DB_PATH)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS study_photos (
            chat INTEGER, topic INTEGER, message INTEGER, owner INTEGER,
            file_id TEXT, caption TEXT, created REAL, PRIMARY KEY(chat,topic,message))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS study_links (
            chat INTEGER, topic INTEGER, message INTEGER, photo INTEGER,
            text TEXT, created REAL, PRIMARY KEY(chat,topic,message))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS study_active (
            chat INTEGER, topic INTEGER, owner INTEGER, photo INTEGER,
            created REAL, PRIMARY KEY(chat,topic,owner))""")
        if "owner" not in {r[1] for r in conn.execute("PRAGMA table_info(study_links)")}:
            conn.execute("ALTER TABLE study_links ADD COLUMN owner INTEGER NOT NULL DEFAULT 0")
        for table in ("study_photos", "study_links", "study_active"):
            conn.execute(f"DELETE FROM {table} WHERE created < ?", (time.time() - TTL,))
        yield conn


def coordinates(message):
    return message.chat_id, getattr(message, "message_thread_id", None) or 0


def save_photo(chat, topic, message_id, owner, file_id, caption=""):
    with database() as conn:
        new = not conn.execute("SELECT 1 FROM study_photos WHERE chat=? AND topic=? AND message=?",
                               (chat, topic, message_id)).fetchone()
        conn.execute("INSERT OR IGNORE INTO study_photos VALUES (?,?,?,?,?,?,?)",
                     (chat, topic, message_id, owner, file_id, caption[:2000], time.time()))
        if new:
            conn.execute("DELETE FROM study_active WHERE chat=? AND topic=? AND owner=?", (chat, topic, owner))
        conn.execute("""DELETE FROM study_photos WHERE chat=? AND message NOT IN
            (SELECT message FROM study_photos WHERE chat=? ORDER BY created DESC LIMIT 50)""", (chat, chat))


def link_message(chat, topic, message_id, photo, text="", owner=0):
    if not isinstance(message_id, int):
        return
    with database() as conn:
        conn.execute("INSERT OR REPLACE INTO study_links(chat,topic,message,photo,text,created,owner) VALUES (?,?,?,?,?,?,?)",
                     (chat, topic, message_id, photo, text[:3000], time.time(), owner))
        conn.execute("""DELETE FROM study_links WHERE chat=? AND message NOT IN
            (SELECT message FROM study_links WHERE chat=? ORDER BY created DESC LIMIT 200)""", (chat, chat))


def select_photo(chat, topic, owner, photo):
    with database() as conn:
        conn.execute("INSERT OR REPLACE INTO study_active VALUES (?,?,?,?,?)",
                     (chat, topic, owner, photo, time.time()))


def resolve(chat, topic, owner, reply_id=None):
    """Return (photo, ambiguity_or_missing, quoted_text). Never infer another user's photo."""
    with database() as conn:
        def photo(number):
            row = conn.execute("SELECT * FROM study_photos WHERE chat=? AND topic=? AND message=?",
                               (chat, topic, number)).fetchone()
            return dict(row) if row else None
        def explanation(number):
            row = conn.execute("""SELECT text FROM study_links WHERE chat=? AND topic=? AND owner=? AND photo=?
                ORDER BY created DESC LIMIT 1""", (chat, topic, owner, number)).fetchone()
            return row[0] if row else ""
        if reply_id is not None:
            direct = photo(reply_id)
            if direct:
                return direct, False, ""
            link = conn.execute("SELECT * FROM study_links WHERE chat=? AND topic=? AND message=?",
                                (chat, topic, reply_id)).fetchone()
            if link and link["photo"] is not None:
                found = photo(link["photo"])
                return found, not bool(found), link["text"]
            # Explicit reply to unrelated text must not attach an unrelated recent image.
            return None, False, link["text"] if link else ""
        active = conn.execute("SELECT photo FROM study_active WHERE chat=? AND topic=? AND owner=?",
                              (chat, topic, owner)).fetchone()
        if active:
            selected = photo(active[0])
            if selected:
                return selected, False, explanation(selected["message"])
        rows = conn.execute("SELECT * FROM study_photos WHERE chat=? AND topic=? AND owner=? ORDER BY created DESC LIMIT 2",
                            (chat, topic, owner)).fetchall()
        return (dict(rows[0]), False, explanation(rows[0]["message"])) if len(rows) == 1 else (None, len(rows) > 1, "")


def is_followup(text):
    value = text.casefold()
    return bool(re.search(r"tush[ui]?nmad|chunmad|tushuntir|sodda|batafsil|shu (joy|rasm|masala|misol)|"
                          r"rasmdagi|masalani|misolni|ikkinchi|uchinchi|birinchi|nega|davom|"
                          r"\d+\s*[-–]?\s*(?:\d+\s*)?[-–]?\s*(?:masala|misol|savol)", value))


def clear(chat, owner):
    with database() as conn:
        ids = [r[0] for r in conn.execute("SELECT message FROM study_photos WHERE chat=? AND owner=?", (chat, owner))]
        for message_id in ids:
            conn.execute("DELETE FROM study_links WHERE chat=? AND photo=?", (chat, message_id))
            conn.execute("DELETE FROM study_active WHERE chat=? AND photo=?", (chat, message_id))
        conn.execute("DELETE FROM study_photos WHERE chat=? AND owner=?", (chat, owner))
        conn.execute("DELETE FROM study_active WHERE chat=? AND owner=?", (chat, owner))
