"""
Dashboard web server — serves the UI and real-time WebSocket updates.
Uses aiohttp for lightweight async HTTP + WebSocket.
"""
import os
import json
import asyncio
from aiohttp import web
from bot.dashboard.state import dashboard_state
from bot.utils.logger import get_logger

log = get_logger(__name__)

DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(DASHBOARD_DIR, "static")

# Connected WebSocket clients for real-time push
_ws_clients: set = set()


async def index_handler(request):
    """Serve the dashboard HTML (no cache to always get latest)."""
    html_path = os.path.join(STATIC_DIR, "index.html")
    resp = web.FileResponse(html_path)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


async def api_state(request):
    """Return full dashboard state snapshot."""
    return web.json_response(dashboard_state.get_snapshot())


async def api_accounts(request):
    """Return accounts list."""
    return web.json_response({"accounts": dashboard_state.accounts})


async def api_export(request):
    """Export all data as JSON download."""
    data = dashboard_state.get_snapshot()
    return web.json_response(data, headers={
        "Content-Disposition": "attachment; filename=molty-export.json"
    })


async def ws_handler(request):
    """WebSocket endpoint — client stays connected for push updates."""
    ws = web.WebSocketResponse(heartbeat=30)  # 30s ping/pong keepalive
    await ws.prepare(request)
    _ws_clients.add(ws)
    log.info("Dashboard WS client connected (%d total)", len(_ws_clients))

    try:
        # Send initial snapshot
        snapshot = dashboard_state.get_snapshot()
        await ws.send_json({"type": "snapshot", "data": snapshot})

        # Keep connection alive — listen for client messages
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                pass  # No client commands yet
            elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                break
    except Exception as e:
        log.debug("WS handler error: %s", e)
    finally:
        _ws_clients.discard(ws)
        log.info("Dashboard WS client disconnected (%d remaining)", len(_ws_clients))

    return ws


async def _push_loop(app):
    """Background task: push state snapshots to all WS clients every 1.5s."""
    log.info("Dashboard push loop started")
    try:
        while True:
            await asyncio.sleep(1.5)
            if not _ws_clients:
                continue
            try:
                snapshot = dashboard_state.get_snapshot()
                msg = json.dumps({"type": "snapshot", "data": snapshot})
                dead = set()
                for ws in list(_ws_clients):  # Copy set to avoid mutation during iteration
                    try:
                        await ws.send_str(msg)
                    except Exception:
                        dead.add(ws)
                if dead:
                    _ws_clients -= dead
                    log.debug("Removed %d dead WS clients", len(dead))
            except Exception as e:
                log.warning("Dashboard push error: %s", e)
    except asyncio.CancelledError:
        log.info("Dashboard push loop stopped")


async def start_push_loop(app):
    """Start push loop as background task on app startup."""
    app['push_task'] = asyncio.create_task(_push_loop(app))


async def stop_push_loop(app):
    """Stop push loop on app shutdown."""
    task = app.get('push_task')
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def api_accounts_post(request):
    """Save account from dashboard form."""
    try:
        data = await request.json()
        dashboard_state.set_account(data)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def api_import(request):
    """Import data from JSON."""
    try:
        data = await request.json()
        if "accounts" in data:
            for acc in data["accounts"]:
                dashboard_state.set_account(acc)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


def create_app() -> web.Application:
    """Create the aiohttp web application."""
    app = web.Application()

    # Routes
    app.router.add_get("/", index_handler)
    app.router.add_get("/api/state", api_state)
    app.router.add_get("/api/accounts", api_accounts)
    app.router.add_post("/api/accounts", api_accounts_post)
    app.router.add_get("/api/export", api_export)
    app.router.add_post("/api/import", api_import)
    app.router.add_get("/ws", ws_handler)

    # Static files
    if os.path.exists(STATIC_DIR):
        app.router.add_static("/static/", STATIC_DIR)

    # Background push loop — uses aiohttp lifecycle hooks (reliable)
    app.on_startup.append(start_push_loop)
    app.on_cleanup.append(stop_push_loop)

    return app


async def start_dashboard(port: int = 8080):
    """Start the dashboard server (non-blocking)."""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("═══════════════════════════════════════════")
    log.info("  📊 Dashboard running at http://0.0.0.0:%d", port)
    log.info("═══════════════════════════════════════════")
