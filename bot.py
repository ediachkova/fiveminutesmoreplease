import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import pytz

from database import Database
from config import BOT_TOKEN, TIMEZONE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=TIMEZONE)
db = Database()

# ─── States ───────────────────────────────────────────────────────────────────

class PlanStates(StatesGroup):
    choosing_period = State()
    choosing_day = State()
    entering_task_name = State()
    entering_task_time = State()
    confirm_more_tasks = State()

# ─── Keyboards ────────────────────────────────────────────────────────────────

def kb_period():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 День",   callback_data="period_day")],
        [InlineKeyboardButton(text="📆 Неделя", callback_data="period_week")],
        [InlineKeyboardButton(text="🗓 Месяц",  callback_data="period_month")],
    ])

def kb_days(days: list[str], selected: list[str]):
    rows = []
    for d in days:
        check = "✅ " if d in selected else ""
        rows.append([InlineKeyboardButton(text=f"{check}{d}", callback_data=f"day_{d}")])
    rows.append([InlineKeyboardButton(text="➡️ Готово", callback_data="days_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_more_tasks():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить ещё задачу", callback_data="more_tasks")],
        [InlineKeyboardButton(text="✅ Закончить",           callback_data="finish_day")],
    ])

def kb_reminder(task_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сделал",             callback_data=f"done_{task_id}")],
        [InlineKeyboardButton(text="🔄 В процессе",         callback_data=f"inprogress_{task_id}")],
        [InlineKeyboardButton(text="⏰ Ещё 5 минуточек",   callback_data=f"snooze_{task_id}")],
    ])

def kb_report():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мой отчёт", callback_data="show_report")],
    ])

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_days_for_period(period: str, start: datetime) -> list[str]:
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).date()
    if period == "day":
        return [today.strftime("%d.%m.%Y")]
    elif period == "week":
        return [(today + timedelta(days=i)).strftime("%d.%m.%Y") for i in range(7)]
    else:  # month
        return [(today + timedelta(days=i)).strftime("%d.%m.%Y") for i in range(30)]

async def send_reminder(chat_id: int, task_id: int):
    task = db.get_task(task_id)
    if not task or task["status"] == "done":
        return
    text = (
        f"🔔 <b>Напоминание!</b>\n\n"
        f"📌 <b>{task['name']}</b>\n"
        f"🕐 {task['start_time']} – {task['end_time']}\n"
        f"📅 {task['day']}\n\n"
        f"Как дела с этой задачей?"
    )
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb_reminder(task_id))
        db.update_task_status(task_id, "reminded")
        # schedule next auto-repeat if no response in 5 min
        schedule_auto_repeat(chat_id, task_id, minutes=5)
    except Exception as e:
        logger.error(f"Error sending reminder: {e}")

def schedule_reminder(chat_id: int, task_id: int, task_day: str, start_time: str):
    tz = pytz.timezone(TIMEZONE)
    try:
        run_at = datetime.strptime(f"{task_day} {start_time}", "%d.%m.%Y %H:%M")
        run_at = tz.localize(run_at)
        now = datetime.now(tz)
        if run_at <= now:
            return  # already past
        job_id = f"remind_{task_id}"
        scheduler.add_job(
            send_reminder,
            trigger=DateTrigger(run_date=run_at),
            args=[chat_id, task_id],
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled reminder for task {task_id} at {run_at}")
    except Exception as e:
        logger.error(f"Error scheduling: {e}")

def schedule_auto_repeat(chat_id: int, task_id: int, minutes: int = 5):
    tz = pytz.timezone(TIMEZONE)
    run_at = datetime.now(tz) + timedelta(minutes=minutes)
    job_id = f"repeat_{task_id}"
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=run_at),
        args=[chat_id, task_id],
        id=job_id,
        replace_existing=True,
    )

def cancel_repeat_job(task_id: int):
    job_id = f"repeat_{task_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

def schedule_at_time(chat_id: int, task_id: int, run_at):
    job_id = f"repeat_{task_id}"
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=run_at),
        args=[chat_id, task_id],
        id=job_id,
        replace_existing=True,
    )

# ─── /start ───────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    db.ensure_user(message.from_user.id)
    await state.clear()
    await message.answer(
        "👋 <b>Привет! Я бот-планировщик.</b>\n\n"
        "Помогу спланировать дела и напомню о каждом в нужное время.\n\n"
        "Чтобы начать планирование — /plan\n"
        "Посмотреть отчёт — /report",
        parse_mode="HTML",
    )

# ─── /plan ────────────────────────────────────────────────────────────────────

@dp.message(Command("plan"))
async def cmd_plan(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📋 <b>На сколько хотите планировать?</b>",
        parse_mode="HTML",
        reply_markup=kb_period(),
    )
    await state.set_state(PlanStates.choosing_period)

@dp.callback_query(PlanStates.choosing_period, F.data.startswith("period_"))
async def cb_period(call: types.CallbackQuery, state: FSMContext):
    period = call.data.split("_")[1]
    tz = pytz.timezone(TIMEZONE)
    days = get_days_for_period(period, datetime.now(tz))
    await state.update_data(period=period, all_days=days, selected_days=[], tasks_by_day={})
    label = {"day": "день", "week": "неделю", "month": "месяц"}[period]
    await call.message.edit_text(
        f"✅ Выбрано: <b>{label}</b>\n\n"
        "📅 <b>Выберите дни для планирования</b> (можно несколько):",
        parse_mode="HTML",
        reply_markup=kb_days(days[:14], []),  # show max 14 days to avoid huge kb
    )
    await state.set_state(PlanStates.choosing_day)

@dp.callback_query(PlanStates.choosing_day, F.data.startswith("day_"))
async def cb_day_toggle(call: types.CallbackQuery, state: FSMContext):
    day = call.data[4:]
    data = await state.get_data()
    selected = data.get("selected_days", [])
    if day in selected:
        selected.remove(day)
    else:
        selected.append(day)
    await state.update_data(selected_days=selected)
    await call.message.edit_reply_markup(
        reply_markup=kb_days(data["all_days"][:14], selected)
    )
    await call.answer()

@dp.callback_query(PlanStates.choosing_day, F.data == "days_done")
async def cb_days_done(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_days", [])
    if not selected:
        await call.answer("Выберите хотя бы один день!", show_alert=True)
        return
    # Start with first day
    first_day = selected[0]
    await state.update_data(
        pending_days=selected,
        current_day=first_day,
        tasks_by_day={d: [] for d in selected}
    )
    await call.message.edit_text(
        f"📅 <b>День: {first_day}</b>\n\n"
        "✏️ Введите название задачи:",
        parse_mode="HTML",
    )
    await state.set_state(PlanStates.entering_task_name)

# ─── Task entry ───────────────────────────────────────────────────────────────

@dp.message(PlanStates.entering_task_name)
async def enter_task_name(message: types.Message, state: FSMContext):
    await state.update_data(current_task_name=message.text.strip())
    await message.answer(
        "🕐 <b>Укажите время задачи</b>\n\n"
        "Формат: <code>ЧЧ:ММ-ЧЧ:ММ</code>\nПример: <code>09:00-10:30</code>",
        parse_mode="HTML",
    )
    await state.set_state(PlanStates.entering_task_time)

@dp.message(PlanStates.entering_task_time)
async def enter_task_time(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    try:
        parts = raw.split("-")
        if len(parts) != 2:
            raise ValueError()
        t_start = datetime.strptime(parts[0].strip(), "%H:%M").strftime("%H:%M")
        t_end   = datetime.strptime(parts[1].strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Введите время как <code>09:00-10:30</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    task_name = data["current_task_name"]
    current_day = data["current_day"]
    tasks_by_day = data["tasks_by_day"]
    tasks_by_day[current_day].append({"name": task_name, "start": t_start, "end": t_end})
    await state.update_data(tasks_by_day=tasks_by_day)

    await message.answer(
        f"✅ <b>{task_name}</b> ({t_start}–{t_end}) добавлена!\n\n"
        f"Что дальше для <b>{current_day}</b>?",
        parse_mode="HTML",
        reply_markup=kb_more_tasks(),
    )
    await state.set_state(PlanStates.confirm_more_tasks)

@dp.callback_query(PlanStates.confirm_more_tasks, F.data == "more_tasks")
async def cb_more_tasks(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await call.message.edit_text(
        f"📅 <b>День: {data['current_day']}</b>\n\n"
        "✏️ Введите название следующей задачи:",
        parse_mode="HTML",
    )
    await state.set_state(PlanStates.entering_task_name)

@dp.callback_query(PlanStates.confirm_more_tasks, F.data == "finish_day")
async def cb_finish_day(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pending = data["pending_days"]
    current = data["current_day"]
    pending.remove(current)

    if pending:
        next_day = pending[0]
        await state.update_data(pending_days=pending, current_day=next_day)
        await call.message.edit_text(
            f"📅 <b>Теперь планируем: {next_day}</b>\n\n"
            "✏️ Введите название задачи:",
            parse_mode="HTML",
        )
        await state.set_state(PlanStates.entering_task_name)
    else:
        # Save everything
        tasks_by_day = data["tasks_by_day"]
        user_id = call.from_user.id
        total = 0
        for day, tasks in tasks_by_day.items():
            for t in tasks:
                task_id = db.add_task(user_id, day, t["name"], t["start"], t["end"])
                schedule_reminder(user_id, task_id, day, t["start"])
                total += 1

        summary_lines = [f"🎉 <b>Планирование завершено!</b>\n\nДобавлено задач: <b>{total}</b>\n"]
        for day, tasks in tasks_by_day.items():
            if tasks:
                summary_lines.append(f"\n📅 <b>{day}</b>")
                for t in tasks:
                    summary_lines.append(f"  • {t['name']} ({t['start']}–{t['end']})")
        summary_lines.append("\n\n⏰ Я напомню о каждой задаче в указанное время!")

        await call.message.edit_text(
            "".join(summary_lines),
            parse_mode="HTML",
            reply_markup=kb_report(),
        )
        await state.clear()

# ─── Reminder callbacks ───────────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("done_"))
async def cb_done(call: types.CallbackQuery):
    task_id = int(call.data.split("_")[1])
    cancel_repeat_job(task_id)
    db.update_task_status(task_id, "done")
    task = db.get_task(task_id)
    await call.message.edit_text(
        f"✅ <b>Отлично!</b> Задача выполнена в срок!\n"
        f"📌 <i>{task['name']}</i>",
        parse_mode="HTML",
    )
    await call.answer("👍 Молодец!")

@dp.callback_query(F.data.startswith("inprogress_"))
async def cb_inprogress(call: types.CallbackQuery):
    task_id = int(call.data.split("_")[1])
    cancel_repeat_job(task_id)
    db.update_task_status(task_id, "in_progress")
    task = db.get_task(task_id)
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    try:
        end_dt = tz.localize(datetime.strptime(f"{task['day']} {task['end_time']}", "%d.%m.%Y %H:%M"))
        remind_at = end_dt - timedelta(minutes=5)
        if remind_at > now:
            note = f"Напомню в {remind_at.strftime('%H:%M')} — за 5 минут до конца."
        else:
            remind_at = now + timedelta(minutes=1)
            note = "Задача вот-вот закончится, напомню через минуту."
        schedule_at_time(call.from_user.id, task_id, remind_at)
    except Exception:
        schedule_auto_repeat(call.from_user.id, task_id, minutes=5)
        note = "Напомню через 5 минут."
    await call.message.edit_text(
        f"🔄 <b>Хорошо, продолжай!</b>\n"
        f"📌 <i>{task['name']}</i>\n\n"
        f"{note}",
        parse_mode="HTML",
    )
    await call.answer("Удачи!")

@dp.callback_query(F.data.startswith("snooze_"))
async def cb_snooze(call: types.CallbackQuery):
    task_id = int(call.data.split("_")[1])
    cancel_repeat_job(task_id)
    db.update_task_status(task_id, "snoozed")
    task = db.get_task(task_id)
    await call.message.edit_text(
        f"⏰ <b>Ещё 5 минуточек...</b>\n"
        f"📌 <i>{task['name']}</i>\n\n"
        f"Напомню в {(datetime.now() + timedelta(minutes=5)).strftime('%H:%M')}",
        parse_mode="HTML",
    )
    schedule_auto_repeat(call.from_user.id, task_id, minutes=5)
    await call.answer("⏰ Хорошо, 5 минут!")

# ─── /report ──────────────────────────────────────────────────────────────────

@dp.message(Command("report"))
async def cmd_report(message: types.Message):
    await show_report(message.from_user.id, message)

@dp.callback_query(F.data == "show_report")
async def cb_show_report(call: types.CallbackQuery):
    await show_report(call.from_user.id, call.message)
    await call.answer()

async def show_report(user_id: int, target):
    stats = db.get_stats(user_id)
    total = stats["total"]
    done = stats["done"]
    snoozed = stats["snoozed"]
    pending = stats["pending"]
    pct = round(done / total * 100) if total else 0

    bar_done   = "🟩" * (done   if done   <= 10 else 10)
    bar_snooze = "🟨" * (min(snoozed, 10))
    bar_pend   = "⬜" * (min(pending, 5))

    text = (
        f"📊 <b>Ваш отчёт</b>\n\n"
        f"📋 Всего задач: <b>{total}</b>\n"
        f"✅ Выполнено в срок: <b>{done}</b> {bar_done}\n"
        f"⏰ Отложено: <b>{snoozed}</b> {bar_snooze}\n"
        f"⏳ Не отвечено: <b>{pending}</b> {bar_pend}\n\n"
        f"🎯 Эффективность: <b>{pct}%</b>"
    )
    if total > 0:
        if pct >= 80:
            text += "\n\n🏆 <i>Ты продуктивный человек!</i>"
        elif pct >= 50:
            text += "\n\n💪 <i>Неплохо, но есть куда расти!</i>"
        else:
            text += "\n\n😅 <i>Попробуй меньше откладывать!</i>"

    if isinstance(target, types.Message):
        await target.answer(text, parse_mode="HTML")
    else:
        await target.answer(text, parse_mode="HTML")

# ─── /mytasks ─────────────────────────────────────────────────────────────────

@dp.message(Command("mytasks"))
async def cmd_mytasks(message: types.Message):
    tasks = db.get_upcoming_tasks(message.from_user.id)
    if not tasks:
        await message.answer("📭 Нет запланированных задач.\n\n/plan — начать планирование")
        return
    lines = ["📋 <b>Ваши предстоящие задачи:</b>\n"]
    current_day = None
    for t in tasks:
        if t["day"] != current_day:
            current_day = t["day"]
            lines.append(f"\n📅 <b>{current_day}</b>")
        status_icon = {"done": "✅", "in_progress": "🔄", "snoozed": "⏰", "reminded": "🔔"}.get(t["status"], "⏳")
        lines.append(f"  {status_icon} {t['name']} ({t['start_time']}–{t['end_time']})")
    await message.answer("\n".join(lines), parse_mode="HTML")

# ─── /help ────────────────────────────────────────────────────────────────────

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🤖 <b>Команды:</b>\n\n"
        "/plan — начать планирование\n"
        "/mytasks — посмотреть задачи\n"
        "/report — статистика выполнения\n"
        "/help — эта справка\n\n"
        "⏰ <b>Как работают напоминания:</b>\n"
        "В указанное время бот пришлёт напоминание.\n"
        "Если не ответить — напомнит через 5 минут.\n"
        "Кнопка «Ещё 5 минуточек» — отложит на 5 мин.",
        parse_mode="HTML",
    )

# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    db.init()
    scheduler.start()
    # Drop any lingering webhook and clear update queue
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
