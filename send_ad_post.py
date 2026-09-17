"""Cyber Tech Academy - Yangilangan reklama posti (yo'nalishlar va Instagram natijalari bilan)."""
import json
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SECRETS_FILE = BASE_DIR / "secrets.local.json"
POSTER_PATH = BASE_DIR / "cybertech_ad_post_1080x1350.jpg"

with open(SECRETS_FILE, encoding="utf-8") as f:
    secrets = json.load(f)

BOT_TOKEN = secrets.get("BOT_TOKEN")
TARGET_CHAT_ID = -1003865779918  # CYBER TECH ACADEMY guruhi
ADMIN_ID = 658069248

BOT_START_URL = "https://t.me/pi_yordamchi_bot?start=sinov_darsi"
INSTAGRAM_URL = "https://www.instagram.com/salomov_2502/"

CAPTION_TEXT = """💻 <b>FARZANDINGIZ TELEFONDA FAQAT O‘YNAMASIN — UNI YARATISHNI O‘RGANSIN.</b>

Farzandingiz telefon yoki kompyuter qarshisida ko‘p vaqt o‘tkazadimi?
Uni texnologiyadan uzoqlashtirish yechim emas — eng to‘g‘ri yo‘l undan unumli foydalanishni o‘rgatishdir!

<b>CYBER TECH ACADEMY</b>’da o‘quvchilar nazariya bilan cheklanmay, dasturlash va texnologiyalarni amalda o‘rganib, mustaqil loyihalar yaratadilar.

🚀 <b>O‘QUV MARKAZIMIZ YO‘NALISHLARI:</b>
🔹 🐍 Python dasturlash
🔹 🤖 Sun’iy intellekt (AI)
🔹 🌐 Web dasturlash
🔹 📱 Android mobil dasturlash
🔹 🔐 Kiberxavfsizlik
🔹 🤖 Robototexnika / Arduino
🔹 🎨 Grafik dizayn / Photoshop
🔹 🎬 Video montaj / Premiere Pro
🔹 📊 Microsoft Office
🔹 💻 Kompyuter savodxonligi

🏆 <b>Bizda o‘qish emas — NATIJA gapiradi!</b>
O‘quvchilarimizning amaliy ishlari, yaratgan loyihalari va natijalarini o‘z ko‘zingiz bilan ko‘ring:
📸 <b>Instagram:</b> <a href="https://www.instagram.com/salomov_2502/">@salomov_2502</a>

🎁 <b>BEPUL SINOV DARSIGA YOZILING!</b>
<i>Farzandingizga qaysi IT yo‘nalishi eng mos kelishini birgalikda aniqlaymiz.</i>

👇 Quyidagi tugmalar orqali qulay tarzda bog‘laning:"""

def send_ad_to(chat_id):
    if not BOT_TOKEN:
        print("Xato: BOT_TOKEN topilmadi")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "🎯 BEPUL SINOV DARSIGA YOZILISH 🚀",
                    "url": BOT_START_URL
                }
            ],
            [
                {
                    "text": "🧠 FARZANDINGIZGA QAYSI IT KASBI MOS? (TEST) 💡",
                    "url": "https://t.me/pi_yordamchi_bot?start=it_test"
                }
            ],
            [
                {
                    "text": "📸 NATIJALARNI KO‘RISH (INSTAGRAM) 🔥",
                    "url": INSTAGRAM_URL
                }
            ]
        ]
    }

    boundary = "----WebKitFormBoundaryCyberTechAdV3"
    body = bytearray()

    def add_field(name, value):
        nonlocal body
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))

    add_field("chat_id", str(chat_id))
    add_field("caption", CAPTION_TEXT)
    add_field("parse_mode", "HTML")
    add_field("reply_markup", json.dumps(reply_markup))

    if POSTER_PATH.exists():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="photo"; filename="{POSTER_PATH.name}"\r\n'.encode("utf-8"))
        body.extend(b"Content-Type: image/jpeg\r\n\r\n")
        body.extend(POSTER_PATH.read_bytes())
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode())
            if res.get("ok"):
                print(f"Chat {chat_id} ga yuborildi! Message ID: {res['result']['message_id']}")
                return True
            else:
                print(f"Xato ({chat_id}):", res)
                return False
    except Exception as e:
        print(f"Aloqa xatosi ({chat_id}):", e)
        return False

def main():
    print("Post yuborilmoqda...")
    # 1. Guruhga yuborish
    send_ad_to(TARGET_CHAT_ID)
    # 2. Adminga yuborish
    send_ad_to(ADMIN_ID)

if __name__ == "__main__":
    main()
