"""Local backup, timezone and single-instance utilities."""
import os
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from config import BASE_DIR, DB_PATH


def tashkent_now():
    return datetime.now(timezone(timedelta(hours=5)))


def backup_data():
    folder = BASE_DIR / "backups" / tashkent_now().strftime("%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True)
    if DB_PATH.exists():
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(folder / DB_PATH.name)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
    workbook = BASE_DIR / "dars jadvallari.xlsx"
    if workbook.exists():
        shutil.copy2(workbook, folder / workbook.name)
    return folder


def acquire_instance():
    handle = open(BASE_DIR / ".bot.lock", "a+b")
    try:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("Botning boshqa nusxasi allaqachon ishlayapti") from None
    return handle
