from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import random
import hashlib
import hmac
import os

from database.connection import get_db, init_db
from database.models import (
    User, Inventory, Lab, MarketListing,
    Transaction, ForumCategory, ForumTopic, ForumPost,
    CookLog, RobLog
)
from api.game_config import (
    LABS, COOK_RECIPE, INGREDIENTS, get_rank,
    xp_for_level, calc_product_price, DELIVERIES,
    ROB_COOLDOWN_MINUTES, ROB_BASE_SUCCESS_CHANCE,
    ROB_MAX_CASH_PERCENT, ROB_MAX_PRODUCT_PERCENT,
    START_CASH, START_INGREDIENTS
)

app = FastAPI(title="Breaking Bad Game API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")


# ──────────────────────────────────────────────────────────────────────────────
# STARTUP
# ──────────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await init_db()


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
async def get_or_create_user(db: AsyncSession, telegram_id: str, nickname: str = None) -> User:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        nick = nickname or f"player_{telegram_id[-6:]}"
        user = User(telegram_id=telegram_id, nickname=nick, cash=START_CASH)
        db.add(user)
        await db.flush()

        inv = Inventory(user_id=user.id, **START_INGREDIENTS)
        lab = Lab(user_id=user.id, lab_type="basement", cook_speed=1.0, cook_volume=10.0, quality_bonus=0.0)
        db.add(inv)
        db.add(lab)
        await db.commit()
        await db.refresh(user)
    return user


def update_rank(user: User):
    rank = get_rank(user.reputation)
    user.rank = rank["name"]


async def add_xp(db: AsyncSession, user: User, xp: int):
    user.xp += xp
    needed = xp_for_level(user.level + 1)
    while user.xp >= needed:
        user.xp -= needed
        user.level += 1
        needed = xp_for_level(user.level + 1)
    await db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS
# ──────────────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    telegram_id: str
    nickname: str

class CookRequest(BaseModel):
    telegram_id: str

class BuyLabRequest(BaseModel):
    telegram_id: str
    lab_type: str

class DeliverRequest(BaseModel):
    telegram_id: str
    delivery_id: str

class RobRequest(BaseModel):
    telegram_id: str
    target_nickname: str

class CreateListingRequest(BaseModel):
    telegram_id: str
    item_type: str
    amount: float
    price_per_unit: float

class BuyListingRequest(BaseModel):
    telegram_id: str
    listing_id: int

class CreateTopicRequest(BaseModel):
    telegram_id: str
    category_slug: str
    title: str
    content: str

class CreatePostRequest(BaseModel):
    telegram_id: str
    topic_id: int
    content: str

class BuyIngredientRequest(BaseModel):
    telegram_id: str
    ingredient: str
    amount: float


# ──────────────────────────────────────────────────────────────────────────────
# USER ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == req.telegram_id))
    existing = result.scalar_one_or_none()
    if existing:
        return {"ok": True, "message": "already_exists", "user": _user_dict(existing)}
    
    user = await get_or_create_user(db, req.telegram_id, req.nickname)
    return {"ok": True, "message": "created", "user": _user_dict(user)}


@app.get("/api/user/{telegram_id}")
async def get_user(telegram_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    inv_result = await db.execute(select(Inventory).where(Inventory.user_id == user.id))
    inv = inv_result.scalar_one_or_none()
    lab_result = await db.execute(select(Lab).where(Lab.user_id == user.id))
    lab = lab_result.scalar_one_or_none()

    return {
        **_user_dict(user),
        "inventory": _inv_dict(inv),
        "lab": _lab_dict(lab),
        "xp_needed": xp_for_level(user.level + 1),
        "rank_info": get_rank(user.reputation),
    }


def _user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "nickname": u.nickname,
        "cash": u.cash,
        "level": u.level,
        "xp": u.xp,
        "reputation": u.reputation,
        "rank": u.rank,
        "is_cooking": u.is_cooking,
        "cook_finish_at": u.cook_finish_at.isoformat() if u.cook_finish_at else None,
    }

def _inv_dict(inv) -> dict:
    if not inv:
        return {}
    return {
        "methylamine": inv.methylamine,
        "phosphorus": inv.phosphorus,
        "acid": inv.acid,
        "packaging": inv.packaging,
        "product_amount": inv.product_amount,
        "product_quality": inv.product_quality,
    }

def _lab_dict(lab) -> dict:
    if not lab:
        return {}
    cfg = LABS.get(lab.lab_type, LABS["basement"])
    return {
        "lab_type": lab.lab_type,
        "name": cfg["name"],
        "emoji": cfg["emoji"],
        "cook_speed": lab.cook_speed,
        "cook_volume": lab.cook_volume,
        "quality_bonus": lab.quality_bonus,
    }


# ──────────────────────────────────────────────────────────────────────────────
# COOKING
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/cook/start")
async def start_cook(req: CookRequest, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, req.telegram_id)
    
    if user.is_cooking:
        remaining = (user.cook_finish_at - datetime.utcnow()).seconds // 60
        return {"ok": False, "message": f"⏳ Варка уже идёт. Осталось ~{remaining} мин."}

    inv_r = await db.execute(select(Inventory).where(Inventory.user_id == user.id))
    inv = inv_r.scalar_one_or_none()
    lab_r = await db.execute(select(Lab).where(Lab.user_id == user.id))
    lab = lab_r.scalar_one_or_none()
    cfg = LABS[lab.lab_type]

    # Проверяем ингредиенты
    missing = []
    for ing, amount in COOK_RECIPE.items():
        if getattr(inv, ing) < amount:
            missing.append(INGREDIENTS[ing]["name"])
    
    if missing:
        return {
            "ok": False,
            "message": f"❌ Не хватает: {', '.join(missing)}",
            "missing": missing,
            "market_url": "/market"
        }

    # Списываем ингредиенты
    for ing, amount in COOK_RECIPE.items():
        setattr(inv, ing, getattr(inv, ing) - amount)

    cook_minutes = cfg["cook_time_minutes"] / lab.cook_speed
    finish_at = datetime.utcnow() + timedelta(minutes=cook_minutes)
    user.is_cooking = True
    user.cook_finish_at = finish_at
    await db.commit()

    return {
        "ok": True,
        "message": f"🧪 Варка началась! Закончится через {int(cook_minutes)} мин.",
        "finish_at": finish_at.isoformat(),
    }


@app.post("/api/cook/finish")
async def finish_cook(req: CookRequest, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, req.telegram_id)

    if not user.is_cooking:
        return {"ok": False, "message": "Варка не запущена."}
    
    if datetime.utcnow() < user.cook_finish_at:
        remaining = int((user.cook_finish_at - datetime.utcnow()).seconds / 60)
        return {"ok": False, "message": f"⏳ Ещё не готово. Осталось ~{remaining} мин."}

    lab_r = await db.execute(select(Lab).where(Lab.user_id == user.id))
    lab = lab_r.scalar_one_or_none()
    inv_r = await db.execute(select(Inventory).where(Inventory.user_id == user.id))
    inv = inv_r.scalar_one_or_none()
    cfg = LABS[lab.lab_type]

    # Брак или успех
    defect_chance = 0.1
    success = random.random() > defect_chance

    if not success:
        user.is_cooking = False
        user.cook_finish_at = None
        await db.commit()
        return {"ok": False, "message": "💥 Взрыв в лаборатории! Партия испорчена. (-20 репутации)", "product": 0}

    base_quality = random.uniform(50, 85) + lab.quality_bonus
    quality = min(100.0, base_quality + random.uniform(-10, 10))
    amount = cfg["cook_volume"]

    # Если уже есть продукт — смешиваем качество
    if inv.product_amount > 0:
        total = inv.product_amount + amount
        inv.product_quality = (inv.product_quality * inv.product_amount + quality * amount) / total
        inv.product_amount = total
    else:
        inv.product_amount = amount
        inv.product_quality = quality

    user.is_cooking = False
    user.cook_finish_at = None
    user.reputation += 5
    update_rank(user)

    log = CookLog(user_id=user.id, lab_type=lab.lab_type, amount_produced=amount, quality=quality, success=True)
    db.add(log)
    await add_xp(db, user, 30)

    return {
        "ok": True,
        "message": f"✅ Варка завершена! Получено {amount:.1f}г продукта, качество {quality:.1f}%",
        "amount": amount,
        "quality": quality,
    }


# ──────────────────────────────────────────────────────────────────────────────
# DELIVERIES
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/deliveries")
async def list_deliveries(telegram_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, telegram_id)
    now = datetime.utcnow()
    
    result = []
    for d in DELIVERIES:
        if d["required_level"] > user.level:
            continue
        cooldown_ok = True
        if user.last_deliver_at:
            elapsed = (now - user.last_deliver_at).seconds / 60
            if elapsed < d["cooldown_minutes"]:
                cooldown_ok = False
        result.append({**d, "available": cooldown_ok})
    
    return result


@app.post("/api/deliver")
async def deliver(req: DeliverRequest, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, req.telegram_id)
    inv_r = await db.execute(select(Inventory).where(Inventory.user_id == user.id))
    inv = inv_r.scalar_one_or_none()

    if inv.product_amount < 5:
        return {"ok": False, "message": "❌ Недостаточно продукта для перевозки (нужно минимум 5г)."}

    d_cfg = next((d for d in DELIVERIES if d["id"] == req.delivery_id), None)
    if not d_cfg:
        return {"ok": False, "message": "Неверный тип перевозки."}
    
    if d_cfg["required_level"] > user.level:
        return {"ok": False, "message": f"❌ Нужен уровень {d_cfg['required_level']}."}

    now = datetime.utcnow()
    if user.last_deliver_at:
        elapsed = (now - user.last_deliver_at).seconds / 60
        if elapsed < d_cfg["cooldown_minutes"]:
            wait = int(d_cfg["cooldown_minutes"] - elapsed)
            return {"ok": False, "message": f"⏳ Кулдаун. Ждите ещё {wait} мин."}

    roll = random.random()

    if roll < d_cfg["risk"] * 0.4:
        # Поймали — конфискация
        lost = min(inv.product_amount, inv.product_amount * 0.5)
        inv.product_amount -= lost
        user.reputation -= 15
        update_rank(user)
        user.last_deliver_at = now
        await db.commit()
        return {"ok": False, "message": f"🚔 Попались! Конфисковали {lost:.1f}г продукта."}
    
    elif roll < d_cfg["risk"]:
        # Ограбили
        lost = min(inv.product_amount, inv.product_amount * 0.3)
        inv.product_amount -= lost
        user.last_deliver_at = now
        await db.commit()
        return {"ok": False, "message": f"🔫 Ограбили в пути! Потеряли {lost:.1f}г."}
    
    else:
        # Успех
        reward = random.uniform(d_cfg["reward_min"], d_cfg["reward_max"])
        user.cash += reward
        user.reputation += 10
        update_rank(user)
        user.last_deliver_at = now
        await add_xp(db, user, d_cfg["xp"])
        return {"ok": True, "message": f"✅ Перевозка успешна! Получено ${reward:,.0f}", "reward": reward}


# ──────────────────────────────────────────────────────────────────────────────
# ROBBERY
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/rob")
async def rob(req: RobRequest, db: AsyncSession = Depends(get_db)):
    robber = await get_or_create_user(db, req.telegram_id)
    
    victim_r = await db.execute(select(User).where(User.nickname == req.target_nickname))
    victim = victim_r.scalar_one_or_none()
    if not victim:
        return {"ok": False, "message": "❌ Игрок не найден."}
    if victim.telegram_id == robber.telegram_id:
        return {"ok": False, "message": "❌ Нельзя ограбить самого себя."}

    now = datetime.utcnow()
    if robber.last_rob_at:
        elapsed = (now - robber.last_rob_at).total_seconds() / 60
        if elapsed < ROB_COOLDOWN_MINUTES:
            wait = int(ROB_COOLDOWN_MINUTES - elapsed)
            return {"ok": False, "message": f"⏳ Кулдаун. Ждите ещё {wait} мин."}

    success = random.random() < ROB_BASE_SUCCESS_CHANCE
    robber.last_rob_at = now

    victim_inv_r = await db.execute(select(Inventory).where(Inventory.user_id == victim.id))
    victim_inv = victim_inv_r.scalar_one_or_none()
    robber_inv_r = await db.execute(select(Inventory).where(Inventory.user_id == robber.id))
    robber_inv = robber_inv_r.scalar_one_or_none()

    stolen_cash = 0.0
    stolen_product = 0.0

    if success:
        stolen_cash = victim.cash * ROB_MAX_CASH_PERCENT * random.uniform(0.5, 1.0)
        stolen_product = victim_inv.product_amount * ROB_MAX_PRODUCT_PERCENT * random.uniform(0.5, 1.0)
        
        victim.cash -= stolen_cash
        robber.cash += stolen_cash
        victim_inv.product_amount = max(0, victim_inv.product_amount - stolen_product)
        robber_inv.product_amount += stolen_product

        robber.reputation += 8
        victim.reputation -= 3
        update_rank(robber)
        update_rank(victim)
    else:
        robber.reputation -= 5
        update_rank(robber)

    log = RobLog(
        robber_id=robber.id, victim_id=victim.id,
        success=success, stolen_cash=stolen_cash, stolen_product=stolen_product
    )
    db.add(log)
    await db.commit()

    if success:
        return {
            "ok": True,
            "message": f"✅ Ограбление успешно! Украдено ${stolen_cash:,.0f} и {stolen_product:.1f}г продукта.",
            "stolen_cash": stolen_cash,
            "stolen_product": stolen_product,
        }
    else:
        return {"ok": False, "message": "❌ Провал! Жертва оказалась не так проста."}


# ──────────────────────────────────────────────────────────────────────────────
# LABS
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/labs")
async def get_labs():
    return LABS

@app.post("/api/buy-lab")
async def buy_lab(req: BuyLabRequest, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, req.telegram_id)
    cfg = LABS.get(req.lab_type)
    if not cfg:
        return {"ok": False, "message": "Неверный тип лаборатории."}
    if user.level < cfg["required_level"]:
        return {"ok": False, "message": f"❌ Нужен уровень {cfg['required_level']}."}
    if user.cash < cfg["price"]:
        return {"ok": False, "message": f"❌ Не хватает денег. Нужно ${cfg['price']:,}."}

    lab_r = await db.execute(select(Lab).where(Lab.user_id == user.id))
    lab = lab_r.scalar_one_or_none()

    user.cash -= cfg["price"]
    lab.lab_type = req.lab_type
    lab.cook_speed = cfg["cook_speed"]
    lab.cook_volume = cfg["cook_volume"]
    lab.quality_bonus = cfg["quality_bonus"]
    await db.commit()

    return {"ok": True, "message": f"✅ Куплена {cfg['emoji']} {cfg['name']}!"}


# ──────────────────────────────────────────────────────────────────────────────
# MARKET
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/market")
async def get_market(
    item_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    q = select(MarketListing, User).join(User, MarketListing.seller_id == User.id).where(
        MarketListing.is_active == True
    )
    if item_type:
        q = q.where(MarketListing.item_type == item_type)
    q = q.order_by(MarketListing.created_at.desc()).offset((page-1)*limit).limit(limit)
    result = await db.execute(q)

    listings = []
    for listing, seller in result.fetchall():
        listings.append({
            "id": listing.id,
            "seller": seller.nickname,
            "seller_rank": seller.rank,
            "item_type": listing.item_type,
            "amount": listing.amount,
            "quality": listing.quality,
            "price_per_unit": listing.price_per_unit,
            "total_price": listing.total_price,
            "created_at": listing.created_at.isoformat(),
        })
    
    return {"listings": listings, "page": page}


@app.post("/api/market/create")
async def create_listing(req: CreateListingRequest, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, req.telegram_id)
    inv_r = await db.execute(select(Inventory).where(Inventory.user_id == user.id))
    inv = inv_r.scalar_one_or_none()

    # Проверяем наличие
    if req.item_type == "product":
        if inv.product_amount < req.amount:
            return {"ok": False, "message": f"❌ Недостаточно продукта."}
        inv.product_amount -= req.amount
        quality = inv.product_quality
    elif req.item_type in INGREDIENTS:
        cur = getattr(inv, req.item_type, 0)
        if cur < req.amount:
            return {"ok": False, "message": f"❌ Недостаточно {INGREDIENTS[req.item_type]['name']}."}
        setattr(inv, req.item_type, cur - req.amount)
        quality = None
    else:
        return {"ok": False, "message": "Неверный тип товара."}

    listing = MarketListing(
        seller_id=user.id,
        item_type=req.item_type,
        amount=req.amount,
        quality=quality,
        price_per_unit=req.price_per_unit,
        total_price=req.price_per_unit * req.amount,
    )
    db.add(listing)
    await db.commit()
    return {"ok": True, "message": "✅ Лот выставлен на рынок!"}


@app.post("/api/market/buy")
async def buy_listing(req: BuyListingRequest, db: AsyncSession = Depends(get_db)):
    buyer = await get_or_create_user(db, req.telegram_id)
    
    listing_r = await db.execute(select(MarketListing).where(
        MarketListing.id == req.listing_id,
        MarketListing.is_active == True
    ))
    listing = listing_r.scalar_one_or_none()
    if not listing:
        return {"ok": False, "message": "❌ Лот не найден или уже продан."}
    if listing.seller_id == buyer.id:
        return {"ok": False, "message": "❌ Нельзя купить собственный лот."}
    if buyer.cash < listing.total_price:
        return {"ok": False, "message": f"❌ Не хватает денег. Нужно ${listing.total_price:,.0f}."}

    seller_r = await db.execute(select(User).where(User.id == listing.seller_id))
    seller = seller_r.scalar_one()
    buyer_inv_r = await db.execute(select(Inventory).where(Inventory.user_id == buyer.id))
    buyer_inv = buyer_inv_r.scalar_one()

    buyer.cash -= listing.total_price
    seller.cash += listing.total_price
    listing.is_active = False

    if listing.item_type == "product":
        if buyer_inv.product_amount > 0:
            total = buyer_inv.product_amount + listing.amount
            buyer_inv.product_quality = (buyer_inv.product_quality * buyer_inv.product_amount + listing.quality * listing.amount) / total
            buyer_inv.product_amount = total
        else:
            buyer_inv.product_amount = listing.amount
            buyer_inv.product_quality = listing.quality or 50.0
    elif listing.item_type in INGREDIENTS:
        cur = getattr(buyer_inv, listing.item_type, 0)
        setattr(buyer_inv, listing.item_type, cur + listing.amount)

    txn = Transaction(
        buyer_id=buyer.id, seller_id=seller.id,
        listing_id=listing.id, amount=listing.amount, total_price=listing.total_price
    )
    db.add(txn)
    await db.commit()
    return {"ok": True, "message": f"✅ Куплено {listing.amount} {listing.item_type} за ${listing.total_price:,.0f}!"}


# ──────────────────────────────────────────────────────────────────────────────
# SHOP (buy ingredients from game)
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/shop/buy-ingredient")
async def shop_buy_ingredient(req: BuyIngredientRequest, db: AsyncSession = Depends(get_db)):
    if req.ingredient not in INGREDIENTS:
        return {"ok": False, "message": "Неверный ингредиент."}
    
    user = await get_or_create_user(db, req.telegram_id)
    ing_cfg = INGREDIENTS[req.ingredient]
    total_cost = ing_cfg["base_price"] * req.amount

    if user.cash < total_cost:
        return {"ok": False, "message": f"❌ Не хватает денег. Нужно ${total_cost:,.0f}."}

    inv_r = await db.execute(select(Inventory).where(Inventory.user_id == user.id))
    inv = inv_r.scalar_one()

    user.cash -= total_cost
    setattr(inv, req.ingredient, getattr(inv, req.ingredient) + req.amount)
    await db.commit()

    return {"ok": True, "message": f"✅ Куплено {req.amount} {ing_cfg['name']} за ${total_cost:,.0f}"}


# ──────────────────────────────────────────────────────────────────────────────
# FORUM
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/forum/categories")
async def forum_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ForumCategory).order_by(ForumCategory.order))
    cats = result.scalars().all()
    return [{"id": c.id, "name": c.name, "slug": c.slug, "description": c.description, "icon": c.icon} for c in cats]


@app.get("/api/forum/topics")
async def forum_topics(
    category_slug: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    q = select(ForumTopic, User, ForumCategory).join(
        User, ForumTopic.author_id == User.id
    ).join(ForumCategory, ForumTopic.category_id == ForumCategory.id)
    
    if category_slug:
        q = q.where(ForumCategory.slug == category_slug)
    
    q = q.order_by(desc(ForumTopic.is_pinned), desc(ForumTopic.updated_at))
    q = q.offset((page-1)*limit).limit(limit)
    result = await db.execute(q)

    topics = []
    for topic, author, cat in result.fetchall():
        post_count_r = await db.execute(
            select(func.count(ForumPost.id)).where(ForumPost.topic_id == topic.id)
        )
        post_count = post_count_r.scalar()
        topics.append({
            "id": topic.id,
            "title": topic.title,
            "author": author.nickname,
            "author_rank": author.rank,
            "category": cat.name,
            "category_slug": cat.slug,
            "views": topic.views,
            "post_count": post_count,
            "is_pinned": topic.is_pinned,
            "updated_at": topic.updated_at.isoformat(),
        })
    return topics


@app.get("/api/forum/topic/{topic_id}")
async def forum_topic(topic_id: int, db: AsyncSession = Depends(get_db)):
    topic_r = await db.execute(select(ForumTopic).where(ForumTopic.id == topic_id))
    topic = topic_r.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    topic.views += 1
    
    posts_r = await db.execute(
        select(ForumPost, User).join(User, ForumPost.author_id == User.id)
        .where(ForumPost.topic_id == topic_id)
        .order_by(ForumPost.created_at)
    )
    posts = []
    for post, author in posts_r.fetchall():
        posts.append({
            "id": post.id,
            "content": post.content,
            "author": author.nickname,
            "author_rank": author.rank,
            "author_level": author.level,
            "created_at": post.created_at.isoformat(),
        })
    
    await db.commit()
    return {"topic": {"id": topic.id, "title": topic.title}, "posts": posts}


@app.post("/api/forum/topic/create")
async def create_topic(req: CreateTopicRequest, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, req.telegram_id)
    cat_r = await db.execute(select(ForumCategory).where(ForumCategory.slug == req.category_slug))
    cat = cat_r.scalar_one_or_none()
    if not cat:
        return {"ok": False, "message": "Категория не найдена."}

    topic = ForumTopic(category_id=cat.id, author_id=user.id, title=req.title)
    db.add(topic)
    await db.flush()

    post = ForumPost(topic_id=topic.id, author_id=user.id, content=req.content)
    db.add(post)
    await db.commit()
    return {"ok": True, "topic_id": topic.id}


@app.post("/api/forum/post/create")
async def create_post(req: CreatePostRequest, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, req.telegram_id)
    topic_r = await db.execute(select(ForumTopic).where(ForumTopic.id == req.topic_id))
    topic = topic_r.scalar_one_or_none()
    if not topic or topic.is_locked:
        return {"ok": False, "message": "Тема закрыта или не найдена."}

    post = ForumPost(topic_id=topic.id, author_id=user.id, content=req.content)
    topic.updated_at = datetime.utcnow()
    db.add(post)
    await db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# LEADERBOARD
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/leaderboard")
async def leaderboard(sort_by: str = "cash", limit: int = 50, db: AsyncSession = Depends(get_db)):
    sort_map = {
        "cash": User.cash,
        "level": User.level,
        "reputation": User.reputation,
    }
    order_col = sort_map.get(sort_by, User.cash)
    result = await db.execute(select(User).order_by(desc(order_col)).limit(limit))
    users = result.scalars().all()
    
    board = []
    for i, u in enumerate(users, 1):
        inv_r = await db.execute(select(Inventory).where(Inventory.user_id == u.id))
        inv = inv_r.scalar_one_or_none()
        board.append({
            "position": i,
            "nickname": u.nickname,
            "rank": u.rank,
            "level": u.level,
            "cash": u.cash,
            "reputation": u.reputation,
            "product_amount": inv.product_amount if inv else 0,
        })
    return board
