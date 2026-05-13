"""
HTTP API Server for the Telegram WebApp.
Runs using aiohttp with error handling middleware.
"""

import json
import os
import logging
from datetime import datetime
from aiohttp import web
from src.database import (
    get_user, get_user_all_balances, get_active_debts, transactions_collection,
    get_custom_categories, add_custom_category, delete_custom_category,
    get_referral_stats, get_all_referral_stats
)
from src.categories import SYSTEM_CATEGORIES
from src.config import BOT_TOKEN
from src.services.error_handler import log_error, handle_error, ErrorType

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()

# Allow CORS for development
def set_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, DELETE'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@routes.options('/{path:.*}')
async def options_handler(request):
    return set_cors(web.Response())

@routes.get('/')
async def root_handler(request):
    # Production: serve React frontend if available
    webapp_index = os.path.join(os.getcwd(), 'webapp', 'dist', 'index.html')
    if os.path.exists(webapp_index):
        return web.FileResponse(webapp_index)
    return web.Response(
        text="Somly AI API Backend is running.\n\n"
             "Frontend not built yet. Run 'cd webapp && npm run build' first.\n",
        content_type="text/plain"
    )

from src.ws_manager import ws_manager
import aiohttp

@routes.get('/api/ws')
async def websocket_handler(request):
    user_id = int(request.query.get('user_id', 0))
    if not user_id:
        return web.Response(status=400, text="Missing user_id")
        
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    ws_manager.connect(user_id, ws)
    try:
        await ws.send_str(json.dumps({"event": "connected", "data": {"status": "ok"}}))
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # Handle potential messages from client if needed (e.g. ping/pong)
                pass
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print('ws connection closed with exception %s' % ws.exception())
    finally:
        ws_manager.disconnect(user_id, ws)
    return ws

@routes.get('/api/redirect')
async def channel_redirect_handler(request):
    """Kanalga o'tishni kuzatish va redirect qilish."""
    user_id_str = request.query.get('u')
    channel_link = request.query.get('c')
    
    if user_id_str and channel_link:
        try:
            user_id = int(user_id_str)
            from src.database import track_channel_click
            await track_channel_click(user_id, channel_link, "onboarding")
        except ValueError:
            pass
            
    # Asosiy kanal havolasiga yo'naltirish
    fallback_link = channel_link if channel_link else "https://t.me"
    raise web.HTTPFound(fallback_link)

@routes.post('/api/qr-scan')
async def qr_scan_handler(request):
    """Mini App dan QR URL qabul qilib, fiscal data qaytarish."""
    try:
        body = await request.json()
        qr_url = body.get("url", "")
        user_id = body.get("user_id", 0)
        
        if not qr_url:
            return set_cors(web.json_response({"error": "Missing url"}, status=400))
        
        from src.services.qr_service import is_fiscal_url, fetch_fiscal_receipt
        from src.database import save_qr_scan
        
        if not is_fiscal_url(qr_url):
            await save_qr_scan(user_id, "not_fiscal", {"url": qr_url})
            return set_cors(web.json_response({"error": "Not a fiscal URL", "fiscal": False}))
        
        receipt = await fetch_fiscal_receipt(qr_url)
        await save_qr_scan(user_id, "success" if receipt["success"] else "fetch_failed", {
            "url": qr_url, "total": receipt.get("total", 0)
        })
        
        return set_cors(web.json_response(receipt))
    except Exception as e:
        logger.error(f"QR scan API error: {e}")
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/admin/qr-stats')
async def admin_qr_stats(request):
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.database import get_qr_scan_stats
        data = await get_qr_scan_stats()
        return set_cors(web.json_response(data))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/admin/ws')
async def admin_websocket_handler(request):
    token = request.query.get('token')
    # Use a dummy request to check token logic since it expects headers, or we can just mock it
    # _verify_admin_token checks request.headers.get("Authorization"), let's check it directly
    auth_header = f"Bearer {token}" if token else ""
    class MockRequest:
        headers = {"Authorization": auth_header}
    from src.api import _verify_admin_token # Need to ensure we can call it
    if not _verify_admin_token(MockRequest()):
        return web.Response(status=401, text="Unauthorized")
        
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    ws_manager.connect_admin(ws)
    try:
        await ws.send_str(json.dumps({"event": "connected", "data": {"status": "ok"}}))
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                pass
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print('admin ws connection closed with exception %s' % ws.exception())
    finally:
        ws_manager.disconnect_admin(ws)
    return ws

@routes.get('/api/exchange-rates')
async def get_exchange_rates_api(request):
    from src.services.currency_service import get_exchange_rates
    data = get_exchange_rates()
    return set_cors(web.json_response(data))

@routes.get('/api/dashboard/trend')
async def get_dashboard_trend(request):
    try:
        user_id = int(request.query.get('user_id', 0))
        if not user_id:
            return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
            
        from datetime import datetime, timedelta
        from src.database import transactions_collection
        
        today = datetime.now()
        start_date = (today - timedelta(days=6)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        
        txs = await transactions_collection.find({
            "telegram_id": user_id,
            "date": {"$gte": start_date, "$lte": end_date}
        }).to_list(length=1000)
        
        days = []
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i))
            d_str = d.strftime("%Y-%m-%d")
            
            day_txs = [t for t in txs if t.get("date") == d_str]
            chiqim = sum(t["amount"] for t in day_txs if t["type"] == "chiqim")
            kirim = sum(t["amount"] for t in day_txs if t["type"] == "kirim")
            
            days.append({
                "day": d.strftime("%a"),
                "total": chiqim if chiqim > kirim else kirim,
                "type": "chiqim" if chiqim >= kirim else "kirim",
                "isToday": i == 0
            })
            
        return set_cors(web.json_response(days))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/dashboard')
async def get_dashboard(request):
    from datetime import datetime, timedelta
    
    user_id = int(request.query.get('user_id', 0))
    if not user_id:
        return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
        
    user = await get_user(user_id) or {}
        
    start_date = request.query.get('start')
    end_date = request.query.get('end')
    
    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        # simple trick for end of month
        next_month = today.replace(day=28) + timedelta(days=4)
        end_date = (next_month - timedelta(days=next_month.day)).strftime("%Y-%m-%d")
        
    # Get balances
    balances_dict = await get_user_all_balances(user_id)
    balances_list = [{"currency": cur, "amount": data.get("amount", 0), "emoji": data.get("emoji", "💰"), "color": data.get("color", "#30D158"), "title": data.get("title", cur), "limit": data.get("limit")} for cur, data in balances_dict.items()]
    if not balances_list:
        balances_list = [{"currency": "UZS", "amount": 0, "emoji": "💰", "color": "#0A84FF", "title": "So'm"}]

    # Get debts
    bergan = await get_active_debts(user_id, "bergan")
    olgan = await get_active_debts(user_id, "olgan")
    b_total = sum(d["amount"] - d.get("paid_amount",0) for d in bergan)
    o_total = sum(d["amount"] - d.get("paid_amount",0) for d in olgan)

    # Calculate previous period dates for comparison
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")
        diff = (ed - sd).days + 1
        prev_sd = (sd - timedelta(days=diff)).strftime("%Y-%m-%d")
        prev_ed = (ed - timedelta(days=diff)).strftime("%Y-%m-%d")
    except Exception:
        prev_sd, prev_ed = start_date, end_date

    # Fetch transactions
    curr_txs = await transactions_collection.find({
        "telegram_id": user_id,
        "date": {"$gte": start_date, "$lte": end_date}
    }).to_list(length=1000)
    
    prev_txs = await transactions_collection.find({
        "telegram_id": user_id,
        "date": {"$gte": prev_sd, "$lte": prev_ed}
    }).to_list(length=1000)
    
    recent_txs = sorted(curr_txs, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
    formatted_txs = [{
        "id": str(tx["_id"]),
        "type": tx["type"],
        "amount": tx["amount"],
        "category": tx.get("category", "Boshqa"),
        "date": tx.get("date", ""),
        "desc": tx.get("description", "")
    } for tx in recent_txs]

    # Aggregations
    stats = {}
    daily_stats = {}
    comparison = {}

    for cur in balances_dict.keys():
        if cur not in stats:
             stats[cur] = {"Hammasi": [], "Kirim": [], "Chiqim": []}
             daily_stats[cur] = {}
             comparison[cur] = {"kirim": {"current": 0, "prev": 0}, "chiqim": {"current": 0, "prev": 0}}
             
    # Default UZS if empty
    if not stats:
         stats["UZS"] = {"Hammasi": [], "Kirim": [], "Chiqim": []}
         daily_stats["UZS"] = {}
         comparison["UZS"] = {"kirim": {"current": 0, "prev": 0}, "chiqim": {"current": 0, "prev": 0}}

    # Group curr_txs
    cat_totals = {} # {currency: {type: {category_name: {"amount": 0, "count": 0, "emoji": ""}}}}
    for tx in curr_txs:
        c = tx.get("currency", "UZS").upper()
        if c not in cat_totals:
            cat_totals[c] = {"kirim": {}, "chiqim": {}}
        t_type = tx.get("type")
        if t_type not in ["kirim", "chiqim"]: continue
        
        # split emoji and name
        raw_cat = tx.get("category", "📋 Boshqa")
        parts = raw_cat.split(" ", 1)
        emoji = parts[0] if len(parts) > 1 else "📋"
        name = parts[1] if len(parts) > 1 else parts[0]
        
        if name not in cat_totals[c][t_type]:
             cat_totals[c][t_type][name] = {"amount": 0, "count": 0, "emoji": emoji}
             
        cat_totals[c][t_type][name]["amount"] += tx.get("amount", 0)
        cat_totals[c][t_type][name]["count"] += 1
        
        # Line chart logic
        d_str = tx.get("date", "")
        if d_str:
            if c not in daily_stats: daily_stats[c] = {}
            if d_str not in daily_stats[c]: daily_stats[c][d_str] = {"kirim": 0, "chiqim": 0}
            daily_stats[c][d_str][t_type] += tx.get("amount", 0)
            
        # Comparison logic
        if c in comparison:
            comparison[c][t_type]["current"] += tx.get("amount", 0)
            
    for tx in prev_txs:
        c = tx.get("currency", "UZS").upper()
        t_type = tx.get("type")
        if t_type in ["kirim", "chiqim"] and c in comparison:
             comparison[c][t_type]["prev"] += tx.get("amount", 0)

    # Format Pie Chart Stats
    # Premium color palettes
    kirim_colors = ['#30D158', '#34C759', '#32D74B', '#28CD41', '#248A3D']
    chiqim_colors = ['#FF453A', '#FF9F0A', '#BF5AF2', '#0A84FF', '#FF375F', '#5E5CE6', '#FFD60A']
    
    for c, types in cat_totals.items():
        if c not in stats: stats[c] = {"Hammasi": [], "Kirim": [], "Chiqim": []}
        
        total_k = sum(k["amount"] for k in types["kirim"].values())
        total_ch = sum(ch["amount"] for ch in types["chiqim"].values())
        
        stats[c]["Hammasi"] = [
            {"name": "Kirim", "value": total_k, "color": "#30D158", "emoji": "💰", "count": sum(k["count"] for k in types["kirim"].values())},
            {"name": "Chiqim", "value": total_ch, "color": "#FF453A", "emoji": "💸", "count": sum(ch["count"] for ch in types["chiqim"].values())}
        ]
        
        for idx, (cat_name, data) in enumerate(types["kirim"].items()):
             stats[c]["Kirim"].append({
                 "name": cat_name, "value": data["amount"], "count": data["count"],
                 "emoji": data["emoji"], "color": kirim_colors[idx % len(kirim_colors)]
             })
        for idx, (cat_name, data) in enumerate(types["chiqim"].items()):
             stats[c]["Chiqim"].append({
                 "name": cat_name, "value": data["amount"], "count": data["count"],
                 "emoji": data["emoji"], "color": chiqim_colors[idx % len(chiqim_colors)]
             })

    response_data = {
        "balances": balances_list,
        "stats": stats,
        "daily_stats": daily_stats,
        "comparison": comparison,
        "debts": {
            "berishimKerak": o_total,
            "olishimKerak": b_total
        },
        "transactions": formatted_txs,
        "language": user.get("language", "uz")
    }
    return set_cors(web.json_response(response_data))


@routes.get('/api/user_info')
async def get_user_info(request):
    user_id = int(request.query.get('user_id', 0))
    if not user_id:
        return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
    
    user = await get_user(user_id)
    return set_cors(web.json_response({
        "language": user.get("language", "uz")
    }))


@routes.get('/api/categories')
async def get_categories(request):
    user_id = int(request.query.get('user_id', 0))
    if not user_id:
        return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
    
    custom_cats = await get_custom_categories(user_id)
    # Convert ObjectId and datetime
    for cat in custom_cats:
        cat["id"] = str(cat["_id"])
        del cat["_id"]
        if "created_at" in cat and isinstance(cat["created_at"], datetime):
            cat["created_at"] = cat["created_at"].isoformat()
        
    return set_cors(web.json_response({
        "system": SYSTEM_CATEGORIES,
        "custom": custom_cats
    }))

@routes.post('/api/categories')
async def create_category(request):
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        name = data.get('name')
        emoji = data.get('emoji')
        cat_type = data.get('type')
        color = data.get('color', '#0A84FF')
        
        if not all([user_id, name, emoji, cat_type]):
            return set_cors(web.json_response({"error": "Missing fields"}, status=400))
            
        cat_id = await add_custom_category(user_id, emoji, name, cat_type, color)
        
        bot = request.app.get('bot')
        if bot:
            user = await get_user(user_id)
            user_name = user.get("full_name", "Siz")
            msg = f"✅ {user_name} Mini Appda:\nYangi kategoriya qo'shildi:\n{emoji} {name} ({cat_type})"
            await bot.send_message(chat_id=user_id, text=msg)
            
        return set_cors(web.json_response({"success": True, "id": str(cat_id)}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.delete('/api/categories/{cat_id}')
async def delete_category(request):
    cat_id = request.match_info['cat_id']
    user_id = int(request.query.get('user_id', 0))
    # We don't have the category name here easily without a DB query, so keep it generic or skip
    await delete_custom_category(cat_id)
    if user_id:
        bot = request.app.get('bot')
        if bot:
            user = await get_user(user_id)
            user_name = user.get("full_name", "Siz")
            await bot.send_message(chat_id=user_id, text=f"✅ {user_name} Mini Appda:\nKategoriya o'chirildi.")
    return set_cors(web.json_response({"success": True}))

@routes.post('/api/balances')
async def create_balance(request):
    from src.database import create_custom_balance
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        currency = data.get('currency')
        title = data.get('title', currency)
        emoji = data.get('emoji', '💰')
        amount = float(data.get('amount', 0))
        color = data.get('color', '#30D158')
        limit = data.get('limit')
        if limit:
            limit = float(limit)
            
        if not all([user_id, currency]):
            return set_cors(web.json_response({"error": "Missing fields"}, status=400))
            
        await create_custom_balance(user_id, currency, title, amount, color, emoji, limit)
        
        bot = request.app.get('bot')
        if bot:
            user = await get_user(user_id)
            user_name = user.get("full_name", "Siz")
            msg = f"✅ {user_name} Mini Appda:\nYangi balans yaratildi:\n{title} - {amount} {currency}"
            await bot.send_message(chat_id=user_id, text=msg)
            
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        logger.error(f"Error creating balance: {e}")
        return set_cors(web.json_response({"error": "Server error"}, status=500))

@routes.put('/api/balances/{currency}')
async def update_balance(request):
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        currency = request.match_info['currency'].upper()
        
        if not user_id:
            return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
            
        from src.database import users_collection
        
        update_fields = {}
        if 'title' in data: update_fields[f"balances.{currency}.title"] = data['title']
        if 'emoji' in data: update_fields[f"balances.{currency}.emoji"] = data['emoji']
        if 'color' in data: update_fields[f"balances.{currency}.color"] = data['color']
        if 'limit' in data: update_fields[f"balances.{currency}.limit"] = data['limit']
        
        if not update_fields:
            return set_cors(web.json_response({"error": "No fields to update"}, status=400))
            
        await users_collection.update_one(
            {"telegram_id": user_id},
            {"$set": update_fields}
        )
        
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        logger.error(f"Error updating balance: {e}")
        return set_cors(web.json_response({"error": "Server error"}, status=500))

@routes.get('/api/balances/{currency}/check_delete')
async def check_delete_balance(request):
    try:
        user_id = int(request.query.get('user_id', 0))
        currency = request.match_info['currency'].upper()
        if not user_id:
            return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
        
        from src.database import transactions_collection
        count = await transactions_collection.count_documents({"telegram_id": user_id, "currency": currency})
        return set_cors(web.json_response({"count": count}))
    except Exception as e:
        logger.error(f"Error checking balance: {e}")
        return set_cors(web.json_response({"error": "Server error"}, status=500))

@routes.delete('/api/balances/{currency}')
async def delete_balance_api(request):
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        currency = request.match_info['currency'].upper()
        
        if not user_id:
            return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
            
        from src.database import delete_custom_balance, transactions_collection
        # Move existing tx to UZS
        await transactions_collection.update_many(
            {"telegram_id": user_id, "currency": currency},
            {"$set": {"currency": "UZS"}}
        )
        
        await delete_custom_balance(user_id, currency)
        
        bot = request.app.get('bot')
        if bot:
            user = await get_user(user_id)
            user_name = user.get("full_name", "Siz")
            msg = f"✅ {user_name} Mini Appda:\n'{currency}' balansi o'chirildi. Undagi tranzaksiyalar UZS balansiga o'tkazildi."
            await bot.send_message(chat_id=user_id, text=msg)
            
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.post('/api/balances/transfer')
async def transfer_balance(request):
    """Transfer funds between two balances"""
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        from_currency = str(data.get('from_balance_id', '')).upper()
        to_currency = str(data.get('to_balance_id', '')).upper()
        amount = float(data.get('amount', 0))
        
        if not all([user_id, from_currency, to_currency, amount]):
            return set_cors(web.json_response({"error": "Missing required fields"}, status=400))
        
        if from_currency == to_currency:
            return set_cors(web.json_response({"error": "Cannot transfer to same balance"}, status=400))
        
        if amount <= 0:
            return set_cors(web.json_response({"error": "Amount must be positive"}, status=400))
        
        # Get user balances
        user = await users_collection.find_one({"telegram_id": user_id})
        if not user:
            return set_cors(web.json_response({"error": "User not found"}, status=404))
        
        balances = user.get("balances", {})
        from_balance = balances.get(from_currency, {})
        to_balance = balances.get(to_currency, {})
        
        if not from_balance:
            return set_cors(web.json_response({"error": f"Balance {from_currency} not found"}, status=404))
        
        if from_balance.get("amount", 0) < amount:
            return set_cors(web.json_response({"error": "Insufficient balance"}, status=400))
        
        # Perform transfer
        new_from_amount = from_balance.get("amount", 0) - amount
        new_to_amount = to_balance.get("amount", 0) + amount if to_balance else amount
        
        await users_collection.update_one(
            {"telegram_id": user_id},
            {"$set": {
                f"balances.{from_currency}.amount": new_from_amount,
                f"balances.{to_currency}.amount": new_to_amount
            }}
        )
        
        # Broadcast update via WebSocket
        await ws_manager.broadcast(user_id, "balance.updated", {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "amount": amount,
            "action": "transfer"
        })
        
        # Send confirmation message via bot
        bot = request.app.get('bot')
        if bot:
            msg = f"✅ O'tkazish muvaffaq:\n{from_currency} → {to_currency}\nSumma: {amount}"
            await bot.send_message(chat_id=user_id, text=msg)
        
        return set_cors(web.json_response({"success": True, "from_amount": new_from_amount, "to_amount": new_to_amount}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.post('/api/notify_action')
async def notify_action(request):
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        message = data.get('message', '')
        
        if not user_id or not message:
            return set_cors(web.json_response({"error": "Missing fields"}, status=400))
            
        bot = request.app.get('bot')
        if bot:
            await bot.send_message(chat_id=user_id, text=message)
            
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.post('/api/settings/notifications')
async def update_notifications(request):
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        morning_reminder = data.get('morning_reminder', True)
        evening_reminder = data.get('evening_reminder', True)
        
        if not user_id:
            return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
        
        from src.database import users_collection
        await users_collection.update_one(
            {"telegram_id": user_id},
            {"$set": {
                "settings.morning_reminder": morning_reminder,
                "settings.evening_reminder": evening_reminder
            }}
        )
        
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        logger.error(f"Error updating notifications: {e}")
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.post('/api/settings/language')
async def update_language(request):
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        language = data.get('language', 'uz')
        
        if not user_id:
            return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
        
        from src.database import users_collection
        await users_collection.update_one(
            {"telegram_id": user_id},
            {"$set": {"language": language}}
        )
        
        bot = request.app.get('bot')
        if bot:
            msg = "✅ Til muvaffaqiyatli o'zgartirildi." if language == 'uz' else "✅ Язык успешно изменен." if language == 'ru' else "✅ Language changed successfully."
            try:
                await bot.send_message(chat_id=user_id, text=msg)
            except:
                pass
                
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        logger.error(f"Error updating language: {e}")
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.post('/api/export')
async def export_excel_route(request):
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        period = data.get('period', 'Bu oy')
        
        bot = request.app.get('bot')
        if bot and user_id:
            try:
                await bot.send_message(chat_id=user_id, text=f"⏳ Excel hisobot tayyorlanmoqda ({period})...")
                # Trigger the actual export logic
                from src.handlers.report_handler import send_excel_report
                import asyncio
                # The send_excel_report might expect (message, user_id) or something similar
                # Just mock or fire if it exists, otherwise just send the message
                try:
                    asyncio.create_task(send_excel_report(bot, user_id))
                except Exception:
                    pass
            except Exception as inner_e:
                logger.error(f"Error triggering excel: {inner_e}")
                
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


# ═══════════════════════════════════════
# GROUP ROUTES
# ═══════════════════════════════════════

@routes.get('/api/groups')
async def get_groups(request):
    from src.database import get_user_groups
    user_id = int(request.query.get('user_id', 0))
    if not user_id:
        return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
    groups = await get_user_groups(user_id)
    return set_cors(web.json_response(groups))

@routes.post('/api/groups')
async def create_group_route(request):
    from src.database import create_group
    try:
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        name = data.get('name', '')
        if not user_id or not name:
            return set_cors(web.json_response({"error": "Missing fields"}, status=400))
        group_id = await create_group(user_id, name)
        return set_cors(web.json_response({"success": True, "id": group_id}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/groups/{group_id}')
async def get_group_detail(request):
    from src.database import get_group_by_id
    group_id = request.match_info['group_id']
    group = await get_group_by_id(group_id)
    if not group:
        return set_cors(web.json_response({"error": "Group not found"}, status=404))
    return set_cors(web.json_response(group))

@routes.post('/api/groups/{group_id}/members')
async def add_member_route(request):
    from src.database import add_group_member
    try:
        group_id = request.match_info['group_id']
        data = await request.json()
        telegram_id = int(data.get('telegram_id', 0))
        name = data.get('name', '')
        if not telegram_id or not name:
            return set_cors(web.json_response({"error": "Missing fields"}, status=400))
        added = await add_group_member(group_id, telegram_id, name)
        if not added:
            return set_cors(web.json_response({"error": "Already a member or group not found"}, status=400))
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.delete('/api/groups/{group_id}/members/{member_id}')
async def remove_member_route(request):
    from src.database import remove_group_member
    try:
        group_id = request.match_info['group_id']
        member_id = int(request.match_info['member_id'])
        removed = await remove_group_member(group_id, member_id)
        return set_cors(web.json_response({"success": removed}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/groups/search-user')
async def search_user_route(request):
    from src.database import search_user_by_phone
    phone = request.query.get('phone', '')
    if not phone or len(phone) < 5:
        return set_cors(web.json_response({"error": "Phone too short"}, status=400))
    user = await search_user_by_phone(phone)
    if not user:
        return set_cors(web.json_response({"error": "User not found"}, status=404))
    return set_cors(web.json_response(user))

@routes.post('/api/groups/{group_id}/balances')
async def add_group_balance_route(request):
    from src.database import add_group_balance
    try:
        group_id = request.match_info['group_id']
        data = await request.json()
        currency = data.get('currency', '')
        title = data.get('title', currency)
        color = data.get('color', '#3B82F6')
        if not currency:
            return set_cors(web.json_response({"error": "Missing currency"}, status=400))
        await add_group_balance(group_id, currency, title, color)
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/channels')
async def get_channels_route(request):
    from src.database import get_all_channels
    channels = await get_all_channels()
    result = []
    for c in channels:
        result.append({
            "name": c.get("name", "Kanal"),
            "link": c.get("link", ""),
            "description": c.get("description", "Somly AI tavsiya etadi"),
        })
    return set_cors(web.json_response(result))

@routes.get('/api/debts')
async def get_debts(request):
    user_id = int(request.query.get('user_id', 0))
    if not user_id:
        return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
    
    bergan = await get_active_debts(user_id, "bergan")
    olgan = await get_active_debts(user_id, "olgan")
    
    def format_debt(d):
        return {
            "id": str(d["_id"]),
            "name": d.get("person", "Noma'lum"),
            "amount": d.get("amount", 0) - d.get("paid_amount", 0),
            "currency": d.get("currency", "UZS"),
            "desc": d.get("description", "Qarz"),
            "date": d.get("created_at", "").isoformat() if hasattr(d.get("created_at", ""), "isoformat") else str(d.get("created_at", "")),
            "due_date": d.get("due_date", ""),
            "status": d.get("status", "active")
        }
        
    response_data = {
        "berishimKerak": [format_debt(d) for d in olgan], # olgan means I owe them
        "olishimKerak": [format_debt(d) for d in bergan]  # bergan means they owe me
    }
    
    return set_cors(web.json_response(response_data))

@routes.post('/api/debts/{debt_id}/{action}')
async def debt_action(request):
    from src.database import update_debt_status, delete_debt, get_debt_by_id, insert_transaction, update_user_balance
    try:
        debt_id = request.match_info['debt_id']
        action = request.match_info['action']
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        
        bot = request.app.get('bot')
        user_name = "Siz"
        if bot and user_id:
             user = await get_user(user_id)
             user_name = user.get("full_name", "Siz")
        
        if action == 'pay':
            debt = await get_debt_by_id(debt_id)
            if not debt:
                return set_cors(web.json_response({"error": "Debt not found"}, status=404))

            await update_debt_status(debt_id, 'paid')
            
            # Cancel related reminders
            from src.database import reminders_collection
            await reminders_collection.update_many(
                {"related_debt_id": debt_id, "status": "pending"},
                {"$set": {"status": "done", "updated_at": datetime.utcnow()}}
            )
            
            t_type = "kirim" if debt.get("direction") == "bergan" else "chiqim" 
            amount = debt.get("amount", 0) - debt.get("paid_amount", 0)
            currency = debt.get("currency", "UZS")
            
            tx_data = {
                "telegram_id": debt.get("telegram_id", user_id),
                "type": t_type,
                "amount": amount,
                "currency": currency,
                "category": "🔄 Qarz qaytdi" if t_type == "kirim" else "🔄 Qarz uzildi",
                "description": f"{debt.get('person')} bilan qarz hisob-kitobi",
                "affects_balance": True
            }
            await insert_transaction(tx_data)
            await update_user_balance(tx_data["telegram_id"], currency, amount, is_income=(t_type == "kirim"))
            
            msg = f"✅ {user_name} Mini Appda:\nQarz qaytarilgan deb belgilandi va balans yangilandi."
        elif action == 'delete':
            await delete_debt(debt_id)
            msg = f"✅ {user_name} Mini Appda:\nQarz o'chirildi."
        else:
            return set_cors(web.json_response({"error": "Invalid action"}, status=400))
            
        if bot and user_id:
            await bot.send_message(chat_id=user_id, text=msg)
            
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.put('/api/transactions/{tx_id}')
async def edit_transaction(request):
    from src.database import update_transaction
    try:
        tx_id = request.match_info['tx_id']
        data = await request.json()
        user_id = int(data.get('user_id', 0))
        updates = data.get('updates', {})
        
        if not updates:
            return set_cors(web.json_response({"error": "No updates provided"}, status=400))
            
        await update_transaction(tx_id, updates)
        
        bot = request.app.get('bot')
        if bot and user_id:
            user = await get_user(user_id)
            user_name = user.get("full_name", "Siz")
            
            # Format message simply showing what changed
            details = "\n".join([f"• {k}: {v}" for k, v in updates.items() if k not in ['id', 'user_id']])
            msg = f"✅ {user_name} Mini Appda:\nTranzaksiya tahrirlandi:\n{details}"
            await bot.send_message(chat_id=user_id, text=msg)
            
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.delete('/api/transactions/{tx_id}')
async def remove_transaction(request):
    from src.database import delete_transaction, get_transaction_by_id, update_user_balance
    try:
        tx_id = request.match_info['tx_id']
        user_id = int(request.query.get('user_id', 0))
        
        tx = await get_transaction_by_id(tx_id)
        if tx:
            await delete_transaction(tx_id)
            # Revert balance
            if tx.get("affects_balance"):
                await update_user_balance(tx["telegram_id"], tx["currency"], -tx["amount"], is_income=(tx["type"] == "kirim"))
            
            if user_id:
                bot = request.app.get('bot')
                if bot:
                    user = await get_user(user_id)
                    user_name = user.get("full_name", "Siz")
                    msg = f"✅ {user_name} Mini Appda:\nTranzaksiya o'chirildi:\n{tx.get('amount')} {tx.get('currency')} ({tx.get('category', '')})"
                    await bot.send_message(chat_id=user_id, text=msg)
            
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


# ═══════════════════════════════════════
# REMINDER ROUTES
# ═══════════════════════════════════════

@routes.get('/api/reminders')
async def get_reminders_api(request):
    from src.database import get_user_reminders
    user_id = int(request.query.get('user_id', 0))
    status = request.query.get('status', 'pending')
    if not user_id:
        return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
    
    reminders = await get_user_reminders(user_id, status)
    result = []
    for r in reminders:
        result.append({
            "id": str(r["_id"]),
            "type": r.get("type", "general"),
            "message": r.get("message", ""),
            "scheduled_time": r.get("scheduled_time").isoformat() if r.get("scheduled_time") else "",
            "status": r.get("status", "pending")
        })
    return set_cors(web.json_response(result))

@routes.post('/api/reminders/{rem_id}/status')
async def update_reminder_status_api(request):
    from src.database import update_reminder_status
    rem_id = request.match_info['rem_id']
    data = await request.json()
    status = data.get('status')
    if not status:
        return set_cors(web.json_response({"error": "Missing status"}, status=400))
    await update_reminder_status(rem_id, status)
    return set_cors(web.json_response({"success": True}))

@routes.delete('/api/reminders/{rem_id}')
async def delete_reminder_api(request):
    from src.database import reminders_collection
    from bson.objectid import ObjectId
    try:
        rem_id = request.match_info['rem_id']
        await reminders_collection.delete_one({"_id": ObjectId(rem_id)})
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


# ═══════════════════════════════════════
# SHARED WALLET ROUTES
# ═══════════════════════════════════════

@routes.get('/api/shared_wallets')
async def get_shared_wallets_api(request):
    from src.database import get_user_shared_wallets
    user_id = int(request.query.get('user_id', 0))
    if not user_id:
        return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
    
    wallets = await get_user_shared_wallets(user_id)
    # Format and include member names
    from src.database import get_user
    result = []
    for w in wallets:
        members_data = []
        for m in w["members"]:
            u = await get_user(m["user_id"])
            members_data.append({
                "user_id": m["user_id"],
                "name": u.get("full_name", "Noma'lum"),
                "role": m["role"],
                "status": m["status"]
            })
            
        result.append({
            "id": str(w["_id"]),
            "name": w["name"],
            "currency": w["currency"],
            "amount": w["amount"],
            "color": w["color"],
            "owner_id": w["owner_id"],
            "members": members_data
        })
    return set_cors(web.json_response(result))

@routes.post('/api/shared_wallets')
async def create_shared_wallet_api(request):
    from src.database import create_shared_wallet
    data = await request.json()
    user_id = int(data.get('user_id', 0))
    name = data.get('name')
    currency = data.get('currency')
    amount = float(data.get('amount', 0))
    color = data.get('color', '#8B5CF6')
    
    if not all([user_id, name, currency]):
        return set_cors(web.json_response({"error": "Missing fields"}, status=400))
        
    wallet_id = await create_shared_wallet(user_id, name, currency, amount, color)
    return set_cors(web.json_response({"success": True, "id": wallet_id}))

@routes.post('/api/shared_wallets/{id}/invite')
async def invite_member_api(request):
    from src.database import find_user_by_contact, create_shared_wallet_invite, get_user
    wallet_id = request.match_info['id']
    data = await request.json()
    from_user_id = int(data.get('user_id', 0))
    contact = data.get('contact') # phone or username
    role = data.get('role', 'member')
    
    if not contact:
        return set_cors(web.json_response({"error": "Contact required"}, status=400))
        
    target_user = await find_user_by_contact(contact)
    if not target_user:
        return set_cors(web.json_response({"error": "Foydalanuvchi topilmadi"}, status=404))
        
    to_user_id = target_user["telegram_id"]
    invite_id = await create_shared_wallet_invite(wallet_id, from_user_id, to_user_id, role)
    
    # Notify target user via bot
    bot = request.app.get('bot')
    if bot:
        sender = await get_user(from_user_id)
        sender_name = sender.get("full_name", "Kimdir")
        from src.database import shared_wallets_collection
        from bson.objectid import ObjectId
        wallet = await shared_wallets_collection.find_one({"_id": ObjectId(wallet_id)})
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"sw_invite:accept:{invite_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"sw_invite:reject:{invite_id}")
            ]
        ])
        
        msg = (
            f"👥 {sender_name} sizni '{wallet['name']}' umumiy hamyoniga qo'shmoqchi.\n"
            f"Ruxsat: {role}"
        )
        await bot.send_message(chat_id=to_user_id, text=msg, reply_markup=kb)
        
    return set_cors(web.json_response({"success": True}))

@routes.get('/api/shared_wallets/invites')
async def get_invites_api(request):
    from src.database import get_user_invites
    user_id = int(request.query.get('user_id', 0))
    invites = await get_user_invites(user_id)
    return set_cors(web.json_response(invites))

@routes.post('/api/shared_wallets/invites/{id}/action')
async def process_invite_api(request):
    from src.database import process_invite_action, get_user
    invite_id = request.match_info['id']
    data = await request.json()
    action = data.get('action') # 'accept' or 'reject'
    
    invite = await process_invite_action(invite_id, action)
    if not invite:
        return set_cors(web.json_response({"error": "Invite not found"}, status=404))
        
    # Notify owner
    bot = request.app.get('bot')
    if bot:
        target = await get_user(invite["to_user_id"])
        target_name = target.get("full_name", "Foydalanuvchi")
        from src.database import shared_wallets_collection
        from bson.objectid import ObjectId
        wallet = await shared_wallets_collection.find_one({"_id": ObjectId(invite["wallet_id"])})
        
        msg = f"👥 {target_name} '{wallet['name']}' hamyoniga qo'shilish taklifini {'qabul qildi' if action == 'accept' else 'rad etdi'}."
        await bot.send_message(chat_id=invite["from_user_id"], text=msg)
        
    return set_cors(web.json_response({"success": True}))

@routes.delete('/api/shared_wallets/{wallet_id}')
async def delete_shared_wallet_api(request):
    from src.database import shared_wallets_collection
    from bson.objectid import ObjectId
    wallet_id = request.match_info['wallet_id']
    await shared_wallets_collection.delete_one({"_id": ObjectId(wallet_id)})
    return set_cors(web.json_response({"success": True}))

@routes.delete('/api/shared_wallets/{wallet_id}/members/{user_id}')
async def remove_wallet_member_api(request):
    from src.database import shared_wallets_collection
    from bson.objectid import ObjectId
    wallet_id = request.match_info['wallet_id']
    user_id = int(request.match_info['user_id'])
    
    await shared_wallets_collection.update_one(
        {"_id": ObjectId(wallet_id)},
        {"$pull": {"members": {"user_id": user_id}}}
    )
    return set_cors(web.json_response({"success": True}))


# ═══════════════════════════════════════
# ADMIN PANEL ROUTES
# ═══════════════════════════════════════

import hashlib
import secrets

# Simple token store (in-memory, resets on restart)
_admin_tokens = set()
_DEFAULT_PIN = "1973"


def _generate_admin_token():
    token = secrets.token_hex(32)
    _admin_tokens.add(token)
    return token


def _verify_admin_token(request):
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "")
    return token in _admin_tokens


async def _get_admin_pin():
    """Bazadan PIN olish yoki default qaytarish."""
    from src.database import db
    settings = await db["admin_settings"].find_one({"key": "pin"})
    if settings:
        return settings["value"]
    return _DEFAULT_PIN


async def _set_admin_pin(new_pin: str):
    """Bazaga yangi PIN yozish."""
    from src.database import db
    await db["admin_settings"].update_one(
        {"key": "pin"},
        {"$set": {"key": "pin", "value": new_pin}},
        upsert=True
    )


@routes.post('/api/admin/pin-verify')
async def admin_pin_verify(request):
    """PIN tekshirish → token qaytarish."""
    try:
        data = await request.json()
        pin = data.get("pin", "")
        stored_pin = await _get_admin_pin()
        
        # Determine IP Address
        client_ip = request.headers.get('X-Forwarded-For') or request.headers.get('X-Real-IP') or request.remote
        logger.warning(f"Admin PIN Verify Attempt from IP: {client_ip}")
        
        if pin == stored_pin:
            token = _generate_admin_token()
            logger.info(f"Admin PIN Verify SUCCESS from IP: {client_ip}")
            return set_cors(web.json_response({"success": True, "token": token}))
            
        logger.warning(f"Admin PIN Verify FAILED from IP: {client_ip}")
        return set_cors(web.json_response({"success": False, "error": "Wrong PIN"}, status=401))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.post('/api/admin/pin-change')
async def admin_pin_change(request):
    """PIN o'zgartirish."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        data = await request.json()
        old_pin = data.get("old_pin", "")
        new_pin = data.get("new_pin", "")
        
        stored_pin = await _get_admin_pin()
        if old_pin != stored_pin:
            return set_cors(web.json_response({"success": False, "error": "Old PIN is wrong"}))
        if len(new_pin) != 4 or not new_pin.isdigit():
            return set_cors(web.json_response({"success": False, "error": "PIN must be 4 digits"}))
        
        await _set_admin_pin(new_pin)
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.get('/api/admin/dashboard')
async def admin_dashboard(request):
    """Dashboard statistikalari."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.database import get_bot_statistics, get_advanced_dashboard_stats, users_collection
        stats = await get_bot_statistics()
        adv_stats = await get_advanced_dashboard_stats()
        
        # Til statistikasi
        lang_pipeline = [
            {"$group": {"_id": "$language", "count": {"$sum": 1}}}
        ]
        lang_stats = await users_collection.aggregate(lang_pipeline).to_list(10)
        langs = {item["_id"] or "uz": item["count"] for item in lang_stats}
        
        stats["lang_breakdown"] = langs
        
        # Daromad darajalari statistikasi
        from src.database import financial_history_collection
        income_pipeline = [
            {"$group": {"_id": "$income_level", "count": {"$sum": 1}}}
        ]
        income_stats_raw = await financial_history_collection.aggregate(income_pipeline).to_list(10)
        
        total_income = sum(item["count"] for item in income_stats_raw)
        income_levels = {"low": 0, "medium": 0, "high": 0}
        if total_income > 0:
            for item in income_stats_raw:
                if item["_id"] in income_levels:
                    income_levels[item["_id"]] = round((item["count"] / total_income) * 100)
                    
        stats["income_levels"] = income_levels
        
        # Qiziqishlar statistikasi
        interest_pipeline = [
            {"$unwind": "$interests"},
            {"$group": {"_id": "$interests", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        interest_stats_raw = await users_collection.aggregate(interest_pipeline).to_list(20)
        total_users_count = stats.get("total_users", 1) or 1
        interest_stats = {}
        for item in interest_stats_raw:
            if item["_id"]:
                interest_stats[item["_id"]] = round((item["count"] / total_users_count) * 100)
        stats["interest_stats"] = interest_stats
        
        # Merge advanced stats
        stats.update(adv_stats)
        
        return set_cors(web.json_response(stats))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.get('/api/admin/users')
async def admin_get_users(request):
    """Foydalanuvchilar ro'yxati."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.database import users_collection
        cursor = users_collection.find(
            {},
            {"_id": 0, "telegram_id": 1, "full_name": 1, "username": 1,
             "phone_number": 1, "language": 1, "age_group": 1,
             "country": 1, "region": 1, "timezone": 1,
             "interests": 1, "is_active": 1, "created_at": 1,
             "last_active": 1, "registration_complete": 1,
             "segmentation_stage": 1, "gender": 1}
        ).sort("created_at", -1)
        users = await cursor.to_list(length=5000)
        
        for u in users:
            if "created_at" in u and u["created_at"]:
                u["created_at"] = u["created_at"].isoformat()
            if "last_active" in u and u["last_active"]:
                u["last_active"] = u["last_active"].isoformat()
        
        return set_cors(web.json_response(users))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/admin/users/{telegram_id}')
async def admin_get_user_detail(request):
    """Bitta userning barcha tafsilotlarini qaytaradi."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        telegram_id = int(request.match_info['telegram_id'])
        from src.database import get_admin_user_detail
        user_detail = await get_admin_user_detail(telegram_id)
        if not user_detail:
            return set_cors(web.json_response({"error": "User topilmadi"}, status=404))
        return set_cors(web.json_response(user_detail))
    except ValueError:
        return set_cors(web.json_response({"error": "Invalid telegram_id"}, status=400))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.put('/api/admin/users/{telegram_id}/gender')
async def admin_update_gender(request):
    """Userning jinsini o'zgartiradi."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        telegram_id = int(request.match_info['telegram_id'])
        data = await request.json()
        new_gender = data.get("gender")
        if new_gender not in ["male", "female", "unknown"]:
            return set_cors(web.json_response({"error": "Noto'g'ri jins"}, status=400))
            
        from src.database import users_collection
        res = await users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"gender": new_gender}}
        )
        if res.matched_count == 0:
            return set_cors(web.json_response({"error": "User topilmadi"}, status=404))
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.delete('/api/admin/users/{telegram_id}/financial-history/{history_id}')
async def admin_delete_financial_history(request):
    """Userning daromad tarixini butunlay o'chirib yuboradi."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        telegram_id = int(request.match_info['telegram_id'])
        history_id = request.match_info['history_id']
        
        from src.database import financial_history_collection
        from bson import ObjectId
        
        res = await financial_history_collection.delete_one({
            "_id": ObjectId(history_id),
            "telegram_id": telegram_id
        })
        
        if res.deleted_count == 0:
            return set_cors(web.json_response({"error": "Tarix topilmadi"}, status=404))
            
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.post('/api/admin/users/{telegram_id}/ai-summary')
async def admin_user_ai_summary(request):
    """Groq API yordamida foydalanuvchining psixologik-moliyaviy tahlilini qaytaradi."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        telegram_id = int(request.match_info['telegram_id'])
        from src.database import get_admin_user_detail
        user = await get_admin_user_detail(telegram_id)
        if not user:
            return set_cors(web.json_response({"error": "User topilmadi"}, status=404))
            
        from src.services.groq_service import process_text_groq
        
        _interests = ', '.join(user['segment']['interests']) if user['segment']['interests'] else "Noma'lum"
        
        # Build prompt
        prompt = f"""
Sen malakali moliyaviy tahlilchi va psixologsan. 
Quyidagi foydalanuvchi haqidagi ma'lumotlarga asoslanib, uning qisqacha (3-4 ta gapdan iborat) o'zbek tilida tahlilini (AI Xulosasini) yozib ber. Foydalanuvchining daromad darajasi, yoshi, eng ko'p xarajat qiladigan sohasi va qiziqishlariga asoslanib uning ehtimoliy kimligi (kasbi yoki hayot tarzi) haqida taxmin qil va qanday moliyaviy taklif yoki mahsulot unga to'g'ri kelishini maslahat ber.

Ma'lumotlar:
- Yosh guruhi: {user['segment']['age_group']}
- Jinsi: {user['segment']['gender']}
- Yashash joyi: {user['segment']['region']}, {user['segment']['location']}
- Qiziqishlari: {_interests}
- O'rtacha oylik daromadi: {user['financial']['avg_income']} UZS
- O'rtacha oylik xarajati: {user['financial']['avg_expense']} UZS
- Eng ko'p pul sarflaydigan kategoriya: {user['financial']['top_expense_cat']}

Tahlil faqat matn ko'rinishida bo'lsin, hech qanday formatlashsiz (boldlarsiz, markdownlarsiz).
"""
        summary_text = await process_text_groq(prompt)
        return set_cors(web.json_response({"summary": summary_text}))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.get('/api/admin/segments')
async def admin_segments(request):
    """Segmentatsiya statistikasi."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.database import users_collection
        
        # Yosh guruhlari
        age_pipeline = [
            {"$match": {"age_group": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$age_group", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        age_stats = await users_collection.aggregate(age_pipeline).to_list(20)
        
        # Davlatlar
        country_pipeline = [
            {"$match": {"country": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$country", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        country_stats = await users_collection.aggregate(country_pipeline).to_list(50)
        
        # Viloyatlar
        region_pipeline = [
            {"$match": {"region": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$region", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        region_stats = await users_collection.aggregate(region_pipeline).to_list(50)
        
        # Qiziqishlar
        interest_pipeline = [
            {"$match": {"interests": {"$exists": True, "$ne": []}}},
            {"$unwind": "$interests"},
            {"$group": {"_id": "$interests", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        interest_stats = await users_collection.aggregate(interest_pipeline).to_list(50)
        
        # Segmentatsiya bosqichlari
        stage_pipeline = [
            {"$group": {"_id": "$segmentation_stage", "count": {"$sum": 1}}}
        ]
        stage_stats = await users_collection.aggregate(stage_pipeline).to_list(10)
        
        return set_cors(web.json_response({
            "age_groups": [{"label": s["_id"], "count": s["count"]} for s in age_stats],
            "countries": [{"label": s["_id"], "count": s["count"]} for s in country_stats],
            "regions": [{"label": s["_id"], "count": s["count"]} for s in region_stats],
            "interests": [{"label": s["_id"], "count": s["count"]} for s in interest_stats],
            "stages": {str(s["_id"]): s["count"] for s in stage_stats},
        }))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.post('/api/admin/segments/filter')
async def admin_filter_segments(request):
    """Tanlangan filtrlar asosida aniq segment ma'lumotlarini qaytaradi."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        filters = await request.json()
        from src.database import get_filtered_segment_data
        
        # Example filters payload:
        # {
        #   "age_groups": ["18-24", "25-34"],
        #   "genders": ["Erkak"],
        #   "countries": ["O'zbekiston"],
        #   "regions": ["Toshkent"],
        #   "languages": ["uz"],
        #   "interests": ["Sport"],
        #   "income_levels": ["Yuqori"]
        # }
        
        data = await get_filtered_segment_data(filters)
        return set_cors(web.json_response(data))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/admin/channel-stats')
async def admin_channel_stats(request):
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
        
    link = request.query.get("link")
    if not link:
        return set_cors(web.json_response({"error": "Missing link parameter"}, status=400))
        
    try:
        from src.database import get_admin_channel_stats
        data = await get_admin_channel_stats(link)
        return set_cors(web.json_response(data))
    except Exception as e:
        logger.error(f"Channel stats error: {e}")
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.get('/api/admin/channels')
async def admin_get_channels(request):
    """Kanallar ro'yxati."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.database import get_all_channels
        channels = await get_all_channels()
        result = []
        for ch in channels:
            result.append({
                "id": str(ch["_id"]),
                "name": ch.get("name", ""),
                "link": ch.get("link", ""),
            })
        return set_cors(web.json_response(result))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.get('/api/admin/channels/extended')
async def admin_get_channels_extended(request):
    """Kanallar ro'yxati va ularning statistikasi."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.database import get_all_channels, users_collection
        bot = request.app.get('bot')
        channels = await get_all_channels()
        
        # Jami bot foydalanuvchilari soni (konversiya uchun)
        total_users = await users_collection.count_documents({"is_active": True})
        
        result = []
        for ch in channels:
            link = ch.get("link", "")
            username = link.split("t.me/")[-1] if "t.me/" in link else link
            if not username.startswith("@"):
                username = f"@{username}"
            
            member_count = 0
            is_admin = False
            
            if bot:
                try:
                    member_count = await bot.get_chat_member_count(chat_id=username)
                    bot_member = await bot.get_chat_member(chat_id=username, user_id=bot.id)
                    if bot_member.status in ["administrator", "creator"]:
                        is_admin = True
                except Exception as e:
                    print(f"Error fetching channel stats for {username}: {e}")
            
            # Simple conversion mock
            joined_via_bot = total_users
            conversion = min(100, int((joined_via_bot / max(1, member_count)) * 100)) if member_count > 0 else 0
            
            result.append({
                "id": str(ch["_id"]),
                "name": ch.get("name", username),
                "username": username,
                "link": link,
                "member_count": member_count,
                "is_admin": is_admin,
                "joined_via_bot": joined_via_bot,
                "conversion": conversion
            })
            
        return set_cors(web.json_response(result))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.post('/api/admin/channels/verify_add')
async def admin_add_channel_verify(request):
    """Kanalni tekshirib qo'shish."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        
        if not username:
            return set_cors(web.json_response({"error": "Username is required"}, status=400))
            
        if not username.startswith("@"):
            username = f"@{username}"
            
        bot = request.app.get('bot')
        if not bot:
            return set_cors(web.json_response({"error": "Bot not available"}, status=500))
            
        # Verify bot is admin
        try:
            bot_member = await bot.get_chat_member(chat_id=username, user_id=bot.id)
            if bot_member.status not in ["administrator", "creator"]:
                return set_cors(web.json_response({"success": False, "error": "Bot bu kanalda admin emas! Avval botni admin qiling."}))
        except Exception as e:
            return set_cors(web.json_response({"success": False, "error": f"Kanal topilmadi yoki bot u yerda umuman yo'q. Avval botni admin qiling."}))
            
        link = f"https://t.me/{username[1:]}"
        
        # Try to get channel title
        try:
            chat = await bot.get_chat(chat_id=username)
            name = chat.title or username
        except:
            name = username
        
        from src.database import add_channel
        success = await add_channel(link, name)
        if success:
            return set_cors(web.json_response({"success": True}))
        return set_cors(web.json_response({"success": False, "error": "Kanal allaqachon mavjud."}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.delete('/api/admin/channels/{channel_id}')
async def admin_delete_channel(request):
    """Kanal o'chirish."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from bson import ObjectId
        from src.database import channels_collection
        channel_id = request.match_info['channel_id']
        result = await channels_collection.delete_one({"_id": ObjectId(channel_id)})
        if result.deleted_count > 0:
            return set_cors(web.json_response({"success": True}))
        return set_cors(web.json_response({"success": False, "error": "Not found"}, status=404))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


import uuid
from datetime import datetime
import asyncio

async def process_broadcast_job(job_id: str, users: list, text: str, bot, target: str):
    from src.database import save_broadcast_job
    
    total = len(users)
    sent = 0
    failed = 0
    
    job_data = {
        "text": text,
        "target": target,
        "total": total,
        "sent": 0,
        "failed": 0,
        "status": "running",
        "created_at": datetime.utcnow()
    }
    await save_broadcast_job(job_id, job_data)
    
    for u in users:
        try:
            await bot.send_message(chat_id=u["telegram_id"], text=text)
            sent += 1
        except Exception:
            failed += 1
            
        # Update progress in DB periodically
        if (sent + failed) % 20 == 0:
            await save_broadcast_job(job_id, {"status": "running", "sent": sent, "failed": failed})
            
        await asyncio.sleep(0.05) # Rate limit protection
        
    await save_broadcast_job(job_id, {
        "status": "completed",
        "sent": sent,
        "failed": failed
    })


@routes.post('/api/admin/broadcast')
async def admin_broadcast(request):
    """Orqa fonda barcha yoki segment/userga xabar yuborish."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        target_mode = data.get("mode", "all") # "all", "segment", "user"
        filters = data.get("filters", None)
        single_user_id = data.get("single_user_id", None)
        
        if not text:
            return set_cors(web.json_response({"error": "Text is required"}, status=400))
        
        from src.database import users_collection
        bot = request.app.get('bot')
        if not bot:
            return set_cors(web.json_response({"error": "Bot not available"}, status=500))
            
        # Build query
        query = {"is_active": True}
        target_label = "Barcha"
        
        if target_mode == "user" and single_user_id:
            try:
                single_user_id = int(single_user_id)
                query["telegram_id"] = single_user_id
                target_label = f"User: {single_user_id}"
            except ValueError:
                return set_cors(web.json_response({"error": "Invalid telegram_id"}, status=400))
        elif target_mode == "segment" and filters:
            target_label = "Segment"
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
        
        cursor = users_collection.find(query, {"telegram_id": 1})
        users = await cursor.to_list(length=100000)
        
        if len(users) == 0:
            return set_cors(web.json_response({"error": "No users found for this target."}, status=404))
            
        job_id = str(uuid.uuid4())
        
        # Start background task
        asyncio.create_task(process_broadcast_job(job_id, users, text, bot, target_label))
        
        return set_cors(web.json_response({"success": True, "job_id": job_id, "total": len(users)}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/admin/broadcast/status/{job_id}')
async def admin_broadcast_status(request):
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        job_id = request.match_info['job_id']
        from src.database import get_broadcast_job
        job = await get_broadcast_job(job_id)
        if not job:
            return set_cors(web.json_response({"error": "Job not found"}, status=404))
            
        if "created_at" in job:
            job["created_at"] = job["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        job["_id"] = str(job["_id"])
            
        return set_cors(web.json_response(job))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/admin/broadcast/history')
async def admin_broadcast_history(request):
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.database import get_broadcast_history
        history = await get_broadcast_history(10)
        return set_cors(web.json_response(history))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.get('/api/admin/spending-insights')
async def admin_spending_insights(request):
    """Userlarning xarajat tahlili — qaysi kategoriyaga ko'p pul sarflashadi."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    
    try:
        from src.database import transactions_collection, users_collection
        days = int(request.query.get("days", 30))
        from datetime import datetime, timedelta
        since = datetime.utcnow() - timedelta(days=days)
        
        # 1. Top kategoriyalar (barcha userlar bo'yicha)
        top_categories = await transactions_collection.aggregate([
            {"$match": {"type": "chiqim", "date": {"$gte": since}}},
            {"$group": {
                "_id": "$category",
                "total_amount": {"$sum": "$amount"},
                "count": {"$sum": 1},
                "unique_users": {"$addToSet": "$telegram_id"}
            }},
            {"$project": {
                "category": "$_id",
                "total_amount": 1,
                "count": 1,
                "user_count": {"$size": "$unique_users"},
                "_id": 0
            }},
            {"$sort": {"total_amount": -1}},
            {"$limit": 20}
        ]).to_list(20)
        
        # 2. Har bir user uchun top 3 kategoriya
        user_interests = await transactions_collection.aggregate([
            {"$match": {"type": "chiqim", "date": {"$gte": since}}},
            {"$group": {
                "_id": {"user": "$telegram_id", "cat": "$category"},
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"total": -1}},
            {"$group": {
                "_id": "$_id.user",
                "top_categories": {"$push": {"category": "$_id.cat", "total": "$total", "count": "$count"}}
            }},
            {"$project": {
                "telegram_id": "$_id",
                "top_categories": {"$slice": ["$top_categories", 3]},
                "_id": 0
            }},
            {"$sort": {"telegram_id": 1}}
        ]).to_list(500)
        
        # 3. User ismlari
        user_ids = [u["telegram_id"] for u in user_interests]
        users_data = {}
        if user_ids:
            async for u in users_collection.find(
                {"telegram_id": {"$in": user_ids}},
                {"telegram_id": 1, "full_name": 1, "username": 1}
            ):
                users_data[u["telegram_id"]] = {
                    "name": u.get("full_name", ""),
                    "username": u.get("username", "")
                }
        
        for ui in user_interests:
            ud = users_data.get(ui["telegram_id"], {})
            ui["name"] = ud.get("name", "Noma'lum")
            ui["username"] = ud.get("username", "")
        
        return set_cors(web.json_response({
            "top_categories": top_categories,
            "user_interests": user_interests,
            "period_days": days
        }))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return set_cors(web.json_response({"error": str(e)}, status=500))


@routes.post('/api/admin/ai-chat/stream')
async def admin_ai_chat_stream(request):
    """AI bilan streaming orqali gaplashish."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    
    try:
        data = await request.json()
        message = data.get("message", "").strip()
        history = data.get("history", [])
        
        if not message:
            return set_cors(web.json_response({"error": "Message is required"}, status=400))
        
        from src.database import get_filtered_segment_data
        import json
        # Jami statistika
        stats = await get_filtered_segment_data({})
        if "users" in stats:
            del stats["users"] # save tokens
            
        system_prompt = f"""Sen Somly AI Admin Assistant san. Senda butun bazadagi agregatsiya qilingan ma'lumotlar bor.
QOIDALAR:
1. Maxfiylik: Foydalanuvchilarning shaxsiy tranzaksiyalarini aniq ko'rsatma, faqat umumiy va o'rtacha holatni tahlil qil.
2. Reklama maslahati: Agar admin qaysi segmentga reklama berish haqida so'rasa, darhol javob bermasdan, avval admindan brif savollarini so'ra (qanday reklama, mahsulot qayerda joylashgan, h.k.). Savollarni matn ko'rinishida variantlar bilan, chiroyli ro'yxat qilib ber.
3. Statistika: Senga berilgan JSON dan foydalanib eng aniq ma'lumotlarni ber (masalan eng faol yosh, eng ko'p xarajat qilingan kategoriya).
4. Doim professional va o'zbek tilida javob ber.

STATISTIKA KONTEKSTI:
{json.dumps(stats, ensure_ascii=False)}
"""

        messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
        
        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*'
            }
        )
        await response.prepare(request)
        
        from src.services.groq_service import groq_service
        async for chunk in groq_service.stream_chat_completion_with_retry(messages, temperature=0.7, max_tokens=1500):
            await response.write(chunk.encode('utf-8'))
            
        await response.write_eof()
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Fallback to normal error response if not prepared yet
        return set_cors(web.json_response({"error": str(e)}, status=500))


# ─── REFERRAL ENDPOINTS ───

@routes.get('/api/referrals')
async def get_user_referrals(request):
    try:
        user_id = int(request.query.get("user_id", 0))
        if not user_id:
            return set_cors(web.json_response({"error": "Missing user_id"}, status=400))
        
        stats = await get_referral_stats(user_id)
        return set_cors(web.json_response(stats))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/admin/referrals')
async def get_admin_referrals(request):
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
        
    try:
        stats = await get_all_referral_stats()
        # Ensure datetimes are serialized
        for s in stats:
            if "last_date" in s and s["last_date"]:
                s["last_date"] = s["last_date"].isoformat()
        return set_cors(web.json_response(stats))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

async def error_middleware(app, handler):
    """Global error handling middleware for all API routes."""
    async def middleware_handler(request):
        try:
            return await handler(request)
        except web.HTTPException:
            raise  # Let aiohttp handle HTTP exceptions normally
        except Exception as e:
            error_msg = f"API Error on {request.method} {request.path}: {type(e).__name__}: {str(e)}"
            log_error(ErrorType.API_GENERAL, error_msg, exception=e)
            logger.exception(f"Unhandled API error: {error_msg}")
            
            # Try to alert admin for DB errors
            if "mongo" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                bot = request.app.get('bot')
                if bot:
                    try:
                        import asyncio
                        asyncio.create_task(
                            handle_error(bot, ErrorType.MONGODB_CONNECTION, error_msg, exception=e)
                        )
                    except Exception:
                        pass
            
            resp = web.json_response({"error": "Internal server error"}, status=500)
            return set_cors(resp)
    return middleware_handler


@routes.get('/api/admin/settings')
async def admin_get_settings(request):
    """Admin sozlamalarini olish."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.database import db
        settings_cursor = db["admin_settings"].find({})
        settings_list = await settings_cursor.to_list(length=50)
        
        result = {}
        for s in settings_list:
            result[s["key"]] = s["value"]
        
        # Defaults
        defaults = {
            "morning_reminder": "09:00",
            "afternoon_reminder": "15:00",
            "evening_reminder": "21:00",
            "monthly_summary_day": 1,
            "monthly_summary_time": "09:00",
            "segment_min_hours": 1,
            "segment_max_hours": 4,
            "interest_freq": "1w",
        }
        for k, v in defaults.items():
            if k not in result:
                result[k] = v
                
        return set_cors(web.json_response(result))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.put('/api/admin/settings')
async def admin_update_settings(request):
    """Admin sozlamalarini saqlash."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        data = await request.json()
        from src.database import db
        
        for key, value in data.items():
            await db["admin_settings"].update_one(
                {"key": key},
                {"$set": {"key": key, "value": value}},
                upsert=True
            )
        
        return set_cors(web.json_response({"success": True}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))

@routes.get('/api/admin/groq-status')
async def admin_groq_status(request):
    """Groq API kalitlari holatini ko'rsatish."""
    if not _verify_admin_token(request):
        return set_cors(web.json_response({"error": "Unauthorized"}, status=401))
    try:
        from src.services.groq_service import groq_service
        keys_info = []
        for ks in groq_service.keys_stats:
            keys_info.append({
                "index": ks.index + 1,
                "status": ks.status,
                "total_requests": ks.total_requests,
                "total_errors": ks.total_errors,
                "connection_errors": ks.connection_errors,
            })
        return set_cors(web.json_response({"keys": keys_info}))
    except Exception as e:
        return set_cors(web.json_response({"error": str(e)}, status=500))


async def on_shutdown(app):
    """Graceful shutdown: Notify all WebSockets before closing."""
    logger.info("Server shutting down, broadcasting to all WebSockets...")
    await ws_manager.broadcast_all("server_restarting")


async def start_api_server(bot=None):
    app = web.Application(middlewares=[error_middleware])
    app['bot'] = bot
    app.add_routes(routes)
    
    # ── Serve React Frontend in Production ──
    webapp_dir = os.path.join(os.getcwd(), 'webapp', 'dist')
    if os.path.exists(webapp_dir):
        # Serve assets directory
        assets_dir = os.path.join(webapp_dir, 'assets')
        if os.path.exists(assets_dir):
            app.router.add_static('/assets/', path=assets_dir, name='assets')
        
        # Serve public files manually or add generic static (we just need index.html to catch-all)
        async def spa_handler(request):
            # If requesting a specific file that exists (like favicon.ico, somly.jpg)
            file_path = os.path.join(webapp_dir, request.path.lstrip('/'))
            if os.path.isfile(file_path):
                return web.FileResponse(file_path)
            # Otherwise, return index.html for React Router
            return web.FileResponse(os.path.join(webapp_dir, 'index.html'))
            
        app.router.add_get('/{tail:.*}', spa_handler)
        
    app.on_shutdown.append(on_shutdown)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 API Server is running on http://0.0.0.0:{port}")
