"""Local, source-addressable PDF lookup. No guessed exercise statements."""
import hashlib
import re
from pathlib import Path
from functools import lru_cache
from pypdf import PdfReader
from book_service import BOOKS


def parse_request(text):
    text = text.casefold()
    number = re.search(r"(?:(\d{1,3})\s*[-–]?\s*(masala|topshiriq|mashq|challenge|sahifa)|"
                       r"(masala|topshiriq|mashq|challenge|sahifa)\s*(\d{1,3}))", text)
    if not number:
        return None
    keys = [key for key, words in {"python": ("python",), "html": ("html",),
            "office": ("word", "excel", "office")}.items() if any(w in text for w in words)]
    if not keys and "kitob" not in text:
        return None
    kind = number[2] or number[3]
    return {"book": keys[0] if len(keys) == 1 else None,
            "kind": "page" if kind == "sahifa" else "exercise", "number": int(number[1] or number[4])}


def _clean(text, page):
    lines = (text or "").splitlines()
    return "\n".join(line for line in lines if not (
        "BY EXAMPLE  •" in line or "150 AMALIY TOPSHIRIQ" in line
        or line.strip() in {str(page), f"Sahifa {page}"}))


@lru_cache(maxsize=6)
def _index(key, path, size, modified):
    reader = PdfReader(path)
    pages = [_clean(p.extract_text(), i + 1) for i, p in enumerate(reader.pages)]
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    exercises = []
    current = None
    active = False
    topic = ""
    def finish():
        nonlocal current
        if current and current["text"].strip():
            current["text"] = current["text"].strip()
            exercises.append(current)
        current = None
    for page, text in enumerate(pages, 1):
        for line in text.splitlines():
            stripped = line.strip()
            if page > 10 and (stripped == "PART III" or stripped.startswith("JAVOBLAR")):
                finish()
                active = False
                break
            heading = re.match(r"(?:\d{3}-\d{3}:|\d+-MAVZU\.|CHAPTER \d+)", stripped)
            stop = (heading or stripped.startswith(("O‘zingizni tekshiring", "CHAPTER CHECKPOINT",
                    "MINI-LOYIHA", "Keyin nima", "Lug'at", "Indeks")))
            if stop:
                finish()
                active = False
                if heading:
                    topic = stripped
            if stripped in {"Topshiriqlar", "Challenges"}:
                finish()
                active = True
                continue
            capstone = (re.fullmatch(r"CHALLENGE (1[45]\d)", stripped) if key == "html" else
                        re.fullmatch(r"(1[45]\d)-topshiriq:.*", stripped) if key == "python" and page > 10 else None)
            match = capstone or (re.fullmatch(r"(\d{3})(?:\s+(.+))?", stripped) if active else None)
            if capstone:
                active = True
            if match and 1 <= int(match[1]) <= 200:
                finish()
                current = {"book": key, "kind": "exercise", "number": int(match[1]),
                           "page": page, "end_page": page, "topic": topic, "text": (match[2] or "") if not capstone else "",
                           "hash": digest}
            elif current:
                current["text"] += "\n" + line
                current["end_page"] = page
    finish()
    return pages, exercises, digest


def lookup(key, kind, number):
    if key not in BOOKS:
        raise ValueError("Qaysi kitob: Python, HTML yoki Word/Excel? Kitob nomini ham yozing.")
    path, title = BOOKS[key]
    stat = path.stat()
    pages, exercises, digest = _index(key, str(path), stat.st_size, stat.st_mtime_ns)
    if kind == "page":
        if not 1 <= number <= len(pages):
            raise ValueError(f"Bu PDF {len(pages)} sahifa. Mavjud sahifa raqamini yozing.")
        source = {"book": key, "kind": kind, "number": number, "page": number, "end_page": number,
                  "text": pages[number-1], "topic": f"{number}-sahifa", "hash": digest}
        if not source["text"].strip():
            raise ValueError("Bu sahifadan matn o'qilmadi. Sahifani rasm qilib yuboring.")
    else:
        matches = [e for e in exercises if e["number"] == number]
        if not matches:
            raise ValueError("Bu masala raqami bo'yicha aniq shart topilmadi. Kitob sahifasini yozing yoki rasmini yuboring.")
        if len(matches) != 1:
            raise ValueError("Bu raqam bir necha joyda uchradi. Aniq PDF sahifasini yozing: " +
                             ", ".join(str(e["page"]) for e in matches))
        source = dict(matches[0])
    source["title"] = title
    source["label"] = f"{key.upper()} · {number}-{'masala' if kind == 'exercise' else 'sahifa'} · PDF {source['page']}-sahifa"
    source["id"] = f"{key}:{digest}:{kind}:{number}:{source['page']}"
    return source
