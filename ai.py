# ai_groq_chat_safe_markdown.py
import os
import asyncio
import re
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State


# ===========================
# 🔑 ТВОЇ ТОКЕНИ
# ===========================
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ===========================
# 🔥 Авто-визначення мови коду
# ===========================
def detect_language(text: str):
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
# 🔒 MarkdownV2 escape
# ===========================
def escape_md(text: str):
    # забираємо блоки коду
    code_blocks = re.findall(r"```.*?```", text, flags=re.DOTALL)
    placeholders = {}

    for i, block in enumerate(code_blocks):
        key = f"__CB_{i}__"
        placeholders[key] = block
        text = text.replace(block, key)

    # Telegram V2 — екрануємо ВСЕ, включно з крапкою.
    esc = (
        text.replace('\\', '\\\\')
            .replace('_', '\\_')
            .replace('*', '\\*')
            .replace('[', '\\[')
            .replace(']', '\\]')
            .replace('(', '\\(')
            .replace(')', '\\)')
            .replace('~', '\\~')
            .replace('`', '\\`')
            .replace('>', '\\>')
            .replace('#', '\\#')
            .replace('+', '\\+')
            .replace('-', '\\-')
            .replace('=', '\\=')
            .replace('|', '\\|')
            .replace('{', '\\{')
            .replace('}', '\\}')
            .replace('.', '\\.')  # ← повертаємо крапку!
            .replace('!', '\\!')
    )

    # повертаємо блоки коду назад
    for key, block in placeholders.items():
        esc = esc.replace(key, block)

    return esc



# ===========================
# 🔥 Автоматичне огортання коду
# ===========================
def wrap_code_blocks(text: str):
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
# FSM
# ===========================
class Chat(StatesGroup):
    chatting = State()


# ===========================
# /start
# ===========================
@dp.message(CommandStart())
async def start(m: types.Message, state: FSMContext):
    await state.set_state(Chat.chatting)
    await state.set_data({"history": []})

    await m.answer(
        "Привіт! Я — AI-чат на Groq.\n"
        "Я вмію:\n"
        "• правильно форматувати код\n"
        "• автоматично визначати мову (Python, C++, JS, HTML)\n"
        "• виводити чорні Telegram-блоки\n\n"
        "Пиши будь-що!\n"
        "/new — очистити чат"
    )


# ===========================
# /new
# ===========================
@dp.message(lambda m: m.text and m.text.lower() in ["/new", "новий чат"])
async def new_chat(m: types.Message, state: FSMContext):
    await state.set_data({"history": []})
    await m.answer("Чат очищено!")


# ===========================
# 🔥 Основний обробник
# ===========================
@dp.message(Chat.chatting)
async def handle(m: types.Message, state: FSMContext):

    await bot.send_chat_action(m.chat.id, "typing")

    data = await state.get_data()
    history = data.get("history", [])

    # 🔥 Фільтруємо плейсхолдери з історії
    clean_history = []
    for msg in history:
        if "__CODE_BLOCK_" not in msg["content"] and "__CB_" not in msg["content"]:
            clean_history.append(msg)

    history = clean_history
    history.append({"role": "user", "content": m.text})

    # SYSTEM PROMPT — відкоригований і стабільний
    system_msg = {
        "role": "system",
        "content": (
            "Ти — технічний AI-помічник. Відповідай українською.\n\n"
            "=== ПРАВИЛА ВИВОДУ КОДУ ===\n"
            "1) Якщо відповідь містить код — завжди вставляй справжні Markdown-блоки:\n"
            "```cpp\n// код\n```\n"
            "або ```python, ```javascript, ```html, ```text.\n\n"
            "2) Заборонено вставляти будь-які плейсхолдери типу __CODE_BLOCK_X__.\n"
            "3) Можеш використовувати будь-які символи — (), [], {}, <>, ., :, ;, +, -, *, /, =.\n"
            "4) Усередині блоків коду нічого не екрануй.\n"
            "5) Якщо є кілька кодових блоків — оформлюй кожен окремо.\n"
        )
    }

    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[system_msg] + history,
            temperature=0.7,
            max_tokens=2048
        )
        reply = response.choices[0].message.content
    except Exception as e:
        await m.answer(f"Помилка: {e}")
        return

    history.append({"role": "assistant", "content": reply})
    await state.update_data(history=history)

    reply = wrap_code_blocks(reply)
    safe_text = escape_md(reply)

    await m.answer(reply)



# ===========================
# RUN
# ===========================
async def main():
    print("Бот запущено")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
