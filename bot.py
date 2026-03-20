```python
import os
import asyncio
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.filters import CommandStart, Command

# ===== ИМПОРТ НАШЕГО AI =====
from backend import chat, clear_history

# ===== LOAD =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# =====================================================
# ================== UI ================================
# =====================================================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="💻 Code Mode"),
            KeyboardButton(text="💬 Chat Mode")
        ],
        [
            KeyboardButton(text="🧹 Clear Memory"),
            KeyboardButton(text="⚡ Help")
        ]
    ],
    resize_keyboard=True
)

# режим пользователя
user_modes = {}

# =====================================================
# ================== START =============================
# =====================================================

@dp.message(CommandStart())
async def start(message: Message):
    user_modes[message.from_user.id] = "chat"

    await message.answer(
        "🤖 AI Assistant ready.\n\n"
        "• Chat Mode — обычный диалог\n"
        "• Code Mode — генерация чистого кода\n\n"
        "Выбери режим ниже 👇",
        reply_markup=main_keyboard
    )

# =====================================================
# ================== HELP ==============================
# =====================================================

@dp.message(Command("help"))
@dp.message(F.text == "⚡ Help")
async def help_cmd(message: Message):
    await message.answer(
        "📘 Возможности:\n\n"
        "• Генерация кода\n"
        "• Исправление ошибок\n"
        "• Умные ответы\n"
        "• Память диалога\n\n"
        "⚙️ Кнопки:\n"
        "💻 Code Mode — режим программирования\n"
        "💬 Chat Mode — обычный режим\n"
        "🧹 Clear Memory — очистка памяти"
    )

# =====================================================
# ================== MODE SWITCH =======================
# =====================================================

@dp.message(F.text == "💻 Code Mode")
async def code_mode(message: Message):
    user_modes[message.from_user.id] = "code"
    await message.answer("💻 Code Mode активирован")

@dp.message(F.text == "💬 Chat Mode")
async def chat_mode(message: Message):
    user_modes[message.from_user.id] = "chat"
    await message.answer("💬 Chat Mode активирован")

# =====================================================
# ================== CLEAR =============================
# =====================================================

@dp.message(F.text == "🧹 Clear Memory")
async def clear(message: Message):
    clear_history(str(message.from_user.id))
    await message.answer("🧹 Память очищена")

# =====================================================
# ================== MAIN CHAT =========================
# =====================================================

@dp.message()
async def handle_message(message: Message):
    user_id = str(message.from_user.id)
    text = message.text

    # индикатор печати
    await bot.send_chat_action(message.chat.id, "typing")

    try:
        # режим
        mode = user_modes.get(message.from_user.id, "chat")

        if mode == "code":
            text = f"Write code:\n{text}"

        # вызываем AI
        response = chat(user_id, text)

        # Telegram лимит
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await message.answer(response[i:i+4000])
        else:
            await message.answer(response)

    except Exception as e:
        await message.answer("❌ Ошибка обработки запроса")

# =====================================================
# ================== RUN ===============================
# =====================================================

async def main():
    print("🚀 Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```
