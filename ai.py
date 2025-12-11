# ai.py

import os
import asyncio
import re

from groq import Groq
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


# ===========================
# 🔑 ТВОЇ ТОКЕНИ
# ===========================
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN or not GROQ_API_KEY:
    raise RuntimeError("Не задані змінні середовища TOKEN або GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ===========================
# ⚙️ Моделі та режими
# ===========================
MODELS = {
    "8B": "llama-3.1-8b-instant",
    "70B": "llama-3.1-70b-versatile",
    "SCOUT": "meta-llama/llama-4-scout-17b-16e-instruct",
}

MODEL_ORDER = ["8B", "70B", "SCOUT"]
DEFAULT_MODEL_KEY = "SCOUT"

ANSWER_MODES = {
    "short": "Відповідай дуже коротко, 1–3 речення.",
    "deep": "Давай детальну, але зрозумілу відповідь з прикладами.",
    "expert": "Відповідай як senior-розробник, структуровано й технічно.",
}
ANSWER_ORDER = ["short", "deep", "expert"]
DEFAULT_ANSWER_MODE = "deep"


# ===========================
# 🧠 Визначення мови коду
# ===========================
def detect_language(text: str) -> str:
    t = text.lower()
    if "#include" in t or "std::" in t or "int main" in t:
        return "cpp"
    if "def " in t or "class " in t or "print(" in t:
        return "python"
    if "<html" in t or "<div" in t:
        return "html"
    if "function " in t or "console.log" in t:
        return "javascript"
    return "text"


# ===========================
# 🔲 Автоматичне огортання коду
# ===========================
def wrap_code(text: str) -> str:
    if "```" in text:
        return text

    lines = text.split("\n")
    suspicious = sum(
        any(x in line for x in (";", "{", "}", "#include", "int ", "->"))
        for line in lines
    )

    if suspicious >= 2:
        lang = detect_language(text)
        return f"```{lang}\n{text}\n```"

    return text


# ===========================
# 🧩 Витягання кодових блоків
# ===========================
CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)

def extract_code_blocks(text: str):
    return CODE_BLOCK_RE.findall(text)



# ===========================
# FSM
# ===========================
class Chat(StatesGroup):
    chatting = State()


# ===========================
# Клавіатура
# ===========================
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🆕 Новий чат"), KeyboardButton(text="💡 Приклади")],
        [KeyboardButton(text="🔄 Змінити модель"), KeyboardButton(text="🧠 Режим відповіді")],
        [KeyboardButton(text="🛠 Поясни код"), KeyboardButton(text="🎨 Переформатувати відповідь")],
        [KeyboardButton(text="📦 Код ON/OFF"), KeyboardButton(text="ℹ️ Про бота")],
    ],
    resize_keyboard=True,
)


# ===========================
# /start
# ===========================
@dp.message(CommandStart())
async def start(m: types.Message, state: FSMContext):
    await state.set_state(Chat.chatting)
    await state.set_data({
        "history": [],
        "model_key": DEFAULT_MODEL_KEY,
        "answer_mode": DEFAULT_ANSWER_MODE,
        "wrap_code": True,
        "awaiting_code_explain": False,
        "last_reply": "",
        "last_code_blocks": [],
    })

    await m.answer(
        "Привіт! Я — AI-чат на Groq (Llama-4 Scout).\n"
        "Пиши будь-що або вибери дію в меню.",
        reply_markup=main_menu,
    )


# ===========================
# 🆕 Новий чат
# ===========================
@dp.message(lambda m: m.text == "🆕 Новий чат")
async def new_chat(m, state):
    data = await state.get_data()
    await state.set_data({
        "history": [],
        "model_key": data["model_key"],
        "answer_mode": data["answer_mode"],
        "wrap_code": data["wrap_code"],
        "awaiting_code_explain": False,
        "last_reply": "",
        "last_code_blocks": [],
    })
    await m.answer("Чат очищено.")


# ===========================
# 💡 Приклади
# ===========================
@dp.message(lambda m: m.text == "💡 Приклади")
async def examples(m):
    await m.answer(
        "Приклади запитів:\n"
        "• Напиши функцію сортування в C++\n"
        "• Поясни SOLID\n"
        "• SQL JOIN приклад\n"
        "• Знайди помилку у Python коді\n"
        "• Зроби HTML шаблон\n"
    )


# ===========================
# 🔄 Зміна моделі
# ===========================
@dp.message(lambda m: m.text == "🔄 Змінити модель")
async def change_model(m, state):
    data = await state.get_data()
    current = data["model_key"]
    idx = MODEL_ORDER.index(current)
    new_key = MODEL_ORDER[(idx + 1) % len(MODEL_ORDER)]

    await state.update_data(model_key=new_key)
    await m.answer(f"Модель змінено: {new_key} → {MODELS[new_key]}")


# ===========================
# 🧠 Режим відповіді
# ===========================
@dp.message(lambda m: m.text == "🧠 Режим відповіді")
async def change_answer_mode(m, state):
    data = await state.get_data()
    current = data["answer_mode"]
    idx = ANSWER_ORDER.index(current)
    new_mode = ANSWER_ORDER[(idx + 1) % len(ANSWER_ORDER)]

    await state.update_data(answer_mode=new_mode)
    await m.answer(f"Режим відповіді: {new_mode.upper()}\n{ANSWER_MODES[new_mode]}")


# ===========================
# 📦 Код ON/OFF
# ===========================
@dp.message(lambda m: m.text == "📦 Код ON/OFF")
async def toggle_wrap_code(m, state):
    data = await state.get_data()
    new_val = not data["wrap_code"]
    await state.update_data(wrap_code=new_val)
    await m.answer(f"Автоматичне оформлення коду: {'ON' if new_val else 'OFF'}")


# ===========================
# ℹ️ Про бота
# ===========================
@dp.message(lambda m: m.text == "ℹ️ Про бота")
async def about(m, state):
    data = await state.get_data()
    await m.answer(
        f"🤖 AI-Chat Bot\n"
        f"Модель: {data['model_key']}\n"
        f"Режим: {data['answer_mode']}\n"
        f"Код wrap: {data['wrap_code']}"
    )


# ===========================
# 🛠 Поясни код
# ===========================
@dp.message(lambda m: m.text == "🛠 Поясни код")
async def explain_code_menu(m, state):
    data = await state.get_data()
    blocks = data["last_code_blocks"]

    if blocks:
        code = max(blocks, key=len)
        await explain_code(m, state, code)
    else:
        await state.update_data(awaiting_code_explain=True)
        await m.answer("Надішли код для пояснення.")


async def explain_code(m, state, code):
    data = await state.get_data()

    messages = [
        {"role": "system", "content": "Пояснюй код крок за кроком."},
        {"role": "user", "content": f"Поясни:\n```text\n{code}\n```"}
    ]

    def _call():
        return client.chat.completions.create(
            model=MODELS[data["model_key"]],
            messages=messages
        )

    resp = await asyncio.to_thread(_call)
    reply = resp.choices[0].message.content

    await m.answer(reply)

    await state.update_data(
        last_reply=reply,
        last_code_blocks=extract_code_blocks(reply)
    )


# ===========================
# 🎨 Переформатувати відповідь
# ===========================
@dp.message(lambda m: m.text == "🎨 Переформатувати відповідь")
async def reformat(m, state):
    data = await state.get_data()
    last = data["last_reply"]

    if not last:
        await m.answer("Немає останньої відповіді.")
        return

    messages = [
        {"role": "system", "content": "Переформатуй відповідь красиво і структуровано."},
        {"role": "user", "content": last}
    ]

    def _call():
        return client.chat.completions.create(
            model=MODELS[data["model_key"]],
            messages=messages
        )

    resp = await asyncio.to_thread(_call)
    reply = resp.choices[0].message.content

    await m.answer(reply)

    await state.update_data(
        last_reply=reply,
        last_code_blocks=extract_code_blocks(reply)
    )


# ===========================
# 🔥 Основний handler
# ===========================
@dp.message(Chat.chatting)
async def handle(m, state):
    data = await state.get_data()

    # Якщо очікуємо лише код
    if data["awaiting_code_explain"]:
        await state.update_data(awaiting_code_explain=False)
        await explain_code(m, state, m.text)
        return

    await bot.send_chat_action(m.chat.id, "typing")

    history = data["history"]
    model_key = data["model_key"]
    answer_mode = data["answer_mode"]
    wrap = data["wrap_code"]

    history.append({"role": "user", "content": m.text})

    system_prompt = (
        "Ти технічний AI.\n" +
        ANSWER_MODES[answer_mode]
    )

    messages = [{"role": "system", "content": system_prompt}] + history

    def _call():
        return client.chat.completions.create(
            model=MODELS[model_key],
            messages=messages
        )

    resp = await asyncio.to_thread(_call)
    reply = resp.choices[0].message.content

    if wrap:
        reply = wrap_code(reply)

    await m.answer(reply)

    history.append({"role": "assistant", "content": reply})

    await state.update_data(
        history=history,
        last_reply=reply,
        last_code_blocks=extract_code_blocks(reply)
    )


# ===========================
# RUN
# ===========================
async def main():
    print("Бот запущено.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
