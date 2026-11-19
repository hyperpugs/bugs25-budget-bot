import os, json, asyncio
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
PORT = int(os.getenv("PORT", 8080))
DATA_FILE = "/app/budget_data.json"

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- БОТ ----------
bot = Bot(token=TOKEN)
dp = Dispatcher()

user_state = {}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.chat.id
    data = load_data()
    if str(uid) not in data:
        data[str(uid)] = {"reminders": []}
        save_data(data)
    await message.answer("👋 Привет! /add_income, /add_expense, /remind, /report")

@dp.message(Command("add_income"))
async def cmd_add_income(message: types.Message):
    await message.answer("Введи сумму дохода (или /cancel):")
    user_state[message.chat.id] = {"action": "income"}
    await dp.set_state(message.from_user.id, "income_amount")

@dp.message(Command("add_expense"))
async def cmd_add_expense(message: types.Message):
    await message.answer("Введи сумму расхода (или /cancel):")
    user_state[message.chat.id] = {"action": "expense"}
    await dp.set_state(message.from_user.id, "expense_amount")

@dp.message(Command("remind"))
async def cmd_remind(message: types.Message):
    await message.answer("Введи дату (ГГГГ-ММ-ДД) и текст, например: 2025-04-28 Ипотека")
    user_state[message.chat.id] = {"action": "remind"}
    await dp.set_state(message.from_user.id, "remind_text")

@dp.message(Command("report"))
async def cmd_report(message: types.Message):
    data = load_data()
    uid = str(message.chat.id)
    user = data.get(uid, {})
    income = user.get("income", 0)
    expense = sum(c.get("fact",0) for c in user.get("categories",{}).values())
    balance = income - expense
    await message.answer(f"📊 Отчёт: доход {income}₽, расход {expense}₽, остаток {balance}₽")

@dp.message(lambda msg: dp.current_state(msg.from_user.id) == "income_amount")
async def process_income_amount(message: types.Message):
    try: amount = int(message.text)
    except:
        await message.answer("Ошибка, введи число.")
        return
    data = load_data()
    uid = str(message.chat.id)
    data[uid]["income"] = data[uid].get("income", 0) + amount
    save_data(data)
    await message.answer(f"Доход +{amount} ₽ учтён.")
    await dp.clear_state(message.from_user.id)

@dp.message(lambda msg: dp.current_state(msg.from_user.id) == "expense_amount")
async def process_expense_amount(message: types.Message):
    try: amount = int(message.text)
    except:
        await message.answer("Ошибка, введи число.")
        return
    data = load_data()
    uid = str(message.chat.id)
    if "categories" not in data[uid]:
        data[uid]["categories"] = {}
    cat = data[uid]["categories"].get("🆘 Непредвиденное", {"plan":0, "fact":0})
    cat["fact"] = cat.get("fact",0) + amount
    data[uid]["categories"]["🆘 Непредвиденное"] = cat
    save_data(data)
    await message.answer(f"Расход +{amount} ₽ учтён.")
    await dp.clear_state(message.from_user.id)

@dp.message(lambda msg: dp.current_state(msg.from_user.id) == "remind_text")
async def process_remind(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Неверный формат. Пример: 2025-04-28 Ипотека")
        return
    date_str, title = parts
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except:
        await message.answer("Дата должна быть ГГГГ-ММ-ДД")
        return
    data = load_data()
    uid = str(message.chat.id)
    data[uid].setdefault("reminders", []).append({
        "title": title, "date": date_str, "repeat": False, "sent": False
    })
    save_data(data)
    await message.answer(f"Напоминание '{title}' на {date_str} добавлено.")
    await dp.clear_state(message.from_user.id)

async def webhook(request: Request):
    await dp.feed_update(bot, await request.json())
    return {"ok": True}

# ---------- ПЛАНЕР ----------
@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/send")
async def send_from_planner(text: str):
    data = load_data()
    for uid in data.keys():
        try:
            await bot.send_message(int(uid), f"📌 *Из планера:* {text}")
        except:
            pass
    return {"status": "ok"}

# ---------- ФОНОВЫЕ ЗАДАЧИ ----------
async def check_reminders():
    while True:
        now = datetime.now()
        data = load_data()
        for uid, user in data.items():
            for rem in user.get("reminders", []):
                rem_date = datetime.strptime(rem["date"], "%Y-%m-%d")
                if now.date() == rem_date.date() and not rem.get("sent", False):
                    try:
                        await bot.send_message(int(uid), f"🔔 *Напоминание:* {rem['title']} ({rem['date']})")
                        rem["sent"] = True
                    except:
                        pass
        save_data(data)
        await asyncio.sleep(1800)

async def monthly_reminder():
    while True:
        now = datetime.now()
        if now.day == 28:
            data = load_data()
            for uid in data.keys():
                try:
                    await bot.send_message(int(uid), "📅 *28 число* – не забудь заполнить планер на следующий месяц!")
                except:
                    pass
        await asyncio.sleep(86400)

@app.on_event("startup")
async def startup():
    asyncio.create_task(check_reminders())
    asyncio.create_task(monthly_reminder())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)