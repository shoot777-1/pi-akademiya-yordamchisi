# Pi Akademiya yordamchisi

## Ishga tushirish

1. Oldingi bot oynasida `Ctrl+C` bosing. Eski nusxa to'xtagan bo'lishi kerak.
2. `run.bat` faylini oching.
3. Telegram'da botga shaxsiy xabar yuboring: `Salom`.

Bot shu kompyuterda ishlaydi. Kompyuter o'chsa yoki uyqu rejimiga o'tsa, bot ham javob bermaydi.
`run.bat` xato bilan to'xtagan jarayonni 10 soniyadan keyin qayta ishga tushiradi;
odatiy yopish yoki `Ctrl+C` bilan to'xtatishda qayta boshlamaydi.
Yangi nusxalar orasida bir vaqtda ikkita bot ishlashiga to'siq qo'yilgan.
Avvalgi, bu to'siqsiz versiyani bir marta qo'lda to'xtatish zarur.

## Sozlamalar

Token va API kaliti `secrets.local.json` ichida saqlanadi. Bu faylni tarqatmang.
Kod ichidagi mavjud kalitlar shu faylga ko'chirildi; ularni qayta kiritish shart emas.
Kerak bo'lsa `PI_BOT_TOKEN` va `PI_OPENAI_API_KEY` muhit qiymatlari orqali almashtirish mumkin.
Umumiy `OPENAI_API_KEY` boshqa dastur kaliti bilan aralashmasligi uchun ishlatilmaydi.
Administrator ID `config.py` yoki `ADMIN_ID` muhit qiymati orqali belgilanadi.

## Buyruqlar — faqat administrator uchun

| Buyruq | Vazifasi |
|---|---|
| `/start` | Bot haqida ma'lumot |
| `/id` | Telegram ID |
| `/bugun` / `/ertaga` | Dars jadvali |
| `/bugun Python` | Kurs nomi bo'yicha jadvalni filtrlash |
| `/yangi_suhbat` | Shu chatdagi shaxsiy suhbat tarixini tozalash |
| `/daraja boshlangich` | Sodda tushuntirish |
| `/daraja orta` | O'rta darajadagi tushuntirish |

Oxirgi 6 savol-javob chat va foydalanuvchi bo'yicha alohida saqlanadi.
24 soat ishlatilmagan tarix keyingi xotira so'rovida o'chiriladi.
Har bir saqlangan xabarning dastlabki 2000 belgisi eslab qolinadi.
Rasm faylining Telegram file_id manzili saqlanadi; keyingi bog'liq savolda rasm qayta yuklanib AI'ga beriladi.
Bir foydalanuvchi uchun bir daqiqada 6 ta AI so'roviga ruxsat beriladi.
Juda uzun javoblar Telegram chegarasiga mos qismlarda yuboriladi.

Oddiy foydalanuvchilarga slash-buyruqlar ruxsat etilmaydi va buyruq menyusi berilmaydi.
Ular savollarini oddiy matn yoki rasm orqali yuboradi. Admin /help ro'yxatini shaxsiy chatda ko'radi.

## Yangi a'zolar va oddiy matn bilan to'lov

Guruhga qo'shilgan yoki bot ko'radigan xabar yozgan odamning Telegram ID, profil ismi,
username va ko'rilgan vaqti saqlanadi. Bot akkauntlari saqlanmaydi.
Kurs, telefon va to'lov kuni Telegram profilidan avtomatik olinmaydi.
Bot ishlamagan paytdagi eski a'zolarni to'liq ro'yxatlash amalga oshirilmaydi;
ular keyingi xabarida qayd etiladi.

Adminning shaxsiy chatida:

- `/azolar` — Telegram profillari va bog'langan o'quvchi IDlari.
- `/oquvchi 123456 | Ali Valiyev | Python | 15` — yangi o'quvchi kartasi yaratish.
- `/boglash 123456 12` — Telegram IDni mavjud o'quvchi ID 12 bilan bog'lash.

Ismlar tengligi asosida Telegram profili avtomatik birlashtirilmaydi.
Kurs/to'lov kuni kiritilmagan a'zoga moliyaviy majburiyat yaratilmaydi.

Admin oddiy yozishi mumkin:

- `Ali Valiyev to'ladi` — joriy oy uchun to'langan.
- `Ali Valiyev to'lamadi` — joriy oy belgisini bekor qilish.
- `Ali Valiyev to'ladi 2026-09` — aniq oy uchun belgilash.
- `ID 12 to'ladi` — o'quvchi ID bo'yicha belgilash.
- O'quvchining xabariga reply qilib `to'ladi` — bog'langan Telegram ID bo'yicha.

Ism bir nechta o'quvchiga mos kelsa hech narsa o'zgarmaydi, ID so'raladi.
Noto'g'ri oy va savol shaklidagi `Ali to'ladimi?` to'lovni belgilamaydi.
To'lov tarixida admin ID, xabar ID, oy va amalga oshirilgan vaqt saqlanadi.
Hozircha pul miqdori emas, oyning to'langan/to'lanmagan holati yuritiladi.

## Guruhda javob berish

- `Pi`, bot username'iga mention yoki bot xabariga reply bo'lsa javob beradi.
- Admin onlayn bo'lsa boshqa suhbatlarga aralashmaydi.
- Admin oflayn bo'lsa savol/yordam belgisi bor matnlarni AI tekshiradi.
- Ustozga qaratilgan xabarlar va oddiy replikalar chetlab o'tiladi.
- Izohsiz rasmlar admin oflayn bo'lganda tahlil qilinadi.
- Shaxsiy chatdagi javoblar admin holatiga bog'liq emas.

Matnni aniqlash qoidalari taxminiy: o'tkazib yuborilgan savolda `Pi` deb murojaat qiling.

## Administrator buyruqlari

| Buyruq | Vazifasi |
|---|---|
| `/set_group` | Shu guruhni eslatmalar uchun belgilash |
| `/online`, `/offline`, `/auto` | Guruhdagi AI javob rejimi |
| `/status` | Hozirgi rejim |
| `/excel_yangilash` | Mahalliy Excel'ni tekshirib qayta import qilish |
| Excel `.xlsx` yuborish | Jadvalni yangilash; 10 MB gacha |
| `/test_eslatma` | Ma'lumotlarni tekshirish; guruh sozlamasini o'zgartirmaydi |
| `/tolovlar` | ID va joriy oy to'lov holatlari; faqat shaxsiy chatda |
| `/tolandi 12 2026-09` | ID 12 uchun sentabr to'lovini belgilash |
| `/tolanmadi 12 2026-09` | Shu belgilashni bekor qilish |
| `/darslar 2026-09-15` | Sana bo'yicha dars IDlarini ko'rish |
| `/dars_bekor 123` | ID 123 darsni bekor qilish |
| `/dars_kochirish 123 2026-09-16 14:00` | Dars sana/vaqtini o'zgartirish |
| `/diagnostika` | Model, token sarfi, oxirgi AI xatosi va import holati |

To'lov oyini yozmasangiz joriy oy olinadi. To'lov va darslarni boshqarish shaxsiy chatda amalga oshiriladi.
`/auto` asosiy eslatma guruhida adminning oxirgi faolligidan keyin 5 daqiqa kutadi.
Hozir bir asosiy eslatma guruhi qo'llab-quvvatlanadi.

## Excel va sanalar

Mavjud fayl tuzilishi saqlangan: to'lovlar varag'i, C ustunda ism, D ustunda kurs,
M ustunda to'lov kuni, N ustunda kontakt; yozuvlar 5-qatordan boshlanadi.
Jadval varag'ida kunlar 3-qatorda, E ustundan boshlab; vaqtlar `14:00` ko'rinishida.
Oy nomli birinchi jadval varag'i import qilinadi.
Varaq nomini `Sentabr 2026` kabi yozish tavsiya etiladi; yil bo'lmasa import qilingan yil olinadi.
Eski sentabr jadvali migratsiyada 2026-yilga bog'landi.

Fayl avval tekshiriladi va zaxiralanadi, keyin asosiy fayl almashtiriladi.
O'quvchilar va darslar bazaga bitta tranzaksiyada yoziladi; xatoda baza o'zgarmaydi.
Import shu oy darslarini almashtiradi, boshqa oylar saqlanadi.
Shu oyga Telegram orqali kiritilgan dars o'zgarishlari qayta importda Excel bilan almashtiriladi.
Bo'sh yoki takroriy ismli ro'yxatlar qabul qilinmaydi. O'quvchilar ism bo'yicha moslanadi;
ismni almashtirish yoki o'quvchini ro'yxatdan chiqarish alohida boshqaruvni talab qiladi.

Eski sentabr to'lovidagi aniq `to'landi` belgilar oylik to'lov jadvaliga ko'chirildi.
Sentabr importida bu belgilar qo'shiladi; Excel'dagi bo'sh/`to'lanmagan` qiymat
avval belgilangan to'lovni avtomatik bekor qilmaydi. Tuzatish uchun `/tolanmadi` ishlating.
29–31-sanalar qisqa oyda oyning oxirgi kuniga moslanadi.
To'langan oy uchun eslatma yuborilmaydi.

## Zaxira va tekshiruv

`backups/` ichiga ishga tushishda, har yangi kunda va import oldidan baza va Excel nusxasi yoziladi.
`bot.log` fayli hajmi cheklangan; oxirgi 3 ta eski log saqlanadi.
Sarflangan tokenlar qayd etiladi; diagnostikada dollar balansi ko'rsatilmaydi.

Tekshiruv: `py -m unittest test_ai_bot test_improvements test_data_workflows test_admin_members test_study_context test_books -v`
Testlar Telegram'ga xabar yubormaydi; ma'lumotlar testi vaqtinchalik bazadan foydalanadi.

## Rasm va davomiy savollar

O'quvchi rasm yuborib, keyin `2–3-masalani tushunmadim` desa, bot oldingi rasmni
qayta ko'rib aynan shu masalalarni tushuntiradi. `Chunmadim`, `shu joyi nega?`,
`yana sodda tushuntir` kabi davomiy murojaatlar ham taniladi.

- Reply aniq rasmga yoki botning o'sha rasmga bergan javobiga bog'lanadi.
- Reply bo'lmasa o'quvchining shu chat/mavzudagi rasmi olinadi; boshqa o'quvchining rasmi taxmin qilinmaydi.
- Bir nechta mos rasm bo'lsa kerakli rasmga reply qilish so'raladi.
- Boshqa o'quvchi ham guruhdagi rasmga reply qilib savol bera oladi.
- O'qilmagan raqam yoki xira matnni taxmin qilmaslik, aniqroq rasm so'rash AI'ga ko'rsatilgan.
- Rasmni qayta yuklash ishlamasa bot yechimni taxmin qilmaydi, qayta yuborishni so'raydi.
- Rasm manzillari 24 soatgacha, chat uchun oxirgi 50 ta rasm va 200 ta bog'liq xabar doirasida saqlanadi.
- Aniq topshiriqqa bog'liq davomiy savol admin onlayn bo'lganda ham javob oladi; ustozga qaratilgan murojaat bundan mustasno.
- Bu imkoniyat Telegram photo sifatida yuborilgan rasmlar uchun. Rasm-fayl/PDF hujjatlari hali shu jarayonga ulanmagan.

## Kitoblarni olish

Oddiy foydalanuvchi ham guruh yoki shaxsiy chatga `kitob` deb yozsa uchala PDF yuboriladi.
`HTML kitob` faqat HTML darsligini, `Word Excel kitob` Office darsligini yuboradi.
`Python kitob` faqat Python darsligini yuboradi.
`kitob kerak`, `kitob tashlab ber`, `kitobni yuboring` shakllari ham ishlaydi.
Bu slash-buyruq emas; admin onlayn bo'lsa ham ishlaydi va OpenAI so'rovi sarflanmaydi.
PDFlar `books/` papkasida saqlanadi. Botni boshqa joyga ko'chirganda shu papkani ham ko'chiring.
Bu o'zgarish kitoblarni tarqatishni qo'shadi; PDF matnidan avtomatik qidirish alohida imkoniyatdir.
