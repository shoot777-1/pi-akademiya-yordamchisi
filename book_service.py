"""Send the academy's supplied PDFs in response to ordinary book requests."""
import logging
import re
from config import BASE_DIR
from telegram.error import TelegramError

logger = logging.getLogger(__name__)
BOOKS = {
    "office": (BASE_DIR / "books" / "Word_Excel_Rus_Interfeys.pdf",
               "Microsoft Word va Excel — rus interfeysi bo'yicha darslik"),
    "html": (BASE_DIR / "books" / "HTML_By_Example_UZ.pdf",
             "HTML by Example — o'zbekcha darslik"),
    "python": (BASE_DIR / "books" / "Python_By_Example_UZ.pdf",
                "Python by Example — o'zbekcha darslik"),
}


def requested_books(text):
    normalized = text.casefold().replace("’", "'").replace("‘", "'").replace("ʻ", "'")
    words = re.findall(r"[\w']+", normalized)
    if not any(word in {"kitob", "kitobni", "kitoblar", "kitoblarni", "kitobi", "kitobini", "kitoblari"} for word in words):
        return []
    allowed = {
        "kitob", "kitobni", "kitoblar", "kitoblarni", "kitobi", "kitobini", "kitoblari",
        "html", "python", "py", "word", "excel", "microsoft", "office", "va", "pi", "pdf",
        "salom", "iltimos", "menga", "bizga", "shu", "ikkala", "hamma", "barcha",
        "kerak", "bormi", "ber", "bering", "bersangiz", "berasanmi", "berasizmi",
        "yubor", "yuboring", "yuborib", "tashla", "tashlang", "tashlab", "yuklab",
    }
    if any(word not in allowed for word in words):
        return []
    selected = []
    if any(word in words for word in ("word", "excel", "microsoft", "office")):
        selected.append("office")
    if "html" in words:
        selected.append("html")
    if "python" in words or "py" in words:
        selected.append("python")
    return selected or list(BOOKS)


async def send_requested_books(message):
    selected = requested_books(message.text)
    if not selected:
        return False
    for key in selected:
        path, title = BOOKS[key]
        try:
            with path.open("rb") as document:
                await message.reply_document(document=document, filename=path.name,
                                             caption=title, do_quote=True)
        except (OSError, TelegramError) as error:
            logger.warning("Kitob yuborilmadi (%s): %s", key, type(error).__name__)
            await message.reply_text(f"{title}: faylni yuborib bo'lmadi. Iltimos, keyinroq qayta so'rang.")
    return True
