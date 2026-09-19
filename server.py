"""Fly by Committee game server (milestone 2: thinnest playable slice).

One process: FastAPI + uvicorn serve the beamer page (/), the phone controller (/play)
and a WebSocket (/ws). A background thread runs the simulation at 20 ticks/s:
gather held buttons -> brain.set_input() -> brain.step(50 ms) -> fly.update()
-> arena rules -> broadcast state JSON to every connected page.

Run:  python server.py            (prints the LAN URL + a QR code for /play)
"""
from __future__ import annotations

import asyncio
import json
import math
import socket
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sim"))
from brain import Brain  # noqa: E402  (sim/ is a plain directory, not a package)
from body import Fly     # noqa: E402

# ----------------------------------------------------------------------------- config
PORT = 8000
TICK_MS = 50                  # simulated ms per tick -> 20 ticks/s
DT_MS = 0.5                   # brain integration step
ARENA_W, ARENA_H = 1600.0, 900.0   # world units (px on the beamer before scaling)
HOLD_TIMEOUT_S = 1.5          # a pressed button expires unless the phone re-sends "press"
FAINT_S = 2.0                 # how long the fly is out after the watchdog fires
WATCHDOG_ACTIVE = 3000        # active neurons in one tick above this = olfactory runaway

# Button -> (sense group, side, Hz). Taste rates are low on purpose: a button is HELD for
# seconds, and sustained sugar >= 60 Hz or bitter 150 Hz ignites the olfactory runaway
# within a few seconds ("Sustained input" in docs/findings.md). 40/60 Hz never did in tests.
BUTTONS = {
    "left_eye":     ("eye_target", "left",  150),
    "right_eye":    ("eye_target", "right", 150),
    "left_shadow":  ("shadow",     "left",  150),
    "right_shadow": ("shadow",     "right", 150),
    "sugar":        ("sugar",      "both",  40),
    "bitter":       ("bitter",     "both",  60),
}
ROLES = {
    "left_eye":     ["left_eye"],
    "right_eye":    ["right_eye"],
    "left_shadow":  ["left_shadow"],
    "right_shadow": ["right_shadow"],
    "tongue":       ["sugar", "bitter"],
}


# ----------------------------------------------------------------------------- shared state
class Inputs:
    """Buttons currently held, per connection. Written by the asyncio thread, read by the sim thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.held: dict[int, dict[str, float]] = {}   # conn id -> {button: last press time}
        self.players: dict[int, dict] = {}            # conn id -> {"role": ..., "name": ...}

    def press(self, cid: int, button: str):
        if button in BUTTONS:
            with self.lock:
                self.held.setdefault(cid, {})[button] = time.monotonic()

    def release(self, cid: int, button: str | None = None):
        with self.lock:
            if button is None:
                self.held.pop(cid, None)
            else:
                self.held.get(cid, {}).pop(button, None)

    def snapshot(self) -> set[str]:
        """Buttons held by anyone right now (stale holds from frozen phones expire)."""
        now = time.monotonic()
        with self.lock:
            return {b for holds in self.held.values() for b, t in holds.items() if now - t < HOLD_TIMEOUT_S}

    def rates(self, held: set[str]) -> dict:
        rates: dict[str, dict[str, float]] = {}
        for b in held:
            group, side, hz = BUTTONS[b]
            for s in (("left", "right") if side == "both" else (side,)):
                rates.setdefault(group, {})[s] = max(rates.get(group, {}).get(s, 0), hz)
        return rates


class Hub:
    """Fan-out of state JSON to all websocket clients."""

    def __init__(self):
        self.clients: dict[int, WebSocket] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def broadcast(self, msg: dict):
        data = json.dumps(msg, separators=(",", ":"))
        dead = []
        for cid, ws in list(self.clients.items()):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.clients.pop(cid, None)

    def send_from_thread(self, msg: dict):
        if self.loop is not None and self.clients:
            asyncio.run_coroutine_threadsafe(self.broadcast(msg), self.loop)


inputs = Inputs()
hub = Hub()


# ----------------------------------------------------------------------------- sim loop
class Game:
    def __init__(self):
        t0 = time.time()
        self.brain = Brain(dt=DT_MS)
        print(f"brain loaded: {self.brain.n} neurons in {time.time() - t0:.1f}s, dt={DT_MS} ms")
        self.fly = Fly(x=ARENA_W / 2, y=ARENA_H / 2, heading=0.0)
        self.fainted_until = 0.0
        self.faints = 0
        self.tick = 0
        self.stop = threading.Event()

    def run(self):
        period = TICK_MS / 1000.0
        stat_t, stat_ticks, stat_brain, stat_late = time.perf_counter(), 0, 0.0, 0
        next_t = time.perf_counter()
        while not self.stop.is_set():
            t_start = time.perf_counter()
            held = inputs.snapshot()
            now = time.monotonic()
            fainted = now < self.fainted_until
            if fainted:
                # The fly is out: no senses, no movement, brain left freshly reset.
                out = {name: {"left": 0.0, "right": 0.0} for name in self.brain.output_names}
                active = 0
                brain_ms = 0.0
            else:
                self.brain.set_input(inputs.rates(held))
                tb = time.perf_counter()
                out, active = self.brain.step(TICK_MS)
                brain_ms = (time.perf_counter() - tb) * 1000
                if active > WATCHDOG_ACTIVE:
                    # Trap 1 in docs/findings.md: olfactory runaway. Reset and fail funny.
                    self.brain.reset()
                    self.fly.feeding = self.fly.jumped = False
                    self.faints += 1
                    self.fainted_until = now + FAINT_S
                    print(f"WATCHDOG: {active} active neurons in one tick -> brain reset, fly fainted", flush=True)
                    hub.send_from_thread({"type": "fainted", "active": active, "seconds": FAINT_S})
                else:
                    self.fly.update(out, TICK_MS / 1000.0)
                    # Arena rule (not behaviour): the arena wraps around like Pac-Man.
                    self.fly.x %= ARENA_W
                    self.fly.y %= ARENA_H
            self.tick += 1
            tick_ms = (time.perf_counter() - t_start) * 1000
            hub.send_from_thread({
                "type": "state",
                "tick": self.tick,
                "fly": {"x": round(self.fly.x, 1), "y": round(self.fly.y, 1),
                        "heading": round(self.fly.heading, 3),
                        "feeding": self.fly.feeding, "jumped": self.fly.jumped},
                "outputs": {k: {"left": round(v["left"]), "right": round(v["right"])} for k, v in out.items()},
                "active": active,
                "held": sorted(held),
                "fainted": fainted,
                "players": [p for p in inputs.players.values()],
                "perf": {"brain_ms": round(brain_ms), "tick_ms": round(tick_ms)},
                "arena": {"w": ARENA_W, "h": ARENA_H},
            })
            # timing stats, printed every 5 s
            stat_ticks += 1
            stat_brain += brain_ms
            if tick_ms > TICK_MS:
                stat_late += 1
            if time.perf_counter() - stat_t >= 5.0:
                el = time.perf_counter() - stat_t
                print(f"sim: {stat_ticks / el:4.1f} ticks/s  brain {stat_brain / stat_ticks:4.1f} ms/tick  "
                      f"late ticks {stat_late}/{stat_ticks}  active {active}  held {sorted(held) or '-'}", flush=True)
                stat_t, stat_ticks, stat_brain, stat_late = time.perf_counter(), 0, 0.0, 0
            # pace to 20 ticks/s; if a tick overran, don't try to catch up (no burst)
            next_t = max(next_t + period, time.perf_counter() - period)
            delay = next_t - time.perf_counter()
            if delay > 0:
                time.sleep(delay)


game: Game | None = None


# ----------------------------------------------------------------------------- web app
@asynccontextmanager
async def lifespan(app: FastAPI):
    global game
    hub.loop = asyncio.get_running_loop()
    game = Game()
    threading.Thread(target=game.run, name="sim", daemon=True).start()
    print_urls()
    yield
    game.stop.set()


app = FastAPI(lifespan=lifespan)
WEB = ROOT / "web"


@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")


@app.get("/play")
async def play():
    return FileResponse(WEB / "play.html")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    cid = id(ws)
    hub.clients[cid] = ws
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            t = msg.get("type")
            if t == "join":
                role = msg.get("role")
                if role in ROLES:
                    inputs.players[cid] = {"role": role, "name": str(msg.get("name", ""))[:20]}
                    await ws.send_text(json.dumps({"type": "joined", "role": role, "buttons": ROLES[role]}))
                else:
                    inputs.players.pop(cid, None)
                    inputs.release(cid)
            elif t == "press":
                inputs.press(cid, msg.get("button"))
            elif t == "release":
                inputs.release(cid, msg.get("button"))
            elif t == "release_all":
                inputs.release(cid)
            elif t == "ping":
                await ws.send_text('{"type":"pong"}')
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.clients.pop(cid, None)
        inputs.players.pop(cid, None)
        inputs.release(cid)


app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


# ----------------------------------------------------------------------------- startup banner
def lan_ips() -> list[str]:
    ips: list[str] = []
    try:  # the address the OS would use for an outbound packet (no packet is sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:  # every other IPv4 on this machine (hotspot / travel router interfaces)
        cmd = ["ifconfig"] if sys.platform == "darwin" else ["ip", "-4", "-o", "addr"]
        toks = subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.split()
        for prev, tok in zip(toks, toks[1:]):
            if prev == "inet" and tok.count(".") == 3:
                ip = tok.split("/")[0]
                if not ip.startswith("127.") and ip not in ips:
                    ips.append(ip)
    except Exception:
        pass
    return ips or ["127.0.0.1"]


def print_urls():
    ips = lan_ips()
    url = f"http://{ips[0]}:{PORT}"
    print("\n" + "=" * 60)
    print(f"  BEAMER   {url}/")
    print(f"  PHONES   {url}/play")
    if len(ips) > 1:
        print("  other addresses: " + ", ".join(f"http://{ip}:{PORT}" for ip in ips[1:]))
    print("=" * 60)
    try:
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(f"{url}/play")
        qr.print_ascii(invert=True)
    except Exception as e:  # pragma: no cover
        print(f"(no QR code: {e})")
    print(f"  scan to join -> {url}/play\n", flush=True)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning", ws_ping_interval=5, ws_ping_timeout=5)
