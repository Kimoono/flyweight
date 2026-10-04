"""Flyweight game server (milestone 2: thinnest playable slice).

One process: FastAPI + uvicorn serve the beamer page (/), the phone controller (/play)
and a WebSocket (/ws). A background thread runs the simulation at 20 ticks/s:
gather held buttons -> brain.set_input() -> brain.step(50 ms) -> fly.update()
-> arena rules -> broadcast state JSON to every connected page.

Run:  python server.py            (prints the LAN URL + a QR code for /play)
      FLY_HOST=<ip> / FLY_PORT=<port> override the advertised address and the port.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sim"))
from brain import Brain  # noqa: E402  (sim/ is a plain directory, not a package)
from body import Fly     # noqa: E402
from senses import Eyes, STARTLE_R, STARTLE_S  # noqa: E402
from world import World, MODES, W as WORLD_W, H as WORLD_H, SIGHT_R  # noqa: E402
HEAT_S = 90.0                 # one heat
COUNTDOWN_S = 3.0
OVER_S = 8.0                  # result shown this long, then back to the lobby
SUGAR_COOLDOWN_S = 2.0        # per phone
BITTER_COOLDOWN_S = 4.0
# Seats on screen: zone id (sim/world.py MODES) -> label, colour, rect in world units (x0, y0, x1, y1; y up).
# The four-player colours avoid green (sugar), yellow (bitter) and red (spider).
ZONE_UI = {
    "left":  ("LEFT",         "#3b82f6", (0, 0, WORLD_W / 2, WORLD_H)),
    "right": ("RIGHT",        "#f59e0b", (WORLD_W / 2, 0, WORLD_W, WORLD_H)),
    "tl":    ("TOP LEFT",     "#3b82f6", (0, WORLD_H / 2, WORLD_W / 2, WORLD_H)),
    "tr":    ("TOP RIGHT",    "#f59e0b", (WORLD_W / 2, WORLD_H / 2, WORLD_W, WORLD_H)),
    "bl":    ("BOTTOM LEFT",  "#a855f7", (0, 0, WORLD_W / 2, WORLD_H / 2)),
    "br":    ("BOTTOM RIGHT", "#14b8a6", (WORLD_W / 2, 0, WORLD_W, WORLD_H / 2)),
}

# ----------------------------------------------------------------------------- config
PORT = int(os.environ.get("FLY_PORT", "8000"))
TICK_MS = 50                  # simulated ms per tick -> 20 ticks/s
DT_MS = 0.5                   # brain integration step
ARENA_W, ARENA_H = WORLD_W, WORLD_H   # world units (px on the beamer before scaling), from sim/world.py
HOLD_TIMEOUT_S = 1.5          # a pressed button expires unless the phone re-sends "press"
FAINT_S = 2.0                 # how long the fly is out after the watchdog fires
WATCHDOG_ACTIVE = 3000        # active neurons in one tick above this = olfactory runaway
CHUNK_MS = 5                  # spike-time resolution sent to the brain view (10 chunks per tick)
SPIKE_SAMPLE = 4000           # max spike events per tick sent to the brain view (random sample beyond)

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
        self.spikes: set[int] = set()        # clients that want the binary brain-view frames (the beamer)
        self.loop: asyncio.AbstractEventLoop | None = None

    async def broadcast(self, msg):
        data = msg if isinstance(msg, bytes) else json.dumps(msg, separators=(",", ":"))
        dead = []
        for cid, ws in list(self.clients.items()):
            if isinstance(data, bytes) and cid not in self.spikes:
                continue
            try:
                await (ws.send_bytes(data) if isinstance(data, bytes) else ws.send_text(data))
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.clients.pop(cid, None)

    def send_from_thread(self, msg):
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
        self.world = World()
        self.senses: list[str] = []
        self.eyes = Eyes()      # what the fly is looking at (sim/senses.py)
        # heat: a duel (two halves) or four players (quadrants), see MODES in sim/world.py
        self.phase = "lobby"            # lobby | countdown | playing | over
        self.phase_t = 0.0              # seconds left in the phase (countdown / playing / over)
        self.seats: dict[str, dict | None] = {z: None for z in MODES[self.world.mode]}   # zone -> {"name", "cid"}
        self.winner: str | None = None
        self.leaderboard: dict[str, dict] = {}    # name -> {"wins", "points", "heats"}
        self.sample_rng = np.random.default_rng(0)
        self.groups_json = json.dumps({kind: {name: {side: self.brain.groups[(name, side)].tolist() for side in ("left", "right")}
                                              for name in names}
                                       for kind, names in (("senses", sorted({n for n, _ in self.brain.groups} - set(self.brain.output_names))),
                                                           ("outputs", self.brain.output_names))})
        self.fainted_until = 0.0
        self.faints = 0
        self.tick = 0
        self.stop = threading.Event()
        self.cmds: queue.Queue = queue.Queue()      # phone/host commands, applied inside the sim thread

    # ---- heat phases
    def advance_phase(self, dt):
        if self.phase == "countdown":
            self.phase_t -= dt
            if self.phase_t <= 0:
                self.phase, self.phase_t = "playing", HEAT_S
        elif self.phase == "playing":
            self.phase_t -= dt
            if self.phase_t <= 0:
                sc = self.world.score
                top = [z for z, v in sc.items() if v == max(sc.values())]
                self.winner = top[0] if len(top) == 1 else "draw"      # a shared top score is a draw
                for side, p in self.seats.items():
                    if p:
                        row = self.leaderboard.setdefault(p["name"], {"wins": 0, "points": 0, "heats": 0})
                        row["points"] += sc[side]; row["heats"] += 1; row["wins"] += int(self.winner == side)
                self.phase, self.phase_t = "over", OVER_S
                print("HEAT over: " + " | ".join(f"{z} {p['name'] if p else '-'} {sc[z]}" for z, p in self.seats.items())
                      + f" -> {self.winner}", flush=True)
        elif self.phase == "over":
            self.phase_t -= dt
            if self.phase_t <= 0:
                self.phase, self.phase_t = "lobby", 0.0

    def apply_commands(self):
        while True:
            try:
                action, arg = self.cmds.get_nowait()
            except queue.Empty:
                break
            if action == "drop":
                x, y, kind, side = arg
                if not (0 <= x <= ARENA_W and 0 <= y <= ARENA_H) or self.phase == "over":
                    continue
                if side in self.seats:                 # sugar on your own ground, bitter on anyone else's
                    if kind == "sugar" and self.world.zone(x, y) != side:
                        continue
                    if kind == "bitter" and self.world.zone(x, y) == side:
                        continue
                what = self.world.add_drop(x, y, bitter=(kind == "bitter"), owner=side)
                self.world.events.append((self.tick * TICK_MS / 1000.0, "SPOILED!" if what == "spoiled" else ""))
                continue
            if action == "heat":
                if arg == "start" and self.phase in ("lobby", "over"):
                    self.world.reset_round(self.fly); self.brain.reset()
                    self.phase, self.phase_t, self.winner = "countdown", COUNTDOWN_S, None
                elif arg == "stop":
                    self.phase, self.phase_t, self.winner = "lobby", 0.0, None
                elif arg == "reset_scores":
                    self.leaderboard = {}
                elif arg == "clear_players":
                    self.seats = {z: None for z in self.seats}
                elif arg in MODES and arg != self.world.mode and self.phase in ("lobby", "over"):
                    self.world.set_mode(arg); self.world.drops = []
                    self.seats = {z: None for z in MODES[arg]}     # everyone picks a seat again
                    self.phase, self.phase_t, self.winner = "lobby", 0.0, None
                continue
            if action == "join_duel":
                name, side, cid = arg
                for s in self.seats:                   # one seat per phone, one phone per seat
                    if self.seats[s] and self.seats[s]["cid"] == cid:
                        self.seats[s] = None
                if side in self.seats:
                    self.seats[side] = {"name": name, "cid": cid}
                continue

    def step_tick(self):
        """brain.step(TICK_MS) in CHUNK_MS pieces so the brain view can show spike order inside a
        tick. Returns (outputs, active, spike events) - same outputs brain.step() would return."""
        counts = np.zeros(self.brain.n, np.int32)
        events = []
        for c in range(TICK_MS // CHUNK_MS):
            cnt = self.brain.step(CHUNK_MS, return_counts=True)
            counts += cnt
            spk = np.flatnonzero(cnt)
            if len(spk):
                events.append(spk.astype(np.uint32) | np.uint32(c << 18))   # neuron index < 2^18
        sec = TICK_MS / 1000.0
        out = {name: {s: float(counts[self.brain.groups[(name, s)]].mean() / sec) for s in ("left", "right")}
               for name in self.brain.output_names}
        ev = np.concatenate(events) if events else np.empty(0, np.uint32)
        if len(ev) > SPIKE_SAMPLE:
            ev = np.sort(self.sample_rng.choice(ev, SPIKE_SAMPLE, replace=False))
        return out, int((counts > 0).sum()), ev

    def run(self):
        period = TICK_MS / 1000.0
        stat_t, stat_ticks, stat_brain, stat_late = time.perf_counter(), 0, 0.0, 0
        next_t = time.perf_counter()
        while not self.stop.is_set():
            t_start = time.perf_counter()
            self.apply_commands()
            held = inputs.snapshot()
            now = time.monotonic()
            fainted = now < self.fainted_until
            if fainted:
                # The fly is out: no senses, no movement, brain left freshly reset.
                out = {name: {"left": 0.0, "right": 0.0} for name in self.brain.output_names}
                active = 0
                brain_ms = 0.0
                ev = np.empty(0, np.uint32)
                rates = {}
            else:
                # what the world does to the senses (sim/senses.py) + what the phones add (direct lines)
                d = self.world.on_drop(self.fly)
                rates, self.senses = self.eyes.encode(self.fly, self.world.drop_xy(), self.world.hazards(self.fly),
                                                     bool(d and d["sugar"]), bool(d and d["bitter"]), TICK_MS / 1000.0,
                                                     splashes=self.world.splashes(STARTLE_S))
                for group, sides in inputs.rates(held).items():
                    for side, hz in sides.items():
                        rates.setdefault(group, {})[side] = max(rates.get(group, {}).get(side, 0), hz)
                self.brain.set_input(rates)
                tb = time.perf_counter()
                out, active, ev = self.step_tick()
                brain_ms = (time.perf_counter() - tb) * 1000
                if active > WATCHDOG_ACTIVE:
                    # Trap 1 in docs/findings.md: olfactory runaway. Reset and fail funny.
                    self.brain.reset()
                    self.fly.feeding = self.fly.jumped = False
                    self.faints += 1
                    self.fainted_until = now + FAINT_S
                    d = self.world.on_drop(self.fly)
                    print(f"WATCHDOG: {active} active neurons in one tick -> brain reset, fly fainted | inputs {rates} | "
                          f"senses {self.senses} | held {sorted(held)} | on drop {d} | spiders {[sp.state for sp in self.world.spiders]} | "
                          f"phase {self.phase} t={self.tick * TICK_MS / 1000:.1f}s", flush=True)
                    hub.send_from_thread({"type": "fainted", "active": active, "seconds": FAINT_S})
                else:
                    if self.world.fly_dead <= 0 and self.phase != "countdown":
                        self.fly.update(out, TICK_MS / 1000.0)
                    self.world.update(self.fly, TICK_MS / 1000.0, self.tick * TICK_MS / 1000.0)   # walls, eating, spider, respawn
            self.tick += 1
            self.advance_phase(TICK_MS / 1000.0)
            tick_ms = (time.perf_counter() - t_start) * 1000
            # binary frame for the brain view: uint32 tick, then uint32 events (chunk << 18 | neuron index)
            hub.send_from_thread(np.uint32(self.tick).tobytes() + ev.tobytes())
            hub.send_from_thread({
                "type": "state",
                "tick": self.tick,
                "fly": {"x": round(self.fly.x, 1), "y": round(self.fly.y, 1),
                        "heading": round(self.fly.heading, 3),
                        "feeding": self.fly.feeding, "jumped": self.fly.jumped},
                "outputs": {k: {"left": round(v["left"]), "right": round(v["right"])} for k, v in out.items()},
                "active": active,
                "held": sorted(held),
                "senses": self.senses if not fainted else [],
                "rates": {f"{g}_{s}": round(hz) for g, sides in (rates.items() if not fainted else []) for s, hz in sides.items()},
                "world": {"drops": [{"x": round(d["x"]), "y": round(d["y"]), "bitter": d["bitter"], "sugar": d["sugar"]} for d in self.world.drops],
                          "spiders": [{"x": round(sp.x), "y": round(sp.y), "state": sp.state, "heading": round(sp.heading, 3),
                                       "lair": [round(sp.home_x), round(sp.home_y)]} for sp in self.world.spiders],
                          "spider_closing": self.world.spider_closing, "sight_r": SIGHT_R, "startle_r": STARTLE_R,
                          "fly_dead": self.world.fly_dead > 0,
                          "eating": round(self.world.eating / 1.5, 2),
                          "score": self.world.score, "caught": self.world.caught,
                          "events": [e for t_ev, e in self.world.events if e and t_ev > (self.tick - 20) * TICK_MS / 1000.0]},
                "heat": {"phase": self.phase, "time_left": round(self.phase_t, 1), "winner": self.winner,
                         "mode": self.world.mode,
                         "zones": [{"id": z, "label": ZONE_UI[z][0], "colour": ZONE_UI[z][1], "rect": ZONE_UI[z][2]} for z in self.seats],
                         "players": {s: (p["name"] if p else None) for s, p in self.seats.items()},
                         "leaderboard": sorted(({"name": n, **v} for n, v in self.leaderboard.items()),
                                               key=lambda r: (-r["wins"], -r["points"], r["name"]))[:10]},
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


@app.get("/host")
async def host():
    return FileResponse(WEB / "host.html")


@app.get("/qr.svg")
async def qr_svg():
    """Join QR code for the beamer, built from the current LAN address (follows a network switch)."""
    import qrcode
    import qrcode.image.svg
    from fastapi.responses import Response
    url = f"http://{lan_ips()[0]}:{PORT}/play"
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathFillImage, border=2)
    return Response(img.to_string(), media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store", "X-Join-Url": url})


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)


@app.get("/positions.bin")
async def positions():
    """float32 (x, y, z) per neuron in simulator index order; built by sim/build_positions.py."""
    return FileResponse(ROOT / "data" / "positions.bin", media_type="application/octet-stream")


@app.get("/groups.json")
async def groups():
    """Neuron indices of every sense and output group, per side (for colouring the brain view)."""
    from fastapi.responses import Response
    return Response(game.groups_json, media_type="application/json")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    cid = id(ws)
    hub.clients[cid] = ws
    last_drop = {"sugar": -1e9, "bitter": -1e9}
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
            elif t == "subscribe":
                (hub.spikes.add if msg.get("spikes") else hub.spikes.discard)(cid)
            elif t == "drop":
                kind = "bitter" if msg.get("kind") == "bitter" else "sugar"
                now = time.monotonic()
                if now - last_drop[kind] >= (BITTER_COOLDOWN_S if kind == "bitter" else SUGAR_COOLDOWN_S):
                    last_drop[kind] = now
                    side = next((s for s, p in game.seats.items() if p and p["cid"] == cid), None)
                    game.cmds.put(("drop", (float(msg.get("x", 0)), float(msg.get("y", 0)), kind, side)))
            elif t == "join_duel":
                name = str(msg.get("name", ""))[:16].strip() or "?"
                game.cmds.put(("join_duel", (name, msg.get("side"), cid)))
            elif t == "heat":
                game.cmds.put(("heat", msg.get("action")))
            elif t == "ping":
                await ws.send_text('{"type":"pong"}')
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.clients.pop(cid, None)
        hub.spikes.discard(cid)
        inputs.players.pop(cid, None)
        inputs.release(cid)


app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


# ----------------------------------------------------------------------------- startup banner
# Interfaces a phone on the wifi cannot reach. A VPN that owns the default route used to win the
# "outbound address" test below, and the QR code then pointed into the tunnel (10.5.0.2).
TUNNEL_IFACES = ("utun", "tun", "tap", "wg", "ppp", "ipsec", "tailscale", "gif", "stf")
# VM / container bridges. Ranked low, not dropped: the Mac's own Internet Sharing hotspot is a bridge too.
VIRTUAL_IFACES = ("bridge", "vmenet", "vmnet", "vboxnet", "docker", "br-", "veth", "virbr")


def iface_ips() -> list[tuple[str, str]]:
    """(interface, IPv4) for every address on this machine, loopback excluded."""
    out: list[tuple[str, str]] = []
    try:
        if sys.platform == "darwin":
            iface = ""
            for line in subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout.splitlines():
                if line and not line[0].isspace():
                    iface = line.split(":")[0]
                elif line.split()[:1] == ["inet"]:
                    out.append((iface, line.split()[1]))
        else:  # "2: wlan0    inet 192.168.1.5/24 brd ..."
            for line in subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True, timeout=3).stdout.splitlines():
                f = line.split()
                if len(f) > 3 and f[2] == "inet":
                    out.append((f[1], f[3].split("/")[0]))
    except Exception:
        pass
    return [(i, ip) for i, ip in out if not ip.startswith("127.")]


def lan_ips() -> list[str]:
    """Addresses to reach this server on, best guess for the phones first.

    FLY_HOST=<ip or name> overrides the guess. Otherwise: real network cards (wifi, ethernet, an
    iPhone hotspot) before VM bridges before VPN tunnels; within a class the address the OS would
    use for outbound traffic comes first. Recomputed on every call, so it follows a network switch.
    """
    forced = os.environ.get("FLY_HOST", "").strip()
    if forced:
        return [forced]
    default = ""
    try:  # the address the OS would use for an outbound packet (no packet is sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        default = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    def rank(pair: tuple[str, str]) -> tuple[int, bool, bool]:
        iface, ip = pair
        kind = 2 if iface.startswith(TUNNEL_IFACES) else 1 if iface.startswith(VIRTUAL_IFACES) else 0
        return (kind, ip.startswith("169.254."), ip != default)

    ips = list(dict.fromkeys(ip for _, ip in sorted(iface_ips(), key=rank)))
    if not ips and default and not default.startswith("127."):
        ips = [default]  # no ifconfig / ip on this system: the outbound address is all we know
    return ips or ["127.0.0.1"]


def print_urls():
    ips = lan_ips()
    url = f"http://{ips[0]}:{PORT}"
    print("\n" + "=" * 60)
    print(f"  BEAMER   {url}/")
    print(f"  PHONES   {url}/play")
    print(f"  HOST     {url}/host   (heats)")
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
