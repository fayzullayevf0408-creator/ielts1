import asyncio
import datetime
import logging
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

# Ma'lumotlar bazasi va statistika xotirasi
user_data = {}  # {user_id: {"lang": "uz", "day": 1, "is_active": True, "idioms": [], "words_count": 0, "essays_count": 0, "last_reset": date}}
all_users = set()
bot_stats = {
    "requests_daily": 0,
    "requests_monthly": 0,
    "requests_yearly": 0,
    "last_date": datetime.date.today(),
}


# FSM holatlari
class BotStates(StatesGroup):
  waiting_for_word = State()
  waiting_for_essay_topic = State()
  waiting_for_essay_photo_or_text = State()
  waiting_for_suggestion = State()
  waiting_for_broadcast = State()


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


# Asosiy menyu (Tilga qarab o'zgaradi + Admin tugmalari)
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


# Statistika hisoblagichni yangilash
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


# Kunlik limitlarni tekshirish va yangilash
def check_and_reset_limits(user_id):
  today = datetime.date.today()
  if user_id not in user_data:
    user_data[user_id] = {
        "lang": "uz",
        "day": 1,
        "is_active": False,
        "idioms": [],
        "words_count": 0,
        "essays_count": 0,
        "last_reset": today,
    }
  else:
    if user_data[user_id].get("last_reset") != today:
      user_data[user_id]["words_count"] = 0
      user_data[user_id]["essays_count"] = 0
      user_data[user_id]["last_reset"] = today


@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
  await state.clear()
  user_id = message.from_user.id
  all_users.add(user_id)
  check_and_reset_limits(user_id)

  await message.answer(
      "Assalomu alaykum! 🤖\nMen Fayzullayev Firdavs tomonidan yaratilgan"
      " yordamchi botman.\n\nIltimos, tilni tanlang / Please select your"
      " language / Пожалуйста, выберите язык:",
      reply_markup=get_language_menu(),
  )


# Tilni tanlash va o'zgartirish
@dp.callback_query(F.data.startswith("lang_") | (F.data == "change_lang"))
async def set_language(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  check_and_reset_limits(user_id)

  if callback.data == "change_lang":
    await callback.message.answer(
        "Tilni tanlang / Select language / Выберите язык:",
        reply_markup=get_language_menu(),
    )
    await callback.answer()
    return

  lang = callback.data.split("_")[1]
  user_data[user_id]["lang"] = lang

  wel_texts = {
      "uz": (
          "✅ Til O'zbek tiliga o'zgartirildi!\nMen Fayzullayev Firdavs"
          " tomonidan yaratilganman. Quyidagi menyudan kerakli bo'limni"
          " tanlang:"
      ),
      "en": (
          "✅ Language changed to English!\nI was created by Fayzullayev"
          " Firdavs. Select a section from the menu below:"
      ),
      "ru": (
          "✅ Язык изменен на русский!\nЯ создан Файзуллаевым Фирдавсом. Выберите"
          " нужный раздел из меню ниже:"
      ),
  }

  await callback.message.answer(
      wel_texts.get(lang, wel_texts["uz"]),
      reply_markup=get_main_menu(lang, user_id),
  )
  await callback.answer()


# Admin uchun statistika va broadcast tugmalari
@dp.callback_query(F.data == "admin_stats")
async def show_admin_stats(callback: types.CallbackQuery):
  if callback.from_user.id != ADMIN_ID:
    await callback.answer(
        "Bu buyruq faqat admin uchun!", show_alert=True
    )
    return

  total_users = len(all_users)
  text = (
      f"📊 **Bot Statistikasi:**\n\n👥 **Foydalanuvchilar:**\n- Jami:"
      f" {total_users}\n\n⚡ **So'rovlar soni:**\n- Kunlik:"
      f" {bot_stats['requests_daily']}\n- Oylik:"
      f" {bot_stats['requests_monthly']}\n- Yillik:"
      f" {bot_stats['requests_yearly']}"
  )
  lang = user_data.get(callback.from_user.id, {}).get("lang", "uz")
  await callback.message.answer(
      text, reply_markup=get_main_menu(lang, callback.from_user.id)
  )
  await callback.answer()


@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
  if callback.from_user.id != ADMIN_ID:
    await callback.answer(
        "Bu buyruq faqat admin uchun!", show_alert=True
    )
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
  count = 0
  for uid in all_users:
    try:
      await bot.send_message(uid, message.text)
      count += 1
    except Exception:
      pass
  await message.answer(f"✅ Xabar {count} ta foydalanuvchiga muvaffaqiyatli yetkazildi.")
  await state.clear()


# Taklif yuborish bo'limi
@dp.callback_query(F.data == "mode_suggestion")
async def suggestion_handler(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  lang = user_data.get(user_id, {}).get("lang", "uz")
  await state.set_state(BotStates.waiting_for_suggestion)

  msgs = {
      "uz": "💡 Taklif yoki shikoyatingizni yozib yuboring:",
      "en": "💡 Send your suggestion or feedback:",
      "ru": "💡 Отправьте ваше предложение или отзыв:",
  }
  await callback.message.answer(msgs.get(lang, msgs["uz"]))
  await callback.answer()


@dp.message(BotStates.waiting_for_suggestion)
async def receive_suggestion(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = user_data.get(user_id, {}).get("lang", "uz")

  suggestion_text = (
      f"💡 Yangi taklif/shikoyat!\n\n👤 Kimdan: @{message.from_user.username}"
      f" (ID: {user_id})\n📝 Xabar: {message.text}"
  )
  try:
    await bot.send_message(ADMIN_ID, suggestion_text)
  except Exception:
    pass

  msgs = {
      "uz": "✅ Taklifingiz adminga yuborildi. Rahmat!",
      "en": "✅ Your suggestion has been sent to the admin. Thank you!",
      "ru": "✅ Ваше предложение отправлено администратору. Спасибо!",
  }
  await message.answer(
      msgs.get(lang, msgs["uz"]), reply_markup=get_main_menu(lang, user_id)
  )
  await state.clear()


# Matematik masalalar (Coming Soon)
@dp.callback_query(F.data == "mode_math")
async def math_coming_soon(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  lang = user_data.get(user_id, {}).get("lang", "uz")
  msgs = {
      "uz": "🚧 Matematik masalalar / misollar bo'limi: Coming Soon (Tez kunda)!",
      "en": "🚧 Math Problems / Examples section: Coming Soon!",
      "ru": (
          "🚧 Раздел математических задач / примеров: Coming Soon (Скоро)!"
      ),
  }
  await callback.answer(msgs.get(lang, msgs["uz"]), show_alert=True)


# AI kimligini so'raganda
@dp.message(
    F.text.lower().contains("sen kimsan")
    | F.text.lower().contains("kimsan")
    | F.text.lower().contains("who are you")
    | F.text.lower().contains("кто ты")
)
async def who_are_you(message: types.Message):
  await message.answer(
      "🤖 Men Fayzullayev Firdavs tomonidan yaratilgan aqlli yordamchi"
      " botman. Ingliz tili va IELTS bo'yicha sizga yordam beraman!"
  )


@dp.callback_query(F.data.startswith("mode_"))
async def mode_callback(callback: types.CallbackQuery, state: FSMContext):
  action = callback.data.split("_")[1]
  user_id = callback.from_user.id
  lang = user_data.get(user_id, {}).get("lang", "uz")
  check_and_reset_limits(user_id)

  if action == "word":
    if user_data[user_id]["words_count"] >= 30:
      msgs = {
          "uz": (
              "❌ Bugungi so'z tahlil qilish limitingiz tugadi (30/30)."
              " Ertaga qayta urinib ko'ring!"
          ),
          "en": (
              "❌ Daily word analysis limit reached (30/30). Try again tomorrow!"
          ),
          "ru": (
              "❌ Лимит анализа слов на сегодня исчерпан (30/30). Попробуйте"
              " завтра!"
          ),
      }
      await callback.message.answer(
          msgs.get(lang, msgs["uz"]),
          reply_markup=get_main_menu(lang, user_id),
      )
      await callback.answer()
      return

    await state.set_state(BotStates.waiting_for_word)
    prompts = {
        "uz": "✍️ Menga istalgan so'z yoki iborani yuboring:",
        "en": "✍️ Send me any word or phrase to analyze:",
        "ru": "✍️ Отправьте мне любое слово или фразу для анализа:",
    }
    await callback.message.answer(prompts.get(lang, prompts["uz"]))

  elif action == "essay":
    if user_data[user_id]["essays_count"] >= 5:
      msgs = {
          "uz": (
              "❌ Bugungi esse tekshirish limitingiz tugadi (5/5). Ertaga qayta"
              " urinib ko'ring!"
          ),
          "en": (
              "❌ Daily essay check limit reached (5/5). Try again tomorrow!"
          ),
          "ru": (
              "❌ Лимит проверки эссе на сегодня исчерпан (5/5). Попробуйте"
              " завтра!"
          ),
      }
      await callback.message.answer(
          msgs.get(lang, msgs["uz"]),
          reply_markup=get_main_menu(lang, user_id),
      )
      await callback.answer()
      return

    await state.set_state(BotStates.waiting_for_essay_topic)
    prompts = {
        "uz": "📝 Esseni tekshirish uchun avval esse mavzusini yuboring:",
        "en": "📝 Send the essay topic first to check your essay:",
        "ru": "📝 Сначала отправьте тему эссе для проверки:",
    }
    await callback.message.answer(prompts.get(lang, prompts["uz"]))

  elif action == "idiom":
    if user_id in user_data and user_data[user_id].get("is_active"):
      current_day = user_data[user_id]["day"]
      msgs = {
          "uz": (
              f"⚠️ Siz allaqachon faol challenge'dasiz!\n📅 Hozirgi kun:"
              f" {current_day} / 31"
          ),
          "en": (
              f"⚠️ You are already in an active challenge!\n📅 Current day:"
              f" {current_day} / 31"
          ),
          "ru": (
              f"⚠️ Вы уже участвуете в челлендже!\n📅 Текущий день: {current_day}"
              f" / 31"
          ),
      }
      await callback.message.answer(msgs.get(lang, msgs["uz"]))
    else:
      user_data[user_id]["day"] = 1
      user_data[user_id]["is_active"] = True
      user_data[user_id]["idioms"] = []

      msgs = {
          "uz": (
              "🔥 31-Kunlik Idioma Challenge boshlandi! 🏆\n1-kun idiomasi"
              " yuklanmoqda..."
          ),
          "en": (
              "🔥 31-Day Idiom Challenge started! 🏆\nLoading day 1 idiom..."
          ),
          "ru": (
              "🔥 31-дневный челлендж идиом начался! 🏆\nЗагрузка идиомы 1-го"
              " дня..."
          ),
      }
      await callback.message.answer(msgs.get(lang, msgs["uz"]))
      asyncio.create_task(send_daily_idiom_for_user(user_id))

  elif action == "history":
    if user_id in user_data and user_data[user_id].get("idioms"):
      hist_title = {
          "uz": "📚 O'rgangan idiomalaringiz:\n\n",
          "en": "📚 Your learned idioms:\n\n",
          "ru": "📚 Ваши изученные идиомы:\n\n",
      }
      history_text = hist_title.get(lang, hist_title["uz"])
      for idx, item in enumerate(user_data[user_id]["idioms"], 1):
        history_text += f"{idx}. {item}\n-------------------\n"
      await callback.message.answer(
          history_text, reply_markup=get_main_menu(lang, user_id)
      )
    else:
      msgs = {
          "uz": (
              "📭 Hozircha o'tilgan idiomalar yo'q. Challenge'ni boshlang!"
          ),
          "en": "📭 No idioms learned yet. Start the challenge!",
          "ru": (
              "📭 Пока нет изученных идиом. Начните челлендж!"
          ),
      }
      await callback.message.answer(
          msgs.get(lang, msgs["uz"]),
          reply_markup=get_main_menu(lang, user_id),
      )

  elif action == "quiz":
    if user_id in user_data and user_data[user_id].get("idioms"):
      update_request_stats()
      known_idioms = ", ".join(user_data[user_id]["idioms"])
      prompt = (
          f"User knows these idioms: {known_idioms}. Create a quiz question with"
          f" 4 options (a, b, c, d) in language '{lang}'. No asterisks (**)."
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
    else:
      msgs = {
          "uz": "❌ Quiz ishlash uchun kamida bitta idioma o'rganing!",
          "en": "❌ Learn at least one idiom to take a quiz!",
          "ru": "❌ Выучите хотя бы одну идиому для викторины!",
      }
      await callback.message.answer(
          msgs.get(lang, msgs["uz"]),
          reply_markup=get_main_menu(lang, user_id),
      )

  await callback.answer()


# 31 kunlik avtomatik idioma yuborish
async def send_daily_idiom_for_user(user_id: int):
  try:
    while user_id in user_data and user_data[user_id].get("is_active"):
      current_day = user_data[user_id]["day"]
      lang = user_data[user_id].get("lang", "uz")

      if current_day > 31:
        user_data[user_id]["is_active"] = False
        ends = {
            "uz": "🎉 31 kunlik Idioma Challenge yakunlandi! 🏆",
            "en": "🎉 31-Day Idiom Challenge completed! 🏆",
            "ru": "🎉 31-дневный челлендж идиом завершен! 🏆",
        }
        await bot.send_message(user_id, ends.get(lang, ends["uz"]))
        break

      update_request_stats()
      sent_history = user_data[user_id]["idioms"]
      prompt = (
          f"Send one unique English idiom for IELTS learners. Day {current_day}."
          f" Avoid previous: {sent_history}. Language for explanation:"
          f" '{lang}'. No asterisks (**). Format:\n\n🔥 Day {current_day}\n💬"
          " Idiom: ...\n📖 Meaning: ...\n💡 Example: ..."
      )

      completion = groq_client.chat.completions.create(
          model="openai/gpt-oss-120b",
          messages=[{"role": "user", "content": prompt}],
          temperature=0.7,
      )

      idiom_text = completion.choices[0].message.content
      await bot.send_message(user_id, idiom_text)

      user_data[user_id]["idioms"].append(idiom_text[:50])
      user_data[user_id]["day"] += 1

      await asyncio.sleep(86400)
  except Exception as e:
    print(f"Challenge xatosi: {e}")


# So'zni tahlil qilish
@dp.message(BotStates.waiting_for_word)
async def process_word(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = user_data.get(user_id, {}).get("lang", "uz")
  check_and_reset_limits(user_id)

  if user_data[user_id]["words_count"] >= 30:
    msgs = {
        "uz": "❌ Kunlik so'z tahlil qilish limitingiz tugadi (30/30).",
        "en": "❌ Daily word analysis limit reached (30/30).",
        "ru": "❌ Лимит анализа слов на сегодня исчерпан (30/30).",
    }
    await message.answer(
        msgs.get(lang, msgs["uz"]), reply_markup=get_main_menu(lang, user_id)
    )
    await state.clear()
    return

  user_data[user_id]["words_count"] += 1
  update_request_stats()
  await bot.send_chat_action(chat_id=message.chat.id, action="typing")

  try:
    prompt = (
        f"Analyze word: '{message.text}'. Language for output: '{lang}'."
        " Rules: NO asterisks (**). Emojis only at the start of lines.\n\nFormat:"
        "\n🔤 Word / Phrase: ...\n📊 Level (CEFR): ...\n🎙 Transcription:"
        " ...\n🧠 Meaning: ...\n💡 Example: ...\n🇺🇿 Translation: ..."
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
  except Exception:
    await message.answer("Error / Xatolik / Ошибка")


# Esse mavzusini qabul qilish
@dp.message(BotStates.waiting_for_essay_topic)
async def process_essay_topic(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = user_data.get(user_id, {}).get("lang", "uz")
  await state.update_data(essay_topic=message.text)
  await state.set_state(BotStates.waiting_for_essay_photo_or_text)

  msgs = {
      "uz": "✅ Mavzu qabul qilindi! Endi esse matnini yoki rasmini yuboring:",
      "en": "✅ Topic received! Now send the essay text or photo:",
      "ru": "✅ Тема принята! Теперь отправьте текст или фото эссе:",
  }
  await message.answer(msgs.get(lang, msgs["uz"]))


# Esse tekshiruvi (Rasm yoki Matn)
@dp.message(BotStates.waiting_for_essay_photo_or_text)
async def process_essay_submission(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  lang = user_data.get(user_id, {}).get("lang", "uz")
  check_and_reset_limits(user_id)

  if user_data[user_id]["essays_count"] >= 5:
    msgs = {
        "uz": "❌ Kunlik esse tekshirish limitingiz tugadi (5/5).",
        "en": "❌ Daily essay check limit reached (5/5).",
        "ru": "❌ Лимит проверки эссе на сегодня исчерпан (5/5).",
    }
    await message.answer(
        msgs.get(lang, msgs["uz"]), reply_markup=get_main_menu(lang, user_id)
    )
    await state.clear()
    return

  user_data[user_id]["essays_count"] += 1
  update_request_stats()
  data = await state.get_data()
  topic = data.get("essay_topic", "Topic")

  await bot.send_chat_action(chat_id=message.chat.id, action="typing")
  essay_content = ""

  if message.photo:
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    essay_content = f"[Photo uploaded by user]"
  else:
    essay_content = message.text

  try:
    prompt = (
        f"Act as an expert IELTS examiner. Topic: {topic}\nEssay: {essay_content}"
        f"\nLanguage for response: '{lang}'. Rules: NO asterisks (**). Emojis"
        " only at the start of lines.\n\nFormat:\n📊 IELTS Band Score: [...]"
        "\n⭐ Examiner Feedback: [...]\n❌ Mistakes: [...]\n🛠 Improved"
        " Version: [...]\n💡 Tip: [...]"
    )

    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2048,
    )

    await message.answer(
        completion.choices[0].message.content,
        reply_markup=get_main_menu(lang, user_id),
    )
    await state.clear()
  except Exception as e:
    print(f"Xato: {e}")
    await message.answer(
        "Error / Xatolik", reply_markup=get_main_menu(lang, user_id)
    )


# 18+ filtri va boshqa xabarlar uchun yo'naltiruvchi handler
@dp.message()
async def general_message_handler(message: types.Message):
  user_id = message.from_user.id
  lang = user_data.get(user_id, {}).get("lang", "uz")
  text_lower = message.text.lower()

  # 18+ va taqiqlangan so'zlar filtri
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
  if any(word in text_lower for word in forbidden_words):
    msgs = {
        "uz": "❌ Kechirasiz, 18+ yoki taqiqlangan kontentga javob bera olmayman.",
        "en": "❌ Sorry, I cannot process 18+ or prohibited content.",
        "ru": (
            "❌ Извините, я не могу обрабатывать контент для взрослых или"
            " запрещенный контент."
        ),
    }
    await message.answer(
        msgs.get(lang, msgs["uz"]), reply_markup=get_main_menu(lang, user_id)
    )
    return

  # Agar foydalanuvchi so'z yoki esse so'ramasdan boshqa narsa yozsa
  msgs = {
      "uz": (
          "⚠️ Iltimos, so'z yoki esse tahlil qilish uchun quyidagi tugmalardan"
          " foydalaning:"
      ),
      "en": "⚠️ Please use the buttons below to analyze words or essays:",
      "ru": (
          "⚠️ Пожалуйста, используйте кнопки ниже для анализа слов или эссе:"
      ),
  }
  await message.answer(
      msgs.get(lang, msgs["uz"]), reply_markup=get_main_menu(lang, user_id)
  )


async def main():
  logging.basicConfig(level=logging.INFO, stream=sys.stdout)
  print("Bot barcha funksiyalar bilan mukammal ishga tushdi...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())