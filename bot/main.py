import asyncio
import os
import httpx
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_URL = os.getenv("API_URL", "https://brknbad-production.up.railway.app")
SITE_URL = os.getenv("SITE_URL", "https://brknbad.github.io/brknbad/")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ──────────────────────────────────────────────────────────────────────────────
# FSM States
# ──────────────────────────────────────────────────────────────────────────────
class RegisterState(StatesGroup):
    waiting_nickname = State()

class RobState(StatesGroup):
    waiting_target = State()

class SellState(StatesGroup):
    waiting_item = State()
    waiting_amount = State()
    waiting_price = State()


# ──────────────────────────────────────────────────────────────────────────────
# KEYBOARDS
# ──────────────────────────────────────────────────────────────────────────────
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"),    KeyboardButton(text="🎒 Инвентарь")],
            [KeyboardButton(text="🧪 Варить"),      KeyboardButton(text="🏭 Лаборатория")],
            [KeyboardButton(text="🚚 Перевозка"),   KeyboardButton(text="🔫 Ограбить")],
            [KeyboardButton(text="💊 Магазин"),     KeyboardButton(text="🌐 Сайт")],
        ],
        resize_keyboard=True,
    )


def delivery_keyboard(deliveries: list):
    buttons = []
    for d in deliveries:
        status = "✅" if d["available"] else "⏳"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {d['emoji']} {d['name']} (${d['reward_min']:,}-${d['reward_max']:,})",
            callback_data=f"deliver_{d['id']}" if d["available"] else "deliver_unavailable"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def lab_keyboard(labs: dict, user_level: int):
    buttons = []
    for lab_id, cfg in labs.items():
        can = user_level >= cfg["required_level"]
        emoji = "✅" if can else "🔒"
        text = f"{emoji} {cfg['emoji']} {cfg['name']} — ${cfg['price']:,}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"buylab_{lab_id}" if can else "lab_locked")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def shop_keyboard():
    items = [
        ("methylamine", "🧪 Метиламин", 300),
        ("phosphorus",  "🔴 Фосфор",    150),
        ("acid",        "⚗️ Кислота",    200),
        ("packaging",   "📦 Упаковка",   50),
    ]
    buttons = []
    for ing, name, price in items:
        buttons.append([
            InlineKeyboardButton(text=f"{name} — ${price}/ед", callback_data=f"shop_10_{ing}"),
            InlineKeyboardButton(text="+10", callback_data=f"shop_10_{ing}"),
            InlineKeyboardButton(text="+50", callback_data=f"shop_50_{ing}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ──────────────────────────────────────────────────────────────────────────────
# API HELPERS
# ──────────────────────────────────────────────────────────────────────────────
async def api_get(path: str, **params):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_URL}{path}", params=params, timeout=10)
        return r.json()

async def api_post(path: str, data: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API_URL}{path}", json=data, timeout=10)
        return r.json()


# ──────────────────────────────────────────────────────────────────────────────
# /start — REGISTRATION
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    tg_id = str(message.from_user.id)
    result = await api_get(f"/api/user/{tg_id}")
    
    if "telegram_id" in result:
        await message.answer(
            f"🎩 С возвращением, <b>{result['nickname']}</b>!\n"
            f"Уровень: {result['level']} | Баланс: ${result['cash']:,.0f}\n"
            f"Ранг: {result['rank']}",
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "⚗️ <b>Добро пожаловать в Breaking Bad Online!</b>\n\n"
            "Здесь ты строишь криминальную империю.\n"
            "Варишь, торгуешь, грабишь — стань легендой.\n\n"
            "Для начала — придумай себе ник:",
            parse_mode="HTML"
        )
        await state.set_state(RegisterState.waiting_nickname)


@dp.message(RegisterState.waiting_nickname)
async def process_nickname(message: types.Message, state: FSMContext):
    nickname = message.text.strip()
    if len(nickname) < 3 or len(nickname) > 20:
        await message.answer("❌ Ник должен быть от 3 до 20 символов.")
        return
    if not nickname.replace("_", "").isalnum():
        await message.answer("❌ Только буквы, цифры и подчёркивания.")
        return

    tg_id = str(message.from_user.id)
    result = await api_post("/api/register", {"telegram_id": tg_id, "nickname": nickname})
    
    if result.get("ok") or result.get("message") == "already_exists":
        await state.clear()
        await message.answer(
            f"✅ <b>Аккаунт создан!</b>\n\n"
            f"Ник: <b>{nickname}</b>\n"
            f"Стартовый капитал: <b>$5,000</b>\n"
            f"Лаборатория: <b>🏚️ Подвал</b>\n\n"
            f"Начальные ингредиенты уже в инвентаре.\n"
            f"Напиши /cook чтобы начать варку!",
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer(f"❌ {result.get('message', 'Ошибка регистрации.')}")


# ──────────────────────────────────────────────────────────────────────────────
# PROFILE
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(F.text == "👤 Профиль")
@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    tg_id = str(message.from_user.id)
    data = await api_get(f"/api/user/{tg_id}")
    if "detail" in data:
        await message.answer("❌ Сначала зарегистрируйся: /start")
        return
    
    rank_info = data.get("rank_info", {})
    rank_emoji = rank_info.get("emoji", "⭐")
    xp_bar = int((data["xp"] / max(data["xp_needed"], 1)) * 10)
    xp_visual = "█" * xp_bar + "░" * (10 - xp_bar)

    text = (
        f"👤 <b>{data['nickname']}</b>\n"
        f"{'─' * 25}\n"
        f"{rank_emoji} Ранг: <b>{data['rank']}</b>\n"
        f"⬆️ Уровень: <b>{data['level']}</b>\n"
        f"📊 Опыт: [{xp_visual}] {data['xp']}/{data['xp_needed']}\n"
        f"💰 Баланс: <b>${data['cash']:,.0f}</b>\n"
        f"⭐ Репутация: <b>{data['reputation']:.0f}</b>\n"
    )
    
    if data.get("is_cooking") and data.get("cook_finish_at"):
        finish = datetime.fromisoformat(data["cook_finish_at"])
        remaining = max(0, int((finish - datetime.utcnow()).total_seconds() / 60))
        text += f"\n🧪 <i>Идёт варка... (~{remaining} мин)</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐 Профиль на сайте", url=f"{SITE_URL}/profile/{data['telegram_id']}")
    ]])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ──────────────────────────────────────────────────────────────────────────────
# INVENTORY
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🎒 Инвентарь")
@dp.message(Command("inventory"))
async def cmd_inventory(message: types.Message):
    tg_id = str(message.from_user.id)
    data = await api_get(f"/api/user/{tg_id}")
    if "detail" in data:
        await message.answer("❌ Сначала зарегистрируйся: /start")
        return
    
    inv = data.get("inventory", {})
    lab = data.get("lab", {})

    text = (
        f"🎒 <b>Инвентарь</b>\n"
        f"{'─' * 25}\n"
        f"🧪 Метиламин: <b>{inv.get('methylamine', 0):.1f}</b>\n"
        f"🔴 Фосфор: <b>{inv.get('phosphorus', 0):.1f}</b>\n"
        f"⚗️ Кислота: <b>{inv.get('acid', 0):.1f}</b>\n"
        f"📦 Упаковка: <b>{inv.get('packaging', 0):.1f}</b>\n"
        f"{'─' * 25}\n"
        f"💊 Продукт: <b>{inv.get('product_amount', 0):.1f}г</b> "
        f"(качество: <b>{inv.get('product_quality', 0):.1f}%</b>)\n"
        f"{'─' * 25}\n"
        f"{lab.get('emoji','🏚️')} Лаборатория: <b>{lab.get('name','Подвал')}</b>\n"
        f"⚡ Скорость варки: <b>x{lab.get('cook_speed',1.0):.1f}</b>\n"
    )
    await message.answer(text, parse_mode="HTML")


# ──────────────────────────────────────────────────────────────────────────────
# COOK
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🧪 Варить")
@dp.message(Command("cook"))
async def cmd_cook(message: types.Message):
    tg_id = str(message.from_user.id)
    
    # Сначала пробуем завершить варку
    finish = await api_post("/api/cook/finish", {"telegram_id": tg_id})
    if finish.get("ok"):
        await message.answer(finish["message"], parse_mode="HTML")
        return
    
    # Если варка идёт — сообщаем
    if "Варка уже идёт" in finish.get("message", "") or "Ещё не готово" in finish.get("message", ""):
        await message.answer(f"⏳ {finish['message']}")
        return
    
    # Начинаем новую варку
    start = await api_post("/api/cook/start", {"telegram_id": tg_id})
    if start.get("ok"):
        await message.answer(
            f"🧪 {start['message']}\n\n"
            f"Вернись позже чтобы забрать партию!\n"
            f"Снова нажми <b>🧪 Варить</b>",
            parse_mode="HTML"
        )
    else:
        msg = start.get("message", "Ошибка.")
        kb = None
        if start.get("market_url"):
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🛒 Открыть рынок", url=f"{SITE_URL}/market")
            ]])
        await message.answer(msg, reply_markup=kb)


# ──────────────────────────────────────────────────────────────────────────────
# DELIVERY
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🚚 Перевозка")
@dp.message(Command("deliver"))
async def cmd_deliver(message: types.Message):
    tg_id = str(message.from_user.id)
    deliveries = await api_get("/api/deliveries", telegram_id=tg_id)
    
    if not deliveries:
        await message.answer("❌ Нет доступных перевозок для вашего уровня.")
        return

    await message.answer(
        "🚚 <b>Выберите перевозку:</b>\n"
        "<i>Риск = шанс провала</i>",
        parse_mode="HTML",
        reply_markup=delivery_keyboard(deliveries)
    )


@dp.callback_query(F.data.startswith("deliver_"))
async def cb_deliver(callback: types.CallbackQuery):
    delivery_id = callback.data.replace("deliver_", "")
    if delivery_id == "unavailable":
        await callback.answer("⏳ Кулдаун ещё не прошёл.", show_alert=True)
        return

    tg_id = str(callback.from_user.id)
    result = await api_post("/api/deliver", {"telegram_id": tg_id, "delivery_id": delivery_id})
    
    await callback.message.edit_text(result["message"])
    await callback.answer()


# ──────────────────────────────────────────────────────────────────────────────
# ROB
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🔫 Ограбить")
@dp.message(Command("rob"))
async def cmd_rob(message: types.Message, state: FSMContext):
    args = message.text.split()
    if len(args) > 1:
        target = args[1].lstrip("@")
        tg_id = str(message.from_user.id)
        result = await api_post("/api/rob", {"telegram_id": tg_id, "target_nickname": target})
        await message.answer(result["message"])
        return

    await message.answer(
        "🔫 <b>Ограбление</b>\n\n"
        "Введите ник игрока которого хотите ограбить:\n"
        "<i>Пример: Heisenberg</i>",
        parse_mode="HTML"
    )
    await state.set_state(RobState.waiting_target)


@dp.message(RobState.waiting_target)
async def process_rob_target(message: types.Message, state: FSMContext):
    target = message.text.strip().lstrip("@")
    tg_id = str(message.from_user.id)
    result = await api_post("/api/rob", {"telegram_id": tg_id, "target_nickname": target})
    await state.clear()
    await message.answer(result["message"])


# ──────────────────────────────────────────────────────────────────────────────
# LAB
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🏭 Лаборатория")
@dp.message(Command("lab"))
async def cmd_lab(message: types.Message):
    tg_id = str(message.from_user.id)
    data = await api_get(f"/api/user/{tg_id}")
    if "detail" in data:
        await message.answer("❌ Сначала зарегистрируйся: /start")
        return
    
    labs = await api_get("/api/labs")
    current_lab = data.get("lab", {})

    text = (
        f"🏭 <b>Лаборатории</b>\n"
        f"Текущая: <b>{current_lab.get('emoji', '🏚️')} {current_lab.get('name', 'Подвал')}</b>\n"
        f"{'─' * 25}\n"
    )
    for lab_id, cfg in labs.items():
        status = "📍 (текущая)" if lab_id == current_lab.get("lab_type") else ""
        text += (
            f"{cfg['emoji']} <b>{cfg['name']}</b> {status}\n"
            f"  💰 Цена: ${cfg['price']:,} | ⚡ Скорость: x{cfg['cook_speed']}\n"
            f"  📦 Объём: {cfg['cook_volume']}г | 🌟 Бонус кач-ва: +{cfg['quality_bonus']}%\n\n"
        )
    
    await message.answer(
        text, parse_mode="HTML",
        reply_markup=lab_keyboard(labs, data["level"])
    )


@dp.callback_query(F.data.startswith("buylab_"))
async def cb_buylab(callback: types.CallbackQuery):
    lab_type = callback.data.replace("buylab_", "")
    tg_id = str(callback.from_user.id)
    result = await api_post("/api/buy-lab", {"telegram_id": tg_id, "lab_type": lab_type})
    await callback.answer(result["message"], show_alert=True)


@dp.callback_query(F.data == "lab_locked")
async def cb_lab_locked(callback: types.CallbackQuery):
    await callback.answer("🔒 Лаборатория недоступна для вашего уровня.", show_alert=True)


# ──────────────────────────────────────────────────────────────────────────────
# SHOP
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(F.text == "💊 Магазин")
@dp.message(Command("shop"))
async def cmd_shop(message: types.Message):
    tg_id = str(message.from_user.id)
    data = await api_get(f"/api/user/{tg_id}")
    if "detail" in data:
        await message.answer("❌ Сначала зарегистрируйся: /start")
        return
    
    await message.answer(
        f"💊 <b>Магазин ингредиентов</b>\n"
        f"Ваш баланс: <b>${data['cash']:,.0f}</b>\n\n"
        f"Цены за 1 единицу:\n"
        f"🧪 Метиламин — $300\n"
        f"🔴 Фосфор — $150\n"
        f"⚗️ Кислота — $200\n"
        f"📦 Упаковка — $50\n\n"
        f"Нажмите чтобы купить:",
        parse_mode="HTML",
        reply_markup=shop_keyboard()
    )


@dp.callback_query(F.data.startswith("shop_"))
async def cb_shop(callback: types.CallbackQuery):
    _, amount_str, ingredient = callback.data.split("_", 2)
    amount = float(amount_str)
    tg_id = str(callback.from_user.id)
    result = await api_post("/api/shop/buy-ingredient", {
        "telegram_id": tg_id,
        "ingredient": ingredient,
        "amount": amount
    })
    await callback.answer(result["message"], show_alert=True)


# ──────────────────────────────────────────────────────────────────────────────
# SITE LINK
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🌐 Сайт")
async def cmd_site(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Рынок",    url=f"{SITE_URL}/market")],
        [InlineKeyboardButton(text="💬 Форум",    url=f"{SITE_URL}/forum")],
        [InlineKeyboardButton(text="🏆 Топ игроков", url=f"{SITE_URL}/leaderboard")],
        [InlineKeyboardButton(text="👤 Мой профиль", url=f"{SITE_URL}/login")],
    ])
    await message.answer(
        f"🌐 <b>Официальный сайт игры</b>\n\n"
        f"На сайте вы можете:\n"
        f"• Торговать на рынке\n"
        f"• Общаться на форуме\n"
        f"• Смотреть топ игроков\n"
        f"• Управлять профилем",
        parse_mode="HTML",
        reply_markup=kb
    )


# ──────────────────────────────────────────────────────────────────────────────
# HELP
# ──────────────────────────────────────────────────────────────────────────────
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "⚗️ <b>Команды Breaking Bad Online</b>\n\n"
        "/start — регистрация / главное меню\n"
        "/profile — профиль игрока\n"
        "/inventory — инвентарь\n"
        "/cook — варить продукт\n"
        "/deliver — перевозки\n"
        "/rob @ник — ограбить игрока\n"
        "/lab — лаборатории\n"
        "/shop — магазин ингредиентов\n\n"
        f"🌐 Сайт: {SITE_URL}",
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
