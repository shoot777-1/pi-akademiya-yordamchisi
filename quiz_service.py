import base64
import json
import logging
import re
from typing import Optional, Dict, Any, List
from ai_service import client, record_usage, ai_error_message
from config import OPENAI_MODEL

logger = logging.getLogger(__name__)

QUIZ_SYSTEM_PROMPT = """Siz "Cyber Tech Academy" IT akademiyasining test va viktorina tuzuvchi katta metodist-o'qituvchisisiz.
Vazifangiz: Berilgan mavzu, matn yoki rasmdagi ma'lumotlar asosida o'quvchilar uchun Telegram viktorinasi (Quiz Poll) formatida AYNAN 10 TA sifatli, mantiqiy va qiziqarli test savollarini tuzish.

TALABLAR:
1. 🌐 TIL VA TARJIMA:
   - Agar matn yoki rasm ingliz yoki rus tilida bo'lsa, uni tushunib, savollar va javoblarni ravon, aniq O'zBEK TILIGA tarjima qilib bering!
   - Dasturlash (Python) kalit so'zlari (print, def, for, while, list, dict va hk.) inglizcha qoldiriladi.
   - Excel formulalari (ВПР, ЕСЛИ, СУММ va hk.) rus tilida qoldiriladi.

2. 📋 TELEGRAM QUIZ POLL CHEKLOVLARI:
   - Har bir savol: qisqa, aniq va tushunarli bo'lsin (eng ko'pi bilan 250 ta belgi).
   - Variantlar soni: HAR BIR SAVOLDA AYNAN 4 TA VARIANT (options) bo'lishi SHART!
   - Har bir variant matni: qisqa bo'lsin (eng ko'pi bilan 95 ta belgi).
   - correct_option_id: to'g'ri variantning 0 dan 3 gacha bo'lgan indeksi (0, 1, 2 yoki 3). To'g'ri javoblar doimo bitta variantda qolib ketmasin, tasodifiy taqsimlansin!
   - explanation: o'quvchi to'g'ri yoki xato belgilaganida chiqadigan qisqa izoh (eng ko'pi bilan 190 ta belgi).
   - Jami savollar soni: AYNAN 10 TA bo'lishi SHART!

3. 📤 JAVOB FORMATI:
   Faqat va faqat quyidagi JSON formatida javob qaytaring (hech qanday qo'shimcha so'zsiz):
{
  "topic": "Mavzu nomi (qisqa)",
  "questions": [
    {
      "question": "1-savol matni?",
      "options": ["A varianti", "B varianti", "C varianti", "D varianti"],
      "correct_option_id": 0,
      "explanation": "Nima uchun ushbu javob to'g'riligi haqida qisqa izoh."
    }
  ]
}
"""

async def generate_quiz_from_ai(text: Optional[str] = None, image_bytes: Optional[bytes] = None, caption_hint: str = "") -> Dict[str, Any]:
    """
    OpenAI yordamida matn yoki rasm asosida 10 talik test generatsiya qilish.
    """
    user_prompt = "Iltimos, ushbu mavzu/kontent bo'yicha Telegram uchun aynan 10 talik test (Quiz Poll) tuzib bering."
    if caption_hint:
        user_prompt += f"\nUstoz ko'rsatmasi: {caption_hint}"
    if text:
        user_prompt += f"\nMavzu yoki matn:\n{text[:8000]}"

    messages = [{"role": "system", "content": QUIZ_SYSTEM_PROMPT}]

    if image_bytes:
        b64_img = base64.b64encode(image_bytes).decode("ascii")
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}", "detail": "high"}}
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_prompt})

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        record_usage(response)
        content = (response.choices[0].message.content or "").strip()
        data = json.loads(content)

        # Validatsiya va tozalash
        topic = data.get("topic") or "Maxsus mavzulashtirilgan test"
        raw_questions = data.get("questions") or []
        
        valid_questions = []
        for q in raw_questions:
            q_text = str(q.get("question", "")).strip()
            opts = q.get("options") or []
            corr = q.get("correct_option_id", 0)
            expl = str(q.get("explanation", "")).strip()

            if not q_text or len(opts) < 2:
                continue

            # Telegram Poll cheklovlarini qat'iy ta'minlash:
            # 1. Savol uzunligi <= 250
            if len(q_text) > 250:
                q_text = q_text[:247] + "..."

            # 2. Variantlar soni aynan 4 ta bo'lishini ta'minlash
            clean_opts = [str(o).strip()[:95] for o in opts[:4]]
            while len(clean_opts) < 4:
                clean_opts.append(f"Qo'shimcha variant {len(clean_opts)+1}")

            # 3. To'g'ri variant indeksi
            if not isinstance(corr, int) or corr < 0 or corr >= len(clean_opts):
                corr = 0

            # 4. Izoh uzunligi <= 190
            if len(expl) > 190:
                expl = expl[:187] + "..."

            valid_questions.append({
                "question": q_text,
                "options": clean_opts,
                "correct_option_id": corr,
                "explanation": expl
            })

        if not valid_questions:
            raise ValueError("AI test savollarini shakllantira olmadi.")

        return {
            "success": True,
            "topic": topic,
            "questions": valid_questions[:10]
        }

    except Exception as e:
        logger.error("Quiz generatsiyasida xatolik: %s", e, exc_info=True)
        return {
            "success": False,
            "error": ai_error_message(e),
            "topic": "",
            "questions": []
        }
