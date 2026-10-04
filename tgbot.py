# =====================================================================
# TELEGRAM BOT: IELTS EXAMINER, RUS TILI (C-A+), AI ASSISTANT & SPEAKING
# Created with all user requirements and strict code length formatting
# =====================================================================

import asyncio
import datetime
import json
import logging
import os
import random
import re
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

  # Speaking Part uchun alohida navbatma-navbat holatlar
  speaking_p1 = State()
  speaking_p2 = State()
  speaking_p3 = State()

  # Full Mock test holatlari
  mock_part1 = State()
  mock_part2 = State()
  mock_part3 = State()
  # Yangi: bo'limlar menyusidagi AI va Rus tili bo'limi holatlari
  hub_waiting_for_ai_prompt = State()
  ru_waiting_for_ai_prompt = State()
  ru_waiting_for_word = State()
  ru_waiting_for_essay_topic = State()
  ru_waiting_for_essay_text = State()
  ru_waiting_for_flashcard_input = State()
  ru_speaking = State()


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

  keyboard.append([
      InlineKeyboardButton(
          text=BACK_TEXTS.get(lang, BACK_TEXTS["uz"]), callback_data="hub_back"
      )
  ])
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


# ---------------------------------------------------------------------
# 6. START VA TILNI BOSHQARISH
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
  set_section(user_id, "hub")
  await callback.message.answer(
      wel_texts.get(lang, wel_texts["uz"]),
      reply_markup=get_hub_menu(lang),
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
      text, reply_markup=get_menu_for_user(callback.from_user.id, lang)
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
      reply_markup=get_menu_for_user(user_id, lang),
  )
  await state.clear()


# ---------------------------------------------------------------------
# 8. AI YORDAMCHI (AI ASSISTANT) REJIMI VA 18+ FILTRI
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "mode_ai")
async def ai_assistant_handler(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  await state.set_state(BotStates.waiting_for_ai_prompt)
  texts = {
      "uz": (
          "🤖 **AI Yordamchi rejimi yoqildi!**\n\nMenga istalgan savolingizni"
          " yuboring (dasturlash, fan, tarjima, matn yozish yoki har qanday"
          " mavzu):"
      ),
      "en": "🤖 **AI Assistant mode activated!**\n\nAsk me anything:",
      "ru": "🤖 **AI Помощник активирован!**\n\nСпросите о чем угодно:",
  }
  await callback.message.answer(texts.get(lang, texts["uz"]))
  await callback.answer()


@dp.message(BotStates.waiting_for_ai_prompt, F.text)
async def process_ai_prompt(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  user_query = message.text
  update_request_stats()

  forbidden = [
      "porn",
      "sex",
      "porno",
      "18+",
      "intim",
      "xxx",
      "сука",
      "блять",
      "fast",
  ]
  if any(w in user_query.lower() for w in forbidden):
    await message.answer(
        "❌ Kechirasiz, 18+ yoki taqiqlangan kontentga javob bera olmayman.",
        reply_markup=get_main_menu(lang, user_id),
    )
    await state.clear()
    return

  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a helpful, intelligent AI assistant. Output"
                    f" strictly in language '{lang}'. No asterisks (**). Use"
                    " emojis only at the beginning of lines."
                ),
            },
            {"role": "user", "content": user_query},
        ],
        temperature=0.7,
        max_tokens=1500,
    )
    await message.answer(
        completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
  except Exception:
    await message.answer(
        "❌ AI javob berishda xatolik yuz berdi.",
        reply_markup=get_main_menu(lang, user_id),
    )
  await state.clear()


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
async def mock_receive_part3_and_finish(message: types.Message, state: FSMContext):
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
# 15. YANGI: BO'LIMLAR MENYUSI (RUS TILI / INGLIZ TILI / TARIX / AI)
# ---------------------------------------------------------------------
GROQ_MODEL = "openai/gpt-oss-120b"
WHISPER_MODELS_RU = ["whisper-large-v3", "whisper-large-v3-turbo"]
RU_TZ = datetime.timezone(datetime.timedelta(hours=5))  # Toshkent, UTC+5
RU_DAILY_WORD_LIMIT = 30
RU_DAILY_ESSAY_LIMIT = 5
LANG_NAMES = {
    "uz": "Uzbek (Latin script)",
    "en": "English",
    "ru": "Russian",
}
REASONING_BUDGET = {"low": 500, "medium": 1500, "high": 3500}

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_sections (
    user_id INTEGER PRIMARY KEY,
    section TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS ru_usage (
    user_id INTEGER PRIMARY KEY,
    words_count INTEGER,
    essays_count INTEGER,
    last_reset TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS ru_flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    word TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS ru_challenge (
    user_id INTEGER PRIMARY KEY,
    next_day INTEGER,
    is_active INTEGER,
    last_sent TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS ru_idioms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    day INTEGER,
    idiom TEXT
)
""")
conn.commit()


def today_str():
  return str(datetime.datetime.now(RU_TZ).date())


def get_section(user_id):
  cursor.execute(
      "SELECT section FROM user_sections WHERE user_id = ?", (user_id,)
  )
  row = cursor.fetchone()
  return row[0] if row and row[0] else "en"


def set_section(user_id, section):
  cursor.execute(
      "INSERT OR REPLACE INTO user_sections (user_id, section) VALUES (?, ?)",
      (user_id, section),
  )
  conn.commit()


def ru_get_usage(user_id):
  today = today_str()
  cursor.execute(
      "SELECT words_count, essays_count, last_reset FROM ru_usage WHERE"
      " user_id = ?",
      (user_id,),
  )
  row = cursor.fetchone()
  if not row:
    cursor.execute(
        "INSERT INTO ru_usage (user_id, words_count, essays_count,"
        " last_reset) VALUES (?, 0, 0, ?)",
        (user_id, today),
    )
    conn.commit()
    return {"words_count": 0, "essays_count": 0}
  words, essays, last_reset = row
  if last_reset != today:
    cursor.execute(
        "UPDATE ru_usage SET words_count = 0, essays_count = 0, last_reset ="
        " ? WHERE user_id = ?",
        (today, user_id),
    )
    conn.commit()
    return {"words_count": 0, "essays_count": 0}
  return {"words_count": words or 0, "essays_count": essays or 0}


def ru_add_usage(user_id, field):
  if field not in ("words_count", "essays_count"):
    return
  ru_get_usage(user_id)
  cursor.execute(
      f"UPDATE ru_usage SET {field} = {field} + 1 WHERE user_id = ?",
      (user_id,),
  )
  conn.commit()


# ---------------------------------------------------------------------
# 15.1 UMUMIY YORDAMCHI FUNKSIYALAR (Groq, xabar bo'lish, JSON, filtr)
# ---------------------------------------------------------------------
async def ask_groq(
    messages,
    temperature=0.3,
    max_tokens=1500,
    effort="low",
    json_mode=False,
):
  """Groq'ga asinxron murojaat (bot qotib qolmaydi), xatoda qayta uriniladi.

  gpt-oss modelida 'o'ylash' tokenlari ham max_tokens ichiga kiradi, shuning
  uchun o'ylash uchun alohida zaxira qo'shiladi.
  """

  def _call(with_extras):
    budget = REASONING_BUDGET.get(effort, 500)
    kwargs = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens + budget + (0 if with_extras else 1000),
    }
    if with_extras:
      kwargs["extra_body"] = {"reasoning_effort": effort}
      if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    completion = groq_client.chat.completions.create(**kwargs)
    return completion.choices[0].message.content or ""

  last_error = None
  for attempt in range(3):
    try:
      text = await asyncio.to_thread(_call, attempt < 2)
      if text.strip():
        return text.strip()
    except Exception as e:
      last_error = e
      logging.warning("Groq xatosi (urinish %s): %s", attempt + 1, e)
    await asyncio.sleep(1.5 * (attempt + 1))
  raise RuntimeError(f"Groq javob bermadi: {last_error}")


def split_text(text, limit=3900):
  """Uzun matnni Telegram limiti (4096) ichiga sig'adigan bo'laklarga bo'ladi."""
  text = (text or "").strip()
  if len(text) <= limit:
    return [text] if text else []
  parts = []
  current = ""
  for paragraph in text.split("\n"):
    while len(paragraph) > limit:
      cut = paragraph.rfind(" ", 0, limit)
      if cut <= 0:
        cut = limit
      if current:
        parts.append(current)
        current = ""
      parts.append(paragraph[:cut])
      paragraph = paragraph[cut:].lstrip()
    if current and len(current) + len(paragraph) + 1 > limit:
      parts.append(current)
      current = paragraph
    else:
      current = current + "\n" + paragraph if current else paragraph
  if current:
    parts.append(current)
  return [p for p in parts if p.strip()]


async def send_long(message, text, reply_markup=None):
  chunks = split_text(text)
  if not chunks:
    chunks = ["…"]
  for i, chunk in enumerate(chunks):
    is_last = i == len(chunks) - 1
    await message.answer(chunk, reply_markup=reply_markup if is_last else None)


def extract_json(text):
  """Model javobidan JSON obyektini xavfsiz ajratib oladi."""
  if not text:
    return None
  cleaned = re.sub(r"```(?:json)?", "", text).strip()
  start = cleaned.find("{")
  end = cleaned.rfind("}")
  if start == -1 or end <= start:
    return None
  candidate = cleaned[start : end + 1]
  try:
    return json.loads(candidate)
  except json.JSONDecodeError:
    pass
  candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
  try:
    return json.loads(candidate)
  except json.JSONDecodeError:
    return None


_RU_BAD_RE = re.compile(r"\b(sex|секс|сука|блять|блядь)\b", re.IGNORECASE)


def is_forbidden_text(text):
  low = (text or "").lower()
  if any(s in low for s in ("porn", "порно", "xxx", "18+", "intim", "интим")):
    return True
  return bool(_RU_BAD_RE.search(low))


def count_words(text):
  return len(re.findall(r"\w+(?:-\w+)*", text or "", re.UNICODE))


def cyrillic_ratio(text):
  letters = [c for c in (text or "") if c.isalpha()]
  if not letters:
    return 0.0
  cyr = sum(1 for c in letters if "\u0400" <= c <= "\u04ff")
  return cyr / len(letters)


def make_button(text, data):
  return InlineKeyboardButton(text=text, callback_data=data)


# ---------------------------------------------------------------------
# 15.2 BO'LIMLAR MENYUSI (til tanlangandan keyin chiqadi)
# ---------------------------------------------------------------------
HUB_TEXTS = {
    "uz": {
        "ru": "🇷🇺 Rus tili",
        "en": "🇬🇧 Ingliz tili",
        "history": "📚 Tarix",
        "ai": "🤖 AI",
        "title": "📌 Kerakli bo'limni tanlang:",
    },
    "en": {
        "ru": "🇷🇺 Russian",
        "en": "🇬🇧 English",
        "history": "📚 History",
        "ai": "🤖 AI",
        "title": "📌 Choose a section:",
    },
    "ru": {
        "ru": "🇷🇺 Русский язык",
        "en": "🇬🇧 Английский язык",
        "history": "📚 История",
        "ai": "🤖 AI",
        "title": "📌 Выберите раздел:",
    },
}

BACK_TEXTS = {
    "uz": "⬅️ Bo'limlarga qaytish",
    "en": "⬅️ Back to Sections",
    "ru": "⬅️ К разделам",
}


def get_hub_menu(lang="uz"):
  t = HUB_TEXTS.get(lang, HUB_TEXTS["uz"])
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              make_button(t["ru"], "hub_ru"),
              make_button(t["en"], "hub_en"),
          ],
          [
              make_button(t["history"], "hub_history"),
              make_button(t["ai"], "hub_ai"),
          ],
      ]
  )


RU_BTN = {
    "ai": {
        "uz": "🤖 AI Yordamchi (Hamma narsaga javob)",
        "en": "🤖 AI Assistant (Ask Anything)",
        "ru": "🤖 AI Помощник (Спроси о чем угодно)",
    },
    "word": {
        "uz": "🔍 Rus so'zi / Tarjima va Tahlil",
        "en": "🔍 Russian Word / Translation & Analysis",
        "ru": "🔍 Слово / Перевод и разбор",
    },
    "essay": {
        "uz": "📝 Rus tilida insho tekshirish (C–A+)",
        "en": "📝 Russian Essay Check (C–A+)",
        "ru": "📝 Проверка сочинения (C–A+)",
    },
    "idiom": {
        "uz": "🔥 31 kunlik Rus idiomalari",
        "en": "🔥 31-Day Russian Idiom Challenge",
        "ru": "🔥 31-дневный челлендж фразеологизмов",
    },
    "flash": {
        "uz": "📇 Flashcards (Konstruktor)",
        "en": "📇 Flashcards (Creator)",
        "ru": "📇 Карточки (Конструктор)",
    },
    "speak": {
        "uz": "🎤 Speaking Simulator",
        "en": "🎤 Speaking Simulator",
        "ru": "🎤 Говорение: симулятор",
    },
    "random": {
        "uz": "🎲 Tasodifiy mavzu",
        "en": "🎲 Random Topic",
        "ru": "🎲 Случайная тема",
    },
    "history": {
        "uz": "📚 O'tilgan idiomalar",
        "en": "📚 Learned Idioms",
        "ru": "📚 Изученные идиомы",
    },
    "quiz": {
        "uz": "🧠 Viktorina (Test - Interaktiv)",
        "en": "🧠 Quiz (Interactive)",
        "ru": "🧠 Викторина (Интерактив)",
    },
    "math": {
        "uz": "🧮 Matematik masalalar / misollar",
        "en": "🧮 Math Problems / Examples",
        "ru": "🧮 Мат. задачи / Примеры",
    },
    "suggest": {
        "uz": "💡 Taklif yuborish",
        "en": "💡 Send Suggestion",
        "ru": "💡 Предложение / Отзыв",
    },
    "lang": {
        "uz": "🌐 Tilni o'zgartirish",
        "en": "🌐 Change Language",
        "ru": "🌐 Изменить язык",
    },
}


def get_ru_menu(lang="uz", user_id=None):
  def t(key):
    return RU_BTN[key].get(lang, RU_BTN[key]["uz"])

  keyboard = [
      [make_button(t("ai"), "ru_mode_ai")],
      [make_button(t("word"), "ru_mode_word")],
      [make_button(t("essay"), "ru_mode_essay")],
      [make_button(t("idiom"), "ru_mode_idiom")],
      [
          make_button(t("flash"), "ru_mode_flashcard"),
          make_button(t("speak"), "ru_mode_speaking"),
      ],
      [make_button(t("random"), "ru_mode_random_topic")],
      [
          make_button(t("history"), "ru_mode_history"),
          make_button(t("quiz"), "ru_mode_quiz"),
      ],
      [make_button(t("math"), "ru_mode_math")],
      [
          make_button(t("suggest"), "ru_mode_suggestion"),
          make_button(t("lang"), "change_lang"),
      ],
      [make_button(BACK_TEXTS.get(lang, BACK_TEXTS["uz"]), "hub_back")],
  ]
  if user_id == ADMIN_ID:
    keyboard.append([
        make_button("📊 Admin Statistikasi", "admin_stats"),
        make_button("📢 Broadcast (Xabar tarqatish)", "admin_broadcast"),
    ])
  return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_menu_for_user(user_id, lang):
  """Foydalanuvchi qaysi bo'limda bo'lsa, o'sha menyuni qaytaradi."""
  section = get_section(user_id)
  if section == "ru":
    return get_ru_menu(lang, user_id)
  if section == "hub":
    return get_hub_menu(lang)
  return get_main_menu(lang, user_id)


@dp.callback_query(F.data == "hub_en")
async def hub_open_english(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  await state.clear()
  set_section(user_id, "en")
  texts = {
      "uz": "🇬🇧 Ingliz tili bo'limi.\nKerakli funksiyani tanlang:",
      "en": "🇬🇧 English section.\nChoose a function:",
      "ru": "🇬🇧 Раздел английского языка.\nВыберите функцию:",
  }
  await callback.message.answer(
      texts.get(lang, texts["uz"]), reply_markup=get_main_menu(lang, user_id)
  )
  await callback.answer()


@dp.callback_query(F.data.in_({"hub_ru", "ru_menu"}))
async def hub_open_russian(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  await state.clear()
  set_section(user_id, "ru")
  await callback.message.answer(
      rt(lang, "enter"), reply_markup=get_ru_menu(lang, user_id)
  )
  await callback.answer()


@dp.callback_query(F.data == "hub_back")
async def hub_back_handler(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  await state.clear()
  set_section(user_id, "hub")
  t = HUB_TEXTS.get(lang, HUB_TEXTS["uz"])
  await callback.message.answer(t["title"], reply_markup=get_hub_menu(lang))
  await callback.answer()


@dp.callback_query(F.data == "hub_history")
async def hub_history_handler(callback: types.CallbackQuery, state: FSMContext):
  # TARIX: avvalgi "O'tilgan idiomalar" bilan aynan bir xil (o'zgarmagan).
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  cursor.execute("SELECT word FROM flashcards WHERE user_id = ?", (user_id,))
  words = [row[0] for row in cursor.fetchall()]
  if not words:
    await callback.message.answer(
        "📭 Hozircha saqlangan so'zlaringiz yo'q.",
        reply_markup=get_hub_menu(lang),
    )
  else:
    await send_long(
        callback.message,
        "📚 **Siz kiritgan so'zlar:**\n\n"
        + "\n".join([f"{i+1}. {w}" for i, w in enumerate(words)]),
        reply_markup=get_hub_menu(lang),
    )
  await callback.answer()


@dp.callback_query(F.data == "hub_ai")
async def hub_ai_start(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  await state.set_state(BotStates.hub_waiting_for_ai_prompt)
  texts = {
      "uz": "🤖 AI Yordamchi rejimi yoqildi!\n\nMenga istalgan savolingizni yuboring:",
      "en": "🤖 AI Assistant mode activated!\n\nAsk me anything:",
      "ru": "🤖 AI Помощник активирован!\n\nСпросите о чем угодно:",
  }
  await callback.message.answer(texts.get(lang, texts["uz"]))
  await callback.answer()


async def run_general_ai(message, state, lang, user_id, menu, extra_system=""):
  update_request_stats()
  if is_forbidden_text(message.text):
    await message.answer(rt(lang, "forbidden"), reply_markup=menu)
    await state.clear()
    return
  system = (
      "You are a helpful, intelligent AI assistant. Output strictly in"
      f" {LANG_NAMES.get(lang, 'Uzbek (Latin script)')} unless the user"
      " explicitly asks for another language. Do not use asterisks (**) or"
      " markdown. Use emojis only at the beginning of lines. "
      + extra_system
  )
  try:
    answer = await ask_groq(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": message.text},
        ],
        temperature=0.7,
        max_tokens=1500,
        effort="low",
    )
    await send_long(message, answer, menu)
  except Exception:
    await message.answer(rt(lang, "ai_error"), reply_markup=menu)
  await state.clear()


@dp.message(BotStates.hub_waiting_for_ai_prompt, F.text)
async def hub_ai_process(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  await run_general_ai(message, state, lang, user_id, get_hub_menu(lang))


# ---------------------------------------------------------------------
# 15.3 RUS TILI BO'LIMI MATNLARI (uz / en / ru)
# ---------------------------------------------------------------------
RT = {
    "enter": {
        "uz": "🇷🇺 Rus tili bo'limi.\nKerakli funksiyani tanlang:",
        "en": "🇷🇺 Russian language section.\nChoose a function:",
        "ru": "🇷🇺 Раздел русского языка.\nВыберите функцию:",
    },
    "ai_on": {
        "uz": (
            "🤖 AI Yordamchi yoqildi!\n\nIstalgan savolingizni yuboring (rus"
            " tili, grammatika, tarjima, matn yozish yoki boshqa mavzu):"
        ),
        "en": (
            "🤖 AI Assistant activated!\n\nAsk me anything (Russian language,"
            " grammar, translation, writing or any other topic):"
        ),
        "ru": (
            "🤖 AI Помощник активирован!\n\nСпросите о чем угодно (русский"
            " язык, грамматика, перевод, тексты или любая другая тема):"
        ),
    },
    "ai_error": {
        "uz": "❌ AI javob berishda xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring.",
        "en": "❌ The AI failed to respond. Please try again in a moment.",
        "ru": "❌ AI не смог ответить. Попробуйте ещё раз чуть позже.",
    },
    "forbidden": {
        "uz": "❌ Kechirasiz, 18+ yoki taqiqlangan kontentga javob bera olmayman.",
        "en": "❌ Sorry, I can't respond to 18+ or prohibited content.",
        "ru": "❌ Извините, я не могу отвечать на запросы 18+ или запрещённого содержания.",
    },
    "generic_error": {
        "uz": "❌ Xatolik yuz berdi. Qayta urinib ko'ring.",
        "en": "❌ Something went wrong. Please try again.",
        "ru": "❌ Произошла ошибка. Попробуйте ещё раз.",
    },
    "word_ask": {
        "uz": "✍️ Menga istalgan rus so'zi yoki iborasini yuboring (boshqa tildagi so'zni ham yuborsangiz bo'ladi):",
        "en": "✍️ Send me any Russian word or phrase (a word in another language works too):",
        "ru": "✍️ Отправьте любое русское слово или выражение (можно и слово на другом языке):",
    },
    "word_limit": {
        "uz": "❌ Kunlik so'z limitiga yetdingiz ({limit}/{limit}).",
        "en": "❌ You have reached the daily word limit ({limit}/{limit}).",
        "ru": "❌ Вы достигли дневного лимита слов ({limit}/{limit}).",
    },
    "essay_limit": {
        "uz": "❌ Kunlik insho limitiga yetdingiz ({limit}/{limit}).",
        "en": "❌ You have reached the daily essay limit ({limit}/{limit}).",
        "ru": "❌ Вы достигли дневного лимита сочинений ({limit}/{limit}).",
    },
    "essay_topic_ask": {
        "uz": (
            "📝 Rus tilidagi insho tekshiruvi (C dan A+ gacha)\n\nAvval insho"
            " mavzusini yuboring.\n\nℹ️ Insho rus tilida bo'lishi kerak."
            " Tavsiya etilgan hajm: 150–250 so'z."
        ),
        "en": (
            "📝 Russian essay check (levels C to A+)\n\nFirst, send the essay"
            " topic.\n\nℹ️ The essay must be written in Russian. Recommended"
            " length: 150–250 words."
        ),
        "ru": (
            "📝 Проверка сочинения (уровни от C до A+)\n\nСначала отправьте"
            " тему сочинения.\n\nℹ️ Сочинение должно быть на русском языке."
            " Рекомендуемый объём: 150–250 слов."
        ),
    },
    "essay_topic_ok": {
        "uz": "✅ Mavzu qabul qilindi! Endi insho matnini yuboring (rus tilida, matn ko'rinishida):",
        "en": "✅ Topic accepted! Now send the essay text (in Russian, as text):",
        "ru": "✅ Тема принята! Теперь отправьте текст сочинения (на русском, текстом):",
    },
    "essay_need_text": {
        "uz": "⚠️ Iltimos, insho matnini oddiy matn ko'rinishida yuboring (rasm yoki ovoz emas).",
        "en": "⚠️ Please send the essay as plain text (not a photo or voice message).",
        "ru": "⚠️ Пожалуйста, отправьте сочинение обычным текстом (не фото и не голосовое).",
    },
    "essay_wait": {
        "uz": "⏳ Insho tekshirilmoqda. Bu 20–60 soniya davom etadi...",
        "en": "⏳ Checking your essay. This takes 20–60 seconds...",
        "ru": "⏳ Сочинение проверяется. Это займёт 20–60 секунд...",
    },
    "essay_short": {
        "uz": "❌ Insho juda qisqa ({n} so'z). Baholash uchun kamida {min} so'z kerak (tavsiya: 150–250). Qayta yuboring:",
        "en": "❌ The essay is too short ({n} words). At least {min} words are needed (recommended: 150–250). Send it again:",
        "ru": "❌ Сочинение слишком короткое ({n} слов). Для оценки нужно минимум {min} слов (рекомендуется 150–250). Отправьте снова:",
    },
    "essay_long": {
        "uz": "❌ Insho juda uzun ({n} so'z). Eng ko'pi bilan {max} so'z yuboring:",
        "en": "❌ The essay is too long ({n} words). Please send at most {max} words:",
        "ru": "❌ Сочинение слишком длинное ({n} слов). Отправьте не более {max} слов:",
    },
    "essay_not_ru": {
        "uz": "❌ Insho rus tilida yozilmagan ko'rinadi. Faqat rus tilidagi insho tekshiriladi. Qayta yuboring:",
        "en": "❌ The essay does not appear to be written in Russian. Only Russian essays can be checked. Send it again:",
        "ru": "❌ Похоже, сочинение написано не на русском языке. Проверяются только сочинения на русском. Отправьте снова:",
    },
    "essay_fail": {
        "uz": "❌ Inshoni tekshirishda xatolik yuz berdi. Limitingizdan ayirilmadi, qayta urinib ko'ring.",
        "en": "❌ Could not check the essay. It was not counted against your limit, please try again.",
        "ru": "❌ Не удалось проверить сочинение. Лимит не списан, попробуйте ещё раз.",
    },
    "idiom_start": {
        "uz": "🔥 31 kunlik rus idiomalari challenge boshlandi! 🏆\nHar kuni bitta yangi frazeologizm yuboriladi.",
        "en": "🔥 The 31-day Russian idiom challenge has started! 🏆\nYou will get one new idiom every day.",
        "ru": "🔥 31-дневный челлендж фразеологизмов начался! 🏆\nКаждый день вы будете получать новый оборот.",
    },
    "idiom_active": {
        "uz": "⚠ Challenge allaqachon faol!\n📅 Hozirgi kun: {day} / 31",
        "en": "⚠ The challenge is already active!\n📅 Current day: {day} / 31",
        "ru": "⚠ Челлендж уже активен!\n📅 Текущий день: {day} / 31",
    },
    "idiom_day": {
        "uz": "📅 {day}-kun / 31",
        "en": "📅 Day {day} / 31",
        "ru": "📅 День {day} / 31",
    },
    "idiom_done": {
        "uz": "🎉 31 kunlik rus idiomalari challenge yakunlandi! 🏆",
        "en": "🎉 The 31-day Russian idiom challenge is complete! 🏆",
        "ru": "🎉 31-дневный челлендж фразеологизмов завершён! 🏆",
    },
    "flash_open": {
        "uz": "📇 Flashcards Konstruktori\n\nYodlamoqchi bo'lgan ruscha so'z yoki iborangizni yuboring (har safar qo'shilib boradi):",
        "en": "📇 Flashcards Creator\n\nSend the Russian words or phrases you want to memorize (they add up each time):",
        "ru": "📇 Конструктор карточек\n\nОтправляйте русские слова или выражения, которые хотите выучить (они накапливаются):",
    },
    "flash_added": {
        "uz": "✅ Qabul qilindi! (Bu sessiyada: {count} ta so'z)\nYana so'z yuborishingiz mumkin:",
        "en": "✅ Accepted! (This session: {count} words)\nYou can send more:",
        "ru": "✅ Принято! (В этой сессии: {count} слов)\nМожно отправить ещё:",
    },
    "flash_finish": {
        "uz": "🏁 Yakunlash & Testni boshlash",
        "en": "🏁 Finish & Start the Test",
        "ru": "🏁 Завершить и начать тест",
    },
    "flash_empty": {
        "uz": "❌ Siz hali birorta so'z kiritmadingiz!",
        "en": "❌ You haven't entered any words yet!",
        "ru": "❌ Вы ещё не ввели ни одного слова!",
    },
    "flash_title": {
        "uz": "🧠 Siz kiritgan so'zlar bo'yicha Flashcard Testi:",
        "en": "🧠 Flashcard test on your words:",
        "ru": "🧠 Тест по вашим словам:",
    },
    "hist_empty": {
        "uz": "📭 Hozircha saqlangan idioma va so'zlaringiz yo'q.",
        "en": "📭 You have no saved idioms or words yet.",
        "ru": "📭 Пока нет сохранённых идиом и слов.",
    },
    "hist_idioms": {
        "uz": "📚 O'tilgan idiomalar:",
        "en": "📚 Learned idioms:",
        "ru": "📚 Изученные идиомы:",
    },
    "hist_words": {
        "uz": "📇 Siz kiritgan so'zlar:",
        "en": "📇 Words you added:",
        "ru": "📇 Добавленные вами слова:",
    },
    "quiz_title": {
        "uz": "🧠 Rus tili viktorinasi",
        "en": "🧠 Russian language quiz",
        "ru": "🧠 Викторина по русскому языку",
    },
    "quiz_ok": {
        "uz": "✅ To'g'ri! Siz tanlagan javob ({choice}) to'g'ri chiqdi! 🎉",
        "en": "✅ Correct! Your answer ({choice}) is right! 🎉",
        "ru": "✅ Верно! Ваш ответ ({choice}) правильный! 🎉",
    },
    "quiz_bad": {
        "uz": "❌ Xato! To'g'ri javob: {correct} edi.",
        "en": "❌ Wrong! The correct answer was {correct}.",
        "ru": "❌ Неверно! Правильный ответ: {correct}.",
    },
    "quiz_old": {
        "uz": "⚠️ Bu savol eskirgan yoki allaqachon javob berilgan. Yangi savol oling.",
        "en": "⚠️ This question has expired or was already answered. Get a new one.",
        "ru": "⚠️ Этот вопрос устарел или на него уже ответили. Возьмите новый.",
    },
    "quiz_next": {
        "uz": "➡️ Keyingi savol",
        "en": "➡️ Next question",
        "ru": "➡️ Следующий вопрос",
    },
    "quiz_menu": {
        "uz": "🏠 Menyu",
        "en": "🏠 Menu",
        "ru": "🏠 Меню",
    },
    "random_title": {
        "uz": "🎲 Tasodifiy mavzular (rus tili):",
        "en": "🎲 Random topics (Russian):",
        "ru": "🎲 Случайные темы:",
    },
    "sugg_prompt": {
        "uz": "💡 Botimiz uchun taklif yoki shikoyatlaringizni yozib yuboring:",
        "en": "💡 Write your suggestions or complaints for our bot:",
        "ru": "💡 Напишите свои предложения или жалобы по работе бота:",
    },
    "speak_menu": {
        "uz": (
            "🎤 Rus tilida Speaking Simulator\n\nTayyorgarlik turini"
            " tanlang:\n- Istalgan bitta qism bo'yicha alohida"
            " shug'ullaning\n- Yoki to'liq Full Mock Testni boshlang!\n\n(Ovozli"
            " xabar yoki matn orqali javob berishingiz mumkin)"
        ),
        "en": (
            "🎤 Russian Speaking Simulator\n\nChoose your practice mode:\n- Train"
            " a single part\n- Or start the full Mock Test!\n\n(You can answer"
            " with a voice message or text)"
        ),
        "ru": (
            "🎤 Симулятор устной речи (русский язык)\n\nВыберите режим:\n-"
            " Тренируйте отдельную часть\n- Или начните полный Mock-тест!\n\n(Можно"
            " отвечать голосовым сообщением или текстом)"
        ),
    },
    "speak_p1": {
        "uz": "📌 1-qism (Suhbat)",
        "en": "📌 Part 1 (Interview)",
        "ru": "📌 Часть 1 (Беседа)",
    },
    "speak_p2": {
        "uz": "🧭 2-qism (Monolog kartochka)",
        "en": "🧭 Part 2 (Monologue card)",
        "ru": "🧭 Часть 2 (Монолог)",
    },
    "speak_p3": {
        "uz": "💬 3-qism (Muhokama)",
        "en": "💬 Part 3 (Discussion)",
        "ru": "💬 Часть 3 (Обсуждение)",
    },
    "speak_mock": {
        "uz": "🚀 Full Mock Test (Real imtihon)",
        "en": "🚀 Full Mock Test (Real exam)",
        "ru": "🚀 Полный Mock-тест (как на экзамене)",
    },
    "speak_q": {
        "uz": "{icon} Savol {n}/{total}",
        "en": "{icon} Question {n}/{total}",
        "ru": "{icon} Вопрос {n}/{total}",
    },
    "speak_hint": {
        "uz": "Javobingizni ovozli xabar yoki matn ko'rinishida yuboring:",
        "en": "Send your answer as a voice message or text:",
        "ru": "Отправьте ответ голосовым сообщением или текстом:",
    },
    "speak_p2_hint": {
        "uz": "1 daqiqa o'ylab oling va taxminan 2 daqiqa gapiring, so'ng ovozli xabar yoki matn yuboring:",
        "en": "Take 1 minute to think, speak for about 2 minutes, then send a voice message or text:",
        "ru": "Подумайте 1 минуту, говорите около 2 минут, затем отправьте голосовое сообщение или текст:",
    },
    "speak_ok": {
        "uz": "✅ Javobingiz qabul qilindi!",
        "en": "✅ Your answer was received!",
        "ru": "✅ Ответ принят!",
    },
    "speak_voice_fail": {
        "uz": "⚠️ Ovozni matnga aylantirib bo'lmadi. Iltimos, qayta yuboring yoki matn bilan javob bering.",
        "en": "⚠️ Could not transcribe the voice message. Please resend it or answer in text.",
        "ru": "⚠️ Не удалось распознать голос. Отправьте ещё раз или ответьте текстом.",
    },
    "speak_eval_wait": {
        "uz": "⏳ Javoblaringiz tahlil qilinmoqda...",
        "en": "⏳ Analysing your answers...",
        "ru": "⏳ Анализируем ваши ответы...",
    },
    "speak_eval_title": {
        "uz": "📊 Speaking yakuniy tahlili",
        "en": "📊 Final speaking evaluation",
        "ru": "📊 Итоговая оценка устной речи",
    },
    "speak_eval_note": {
        "uz": "ℹ️ Talaffuz audio emas, matnga aylantirilgan javob asosida taxminiy baholanadi.",
        "en": "ℹ️ Pronunciation is only estimated from the transcript, not from the audio itself.",
        "ru": "ℹ️ Произношение оценивается лишь приблизительно по расшифровке, а не по самому аудио.",
    },
}


def rt(lang, key, **kwargs):
  entry = RT[key]
  text = entry.get(lang) or entry["uz"]
  return text.format(**kwargs) if kwargs else text


# ---------------------------------------------------------------------
# 16. RUS TILI: AI YORDAMCHI VA SO'Z TAHLILI
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "ru_mode_ai")
async def ru_ai_start(callback: types.CallbackQuery, state: FSMContext):
  lang = get_user_db(callback.from_user.id)["lang"]
  await state.set_state(BotStates.ru_waiting_for_ai_prompt)
  await callback.message.answer(rt(lang, "ai_on"))
  await callback.answer()


@dp.message(BotStates.ru_waiting_for_ai_prompt, F.text)
async def ru_ai_process(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  await run_general_ai(
      message,
      state,
      lang,
      user_id,
      get_ru_menu(lang, user_id),
      extra_system=(
          "You are also an expert tutor of the Russian language (grammar,"
          " vocabulary, stress, punctuation, style, translation)."
      ),
  )


@dp.callback_query(F.data == "ru_mode_word")
async def ru_word_start(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  if ru_get_usage(user_id)["words_count"] >= RU_DAILY_WORD_LIMIT:
    await callback.message.answer(
        rt(lang, "word_limit", limit=RU_DAILY_WORD_LIMIT),
        reply_markup=get_ru_menu(lang, user_id),
    )
    await callback.answer()
    return
  await state.set_state(BotStates.ru_waiting_for_word)
  await callback.message.answer(rt(lang, "word_ask"))
  await callback.answer()


@dp.message(BotStates.ru_waiting_for_word, F.text)
async def ru_word_process(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  menu = get_ru_menu(lang, user_id)
  word = message.text.strip()[:200]
  if is_forbidden_text(word):
    await message.answer(rt(lang, "forbidden"), reply_markup=menu)
    await state.clear()
    return
  update_request_stats()
  system = (
      "You are an expert lexicographer and teacher of Russian as a foreign"
      " language. Analyse the given word or phrase for a student preparing"
      " for the Uzbekistan national certificate in Russian. If the input is"
      " not Russian, first give the best Russian equivalent(s), then analyse"
      " the main one. Mark the stressed vowel with a combining acute accent"
      " (U+0301). Cover, each on its own line starting with an emoji:"
      " 1) the word with stress; 2) translation and meaning; 3) part of"
      " speech, gender/number, and for verbs the aspect pair and conjugation"
      " of the present/future; for nouns and adjectives the key case forms;"
      " 4) three example sentences in Russian, each followed by its"
      " translation; 5) synonyms and antonyms; 6) typical mistakes of"
      " Uzbek-speaking learners; 7) CEFR level (A1-C2). Output explanations"
      f" strictly in {LANG_NAMES.get(lang)}. Do not use asterisks (**) or"
      " markdown."
  )
  try:
    answer = await ask_groq(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Word or phrase: {word}"},
        ],
        temperature=0.4,
        max_tokens=1400,
        effort="low",
    )
    ru_add_usage(user_id, "words_count")
    await send_long(message, answer, menu)
  except Exception:
    await message.answer(rt(lang, "ai_error"), reply_markup=menu)
  await state.clear()


# ---------------------------------------------------------------------
# 17. RUS TILI: INSHO TEKSHIRISH (C, C+, B, B+, A, A+)
#     Daraja shkalasi: Bilimni baholash agentligi milliy sertifikat
#     chegaralari (46 / 50 / 55 / 60 / 65 / 70 ball) bo'yicha hisoblanadi.
#     Ballarni AI emas, DASTUR hisoblaydi (AI xatolarni topadi va mezonlar
#     bo'yicha ball beradi, dastur esa xatolar zichligi bo'yicha
#     "shishirib" yuborishni cheklaydi).
# ---------------------------------------------------------------------
RU_LEVELS = [
    (70.0, "A+"),
    (65.0, "A"),
    (60.0, "B+"),
    (55.0, "B"),
    (50.0, "C+"),
    (46.0, "C"),
]
RU_ESSAY_MAX = {
    "content": 25,
    "structure": 15,
    "vocabulary": 15,
    "grammar": 20,
    "orthography": 15,
    "style": 10,
}
# (100 so'zga to'g'ri keladigan xatolar chegarasi, eng ko'p ruxsat etilgan ball)
RU_GRAMMAR_CAP = [(0.5, 20), (1.0, 17), (1.5, 14), (2.5, 10), (3.5, 7), (5.0, 4), (999, 2)]
RU_ORTHO_CAP = [(0.5, 15), (1.0, 13), (2.0, 10), (3.0, 7), (4.5, 5), (6.0, 3), (999, 1)]
RU_VOCAB_CAP = [(0.3, 15), (0.7, 13), (1.5, 10), (2.5, 7), (4.0, 4), (999, 2)]
RU_STYLE_CAP = [(0.3, 10), (0.7, 8), (1.5, 6), (2.5, 4), (999, 2)]
RU_ERROR_CATEGORIES = ["grammar", "spelling", "punctuation", "lexical", "style"]
RU_LEN_REJECT = 60
RU_LEN_MAX = 450
RU_LEN_CAPS = [(100, 54.9), (140, 64.9)]


def density_cap(count, words, table):
  per100 = count * 100.0 / max(words, 1)
  for limit, points in table:
    if per100 <= limit:
      return points
  return table[-1][1]


def score_to_level(score):
  for threshold, name in RU_LEVELS:
    if score >= threshold:
      return name
  return None


def next_level_gap(score):
  for threshold, name in reversed(RU_LEVELS):
    if score < threshold:
      return name, threshold - score
  return None, 0


def fmt_score(value):
  return f"{value:.1f}".rstrip("0").rstrip(".")


def _to_int(value, default=0):
  try:
    return int(round(float(value)))
  except (TypeError, ValueError):
    return default


def compute_essay_result(data, words):
  """AI bergan JSON'dan yakuniy ball va darajani hisoblaydi."""
  raw = data.get("scores")
  if not isinstance(raw, dict) or any(k not in raw for k in RU_ESSAY_MAX):
    return None
  counts_raw = data.get("counts") if isinstance(data.get("counts"), dict) else {}
  errors = data.get("errors") if isinstance(data.get("errors"), list) else []
  errors = [e for e in errors if isinstance(e, dict)]
  listed = {cat: 0 for cat in RU_ERROR_CATEGORIES}
  for e in errors:
    cat = str(e.get("category", "")).strip().lower()
    if cat in listed:
      listed[cat] += 1
  counts = {
      cat: max(_to_int(counts_raw.get(cat)), listed[cat])
      for cat in RU_ERROR_CATEGORIES
  }
  scores = {
      key: max(0, min(mx, _to_int(raw.get(key))))
      for key, mx in RU_ESSAY_MAX.items()
  }
  on_topic = str(data.get("on_topic", "full")).strip().lower()
  if on_topic == "partial":
    scores["content"] = min(scores["content"], 14)
  elif on_topic == "off":
    scores["content"] = min(scores["content"], 4)
  scores["grammar"] = min(
      scores["grammar"], density_cap(counts["grammar"], words, RU_GRAMMAR_CAP)
  )
  scores["orthography"] = min(
      scores["orthography"],
      density_cap(
          counts["spelling"] + counts["punctuation"], words, RU_ORTHO_CAP
      ),
  )
  scores["vocabulary"] = min(
      scores["vocabulary"], density_cap(counts["lexical"], words, RU_VOCAB_CAP)
  )
  scores["style"] = min(
      scores["style"], density_cap(counts["style"], words, RU_STYLE_CAP)
  )
  total = float(sum(scores.values()))
  cap = None
  cap_reason = None
  for limit, cap_value in RU_LEN_CAPS:
    if words < limit:
      cap, cap_reason = cap_value, "length"
      break
  if on_topic == "off" and (cap is None or cap > 49.9):
    cap, cap_reason = 49.9, "off_topic"
  applied = None
  if cap is not None and total > cap:
    total = cap
    applied = (cap_reason, cap)
  return {
      "scores": scores,
      "counts": counts,
      "errors": errors,
      "total": total,
      "level": score_to_level(total),
      "applied_cap": applied,
  }


def build_essay_system_prompt(lang):
  return (
      "You are a senior examiner of the Russian language (native speaker, 20"
      " years of experience) grading a written essay (сочинение / эссе) for"
      " the Uzbekistan national certificate system. The program converts your"
      " numeric scores into the levels C, C+, B, B+, A, A+, so you NEVER write"
      " a level letter yourself.\n\n"
      "Be STRICT, objective and consistent. Never inflate scores. Calibration"
      " for the total (0-100): 85-100 near-flawless native-like essay (very"
      " rare); 70-84 strong essay with only minor mistakes; 60-69 good essay"
      " with several mistakes that do not block understanding; 50-59"
      " acceptable but with frequent mistakes and simple language; 46-49 weak"
      " but understandable; below 46 many errors, shallow or off-topic.\n\n"
      "CRITERIA (integer scores):\n"
      "- content (0-25): 21-25 topic fully covered, clear thesis, 2+ relevant"
      " arguments with concrete examples; 14-20 topic covered but arguments"
      " thin or generic; 7-13 superficial or partly off-topic; 0-6 mostly"
      " off-topic.\n"
      "- structure (0-15): 13-15 clear introduction, body, conclusion, good"
      " paragraphing and logical connectors; 9-12 present but weak links;"
      " 4-8 chaotic; 0-3 none.\n"
      "- vocabulary (0-15): 13-15 rich, precise, varied; 9-12 adequate but"
      " repetitive; 4-8 limited, wrong word choice; 0-3 very poor.\n"
      "- grammar (0-20): cases, agreement, verb forms and aspect, government"
      " of prepositions, word order, sentence variety. 17-20 almost no"
      " errors; 12-16 some errors; 6-11 frequent; 0-5 systematic.\n"
      "- orthography (0-15): spelling AND punctuation. 13-15 at most 1-2"
      " errors; 9-12 some; 4-8 many; 0-3 very many.\n"
      "- style (0-10): consistent neutral/academic register, no speech"
      " errors (речевые ошибки), clichés or tautology. 9-10 excellent; 6-8"
      " mostly fine; 3-5 mixed colloquial; 0-2 inappropriate.\n\n"
      "ERROR ANALYSIS RULES:\n"
      "- Find ALL real errors. List the 25 most significant in 'errors'."
      " Quote the wrong fragment EXACTLY as the student wrote it, keep it"
      " short (a word or a phrase) and give the corrected fragment in"
      " 'right'.\n"
      "- category must be one of: grammar, spelling, punctuation, lexical,"
      " style.\n"
      "- 'counts' must hold the TOTAL number of errors per category in the"
      " WHOLE essay, not only the listed ones.\n"
      "- Never invent errors and never flag correct text. Do not penalize"
      " е/ё interchange or acceptable punctuation variants.\n"
      "- 'on_topic': 'full', 'partial' or 'off'. 'is_russian': false if the"
      " text is mostly not Russian (for example Uzbek in Cyrillic or Latin).\n"
      "- 'corrected_essay': the full essay with every error fixed, changing"
      " as little as possible and keeping the student's ideas.\n\n"
      "OUTPUT: valid JSON only (no markdown fences, no comments) with exactly"
      " this structure:\n"
      '{"is_russian": true, "on_topic": "full", "scores": {"content": 0,'
      ' "structure": 0, "vocabulary": 0, "grammar": 0, "orthography": 0,'
      ' "style": 0}, "counts": {"grammar": 0, "spelling": 0, "punctuation":'
      ' 0, "lexical": 0, "style": 0}, "errors": [{"category": "grammar",'
      ' "wrong": "", "right": "", "explanation": ""}], "strengths": ["",'
      ' ""], "weaknesses": ["", ""], "corrected_essay": "", "tips": ["",'
      ' "", ""]}\n'
      "Fields 'wrong', 'right' and 'corrected_essay' stay in Russian. Write"
      " 'explanation', 'strengths', 'weaknesses' and 'tips' strictly in"
      f" {LANG_NAMES.get(lang)}. Give 2-3 strengths, 2-3 weaknesses and 3"
      " concrete tips. Keep every explanation to one short sentence."
  )


async def ru_grade_essay(topic, essay, lang, words):
  """(data, result) qaytaradi; 'not_ru' yoki (None, None) ham mumkin."""
  system = build_essay_system_prompt(lang)
  user = f"TOPIC:\n{topic}\n\nSTUDENT ESSAY ({words} words):\n{essay}"
  for _ in range(2):
    raw = await ask_groq(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=min(9000, 2500 + words * 6),
        effort="medium",
        json_mode=True,
    )
    data = extract_json(raw)
    if not isinstance(data, dict):
      continue
    if data.get("is_russian") is False:
      return "not_ru", None
    result = compute_essay_result(data, words)
    if result:
      return data, result
  return None, None


async def ru_grade_essay_plain(topic, essay, lang):
  """JSON ishlamasa — oddiy matnli zaxira tekshiruv."""
  system = (
      "You are a strict senior examiner of the Russian language grading an"
      " essay for the Uzbekistan national certificate. Use ONLY these levels:"
      " C, C+, B, B+, A, A+ (A+ = 70 points or more out of 100, A 65, B+ 60,"
      " B 55, C+ 50, C 46). If the essay is below level C, write 'below C'."
      " Give: the level with a score out of 100, scores for content,"
      " structure, vocabulary, grammar, spelling and punctuation, the main"
      " mistakes with corrections, a corrected version and 3 tips. Start"
      " every line with an emoji. Do not use asterisks (**). Output"
      f" explanations in {LANG_NAMES.get(lang)}."
  )
  return await ask_groq(
      [
          {"role": "system", "content": system},
          {"role": "user", "content": f"TOPIC:\n{topic}\n\nESSAY:\n{essay}"},
      ],
      temperature=0.1,
      max_tokens=2500,
      effort="medium",
  )


ESSAY_T = {
    "uz": {
        "result": "🎓 Natija: {level} ({score}/100)",
        "below_c": "C dan past",
        "scale": "📌 Milliy sertifikat shkalasi bo'yicha taxminiy daraja (A+ ≥70, A ≥65, B+ ≥60, B ≥55, C+ ≥50, C ≥46)",
        "next": "🎯 Keyingi daraja ({level}) uchun yana {gap} ball kerak.",
        "top": "🏆 Bu eng yuqori daraja!",
        "criteria": "📊 Mezonlar:",
        "content": "Mazmun va mavzu",
        "structure": "Struktura va mantiq",
        "vocabulary": "Leksika",
        "grammar": "Grammatika",
        "orthography": "Imlo va punktuatsiya",
        "style": "Uslub",
        "words": "🔢 So'z soni: {n}",
        "counts": "🧮 Xatolar: grammatika {grammar}, imlo {spelling}, punktuatsiya {punctuation}, leksika {lexical}, uslub {style}",
        "weakest": "🎯 Eng zaif mezonlar: {items}",
        "strengths": "✅ Kuchli tomonlar:",
        "weaknesses": "⚠️ Zaif tomonlar:",
        "errors": "❌ Xatolar tahlili (birinchi {shown} ta, jami {total} ta):",
        "no_errors": "🎉 Sezilarli xato topilmadi!",
        "grammar_c": "Grammatika",
        "spelling_c": "Imlo",
        "punctuation_c": "Punktuatsiya",
        "lexical_c": "Leksika",
        "style_c": "Uslub",
        "corrected": "📝 Tuzatilgan variant (faqat zarur tuzatishlar):",
        "tips": "💡 Maslahatlar:",
        "cap_length": "⚠️ Hajm cheklovi: {n} so'z yozilgani uchun ball {cap} dan oshmaydi (tavsiya: 150–250 so'z).",
        "cap_off": "⚠️ Insho mavzuga mos kelmagani uchun ball {cap} dan oshmaydi.",
        "disclaimer": "ℹ️ Bu AI tomonidan berilgan taxminiy baho, rasmiy milliy sertifikat natijasi emas.",
    },
    "en": {
        "result": "🎓 Result: {level} ({score}/100)",
        "below_c": "below C",
        "scale": "📌 Estimated level on the national certificate scale (A+ ≥70, A ≥65, B+ ≥60, B ≥55, C+ ≥50, C ≥46)",
        "next": "🎯 You need {gap} more points for the next level ({level}).",
        "top": "🏆 This is the highest level!",
        "criteria": "📊 Criteria:",
        "content": "Content and topic",
        "structure": "Structure and logic",
        "vocabulary": "Vocabulary",
        "grammar": "Grammar",
        "orthography": "Spelling and punctuation",
        "style": "Style",
        "words": "🔢 Word count: {n}",
        "counts": "🧮 Errors: grammar {grammar}, spelling {spelling}, punctuation {punctuation}, lexical {lexical}, style {style}",
        "weakest": "🎯 Weakest criteria: {items}",
        "strengths": "✅ Strengths:",
        "weaknesses": "⚠️ Weaknesses:",
        "errors": "❌ Error analysis (first {shown} of {total}):",
        "no_errors": "🎉 No significant errors found!",
        "grammar_c": "Grammar",
        "spelling_c": "Spelling",
        "punctuation_c": "Punctuation",
        "lexical_c": "Vocabulary",
        "style_c": "Style",
        "corrected": "📝 Corrected version (necessary fixes only):",
        "tips": "💡 Tips:",
        "cap_length": "⚠️ Length limit: with only {n} words the score cannot exceed {cap} (recommended: 150–250 words).",
        "cap_off": "⚠️ The essay does not match the topic, so the score cannot exceed {cap}.",
        "disclaimer": "ℹ️ This is an AI estimate, not an official national certificate result.",
    },
    "ru": {
        "result": "🎓 Результат: {level} ({score}/100)",
        "below_c": "ниже C",
        "scale": "📌 Ориентировочный уровень по шкале национального сертификата (A+ ≥70, A ≥65, B+ ≥60, B ≥55, C+ ≥50, C ≥46)",
        "next": "🎯 До следующего уровня ({level}) не хватает {gap} баллов.",
        "top": "🏆 Это высший уровень!",
        "criteria": "📊 Критерии:",
        "content": "Содержание и тема",
        "structure": "Композиция и логика",
        "vocabulary": "Лексика",
        "grammar": "Грамматика",
        "orthography": "Орфография и пунктуация",
        "style": "Стиль",
        "words": "🔢 Количество слов: {n}",
        "counts": "🧮 Ошибки: грамматические {grammar}, орфографические {spelling}, пунктуационные {punctuation}, лексические {lexical}, стилистические {style}",
        "weakest": "🎯 Самые слабые критерии: {items}",
        "strengths": "✅ Сильные стороны:",
        "weaknesses": "⚠️ Слабые стороны:",
        "errors": "❌ Разбор ошибок (первые {shown} из {total}):",
        "no_errors": "🎉 Существенных ошибок не найдено!",
        "grammar_c": "Грамматика",
        "spelling_c": "Орфография",
        "punctuation_c": "Пунктуация",
        "lexical_c": "Лексика",
        "style_c": "Стиль",
        "corrected": "📝 Исправленный вариант (только необходимые правки):",
        "tips": "💡 Советы:",
        "cap_length": "⚠️ Ограничение по объёму: при {n} словах балл не может превышать {cap} (рекомендуется 150–250 слов).",
        "cap_off": "⚠️ Сочинение не соответствует теме, поэтому балл не может превышать {cap}.",
        "disclaimer": "ℹ️ Это приблизительная оценка ИИ, а не официальный результат национального сертификата.",
    },
}


def make_bar(score, maximum):
  filled = int(round(10 * score / maximum)) if maximum else 0
  filled = max(0, min(10, filled))
  return "█" * filled + "░" * (10 - filled)


def _clean_list(value, limit=4):
  if not isinstance(value, list):
    return []
  items = [str(v).strip() for v in value if str(v).strip()]
  return items[:limit]


def build_essay_report(lang, data, result, words):
  t = ESSAY_T.get(lang, ESSAY_T["uz"])
  total = result["total"]
  level = result["level"] or t["below_c"]
  lines = [t["result"].format(level=level, score=fmt_score(total)), t["scale"]]
  next_name, gap = next_level_gap(total)
  if result["level"] is None:
    lines.append(t["next"].format(level="C", gap=fmt_score(46 - total)))
  elif next_name is None:
    lines.append(t["top"])
  else:
    lines.append(t["next"].format(level=next_name, gap=fmt_score(gap)))
  if result["applied_cap"]:
    reason, cap = result["applied_cap"]
    key = "cap_length" if reason == "length" else "cap_off"
    lines.append(t[key].format(n=words, cap=fmt_score(cap)))
  lines += ["", t["criteria"]]
  scores = result["scores"]
  for key, maximum in RU_ESSAY_MAX.items():
    lines.append(
        f"▫️ {t[key]}: {make_bar(scores[key], maximum)} {scores[key]}/{maximum}"
    )
  weakest = sorted(
      RU_ESSAY_MAX, key=lambda k: scores[k] / RU_ESSAY_MAX[k]
  )[:2]
  weak_text = ", ".join(
      f"{t[k]} ({scores[k]}/{RU_ESSAY_MAX[k]})"
      for k in weakest
      if scores[k] / RU_ESSAY_MAX[k] < 0.8
  )
  lines += ["", t["words"].format(n=words), t["counts"].format(**result["counts"])]
  if weak_text:
    lines.append(t["weakest"].format(items=weak_text))
  strengths = _clean_list(data.get("strengths"), 3)
  weaknesses = _clean_list(data.get("weaknesses"), 3)
  if strengths:
    lines += ["", t["strengths"]] + [f"✔️ {s}" for s in strengths]
  if weaknesses:
    lines += ["", t["weaknesses"]] + [f"➖ {w}" for w in weaknesses]
  errors = result["errors"]
  total_errors = max(sum(result["counts"].values()), len(errors))
  lines.append("")
  if errors:
    shown = errors[:12]
    lines.append(t["errors"].format(shown=len(shown), total=total_errors))
    for i, e in enumerate(shown, 1):
      cat = str(e.get("category", "")).strip().lower()
      cat_name = t.get(f"{cat}_c", cat)
      wrong = str(e.get("wrong", "")).strip()
      right = str(e.get("right", "")).strip()
      lines.append(f"❌ {i}. [{cat_name}] «{wrong}» → «{right}»")
      expl = str(e.get("explanation", "")).strip()
      if expl:
        lines.append(f"💬 {expl}")
  elif total_errors == 0:
    lines.append(t["no_errors"])
  corrected = str(data.get("corrected_essay", "")).strip()
  if corrected:
    lines += ["", t["corrected"], corrected]
  tips = _clean_list(data.get("tips"), 4)
  if tips:
    lines += ["", t["tips"]] + [f"🔸 {tip}" for tip in tips]
  lines += ["", t["disclaimer"]]
  return "\n".join(lines)


@dp.callback_query(F.data == "ru_mode_essay")
async def ru_essay_start(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  if ru_get_usage(user_id)["essays_count"] >= RU_DAILY_ESSAY_LIMIT:
    await callback.message.answer(
        rt(lang, "essay_limit", limit=RU_DAILY_ESSAY_LIMIT),
        reply_markup=get_ru_menu(lang, user_id),
    )
    await callback.answer()
    return
  await state.set_state(BotStates.ru_waiting_for_essay_topic)
  await callback.message.answer(rt(lang, "essay_topic_ask"))
  await callback.answer()


@dp.message(BotStates.ru_waiting_for_essay_topic, F.text)
async def ru_essay_topic(message: types.Message, state: FSMContext):
  lang = get_user_db(message.from_user.id)["lang"]
  await state.update_data(essay_topic=message.text.strip()[:500])
  await state.set_state(BotStates.ru_waiting_for_essay_text)
  await message.answer(rt(lang, "essay_topic_ok"))


@dp.message(BotStates.ru_waiting_for_essay_topic)
async def ru_essay_topic_not_text(message: types.Message, state: FSMContext):
  lang = get_user_db(message.from_user.id)["lang"]
  await message.answer(rt(lang, "essay_need_text"))


@dp.message(BotStates.ru_waiting_for_essay_text, F.text)
async def ru_essay_submit(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  menu = get_ru_menu(lang, user_id)
  essay = message.text.strip()
  words = count_words(essay)
  if words < RU_LEN_REJECT:
    await message.answer(rt(lang, "essay_short", n=words, min=RU_LEN_REJECT))
    return
  if words > RU_LEN_MAX:
    await message.answer(rt(lang, "essay_long", n=words, max=RU_LEN_MAX))
    return
  if cyrillic_ratio(essay) < 0.7:
    await message.answer(rt(lang, "essay_not_ru"))
    return
  data_state = await state.get_data()
  topic = data_state.get("essay_topic", "Free topic")
  wait_msg = await message.answer(rt(lang, "essay_wait"))
  update_request_stats()
  report = None
  try:
    data, result = await ru_grade_essay(topic, essay, lang, words)
    if data == "not_ru":
      await message.answer(rt(lang, "essay_not_ru"))
      try:
        await wait_msg.delete()
      except Exception:
        pass
      return
    if data is not None and result is not None:
      report = build_essay_report(lang, data, result, words)
    else:
      report = await ru_grade_essay_plain(topic, essay, lang)
      report += "\n\n" + ESSAY_T.get(lang, ESSAY_T["uz"])["disclaimer"]
  except Exception as e:
    logging.warning("Insho tekshirish xatosi: %s", e)
  try:
    await wait_msg.delete()
  except Exception:
    pass
  if not report:
    await message.answer(rt(lang, "essay_fail"), reply_markup=menu)
    await state.clear()
    return
  ru_add_usage(user_id, "essays_count")
  await send_long(message, report, menu)
  await state.clear()


@dp.message(BotStates.ru_waiting_for_essay_text)
async def ru_essay_text_not_text(message: types.Message, state: FSMContext):
  lang = get_user_db(message.from_user.id)["lang"]
  await message.answer(rt(lang, "essay_need_text"))


# ---------------------------------------------------------------------
# 18. RUS TILI: 31 KUNLIK IDIOMA (FRAZEOLOGIZM) CHALLENGE
#     Eslatma: kunlik yuborish bot qayta ishga tushsa ham davom etadi
#     (ma'lumotlar bazasida saqlanadi va har 10 daqiqada tekshiriladi).
# ---------------------------------------------------------------------
ru_background_tasks = set()


def spawn_task(coro):
  task = asyncio.create_task(coro)
  ru_background_tasks.add(task)
  task.add_done_callback(ru_background_tasks.discard)
  return task


def ru_get_challenge(user_id):
  cursor.execute(
      "SELECT next_day, is_active, last_sent FROM ru_challenge WHERE user_id"
      " = ?",
      (user_id,),
  )
  return cursor.fetchone()


def split_idiom_line(text):
  idiom = ""
  rest = []
  for line in text.strip().split("\n"):
    if not idiom and line.strip().upper().startswith("IDIOM:"):
      idiom = line.split(":", 1)[1].strip()
    else:
      rest.append(line)
  return idiom, "\n".join(rest).strip()


async def ru_send_daily_idiom(user_id):
  row = ru_get_challenge(user_id)
  if not row or not row[1]:
    return False
  day = row[0]
  lang = get_user_db(user_id)["lang"]
  cursor.execute(
      "SELECT idiom FROM ru_idioms WHERE user_id = ? ORDER BY id DESC LIMIT"
      " 60",
      (user_id,),
  )
  used = [r[0] for r in cursor.fetchall() if r[0]]
  level = "B1" if day <= 10 else ("B2" if day <= 21 else "C1")
  system = (
      "You are an expert teacher of Russian as a foreign language preparing"
      " students for the Uzbekistan national certificate. Give ONE Russian"
      f" phraseological unit (идиома / фразеологизм), level {level}, for day"
      f" {day} of 31. It must NOT be any of these already used ones:"
      f" {'; '.join(used) if used else 'none'}.\n"
      "The FIRST line must be exactly: IDIOM: <the idiom only>\n"
      "Then, each on its own line starting with an emoji: meaning; literal"
      " translation; where and in what register it is used; two example"
      " sentences in Russian, each followed by its translation; a synonym or"
      " similar expression; one common mistake of learners. Write"
      f" explanations in {LANG_NAMES.get(lang)}. Do not use asterisks (**)."
  )
  try:
    raw = await ask_groq(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Day {day}"},
        ],
        temperature=0.8,
        max_tokens=900,
        effort="low",
    )
  except Exception as e:
    logging.warning("Idioma yaratishda xato: %s", e)
    return False
  update_request_stats()
  idiom, body = split_idiom_line(raw)
  text = rt(lang, "idiom_day", day=day) + "\n\n" + body
  if day >= 31:
    text += "\n\n" + rt(lang, "idiom_done")
  try:
    for chunk in split_text(text):
      await bot.send_message(user_id, chunk)
  except Exception as e:
    err = str(e).lower()
    if "blocked" in err or "deactivated" in err or "chat not found" in err:
      cursor.execute(
          "UPDATE ru_challenge SET is_active = 0 WHERE user_id = ?", (user_id,)
      )
      conn.commit()
    logging.warning("Idioma yuborishda xato (%s): %s", user_id, e)
    return False
  cursor.execute(
      "INSERT INTO ru_idioms (user_id, day, idiom) VALUES (?, ?, ?)",
      (user_id, day, idiom or f"#{day}"),
  )
  cursor.execute(
      "UPDATE ru_challenge SET next_day = ?, is_active = ?, last_sent = ?"
      " WHERE user_id = ?",
      (day + 1, 0 if day >= 31 else 1, today_str(), user_id),
  )
  conn.commit()
  return True


async def ru_challenge_scheduler():
  """Har 10 daqiqada: bugun hali idioma olmagan faol foydalanuvchilarga yuboradi."""
  while True:
    try:
      now = datetime.datetime.now(RU_TZ)
      if now.hour >= 8:
        cursor.execute(
            "SELECT user_id FROM ru_challenge WHERE is_active = 1 AND"
            " (last_sent IS NULL OR last_sent != ?)",
            (today_str(),),
        )
        for (uid,) in cursor.fetchall():
          await ru_send_daily_idiom(uid)
          await asyncio.sleep(0.5)
    except Exception as e:
      logging.warning("Scheduler xatosi: %s", e)
    await asyncio.sleep(600)


@dp.callback_query(F.data == "ru_mode_idiom")
async def ru_idiom_start(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  row = ru_get_challenge(user_id)
  if row and row[1]:
    await callback.message.answer(
        rt(lang, "idiom_active", day=max(row[0] - 1, 1))
    )
  else:
    cursor.execute(
        "INSERT OR REPLACE INTO ru_challenge (user_id, next_day, is_active,"
        " last_sent) VALUES (?, 1, 1, '')",
        (user_id,),
    )
    conn.commit()
    await callback.message.answer(rt(lang, "idiom_start"))
    spawn_task(ru_send_daily_idiom(user_id))
  await callback.answer()


# ---------------------------------------------------------------------
# 19. RUS TILI: TARIX (O'TILGAN IDIOMALAR VA SO'ZLAR)
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "ru_mode_history")
async def ru_history_handler(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  menu = get_ru_menu(lang, user_id)
  cursor.execute(
      "SELECT day, idiom FROM ru_idioms WHERE user_id = ? ORDER BY id",
      (user_id,),
  )
  idioms = cursor.fetchall()
  cursor.execute(
      "SELECT word FROM ru_flashcards WHERE user_id = ? ORDER BY id DESC"
      " LIMIT 100",
      (user_id,),
  )
  words = [r[0] for r in cursor.fetchall()]
  if not idioms and not words:
    await callback.message.answer(rt(lang, "hist_empty"), reply_markup=menu)
    await callback.answer()
    return
  parts = []
  if idioms:
    parts.append(rt(lang, "hist_idioms"))
    parts += [f"{d}. {i}" for d, i in idioms]
  if words:
    if parts:
      parts.append("")
    parts.append(rt(lang, "hist_words"))
    parts += [f"{n+1}. {w}" for n, w in enumerate(words)]
  await send_long(callback.message, "\n".join(parts), menu)
  await callback.answer()


# ---------------------------------------------------------------------
# 20. RUS TILI: FLASHCARDS KONSTRUKTORI
# ---------------------------------------------------------------------
def ru_flash_markup(lang):
  return InlineKeyboardMarkup(
      inline_keyboard=[[make_button(rt(lang, "flash_finish"), "ru_fc_finish")]]
  )


@dp.callback_query(F.data == "ru_mode_flashcard")
async def ru_flash_open(callback: types.CallbackQuery, state: FSMContext):
  lang = get_user_db(callback.from_user.id)["lang"]
  await state.set_state(BotStates.ru_waiting_for_flashcard_input)
  await state.update_data(fc_words=[])
  await callback.message.answer(
      rt(lang, "flash_open"), reply_markup=ru_flash_markup(lang)
  )
  await callback.answer()


@dp.message(BotStates.ru_waiting_for_flashcard_input, F.text)
async def ru_flash_add(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  word = message.text.strip()[:100]
  cursor.execute(
      "INSERT INTO ru_flashcards (user_id, word) VALUES (?, ?)", (user_id, word)
  )
  conn.commit()
  data = await state.get_data()
  words = list(data.get("fc_words", []))
  words.append(word)
  await state.update_data(fc_words=words)
  await message.answer(
      rt(lang, "flash_added", count=len(words)),
      reply_markup=ru_flash_markup(lang),
  )


@dp.callback_query(F.data == "ru_fc_finish")
async def ru_flash_finish(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  menu = get_ru_menu(lang, user_id)
  await callback.answer()
  data = await state.get_data()
  words = list(data.get("fc_words", []))
  await state.clear()
  if not words:
    cursor.execute(
        "SELECT word FROM ru_flashcards WHERE user_id = ? ORDER BY id DESC"
        " LIMIT 15",
        (user_id,),
    )
    words = [r[0] for r in cursor.fetchall()]
  if not words:
    await callback.message.answer(rt(lang, "flash_empty"), reply_markup=menu)
    return
  update_request_stats()
  system = (
      "You are a teacher of Russian as a foreign language. Create an"
      " interactive vocabulary test (up to 10 questions) from the given"
      " Russian words: mix translation questions, choosing the correct form,"
      " and fill-in-the-blank sentences. Put the answer key with short"
      " explanations at the very end. Write instructions and explanations"
      f" in {LANG_NAMES.get(lang)}. Do not use asterisks (**). Start lines"
      " with emojis only."
  )
  try:
    answer = await ask_groq(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": "Words: " + ", ".join(words)},
        ],
        temperature=0.7,
        max_tokens=1800,
        effort="low",
    )
    await send_long(callback.message, rt(lang, "flash_title") + "\n\n" + answer, menu)
  except Exception:
    await callback.message.answer(rt(lang, "generic_error"), reply_markup=menu)


# ---------------------------------------------------------------------
# 21. RUS TILI: INTERAKTIV VIKTORINA (A, B, C, D TUGMALARI)
# ---------------------------------------------------------------------
RU_QUIZ_TOPICS = [
    "ударение (орфоэпия)",
    "паронимы",
    "фразеологизмы",
    "падежные окончания существительных",
    "спряжение глаголов и вид глагола",
    "причастия и деепричастия",
    "правописание Н и НН",
    "слитное и раздельное написание НЕ",
    "пунктуация в сложных предложениях",
    "лексическое значение слова",
    "синонимы и антонимы",
    "словообразование",
    "числительные",
    "предлоги и управление",
    "употребление местоимений",
    "стили и типы речи",
]


def ru_parse_quiz(text):
  data = extract_json(text)
  if not isinstance(data, dict):
    return None
  options = data.get("options")
  if isinstance(options, list) and len(options) == 4:
    options = dict(zip("ABCD", options))
  if not isinstance(options, dict):
    return None
  options = {str(k).strip().upper()[:1]: str(v).strip() for k, v in options.items()}
  correct = str(data.get("correct", "")).strip().upper()[:1]
  question = str(data.get("question", "")).strip()
  if set(options.keys()) != set("ABCD") or correct not in options or not question:
    return None
  return {
      "question": question,
      "options": options,
      "correct": correct,
      "explanation": str(data.get("explanation", "")).strip(),
  }


async def ru_make_quiz(lang):
  topic = random.choice(RU_QUIZ_TOPICS)
  system = (
      "You write multiple-choice questions on the Russian language at levels"
      " B1-C1 in the style of the Uzbekistan national certificate. Topic:"
      f" {topic}. Exactly ONE option is correct and the three distractors are"
      " plausible. Output valid JSON only: {\"question\": \"...\","
      " \"options\": {\"A\": \"...\", \"B\": \"...\", \"C\": \"...\","
      " \"D\": \"...\"}, \"correct\": \"A\", \"explanation\": \"...\"}. The"
      " question and options are in Russian; the explanation (the rule, one"
      f" or two sentences) is in {LANG_NAMES.get(lang)}. Place the correct"
      " answer at a random position. No asterisks."
  )
  for _ in range(3):
    raw = await ask_groq(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Random seed: {random.randint(1, 10**6)}"},
        ],
        temperature=0.9,
        max_tokens=700,
        effort="low",
        json_mode=True,
    )
    quiz = ru_parse_quiz(raw)
    if quiz:
      return quiz
  return None


@dp.callback_query(F.data == "ru_mode_quiz")
async def ru_quiz_start(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  await callback.answer()
  update_request_stats()
  try:
    quiz = await ru_make_quiz(lang)
  except Exception:
    quiz = None
  if not quiz:
    await callback.message.answer(
        rt(lang, "generic_error"), reply_markup=get_ru_menu(lang, user_id)
    )
    return
  await state.update_data(
      ru_quiz={"correct": quiz["correct"], "explanation": quiz["explanation"]}
  )
  options_text = "\n".join(f"{k}) {v}" for k, v in sorted(quiz["options"].items()))
  markup = InlineKeyboardMarkup(
      inline_keyboard=[[make_button(c, f"ru_qz_{c}") for c in "ABCD"]]
  )
  await callback.message.answer(
      f"{rt(lang, 'quiz_title')}\n\n{quiz['question']}\n\n{options_text}",
      reply_markup=markup,
  )


@dp.callback_query(F.data.startswith("ru_qz_"))
async def ru_quiz_answer(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  choice = callback.data.split("_")[2]
  data = await state.get_data()
  quiz = data.get("ru_quiz")
  await callback.answer()
  if not quiz:
    await callback.message.answer(rt(lang, "quiz_old"))
    return
  await state.update_data(ru_quiz=None)
  try:
    await callback.message.edit_reply_markup(reply_markup=None)
  except Exception:
    pass
  if choice == quiz["correct"]:
    text = rt(lang, "quiz_ok", choice=choice)
  else:
    text = rt(lang, "quiz_bad", correct=quiz["correct"])
  if quiz.get("explanation"):
    text += "\n\n💡 " + quiz["explanation"]
  markup = InlineKeyboardMarkup(
      inline_keyboard=[[
          make_button(rt(lang, "quiz_next"), "ru_mode_quiz"),
          make_button(rt(lang, "quiz_menu"), "ru_menu"),
      ]]
  )
  await callback.message.answer(text, reply_markup=markup)


# ---------------------------------------------------------------------
# 22. RUS TILI: MATEMATIKA VA TASODIFIY MAVZULAR
# ---------------------------------------------------------------------
@dp.callback_query(F.data == "ru_mode_math")
async def ru_math_mode(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  menu = get_ru_menu(lang, user_id)
  await callback.answer()
  update_request_stats()
  prompt = (
      "Generate a challenging school-level math problem with a detailed"
      " step-by-step solution. Write the problem and the solution in"
      " Russian"
      + (
          ""
          if lang == "ru"
          else f", then add a short glossary of the key terms translated"
          f" into {LANG_NAMES.get(lang)}"
      )
      + f". Random seed: {random.randint(1, 10**6)}. Do not use asterisks"
      " (**)."
  )
  try:
    answer = await ask_groq(
        [{"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=1200,
        effort="low",
    )
    await send_long(callback.message, answer, menu)
  except Exception:
    await callback.message.answer(rt(lang, "generic_error"), reply_markup=menu)


@dp.callback_query(F.data == "ru_mode_random_topic")
async def ru_random_topic_mode(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  menu = get_ru_menu(lang, user_id)
  await callback.answer()
  update_request_stats()
  prompt = (
      "Generate a random topic for a Russian monologue (speaking card with 4"
      " guiding points) and a random essay (сочинение) topic suitable for"
      " B2-C1 learners. Write them in Russian"
      + (
          ""
          if lang == "ru"
          else f" and add a translation into {LANG_NAMES.get(lang)} under each"
      )
      + f". Random seed: {random.randint(1, 10**6)}. Do not use asterisks"
      " (**). Start lines with emojis only."
  )
  try:
    answer = await ask_groq(
        [{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=800,
        effort="low",
    )
    await send_long(
        callback.message, rt(lang, "random_title") + "\n\n" + answer, menu
    )
  except Exception:
    await callback.message.answer(rt(lang, "generic_error"), reply_markup=menu)


@dp.callback_query(F.data == "ru_mode_suggestion")
async def ru_suggestion_handler(callback: types.CallbackQuery, state: FSMContext):
  lang = get_user_db(callback.from_user.id)["lang"]
  # Qabul qilish mavjud waiting_for_suggestion handleri orqali ishlaydi
  # (u foydalanuvchini o'z bo'limi menyusiga qaytaradi).
  await state.set_state(BotStates.waiting_for_suggestion)
  await callback.message.answer(rt(lang, "sugg_prompt"))
  await callback.answer()


# ---------------------------------------------------------------------
# 23. RUS TILI: SPEAKING SIMULATOR (1, 2, 3-QISM VA FULL MOCK)
# ---------------------------------------------------------------------
RU_SPEAK_FLOWS = {
    "p1": ["p1", "p1", "p1"],
    "p2": ["p2"],
    "p3": ["p3", "p3"],
    "mock": ["p1", "p2", "p3"],
}
RU_SPEAK_ICONS = {"p1": "📌", "p2": "🧭", "p3": "💬"}
RU_P1_TOPICS = [
    "семья", "учёба", "работа", "родной город", "еда", "хобби", "путешествия",
    "погода", "друзья", "спорт", "музыка", "транспорт", "покупки", "здоровье",
    "праздники", "книги", "интернет", "распорядок дня", "дом и квартира",
    "выходные",
]
RU_P2_TOPICS = [
    "памятное путешествие", "близкий друг", "любимая книга или фильм",
    "важное событие в жизни", "интересный человек", "любимое место в городе",
    "подарок, который вам запомнился", "полезный навык", "праздник в вашей семье",
    "учитель, который повлиял на вас", "день, который вы не забудете",
    "ваша мечта", "любимое блюдо", "покупка, которой вы довольны",
]
RU_P3_TOPICS = [
    "роль образования в обществе", "влияние технологий на общение",
    "сохранение традиций и языка", "экология и забота о природе",
    "будущее профессий", "городская и сельская жизнь", "здоровый образ жизни",
    "роль семьи в воспитании", "изучение иностранных языков", "туризм и культура",
    "социальные сети и молодёжь", "ответственность и свобода",
]


async def ru_make_question(kind, lang, context=""):
  if kind == "p1":
    task = (
        "Create ONE simple question for the Part 1 interview of a Russian"
        " speaking test (level A2-B1) about the topic:"
        f" {random.choice(RU_P1_TOPICS)}."
    )
  elif kind == "p2":
    task = (
        "Create ONE Part 2 monologue card in Russian (level B1-B2) about:"
        f" {random.choice(RU_P2_TOPICS)}. Format: first line 'Расскажите о"
        " ...', then 4 short guiding points, each on a new line starting"
        " with ▫️."
    )
  else:
    topic = context if context else random.choice(RU_P3_TOPICS)
    task = (
        "Create ONE abstract discussion question for Part 3 of a Russian"
        f" speaking test (level B2-C1) related to: {topic}."
    )
  translate = (
      ""
      if lang == "ru"
      else (
          " After the Russian text add a new line with a short translation"
          f" into {LANG_NAMES.get(lang)} in parentheses."
      )
  )
  prompt = (
      task
      + " Write the question in Russian."
      + translate
      + " Output only the question text, with no preface and no asterisks."
  )
  return await ask_groq(
      [{"role": "user", "content": prompt}],
      temperature=0.9,
      max_tokens=350,
      effort="low",
  )


async def ru_transcribe(message):
  path = f"voice_ru_{message.from_user.id}_{message.message_id}.ogg"
  try:
    tg_file = await bot.get_file(message.voice.file_id)
    await bot.download_file(tg_file.file_path, path)

    def _run(model):
      with open(path, "rb") as audio:
        result = groq_client.audio.transcriptions.create(
            model=model,
            file=audio,
            language="ru",
            response_format="text",
        )
      return str(result).strip()

    for model in WHISPER_MODELS_RU:
      try:
        text = await asyncio.to_thread(_run, model)
        if text:
          return text
      except Exception as e:
        logging.warning("Whisper (%s) xatosi: %s", model, e)
    return ""
  except Exception as e:
    logging.warning("Ovozni yuklashda xato: %s", e)
    return ""
  finally:
    if os.path.exists(path):
      os.remove(path)


async def ru_evaluate_speaking(lang, answers):
  transcript = "\n\n".join(
      f"[{a['kind'].upper()}] Question: {a['q']}\nAnswer: {a['a']}"
      for a in answers
  )
  system = (
      "You are a strict, professional examiner of spoken Russian for the"
      " Uzbekistan national certificate system. Evaluate the candidate's"
      " answers (a transcript) on: fluency and coherence, lexical resource,"
      " grammatical range and accuracy (cases, aspect, agreement), and"
      " pronunciation (you only have a transcript, so state that this part is"
      " an estimate). The overall level must be exactly one of: C, C+, B, B+,"
      " A, A+ (A+ is excellent, C is the minimum acceptable); if the"
      " performance is below C write 'below C'. Also give an estimated CEFR"
      " level. Be strict and realistic. Required lines, each starting with an"
      " emoji: overall level; fluency and coherence; lexical resource;"
      " grammar; pronunciation estimate; the main mistakes with corrections"
      " (quote the Russian fragment and the fixed version); one improved"
      " sample answer in Russian; 3 actionable tips. Write explanations in"
      f" {LANG_NAMES.get(lang)}. Do not use asterisks (**)."
  )
  return await ask_groq(
      [
          {"role": "system", "content": system},
          {"role": "user", "content": transcript},
      ],
      temperature=0.2,
      max_tokens=1800,
      effort="medium",
  )


@dp.callback_query(F.data == "ru_mode_speaking")
async def ru_speaking_menu(callback: types.CallbackQuery, state: FSMContext):
  lang = get_user_db(callback.from_user.id)["lang"]
  markup = InlineKeyboardMarkup(
      inline_keyboard=[
          [make_button(rt(lang, "speak_p1"), "ru_sp_p1")],
          [make_button(rt(lang, "speak_p2"), "ru_sp_p2")],
          [make_button(rt(lang, "speak_p3"), "ru_sp_p3")],
          [make_button(rt(lang, "speak_mock"), "ru_sp_mock")],
      ]
  )
  await callback.message.answer(rt(lang, "speak_menu"), reply_markup=markup)
  await callback.answer()


def ru_speaking_prompt_text(lang, kind, n, total, question):
  header = rt(lang, "speak_q", icon=RU_SPEAK_ICONS[kind], n=n, total=total)
  hint = rt(lang, "speak_p2_hint" if kind == "p2" else "speak_hint")
  return f"{header}\n\n{question}\n\n{hint}"


@dp.callback_query(F.data.in_({"ru_sp_p1", "ru_sp_p2", "ru_sp_p3", "ru_sp_mock"}))
async def ru_speaking_begin(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  flow = callback.data.replace("ru_sp_", "")
  await callback.answer()
  update_request_stats()
  kind = RU_SPEAK_FLOWS[flow][0]
  try:
    question = await ru_make_question(kind, lang)
  except Exception:
    await callback.message.answer(
        rt(lang, "ai_error"), reply_markup=get_ru_menu(lang, user_id)
    )
    return
  await state.set_state(BotStates.ru_speaking)
  await state.update_data(
      sp_flow=flow, sp_answers=[], sp_q=question, sp_kind=kind
  )
  await callback.message.answer(
      ru_speaking_prompt_text(
          lang, kind, 1, len(RU_SPEAK_FLOWS[flow]), question
      )
  )


@dp.message(BotStates.ru_speaking, F.voice | F.text)
async def ru_speaking_answer(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  menu = get_ru_menu(lang, user_id)
  data = await state.get_data()
  flow = data.get("sp_flow")
  if not flow:
    await state.clear()
    await message.answer(rt(lang, "enter"), reply_markup=menu)
    return
  answers = list(data.get("sp_answers", []))
  if message.voice:
    await bot.send_chat_action(message.chat.id, "typing")
    user_text = await ru_transcribe(message)
    if not user_text:
      await message.answer(rt(lang, "speak_voice_fail"))
      return
  else:
    user_text = message.text.strip()
  answers.append({
      "kind": data.get("sp_kind", "p1"),
      "q": data.get("sp_q", ""),
      "a": user_text,
  })
  steps = RU_SPEAK_FLOWS[flow]
  update_request_stats()
  if len(answers) < len(steps):
    next_kind = steps[len(answers)]
    context = ""
    if flow == "mock" and next_kind == "p3":
      context = answers[1]["q"]
    try:
      question = await ru_make_question(next_kind, lang, context)
    except Exception:
      await message.answer(rt(lang, "ai_error"))
      return
    await state.update_data(
        sp_answers=answers, sp_q=question, sp_kind=next_kind
    )
    await message.answer(
        rt(lang, "speak_ok")
        + "\n\n"
        + ru_speaking_prompt_text(
            lang, next_kind, len(answers) + 1, len(steps), question
        )
    )
    return
  wait_msg = await message.answer(rt(lang, "speak_eval_wait"))
  try:
    report = await ru_evaluate_speaking(lang, answers)
    text = (
        rt(lang, "speak_eval_title")
        + "\n\n"
        + report
        + "\n\n"
        + rt(lang, "speak_eval_note")
    )
    await send_long(message, text, menu)
  except Exception:
    await message.answer(rt(lang, "ai_error"), reply_markup=menu)
  try:
    await wait_msg.delete()
  except Exception:
    pass
  await state.clear()


# ---------------------------------------------------------------------
# 24. GENERAL FALLBACK HANDLER (BARCHA XABARLARGA AI ORQALI JAVOB)
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
        reply_markup=get_menu_for_user(user_id, lang),
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
        reply_markup=get_menu_for_user(user_id, lang),
    )
  except Exception:
    await message.answer(
        "⚠️ Iltimos, amal bajarish uchun quyidagi tugmalardan"
        " foydalaning:",
        reply_markup=get_menu_for_user(user_id, lang),
    )


# ---------------------------------------------------------------------
# 25. BOTNI ISHGA TUSHIRISH (MAIN)
# ---------------------------------------------------------------------
async def main():
  logging.basicConfig(level=logging.INFO, stream=sys.stdout)
  print("Bot ishga tushdi: bo'limlar menyusi, Ingliz tili va Rus tili bo'limlari...")
  spawn_task(ru_challenge_scheduler())
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
