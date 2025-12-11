# ai_groq_chat_full.py

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
# 🔑 ТВОЇ ТОКЕНИ (ENV у Railway)
# ===========================
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN or not GROQ_API_KEY:
    raise RuntimeError("Не задані змінні середовища TOKEN або GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ===========================
# ⚙️ Налаштування моделей та режимів
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
    if "<html" in t or "<div" in t or "<body" in t:
        return "html"
    if "function " in t or "console.log" in t or " => " in t:
        return "javascript"
    return "text"


# ===========================
# 📦 Автоматичне огортання всього тексту в ```код``` (якщо це схоже на код)
# ===========================
def wrap_code_blocks(text: str) -> str:
    if "```" in text:
        return text

    lines = text.strip().split("\n")
    if len(lines) < 2:
        return text

    suspicious = sum(
        any(sym in line for sym in (";", "(", ")", "{", "}", "=", "<", ">"))
        for line in lines
    )

    if suspicious >= 2:
        lang = detect_language(text)
        return f"```{lang}\n{text}\n```"

    return text


# ===========================
# 🧩 Діставання кодових блоків з відповіді
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
# Клавіатура меню
# ===========================
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🆕 Новий чат"), KeyboardButton(text="💡 Приклади")],
        [KeyboardButton(text="🔄 Змінити модель"), KeyboardButton(text="🧠 Режим відповіді")],
        [KeyboardButton(text="🛠 Поясни код"), KeyboardButton(text="🎨 Переформатувати відповідь")],
        [KeyboardButton(text="📦 Код у блоці ON/OFF"), KeyboardButton(text="ℹ️ Про бота")],
    ],
    resize_keyboard=True,
)


# ===========================
# /start
# ===========================
@dp.message(CommandStart())
async def start(m: types.Message, state: FSMContext):
    await state.set_state(Chat.chatting)
    await state.set_data(
        {
            "history": [],
            "model_key": DEFAULT_MODEL_KEY,
            "answer_mode": DEFAULT_ANSWER_MODE,
            "wrap_code": True,
            "awaiting_code_explain": False,
            "last_reply": "",
            "last_code_blocks": [],
        }
    )

    await m.answer(
        "Привіт! Я — AI-чат на Groq (Llama-4 Scout).\n"
        "Обери дію в меню або просто напиши свій запит.",
        reply_markup=main_menu,
    )


# ===========================
# 🆕 Новий чат
# ===========================
@dp.message(lambda m: m.text == "🆕 Новий чат")
async def menu_new(m: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.set_data(
        {
            "history": [],
            "model_key": data.get("model_key", DEFAULT_MODEL_KEY),
            "answer_mode": data.get("answer_mode", DEFAULT_ANSWER_MODE),
            "wrap_code": data.get("wrap_code", True),
            "awaiting_code_explain": False,
            "last_reply": "",
            "last_code_blocks": [],
        }
    )
    await m.answer("Чат очищено.")


# ===========================
# 💡 Приклади
# ===========================
@dp.message(lambda m: m.text == "💡 Приклади")
async def menu_examples(m: types.Message):
    text = (
        "Ось декілька прикладів запитів:\n\n"
        "1. Напиши функцію C++ для сортування масиву вставками.\n"
        "2. Поясни, що таке SOLID простими словами.\n"
        "3. Зроби SQL-запит з JOIN для вибірки замовлень і клієнтів.\n"
        "4. Знайди помилку в цьому коді Python і виправ.\n"
        "5. Згенеруй HTML-шаблон односторінкового сайту.\n"
        "6. Допоможи розвʼязати задачу з теорії ймовірностей.\n"
    )
    await m.answer(text)


# ===========================
# 🔄 Зміна моделі
# ===========================
@dp.message(lambda m: m.text == "🔄 Змінити модель")
async def menu_change_model(m: types.Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("model_key", DEFAULT_MODEL_KEY)

    idx = MODEL_ORDER.index(current) if current in MODEL_ORDER else 0
    new_key = MODEL_ORDER[(idx + 1) % len(MODEL_ORDER)]

    await state.update_data(model_key=new_key)
    await m.answer(f"Обрана модель: {new_key} → `{MODELS[new_key]}`")


# ===========================
# 🧠 Режим відповіді
# ===========================
@dp.message(lambda m: m.text == "🧠 Режим відповіді")
async def menu_answer_mode(m: types.Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("answer_mode", DEFAULT_ANSWER_MODE)

    idx = ANSWER_ORDER.index(current) if current in ANSWER_ORDER else 0
    new_mode = ANSWER_ORDER[(idx + 1) % len(ANSWER_ORDER)]

    await state.update_data(answer_mode=new_mode)
    desc = ANSWER_MODES[new_mode]
    await m.answer(f"Режим відповіді: {new_mode.upper()}\n{desc}")


# ===========================
# 📦 Код у блоці ON/OFF
# ===========================
@dp.message(lambda m: m.text == "📦 Код у блоці ON/OFF")
async def menu_code_wrap(m: types.Message, state: FSMContext):
    data = await state.get_data()
    new_val = not data.get("wrap_code", True)
    await state.update_data(wrap_code=new_val)
    status = "УВІМКНЕНО" if new_val else "ВИМКНЕНО"
    await m.answer(f"Автоматичне оформлення всього тексту як кодового блоку: {status}")


# ===========================
# ℹ️ Про бота
# ===========================
@dp.message(lambda m: m.text == "ℹ️ Про бота")
async def menu_about(m: types.Message, state: FSMContext):
    data = await state.get_data()
    model_key = data.get("model_key", DEFAULT_MODEL_KEY)
    answer_mode = data.get("answer_mode", DEFAULT_ANSWER_MODE)

    await m.answer(
        "🤖 AI-Chat Bot\n"
        f"🧠 Модель: {model_key} → {MODELS[model_key]}\n"
        f"📏 Режим відповіді: {answer_mode}\n"
        "⚙ Працює через Groq API + aiogram.\n"
    )


# ===========================
# 🛠 Поясни код
# ===========================
@dp.message(lambda m: m.text == "🛠 Поясни код")
async def menu_explain_code(m: types.Message, state: FSMContext):
    data = await state.get_data()
    blocks = data.get("last_code_blocks") or []

    if blocks:
        # беремо найбільший кодовий блок з останньої відповіді
        code = max(blocks, key=len)
        await _explain_code_internal(m, state, code)
    else:
        # немає збереженого коду — просимо надіслати
        await state.update_data(awaiting_code_explain=True)
        await m.answer("Надішли код, який потрібно пояснити.")


async def _explain_code_internal(m: types.Message, state: FSMContext, code: str):
    data = await state.get_data()
    model_key = data.get("model_key", DEFAULT_MODEL_KEY)

    system_prompt = (
        "Ти пояснюєш код українською мовою.\n"
        "Дай покроковий розбір, що робить код, важливі моменти та можливі помилки."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Поясни цей код:\n```text\n{code}\n```"},
    ]

    def _call():
        return client.chat.completions.create(
            model=MODELS[model_key],
            messages=messages,
            temperature=0.4,
            max_completion_tokens=1024,
            top_p=1,
        )

    await bot.send_chat_action(m.chat.id, "typing")
    resp = await asyncio.to_thread(_call)
    reply = resp.choices[0].message.content

    await m.answer(reply)

    # оновимо останню відповідь / код
    blocks = extract_code_blocks(reply)
    await state.update_data(last_reply=reply, last_code_blocks=blocks)


# ===========================
# 🎨 Переформатувати відповідь
# ===========================
@dp.message(lambda m: m.text == "🎨 Переформатувати відповідь")
async def menu_reformat_answer(m: types.Message, state: FSMContext):
    data = await state.get_data()
    last_reply = data.get("last_reply", "")

    if not last_reply:
        await m.answer("Поки що немає відповіді, яку можна переформатувати.")
        return

    model_key = data.get("model_key", DEFAULT_MODEL_KEY)

    system_prompt = (
        "Ти форматувальник тексту.\n"
        "Перепиши наступну відповідь більш читабельно: з заголовками, списками, "
        "чіткими блоками, але без вигадування нової інформації."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": last_reply},
    ]

    def _call():
        return client.chat.completions.create(
            model=MODELS[model_key],
            messages=messages,
            temperature=0.3,
            max_completion_tokens=1024,
            top_p=1,
        )

    await bot.send_chat_action(m.chat.id, "typing")
    resp = await asyncio.to_thread(_call)
    reply = resp.choices[0].message.content

    await m.answer(reply)

    blocks = extract_code_blocks(reply)
    await state.update_data(last_reply=reply, last_code_blocks=blocks)


# ===========================
# 🔥 Основний обробник повідомлень
# ===========================
@dp.message(Chat.chatting)
async def handle(m: types.Message, state: FSMContext):
    # Якщо ми чекаємо код для пояснення
    data = await state.get_data()
    if data.get("awaiting_code_explain"):
        await state.update_data(awaiting_code_explain=False)
        code_text = m.text
        await _explain_code_internal(m, state, code_text)
        return

    await bot.send_chat_action(m.chat.id, "typing")

    history = data.get("history", [])
    model_key = data.get("model_key", DEFAULT_MODEL_KEY)
    answer_mode = data.get("answer_mode", DEFAULT_ANSWER_MODE)
    wrap_code_flag = data.get("wrap_code", True)

    # очищаємо історію від технічних плейсхолдерів (на всякий випадок)
    clean_history = []
    for msg in history:
        if "__CB_" not in msg.get("content", ""):
            clean_history.append(msg)
    history = clean_history

    history.append({"role": "user", "content": m.text})

    style_instruction = ANSWER_MODES.get(answer_mode, "")

    system_msg = {
        "role": "system",
        "content": (
            "Ти — технічний AI-помічник. Відповідай українською.\n" + style_instruction
        ),
    }

    messages = [system_msg] + history

    def _call():
        return client.chat.completions.create(
            model=MODELS[model_key],
            messages=messages,
            temperature=0.7,
            max_completion_tokens=2048,
            top_p=1,
        )

    resp = await asyncio.to_thread(_call)
    reply = resp.choices[0].message.content

    # Авто-обгортання коду (опційно)
    if wrap_code_flag:
        reply = wrap_code_blocks(reply)

    await m.answer(reply)

    # Оновимо історію та останню відповідь
    history.append({"role": "assistant", "content": reply})
    code_blocks = extract_code_blocks(reply)

    await state.update_data(
        history=history,
        last_reply=reply,
        last_code_blocks=code_blocks,
    )


# ===========================
# RUN
# ===========================
async def main():
    print("Бот запущено")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
