from dataclasses import dataclass, field
from typing import Dict

# ─── Ингредиенты ─────────────────────────────────────────────────────────────
INGREDIENTS = {
    "methylamine": {"name": "Метиламин", "emoji": "🧪", "base_price": 300},
    "phosphorus":  {"name": "Фосфор",    "emoji": "🔴", "base_price": 150},
    "acid":        {"name": "Кислота",   "emoji": "⚗️",  "base_price": 200},
    "packaging":   {"name": "Упаковка",  "emoji": "📦", "base_price": 50},
}

# ─── Рецепт варки ─────────────────────────────────────────────────────────────
COOK_RECIPE = {
    "methylamine": 2.0,
    "phosphorus":  1.0,
    "acid":        1.5,
    "packaging":   1.0,
}

# ─── Лаборатории ──────────────────────────────────────────────────────────────
LABS = {
    "basement": {
        "name": "Подвал",
        "emoji": "🏚️",
        "price": 0,
        "cook_speed": 1.0,
        "cook_volume": 10.0,
        "quality_bonus": 0.0,
        "cook_time_minutes": 60,
        "required_level": 1,
    },
    "van": {
        "name": "Фургон",
        "emoji": "🚐",
        "price": 15_000,
        "cook_speed": 1.5,
        "cook_volume": 25.0,
        "quality_bonus": 10.0,
        "cook_time_minutes": 45,
        "required_level": 5,
    },
    "industrial": {
        "name": "Промышленная лаборатория",
        "emoji": "🏭",
        "price": 75_000,
        "cook_speed": 3.0,
        "cook_volume": 100.0,
        "quality_bonus": 25.0,
        "cook_time_minutes": 30,
        "required_level": 10,
    },
}

# ─── Репутация / ранги ────────────────────────────────────────────────────────
RANKS = [
    {"name": "новичок",  "emoji": "🌱", "min_rep": 0,     "max_rep": 99},
    {"name": "дилер",    "emoji": "💼", "min_rep": 100,   "max_rep": 499},
    {"name": "варщик",   "emoji": "🧪", "min_rep": 500,   "max_rep": 1999},
    {"name": "барон",    "emoji": "👑", "min_rep": 2000,  "max_rep": 9999},
    {"name": "легенда",  "emoji": "💀", "min_rep": 10000, "max_rep": 999999},
]

def get_rank(reputation: float) -> dict:
    for rank in reversed(RANKS):
        if reputation >= rank["min_rep"]:
            return rank
    return RANKS[0]

# ─── Уровни ───────────────────────────────────────────────────────────────────
def xp_for_level(level: int) -> int:
    return int(100 * (level ** 1.5))

# ─── Рынок ───────────────────────────────────────────────────────────────────
PRODUCT_BASE_PRICE = 500   # за единицу при качестве 50%

def calc_product_price(quality: float) -> float:
    """Цена единицы продукта в зависимости от качества."""
    return PRODUCT_BASE_PRICE * (quality / 50.0)

# ─── Перевозки ────────────────────────────────────────────────────────────────
DELIVERIES = [
    {
        "id": "local",
        "name": "Местная доставка",
        "emoji": "🚗",
        "reward_min": 500,
        "reward_max": 1500,
        "risk": 0.1,
        "cooldown_minutes": 30,
        "required_level": 1,
        "xp": 20,
    },
    {
        "id": "city",
        "name": "По городу",
        "emoji": "🏙️",
        "reward_min": 2000,
        "reward_max": 5000,
        "risk": 0.25,
        "cooldown_minutes": 60,
        "required_level": 3,
        "xp": 60,
    },
    {
        "id": "interstate",
        "name": "Межштатная",
        "emoji": "🛣️",
        "reward_min": 8000,
        "reward_max": 20000,
        "risk": 0.4,
        "cooldown_minutes": 120,
        "required_level": 7,
        "xp": 150,
    },
]

# ─── Ограбления ───────────────────────────────────────────────────────────────
ROB_COOLDOWN_MINUTES = 60
ROB_BASE_SUCCESS_CHANCE = 0.45
ROB_MAX_CASH_PERCENT = 0.15    # макс % кэша жертвы
ROB_MAX_PRODUCT_PERCENT = 0.20 # макс % продукта жертвы

# ─── Стартовый капитал ────────────────────────────────────────────────────────
START_CASH = 5_000.0
START_INGREDIENTS = {
    "methylamine": 5.0,
    "phosphorus":  3.0,
    "acid":        4.0,
    "packaging":   5.0,
}
