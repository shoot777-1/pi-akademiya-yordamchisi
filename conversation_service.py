"""Bounded conversation history, isolated by chat and Telegram user."""
import json
import sqlite3
import time
from contextlib import closing
from config import DB_PATH

MAX_MESSAGES = 12
MAX_CONTENT = 2000
TTL_SECONDS = 24 * 60 * 60


def connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS conversations (
        chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        messages TEXT NOT NULL, updated REAL NOT NULL,
        PRIMARY KEY (chat_id, user_id))""")
    return conn


def get_history(chat_id, user_id):
    with closing(connection()) as conn, conn:
        conn.execute("DELETE FROM conversations WHERE updated < ?", (time.time() - TTL_SECONDS,))
        row = conn.execute("SELECT messages FROM conversations WHERE chat_id=? AND user_id=?",
                           (chat_id, user_id)).fetchone()
        return json.loads(row[0]) if row else []


def remember(chat_id, user_id, question, answer):
    messages = get_history(chat_id, user_id)
    messages.extend([{"role": "user", "content": question[:MAX_CONTENT]},
                     {"role": "assistant", "content": answer[:MAX_CONTENT]}])
    with closing(connection()) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO conversations VALUES (?, ?, ?, ?)",
                     (chat_id, user_id, json.dumps(messages[-MAX_MESSAGES:]), time.time()))


def clear_history(chat_id, user_id):
    with closing(connection()) as conn, conn:
        conn.execute("DELETE FROM conversations WHERE chat_id=? AND user_id=?", (chat_id, user_id))
