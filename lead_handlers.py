"""
Cyber Tech Academy - Ota-onalar uchun Sinov darsi va IT Moyillik Testi handlerlari.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from config import ADMIN_ID
from lead_service import IT_QUIZ_QUESTIONS, save_lead
from operations import tashkent_now

# Foydalanuvchi qadamlarini saqlash (in-memory chat_data yoki dict)
USER_LEAD_DATA = {}
USER_QUIZ_DATA = {}

START_PARENT_TEXT = """🎓 <b>CYBER TECH ACADEMY — Rasmiy Botiga Xush Kelibsiz!</b>

Bizda o‘quvchilar kompyuter va telefondan shunchaki foydalanmaydi — <b>ular texnologiya yaratishni o‘rganadi!</b>

Biz uchun eng muhim ko‘rsatkich — nechta dars o‘tilgani emas, balki <b>o‘quvchining amaliy natijasi</b>.

👇 <b>Quyidagi kerakli bo‘limni tanlang:</b>"""

GROUP_ID = -1003865779918
GROUP_INVITE_URL = "https://t.me/cyber_tech_academy_gruppamiz"

async def is_user_subscribed(bot, user_id: int) -> bool:
    """Foydalanuvchi CYBER TECH ACADEMY guruhiga a'zoligini tekshirish"""
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        return member.status in ["creator", "administrator", "member", "restricted"]
    except Exception as e:
        logger.warning("Obunani tekshirishda ogohlantirish: %s", e)
        return False

def get_subscription_prompt_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Rasmiy guruhimizga a’zo bo‘lish ➔", url=GROUP_INVITE_URL)],
        [InlineKeyboardButton("✅ A’zo bo‘ldim / Tekshirish", callback_data="lead_check_sub")]
    ])

def get_parent_menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Bepul sinov darsiga yozilish", callback_data="lead_step_age")],
        [InlineKeyboardButton("🧠 Farzandingiz qaysi IT kasbiga moyil? (Test)", callback_data="quiz_p_start")],
        [InlineKeyboardButton("👥 Rasmiy guruhimiz", url=GROUP_INVITE_URL)],
        [InlineKeyboardButton("📸 O‘quvchilar natijalari (Instagram)", url="https://www.instagram.com/salomov_2502/")],
        [InlineKeyboardButton("📞 Administrator bilan bog‘lanish", url="https://t.me/salomov_2502")]
    ])

NOT_SUBSCRIBED_TEXT = (
    "❌ <b>Siz hali guruhimizga a’zo bo‘lmadingiz!</b>\n\n"
    "Botdan foydalanish, bepul sinov darsiga yozilish yoki IT testini topshirish uchun avval <b>rasmiy guruhimizga a’zo bo‘ling:</b>\n\n"
    "👉 1. Pastdagi <b>«👥 Rasmiy guruhimizga a’zo bo‘lish ➔»</b> tugmasini bosing;\n"
    "👉 2. Guruhga qo‘shilgach, <b>«✅ A’zo bo‘ldim / Tekshirish»</b> tugmasini bosing."
)

async def handle_parent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ota-onalar va yangi foydalanuvchilar uchun /start oynasi"""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    # Guruhga a'zolikni qat'iy tekshirish - a'zo bo'lmaganlarga so'rovnoma UMUMAN chiqmaydi!
    subscribed = await is_user_subscribed(context.bot, user.id)
    if not subscribed:
        await chat.send_message(NOT_SUBSCRIBED_TEXT, parse_mode="HTML", reply_markup=get_subscription_prompt_markup())
        return

    # Faqat guruh a'zolariga so'rovnoma va asosiy menyu ochiladi:
    text = START_PARENT_TEXT
    await chat.send_message(text, parse_mode="HTML", reply_markup=get_parent_menu_markup())

async def lead_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Sinov darsiga yozilish va IT test inline callbacklarini qayta ishlash"""
    query = update.callback_query
    if not query or not query.data:
        return False
    data = query.data
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return False

    # --- 0. OBUNA TEKSHIRISH ---
    if data in ("check_sub", "lead_check_sub"):
        subscribed = await is_user_subscribed(context.bot, user.id)
        if subscribed:
            await query.answer("🎉 Rahmat! A’zoligingiz muvaffaqiyatli tasdiqlandi.", show_alert=False)
            try:
                await query.edit_message_text(START_PARENT_TEXT, parse_mode="HTML", reply_markup=get_parent_menu_markup())
            except Exception:
                pass
        else:
            await query.answer("❌ Siz hali guruhimizga a’zo bo‘lmadingiz! Avval guruhga a’zo bo‘ling.", show_alert=True)
            try:
                await query.edit_message_text(NOT_SUBSCRIBED_TEXT, parse_mode="HTML", reply_markup=get_subscription_prompt_markup())
            except Exception:
                pass
        return True

    # Guruhga a'zo bo'lmagan foydalanuvchi biror so'rovnoma tugmasini bossa, uni ham to'xtatamiz!
    subscribed = await is_user_subscribed(context.bot, user.id)
    if not subscribed:
        await query.answer("❌ Siz hali guruhimizga a’zo bo‘lmadingiz! Avval a’zo bo‘ling.", show_alert=True)
        try:
            await query.edit_message_text(NOT_SUBSCRIBED_TEXT, parse_mode="HTML", reply_markup=get_subscription_prompt_markup())
        except Exception:
            pass
        return True

    # --- 1. SINOV DARSIGA YOZILISH OQIMI ---
    if data == "lead_step_age" or data == "lead_restart":
        USER_LEAD_DATA[user.id] = {"full_name": user.full_name, "username": user.username}
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("👦 7 – 10 yosh", callback_data="lead_age_7_10")],
            [InlineKeyboardButton("🧑 11 – 14 yosh", callback_data="lead_age_11_14")],
            [InlineKeyboardButton("👨 15 – 18 yosh", callback_data="lead_age_15_18")],
            [InlineKeyboardButton("⬅️ Ortga", callback_data="lead_back_home")]
        ])
        await query.edit_message_text(
            "👶 <b>1-Qadam:</b> Farzandingizning yosh toifasini tanlang:",
            parse_mode="HTML",
            reply_markup=markup
        )
        return True

    elif data.startswith("lead_age_"):
        age_map = {
            "lead_age_7_10": "7-10 yosh",
            "lead_age_11_14": "11-14 yosh",
            "lead_age_15_18": "15-18 yosh"
        }
        USER_LEAD_DATA.setdefault(user.id, {})["age"] = age_map.get(data, "11-14 yosh")

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🐍 Python va Sun’iy intellekt (AI)", callback_data="lead_c_python")],
            [InlineKeyboardButton("🤖 Robototexnika / Arduino", callback_data="lead_c_robot")],
            [InlineKeyboardButton("🌐 Web & Android dasturlash", callback_data="lead_c_web")],
            [InlineKeyboardButton("🎨 Grafik dizayn & Video montaj", callback_data="lead_c_design")],
            [InlineKeyboardButton("💻 Kompyuter savodxonligi & Office", callback_data="lead_c_basic")],
            [InlineKeyboardButton("🤷‍♂️ Hali aniq emas (Maslahat kerak)", callback_data="lead_c_consult")],
            [InlineKeyboardButton("⬅️ Ortga", callback_data="lead_step_age")]
        ])
        await query.edit_message_text(
            "🚀 <b>2-Qadam:</b> Farzandingiz ko‘proq qaysi yo‘nalishga qiziqadi?",
            parse_mode="HTML",
            reply_markup=markup
        )
        return True

    elif data.startswith("lead_c_"):
        course_map = {
            "lead_c_python": "Python & AI",
            "lead_c_robot": "Robototexnika / Arduino",
            "lead_c_web": "Web & Android",
            "lead_c_design": "Grafik dizayn & Video",
            "lead_c_basic": "Kompyuter savodxonligi",
            "lead_c_consult": "Maslahatlashib tanlaymiz"
        }
        USER_LEAD_DATA.setdefault(user.id, {})["course"] = course_map.get(data, "Dasturlash")
        USER_LEAD_DATA[user.id]["waiting_phone"] = True

        reply_btn = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Telefon raqamimni yuborish", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await query.message.delete()
        await chat.send_message(
            "📞 <b>3-Qadam:</b> Siz bilan bog‘lanib, sinov darsi vaqtini belgilashimiz uchun <b>telefon raqamingizni yuboring:</b>\n\n"
            "<i>Pastdagi '📱 Telefon raqamimni yuborish' tugmasini bosing yoki qo‘lda yozing (Masalan: +998901234567):</i>",
            parse_mode="HTML",
            reply_markup=reply_btn
        )
        return True

    elif data == "lead_back_home":
        await query.edit_message_text(START_PARENT_TEXT, parse_mode="HTML", reply_markup=get_parent_menu_markup())
        return True

    # --- 2. IT MOYILLIK TESTI (QUIZ) OQIMI ---
    elif data == "quiz_p_start":
        USER_QUIZ_DATA[user.id] = {"step": 0, "scores": {"python": 0, "robot": 0, "design": 0, "basic": 0}}
        await send_quiz_question(query, user.id, 0)
        return True

    elif data.startswith("qp_ans_"):
        # Misol: qp_ans_0_python
        parts = data.split("_")
        q_idx = int(parts[2])
        ans_cat = parts[3]

        u_quiz = USER_QUIZ_DATA.get(user.id)
        if not u_quiz:
            USER_QUIZ_DATA[user.id] = {"step": 0, "scores": {"python": 0, "robot": 0, "design": 0, "basic": 0}}
            u_quiz = USER_QUIZ_DATA[user.id]

        u_quiz["scores"][ans_cat] = u_quiz["scores"].get(ans_cat, 0) + 1
        next_step = q_idx + 1

        if next_step < len(IT_QUIZ_QUESTIONS):
            u_quiz["step"] = next_step
            await send_quiz_question(query, user.id, next_step)
        else:
            # Test natijasi
            await show_quiz_result(query, context, user.id, u_quiz["scores"])
        return True

    return False

async def send_quiz_question(query, user_id, q_idx):
    q_data = IT_QUIZ_QUESTIONS[q_idx]
    buttons = []
    for opt_text, opt_cat in q_data["options"]:
        buttons.append([InlineKeyboardButton(opt_text, callback_data=f"qp_ans_{q_idx}_{opt_cat}")])
    buttons.append([InlineKeyboardButton("❌ Testni to‘xtatish", callback_data="lead_back_home")])

    text = f"<b>{q_data['question']}</b>\n\n<i>Savol {q_idx+1} / {len(IT_QUIZ_QUESTIONS)}:</i>"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def show_quiz_result(query, context, user_id, scores):
    # Eng yuqori ball to'plagan yo'nalish
    best_cat = max(scores, key=scores.get)

    result_details = {
        "python": {
            "title": "🐍 Python Dasturlash va Sun’iy Intellekt (AI)",
            "desc": "Farzandingizda kuchli mantiqiy tafakkur, jumboqlarni tahlil qilish va algoritmik fikrlash qobiliyati bor! U kompyuter o‘yinlarini shunchaki o‘ynamasdan, o‘z dasturlarini va aqlli botlarini yaratishga 100% tayyor.",
            "fit": "94%"
        },
        "robot": {
            "title": "🤖 Robototexnika va Arduino Muhandisligi",
            "desc": "Farzandingizda ixtirochilik va texnikaga qiziqish juda kuchli! U o‘z qo‘llari bilan sxemalar yig‘ish, datchiklar bilan ishlash va aqlli robotlarni dasturlashda ajoyib natijalarga erishadi.",
            "fit": "91%"
        },
        "design": {
            "title": "🎨 Grafik Dizayn va Video Montaj",
            "desc": "Farzandingizda ijodkorlik va vizual did yuqori darajada rivojlangan! Photoshop, Illustrator va Premiere Pro orqali u o‘z tasavvuridagi g‘oyalarni professional darajadagi mediaga aylantira oladi.",
            "fit": "89%"
        },
        "basic": {
            "title": "💻 Zamonaviy Kompyuter Savodxonligi & Ofis Dasturlari",
            "desc": "Farzandingizga hozir kompyuterdan professional foydalanish, tez terish, Word, Excel va internet xavfsizligi asoslarini puxta o‘rganish eng to‘g‘ri poydevor bo‘ladi!",
            "fit": "88%"
        }
    }

    res = result_details.get(best_cat, result_details["python"])
    USER_LEAD_DATA.setdefault(user_id, {})["quiz_result"] = res["title"]

    text = (
        f"🏆 <b>TEST NATIJALARI TAYYOR!</b>\n\n"
        f"🎯 <b>Tavsiya etiladigan yo‘nalish:</b>\n"
        f"👉 <b>{res['title']}</b> (Moslik: <b>{res['fit']}</b>)\n\n"
        f"💡 <i>{res['desc']}</i>\n\n"
        f"🎁 <b>Ajoyib yangilik:</b> Ushbu yo‘nalish bo‘yicha farzandingizga <b>BEPUL SINOV DARSI</b> imkoniyatini taqdim etamiz!\n\n"
        f"Farzandingiz kelajagini birinchi qadamdan to‘g‘ri boshlang:"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Bepul sinov darsiga yozilish", callback_data=f"lead_c_{best_cat}")],
        [InlineKeyboardButton("📸 O‘quvchilar loyihalari (Instagram)", url="https://www.instagram.com/salomov_2502/")],
        [InlineKeyboardButton("🏠 Bosh sahifaga qaytish", callback_data="lead_back_home")]
    ])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

import html
import logging
logger = logging.getLogger(__name__)

def parse_clean_phone(text_or_contact) -> str:
    """Har qanday formatdagi O'zbekiston raqamini toza +998XXXXXXXXX formatga o'tkazish"""
    import re
    if not text_or_contact:
        return ""
    digits = "".join(re.findall(r"\d", str(text_or_contact)))
    if len(digits) == 9:  # Masalan: 933100764 -> +998933100764
        return f"+998{digits}"
    elif len(digits) == 12 and digits.startswith("998"):
        return f"+{digits}"
    elif len(digits) >= 7:
        return f"+{digits}" if not str(text_or_contact).startswith("+") else str(text_or_contact)
    return ""

async def send_lead_notifications(bot, lead_id, user_id, full_name, username, phone, age, course, quiz_result=""):
    """Adminga va Guruhga yangi ariza kelgani haqida kafolatlangan xabarnoma yuborish"""
    user_tag = f"@{username}" if username else "mavjud emas"
    safe_name = html.escape(str(full_name or "Mijoz"))
    now_str = tashkent_now().strftime('%Y-%m-%d %H:%M')
    
    notify_msg = (
        f"🚨 <b>YANGI SINOV DARSI ARIZASI! (№{lead_id})</b>\n\n"
        f"👤 <b>Murojaatchi:</b> {safe_name} ({user_tag})\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"📞 <b>Telefon raqam:</b> <code>{phone}</code>\n"
        f"👶 <b>Farzand yoshi:</b> {html.escape(str(age))}\n"
        f"🚀 <b>Tanlangan yo‘nalish:</b> {html.escape(str(course))}\n"
    )
    if quiz_result:
        notify_msg += f"🧠 <b>Test natijasi:</b> {html.escape(str(quiz_result))}\n"
    notify_msg += (
        f"⏰ <b>Vaqti:</b> {now_str}\n\n"
        f"👉 <b>Darhol bog‘lanish:</b> <code>{phone}</code>"
    )

    # Adminga murojaatchi bilan darhol bog'lanish tugmasi
    admin_buttons = []
    if username:
        admin_buttons.append([InlineKeyboardButton("💬 Telegramdan yozish", url=f"https://t.me/{username}")])
    elif user_id:
        admin_buttons.append([InlineKeyboardButton("💬 Profilni ochish", url=f"tg://user?id={user_id}")])

    admin_markup = InlineKeyboardMarkup(admin_buttons) if admin_buttons else None

    # Yuboriladigan admin chatlari (har doim 658069248 va agar boshqa bo'lsa ADMIN_ID)
    admin_targets = {658069248}
    if ADMIN_ID:
        admin_targets.add(int(ADMIN_ID))

    # 1. Barcha adminlarning shaxsiy chatiga yetkazish
    for a_id in admin_targets:
        try:
            await bot.send_message(
                chat_id=a_id,
                text=notify_msg,
                parse_mode="HTML",
                reply_markup=admin_markup
            )
            logger.info("Admin %s ga ariza bildirishnomasi yetkazildi", a_id)
        except Exception as e:
            logger.error("Admin %s ga xabarnoma yuborishda xato: %s", a_id, e)

    # 2. Rasmiy guruhga yetkazish (-1003865779918)
    try:
        await bot.send_message(
            chat_id=GROUP_ID,
            text=notify_msg,
            parse_mode="HTML"
        )
        logger.info("Guruh %s ga ariza bildirishnomasi yetkazildi", GROUP_ID)
    except Exception as e:
        logger.error("Guruh %s ga xabarnoma yuborishda xato: %s", GROUP_ID, e)

async def handle_contact_or_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Telefon raqam yoki kontakt yuborilganda arizani qabul qilish"""
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user:
        return False

    phone = ""
    if message.contact:
        phone = parse_clean_phone(message.contact.phone_number)
    elif message.text:
        text = message.text.strip()
        import re
        digits = "".join(re.findall(r"\d", text))
        is_waiting = USER_LEAD_DATA.get(user.id, {}).get("waiting_phone", False)
        
        # 7 tadan 15 tagacha raqam bo'lsa yoki kutayotgan holatda kiritilsa
        if len(digits) >= 7:
            phone = parse_clean_phone(digits)
        elif is_waiting:
            phone = parse_clean_phone(text)

    if not phone:
        return False

    lead_info = USER_LEAD_DATA.get(user.id, {})
    age = lead_info.get("age", "Belgilanmagan")
    course = lead_info.get("course", "Sinov darsi / Konsultatsiya")
    q_res = lead_info.get("quiz_result", "")

    lead_id = 1
    try:
        lead_id = save_lead(
            telegram_id=user.id,
            full_name=user.full_name or "Foydalanuvchi",
            username=user.username or "",
            child_age=age,
            chosen_course=course,
            phone_number=phone,
            quiz_result=q_res
        )
    except Exception as e:
        logger.error("Bazaga saqlashda xatolik: %s", e)

    if user.id in USER_LEAD_DATA:
        USER_LEAD_DATA[user.id]["waiting_phone"] = False

    safe_first_name = html.escape(user.first_name or "Hurmatli mijoz")

    # 1. Foydalanuvchiga tasdiqlash xabari
    thanks_text = (
        f"🎉 <b>ARIZANGIZ QABUL QILINDI! (№{lead_id})</b>\n\n"
        f"Rahmat, <b>{safe_first_name}</b>! Mutaxassisimiz tez orada <code>{phone}</code> raqami orqali siz bilan bog‘lanadi "
        f"va sinov darsi vaqtini qulay qilib belgilaydi.\n\n"
        f"📌 <b>Tanlangan yo‘nalish:</b> {course}\n"
        f"👶 <b>Farzand yoshi:</b> {age}\n"
        f"📞 <b>Aloqa uchun:</b> +998 93 310 07 64\n\n"
        f"📸 Ungacha o‘quvchilarimizning natijalarini "
        f"Instagramda ko‘rishingiz mumkin: <a href='https://www.instagram.com/salomov_2502/'>@salomov_2502</a>"
    )
    try:
        await message.reply_text(thanks_text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        logger.error("Foydalanuvchiga tasdiq xabar yuborishda xato: %s", e)
        await message.reply_text(f"✅ Arizangiz qabul qilindi! Telefon: {phone}\nTez orada bog'lanamiz.", reply_markup=ReplyKeyboardRemove())

    # 2. Adminga va Guruhga kafolatlangan xabarnoma jo'natish
    await send_lead_notifications(
        bot=context.bot,
        lead_id=lead_id,
        user_id=user.id,
        full_name=user.full_name or "Mijoz",
        username=user.username or "",
        phone=phone,
        age=age,
        course=course,
        quiz_result=q_res
    )

    return True
