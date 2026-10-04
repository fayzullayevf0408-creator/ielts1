# =====================================================================
# TELEGRAM BOT: IELTS EXAMINER, RUSSIAN MILLIY SERTIFIKAT & AI ASSISTANT
# Created with all user requirements and strict code length formatting
# =====================================================================
import asyncio
import datetime
import logging
import os
import sqlite3
import sys
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from groq import Groq
# ---------------------------------------------------------------------
# 1. TOKENLAR VA ASOSIY SOZLAMALAR
# ---------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8559476528:AAGEap-Jm-AsCTNAs7NeAn_fZW1LM0qom3I"
GROQ_API_KEY = "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"
ADMIN_ID = 6773733838
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)
# ---------------------------------------------------------------------
# 2. SQLITE BAZA BILAN ISHLASH VA JADVALLARNI YARATISH
# ---------------------------------------------------------------------
conn = sqlite3.connect("bot_database_v2.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    lang TEXT,
    day INTEGER,
    is_active INTEGER,
    words_count INTEGER,
    essays_count INTEGER,
    last_reset TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    word TEXT
)
""")
# Rus tili grammatikasi uchun takrorlanmaslik bazasi
cursor.execute("""
CREATE TABLE IF NOT EXISTS russian_grammar_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    question_hash TEXT
)
""")
conn.commit()
def get_user_db(user_id):
  today = str(datetime.date.today())
  cursor.execute(
      "SELECT lang, day, is_active, words_count, essays_count, last_reset FROM"
      " users WHERE user_id = ?",
      (user_id,),
  )
  row = cursor.fetchone()
  if not row:
    cursor.execute(
        "INSERT INTO users VALUES (?, 'uz', 1, 0, 0, 0, ?)", (user_id, today)
    )
    conn.commit()
    return {
        "lang": "uz",
        "day": 1,
        "is_active": 0,
        "words_count": 0,
        "essays_count": 0,
        "last_reset": today,
    }
  lang, day, is_active, w_count, e_count, last_reset = row
  if last_reset != today:
    cursor.execute(
        "UPDATE users SET words_count = 0, essays_count = 0, last_reset = ?"
        " WHERE user_id = ?",
        (today, user_id),
    )
    conn.commit()
    w_count, e_count = 0, 0
  return {
      "lang": lang,
      "day": day,
      "is_active": is_active,
      "words_count": w_count,
      "essays_count": e_count,
      "last_reset": today,
  }
def update_user_db(user_id, **kwargs):
  for key, value in kwargs.items():
    cursor.execute(
        f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id)
    )
  conn.commit()
# ---------------------------------------------------------------------
# 3. STATISTIKA VA HISOBLASH TIZIMI
# ---------------------------------------------------------------------
bot_stats = {
    "requests_daily": 0,
    "requests_monthly": 0,
    "requests_yearly": 0,
    "last_date": datetime.date.today(),
}
def update_request_stats():
  today = datetime.date.today()
  if bot_stats["last_date"] != today:
    if bot_stats["last_date"].month != today.month:
      if bot_stats["last_date"].year != today.year:
        bot_stats["requests_yearly"] = 0
      bot_stats["requests_monthly"] = 0
    bot_stats["requests_daily"] = 0
    bot_stats["last_date"] = today
  bot_stats["requests_daily"] += 1
  bot_stats["requests_monthly"] += 1
  bot_stats["requests_yearly"] += 1
# ---------------------------------------------------------------------
# 4. FSM (FINITE STATE MACHINE) HOLATLARI
# ---------------------------------------------------------------------
class BotStates(StatesGroup):
  waiting_for_word = State()
  waiting_for_essay_topic = State()
  waiting_for_essay_photo_or_text = State()
  waiting_for_suggestion = State()
  waiting_for_broadcast = State()
  waiting_for_flashcard_input = State()
  waiting_for_ai_prompt = State()
  # Rus tili Milliy Sertifikat holatlari
  waiting_for_rus_essay_topic = State()
  waiting_for_rus_essay_text = State()
  waiting_for_rus_word = State()
  # Speaking Part uchun alohida navbatma-navbat holatlar
  speaking_p1 = State()
  speaking_p2 = State()
  speaking_p3 = State()
  # Full Mock test holatlari
  mock_part1 = State()
  mock_part2 = State()
  mock_part3 = State()
# ---------------------------------------------------------------------
# 5. INTERFEYS VA MENYULAR
# ---------------------------------------------------------------------
def get_language_menu():
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🇺🇿 O'zbek tili", callback_data="lang_uz"
              ),
              InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
              InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
          ]
      ]
  )
def get_main_menu(lang="uz", user_id=None):
  if lang == "en":
    keyboard = [
        [
            InlineKeyboardButton(
                text="🤖 AI Assistant (Ask Anything)", callback_data="mode_ai"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 Word / Translation & Analysis",
                callback_data="mode_word",
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 IELTS Essay / Text Check", callback_data="mode_essay"
            )
        ],
        [
            InlineKeyboardButton(
                text=(
                    "🇷🇺 Rus tili Milliy Sertifikat (UZBMB)"
                ),  # Rus tili menyusi
                callback_data="mode_rus_milliy",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔥 31-Day Idiom Challenge", callback_data="mode_idiom"
            )
        ],
        [
            InlineKeyboardButton(
                text="📇 Flashcards (Custom Creator)",
                callback_data="mode_flashcard",
            ),
            InlineKeyboardButton(
                text="🎤 Speaking Simulator (Real-time)",
                callback_data="mode_speaking",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🎲 Random IELTS Topic", callback_data="mode_random_topic"
            )
        ],
        [
            InlineKeyboardButton(
                text="📚 Learned Idioms", callback_data="mode_history"
            ),
            InlineKeyboardButton(
                text="🧠 Idiom Quiz (Interactive)", callback_data="mode_quiz"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🧮 Math Problems / Examples", callback_data="mode_math"
            )
        ],
        [
            InlineKeyboardButton(
                text="💡 Send Suggestion", callback_data="mode_suggestion"
            ),
            InlineKeyboardButton(
                text="🌐 Change Language", callback_data="change_lang"
            ),
        ],
    ]
  elif lang == "ru":
    keyboard = [
        [
            InlineKeyboardButton(
                text="🤖 AI Помощник (Спроси о чем угодно)",
                callback_data="mode_ai",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 Слово / Перевод и Анализ", callback_data="mode_word"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 IELTS Эссе / Проверка текста", callback_data="mode_essay"
            )
        ],
        [
            InlineKeyboardButton(
                text=(
                    "🇷🇺 Rus tili Milliy Sertifikat (UZBMB)"
                ),  # Rus tili menyusi
                callback_data="mode_rus_milliy",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔥 31-дневный челлендж идиом", callback_data="mode_idiom"
            )
        ],
        [
            InlineKeyboardButton(
                text="📇 Карточки (Конструктор)", callback_data="mode_flashcard"
            ),
            InlineKeyboardButton(
                text="🎤 Speaking Симулятор (Реальный режим)",
                callback_data="mode_speaking",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🎲 Случайная тема IELTS", callback_data="mode_random_topic"
            )
        ],
        [
            InlineKeyboardButton(
                text="📚 Изученные идиомы", callback_data="mode_history"
            ),
            InlineKeyboardButton(
                text="🧠 Викторина (Интерактив)", callback_data="mode_quiz"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🧮 Мат. задачи / Примеры", callback_data="mode_math"
            )
        ],
        [
            InlineKeyboardButton(
                text="💡 Предложение / Отзыв", callback_data="mode_suggestion"
            ),
            InlineKeyboardButton(
                text="🌐 Изменить язык", callback_data="change_lang"
            ),
        ],
    ]
  else:
    keyboard = [
        [
            InlineKeyboardButton(
                text="🤖 AI Yordamchi (Hamma narsaga javob)",
                callback_data="mode_ai",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 So'z / Tarjima va Tahlil", callback_data="mode_word"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 IELTS Esse / Matn tekshirish", callback_data="mode_essay"
            )
        ],
        [
            InlineKeyboardButton(
                text=(
                    "🇷🇺 Rus tili Milliy Sertifikat (UZBMB)"
                ),  # Rus tili menyusi
                callback_data="mode_rus_milliy",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔥 31-Kunlik Idioma Challenge", callback_data="mode_idiom"
            )
        ],
        [
            InlineKeyboardButton(
                text="📇 Flashcards (Shaxsiy Konstruktor)",
                callback_data="mode_flashcard",
            ),
            InlineKeyboardButton(
                text="🎤 Speaking Simulator (Real-time)",
                callback_data="mode_speaking",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🎲 Tasodifiy IELTS Mavzu", callback_data="mode_random_topic"
            )
        ],
        [
            InlineKeyboardButton(
                text="📚 O'tilgan idiomalar", callback_data="mode_history"
            ),
            InlineKeyboardButton(
                text="🧠 Idioma Viktorina (Test - Interaktiv)",
                callback_data="mode_quiz",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🧮 Matematik masalalar / misollar",
                callback_data="mode_math",
            )
        ],
        [
            InlineKeyboardButton(
                text="💡 Taklif yuborish", callback_data="mode_suggestion"
            ),
            InlineKeyboardButton(
                text="🌐 Tilni o'zgartirish", callback_data="change_lang"
            ),
        ],
    ]
  if user_id == ADMIN_ID:
    keyboard.append([
        InlineKeyboardButton(
            text="📊 Admin Statistikasi", callback_data="admin_stats"
        ),
        InlineKeyboardButton(
            text="📢 Broadcast (Xabar tarqatish)",
            callback_data="admin_broadcast",
        ),
    ])
  return InlineKeyboardMarkup(inline_keyboard=keyboard)


# Rus tili Milliy Sertifikat 5 ta bo'lim menyusi
def get_rus_milliy_menu():
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="📊 Grammatika (UZBMB Standart)",
                  callback_data="rus_grammar",
              )
          ],
          [
              InlineKeyboardButton(
                  text="✍️ Essay (C - A+ Qat'iy Baholash)",
                  callback_data="rus_essay",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📖 Lug'at va Tarjima", callback_data="rus_dict"
              )
          ],
          [
              InlineKeyboardButton(
                  text="📌 Bo'lim 4 (Qoldiq / Tez kunda)",
                  callback_data="rus_extra_1",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📌 Bo'lim 5 (Qoldiq / Tez kunda)",
                  callback_data="rus_extra_2",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🔙 Asosiy Menyu", callback_data="rus_back_main"
              )
          ],
      ]
  )


# ---------------------------------------------------------------------
# 6. START VA TILni BOSHQARISH
# ---------------------------------------------------------------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
  await state.clear()
  user_id = message.from_user.id
  get_user_db(user_id)
  cursor.execute(
      "INSERT OR IGNORE INTO users (user_id, lang, day, is_active,"
      " words_count, essays_count, last_reset) VALUES (?, 'uz', 1, 0, 0, 0, ?)",
      (user_id, str(datetime.date.today())),
  )
  conn.commit()
  await message.answer(
      "Assalomu alaykum! 🤖\nMen Fayzullayev Firdavs tomonidan yaratilgan"
      " yordamchi botman.\n\nIltimos, tilni tanlang / Please select your"
      " language:",
      reply_markup=get_language_menu(),
  )


@dp.callback_query(F.data.startswith("lang_") | (F.data == "change_lang"))
async def set_language(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  get_user_db(user_id)
  if callback.data == "change_lang":
    await callback.message.answer(
        "Tilni tanlang / Select language / Выберите язык:",
        reply_markup=get_language_menu(),
    )
    await callback.answer()
    return
  lang = callback.data.split("_")[1]
  update_user_db(user_id, lang=lang)
  wel_texts = {
      "uz": "✅ Til O'zbek tiliga o'zgartirildi!\nKerakli bo'limni tanlang:",
      "en": "✅ Language changed to English!\nSelect a section:",
      "ru": "✅ Язык изменен на русский!\nВыберите раздел:",
  }
  await callback.message.answer(
      wel_texts.get(lang, wel_texts["uz"]),
      reply_markup=get_main_menu(lang, user_id),
  )
  await callback.answer()


# ---------------------------------------------------------------------
# 7. ADMIN PANEL VA TAKLIFLAR
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "admin_stats")
async def show_admin_stats(callback: types.CallbackQuery):
  if callback.from_user.id != ADMIN_ID:
    await callback.answer("Bu buyruq faqat admin uchun!", show_alert=True)
    return
  cursor.execute("SELECT COUNT(*) FROM users")
  total_users = cursor.fetchone()[0]
  text = (
      f"📊 **Bot Statistikasi:**\n\n👥 Jami foydalanuvchilar:"
      f" {total_users}\n\n⚡ So'rovlar:\n- Kunlik:"
      f" {bot_stats['requests_daily']}\n- Oylik:"
      f" {bot_stats['requests_monthly']}"
  )
  lang = get_user_db(callback.from_user.id)["lang"]
  await callback.message.answer(
      text, reply_markup=get_main_menu(lang, callback.from_user.id)
  )
  await callback.answer()


@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
  if callback.from_user.id != ADMIN_ID:
    await callback.answer("Bu buyruq faqat admin uchun!", show_alert=True)
    return
  await state.set_state(BotStates.waiting_for_broadcast)
  await callback.message.answer(
      "📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring:"
  )
  await callback.answer()


@dp.message(BotStates.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
  if message.from_user.id != ADMIN_ID:
    return
  cursor.execute("SELECT user_id FROM users")
  users = cursor.fetchall()
  count = 0
  for (uid,) in users:
    try:
      await bot.send_message(uid, message.text)
      count += 1
    except Exception:
      pass
  await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yetkazildi.")
  await state.clear()


@dp.callback_query(F.data == "mode_suggestion")
async def suggestion_handler(callback: types.CallbackQuery, state: FSMContext):
  await state.set_state(BotStates.waiting_for_suggestion)
  await callback.message.answer(
      "💡 Botimiz uchun taklif yoki shikoyatlaringizni yozib yuboring:"
  )
  await callback.answer()


@dp.message(BotStates.waiting_for_suggestion)
async def receive_suggestion(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  suggestion_text = (
      f"💡 Yangi taklif!\n\n👤 Kimdan: @{message.from_user.username} (ID:"
      f" {user_id})\n📝 Xabar: {message.text}"
  )
  try:
    await bot.send_message(ADMIN_ID, suggestion_text)
  except Exception:
    pass
  await message.answer(
      "✅ Taklifingiz adminga yuborildi. Rahmat!",
      reply_markup=get_main_menu(lang, user_id),
  )
  await state.clear()


# ---------------------------------------------------------------------
# 8. RUS TILI MILLIY SERTIFIKAT (UZBMB) MODULI
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "mode_rus_milliy")
async def rus_milliy_menu_handler(callback: types.CallbackQuery):
  await callback.message.answer(
      "🇷🇺 **Rus tili Milliy Sertifikat (UZBMB)** tayyorgarlik bo'limiga"
      " xush kelibsiz!\n\nQuyidagi bo'limlardan birini tanlang:",
      reply_markup=get_rus_milliy_menu(),
  )
  await callback.answer()


@dp.callback_query(F.data == "rus_back_main")
async def rus_back_to_main(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  await callback.message.answer(
      "Asosiy menyu:", reply_markup=get_main_menu(lang, user_id)
  )
  await callback.answer()


# 1. Rus tili Grammatika (UZBMB standarti, C dan A+ gacha, takrorlanmas testlar)
@dp.callback_query(F.data == "rus_grammar")
async def rus_grammar_handler(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  update_request_stats()

  # Takrorlanmaslikni ta'minlash uchun oldingi testlar hashini olamiz
  cursor.execute(
      "SELECT question_hash FROM russian_grammar_history WHERE user_id = ?",
      (user_id,),
  )
  history = [row[0] for row in cursor.fetchall()]
  history_str = (
      ", ".join(history[-20:]) if history else "Yo'q (birinchi test)"
  )

  prompt = (
      "Create a mixed Russian grammar test question adhering strictly to"
      " Uzbekistan National Certificate (UZBMB) standards. The question must"
      " be unique and NOT resemble these previous ones: "
      f"[{history_str}]. Provide the Question, 4 options labeled 'A)', 'B)',"
      " 'C)', 'D)', and clearly specify 'CORRECT: X' at the end. Also assign"
      " an official UZBMB level scale rating for this test item (from C, B2,"
      " B1, A2, A to A+). Output strictly in Uzbek language instructions and"
      " Russian content where required. No asterisks (**)."
  )
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=600,
    )
    content = completion.choices[0].message.content
    correct_option = "A"
    for line in content.split("\n"):
      if "CORRECT:" in line.upper():
        correct_option = line.split(":")[-1].strip().upper()

    # Bazaga yozamiz (takrorlanmasligi uchun qisqa hash sifatida saqlaymiz)
    q_hash = content[:30]
    cursor.execute(
        "INSERT INTO russian_grammar_history (user_id, question_hash) VALUES"
        " (?, ?)",
        (user_id, q_hash),
    )
    conn.commit()

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="A", callback_data=f"rus_g_A_{correct_option}"
                ),
                InlineKeyboardButton(
                    text="B", callback_data=f"rus_g_B_{correct_option}"
                ),
                InlineKeyboardButton(
                    text="C", callback_data=f"rus_g_C_{correct_option}"
                ),
                InlineKeyboardButton(
                    text="D", callback_data=f"rus_g_D_{correct_option}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Boshqa test olish", callback_data="rus_grammar"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Orqaga", callback_data="mode_rus_milliy"
                )
            ],
        ]
    )
    await callback.message.answer(
        f"📊 **UZBMB Rus tili — Grammatika Testi:**\n\n{content}",
        reply_markup=markup,
    )
  except Exception:
    await callback.message.answer(
        "❌ Test yaratishda xatolik yuz berdi.",
        reply_markup=get_rus_milliy_menu(),
    )
  await callback.answer()


@dp.callback_query(F.data.startswith("rus_g_"))
async def process_rus_grammar_answer(callback: types.CallbackQuery):
  parts = callback.data.split("_")
  user_choice = parts[2]
  correct_choice = parts[3]
  if user_choice == correct_choice:
    await callback.message.answer(
        f"✅ To'g'ri! Siz tanlagan javob ({user_choice}) UZBMB"
        " standartlariga ko'ra to'g'ri chiqdi! 🎉 Darajangiz: A+"
    )
  else:
    await callback.message.answer(
        f"❌ Xato! To'g'ri javob: **{correct_choice}** edi. Keyingi safar"
        " diqqatliroq bo'ling."
    )
  await callback.answer()


# 2. Rus tili Essay (C dan A+ gacha qat'iy baholash)
@dp.callback_query(F.data == "rus_essay")
async def rus_essay_start(callback: types.CallbackQuery, state: FSMContext):
  await state.set_state(BotStates.waiting_for_rus_essay_topic)
  await callback.message.answer(
      "✍️ **Rus tili Essay (Milliy Sertifikat)**\n\nIltimos, essay"
      " mavzusini yuboring (yoki o'zingiz yozmoqchi bo'lgan mavzu):"
  )
  await callback.answer()


@dp.message(BotStates.waiting_for_rus_essay_topic)
async def rus_essay_get_topic(message: types.Message, state: FSMContext):
  await state.update_data(rus_essay_topic=message.text)
  await state.set_state(BotStates.waiting_for_rus_essay_text)
  await message.answer(
      "✅ Mavzu qabul qilindi!\n\nEndi rus tilida yozgan essay matnini yuboring:"
  )


@dp.message(BotStates.waiting_for_rus_essay_text)
async def rus_essay_evaluate(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  data = await state.get_data()
  topic = data.get("rus_essay_topic", "Mavzu")
  essay_text = message.text
  update_request_stats()

  system_prompt = (
      "You are an exceptionally strict, uncompromising, and professional"
      " official UZBMB Russian Language Examiner for National Certificate."
      " Evaluate the candidate's essay strictly according to UZBMB standards."
      " Assign a rigid grade scale from C, B, B+, A, to A+. NO asterisks (**)."
      " Use emojis only at the beginning of lines.\n\nRequired Structure:\n📊"
      " Sertifikat Darajasi (C dan A+ gacha): [...]\n⭐ UZBMB Mezonlari bo'yicha"
      " Baholash: [...]\n❌ Grammatik va Leksik Xatolar: [...]\n🛠 Mukammal"
      " Akademik Versiya: [...]\n💡 Tavsiyalar: [...]"
  )
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Mavzu: {topic}\n\nCandidate's Essay: {essay_text}",
            },
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    await message.answer(
        completion.choices[0].message.content,
        reply_markup=get_rus_milliy_menu(),
    )
    await state.clear()
  except Exception:
    await message.answer(
        "❌ Esseni baholashda xatolik yuz berdi.",
        reply_markup=get_rus_milliy_menu(),
    )
    await state.clear()


# 3. Rus tili Lug'at va Tarjima
@dp.callback_query(F.data == "rus_dict")
async def rus_dict_handler(callback: types.CallbackQuery, state: FSMContext):
  await state.set_state(BotStates.waiting_for_rus_word)
  await callback.message.answer(
      "📖 **Rus tili Lug'at va Tahlil**\n\nMenga tarjima qilmoqchi yoki"
      " tahlil qilmoqchi bo'lgan ruscha so'z yoki iborangizni yuboring:"
  )
  await callback.answer()


@dp.message(BotStates.waiting_for_rus_word)
async def process_rus_word(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  word = message.text
  update_request_stats()

  prompt = (
      f"Analyze Russian word/phrase: '{word}' for UZBMB National Certificate"
      " level. Provide translation into Uzbek, synonyms, morphological"
      " analysis, and example sentences. Rules: NO asterisks (**). Emojis"
      " only at the start of lines."
  )
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=1000,
    )
    await message.answer(
        completion.choices[0].message.content,
        reply_markup=get_rus_milliy_menu(),
    )
  except Exception:
    await message.answer(
        "❌ Tahlil qilishda xatolik yuz berdi.",
        reply_markup=get_rus_milliy_menu(),
    )
  await state.clear()


# 4 va 5-qoldiq bo'limlar uchun handler
@dp.callback_query(F.data.in_({"rus_extra_1", "rus_extra_2"}))
async def rus_extra_handler(callback: types.CallbackQuery):
  await callback.message.answer(
      "📌 Bu bo'lim tez orada qo'shimcha imkoniyatlar bilan to'ldiriladi!",
      reply_markup=get_rus_milliy_menu(),
  )
  await callback.answer()


# ---------------------------------------------------------------------
# 9. OVOZLI XABARLARNI GROQ WHISPER ORQALI MATNGA O'GIRISH FUNKSIYASI
# ---------------------------------------------------------------------
async def transcribe_voice_message(message: types.Message) -> str:
  file_id = message.voice.file_id
  file = await bot.get_file(file_id)
  file_path = file.file_path
  ogg_path = f"voice_{message.from_user.id}.ogg"
  await bot.download_file(file_path, ogg_path)
  try:
    with open(ogg_path, "rb") as audio_file:
      transcript = groq_client.audio.transcriptions.create(
          model="whisper-large-v3-turbo", file=audio_file, response_format="text"
      )
    os.remove(ogg_path)
    return str(transcript)
  except Exception as e:
    if os.path.exists(ogg_path):
      os.remove(ogg_path)
    print(f"Whisper Transcription Error: {e}")
    return ""


# ---------------------------------------------------------------------
# 10. SPEAKING SIMULATOR (KETMA-KET BITTADAN SAVOL BERISH VA TEKSHIRISH)
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "mode_speaking")
async def speaking_main_menu(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  texts = {
      "uz": (
          "🎤 **IELTS Speaking Simulator**\n\nTayyorgarlik turini"
          " tanlang:\n- Istalgan bitta part bo'yicha alohida"
          " shug'ullaning\n- Yoki real imtihon muhitidagi to'liq **Full Mock"
          " Test**ni boshlang!\n\n*(Eslatma: Ovozli xabar yoki matn orqali"
          " javob berishingiz mumkin)*"
      ),
      "en": "🎤 **IELTS Speaking Simulator**\n\nChoose your practice mode:",
      "ru": "🎤 **IELTS Speaking Simulator**\n\nВыберите режим подготовки:",
  }
  markup = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="📌 Part 1 (Introduction - Sequential)",
                  callback_data="speak_part_1",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🧭 Part 2 (Cue Card)", callback_data="speak_part_2"
              )
          ],
          [
              InlineKeyboardButton(
                  text="💬 Part 3 (Discussion - Sequential)",
                  callback_data="speak_part_3",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🚀 Full Mock Test (Real Exam)",
                  callback_data="speak_full_mock",
              )
          ],
      ]
  )
  await callback.message.answer(texts.get(lang, texts["uz"]), reply_markup=markup)
  await callback.answer()


# --- SPEAKING PART 1 ---
@dp.callback_query(F.data == "speak_part_1")
async def start_single_part1(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  prompt = (
      "Generate ONE simple IELTS Speaking Part 1 question on a random daily"
      f" topic. Output strictly in language '{lang}'. No asterisks (**)."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "user", "content": prompt}],
      temperature=0.7,
      max_tokens=200,
  )
  question = completion.choices[0].message.content
  await state.set_state(BotStates.speaking_p1)
  await state.update_data(p1_count=1, p1_q=question)
  await callback.message.answer(
      f"📌 **IELTS Speaking — Part 1 (1-savol)**\n\n{question}\n\n*Javobingizni"
      " ovozli xabar yoki matn ko'rinishida yuboring:*"
  )
  await callback.answer()


@dp.message(BotStates.speaking_p1, F.voice | F.text)
async def process_single_part1(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  if message.voice:
    user_ans = await transcribe_voice_message(message)
    if not user_ans:
      user_ans = "[Voice message could not be transcribed]"
  else:
    user_ans = message.text
  data = await state.get_data()
  count = data.get("p1_count", 1)
  update_request_stats()
  if count < 3:
    prompt = (
        "Generate next IELTS Speaking Part 1 question. Output strictly in"
        f" language '{lang}'. No asterisks (**)."
    )
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=200,
    )
    next_q = completion.choices[0].message.content
    await state.update_data(p1_count=count + 1)
    await message.answer(
        f"✅ Javobingiz qabul qilindi!\n\n📌 **Part 1 ({count+1}-savol):**\n\n{next_q}\n\n*Javobingizni"
        " yuboring:*"
    )
  else:
    system_prompt = (
        "You are a strict and professional IELTS Examiner. Evaluate the"
        " candidate's Part 1 answers. Provide Band Score, Fluency, Lexical"
        " Resource, Grammatical Range, Pronunciation feedback, and tips."
        f" Output strictly in language '{lang}'. NO asterisks (**). Use emojis"
        " only at the beginning of lines."
    )
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Part 1 Last Answer: {user_ans}"},
        ],
        temperature=0.2,
        max_tokens=1000,
    )
    await message.answer(
        "📊 **Part 1 Yakuniy Tahlili:**\n\n"
        + completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
    await state.clear()


# --- SPEAKING PART 2 ---
@dp.callback_query(F.data == "speak_part_2")
async def start_single_part2(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  prompt = (
      "Generate an IELTS Speaking Part 2 Cue Card topic (Describe a...). Output"
      f" strictly in language '{lang}'. No asterisks (**)."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "user", "content": prompt}],
      temperature=0.7,
      max_tokens=400,
  )
  cue_card = completion.choices[0].message.content
  await state.set_state(BotStates.speaking_p2)
  await callback.message.answer(
      "🧭 **IELTS Speaking — Part 2 (Cue Card)**\n\n1 daqiqa o'ylab oling va 2"
      " daqiqa davomida gapirib, ovozli xabar yoki matn"
      f" yuboring:\n\n{cue_card}"
  )
  await callback.answer()


@dp.message(BotStates.speaking_p2, F.voice | F.text)
async def process_single_part2(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  if message.voice:
    user_ans = await transcribe_voice_message(message)
    if not user_ans:
      user_ans = "[Voice message]"
  else:
    user_ans = message.text
  update_request_stats()
  system_prompt = (
      "You are a strict IELTS Examiner. Evaluate this Part 2 Cue Card response"
      " based on long-turn fluency, vocabulary, grammar, and structure."
      f" Output strictly in language '{lang}'. NO asterisks (**). Use emojis"
      " only at the beginning of lines."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": f"Part 2 Response: {user_ans}"},
      ],
      temperature=0.2,
      max_tokens=1000,
  )
  await message.answer(
      completion.choices[0].message.content,
      reply_markup=get_main_menu(lang, user_id),
  )
  await state.clear()


# --- SPEAKING PART 3 ---
@dp.callback_query(F.data == "speak_part_3")
async def start_single_part3(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  prompt = (
      "Generate ONE complex discussion question for IELTS Speaking Part 3 on a"
      f" social topic. Output strictly in language '{lang}'. No asterisks (**)."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "user", "content": prompt}],
      temperature=0.7,
      max_tokens=200,
  )
  question = completion.choices[0].message.content
  await state.set_state(BotStates.speaking_p3)
  await state.update_data(p3_count=1)
  await callback.message.answer(
      f"💬 **IELTS Speaking — Part 3 (1-savol)**\n\n{question}\n\n*Javobingizni"
      " ovozli xabar yoki matn orqali yuboring:*"
  )
  await callback.answer()


@dp.message(BotStates.speaking_p3, F.voice | F.text)
async def process_single_part3(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  if message.voice:
    user_ans = await transcribe_voice_message(message)
    if not user_ans:
      user_ans = "[Voice message]"
  else:
    user_ans = message.text
  data = await state.get_data()
  count = data.get("p3_count", 1)
  update_request_stats()
  if count < 2:
    prompt = (
        "Generate next complex discussion question for IELTS Speaking Part 3."
        f" Output strictly in language '{lang}'. No asterisks (**)."
    )
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=200,
    )
    next_q = completion.choices[0].message.content
    await state.update_data(p3_count=count + 1)
    await message.answer(
        f"✅ Javob qabul qilindi!\n\n💬 **Part 3 ({count+1}-savol):**\n\n{next_q}\n\n*Javobingizni"
        " yuboring:*"
    )
  else:
    system_prompt = (
        "You are a strict IELTS Examiner. Evaluate this Part 3 advanced"
        " discussion response for abstract ideas, complex structures, and"
        f" lexical resource. Output strictly in language '{lang}'. NO asterisks"
        " (**). Use emojis only at the beginning of lines."
    )
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Part 3 Response: {user_ans}"},
        ],
        temperature=0.2,
        max_tokens=1000,
    )
    await message.answer(
        "📊 **Part 3 Yakuniy Tahlili:**\n\n"
        + completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
    await state.clear()


# --- REAL FULL MOCK TEST ---
@dp.callback_query(F.data == "speak_full_mock")
async def start_full_mock(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  prompt = (
      "Generate ONE IELTS Speaking Part 1 question. Output strictly in language"
      f" '{lang}'. No asterisks (**)."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "user", "content": prompt}],
      temperature=0.7,
      max_tokens=200,
  )
  q1 = completion.choices[0].message.content
  await state.set_state(BotStates.mock_part1)
  await callback.message.answer(
      f"🚀 **Full IELTS Speaking Mock Test boshlandi!**\n\n1-Bosqich: **Part 1"
      f" (Introduction)**\n\n{q1}\n\n*Javobingizni yuboring:*"
  )
  await callback.answer()


@dp.message(BotStates.mock_part1, F.voice | F.text)
async def mock_receive_part1(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  ans1 = (
      await transcribe_voice_message(message)
      if message.voice
      else message.text
  )
  await state.update_data(m_ans1=ans1)
  update_request_stats()
  prompt = (
      "Generate an IELTS Speaking Part 2 Cue Card topic. Output strictly in"
      f" language '{lang}'. No asterisks (**)."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "user", "content": prompt}],
      temperature=0.7,
      max_tokens=300,
  )
  p2_cue = completion.choices[0].message.content
  await state.set_state(BotStates.mock_part2)
  await state.update_data(m_cue2=p2_cue)
  await message.answer(
      f"✅ Part 1 yakunlandi!\n\n2-Bosqich: **Part 2 (Cue"
      f" Card)**\nMavzu:\n\n{p2_cue}\n\n*Ovozli xabar yoki matn ko'rinishida"
      " javobingizni yuboring:*"
  )


@dp.message(BotStates.mock_part2, F.voice | F.text)
async def mock_receive_part2(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  ans2 = (
      await transcribe_voice_message(message)
      if message.voice
      else message.text
  )
  await state.update_data(m_ans2=ans2)
  data = await state.get_data()
  p2_topic = data.get("m_cue2", "Topic")
  update_request_stats()
  prompt = (
      "Generate ONE Part 3 discussion question based on this topic:"
      f" {p2_topic}. Output strictly in language '{lang}'. No asterisks (**)."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "user", "content": prompt}],
      temperature=0.7,
      max_tokens=200,
  )
  p3_q = completion.choices[0].message.content
  await state.set_state(BotStates.mock_part3)
  await message.answer(
      f"✅ Part 2 qabul qilindi!\n\n3-Bosqich: **Part"
      f" 3 (Discussion)**\n\n{p3_q}\n\n*Oxirgi javobingizni yuboring:*"
  )


@dp.message(BotStates.mock_part3, F.voice | F.text)
async def mock_receive_part3_and_finish(
    message: types.Message, state: FSMContext
):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  ans3 = (
      await transcribe_voice_message(message)
      if message.voice
      else message.text
  )
  data = await state.get_data()
  ans1 = data.get("m_ans1", "")
  ans2 = data.get("m_ans2", "")
  update_request_stats()
  system_prompt = (
      "You are an official, strict, and professional IELTS Examiner. Evaluate"
      " the candidate's complete Full Mock Test (Part 1, Part 2, Part 3"
      " together). Provide a comprehensive, rigid evaluation across all 4"
      " official IELTS criteria: 1. Fluency and Coherence\n2. Lexical"
      " Resource\n3. Grammatical Range and Accuracy\n4. Pronunciation\nGive a"
      " realistic Overall Band Score and detailed feedback for each part."
      f" Output strictly in language '{lang}'. NO asterisks (**). Use emojis"
      " only at the very beginning of lines.\n\nRequired Output"
      " Structure:\n📊 Overall IELTS Speaking Band Score: [...]\n⭐ Part-by-Part"
      " Examiner Feedback: [...]\n❌ Major Mistakes & Grammar Flaws:"
      " [...]\n🛠 Actionable Tips for Higher Band: [...]"
  )
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Full Mock Answers -> Part 1: {ans1} | Part 2: {ans2} | Part"
                    f" 3: {ans3}"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=1500,
    )
    await message.answer(
        completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
    await state.clear()
  except Exception:
    await message.answer(
        "❌ Tahlil qilishda xatolik yuz berdi.",
        reply_markup=get_main_menu(lang, user_id),
    )
    await state.clear()


# ---------------------------------------------------------------------
# 11. INTERAKTIV QUIZ (TUGMALI A, B, C, D)
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "mode_quiz")
async def interactive_quiz_handler(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  prompt = (
      "Create an IELTS idiom or vocabulary multiple choice question. Provide"
      " the Question, and 4 options labeled exactly as 'A)', 'B)', 'C)',"
      " 'D)'. At the very end on a new line write 'CORRECT: X' where X is A, B,"
      f" C or D. Output strictly in language '{lang}'. No asterisks (**)."
  )
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )
    content = completion.choices[0].message.content
    correct_option = "A"
    for line in content.split("\n"):
      if "CORRECT:" in line.upper():
        correct_option = line.split(":")[-1].strip().upper()
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="A", callback_data=f"quiz_ans_A_{correct_option}"
                ),
                InlineKeyboardButton(
                    text="B", callback_data=f"quiz_ans_B_{correct_option}"
                ),
                InlineKeyboardButton(
                    text="C", callback_data=f"quiz_ans_C_{correct_option}"
                ),
                InlineKeyboardButton(
                    text="D", callback_data=f"quiz_ans_D_{correct_option}"
                ),
            ]
        ]
    )
    await callback.message.answer(
        f"🧠 **IELTS Interaktiv Quiz:**\n\n{content}", reply_markup=markup
    )
  except Exception:
    await callback.message.answer("❌ Quiz yaratishda xatolik yuz berdi.")
  await callback.answer()


@dp.callback_query(F.data.startswith("quiz_ans_"))
async def process_quiz_answer(callback: types.CallbackQuery):
  parts = callback.data.split("_")
  user_choice = parts[2]
  correct_choice = parts[3]
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  if user_choice == correct_choice:
    await callback.message.answer(
        f"✅ To'g'ri! Siz tanlagan javob ({user_choice}) to'g'ri chiqdi! 🎉",
        reply_markup=get_main_menu(lang, user_id),
    )
  else:
    await callback.message.answer(
        f"❌ Xato! To'g'ri javob: **{correct_choice}** edi.",
        reply_markup=get_main_menu(lang, user_id),
    )
  await callback.answer()


# ---------------------------------------------------------------------
# 12. FLASHCARDS, MATH, RANDOM TOPICS VA BOSHQA REJIMLAR
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "mode_flashcard")
async def flashcard_menu(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  cursor.execute("DELETE FROM flashcards WHERE user_id = ?", (user_id,))
  conn.commit()
  await state.set_state(BotStates.waiting_for_flashcard_input)
  markup = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="🏁 Yakunlash & Testni boshlash", callback_data="fc_finish"
          )
      ]]
  )
  await callback.message.answer(
      "📇 **Flashcards Konstruktori**\n\nYodlamoqchi bo'lgan inglizcha so'z"
      " yoki iborangizni yuboring (har safar qo'shilib boradi):",
      reply_markup=markup,
  )
  await callback.answer()


@dp.message(BotStates.waiting_for_flashcard_input)
async def process_flashcard_word(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  word = message.text.strip()
  cursor.execute(
      "INSERT INTO flashcards (user_id, word) VALUES (?, ?)", (user_id, word)
  )
  conn.commit()
  cursor.execute(
      "SELECT COUNT(*) FROM flashcards WHERE user_id = ?", (user_id,)
  )
  count = cursor.fetchone()[0]
  markup = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="🏁 Yakunlash & Testni boshlash", callback_data="fc_finish"
          )
      ]]
  )
  await message.answer(
      f"✅ Qabul qilindi! (Jami: {count} ta so'z)\nYana so'z yuborishingiz"
      " mumkin:",
      reply_markup=markup,
  )


@dp.callback_query(F.data == "fc_finish")
async def flashcard_finish(callback: types.CallbackQuery, state: FSMContext):
  await state.clear()
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  cursor.execute("SELECT word FROM flashcards WHERE user_id = ?", (user_id,))
  words = [row[0] for row in cursor.fetchall()]
  if not words:
    await callback.message.answer("❌ Siz hali birorta so'z kiritmadingiz!")
    await callback.answer()
    return
  update_request_stats()
  words_str = ", ".join(words)
  prompt = (
      "Create an interactive IELTS vocabulary quiz based on these words:"
      f" {words_str}. Output strictly in language '{lang}'. No asterisks (**)."
  )
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=800,
    )
    await callback.message.answer(
        "🧠 **Siz kiritgan so'zlar bo'yicha Flashcard Testi:**\n\n"
        + completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
  except Exception:
    await callback.message.answer("❌ Xatolik yuz berdi.")
  await callback.answer()


@dp.callback_query(F.data == "mode_math")
async def math_mode(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  prompt = (
      "Generate a challenging math problem with step-by-step solution. Output"
      f" strictly in language '{lang}'. No asterisks (**)."
  )
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=1000,
    )
    await callback.message.answer(
        completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
  except Exception:
    await callback.message.answer("❌ Xatolik yuz berdi.")
  await callback.answer()


@dp.callback_query(F.data == "mode_random_topic")
async def random_topic_mode(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  prompt = (
      "Generate a random IELTS Speaking Part 2 cue card topic and Writing Task"
      f" 2 topic. Output strictly in language '{lang}'. No asterisks (**)."
  )
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=800,
    )
    await callback.message.answer(
        "🎲 **Tasodifiy IELTS Mavzulari:**\n\n"
        + completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
  except Exception:
    await callback.message.answer("❌ Xatolik yuz berdi.")
  await callback.answer()


# ---------------------------------------------------------------------
# 13. CALLBACK ROUTER VA CHALLENGE (31-KUNLIK IDIOMA)
# ---------------------------------------------------------------------
@dp.callback_query(F.data.startswith("mode_"))
async def mode_callback(callback: types.CallbackQuery, state: FSMContext):
  action = callback.data.split("_")[1]
  user_id = callback.from_user.id
  user_info = get_user_db(user_id)
  lang = user_info["lang"]
  if action == "word":
    if user_info["words_count"] >= 30:
      await callback.message.answer(
          "❌ Kunlik so'z limitiga yetdingiz (30/30).",
          reply_markup=get_main_menu(lang, user_id),
      )
      await callback.answer()
      return
    await state.set_state(BotStates.waiting_for_word)
    await callback.message.answer("✍️ Menga istalgan so'z yoki iborani yuboring:")
  elif action == "essay":
    if user_info["essays_count"] >= 5:
      await callback.message.answer(
          "❌ Kunlik esse limitiga yetdingiz (5/5).",
          reply_markup=get_main_menu(lang, user_id),
      )
      await callback.answer()
      return
    await state.set_state(BotStates.waiting_for_essay_topic)
    await callback.message.answer(
        "📝 Esseni tekshirish uchun avval mavzusini yuboring:"
    )
  elif action == "idiom":
    if user_info["is_active"]:
      await callback.message.answer(
          f"⚠ Challenge allaqachon faol!\n📅 Hozirgi kun:"
          f" {user_info['day']} / 31"
      )
    else:
      update_user_db(user_id, day=1, is_active=1)
      await callback.message.answer(
          "🔥 31-Kunlik Idioma Challenge boshlandi! 🏆"
      )
      asyncio.create_task(send_daily_idiom_for_user(user_id))
  elif action == "history":
    cursor.execute("SELECT word FROM flashcards WHERE user_id = ?", (user_id,))
    words = [row[0] for row in cursor.fetchall()]
    if not words:
      await callback.message.answer(
          "📭 Hozircha saqlangan so'zlaringiz yo'q.",
          reply_markup=get_main_menu(lang, user_id),
      )
    else:
      await callback.message.answer(
          "📚 **Siz kiritgan so'zlar:**\n\n"
          + "\n".join([f"{i+1}. {w}" for i, w in enumerate(words)]),
          reply_markup=get_main_menu(lang, user_id),
      )
  await callback.answer()


async def send_daily_idiom_for_user(user_id: int):
  try:
    while True:
      user_info = get_user_db(user_id)
      if not user_info["is_active"]:
        break
      current_day = user_info["day"]
      lang = user_info["lang"]
      if current_day > 31:
        update_user_db(user_id, is_active=0)
        await bot.send_message(
            user_id, "🎉 31 kunlik Idioma Challenge yakunlandi! 🏆"
        )
        break
      update_request_stats()
      prompt = (
          "Send one unique English idiom for IELTS. Day"
          f" {current_day}. Explanation language: '{lang}'. No asterisks (**)."
      )
      completion = groq_client.chat.completions.create(
          model="openai/gpt-oss-120b",
          messages=[{"role": "user", "content": prompt}],
          temperature=0.7,
      )
      await bot.send_message(user_id, completion.choices[0].message.content)
      update_user_db(user_id, day=current_day + 1)
      await asyncio.sleep(86400)
  except Exception as e:
    print(f"Challenge xatosi: {e}")


# ---------------------------------------------------------------------
# 14. SO'Z VA ESSAY TEKSHIRISH TIZIMI
# ---------------------------------------------------------------------
@dp.message(BotStates.waiting_for_word)
async def process_word(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  user_info = get_user_db(user_id)
  lang = user_info["lang"]
  update_user_db(user_id, words_count=user_info["words_count"] + 1)
  update_request_stats()
  prompt = (
      f"Analyze word: '{message.text}'. Output language: '{lang}'. Rules: NO"
      " asterisks (**). Emojis only at the start of lines."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "user", "content": prompt}],
      temperature=0.5,
  )
  await message.answer(
      completion.choices[0].message.content,
      reply_markup=get_main_menu(lang, user_id),
  )
  await state.clear()


@dp.message(BotStates.waiting_for_essay_topic)
async def process_essay_topic(message: types.Message, state: FSMContext):
  await state.update_data(essay_topic=message.text)
  await state.set_state(BotStates.waiting_for_essay_photo_or_text)
  await message.answer("✅ Mavzu qabul qilindi! Endi esse matnini yuboring:")


@dp.message(BotStates.waiting_for_essay_photo_or_text)
async def process_essay_submission(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  user_info = get_user_db(user_id)
  lang = user_info["lang"]
  update_user_db(user_id, essays_count=user_info["essays_count"] + 1)
  update_request_stats()
  data = await state.get_data()
  topic = data.get("essay_topic", "Topic")
  essay_content = message.text or "[Essay text]"
  system_prompt = (
      "You are an exceptionally strict, uncompromising, and professional"
      f" official IELTS Examiner. Output strictly in language '{lang}'. NO"
      " asterisks (**). Use emojis only at the very beginning of lines.\n\nRequired"
      " Output Structure:\n📊 IELTS Band Score: [...]\n⭐ Detailed Examiner"
      " Feedback: [...]\n❌ Major Mistakes & Grammar Flaws: [...]\n🛠 Improved"
      " Academic Version: [...]\n💡 Examiner Tip for Higher Band: [...]"
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[
          {"role": "system", "content": system_prompt},
          {
              "role": "user",
              "content": f"Topic: {topic}\n\nCandidate's Essay: {essay_content}",
          },
      ],
      temperature=0.1,
      max_tokens=2048,
  )
  await message.answer(
      completion.choices[0].message.content,
      reply_markup=get_main_menu(lang, user_id),
  )
  await state.clear()


# ---------------------------------------------------------------------
# 15. GENERAL FALLBACK HANDLER (BARCHA XABARLARGA AI ORQALI JAVOB)
# ---------------------------------------------------------------------
@dp.message()
async def general_message_handler(message: types.Message):
  user_id = message.from_user.id
  user_info = get_user_db(user_id)
  lang = user_info["lang"]
  if not message.text:
    return
  forbidden_words = [
      "porn",
      "sex",
      "porno",
      "18+",
      "intim",
      "xxx",
      "сука",
      "блять",
  ]
  if any(word in message.text.lower() for word in forbidden_words):
    await message.answer(
        "❌ Kechirasiz, taqiqlangan kontentga javob bera olmayman.",
        reply_markup=get_main_menu(lang, user_id),
    )
    return
  update_request_stats()
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a helpful AI assistant. Output strictly in"
                    f" language '{lang}'. No asterisks (**)."
                ),
            },
            {"role": "user", "content": message.text},
        ],
        temperature=0.7,
        max_tokens=1000,
    )
    await message.answer(
        completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
  except Exception:
    await message.answer(
        "⚠️ Iltimos, amal bajarish uchun quyidagi tugmalardan"
        " foydalaning:",
        reply_markup=get_main_menu(lang, user_id),
    )


# ---------------------------------------------------------------------
# 16. BOTNI ISHGA TUSHIRISH (MAIN)
# ---------------------------------------------------------------------
async def main():
  logging.basicConfig(level=logging.INFO, stream=sys.stdout)
  print(
      "Bot rus tili Milliy Sertifikat (UZBMB) bo'limi, takrorlanmas grammatika"
      " testlari va qat'iy C-A+ baholash tizimi bilan muvaffaqiyatli ishga"
      " tushdi..."
  )
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
