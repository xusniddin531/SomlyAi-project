import json
import asyncio
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # telegram_id -> list of web.WebSocketResponse
        self.active_connections: dict[int, list] = {}
        self.admin_connections: list = []

    def connect_admin(self, ws):
        if ws not in self.admin_connections:
            self.admin_connections.append(ws)
            logger.info(f"Admin connected to WebSocket. Total admins: {len(self.admin_connections)}")

    def disconnect_admin(self, ws):
        if ws in self.admin_connections:
            self.admin_connections.remove(ws)
            logger.info("Admin disconnected from WebSocket.")

    def connect(self, user_id: int, ws):
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(ws)
        logger.info(f"User {user_id} connected to WebSocket. Total connections for user: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: int, ws):
        if user_id in self.active_connections:
            if ws in self.active_connections[user_id]:
                self.active_connections[user_id].remove(ws)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"User {user_id} disconnected from WebSocket.")

    async def broadcast(self, user_id: int, event: str, data: dict = None):
        """
        Send an event to all connected websockets for a specific user.
        Also invalidates the user's dashboard cache so the next /api/dashboard
        call returns fresh data immediately (no 10s wait).
        """
        if data is None:
            data = {}

        # ── Invalidate dashboard cache for this user (mutations are noticed instantly) ──
        # Lazy import to avoid circular dependency (api.py imports ws_manager).
        try:
            from src.api import invalidate_user_cache
            invalidate_user_cache(user_id)
        except Exception:
            pass  # cache invalidation is best-effort

        if user_id in self.active_connections:
            message = json.dumps({"event": event, "data": data}, default=str)
            websockets = self.active_connections[user_id].copy()
            for ws in websockets:
                try:
                    await ws.send_str(message)
                except Exception as e:
                    logger.error(f"Error sending websocket message to {user_id}: {e}")
                    self.disconnect(user_id, ws)

    def broadcast_admin(self, event: str, data: dict = None):
        """Send an event to all connected admin websockets (async wrapper for consistency but runs via create_task if needed)."""
        pass # Will implement properly with async

    async def broadcast_all(self, event: str, data: dict = None):
        """
        Send an event to ALL connected websockets (used for graceful shutdown).
        """
        if data is None:
            data = {}
        message = json.dumps({"event": event, "data": data}, default=str)
        
        for user_id in list(self.active_connections.keys()):
            websockets = self.active_connections[user_id].copy()
            for ws in websockets:
                try:
                    await ws.send_str(message)
                except Exception as e:
                    self.disconnect(user_id, ws)

        # Broadcast to admins as well
        for ws in self.admin_connections.copy():
            try:
                await ws.send_str(message)
            except Exception:
                self.disconnect_admin(ws)

    async def broadcast_admin_async(self, event: str, data: dict = None):
        if data is None:
            data = {}
        message = json.dumps({"event": event, "data": data}, default=str)
        for ws in self.admin_connections.copy():
            try:
                await ws.send_str(message)
            except Exception:
                self.disconnect_admin(ws)
                
    def broadcast_admin(self, event: str, data: dict = None):
        """Fire and forget broadcast to admins."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.broadcast_admin_async(event, data))
        except RuntimeError:
            pass


ws_manager = ConnectionManager()
