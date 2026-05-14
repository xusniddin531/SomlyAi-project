"""
Database layer for Somly AI.

Balance structure per user:
{
    "telegram_id": 12345,
    "balances": {
        "UZS": {"amount": 0, "title": "So'm", "color": "#3B82F6", "limit": null},
        "USD": {"amount": 0, "title": "Dollar", "color": "#10B981", "limit": null}
    },
    "is_active": true
}

Debt structure:
{
    "telegram_id": 12345,
    "person": "Jasur",
    "amount": 100000,
    "paid_amount": 0,
    "currency": "UZS",
    "direction": "bergan",   # bergan = u senga qarzdir | olgan = sen unga qarzsan
    "date": "2026-04-21",
    "due_date": "2026-05-01" or null,
    "status": "active",      # active | paid | partial | cancelled
    "created_at": datetime
}
"""

from datetime import datetime, timedelta
import os
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from src import config
from src.ws_manager import ws_manager

client = AsyncIOMotorClient(config.MONGO_URI)
db = client[config.DB_NAME]

# Collections
users_collection = db["users"]
transactions_collection = db["transactions"]
debts_collection = db["debts"]
admins_collection = db["admins"]
channels_collection = db["channels"]
custom_categories_collection = db["custom_categories"]
config_collection = db["config"]
groups_collection = db["groups"]
knowledge_collection = db["knowledge_base"]
reminders_collection = db["reminders"]
shared_wallets_collection = db["shared_wallets"]
invites_collection = db["invites"]
referrals_collection = db["referrals"]
chat_history_collection = db["chat_history"]
broadcasts_collection = db["broadcasts"]
financial_history_collection = db["financial_history"]
channel_subscriptions_collection = db["channel_subscriptions"]
qr_scans_collection = db["qr_scans"]
ads_collection = db["ads"]
# ═══════════════════════════════════════
# REFERRAL OPERATIONS
# ═══════════════════════════════════════

async def track_referral(referrer_id: int, referred_id: int):
    """Yangi foydalanuvchi kim orqali kelganini saqlaydi."""
    # Check if already tracked
    exists = await referrals_collection.find_one({"referred_id": referred_id})
    if exists: return False
    
    referral = {
        "referrer_id": referrer_id,
        "referred_id": referred_id,
        "created_at": datetime.utcnow(),
        "source": "referral"
    }
    await referrals_collection.insert_one(referral)
    return True

async def get_referral_stats(user_id: int):
    """Foydalanuvchining taklif statistikasini oladi."""
    count = await referrals_collection.count_documents({"referrer_id": user_id})
    # Asosiy userlar jadvalidan ro'yxatdan o'tganlarni ham tekshirishimiz mumkin
    # Lekin hozircha taklif qilinganlarning o'zi kifoya
    return {
        "invited": count,
        "registered": count # Hozircha referal bo'lib kelgan hammasi registered hisoblanadi
    }

async def get_all_referral_stats():
    """Admin panel uchun barcha referal statistikasini oladi."""
    pipeline = [
        {"$group": {
            "_id": "$referrer_id",
            "count": {"$sum": 1},
            "last_referral": {"$max": "$created_at"}
        }},
        {"$sort": {"count": -1}},
        {"$limit": 50}
    ]
    cursor = referrals_collection.aggregate(pipeline)
    stats = await cursor.to_list(length=50)
    
    # User ma'lumotlarini qo'shish
    result = []
    for s in stats:
        user = await get_user(s["_id"])
        result.append({
            "user_id": s["_id"],
            "name": user.get("full_name", "Noma'lum"),
            "count": s["count"],
            "last_date": s["last_referral"]
        })
    return result

# ═══════════════════════════════════════
# SHARED WALLET OPERATIONS
# ═══════════════════════════════════════

async def create_shared_wallet(owner_id: int, name: str, currency: str, amount: float, color: str = "#8B5CF6"):
    wallet = {
        "owner_id": owner_id,
        "name": name,
        "currency": currency,
        "amount": amount,
        "color": color,
        "members": [
            {"user_id": owner_id, "role": "owner", "status": "active"}
        ],
        "created_at": datetime.utcnow()
    }
    result = await shared_wallets_collection.insert_one(wallet)
    return str(result.inserted_id)

async def get_user_shared_wallets(user_id: int):
    """Foydalanuvchi a'zo bo'lgan barcha umumiy hamyonlarni oladi."""
    cursor = shared_wallets_collection.find({"members.user_id": user_id, "members.status": "active"})
    return await cursor.to_list(length=100)

async def update_shared_wallet_balance(wallet_id: str, amount: float, is_income: bool):
    change = amount if is_income else -amount
    result = await shared_wallets_collection.find_one_and_update(
        {"_id": ObjectId(wallet_id)},
        {"$inc": {"amount": change}},
        return_document=True
    )
    return result["amount"] if result else 0

async def create_shared_wallet_invite(wallet_id: str, from_user_id: int, to_user_id: int, role: str):
    invite = {
        "wallet_id": wallet_id,
        "from_user_id": from_user_id,
        "to_user_id": to_user_id,
        "role": role,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    result = await invites_collection.insert_one(invite)
    return str(result.inserted_id)

async def get_user_invites(user_id: int):
    cursor = invites_collection.find({"to_user_id": user_id, "status": "pending"})
    invites = await cursor.to_list(length=100)
    # Join with wallet info
    for inv in invites:
        wallet = await shared_wallets_collection.find_one({"_id": ObjectId(inv["wallet_id"])})
        inv["wallet_name"] = wallet["name"] if wallet else "Noma'lum hamyon"
        inv["id"] = str(inv["_id"])
    return invites

async def process_invite_action(invite_id: str, action: str):
    """action: 'accept' yoki 'reject'"""
    invite = await invites_collection.find_one({"_id": ObjectId(invite_id)})
    if not invite: return False
    
    if action == "accept":
        await invites_collection.update_one({"_id": ObjectId(invite_id)}, {"$set": {"status": "accepted"}})
        # Add to wallet members
        await shared_wallets_collection.update_one(
            {"_id": ObjectId(invite["wallet_id"])},
            {"$push": {"members": {"user_id": invite["to_user_id"], "role": invite["role"], "status": "active"}}}
        )
    else:
        await invites_collection.update_one({"_id": ObjectId(invite_id)}, {"$set": {"status": "rejected"}})
    return invite

async def find_user_by_contact(contact: str):
    """contact: telefon raqam (+998...) yoki username (@...)"""
    query = {}
    if contact.startswith("+"):
        query["phone_number"] = contact
    elif contact.startswith("@"):
        query["username"] = contact.replace("@", "")
    else:
        # Balki shunchaki username yozgandir
        query["username"] = contact
        
    return await users_collection.find_one(query)

# ═══════════════════════════════════════
# REMINDER OPERATIONS
# ═══════════════════════════════════════

async def insert_reminder(data: dict) -> str:
    """
    data: {
        user_id: int,
        type: str ("financial", "general"),
        message: str,
        scheduled_time: datetime,
        status: str ("pending", "reminded", "done", "cancelled"),
        related_debt_id: str (optional)
    }
    """
    data["created_at"] = datetime.utcnow()
    data.setdefault("status", "pending")
    result = await reminders_collection.insert_one(data)
    return str(result.inserted_id)

async def get_pending_reminders() -> list:
    """Hozirgi vaqtdan o'tgan, lekin hali yuborilmagan eslatmalarni oladi."""
    now = datetime.now()
    now_utc = datetime.utcnow()
    cursor = reminders_collection.find({
        "status": "pending",
        "$or": [
            {"scheduled_time": {"$lte": now}},
            {
                "pending_transaction": {"$exists": True},
                "scheduled_time": {"$exists": False},
                "remind_at": {"$lte": now_utc}
            },
        ]
    })
    return await cursor.to_list(length=1000)

async def update_reminder_status(reminder_id: str, status: str):
    await reminders_collection.update_one(
        {"_id": ObjectId(reminder_id)},
        {"$set": {"status": status, "updated_at": datetime.utcnow()}}
    )

async def get_user_reminders(user_id: int, status: str = "pending") -> list:
    """Foydalanuvchining eslatmalarini oladi (pending yoki archive)."""
    query = {"user_id": user_id}
    if status == "archive":
        query["status"] = {"$in": ["done", "cancelled", "reminded"]}
    else:
        query["status"] = "pending"
        
    cursor = reminders_collection.find(query).sort("scheduled_time", 1 if status == "pending" else -1)
    return await cursor.to_list(length=100)

async def update_reminder_time(reminder_id: str, new_time: datetime):
    await reminders_collection.update_one(
        {"_id": ObjectId(reminder_id)},
        {
            "$set": {
                "scheduled_time": new_time,
                "status": "pending",
                "updated_at": datetime.utcnow()
            },
            "$unset": {"remind_at": ""}
        }
    )

# ═══════════════════════════════════════
# SEGMENTATION OPERATIONS
# ═══════════════════════════════════════

async def start_segmentation(telegram_id: int):
    """Onboarding tugagandan keyin segmentatsiya jarayonini boshlash.
    1-4 soat (random) oralig'ida birinchi savol yuboriladi."""
    import random
    delay_hours = random.uniform(1, 4)
    next_time = datetime.utcnow() + timedelta(hours=delay_hours)
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {
            "segmentation_stage": 0,
            "next_segment_time": next_time,
            "interests": [],
            "interest_queries": [],
        }}
    )


async def get_pending_segmentation_users():
    """Segmentation savoli yuborish kerak bo'lgan foydalanuvchilarni topadi.
    Faqat 09:00–21:00 (UTC+5) oralig'ida aktiv bo'lganlarni qaytaradi.
    ADMIN hech qachon segmentation savollariga tushmaydi."""
    now = datetime.utcnow()
    # UTC+5 da soat nechida ekanligini tekshirish (O'zbekiston vaqti)
    uzb_hour = (now.hour + 5) % 24
    if uzb_hour < 9 or uzb_hour >= 21:
        return []

    # Admin ID ni chiqarib tashlash
    admin_id = int(config.ADMIN_ID) if config.ADMIN_ID else 0

    cursor = users_collection.find({
        "registration_complete": True,
        "is_active": True,
        "segmentation_stage": {"$in": [0, 1]},
        "next_segment_time": {"$lte": now},
        "telegram_id": {"$ne": admin_id},
    })
    return await cursor.to_list(length=100)


async def update_segment_data(telegram_id: int, data: dict, advance_stage: bool = True):
    """Segment javobini saqlash va keyingi bosqichga o'tish.
    advance_stage=True bo'lsa, next_segment_time ham yangilanadi."""
    import random
    update = {"$set": data}
    if advance_stage:
        delay_hours = random.uniform(1, 4)
        next_time = datetime.utcnow() + timedelta(hours=delay_hours)
        user = await get_user(telegram_id)
        current_stage = user.get("segmentation_stage", 0)
        update["$set"]["segmentation_stage"] = current_stage + 1
        update["$set"]["next_segment_time"] = next_time
    await users_collection.update_one({"telegram_id": telegram_id}, update)


async def complete_segmentation(telegram_id: int):
    """Barcha segment savollar tugadi. Stage=2 (done)."""
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"segmentation_stage": 2, "next_segment_time": None}}
    )


async def add_user_interest(telegram_id: int, interest: str):
    """Foydalanuvchi qiziqishlarini qo'shish."""
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$addToSet": {"interests": interest}}
    )


async def add_interest_query(telegram_id: int, category: str):
    """Bu kategoriya uchun savol berilganini belgilash (qayta so'ramaslik uchun)."""
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$addToSet": {"interest_queries": category}}
    )


async def get_user_category_counts(telegram_id: int, days: int = 30) -> list:
    """Oxirgi N kunda kategoriya bo'yicha xarajatlar sonini olish."""
    since = datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {
            "telegram_id": telegram_id,
            "type": "chiqim",
            "affects_balance": True,
            "created_at": {"$gte": since}
        }},
        {"$group": {
            "_id": "$category",
            "count": {"$sum": 1},
            "total": {"$sum": "$amount"}
        }},
        {"$match": {"count": {"$gte": 2}}},
        {"$sort": {"count": -1}}
    ]
    return await transactions_collection.aggregate(pipeline).to_list(length=50)


# ═══════════════════════════════════════
# USER & BALANCE OPERATIONS
# ═══════════════════════════════════════

DEFAULT_BALANCES = {
    "UZS": {"amount": 0, "title": "So'm",   "color": "#3B82F6", "limit": None},
    "USD": {"amount": 0, "title": "Dollar", "color": "#10B981", "limit": None},
}

async def get_user(telegram_id: int) -> dict:
    """Get or create user with default UZS + USD balances."""
    user = await users_collection.find_one({"telegram_id": telegram_id})
    if not user:
        user = {
            "telegram_id": telegram_id,
            "username": None,
            "full_name": None,
            "gender": "unknown",
            "age": None,
            "location": None,
            "region": None,
            "phone_number": None,
            "registration_complete": False,
            "language": "uz",
            "balances": {k: dict(v) for k, v in DEFAULT_BALANCES.items()},
            "settings": {"morning_reminder": True, "evening_reminder": True},
            "channels_joined": False,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow(),
        }
        await users_collection.insert_one(user)
        user = await users_collection.find_one({"telegram_id": telegram_id})
    else:
        # Update last active
        await users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"last_active": datetime.utcnow()}}
        )
    return user


async def ensure_balance_exists(telegram_id: int, currency: str):
    """If currency balance doesn't exist yet, create it with 0."""
    user = await get_user(telegram_id)
    balances = user.get("balances", {})
    if currency not in balances:
        await users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": {f"balances.{currency}": {
                "amount": 0,
                "title": currency,
                "color": "#6B7280",
                "limit": None,
            }}}
        )




async def update_user_language(telegram_id: int, language: str):
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"language": language}}
    )

async def update_user_channels_joined(telegram_id: int, joined: bool):
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"channels_joined": joined}}
    )


async def update_user_name(telegram_id: int, name: str, username: str = None):
    update_data = {"full_name": name}
    if username:
        update_data["username"] = username
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": update_data}
    )

async def update_user_demographics(telegram_id: int, age: str = None, location: str = None, region: str = None):
    update_data = {}
    if age is not None: update_data["age"] = age
    if location is not None: update_data["location"] = location
    if region is not None: update_data["region"] = region
    
    if update_data:
        await users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": update_data}
        )


async def update_user_gender(telegram_id: int, gender: str):
    """Update user gender. Values: 'male', 'female', 'unknown'."""
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"gender": gender}}
    )


async def update_user_phone(telegram_id: int, phone: str):
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"phone_number": phone, "registration_complete": True}}
    )
    ws_manager.broadcast_admin("new_user", {"telegram_id": telegram_id})

async def update_user_balance(telegram_id: int, currency: str, amount: float, is_income: bool) -> float:
    """
    Kirim → balance increases.
    Chiqim → balance decreases (can go negative).
    Returns new balance amount.
    """
    currency = currency.upper()
    await ensure_balance_exists(telegram_id, currency)
    user = await get_user(telegram_id)

    current = user["balances"][currency]["amount"]
    new_amount = current + amount if is_income else current - amount

    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {f"balances.{currency}.amount": new_amount}}
    )
    await ws_manager.broadcast(telegram_id, "balance.updated", {"currency": currency, "amount": new_amount, "action": "amount_updated"})
    return new_amount


async def get_user_balance(telegram_id: int, currency: str) -> float:
    currency = currency.upper()
    await ensure_balance_exists(telegram_id, currency)
    user = await get_user(telegram_id)
    return user["balances"][currency]["amount"]


async def get_user_all_balances(telegram_id: int) -> dict:
    user = await get_user(telegram_id)
    return user.get("balances", {})


async def get_user_all_balance_names(telegram_id: int):
    """Foydalanuvchining barcha balanslari va umumiy hamyonlari nomlarini oladi (AI uchun)."""
    user = await get_user(telegram_id)
    balances = user.get("balances", {})
    private_names = [info.get("title", code) for code, info in balances.items()]
    
    shared = await get_user_shared_wallets(telegram_id)
    shared_names = [w["name"] for w in shared]
    
    return private_names + shared_names


async def resolve_balance_name(telegram_id: int, name: str):
    """
    Balans nomini ID ga aylantiradi. 
    Returns: ('private', currency_code) yoki ('shared', wallet_id) yoki (None, None)
    """
    if not name: return None, None
    
    # 1. Private balances
    user = await get_user(telegram_id)
    balances = user.get("balances", {})
    for code, info in balances.items():
        if name.lower() in [code.lower(), info.get("title", "").lower()]:
            return 'private', code
            
    # 2. Shared wallets
    shared = await get_user_shared_wallets(telegram_id)
    for w in shared:
        if name.lower() == w["name"].lower():
            return 'shared', str(w["_id"])
            
    return None, None


async def create_custom_balance(telegram_id: int, currency: str, title: str,
                                initial_amount: float, color: str, emoji: str = '💰', limit: float = None):
    """Foydalanuvchi yangi balans qo'shadi."""
    currency = currency.upper()
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {f"balances.{currency}": {
            "amount": initial_amount,
            "title": title,
            "emoji": emoji,
            "color": color,
            "limit": limit,
        }}}
    )
    await ws_manager.broadcast(telegram_id, "balance.updated", {"currency": currency, "amount": initial_amount, "action": "created"})


async def update_balance_limit(telegram_id: int, currency: str, limit: float):
    currency = currency.upper()
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {f"balances.{currency}.limit": limit}}
    )
    await ws_manager.broadcast(telegram_id, "balance.updated", {"currency": currency, "limit": limit, "action": "limit_updated"})


# ═══════════════════════════════════════
# TRANSACTION OPERATIONS
# ═══════════════════════════════════════

async def insert_transaction(data: dict) -> str:
    data["created_at"] = datetime.utcnow()
    result = await transactions_collection.insert_one(data)
    data["_id"] = str(result.inserted_id)
    if "telegram_id" in data:
        await ws_manager.broadcast(data["telegram_id"], "transaction.created", data)
        ws_manager.broadcast_admin("new_event", data)
    return str(result.inserted_id)


async def get_monthly_expense(telegram_id: int, currency: str) -> float:
    """Bu oyda qilingan jami chiqimlar summasi."""
    now = datetime.utcnow()
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    pipeline = [
        {"$match": {
            "telegram_id": telegram_id,
            "type": "chiqim",
            "currency": currency.upper(),
            "affects_balance": True,
            "created_at": {"$gte": first_day},
        }},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    cursor = transactions_collection.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    return result[0]["total"] if result else 0.0


async def get_monthly_income(telegram_id: int, currency: str) -> float:
    """Bu oyda qilingan jami kirimlar summasi."""
    now = datetime.utcnow()
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    pipeline = [
        {"$match": {
            "telegram_id": telegram_id,
            "type": "kirim",
            "currency": currency.upper(),
            "affects_balance": True,
            "created_at": {"$gte": first_day},
        }},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    cursor = transactions_collection.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    return result[0]["total"] if result else 0.0


async def get_user_financial_context(telegram_id: int) -> dict:
    """Returns financial context for the AI prompt."""
    user = await get_user(telegram_id)
    main_currency = "UZS" # Default
    # Just take the first active balance currency as main, or UZS
    balances = user.get("balances", {})
    if "UZS" in balances:
        main_currency = "UZS"
    elif balances:
        main_currency = list(balances.keys())[0]

    monthly_expense = await get_monthly_expense(telegram_id, main_currency)
    monthly_limit = balances.get(main_currency, {}).get("limit", 0)

    return {
        "language": user.get("language", "uz"),
        "main_currency": main_currency,
        "monthly_expense": monthly_expense,
        "monthly_limit": monthly_limit,
        "age": user.get("age", "Noma'lum"),
        "location": user.get("location", "Noma'lum"),
        "region": user.get("region", "Noma'lum"),
        "full_name": user.get("full_name", "Noma'lum")
    }

async def get_recent_transactions_context(telegram_id: int) -> str:
    """Returns a compressed string of the last 30 transactions to train the AI category mapping."""
    pipeline = [
        {"$match": {"telegram_id": telegram_id, "type": {"$in": ["kirim", "chiqim"]}}},
        {"$sort": {"created_at": -1}},
        {"$limit": 30},
        {"$project": {"description": 1, "category": 1}}
    ]
    cursor = transactions_collection.aggregate(pipeline)
    txs = await cursor.to_list(length=30)
    
    if not txs:
        return "Hali tranzaksiyalar yo'q."
        
    context_lines = []
    # Deduplicate by description to save tokens
    seen_desc = set()
    for tx in txs:
        desc = tx.get("description", "").lower().strip()
        cat = tx.get("category", "")
        if desc and cat and desc not in seen_desc:
            context_lines.append(f"- {desc} -> {cat}")
            seen_desc.add(desc)
            
    return "\n".join(context_lines)


async def get_transactions_paginated(
    telegram_id: int, page: int = 1, per_page: int = 10,
    type_filter: str = None, category_filter: str = None,
    currency_filter: str = None, search_query: str = None,
    date_from: str = None, date_to: str = None,
) -> tuple:
    """Returns (transactions_list, total_count) with filters and pagination."""
    query = {"telegram_id": telegram_id}

    if type_filter and type_filter != "all":
        query["type"] = type_filter
    if category_filter:
        query["category"] = {"$regex": category_filter, "$options": "i"}
    if currency_filter:
        query["currency"] = currency_filter.upper()
    if search_query:
        query["$or"] = [
            {"description": {"$regex": search_query, "$options": "i"}},
            {"category": {"$regex": search_query, "$options": "i"}},
        ]
    if date_from or date_to:
        date_q = {}
        if date_from:
            date_q["$gte"] = date_from
        if date_to:
            date_q["$lte"] = date_to
        query["date"] = date_q

    total = await transactions_collection.count_documents(query)
    skip = (page - 1) * per_page
    cursor = transactions_collection.find(query).sort("created_at", -1).skip(skip).limit(per_page)
    txs = await cursor.to_list(length=per_page)
    return txs, total


async def get_transaction_by_id(tx_id: str) -> dict | None:
    try:
        return await transactions_collection.find_one({"_id": ObjectId(tx_id)})
    except Exception:
        return None


async def update_transaction(tx_id: str, updates: dict):
    tx = await get_transaction_by_id(tx_id)
    if not tx: return
    await transactions_collection.update_one(
        {"_id": ObjectId(tx_id)},
        {"$set": updates}
    )
    if "telegram_id" in tx:
        await ws_manager.broadcast(tx["telegram_id"], "transaction.updated", {"id": tx_id, "updates": updates})


async def delete_transaction(tx_id: str) -> dict | None:
    """Delete transaction and return it for balance recalculation."""
    tx = await get_transaction_by_id(tx_id)
    if tx:
        await transactions_collection.delete_one({"_id": ObjectId(tx_id)})
        if "telegram_id" in tx:
            await ws_manager.broadcast(tx["telegram_id"], "transaction.deleted", {"id": tx_id})
    return tx


async def get_user_categories(telegram_id: int) -> list:
    """Get unique categories used by this user."""
    pipeline = [
        {"$match": {"telegram_id": telegram_id}},
        {"$group": {"_id": "$category"}},
        {"$sort": {"_id": 1}},
    ]
    result = await transactions_collection.aggregate(pipeline).to_list(length=50)
    return [r["_id"] for r in result if r["_id"]]


# ═══════════════════════════════════════
# CUSTOM CATEGORIES OPERATIONS
# ═══════════════════════════════════════

async def get_custom_categories(telegram_id: int) -> list:
    cursor = custom_categories_collection.find({"telegram_id": telegram_id}).sort("name", 1)
    return await cursor.to_list(length=100)


async def add_custom_category(telegram_id: int, emoji: str, name: str, cat_type: str, color: str = '#0A84FF') -> str:
    result = await custom_categories_collection.insert_one({
        "telegram_id": telegram_id,
        "emoji": emoji,
        "name": name,
        "type": cat_type,
        "color": color,
        "created_at": datetime.utcnow(),
    })
    await ws_manager.broadcast(telegram_id, "categories.updated", {"action": "created"})
    return str(result.inserted_id)


async def update_custom_category(cat_id: str, updates: dict):
    cat = await get_custom_category_by_id(cat_id)
    if not cat: return
    await custom_categories_collection.update_one(
        {"_id": ObjectId(cat_id)},
        {"$set": updates}
    )
    if "telegram_id" in cat:
        await ws_manager.broadcast(cat["telegram_id"], "categories.updated", {"action": "updated"})


async def delete_custom_category(cat_id: str):
    cat = await get_custom_category_by_id(cat_id)
    if cat:
        await custom_categories_collection.delete_one({"_id": ObjectId(cat_id)})
        if "telegram_id" in cat:
            await ws_manager.broadcast(cat["telegram_id"], "categories.updated", {"action": "deleted"})


async def get_custom_category_by_id(cat_id: str) -> dict | None:
    try:
        return await custom_categories_collection.find_one({"_id": ObjectId(cat_id)})
    except Exception:
        return None


# ═══════════════════════════════════════
# DEBT OPERATIONS
# ═══════════════════════════════════════

async def insert_debt(data: dict) -> str:
    data["created_at"] = datetime.utcnow()
    data.setdefault("paid_amount", 0)
    data.setdefault("status", "active")
    result = await debts_collection.insert_one(data)
    data["_id"] = str(result.inserted_id)
    if "telegram_id" in data:
        await ws_manager.broadcast(data["telegram_id"], "debt.created", data)
    return str(result.inserted_id)


async def get_debt_by_id(debt_id: str) -> dict | None:
    try:
        return await debts_collection.find_one({"_id": ObjectId(debt_id)})
    except Exception:
        return None


async def get_active_debts(telegram_id: int, direction: str = None) -> list:
    """
    direction: 'bergan' or 'olgan' or None (all).
    Returns only active/partial debts.
    """
    query = {
        "telegram_id": telegram_id,
        "status": {"$in": ["active", "partial"]},
    }
    if direction:
        query["direction"] = direction
    cursor = debts_collection.find(query).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def update_debt_status(debt_id: str, status: str, paid_amount: float = None):
    update = {"$set": {"status": status, "updated_at": datetime.utcnow()}}
    if paid_amount is not None:
        update["$set"]["paid_amount"] = paid_amount
    await debts_collection.update_one({"_id": ObjectId(debt_id)}, update)
    
    debt = await get_debt_by_id(debt_id)
    if debt and "telegram_id" in debt:
        if status == "paid":
            await ws_manager.broadcast(debt["telegram_id"], "debt.paid", {"id": debt_id})
        else:
            await ws_manager.broadcast(debt["telegram_id"], "debt.updated", {"id": debt_id, "status": status})


async def update_debt_due_date(debt_id: str, new_due_date: str):
    await debts_collection.update_one(
        {"_id": ObjectId(debt_id)},
        {"$set": {"due_date": new_due_date, "updated_at": datetime.utcnow()}}
    )
    debt = await get_debt_by_id(debt_id)
    if debt and "telegram_id" in debt:
        await ws_manager.broadcast(debt["telegram_id"], "debt.updated", {"id": debt_id, "due_date": new_due_date})


async def delete_debt(debt_id: str):
    debt = await get_debt_by_id(debt_id)
    await debts_collection.update_one(
        {"_id": ObjectId(debt_id)},
        {"$set": {"status": "cancelled", "updated_at": datetime.utcnow()}}
    )
    if debt and "telegram_id" in debt:
        await ws_manager.broadcast(debt["telegram_id"], "debt.updated", {"id": debt_id, "status": "cancelled"})


async def get_debts_due_soon(days_ahead: int = 3) -> list:
    """Muddati yaqinlashgan yoki o'tgan qarzlar."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    future = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    cursor = debts_collection.find({
        "status": {"$in": ["active", "partial"]},
        "due_date": {"$ne": "nomalum", "$ne": None},
    })
    debts = await cursor.to_list(length=500)

    result = []
    for d in debts:
        dd = d.get("due_date", "")
        if not dd or dd == "nomalum":
            continue
        result.append(d)
    return result


async def get_total_debt_by_direction(telegram_id: int, direction: str, currency: str = None) -> float:
    query = {
        "telegram_id": telegram_id,
        "direction": direction,
        "status": {"$in": ["active", "partial"]},
    }
    if currency:
        query["currency"] = currency.upper()

    pipeline = [
        {"$match": query},
        {"$group": {"_id": None, "total": {"$sum": {
            "$subtract": ["$amount", {"$ifNull": ["$paid_amount", 0]}]
        }}}},
    ]
    cursor = debts_collection.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    return result[0]["total"] if result else 0.0


# ═══════════════════════════════════════
# ADMIN & CHANNELS OPERATIONS
# ═══════════════════════════════════════

async def is_admin(telegram_id: int) -> bool:
    # Strictly only ADMIN_ID can use admin commands per new requirements
    return str(telegram_id) == str(config.ADMIN_ID)

async def set_user_blacklist(telegram_id: int, status: bool) -> bool:
    """Ban or unban a user."""
    result = await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"is_blacklisted": status}}
    )
    return result.modified_count > 0 or result.matched_count > 0


async def add_admin(telegram_id: int) -> bool:
    if await is_admin(telegram_id):
        return False
    await admins_collection.insert_one({"telegram_id": telegram_id, "added_at": datetime.utcnow()})
    return True


async def remove_admin(telegram_id: int) -> bool:
    if str(telegram_id) == str(config.ADMIN_ID):
        return False # Cannot remove Super Admin
    result = await admins_collection.delete_one({"telegram_id": telegram_id})
    return result.deleted_count > 0


async def get_all_channels() -> list:
    cursor = channels_collection.find({})
    return await cursor.to_list(length=100)


async def add_channel(link: str, name: str) -> bool:
    exists = await channels_collection.find_one({"link": link})
    if exists:
        return False
    # If link is like https://t.me/kanalnomi, the chat_id checking is easier if we store username
    # We will just store the link and name for the button.
    await channels_collection.insert_one({"link": link, "name": name, "added_at": datetime.utcnow()})
    return True


async def remove_channel(link: str) -> bool:
    result = await channels_collection.delete_one({"link": link})
    return result.deleted_count > 0

async def update_channel_by_index(index: int, new_link: str, new_name: str) -> bool:
    """O'zgartirish index orqali, bu yerda index 0-based"""
    channels = await get_all_channels()
    if index < 0 or index >= len(channels):
        return False
    target_id = channels[index]["_id"]
    await channels_collection.update_one({"_id": target_id}, {"$set": {"link": new_link, "name": new_name}})
    return True


async def update_last_channel_check(telegram_id: int):
    """Kanal obunasi muvaffaqiyatli tekshirilgandan keyin vaqtni yangilash."""
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"last_channel_check": datetime.utcnow()}}
    )


def should_check_channel_subscription(user: dict) -> bool:
    """Foydalanuvchi obunasini tekshirish kerakmi? (24 soat o'tganmi?)
    - last_channel_check yo'q → tekshirish kerak
    - 24 soat o'tgan → tekshirish kerak
    - 24 soat o'tmagan → tekshirish shart emas
    """
    last_check = user.get("last_channel_check")
    if not last_check:
        return True
    return (datetime.utcnow() - last_check) > timedelta(hours=24)


# ═══════════════════════════════════════
# MEMORY & HABITS (QISM 5)
# ═══════════════════════════════════════

async def get_user_habits(telegram_id: int) -> dict:
    """
    QISM 5: Oxirgi 50 ta tranzaksiyadan foydalanuvchi odatlarini (habits) aniqlaydi.
    """
    pipeline = [
        {"$match": {
            "telegram_id": telegram_id,
            "type": {"$in": ["kirim", "chiqim"]},
            "affects_balance": True
        }},
        {"$sort": {"_id": -1}},
        {"$limit": 50}
    ]
    cursor = transactions_collection.aggregate(pipeline)
    transactions = await cursor.to_list(length=50)

    if not transactions:
        return {"default_category": None, "default_currency": None, "category_averages": {}}

    cat_counts = {}
    curr_counts = {}
    cat_amounts = {}

    for tx in transactions:
        cat = tx.get("category")
        curr = tx.get("currency")
        amt = tx.get("amount", 0)
        
        if cat:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            if cat not in cat_amounts:
                cat_amounts[cat] = []
            cat_amounts[cat].append(amt)
            
        if curr:
            curr_counts[curr] = curr_counts.get(curr, 0) + 1

    default_cat = max(cat_counts, key=cat_counts.get) if cat_counts else None
    default_curr = max(curr_counts, key=curr_counts.get) if curr_counts else None
    
    cat_averages = {}
    for c, amts in cat_amounts.items():
        if len(amts) >= 2: # At least 2 transactions required for a reliable average
            cat_averages[c] = sum(amts) / len(amts)

    return {
        "default_category": default_cat,
        "default_currency": default_curr,
        "category_averages": cat_averages
    }

# ═══════════════════════════════════════
# TRANZAKSIYA TAHRIRLASH VA HISOBOTLAR (QISM 6)
# ═══════════════════════════════════════

async def get_last_transaction(telegram_id: int):
    cursor = transactions_collection.find({
        "telegram_id": telegram_id,
        "type": {"$in": ["kirim", "chiqim"]}
    }).sort("_id", -1).limit(1)
    results = await cursor.to_list(length=1)
    return results[0] if results else None

async def delete_transaction_by_id(tx_id: str):
    from bson.objectid import ObjectId
    result = await transactions_collection.delete_one({"_id": ObjectId(tx_id)})
    return result.deleted_count > 0

async def update_transaction_by_id(tx_id: str, updates: dict):
    from bson.objectid import ObjectId
    result = await transactions_collection.update_one({"_id": ObjectId(tx_id)}, {"$set": updates})
    return result.modified_count > 0

async def change_transaction_category(tx_id: str, new_category: str) -> bool:
    """Tranzaksiya kategoriyasini o'zgartirish."""
    return await update_transaction_by_id(tx_id, {"category": new_category})

async def change_transaction_balance(tx_id: str, new_currency: str) -> bool:
    """
    Tranzaksiya hisobini (valyutasini) o'zgartirish.
    Eski balandni tiklaydi, yangisidan ayiradi/qo'shadi.
    """
    tx = await get_transaction_by_id(tx_id)
    if not tx: return False
    
    old_currency = tx.get("currency")
    if old_currency == new_currency: return True
    
    user_id = tx["telegram_id"]
    amount = tx["amount"]
    is_inc = (tx["type"] == "kirim")
    
    # 1. Eski balansni tiklash
    # Agar chiqim bo'lgan bo'lsa - summani qaytaramiz (+), kirim bo'lsa - ayiramiz (-)
    await update_user_balance(user_id, old_currency, amount, is_income=(not is_inc))
    
    # 2. Yangi balansni o'zgartirish
    await update_user_balance(user_id, new_currency, amount, is_income=is_inc)
    
    # 3. Tranzaksiyani yangilash
    return await update_transaction_by_id(tx_id, {"currency": new_currency})

async def confirm_delete_transaction_logic(tx_id: str) -> bool:
    """Tranzaksiyani o'chirish va balansni tiklash."""
    tx = await get_transaction_by_id(tx_id)
    if not tx: return False
    
    user_id = tx["telegram_id"]
    amount = tx["amount"]
    currency = tx["currency"]
    is_inc = (tx["type"] == "kirim")
    
    # Balansni tiklash (teskari amal)
    await update_user_balance(user_id, currency, amount, is_income=(not is_inc))
    
    # O'chirish
    return await delete_transaction_by_id(tx_id)

async def get_monthly_summary(telegram_id: int, date_str: str = None) -> dict:
    if not date_str:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    prefix = date_str[:7] # YYYY-MM
    pipeline = [
        {"$match": {
            "telegram_id": telegram_id,
            "date": {"$regex": f"^{prefix}"},
            "affects_balance": True
        }}
    ]
    cursor = transactions_collection.aggregate(pipeline)
    txs = await cursor.to_list(length=2000)
    
    kirim = 0
    chiqim = 0
    categories = {}
    
    for t in txs:
        amt = t.get("amount", 0)
        if t.get("type") == "kirim":
            kirim += amt
        elif t.get("type") == "chiqim":
            chiqim += amt
            cat = t.get("category", "Boshqa")
            categories[cat] = categories.get(cat, 0) + amt
            
    return {
        "total_kirim": kirim,
        "total_chiqim": chiqim,
        "categories": categories,
        "transactions_count": len(txs),
        "month": prefix
    }
    await channels_collection.update_one(
        {"_id": target_id},
        {"$set": {"link": new_link, "name": new_name, "updated_at": datetime.utcnow()}}
    )
    return True

async def set_webapp_url(url: str):
    await config_collection.update_one(
        {"_id": "webapp_url"},
        {"$set": {"url": url}},
        upsert=True
    )

_webapp_url_cache = {"url": None, "ts": 0}

async def get_webapp_url() -> str:
    import time
    now = time.time()
    # Return cached value if fresh (60 seconds)
    if _webapp_url_cache["url"] and (now - _webapp_url_cache["ts"]) < 60:
        return _webapp_url_cache["url"]
    # Priority: env var > database > fallback
    env_url = os.environ.get("WEBAPP_URL")
    if env_url:
        _webapp_url_cache["url"] = env_url
        _webapp_url_cache["ts"] = now
        return env_url
    doc = await config_collection.find_one({"_id": "webapp_url"})
    result = doc.get("url", "https://somlyai-project-production.up.railway.app") if doc else "https://somlyai-project-production.up.railway.app"
    _webapp_url_cache["url"] = result
    _webapp_url_cache["ts"] = now
    return result


# ═══════════════════════════════════════
# STATISTICS OPERATIONS
# ═══════════════════════════════════════

async def get_bot_statistics() -> dict:
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = today - timedelta(days=7)

    total_users = await users_collection.count_documents({})
    today_users = await users_collection.count_documents({"created_at": {"$gte": today}})
    active_users = await users_collection.count_documents({"last_active": {"$gte": seven_days_ago}})
    today_messages = await transactions_collection.count_documents({"created_at": {"$gte": today}})
    
    total_txs = await transactions_collection.count_documents({})
    
    # Lang counts
    uz_count = await users_collection.count_documents({"language": "uz"})
    ru_count = await users_collection.count_documents({"language": "ru"})
    en_count = await users_collection.count_documents({"language": "en"})
    
    uz_p = int((uz_count / total_users * 100) if total_users > 0 else 0)
    ru_p = int((ru_count / total_users * 100) if total_users > 0 else 0)
    en_p = int((en_count / total_users * 100) if total_users > 0 else 0)

    return {
        "total_users": total_users,
        "today_users": today_users,
        "active_users": active_users,
        "today_messages": today_messages,
        "today_txs": today_messages,  # For simple mapping
        "total_txs": total_txs,
        "langs": f"UZ: {uz_p}% | RU: {ru_p}% | EN: {en_p}%"
    }

async def get_advanced_dashboard_stats() -> dict:
    """Admin Dashboard uchun kompleks grafik va heatmap statistikalari."""
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 1. 30-day User Growth (Line Chart)
    thirty_days_ago = today - timedelta(days=29)
    pipeline_30d = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": {
                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    users_30d_raw = await users_collection.aggregate(pipeline_30d).to_list(100)
    
    # Fill missing days with 0
    users_growth_30d = []
    for i in range(30):
        d = (thirty_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        found = next((item["count"] for item in users_30d_raw if item["_id"] == d), 0)
        users_growth_30d.append({"date": d[-5:], "count": found})  # only MM-DD for chart

    # 2. 7-day Messages (Bar Chart) - Using transactions_collection as proxy for messages
    seven_days_ago = today - timedelta(days=6)
    pipeline_7d = [
        {"$match": {"created_at": {"$gte": seven_days_ago}}},
        {"$group": {
            "_id": {
                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    msgs_7d_raw = await transactions_collection.aggregate(pipeline_7d).to_list(100)
    
    messages_7d = []
    for i in range(7):
        d = (seven_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        found = next((item["count"] for item in msgs_7d_raw if item["_id"] == d), 0)
        messages_7d.append({"date": d[-5:], "count": found})

    # 3. Heatmap Data (7 days x 24 hours) from transactions/messages
    pipeline_heatmap = [
        {"$match": {"created_at": {"$gte": seven_days_ago}}},
        {"$project": {
            "dayOfWeek": {"$dayOfWeek": "$created_at"}, # 1: Sun, 2: Mon, ... 7: Sat
            "hour": {"$hour": "$created_at"}
        }},
        {"$group": {
            "_id": {"day": "$dayOfWeek", "hour": "$hour"},
            "count": {"$sum": 1}
        }}
    ]
    heatmap_raw = await transactions_collection.aggregate(pipeline_heatmap).to_list(200)
    
    # Format heatmap data: array of { day: 0-6 (Mon-Sun), hour: 0-23, count: N }
    # MongoDB $dayOfWeek: 1 (Sun) to 7 (Sat). We want 0 (Mon) to 6 (Sun).
    heatmap_data = []
    for item in heatmap_raw:
        mongo_day = item["_id"]["day"]
        hour = item["_id"]["hour"]
        js_day = (mongo_day + 5) % 7 # Convert 1(Sun)->6, 2(Mon)->0, ..., 7(Sat)->5
        heatmap_data.append({"day": js_day, "hour": hour, "count": item["count"]})

    # 4. Recent Events
    # We fetch the latest 5 registered users as recent events
    recent_users = await users_collection.find(
        {"created_at": {"$exists": True}}
    ).sort("created_at", -1).limit(5).to_list(5)
    
    recent_events = []
    for u in recent_users:
        name = u.get("full_name") or u.get("username") or str(u.get("telegram_id"))
        city = u.get("region") or u.get("country") or "Noma'lum"
        dt = u.get("created_at")
        time_str = dt.strftime("%Y-%m-%d %H:%M") if dt else "Yaqinda"
        recent_events.append({
            "type": "user",
            "text": f"Yangi user: {name} ({city})",
            "time": time_str
        })
        
    # Also fetch latest channels if any
    recent_channels = await channels_collection.find().sort("_id", -1).limit(2).to_list(2)
    for c in recent_channels:
        recent_events.append({
            "type": "channel",
            "text": f"Kanal qo'shildi: {c.get('name')}",
            "time": "Yaqinda"
        })

    # Eng aktiv vaqt va kun (umumiy)
    from collections import defaultdict
    g_hour_totals = defaultdict(int)
    g_day_totals = defaultdict(int)
    for item in heatmap_data:
        g_hour_totals[item["hour"]] += item["count"]
        g_day_totals[item["day"]] += item["count"]
    
    g_best_hour = max(g_hour_totals, key=g_hour_totals.get) if g_hour_totals else None
    g_best_day = max(g_day_totals, key=g_day_totals.get) if g_day_totals else None
    g_day_names = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

    return {
        "users_growth_30d": users_growth_30d,
        "messages_7d": messages_7d,
        "heatmap": heatmap_data,
        "recent_events": recent_events,
        "global_best_hour": g_best_hour,
        "global_best_day": g_day_names[g_best_day] if g_best_day is not None else "Noma'lum"
    }

async def get_user_full_stats(telegram_id: int) -> dict:
    user = await users_collection.find_one({"telegram_id": telegram_id})
    if not user:
        return None
        
    tx_count = await transactions_collection.count_documents({"telegram_id": telegram_id})
    
    return {
        "full_name": user.get("full_name", "Noma'lum"),
        "phone": user.get("phone_number", "Noma'lum"),
        "created_at": user.get("created_at", datetime.utcnow()).strftime("%Y-%m-%d"),
        "balances": user.get("balances", {}),
        "tx_count": tx_count,
        "last_active": user.get("last_active", datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S")
    }

async def get_admin_users_data() -> list:
    """Returns safe demographic data of all users for the admin panel."""
    cursor = users_collection.find({}, {
        "telegram_id": 1,
        "username": 1,
        "full_name": 1,
        "phone_number": 1,
        "age": 1,
        "location": 1,
        "region": 1,
        "created_at": 1,
        "last_active": 1,
        "language": 1,
        "is_active": 1
    }).sort("created_at", -1)
    
    users = await cursor.to_list(length=10000)
    # Format dates to string
    for u in users:
        u["_id"] = str(u["_id"])
        if "created_at" in u and u["created_at"]:
            u["created_at"] = u["created_at"].strftime("%Y-%m-%d %H:%M")
        if "last_active" in u and u["last_active"]:
            u["last_active"] = u["last_active"].strftime("%Y-%m-%d %H:%M")
    return users

async def get_admin_user_detail(telegram_id: int) -> dict:
    """Returns extremely detailed information for a single user for the admin panel."""
    user = await users_collection.find_one({"telegram_id": telegram_id})
    if not user:
        return None
        
    # Transaction statistics
    tx_pipeline = [
        {"$match": {"telegram_id": telegram_id}},
        {"$group": {
            "_id": "$type", # "income" or "expense"
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }}
    ]
    tx_stats = await transactions_collection.aggregate(tx_pipeline).to_list(10)
    
    total_txs = await transactions_collection.count_documents({"telegram_id": telegram_id})
    
    # Calculate avg monthly income/expense (simple estimation based on total / months since join)
    created_at = user.get("created_at", datetime.utcnow())
    months_active = max(1, (datetime.utcnow() - created_at).days / 30)
    
    total_income = 0
    total_expense = 0
    for stat in tx_stats:
        if stat["_id"] == "income": total_income = stat["total"]
        if stat["_id"] == "expense": total_expense = stat["total"]
        
    avg_income = int(total_income / months_active)
    avg_expense = int(abs(total_expense) / months_active)
    
    # Top expense category
    top_cat_pipeline = [
        {"$match": {"telegram_id": telegram_id, "type": "expense"}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": 1}}, # expense is negative, so smallest is biggest expense
        {"$limit": 1}
    ]
    top_cat = await transactions_collection.aggregate(top_cat_pipeline).to_list(1)
    top_expense_cat = top_cat[0]["_id"] if top_cat else "Noma'lum"
    
    # Income level
    income_level = "O'rta"
    if avg_income > 5000000: income_level = "Yuqori"
    elif avg_income < 2000000 and avg_income > 0: income_level = "Past"
    elif avg_income == 0: income_level = "Noma'lum"
    
    # Activity Graph (30 days)
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = today - timedelta(days=29)
    activity_pipeline = [
        {"$match": {"telegram_id": telegram_id, "created_at": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": {
                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    activity_raw = await transactions_collection.aggregate(activity_pipeline).to_list(100)
    
    activity_30d = []
    for i in range(30):
        d = (thirty_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        found = next((item["count"] for item in activity_raw if item["_id"] == d), 0)
        activity_30d.append({"date": d[-5:], "count": found})
        
    # Format basic dates
    created_str = created_at.strftime("%Y-%m-%d %H:%M")
    last_active_str = user.get("last_active", datetime.utcnow()).strftime("%Y-%m-%d %H:%M")

    # Financial History
    history_cursor = financial_history_collection.find({"telegram_id": telegram_id}).sort("month", -1)
    history_list = await history_cursor.to_list(length=50)
    for h in history_list:
        h["_id"] = str(h["_id"])
        h["calculated_at"] = h["calculated_at"].strftime("%Y-%m-%d %H:%M") if "calculated_at" in h else ""
    # User Individual Heatmap (7x24)
    heatmap_pipeline = [
        {"$match": {"telegram_id": telegram_id}},
        {"$group": {
            "_id": {
                "dayOfWeek": {"$dayOfWeek": "$created_at"},
                "hour": {"$hour": "$created_at"}
            },
            "count": {"$sum": 1}
        }}
    ]
    heatmap_raw = await transactions_collection.aggregate(heatmap_pipeline).to_list(200)
    
    user_heatmap = []
    for item in heatmap_raw:
        mongo_day = item["_id"]["dayOfWeek"]  # 1=Sunday, 2=Monday...7=Saturday
        hour = item["_id"]["hour"]
        js_day = (mongo_day - 2) % 7  # Convert to 0=Monday...6=Sunday
        user_heatmap.append({"day": js_day, "hour": hour, "count": item["count"]})

    # Eng aktiv vaqt va kun
    best_hour = None
    best_day = None
    if user_heatmap:
        from collections import defaultdict
        hour_totals = defaultdict(int)
        day_totals = defaultdict(int)
        for item in user_heatmap:
            hour_totals[item["hour"]] += item["count"]
            day_totals[item["day"]] += item["count"]
        best_hour = max(hour_totals, key=hour_totals.get) if hour_totals else None
        best_day = max(day_totals, key=day_totals.get) if day_totals else None

    day_names = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

    return {
        "basic": {
            "telegram_id": user["telegram_id"],
            "full_name": user.get("full_name", "Noma'lum"),
            "username": user.get("username", ""),
            "phone_number": user.get("phone_number", "Kiritilmagan"),
            "language": user.get("language", "uz"),
            "created_at": created_str,
            "last_active": last_active_str,
            "total_messages": total_txs,
            "total_txs": total_txs,
            "is_active": user.get("is_active", True)
        },
        "segment": {
            "age_group": user.get("age_group", "Noma'lum"),
            "gender": user.get("gender", "Noma'lum"),
            "location": user.get("location", "Noma'lum"),
            "region": user.get("region", "Noma'lum"),
            "timezone": user.get("timezone", "UTC+5"),
            "interests": user.get("interests", [])
        },
        "financial": {
            "avg_income": avg_income,
            "avg_expense": avg_expense,
            "income_level": income_level,
            "top_expense_cat": top_expense_cat
        },
        "activity_30d": activity_30d,
        "financial_history": history_list,
        "user_heatmap": user_heatmap,
        "best_hour": best_hour,
        "best_day": day_names[best_day] if best_day is not None else "Noma'lum"
    }

async def get_filtered_segment_data(filters: dict) -> dict:
    """Facebook Ads uslubidagi segmentatsiya uchun agregatsiya."""
    query = {}
    
    # 1. Build Query
    if filters.get("age_groups") and len(filters["age_groups"]) > 0:
        query["age_group"] = {"$in": filters["age_groups"]}
    
    if filters.get("genders") and len(filters["genders"]) > 0:
        query["gender"] = {"$in": filters["genders"]}
        
    if filters.get("countries") and len(filters["countries"]) > 0:
        query["country"] = {"$in": filters["countries"]}
        
    if filters.get("regions") and len(filters["regions"]) > 0:
        query["region"] = {"$in": filters["regions"]}
        
    if filters.get("languages") and len(filters["languages"]) > 0:
        query["language"] = {"$in": filters["languages"]}
        
    if filters.get("interests") and len(filters["interests"]) > 0:
        query["interests"] = {"$in": filters["interests"]}

    # Match users
    matched_cursor = users_collection.find(query, {
        "telegram_id": 1, "full_name": 1, "username": 1, 
        "region": 1, "age_group": 1, "gender": 1, "language": 1
    })
    matched_users = await matched_cursor.to_list(length=10000)
    matched_count = len(matched_users)
    
    if matched_count == 0:
        return {
            "count": 0,
            "top_regions": [],
            "avg_income": 0,
            "top_expense_cat": "Noma'lum",
            "lang_chart": [],
            "age_chart": [],
            "heatmap": [],
            "users": []
        }
        
    user_ids = [u["telegram_id"] for u in matched_users]
    
    # 2. Users Aggregations (Lang & Age & Region)
    lang_counts = {}
    age_counts = {}
    region_counts = {}
    for u in matched_users:
        l = u.get("language", "uz")
        a = u.get("age_group", "Noma'lum")
        r = u.get("region", "Noma'lum")
        lang_counts[l] = lang_counts.get(l, 0) + 1
        age_counts[a] = age_counts.get(a, 0) + 1
        region_counts[r] = region_counts.get(r, 0) + 1
        
    lang_chart = [{"name": k, "value": v} for k, v in lang_counts.items()]
    age_chart = [{"name": k, "value": v} for k, v in age_counts.items()]
    
    sorted_regions = sorted(region_counts.items(), key=lambda x: x[1], reverse=True)
    top_regions = [r[0] for r in sorted_regions[:2]]
    
    # 3. Transactions Aggregation
    # Instead of pulling all transactions, we aggregate on db level
    # Income levels (Filtering by income level happens here if needed)
    tx_pipeline = [
        {"$match": {"telegram_id": {"$in": user_ids}}},
        {"$facet": {
            "income": [
                {"$match": {"type": "income"}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ],
            "expenses_by_cat": [
                {"$match": {"type": "expense"}},
                {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
                {"$sort": {"total": 1}},
                {"$limit": 1}
            ],
            "heatmap": [
                {"$project": {
                    "dayOfWeek": {"$dayOfWeek": "$created_at"},
                    "hour": {"$hour": "$created_at"}
                }},
                {"$group": {
                    "_id": {"day": "$dayOfWeek", "hour": "$hour"},
                    "count": {"$sum": 1}
                }}
            ]
        }}
    ]
    tx_res = await transactions_collection.aggregate(tx_pipeline).to_list(1)
    
    total_income = 0
    top_expense_cat = "Noma'lum"
    heatmap_raw = []
    
    if tx_res and len(tx_res) > 0:
        res = tx_res[0]
        if res.get("income") and len(res["income"]) > 0:
            total_income = res["income"][0]["total"]
        if res.get("expenses_by_cat") and len(res["expenses_by_cat"]) > 0:
            top_expense_cat = res["expenses_by_cat"][0]["_id"]
        if res.get("heatmap"):
            heatmap_raw = res["heatmap"]
            
    # Rough average income estimation
    # Assume average active months per user is 2
    avg_income = int(total_income / (matched_count * 2)) if matched_count > 0 else 0
    
    # Format Heatmap
    heatmap_data = []
    for item in heatmap_raw:
        if not item.get("_id"): continue
        mongo_day = item["_id"].get("day")
        hour = item["_id"].get("hour")
        if mongo_day is None or hour is None: continue
        js_day = (mongo_day + 5) % 7 
        heatmap_data.append({"day": js_day, "hour": hour, "count": item["count"]})
        
    # If income level filter is provided, we should ideally filter `matched_users` again
    # But since that requires calculating income per user, we will simplify: 
    # if the overall avg_income doesn't match the level, or we just skip this strict check for MVP.
    # The prompt allows checking basic info.
    
    # Prepare limited user list to return (e.g., first 500)
    users_to_return = []
    for u in matched_users[:500]:
        users_to_return.append({
            "telegram_id": u["telegram_id"],
            "full_name": u.get("full_name", "Noma'lum"),
            "region": u.get("region", "Noma'lum"),
            "age_group": u.get("age_group", "Noma'lum"),
            "gender": u.get("gender", "Noma'lum")
        })

    return {
        "count": matched_count,
        "top_regions": top_regions,
        "avg_income": avg_income,
        "top_expense_cat": top_expense_cat,
        "lang_chart": lang_chart,
        "age_chart": age_chart,
        "heatmap": heatmap_data,
        "users": users_to_return
    }

async def save_broadcast_job(job_id: str, data: dict):
    """Saves or updates a broadcast job."""
    await broadcasts_collection.update_one(
        {"_id": job_id},
        {"$set": data},
        upsert=True
    )

async def get_broadcast_job(job_id: str) -> dict:
    return await broadcasts_collection.find_one({"_id": job_id})

async def get_broadcast_history(limit: int = 10) -> list:
    """Returns the most recent broadcast jobs."""
    cursor = broadcasts_collection.find().sort("created_at", -1).limit(limit)
    history = await cursor.to_list(length=limit)
    for item in history:
        item["_id"] = str(item["_id"])
        if "created_at" in item and item["created_at"]:
            item["created_at"] = item["created_at"].strftime("%Y-%m-%d %H:%M:%S")
    return history

# ═══════════════════════════════════════
# GROUP OPERATIONS
# ═══════════════════════════════════════

async def create_group(owner_id: int, name: str) -> str:
    """Yangi guruh yaratish. Owner avtomatik a'zo bo'ladi."""
    owner = await get_user(owner_id)
    owner_name = owner.get("full_name", "Noma'lum")
    group = {
        "name": name,
        "owner_id": owner_id,
        "members": [
            {"telegram_id": owner_id, "name": owner_name, "role": "admin"}
        ],
        "balances": {
            "UZS": {"amount": 0, "title": "So'm", "color": "#3B82F6"},
            "USD": {"amount": 0, "title": "Dollar", "color": "#10B981"}
        },
        "telegram_chat_id": None,
        "is_configured": True,
        "created_at": datetime.utcnow(),
    }
    result = await groups_collection.insert_one(group)
    return str(result.inserted_id)


async def get_user_groups(telegram_id: int) -> list:
    """Foydalanuvchi a'zo bo'lgan barcha guruhlar."""
    cursor = groups_collection.find(
        {"members.telegram_id": telegram_id}
    ).sort("created_at", -1)
    groups = await cursor.to_list(length=50)
    for g in groups:
        g["id"] = str(g["_id"])
        del g["_id"]
        if g.get("created_at"):
            g["created_at"] = g["created_at"].isoformat()
    return groups


async def get_group_by_id(group_id: str) -> dict | None:
    try:
        group = await groups_collection.find_one({"_id": ObjectId(group_id)})
        if group:
            group["id"] = str(group["_id"])
            del group["_id"]
            if group.get("created_at"):
                group["created_at"] = group["created_at"].isoformat()
        return group
    except Exception:
        return None


async def get_group_by_chat_id(chat_id: int) -> dict | None:
    """Telegram chat_id orqali guruhni topish."""
    group = await groups_collection.find_one({"telegram_chat_id": chat_id})
    if group:
        group["id"] = str(group["_id"])
        del group["_id"]
    return group


async def add_group_member(group_id: str, telegram_id: int, name: str) -> bool:
    """Guruhga a'zo qo'shish. Agar allaqachon bo'lsa False qaytaradi."""
    group = await groups_collection.find_one({"_id": ObjectId(group_id)})
    if not group:
        return False
    for m in group.get("members", []):
        if m["telegram_id"] == telegram_id:
            return False  # Already a member
    await groups_collection.update_one(
        {"_id": ObjectId(group_id)},
        {"$push": {"members": {
            "telegram_id": telegram_id,
            "name": name,
            "role": "member",
            "added_at": datetime.utcnow().isoformat()
        }}}
    )
    return True


async def remove_group_member(group_id: str, telegram_id: int) -> bool:
    result = await groups_collection.update_one(
        {"_id": ObjectId(group_id)},
        {"$pull": {"members": {"telegram_id": telegram_id}}}
    )
    return result.modified_count > 0


async def search_user_by_phone(phone: str) -> dict | None:
    """Telefon raqami bo'yicha foydalanuvchi qidirish."""
    # Normalize: remove spaces, dashes, plus
    clean = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    user = await users_collection.find_one({
        "$or": [
            {"phone_number": {"$regex": clean[-9:]}},  # Last 9 digits match
            {"phone_number": phone}
        ]
    })
    if user:
        return {
            "telegram_id": user["telegram_id"],
            "full_name": user.get("full_name", "Noma'lum"),
            "phone_number": user.get("phone_number", ""),
            "username": user.get("username", "")
        }
    return None


async def link_telegram_chat(group_id: str, chat_id: int):
    """Telegram guruh chat_id ni guruhga bog'lash."""
    await groups_collection.update_one(
        {"_id": ObjectId(group_id)},
        {"$set": {"telegram_chat_id": chat_id, "is_configured": True}}
    )


async def update_group_balance(group_id: str, currency: str, amount: float, is_income: bool) -> float:
    """Guruh balansini yangilash. Shaxsiy balansga ta'sir qilmaydi."""
    currency = currency.upper()
    group = await groups_collection.find_one({"_id": ObjectId(group_id)})
    if not group:
        return 0

    balances = group.get("balances", {})
    if currency not in balances:
        balances[currency] = {"amount": 0, "title": currency, "color": "#6B7280"}

    current = balances[currency]["amount"]
    new_amount = current + amount if is_income else current - amount

    await groups_collection.update_one(
        {"_id": ObjectId(group_id)},
        {"$set": {f"balances.{currency}.amount": new_amount}}
    )
    return new_amount


async def add_group_balance(group_id: str, currency: str, title: str, color: str = "#3B82F6"):
    """Guruhga yangi balans turi qo'shish."""
    currency = currency.upper()
    await groups_collection.update_one(
        {"_id": ObjectId(group_id)},
        {"$set": {f"balances.{currency}": {
            "amount": 0, "title": title, "color": color
        }}}
    )


async def insert_group_transaction(group_id: str, data: dict) -> str:
    """Guruh tranzaksiyasini saqlash. Shaxsiy balansga ta'sir qilmaydi."""
    data["group_id"] = group_id
    data["created_at"] = datetime.utcnow()
    result = await transactions_collection.insert_one(data)
    return str(result.inserted_id)

# ═══════════════════════════════════════
# DYNAMIC KNOWLEDGE BASE (QISM 8)
# ═══════════════════════════════════════

async def add_knowledge(topic: str, content: str, admin_id: int) -> bool:
    exists = await knowledge_collection.find_one({"topic": topic})
    if exists:
        return False
    await knowledge_collection.insert_one({
        "topic": topic,
        "content": content,
        "added_by": admin_id,
        "added_at": datetime.utcnow(),
        "active": True,
        "usage_count": 0
    })
    return True

async def get_all_knowledges() -> list:
    cursor = knowledge_collection.find({}).sort("usage_count", -1)
    return await cursor.to_list(length=100)

async def get_active_knowledge_context() -> str:
    # Fetch all active knowledges
    cursor = knowledge_collection.find({"active": True})
    knowledges = await cursor.to_list(length=100)
    
    if not knowledges:
        return ""
        
    # Increment usage count for all active knowledges
    topic_ids = [k["_id"] for k in knowledges]
    if topic_ids:
        import asyncio
        asyncio.create_task(knowledge_collection.update_many(
            {"_id": {"$in": topic_ids}},
            {"$inc": {"usage_count": 1}}
        ))
    
    context_str = ""
    for k in knowledges:
        context_str += f"Mavzu: {k['topic']}\nMa'lumot: {k['content']}\n\n"
        
    return context_str.strip()

async def set_knowledge_active(topic: str, active: bool) -> bool:
    result = await knowledge_collection.update_one(
        {"topic": topic},
        {"$set": {"active": active}}
    )
    return result.modified_count > 0

async def update_knowledge(topic: str, new_content: str) -> bool:
    result = await knowledge_collection.update_one(
        {"topic": topic},
        {"$set": {"content": new_content, "active": True}}
    )
    return result.modified_count > 0


# ═══════════════════════════════════════
# FINANCIAL ADVICE OPERATIONS
# ═══════════════════════════════════════

async def get_financial_advice_context(telegram_id: int, currency: str = "UZS"):
    """
    Maslahat uchun kerakli ma'lumotlarni yig'adi:
    - Oxirgi 3 oylik umumiy xarajatlar
    - Joriy oy kategoriyalari
    - Limit holati
    - Qarzlar holati
    """
    from datetime import datetime, timedelta
    
    today = datetime.utcnow()
    first_day_this_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    three_months_ago = (first_day_this_month - timedelta(days=60)).replace(day=1)
    
    # Oxirgi 3 oy xarajatlari oylar kesimida
    pipeline_3m = [
        {"$match": {
            "telegram_id": telegram_id,
            "currency": currency,
            "type": "chiqim",
            "affects_balance": True,
            "created_at": {"$gte": three_months_ago}
        }},
        {"$group": {
            "_id": {"month": {"$month": "$created_at"}, "year": {"$year": "$created_at"}},
            "total": {"$sum": "$amount"}
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1}}
    ]
    res_3m = await transactions_collection.aggregate(pipeline_3m).to_list(length=10)
    
    # Joriy oy kategoriyalari
    pipeline_cat = [
        {"$match": {
            "telegram_id": telegram_id,
            "currency": currency,
            "type": "chiqim",
            "affects_balance": True,
            "created_at": {"$gte": first_day_this_month}
        }},
        {"$group": {
            "_id": "$category",
            "total": {"$sum": "$amount"}
        }},
        {"$sort": {"total": -1}}
    ]
    res_cat = await transactions_collection.aggregate(pipeline_cat).to_list(length=20)
    
    # Joriy limit
    user = await get_user(telegram_id)
    balances = user.get("balances", {})
    current_limit = balances.get(currency, {}).get("limit", 0)
    
    # Qarzlar
    debts = await debts_collection.find({
        "telegram_id": telegram_id,
        "status": {"$in": ["active", "partial"]}
    }).to_list(length=20)
    
    active_debts_count = len(debts)
    total_debt = sum([d.get("amount", 0) - d.get("paid_amount", 0) for d in debts])
    nearest_debt = None
    if debts:
        # Eng yaqin muddatni topish
        valid_debts = [d for d in debts if d.get("due_date") and d.get("due_date") != "nomalum"]
        if valid_debts:
            valid_debts.sort(key=lambda x: x["due_date"])
            nearest_debt = valid_debts[0]
            
    return {
        "monthly_totals": res_3m,
        "current_month_categories": res_cat,
        "limit": current_limit,
        "active_debts_count": active_debts_count,
        "total_debt_amount": total_debt,
        "nearest_debt": nearest_debt
    }

async def update_last_advice_date(telegram_id: int):
    """Oxirgi marta qachon maslahat berilganini yangilaydi."""
    from datetime import datetime
    await users_collection.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"last_advice_date": datetime.utcnow()}}
    )

async def can_send_advice_today(telegram_id: int) -> bool:
    """Bugun maslahat berilgan bo'lsa False qaytaradi."""
    from datetime import datetime
    user = await get_user(telegram_id)
    if not user: return True
    
    last_date = user.get("last_advice_date")
    if not last_date: return True
    
    # Bugun ekanligini tekshirish
    return last_date.date() != datetime.utcnow().date()

async def get_report_context(telegram_id: int, currency: str = "UZS"):
    """
    AI hisobot yaratishi uchun kerakli to'liq ma'lumotlarni yig'adi:
    - Balanslar
    - Bugungi tranzaksiyalar
    - Bu oy xarajatlari va kategoriyalari
    - O'tgan oy xarajatlari
    - Qarzlar
    """
    from datetime import datetime, timedelta
    
    user = await get_user(telegram_id)
    if not user:
        return {}

    balances = user.get("balances", {})
    
    today = datetime.utcnow()
    start_of_today = today.replace(hour=0, minute=0, second=0, microsecond=0)
    first_day_this_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # O'tgan oyning boshi va oxiri
    last_day_last_month = first_day_this_month - timedelta(days=1)
    first_day_last_month = last_day_last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Bugungi tranzaksiyalar
    today_tx = await transactions_collection.find({
        "telegram_id": telegram_id,
        "created_at": {"$gte": start_of_today}
    }).to_list(length=50)
    
    # Joriy oy xarajatlari (kategoriya bo'yicha)
    pipeline_cat_this_month = [
        {"$match": {
            "telegram_id": telegram_id,
            "type": "chiqim",
            "affects_balance": True,
            "created_at": {"$gte": first_day_this_month}
        }},
        {"$group": {
            "_id": "$category",
            "total": {"$sum": "$amount"}
        }},
        {"$sort": {"total": -1}}
    ]
    this_month_categories = await transactions_collection.aggregate(pipeline_cat_this_month).to_list(length=20)
    this_month_total = sum([c["total"] for c in this_month_categories])
    
    # O'tgan oy jami xarajatlari
    pipeline_last_month = [
        {"$match": {
            "telegram_id": telegram_id,
            "type": "chiqim",
            "affects_balance": True,
            "created_at": {"$gte": first_day_last_month, "$lt": first_day_this_month}
        }},
        {"$group": {
            "_id": None,
            "total": {"$sum": "$amount"}
        }}
    ]
    last_month_res = await transactions_collection.aggregate(pipeline_last_month).to_list(length=1)
    last_month_total = last_month_res[0]["total"] if last_month_res else 0
    
    # Qarzlar
    debts = await debts_collection.find({
        "telegram_id": telegram_id,
        "status": {"$in": ["active", "partial"]}
    }).to_list(length=50)
    
    # Cleanup object ids for AI context
    for tx in today_tx:
        tx["_id"] = str(tx["_id"])
        tx["created_at"] = tx["created_at"].isoformat()
        
    for d in debts:
        d["_id"] = str(d["_id"])
        if "created_at" in d:
            d["created_at"] = d["created_at"].isoformat()
            
    return {
        "balances": balances,
        "today_transactions": today_tx,
        "this_month": {
            "total_spent": this_month_total,
            "categories": this_month_categories
        },
        "last_month": {
            "total_spent": last_month_total
        },
        "active_debts": debts
    }

# ═══════════════════════════════════════
# CHAT HISTORY OPERATIONS
# ═══════════════════════════════════════

async def save_chat_message(user_id: int, role: str, content: str, tx_id: str = None, debt_id: str = None):
    """
    Saves a chat message to history for context memory.
    role: "user" | "assistant"
    """
    doc = {
        "user_id": user_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow(),
        "related_transaction_id": tx_id,
        "related_debt_id": debt_id
    }
    await chat_history_collection.insert_one(doc)

async def get_chat_history(user_id: int, limit: int = 15) -> list:
    """
    Returns recent chat history formatted for AI context.
    """
    cursor = chat_history_collection.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    
    # We fetched descending, so reverse it to chronological order
    docs.reverse()
    
    formatted = []
    for doc in docs:
        msg = {
            "role": doc["role"],
            "content": doc["content"]
        }
        # Include reference IDs if available to help AI update them
        refs = []
        if doc.get("related_transaction_id"):
            refs.append(f"TX_ID: {doc['related_transaction_id']}")
        if doc.get("related_debt_id"):
            refs.append(f"DEBT_ID: {doc['related_debt_id']}")
            
        if refs and doc["role"] == "assistant":
             msg["content"] += f" [System Reference: {', '.join(refs)}]"
             
        formatted.append(msg)
        
    return formatted

# ═══════════════════════════════════════
# CHANNEL SUBSCRIPTION TRACKING
# ═══════════════════════════════════════

async def track_channel_click(user_id: int, channel_link: str, source: str = "onboarding"):
    """Foydalanuvchi kanal tugmasini bosganda vaqtini saqlash."""
    now = datetime.utcnow()
    await channel_subscriptions_collection.update_one(
        {"user_id": user_id, "channel_link": channel_link},
        {
            "$setOnInsert": {"subscribed_at": None, "confirmed": False, "left_at": None, "source": source},
            "$set": {"button_clicked_at": now}
        },
        upsert=True
    )

async def confirm_channel_subscription(user_id: int, channel_link: str):
    """Obuna tasdiqlanganda vaqtini saqlash."""
    now = datetime.utcnow()
    await channel_subscriptions_collection.update_one(
        {"user_id": user_id, "channel_link": channel_link},
        {
            "$setOnInsert": {"button_clicked_at": None, "left_at": None, "source": "unknown"},
            "$set": {"subscribed_at": now, "confirmed": True, "left_at": None}
        },
        upsert=True
    )

async def mark_channel_left(user_id: int, channel_link: str):
    """Kanaldan chiqib ketganda."""
    now = datetime.utcnow()
    await channel_subscriptions_collection.update_one(
        {"user_id": user_id, "channel_link": channel_link},
        {"$set": {"confirmed": False, "left_at": now}}
    )

async def get_admin_channel_stats(channel_link: str) -> dict:
    """Admin panel uchun kanal konversiyasi va statistikasi."""
    cursor = channel_subscriptions_collection.find({"channel_link": channel_link})
    records = await cursor.to_list(None)
    
    total_passed = len(records)
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    
    passed_today = 0
    passed_week = 0
    passed_month = 0
    
    clicked_count = 0
    subscribed_count = 0
    left_count = 0
    not_subscribed_count = 0
    
    chart_data_dict = {}
    users_list = []
    
    for r in records:
        uid = r["user_id"]
        # Konversiya
        if r.get("button_clicked_at"):
            clicked_count += 1
            
        if r.get("confirmed"):
            subscribed_count += 1
        elif r.get("left_at"):
            left_count += 1
        elif r.get("button_clicked_at") and not r.get("subscribed_at"):
            not_subscribed_count += 1
            
        # Vaqt
        dt = r.get("subscribed_at") or r.get("button_clicked_at")
        if dt:
            d = dt.date()
            if d == today: passed_today += 1
            if d >= start_of_week: passed_week += 1
            if d >= start_of_month: passed_month += 1
            
            d_str = d.strftime("%m-%d")
            chart_data_dict[d_str] = chart_data_dict.get(d_str, 0) + 1
            
        users_list.append({
            "user_id": uid,
            "date": dt.strftime("%Y-%m-%d %H:%M") if dt else "Noma'lum",
            "left_at": r.get("left_at").strftime("%Y-%m-%d %H:%M") if r.get("left_at") else None,
            "status": "Aktiv" if r.get("confirmed") else ("Chiqib ketgan" if r.get("left_at") else "Kutmoqda")
        })

    # Join user info
    for u in users_list:
        u_doc = await users_collection.find_one({"telegram_id": u["user_id"]})
        if u_doc:
            u["name"] = u_doc.get("full_name", "Noma'lum")
            u["phone"] = u_doc.get("phone_number", "Yo'q")
            u["region"] = u_doc.get("region", "Noma'lum")
            u["age_group"] = u_doc.get("age_group", "Noma'lum")
        else:
            u["name"] = "Noma'lum"
            u["phone"] = "Yo'q"
            u["region"] = "Noma'lum"
            u["age_group"] = "Noma'lum"

    chart_data = [{"date": k, "count": v} for k, v in sorted(chart_data_dict.items())]
    
    return {
        "summary": {
            "total_passed": total_passed,
            "today": passed_today,
            "week": passed_week,
            "month": passed_month
        },
        "conversion": {
            "clicked": clicked_count,
            "subscribed": subscribed_count,
            "left": left_count,
            "not_subscribed": not_subscribed_count
        },
        "chart": chart_data,
        "users": users_list
    }

# ═══════════════════════════════════════
# QR SCAN TRACKING
# ═══════════════════════════════════════

async def save_qr_scan(user_id: int, status: str, data: dict):
    """QR skan natijasini saqlash."""
    doc = {
        "user_id": user_id,
        "status": status,  # success, not_found, not_fiscal, fetch_failed
        "data": data,
        "created_at": datetime.utcnow()
    }
    await qr_scans_collection.insert_one(doc)

async def get_qr_scan_stats() -> dict:
    """Admin panel uchun QR skan statistikasi."""
    total = await qr_scans_collection.count_documents({})
    success = await qr_scans_collection.count_documents({"status": "success"})
    not_found = await qr_scans_collection.count_documents({"status": "not_found"})
    not_fiscal = await qr_scans_collection.count_documents({"status": "not_fiscal"})
    fetch_failed = await qr_scans_collection.count_documents({"status": "fetch_failed"})
    
    return {
        "total": total,
        "success": success,
        "not_found": not_found,
        "not_fiscal": not_fiscal,
        "fetch_failed": fetch_failed,
        "success_rate": round((success / total * 100), 1) if total > 0 else 0
    }


# ═══════════════════════════════════════
# ADVERTISEMENT OPERATIONS
# ═══════════════════════════════════════

async def _generate_ad_id() -> str:
    """Generate next sequential ad ID like AD001, AD002..."""
    last = await ads_collection.find_one(sort=[("seq", -1)])
    seq = (last.get("seq", 0) if last else 0) + 1
    return f"AD{seq:03d}", seq


async def create_ad(data: dict) -> dict:
    """Create a new advertisement."""
    ad_id, seq = await _generate_ad_id()
    doc = {
        "_id": ad_id,
        "seq": seq,
        "name": data.get("name", "Nomsiz reklama"),
        "content_type": data.get("content_type", "text"),  # text|photo|video|document|photo_text
        "text": data.get("text", ""),
        "media_file_id": data.get("media_file_id"),  # Telegram file_id
        "media_url": data.get("media_url"),  # temporary upload path
        "caption": data.get("caption", ""),
        "inline_buttons": data.get("inline_buttons", []),  # [[{text, url}]]
        "targets": data.get("targets", ["bot"]),  # ["bot", "@channel"]
        "segment_mode": data.get("segment_mode", "all"),  # all | segment
        "segment_filters": data.get("segment_filters", {}),
        "schedule_type": data.get("schedule_type", "now"),  # now | scheduled
        "scheduled_at": data.get("scheduled_at"),
        "duration_hours": data.get("duration_hours"),
        "status": "draft",  # draft|scheduled|sending|completed|stopped
        "stats": {"sent": 0, "failed": 0, "total": 0},
        "created_at": datetime.utcnow(),
        "created_by": data.get("created_by"),
    }
    await ads_collection.insert_one(doc)
    return doc


async def get_ads(limit: int = 50, offset: int = 0) -> list:
    """Get all ads ordered by creation date (newest first)."""
    cursor = ads_collection.find().sort("created_at", -1).skip(offset).limit(limit)
    ads = []
    async for ad in cursor:
        ad["_id"] = str(ad["_id"])
        if "created_at" in ad and hasattr(ad["created_at"], "strftime"):
            ad["created_at"] = ad["created_at"].strftime("%Y-%m-%d %H:%M")
        if "scheduled_at" in ad and ad["scheduled_at"] and hasattr(ad["scheduled_at"], "strftime"):
            ad["scheduled_at"] = ad["scheduled_at"].strftime("%Y-%m-%d %H:%M")
        ads.append(ad)
    return ads


async def get_ad(ad_id: str) -> dict:
    """Get a single ad by ID."""
    ad = await ads_collection.find_one({"_id": ad_id})
    if ad:
        ad["_id"] = str(ad["_id"])
        if "created_at" in ad and hasattr(ad["created_at"], "strftime"):
            ad["created_at"] = ad["created_at"].strftime("%Y-%m-%d %H:%M")
        if "scheduled_at" in ad and ad["scheduled_at"] and hasattr(ad["scheduled_at"], "strftime"):
            ad["scheduled_at"] = ad["scheduled_at"].strftime("%Y-%m-%d %H:%M")
    return ad


async def update_ad(ad_id: str, updates: dict) -> bool:
    """Update an ad's fields."""
    result = await ads_collection.update_one(
        {"_id": ad_id},
        {"$set": updates}
    )
    return result.modified_count > 0


async def delete_ad(ad_id: str) -> bool:
    """Delete an ad."""
    result = await ads_collection.delete_one({"_id": ad_id})
    return result.deleted_count > 0


async def get_ads_count() -> int:
    """Get total number of ads."""
    return await ads_collection.count_documents({})


async def estimate_ad_reach(targets: list, segment_mode: str, segment_filters: dict) -> dict:
    """Estimate how many users/subscribers the ad will reach."""
    result = {"bot_users": 0, "channel_subscribers": 0, "total": 0, "details": []}

    if "bot" in targets:
        query = {"is_active": True}
        if segment_mode == "segment" and segment_filters:
            if segment_filters.get("age_groups"):
                query["age_group"] = {"$in": segment_filters["age_groups"]}
            if segment_filters.get("genders"):
                query["gender"] = {"$in": segment_filters["genders"]}
            if segment_filters.get("regions"):
                query["region"] = {"$in": segment_filters["regions"]}
            if segment_filters.get("languages"):
                query["language"] = {"$in": segment_filters["languages"]}
        count = await users_collection.count_documents(query)
        result["bot_users"] = count
        result["details"].append({"target": "🤖 Bot foydalanuvchilar", "count": count})

    # Channel subscribers from channel_subscriptions_collection
    for t in targets:
        if t.startswith("@"):
            ch = await channel_subscriptions_collection.find_one({"username": t})
            count = ch.get("subscriber_count", 0) if ch else 0
            result["channel_subscribers"] += count
            result["details"].append({"target": f"📢 {t}", "count": count})

    result["total"] = result["bot_users"] + result["channel_subscribers"]
    return result
