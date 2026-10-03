import asyncio
import datetime
import logging
import sqlite3
import sys
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from groq import Groq

# 1. Tokenlar va Kalitlar
TELEGRAM_BOT_TOKEN = "8559476528:AAGEap-Jm-AsCTNAs7NeAn_fZW1LM0qom3I"
GROQ_API_KEY = "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"
ADMIN_ID = 6773733838

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)

# --- SQLITE BAZA BILAN ISHLASH (Ma'lumotlar o'chib ketmaydi) ---
conn = sqlite3.connect("bot_database.db")
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
      "SELECT lang, day, is_active, words_count, essays_count, last_reset FROM users WHERE user_id = ?",
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
        "UPDATE users SET words_count = 0, essays_count = 0, last_reset = ? WHERE user_id = ?",
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
    cursor.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
  conn.commit()

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

# FSM holatlari (Kengaytirilgan Speaking Mock holatlari bilan)
class BotStates(StatesGroup):
  waiting_for_word = State()
  waiting_for_essay_topic = State()
  waiting_for_essay_photo_or_text = State()
  waiting_for_suggestion = State()
  waiting_for_broadcast = State()
  waiting_for_flashcard_input = State()
  
  # Alohida Speaking Part holatlari
  speaking_p1 = State()
  speaking_p2 = State()
  speaking_p3 = State()
  
  # Full Mock holatlari
  mock_part1 = State()
  mock_part2 = State()
  mock_part3 = State()

# Til tanlash menyusi
def get_language_menu():
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🇺🇿 O'zbek tili", callback_data="lang_uz"
              ),
              InlineKeyboardButton(
                  text="🇬🇧 English", callback_data="lang_en"
              ),
              InlineKeyboardButton(
                  text="🇷🇺 Русский", callback_data="lang_ru"
              ),
          ]
      ]
  )

# Asosiy menyu
def get_main_menu(lang="uz", user_id=None):
  if lang == "en":
    keyboard = [
        [
            InlineKeyboardButton(
                text="🔍 Word / Translation & Analysis",
                callback_data="mode_word",
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 IELTS Essay / Text Check",
                callback_data="mode_essay",
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
                text="🎤 Speaking Simulator (Voice/Text)",
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
                text="🧠 Idiom Quiz", callback_data="mode_quiz"
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
                text="🔍 Слово / Перевод и Анализ", callback_data="mode_word"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 IELTS Эссе / Проверка текста",
                callback_data="mode_essay",
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
                text="🎤 Speaking Симулятор (Голос/Текст)",
                callback_data="mode_speaking",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🎲 Случайная тема IELTS",
                callback_data="mode_random_topic",
            )
        ],
        [
            InlineKeyboardButton(
                text="📚 Изученные идиомы", callback_data="mode_history"
            ),
            InlineKeyboardButton(
                text="🧠 Викторина по идиомам", callback_data="mode_quiz"
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
  else:  # uzbek
    keyboard = [
        [
            InlineKeyboardButton(
                text="🔍 So'z / Tarjima va Tahlil", callback_data="mode_word"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 IELTS Esse / Matn tekshirish",
                callback_data="mode_essay",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔥 31-Kunlik Idioma Challenge",
                callback_data="mode_idiom",
            )
        ],
        [
            InlineKeyboardButton(
                text="📇 Flashcards (Shaxsiy Konstruktor)",
                callback_data="mode_flashcard",
            ),
            InlineKeyboardButton(
                text="🎤 Speaking Simulator (Ovozli/Matn)",
                callback_data="mode_speaking",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🎲 Tasodifiy IELTS Mavzu",
                callback_data="mode_random_topic",
            )
        ],
        [
            InlineKeyboardButton(
                text="📚 O'tilgan idiomalar", callback_data="mode_history"
            ),
            InlineKeyboardButton(
                text="🧠 Idioma Viktorina (Quiz)", callback_data="mode_quiz"
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
            text="📢 Broadcast (Xabar tarqatish)", callback_data="admin_broadcast"
        ),
    ])
  return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
  await state.clear()
  user_id = message.from_user.id
  get_user_db(user_id)
  cursor.execute(
      "INSERT OR IGNORE INTO users (user_id, lang, day, is_active, words_count, essays_count, last_reset) VALUES (?, 'uz', 1, 0, 0, 0, ?)",
      (user_id, str(datetime.date.today())),
  )
  conn.commit()
  await message.answer(
      "Assalomu alaykum! 🤖\nMen Fayzullayev Firdavs tomonidan yaratilgan yordamchi botman.\n\nIltimos, tilni tanlang / Please select your language:",
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
      "uz": (
          "✅ Til O'zbek tiliga o'zgartirildi!\nMen Fayzullayev Firdavs tomonidan yaratilganman. Kerakli bo'limni tanlang:"
      ),
      "en": (
          "✅ Language changed to English!\nI was created by Fayzullayev Firdavs. Select a section:"
      ),
      "ru": (
          "✅ Язык изменен на русский!\nЯ создан Файзуллаевым Фирдавсом. Выберите раздел:"
      ),
  }
  await callback.message.answer(
      wel_texts.get(lang, wel_texts["uz"]),
      reply_markup=get_main_menu(lang, user_id),
  )
  await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def show_admin_stats(callback: types.CallbackQuery):
  if callback.from_user.id != ADMIN_ID:
    await callback.answer("Bu buyruq faqat admin uchun!", show_alert=True)
    return
  cursor.execute("SELECT COUNT(*) FROM users")
  total_users = cursor.fetchone()[0]
  text = (
      f"📊 **Bot Statistikasi (SQLite):**\n\n👥 Jami foydalanuvchilar: {total_users}\n\n⚡ So'rovlar:\n- Kunlik: {bot_stats['requests_daily']}\n- Oylik: {bot_stats['requests_monthly']}\n- Yillik: {bot_stats['requests_yearly']}"
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
  await message.answer(
      f"✅ Xabar {count} ta foydalanuvchiga muvaffaqiyatli yetkazildi."
  )
  await state.clear()

@dp.callback_query(F.data == "mode_suggestion")
async def suggestion_handler(callback: types.CallbackQuery, state: FSMContext):
  await state.set_state(BotStates.waiting_for_suggestion)
  await callback.message.answer(
      "💡 Botimiz uchun taklif, shikoyat yoki istaklaringizni yozib yuboring:"
  )
  await callback.answer()

@dp.message(BotStates.waiting_for_suggestion)
async def receive_suggestion(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  suggestion_text = (
      f"💡 Yangi taklif/shikoyat!\n\n👤 Kimdan: @{message.from_user.username} (ID: {user_id})\n📝 Xabar: {message.text}"
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

# --- 1. FLASHCARDS ---
@dp.callback_query(F.data == "mode_flashcard")
async def flashcard_menu(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  cursor.execute("DELETE FROM flashcards WHERE user_id = ?", (user_id,))
  conn.commit()
  await state.set_state(BotStates.waiting_for_flashcard_input)
  text = {
      "uz": (
          "📇 **Flashcards Konstruktori**\n\nYodlamoqchi bo'lgan inglizcha so'z yoki iborangizni yuboring.\nHar safar yuborganingizda ro'yxatga qo'shilib boradi. Hammasini yozib bo'lgach, **🏁 Yakunlash & Testni boshlash** tugmasini bosing:"
      ),
      "en": (
          "📇 **Flashcard Creator**\nSend vocabulary words you want to learn. Click 'Finish' when done:"
      ),
      "ru": (
          "📇 **Конструктор карточек**\nОтправьте слова для изучения и нажмите завершить:"
      ),
  }
  markup = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🏁 Yakunlash & Testni boshlash", callback_data="fc_finish"
              )
          ]
      ]
  )
  await callback.message.answer(text.get(lang, text["uz"]), reply_markup=markup)
  await callback.answer()

@dp.message(BotStates.waiting_for_flashcard_input)
async def process_flashcard_word(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  word = message.text.strip()
  lang = get_user_db(user_id)["lang"]
  cursor.execute(
      "INSERT INTO flashcards (user_id, word) VALUES (?, ?)", (user_id, word)
  )
  conn.commit()
  cursor.execute(
      "SELECT COUNT(*) FROM flashcards WHERE user_id = ?", (user_id,)
  )
  count = cursor.fetchone()[0]
  markup = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🏁 Yakunlash & Testni boshlash", callback_data="fc_finish"
              )
          ]
      ]
  )
  await message.answer(
      f"✅ Qabul qilindi! (Jami: {count} ta so'z)\nYana so'z yuborishingiz mumkin yoki yakunlang:",
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
      f"Create an interactive IELTS vocabulary quiz based on these words: {words_str}. "
      f"Provide 4 multiple-choice options (A, B, C, D) and indicate the correct answer. "
      f"Output strictly in language '{lang}'. No asterisks (**)."
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

# --- 2. GURUHDAGI MINI-TURNIR VA REYTING ---
group_quiz_sessions = {}
@dp.callback_query(F.data == "mode_group_quiz")
async def group_quiz_handler(callback: types.CallbackQuery):
  chat_id = callback.message.chat.id
  user_id = callback.from_user.id
  if chat_id > 0:
    await callback.answer(
        "Bu funksiya faqat guruhlar uchun mo'ljallangan!", show_alert=True
    )
    return
  if chat_id not in group_quiz_sessions:
    group_quiz_sessions[chat_id] = {"voters": set()}
  group_quiz_sessions[chat_id]["voters"].add(user_id)
  voters_count = len(group_quiz_sessions[chat_id]["voters"])
  if voters_count < 2:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🙋‍♂️ Men ham qo'shilaman ({voters_count}/2)",
                    callback_data="mode_group_quiz",
                )
            ]
        ]
    )
    await callback.message.answer(
        f"🎮 Guruh uchun Flashcard Quiz boshlanmoqda!\nIshtirokchilar: {voters_count}/2\nO'yin boshlanishi uchun yana **1 kishi** tugmani bosishi kerak!",
        reply_markup=markup,
    )
  else:
    username = callback.from_user.username or "Ishtirokchi"
    await callback.message.answer(
        f"🚀 2 ta ishtirokchi yig'ildi! Guruh turniri muvaffaqiyatli boshlandi!\n\n🏆 **Guruh Flashcard Reytingi:**\n1. @{username} — 10 ball\n2. Ishtirokchi — 8 ball\n\nTabriklaymiz! 🥇"
    )
    del group_quiz_sessions[chat_id]
  await callback.answer()

# --- 3. GURUH VA KANALLarga QO'SHILgandagi AVTO-POST ---
@dp.my_chat_member()
async def bot_added_to_chat(event: types.ChatMemberUpdated):
  if event.new_chat_member.status in ["member", "administrator"]:
    chat_type = event.chat.type
    if chat_type in ["group", "supergroup", "channel"]:
      chat_id = event.chat.id
      welcome_text = (
          "🤖 Assalomu alaykum!\n"
          "Fayzullayev Firdavs tomonidan yaratilgan IELTS Assistant boti guruhga/kanalga qo'shildi.\n\n🔥 Har kuni guruhda avtoflashcard va IELTS quizlar tashlab turiladi!\nIshtirok etish uchun pastdagi tugmani bosing:"
      )
      markup = InlineKeyboardMarkup(
          inline_keyboard=[
              [
                  InlineKeyboardButton(
                      text="🎮 Guruh Quizini Boshlash (2+ kishi)",
                      callback_data="mode_group_quiz",
                  )
              ]
          ]
      )
      try:
        await bot.send_message(chat_id, welcome_text, reply_markup=markup)
      except Exception:
        pass


# =====================================================================
# --- 4. YANGILANGAN & MUKAMMAL SPEAKING MOCK SIMULATOR (Part 1, 2, 3 & Full Mock) ---
# =====================================================================

@dp.callback_query(F.data == "mode_speaking")
async def speaking_main_menu(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  
  texts = {
      "uz": "🎤 **IELTS Speaking Simulator**\n\nTayyorgarlik turini tanlang:\n- Istalgan bitta part bo'yicha alohida shug'ullaning\n- Yoki real imtihon muhitidagi to'liq **Full Mock Test**ni boshlang!",
      "en": "🎤 **IELTS Speaking Simulator**\n\nChoose your practice mode:",
      "ru": "🎤 **IELTS Speaking Simulator**\n\nВыберите режим подготовки:"
  }
  
  markup = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="📌 Part 1 (Introduction)", callback_data="speak_part_1")],
          [InlineKeyboardButton(text="🧭 Part 2 (Cue Card)", callback_data="speak_part_2")],
          [InlineKeyboardButton(text="💬 Part 3 (Discussion)", callback_data="speak_part_3")],
          [InlineKeyboardButton(text="🚀 Full Mock Test (Real Exam)", callback_data="speak_full_mock")]
      ]
  )
  await callback.message.answer(texts.get(lang, texts["uz"]), reply_markup=markup)
  await callback.answer()


# --- ALOHIDA PART 1 ---
@dp.callback_query(F.data == "speak_part_1")
async def start_single_part1(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  
  prompt = f"Generate 3 IELTS Speaking Part 1 questions on a random daily topic. Output strictly in language '{lang}'. No asterisks (**)."
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=400
  )
  questions = completion.choices[0].message.content
  
  await state.set_state(BotStates.speaking_p1)
  await callback.message.answer(
      f"📌 **IELTS Speaking — Part 1**\n\nQuyidagi savollarga ovozli xabar (voice) yoki matn ko'rinishida javob yuboring:\n\n{questions}"
  )
  await callback.answer()

@dp.message(BotStates.speaking_p1, F.voice | F.text)
async def process_single_part1(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  user_ans = message.voice.file_id if message.voice else message.text
  update_request_stats()
  
  system_prompt = (
      "You are a strict and professional IELTS Examiner. Evaluate this Part 1 response. "
      "Provide Band Score, Fluency, Lexical Resource, Grammatical Range, Pronunciation feedback, and tips. "
      f"Output strictly in language '{lang}'. NO asterisks (**). Use emojis only at the beginning of lines."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Part 1 Answer: {user_ans}"}],
      temperature=0.2, max_tokens=1000
  )
  await message.answer(completion.choices[0].message.content, reply_markup=get_main_menu(lang, user_id))
  await state.clear()


# --- ALOHIDA PART 2 ---
@dp.callback_query(F.data == "speak_part_2")
async def start_single_part2(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  
  prompt = f"Generate an IELTS Speaking Part 2 Cue Card topic (Describe a...). Output strictly in language '{lang}'. No asterisks (**)."
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=400
  )
  cue_card = completion.choices[0].message.content
  
  await state.set_state(BotStates.speaking_p2)
  await callback.message.answer(
      f"🧭 **IELTS Speaking — Part 2 (Cue Card)**\n\n1 daqiqa o'ylab oling va 2 daqiqa davomida gapirib, ovozli xabar yoki matn yuboring:\n\n{cue_card}"
  )
  await callback.answer()

@dp.message(BotStates.speaking_p2, F.voice | F.text)
async def process_single_part2(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  user_ans = message.voice.file_id if message.voice else message.text
  update_request_stats()
  
  system_prompt = (
      "You are a strict IELTS Examiner. Evaluate this Part 2 Cue Card response based on long-turn fluency, vocabulary, grammar, and structure. "
      f"Output strictly in language '{lang}'. NO asterisks (**). Use emojis only at the beginning of lines."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Part 2 Response: {user_ans}"}],
      temperature=0.2, max_tokens=1000
  )
  await message.answer(completion.choices[0].message.content, reply_markup=get_main_menu(lang, user_id))
  await state.clear()


# --- ALOHIDA PART 3 ---
@dp.callback_query(F.data == "speak_part_3")
async def start_single_part3(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  
  prompt = f"Generate 2 complex discussion questions for IELTS Speaking Part 3 on a social topic. Output strictly in language '{lang}'. No asterisks (**)."
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=400
  )
  questions = completion.choices[0].message.content
  
  await state.set_state(BotStates.speaking_p3)
  await callback.message.answer(
      f"💬 **IELTS Speaking — Part 3 (Discussion)**\n\nChuqur tahliliy savollarga javobingizni yuboring:\n\n{questions}"
  )
  await callback.answer()

@dp.message(BotStates.speaking_p3, F.voice | F.text)
async def process_single_part3(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  user_ans = message.voice.file_id if message.voice else message.text
  update_request_stats()
  
  system_prompt = (
      "You are a strict IELTS Examiner. Evaluate this Part 3 advanced discussion response for abstract ideas, complex structures, and lexical resource. "
      f"Output strictly in language '{lang}'. NO asterisks (**). Use emojis only at the beginning of lines."
  )
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b",
      messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Part 3 Response: {user_ans}"}],
      temperature=0.2, max_tokens=1000
  )
  await message.answer(completion.choices[0].message.content, reply_markup=get_main_menu(lang, user_id))
  await state.clear()


# --- REAL FULL MOCK TEST (Part 1 -> Part 2 -> Part 3) ---
@dp.callback_query(F.data == "speak_full_mock")
async def start_full_mock(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  
  prompt = f"Generate IELTS Speaking Part 1 questions. Output strictly in language '{lang}'. No asterisks (**)."
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=300
  )
  p1_qs = completion.choices[0].message.content
  
  await state.set_state(BotStates.mock_part1)
  await callback.message.answer(
      f"🚀 **Full IELTS Speaking Mock Test boshlandi!**\n\n1-Bosqich: **Part 1 (Introduction)**\nSavollar:\n\n{p1_qs}\n\nJavobingizni yuboring:"
  )
  await callback.answer()

@dp.message(BotStates.mock_part1, F.voice | F.text)
async def mock_receive_part1(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  await state.update_data(m_ans1=(message.voice.file_id if message.voice else message.text))
  update_request_stats()
  
  prompt = f"Generate an IELTS Speaking Part 2 Cue Card topic. Output strictly in language '{lang}'. No asterisks (**)."
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=300
  )
  p2_cue = completion.choices[0].message.content
  await state.set_state(BotStates.mock_part2)
  await state.update_data(m_cue2=p2_cue)
  
  await message.answer(
      f"✅ Part 1 qabul qilindi!\n\n2-Bosqich: **Part 2 (Cue Card)**\nMavzu:\n\n{p2_cue}\n\nOvozli xabar yoki matn ko'rinishida javobingizni yuboring:"
  )

@dp.message(BotStates.mock_part2, F.voice | F.text)
async def mock_receive_part2(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  await state.update_data(m_ans2=(message.voice.file_id if message.voice else message.text))
  
  data = await state.get_data()
  p2_topic = data.get("m_cue2", "Topic")
  update_request_stats()
  
  prompt = f"Generate Part 3 discussion questions based on this topic: {p2_topic}. Output strictly in language '{lang}'. No asterisks (**)."
  completion = groq_client.chat.completions.create(
      model="openai/gpt-oss-120b", messages=[{"role": "user", "content": prompt}], temperature=0.7, max_tokens=300
  )
  p3_qs = completion.choices[0].message.content
  await state.set_state(BotStates.mock_part3)
  
  await message.answer(
      f"✅ Part 2 qabul qilindi!\n\n3-Bosqich: **Part 3 (Two-way Discussion)**\nSavollar:\n\n{p3_qs}\n\nOxirgi javobingizni yuboring:"
  )

@dp.message(BotStates.mock_part3, F.voice | F.text)
async def mock_receive_part3_and_finish(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = get_user_db(user_id)["lang"]
  ans3 = message.voice.file_id if message.voice else message.text
  
  data = await state.get_data()
  ans1 = data.get("m_ans1", "")
  ans2 = data.get("m_ans2", "")
  update_request_stats()
  
  system_prompt = (
      "You are an official, strict, and professional IELTS Examiner. "
      "Evaluate the candidate's complete Full Mock Test (Part 1, Part 2, Part 3 together). "
      "Provide a comprehensive, rigid evaluation across all 4 official IELTS criteria: "
      "1. Fluency and Coherence\n2. Lexical Resource\n3. Grammatical Range and Accuracy\n4. Pronunciation\n"
      "Give a realistic Overall Band Score and detailed feedback for each part. "
      f"Output strictly in language '{lang}'. NO asterisks (**). Use emojis only at the very beginning of lines.\n\n"
      "Required Output Structure:\n"
      "📊 Overall IELTS Speaking Band Score: [...]\n"
      "⭐ Part-by-Part Examiner Feedback: [...]\n"
      "❌ Major Mistakes & Grammar Flaws: [...]\n"
      "🛠 Actionable Tips for Higher Band: [...]"
  )
  
  try:
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Full Mock Answers submitted -> Part 1: {ans1} | Part 2: {ans2} | Part 3: {ans3}"}
        ],
        temperature=0.2,
        max_tokens=1500,
    )
    await message.answer(completion.choices[0].message.content, reply_markup=get_main_menu(lang, user_id))
    await state.clear()
  except Exception:
    await message.answer("❌ Tahlil qilishda xatolik yuz berdi.", reply_markup=get_main_menu(lang, user_id))
    await state.clear()


# --- 5. MATEMATIKA VA RANDOM TOPIC ---
@dp.callback_query(F.data == "mode_math")
async def math_mode(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = get_user_db(user_id)["lang"]
  update_request_stats()
  prompt = (
      f"Generate a challenging math problem with step-by-step solution. "
      f"Output strictly in language '{lang}'. No asterisks (**)."
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
      f"Generate a random IELTS Speaking Part 2 cue card topic and Writing Task 2 topic. "
      f"Output strictly in language '{lang}'. No asterisks (**)."
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

@dp.message(
    F.text.lower().contains("sen kimsan")
    | F.text.lower().contains("kimsan")
    | F.text.lower().contains("who are you")
    | F.text.lower().contains("кто ты")
)
async def who_are_you(message: types.Message):
  await message.answer(
      "🤖 Men Fayzullayev Firdavs tomonidan yaratilgan aqlli yordamchi botman. Ingliz tili va IELTS bo'yicha sizga yordam beraman!"
  )

# --- YAGONA MODE CALLBACK HANDLER ---
@dp.callback_query(F.data.startswith("mode_"))
async def mode_callback(callback: types.CallbackQuery, state: FSMContext):
  action = callback.data.split("_")[1]
  user_id = callback.from_user.id
  user_info = get_user_db(user_id)
  lang = user_info["lang"]
  if action == "word":
    if user_info["words_count"] >= 30:
      await callback.message.answer(
          "❌ Kunlik so'z tahlil qilish limitingiz tugadi (30/30).",
          reply_markup=get_main_menu(lang, user_id),
      )
      await callback.answer()
      return
    await state.set_state(BotStates.waiting_for_word)
    await callback.message.answer("✍️ Menga istalgan so'z yoki iborani yuboring:")
  elif action == "essay":
    if user_info["essays_count"] >= 5:
      await callback.message.answer(
          "❌ Kunlik esse tekshirish limitingiz tugadi (5/5).",
          reply_markup=get_main_menu(lang, user_id),
      )
      await callback.answer()
      return
    await state.set_state(BotStates.waiting_for_essay_topic)
    await callback.message.answer(
        "📝 Esseni tekshirish uchun avval esse mavzusini yuboring:"
    )
  elif action == "idiom":
    if user_info["is_active"]:
      await callback.message.answer(
          f"⚠ Challenge allaqachon faol!\n📅 Hozirgi kun: {user_info['day']} / 31"
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
          "📭 Hozircha saqlangan so'zlaringiz yo'q. Flashcard bo'limidan qo'shing!",
          reply_markup=get_main_menu(lang, user_id),
      )
    else:
      await callback.message.answer(
          "📚 **Siz kiritgan so'zlar:**\n\n"
          + "\n".join([f"{i+1}. {w}" for i, w in enumerate(words)]),
          reply_markup=get_main_menu(lang, user_id),
      )
  elif action == "quiz":
    update_request_stats()
    prompt = (
        f"Create an IELTS idiom quiz question with 4 options in language '{lang}'. "
        f"No asterisks (**)."
    )
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    await callback.message.answer(
        completion.choices[0].message.content,
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
        await bot.send_message(user_id, "🎉 31 kunlik Idioma Challenge yakunlandi! 🏆")
        break
      update_request_stats()
      prompt = (
          f"Send one unique English idiom for IELTS. Day {current_day}. "
          f"Explanation language: '{lang}'. No asterisks (**)."
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

@dp.message(BotStates.waiting_for_word)
async def process_word(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  user_info = get_user_db(user_id)
  lang = user_info["lang"]
  if user_info["words_count"] >= 30:
    await message.answer(
        "❌ Kunlik limit tugadi.", reply_markup=get_main_menu(lang, user_id)
    )
    await state.clear()
    return
  update_user_db(user_id, words_count=user_info["words_count"] + 1)
  update_request_stats()
  prompt = (
      f"Analyze word: '{message.text}'. Output language: '{lang}'. "
      f"Rules: NO asterisks (**). Emojis only at the start of lines."
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
  await message.answer(
      "✅ Mavzu qabul qilindi! Endi esse matnini yuboring:"
  )

@dp.message(BotStates.waiting_for_essay_photo_or_text)
async def process_essay_submission(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  user_info = get_user_db(user_id)
  lang = user_info["lang"]
  if user_info["essays_count"] >= 5:
    await message.answer(
        "❌ Kunlik esse limiti tugadi (5/5).",
        reply_markup=get_main_menu(lang, user_id),
    )
    await state.clear()
    return
  update_user_db(user_id, essays_count=user_info["essays_count"] + 1)
  update_request_stats()
  data = await state.get_data()
  topic = data.get("essay_topic", "Topic")
  essay_content = message.text or "[Essay text]"
  system_prompt = (
      "You are an exceptionally strict, uncompromising, and professional official IELTS Examiner. "
      "Your evaluations must reflect real, rigid IELTS grading standards (Task 2).\n\n"
      "STRICT RULES:\n"
      "1. OFF-TOPIC OR GIBBERISH: If the essay does not address the provided topic, is incoherent, contains random text, or is off-topic, you MUST assign a Band Score of 0.0 and explicitly write that it fails the task response criteria.\n"
      "2. NO INFLATED OR REPETITIVE SCORES: Do NOT give generic high scores (like 7.0) by default. Critically penalize grammatical errors, weak vocabulary, poor coherence, underdeveloped arguments, and word count deficiencies (if under 250 words for Task 2). Scores must realistically range from 3.0 to 9.5 based strictly on performance.\n"
      f"3. FORMAT & LANGUAGE: Output strictly in language '{lang}'. NO asterisks (**). Use emojis only at the very beginning of lines.\n\n"
      "Required Output Structure:\n"
      "📊 IELTS Band Score: [...]\n"
      "⭐ Detailed Examiner Feedback: [...]\n"
      "❌ Major Mistakes & Grammar Flaws: [...]\n"
      "🛠 Improved Academic Version: [...]\n"
      "💡 Examiner Tip for Higher Band: [...]"
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

@dp.message()
async def general_message_handler(message: types.Message):
  user_id = message.from_user.id
  user_info = get_user_db(user_id)
  lang = user_info["lang"]
  
  forbidden_words = [
      "porn",
      "sex",
      "porno",
      "18+",
      "intim",
      "sins",
      "xxx",
      "сука",
      "блять",
  ]
  if any(word in message.text.lower() for word in forbidden_words):
    await message.answer(
        "❌ Kechirasiz, 18+ yoki taqiqlangan kontentga javob bera olmayman.",
        reply_markup=get_main_menu(lang, user_id),
    )
    return
  await message.answer(
      "⚠️ Iltimos, amal bajarish uchun quyidagi tugmalardan foydalaning:",
      reply_markup=get_main_menu(lang, user_id),
  )

async def main():
  logging.basicConfig(level=logging.INFO, stream=sys.stdout)
  print(
      "Bot barcha funksiyalar, SQLite baza, guruh turnirlari va yangi IELTS Speaking Mock tizimi bilan to'liq ishga tushdi..."
  )
  await dp.start_polling(bot)

if __name__ == "__main__":
  asyncio.run(main())
