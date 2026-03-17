from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, 
    ForeignKey, Text, Enum
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import enum

Base = declarative_base()


class ReputationRank(str, enum.Enum):
    novice = "новичок"
    dealer = "дилер"
    cook = "варщик"
    baron = "барон"
    legend = "легенда"


class LabType(str, enum.Enum):
    basement = "подвал"
    van = "фургон"
    industrial = "промышленная"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(50), unique=True, nullable=False, index=True)
    nickname = Column(String(50), unique=True, nullable=False)
    cash = Column(Float, default=5000.0)
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    reputation = Column(Float, default=0.0)
    rank = Column(String(20), default=ReputationRank.novice)
    is_cooking = Column(Boolean, default=False)
    cook_finish_at = Column(DateTime, nullable=True)
    last_rob_at = Column(DateTime, nullable=True)
    last_deliver_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    avatar = Column(String(200), nullable=True)
    bio = Column(Text, nullable=True)

    inventory = relationship("Inventory", back_populates="user", uselist=False, cascade="all, delete-orphan")
    lab = relationship("Lab", back_populates="user", uselist=False, cascade="all, delete-orphan")
    listings = relationship("MarketListing", back_populates="seller", cascade="all, delete-orphan")
    forum_posts = relationship("ForumPost", back_populates="author", cascade="all, delete-orphan")
    forum_topics = relationship("ForumTopic", back_populates="author", cascade="all, delete-orphan")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    methylamine = Column(Float, default=0.0)   # метиламин
    phosphorus = Column(Float, default=0.0)    # фосфор
    acid = Column(Float, default=0.0)          # кислота
    packaging = Column(Float, default=0.0)     # упаковка
    product_amount = Column(Float, default=0.0)
    product_quality = Column(Float, default=0.0)  # 0-100

    user = relationship("User", back_populates="inventory")


class Lab(Base):
    __tablename__ = "labs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    lab_type = Column(String(20), default=LabType.basement)
    cook_speed = Column(Float, default=1.0)     # множитель скорости
    cook_volume = Column(Float, default=10.0)   # объём варки
    quality_bonus = Column(Float, default=0.0)  # бонус к качеству

    user = relationship("User", back_populates="lab")


class MarketListing(Base):
    __tablename__ = "market_listings"

    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey("users.id"))
    item_type = Column(String(30), nullable=False)   # product / methylamine / phosphorus / acid / packaging
    amount = Column(Float, nullable=False)
    quality = Column(Float, nullable=True)           # только для продукта
    price_per_unit = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    seller = relationship("User", back_populates="listings")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey("users.id"))
    seller_id = Column(Integer, ForeignKey("users.id"))
    listing_id = Column(Integer, ForeignKey("market_listings.id"))
    amount = Column(Float)
    total_price = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class ForumCategory(Base):
    __tablename__ = "forum_categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    icon = Column(String(10), default="💬")
    order = Column(Integer, default=0)

    topics = relationship("ForumTopic", back_populates="category", cascade="all, delete-orphan")


class ForumTopic(Base):
    __tablename__ = "forum_topics"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("forum_categories.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(200), nullable=False)
    is_pinned = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False)
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("ForumCategory", back_populates="topics")
    author = relationship("User", back_populates="forum_topics")
    posts = relationship("ForumPost", back_populates="topic", cascade="all, delete-orphan")


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("forum_topics.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("ForumTopic", back_populates="posts")
    author = relationship("User", back_populates="forum_posts")


class CookLog(Base):
    __tablename__ = "cook_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lab_type = Column(String(20))
    amount_produced = Column(Float)
    quality = Column(Float)
    success = Column(Boolean)
    created_at = Column(DateTime, default=datetime.utcnow)


class RobLog(Base):
    __tablename__ = "rob_logs"

    id = Column(Integer, primary_key=True)
    robber_id = Column(Integer, ForeignKey("users.id"))
    victim_id = Column(Integer, ForeignKey("users.id"))
    success = Column(Boolean)
    stolen_cash = Column(Float, default=0)
    stolen_product = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
