import asyncio
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ---------- FastAPI (веб-планер) ----------
app = FastAPI(title="Budget Planner")

class Expense(BaseModel):
    category: str
    amount: float
    description: str = ""

expenses = []

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head><title>Budget Planner</title></head>
        <body>
            <h1>💰 Budget Bot is running</h1>
            <p>Use Telegram bot to manage expenses.</p>
            <p>POST /add-expense to add an expense (JSON).</p>
        </body>
    </html>
    """

@app.post("/add-expense")
async def add_expense(expense: Expense):
    expenses.append(expense.dict())
    return {"status": "ok", "expense": expense.dict()}

@app.get("/expenses")
async def get_expenses():
    return expenses

# ---------- Aiogram (Telegram бот) ----------
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот для учёта бюджета.\n"
        "Команды:\n"
        "/add <категория> <сумма> <описание> — добавить расход\n"
        "/balance — показать баланс (заглушка)\n"
        "/expenses — список расходов"
    )

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        return await message.answer("Формат: /add <категория> <сумма> <описание>")
    category = args[1]
    try:
        amount = float(args[2])
    except ValueError:
        return await message.answer("Сумма должна быть числом")
    description = args[3] if len(args) > 3 else ""
    expenses.append({"category": category, "amount": amount, "description": description})
    await message.answer(f"✅ Добавлено: {category} {amount}₽ ({description})")

@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    total = sum(e["amount"] for e in expenses)
    await message.answer(f"💸 Общий расход: {total}₽")

@dp.message(Command("expenses"))
async def cmd_expenses(message: types.Message):
    if not expenses:
        return await message.answer("Расходов пока нет")
    text = "\n".join(
        f"{i+1}. {e['category']} — {e['amount']}₽ ({e['description']})"
        for i, e in enumerate(expenses)
    )
    await message.answer(text)

async def main():
    # Запускаем веб-сервер (uvicorn) в фоне
    import uvicorn
    task = asyncio.create_task(uvicorn.run(app, host="0.0.0.0", port=8000))
    # Запускаем бота (поллинг)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
