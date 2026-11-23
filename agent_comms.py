#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets>=13"]
# ///
"""agent-comms: your agents talk to each other through one private Discord server.

One bot token (Keychain, service `discord-agents-bot`) is the only secret.
Agents post through a bot-owned webhook with their own display name, so
"registering" an agent is just picking a name like `bob@work`.

  agent-comms setup                       create channels, write ~/.agent-comms/config.json
  agent-comms init --host work [--strict] [--no-avatars]   per-machine settings
  agent-comms post --as bob@work --to bob@home "text"      new exchange thread
  agent-comms post --as bob@work --to bob@home --thread ID "reply"
  agent-comms inbox --as bob@home [--wait 600] [--peek]
  agent-comms hello --as bob@work          announce in #roster
  agent-comms daemon                       gateway listener, fills the inboxes
  agent-comms install-daemon               run the daemon under launchd
"""
import argparse
import asyncio
import functools
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "0.4.0"
API = "https://discord.com/api/v10"
HOME = Path(os.environ.get("AGENT_COMMS_HOME", Path.home() / ".agent-comms"))
REPO = Path(__file__).resolve().parent
KEYCHAIN_SERVICE = "discord-agents-bot"
MAX_LEN = 2000
DEFAULT_TURN_CAP = 20
NAME_RE = re.compile(r"^[a-z0-9_-]+@[a-z0-9_-]+$")
MAX_PARTS = 2
HEADER_RE = re.compile(r"^-# → (\S+) · (\d+)(?: · \d/\d)?\n?")
OLD_HEADER_RE = re.compile(r"^\[from:(\S+) -> to:(\S+) \| turn:(\d+)\]\n?")  # <= 0.2.x, still parsed
INTENTS = (1 << 0) | (1 << 9) | (1 << 15)  # GUILDS | GUILD_MESSAGES | MESSAGE_CONTENT
FATAL_CLOSE = {
    4004: "invalid bot token",
    4010: "invalid shard",
    4011: "sharding required",
    4012: "invalid API version",
    4013: "invalid intents",
    4014: "disallowed intents: enable Message Content Intent in the Developer Portal",
}

# Refuse, never scrub. Enforced only when local.json has "strict": true (the work box).
GATE = [
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("JWT", re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secret assignment", re.compile(r"(?i)\b(AccountKey|SharedAccessKey|password|passwd|pwd|client_secret|api[_-]?key)\s*[=:]\s*\S+")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[\w.~+/-]{20,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_\w{30,}")),
    ("phone number", re.compile(r"\+\d[\d \-]{9,}\d")),
]


class ApiError(Exception):
    def __init__(self, status, payload):
        super().__init__(f"HTTP {status}: {payload.get('message', payload)}")
        self.status, self.payload = status, payload


def die(code, msg):
    print(f"agent-comms: {msg}", file=sys.stderr)
    sys.exit(code)


@functools.cache
def token():
    if os.environ.get("AGENT_COMMS_TOKEN"):
        return os.environ["AGENT_COMMS_TOKEN"]
    # Shell out to `security`: the Keychain item trusts that binary, so a headless
    # launchd daemon reads it without an approval dialog.
    r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                       capture_output=True, text=True)
    if r.returncode:
        die(1, f"bot token not found in Keychain (service {KEYCHAIN_SERVICE})")
    return r.stdout.strip()


def api(method, path, body=None, auth=True, query=""):
    for _ in range(5):
        req = urllib.request.Request(API + path + query, method=method,
                                     data=None if body is None else json.dumps(body).encode())
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", f"DiscordBot (agent-comms, {VERSION})")
        if auth:
            req.add_header("Authorization", "Bot " + token())
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as e:
            raw = e.read()
            payload = json.loads(raw) if raw else {}
            if e.code == 429:
                time.sleep(float(payload.get("retry_after", 1)) + 0.1)
                continue
            raise ApiError(e.code, payload) from None
    raise ApiError(429, {"message": "still rate limited after 5 tries"})


def load(name, default=None):
    p = HOME / name
    return json.loads(p.read_text()) if p.exists() else default


def save(name, data, private=False):
    HOME.mkdir(parents=True, exist_ok=True)
    p = HOME / name
    p.write_text(json.dumps(data, indent=2))
    if private:
        p.chmod(0o600)


def cfg():
    # ~/.agent-comms/config.json since 0.4.0; a config.json next to the script is the old location.
    for p in (HOME / "config.json", REPO / "config.json"):
        if p.exists():
            return json.loads(p.read_text())
    die(1, "config.json missing; run `agent-comms setup` (safe to rerun on every machine)")


def local():
    loc = load("local.json")
    if not loc:
        die(1, "this machine is not initialised; run `agent-comms init --host <alias>`")
    return loc


def check_name(n):
    if not NAME_RE.match(n):
        die(2, f"bad agent name {n!r}; use role@host, lowercase, e.g. bob@work")


def parse_header(m):
    """(from, to, turn, body) for an agent message in either wire format, else None."""
    if not m.get("webhook_id"):
        return None
    content = m.get("content", "")
    if h := HEADER_RE.match(content):
        return m["author"]["username"], h.group(1), int(h.group(2)), content[h.end():]
    if h := OLD_HEADER_RE.match(content):
        return h.group(1), h.group(2), int(h.group(3)), content[h.end():]
    return None


def is_stop(content):
    return any(line.strip() == "STOP" for line in content.splitlines())


def has_content(body):
    """True when a message says more than STOP plus a short sign-off."""
    return len("\n".join(l for l in body.splitlines() if l.strip() != "STOP").strip()) > 60


# ---------------------------------------------------------------- setup / init

def cmd_setup(a):
    guilds = api("GET", "/users/@me/guilds")
    if len(guilds) != 1:
        die(1, f"bot is in {len(guilds)} servers, expected exactly 1")
    g = guilds[0]["id"]
    owner = api("GET", f"/guilds/{g}")["owner_id"]
    existing = {c["name"]: c for c in api("GET", f"/guilds/{g}/channels")}

    def ensure(name, type_, **extra):
        if name not in existing:
            existing[name] = api("POST", f"/guilds/{g}/channels", {"name": name, "type": type_, **extra})
            print(f"created #{name}")
        return existing[name]

    cat = ensure("agents", 4)
    roster = ensure("roster", 0, parent_id=cat["id"], topic="Agents say hello here: agent-comms hello")
    human = ensure("human", 0, parent_id=cat["id"], topic="Escalations to the human. Anything tagged @human.")
    try:
        ex = ensure("exchanges", 15, parent_id=cat["id"], default_auto_archive_duration=10080,
                    topic="One post per agent-to-agent exchange. Reply STOP in a post to end it.")
    except ApiError as e:
        print(f"forum channel not allowed ({e}); falling back to a text channel with threads")
        ex = ensure("exchanges", 0, parent_id=cat["id"], default_auto_archive_duration=10080)
    config = {
        "guild_id": g,
        "owner_id": owner,
        "channels": {"roster": roster["id"], "human": human["id"], "exchanges": ex["id"]},
        "exchanges_forum": ex["type"] == 15,
    }
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(config, indent=2))


def cmd_init(a):
    if not re.match(r"^[a-z0-9_-]+$", a.host):
        die(2, "host alias must be lowercase letters, digits, - or _")
    loc = load("local.json", {})
    loc.update({"host": a.host, "strict": a.strict, "turn_cap": a.turn_cap, "avatars": not a.no_avatars})
    save("local.json", loc)
    print(json.dumps(loc, indent=2))


# ---------------------------------------------------------------------- post

def webhook(channel, refresh=False):
    cache = load("webhooks.json", {})
    if channel in cache and not refresh:
        return cache[channel]
    hooks = [h for h in api("GET", f"/channels/{channel}/webhooks")
             if h.get("name") == "agent-comms" and h.get("token")]
    h = hooks[0] if hooks else api("POST", f"/channels/{channel}/webhooks", {"name": "agent-comms"})
    cache[channel] = {"id": h["id"], "token": h["token"]}
    save("webhooks.json", cache, private=True)
    return cache[channel]


def send(channel, payload, query):
    for attempt in range(2):
        hook = webhook(channel, refresh=attempt > 0)
        try:
            return api("POST", f"/webhooks/{hook['id']}/{hook['token']}", payload, auth=False, query=query)
        except ApiError as e:
            if e.status == 404 and attempt == 0:  # webhook deleted by hand, recreate
                continue
            raise


def post(sender, to, body, channel_key="exchanges", thread=None, title=None, stop=False):
    c, loc = cfg(), local()
    check_name(sender)
    if not sender.endswith("@" + loc["host"]):
        die(2, f"{sender} does not live on this host ({loc['host']})")
    body = body.strip()
    if stop:
        body = (body + "\nSTOP").strip()
    if not body:
        die(2, "empty message")
    if loc.get("strict"):
        for label, rx in GATE:
            if rx.search(body) or (title and rx.search(title)):
                die(3, f"refused by gate: matched pattern '{label}'. Agents on this host post meta only.")

    channel, turn = c["channels"][channel_key], 1
    if thread:
        history = api("GET", f"/channels/{thread}/messages", query="?limit=100")
        if any(is_stop(m.get("content", "")) for m in history):
            die(4, "thread was ended with STOP; start a new one if there is more to say")
        headers = [h for h in map(parse_header, history) if h]
        turn = 1 + max((h[2] for h in headers), default=0)  # split parts share a turn
        if to == "thread":
            names = {n for frm, dest, _, _ in headers for n in [frm, *dest.split(",")] if NAME_RE.match(n)}
            to = ",".join(sorted(names - {sender}))
            if not to:
                die(2, "--to thread found no other agents in this thread")
        channel = api("GET", f"/channels/{thread}")["parent_id"]
    elif to == "thread":
        die(2, "--to thread needs --thread")
    cap = loc.get("turn_cap", DEFAULT_TURN_CAP)
    if turn > cap:
        die(4, f"turn cap {cap} reached; tag @human in a new message or stop")

    name = (title or body.splitlines()[0])[:95]  # before the mention becomes <@id>
    tag_human = "@human" in body
    if tag_human:
        body = body.replace("@human", f"<@{c['owner_id']}>")
    parts = split_body(body, MAX_LEN - len(header(to, turn, (2, 2))))
    if len(parts) > MAX_PARTS:
        die(2, f"message needs {len(parts)} Discord messages, cap is {MAX_PARTS}. Say less.")

    query = "?wait=true"
    first_payload = {}
    if not thread and channel_key == "exchanges":
        if c["exchanges_forum"]:
            first_payload["thread_name"] = name
        else:
            thread = api("POST", f"/channels/{channel}/threads",
                         {"name": name, "type": 11, "auto_archive_duration": 10080})["id"]
    for i, part in enumerate(parts, 1):
        payload = {"content": header(to, turn, (i, len(parts)) if len(parts) > 1 else None) + part,
                   "username": sender,
                   **({"avatar_url": f"https://api.dicebear.com/9.x/bottts-neutral/png?seed={sender}&size=128"}
                      if loc.get("avatars", True) else {}),
                   "allowed_mentions": {"parse": [], "users": [c["owner_id"]] if tag_human else []},
                   **(first_payload if i == 1 else {})}
        q = query + (f"&thread_id={thread}" if thread else "")
        try:
            msg = send(channel, payload, q)
        except ApiError as e:
            if not (thread and e.payload.get("code") == 50083):  # thread archived
                raise
            api("PATCH", f"/channels/{thread}", {"archived": False})
            msg = send(channel, payload, q)
        thread = thread or msg["channel_id"]  # a forum post's first message creates the thread
    return thread or msg["channel_id"]


def header(to, turn, part=None):
    """Compact wire header, rendered as small grey subtext. The sender is the webhook name."""
    return f"-# → {to} · {turn}" + (f" · {part[0]}/{part[1]}" if part else "") + "\n"


def split_body(body, budget):
    """Split on paragraph breaks; hard-split any paragraph that alone exceeds the budget."""
    if len(body) <= budget:
        return [body]
    paras = []
    for p in body.split("\n\n"):
        while len(p) > budget:
            paras.append(p[:budget])
            p = p[budget:]
        paras.append(p)
    parts, cur = [], ""
    for p in paras:
        if cur and len(cur) + 2 + len(p) > budget:
            parts.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    return parts + [cur] if cur else parts


def cmd_post(a):
    for r in a.to.split(","):
        if r not in ("*", "roster", "human", "thread") and not r.startswith("*@"):
            check_name(r)
    body = a.message if a.message is not None else sys.stdin.read()
    print(post(a.name, a.to, body, a.channel, a.thread, a.title, a.stop))


def cmd_hello(a):
    loc = local()
    note = a.note or f"online on {loc['host']}"
    post(a.name, "roster", note, channel_key="roster")
    print("said hello in #roster")


# --------------------------------------------------------------------- inbox

def fmt(r):
    turn = f" | turn:{r['turn']}" if r["turn"] else ""
    head = f"--- thread:{r['thread']}{turn} | {r['from']} -> {r['to']}"
    if r["stop"]:
        head += " | STOP"
    return f"{head}\n{r['body'].strip()}"


def cmd_inbox(a):
    check_name(a.name)
    cur_file = HOME / "cursors" / a.name
    deadline = time.time() + a.wait if a.wait else None
    settled = False
    while True:
        cur = int(cur_file.read_text()) if cur_file.exists() else 0
        recs = []
        for f in (a.name, "_all"):
            p = HOME / "inbox" / f"{f}.jsonl"
            if p.exists():
                recs += [r for r in map(json.loads, p.read_text().splitlines())
                         if int(r["id"]) > cur and r["from"] != a.name]
        # A bare agent STOP ("thanks, closing") is not worth a wake; it still prints with
        # the next real message or on timeout. A STOP carrying a real answer does wake.
        wake = [r for r in recs if r["human"] or not r["stop"] or has_content(r["body"])]
        if wake and deadline and not settled:
            settled = True  # a split message may still be landing; read once more
            time.sleep(3)
            continue
        if wake or not deadline or time.time() >= deadline:
            break
        time.sleep(1)  # local file only, costs nothing
    if not recs:
        print("(no new messages)", file=sys.stderr)
        sys.exit(1)
    recs.sort(key=lambda r: int(r["id"]))
    print("\n\n".join(fmt(r) for r in recs))
    if not a.peek:
        cur_file.parent.mkdir(parents=True, exist_ok=True)
        cur_file.write_text(recs[-1]["id"])


# -------------------------------------------------------------------- daemon

class Daemon:
    def __init__(self):
        self.c, self.host = cfg(), local()["host"]
        self.state = load("state.json", {"last_id": "0", "seen": [], "threads": {}})
        self.seen = set(self.state["seen"])
        self.session = self.resume_url = self.seq = None
        self.acked = True

    def log(self, *parts):
        print(time.strftime("%Y-%m-%d %H:%M:%S"), *parts, flush=True)

    def targets(self, names, exclude=None):
        out = set()
        for n in names:
            if n in ("*", f"*@{self.host}"):
                out.add("_all")
            elif n.endswith("@" + self.host) and n != exclude:
                out.add(n)
        return out

    def handle(self, m):
        if m.get("guild_id", self.c["guild_id"]) != self.c["guild_id"] or m["id"] in self.seen:
            return
        self.seen.add(m["id"])
        content, ch = m.get("content", ""), m["channel_id"]
        hdr = parse_header(m)
        # Only the server owner's own account is human authority. A webhook can call itself anything.
        human = m["author"]["id"] == self.c["owner_id"] and not m.get("webhook_id")
        if hdr:
            frm, to, turn, body = hdr
            parts = self.state["threads"].setdefault(ch, [])
            for n in [frm, *to.split(",")]:
                if NAME_RE.match(n) and n not in parts:
                    parts.append(n)
            dest = self.targets(to.split(","), exclude=frm)
        elif human:
            frm, to, turn, body = "human", "", None, content
            direct = re.match(r"^@?([a-z0-9_-]+@[a-z0-9_-]+):?\s", content, re.I)  # phones capitalise
            if direct:
                to = direct.group(1).lower()
                dest = self.targets([to])
            elif ch in self.state["threads"]:
                to, dest = "thread", self.targets(self.state["threads"][ch])
            else:
                to, dest = "*", {"_all"}
        else:
            dest = set()
        if dest:
            rec = {"id": m["id"], "ts": m["timestamp"], "thread": ch, "from": frm, "to": to,
                   "turn": turn, "human": human, "stop": is_stop(content), "body": body}
            (HOME / "inbox").mkdir(parents=True, exist_ok=True)
            for d in dest:
                with open(HOME / "inbox" / f"{d}.jsonl", "a") as f:
                    f.write(json.dumps(rec) + "\n")
            self.log("delivered", m["id"], "from", frm, "to", ",".join(sorted(dest)))
        if int(m["id"]) > int(self.state["last_id"]):
            self.state["last_id"] = m["id"]
        self.state["seen"] = sorted(self.seen, key=int)[-1000:]
        self.seen = set(self.state["seen"])
        save("state.json", self.state)

    def backfill(self):
        """A fresh IDENTIFY does not replay what we missed while the laptop slept."""
        after, chans = self.state["last_id"], [self.c["channels"]["roster"], self.c["channels"]["human"]]
        if not self.c["exchanges_forum"]:
            chans.append(self.c["channels"]["exchanges"])
        chans += [t["id"] for t in api("GET", f"/guilds/{self.c['guild_id']}/threads/active")["threads"]]
        msgs = []
        for ch in chans:
            cur = after
            while True:
                batch = api("GET", f"/channels/{ch}/messages", query=f"?after={cur}&limit=100")
                msgs += batch
                if len(batch) < 100:
                    break
                cur = max(batch, key=lambda m: int(m["id"]))["id"]
        for m in sorted(msgs, key=lambda m: int(m["id"])):
            self.handle(m)
        self.log(f"backfill done, {len(msgs)} messages checked")

    async def heartbeat(self, ws, interval):
        await asyncio.sleep(interval * random.random())
        while True:
            if not self.acked:
                self.log("no heartbeat ACK, reconnecting")
                await ws.close(code=4000)
                return
            self.acked = False
            await ws.send(json.dumps({"op": 1, "d": self.seq}))
            await asyncio.sleep(interval)

    async def session_loop(self, ws):
        hello = json.loads(await ws.recv())
        self.acked = True
        hb = asyncio.create_task(self.heartbeat(ws, hello["d"]["heartbeat_interval"] / 1000))
        try:
            if self.session:
                await ws.send(json.dumps({"op": 6, "d": {"token": token(), "session_id": self.session, "seq": self.seq}}))
            else:
                await ws.send(json.dumps({"op": 2, "d": {"token": token(), "intents": INTENTS,
                                                         "properties": {"os": "macos", "browser": "agent-comms", "device": "agent-comms"}}}))
            async for raw in ws:
                p = json.loads(raw)
                if p.get("s") is not None:
                    self.seq = p["s"]
                op = p["op"]
                if op == 0:
                    if p["t"] == "READY":
                        self.session, self.resume_url = p["d"]["session_id"], p["d"]["resume_gateway_url"]
                        self.log("ready as", p["d"]["user"]["username"], "on host", self.host)
                        try:
                            await asyncio.to_thread(self.backfill)
                        except Exception as e:
                            self.log("backfill failed, staying live:", repr(e))
                    elif p["t"] == "RESUMED":
                        self.log("resumed")
                    elif p["t"] == "MESSAGE_CREATE":
                        try:
                            self.handle(p["d"])
                        except Exception as e:
                            self.log("skipped message", p["d"].get("id"), repr(e))
                elif op == 1:
                    await ws.send(json.dumps({"op": 1, "d": self.seq}))
                elif op == 7:
                    self.log("server asked to reconnect")
                    await ws.close(code=4000)  # non-1000 keeps the session resumable
                    return
                elif op == 9:
                    if not p["d"]:
                        self.session = self.resume_url = self.seq = None
                    await asyncio.sleep(1 + random.random() * 4)
                    await ws.close(code=4000)
                    return
                elif op == 11:
                    self.acked = True
        finally:
            hb.cancel()

    async def run(self):
        import websockets

        gateway = (await asyncio.to_thread(api, "GET", "/gateway/bot"))["url"]
        backoff = 1
        while True:
            try:
                async with websockets.connect((self.resume_url or gateway) + "/?v=10&encoding=json",
                                              max_size=None) as ws:
                    await self.session_loop(ws)
                backoff = 1
            except websockets.ConnectionClosed as e:
                code = e.rcvd.code if e.rcvd else None
                if code in FATAL_CLOSE:
                    # Exit 0 so launchd (KeepAlive on failure only) does not burn identifies.
                    self.log(f"fatal close {code}: {FATAL_CLOSE[code]}")
                    sys.exit(0)
                if code in (4007, 4009):
                    self.session = self.resume_url = self.seq = None
                self.log("connection closed", code)
            except Exception as e:
                # Never crash out: launchd restarts would each IDENTIFY, and >1000/day resets the token.
                self.log("error", repr(e))
            await asyncio.sleep(backoff + random.random())
            backoff = min(backoff * 2, 60)


def cmd_daemon(a):
    asyncio.run(Daemon().run())


PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{uv}</string><string>run</string><string>--quiet</string><string>--script</string><string>{script}</string><string>daemon</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def cmd_install_daemon(a):
    local()
    label = "nl.itsrene.agent-comms"
    plist = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    uv = shutil.which("uv") or die(1, "uv not on PATH")
    # The plugin cache path changes on every plugin update, so run from a stable copy.
    app = HOME / "app"
    app.mkdir(parents=True, exist_ok=True)
    if REPO != app:
        shutil.copy2(REPO / "agent_comms.py", app / "agent_comms.py")
        shutil.copy2(REPO / "commands" / "discord.md", app / "discord.md")
    # Pre-0.4.0 installs kept config.json in the app copy; move it to its new home.
    if not (HOME / "config.json").exists() and (app / "config.json").exists():
        shutil.copy2(app / "config.json", HOME / "config.json")
    # Plugin commands are always namespaced (/agent-comms:discord); a user command gives plain /discord.
    if (app / "discord.md").exists():
        cmd = Path.home() / ".claude/commands/discord.md"
        cmd.parent.mkdir(parents=True, exist_ok=True)
        cmd.unlink(missing_ok=True)
        cmd.symlink_to(app / "discord.md")
    (app / "agent_comms.py").chmod(0o755)
    bin_link = Path.home() / ".local/bin/agent-comms"
    bin_link.parent.mkdir(parents=True, exist_ok=True)
    bin_link.unlink(missing_ok=True)
    bin_link.symlink_to(app / "agent_comms.py")
    plist.write_text(PLIST.format(label=label, uv=uv, script=app / "agent_comms.py", log=HOME / "daemon.log"))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(plist)], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
    print(f"daemon running under launchd ({label}); log: {HOME / 'daemon.log'}")


def main():
    p = argparse.ArgumentParser(prog="agent-comms", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    s = sub.add_parser("init")
    s.add_argument("--host", required=True)
    s.add_argument("--strict", action="store_true", help="enable the data gate (work machines)")
    s.add_argument("--turn-cap", type=int, default=DEFAULT_TURN_CAP)
    s.add_argument("--no-avatars", action="store_true", help="skip the dicebear.com avatar URLs")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("post")
    s.add_argument("--as", dest="name", required=True)
    s.add_argument("--to", required=True, help="name, comma list, * or *@host")
    s.add_argument("--thread")
    s.add_argument("--title")
    s.add_argument("--channel", choices=["exchanges", "human", "roster"], default="exchanges")
    s.add_argument("--stop", action="store_true", help="end the thread")
    s.add_argument("message", nargs="?", help="omit to read stdin")
    s.set_defaults(fn=cmd_post)
    s = sub.add_parser("inbox")
    s.add_argument("--as", dest="name", required=True)
    s.add_argument("--wait", type=int, default=0, help="block up to N seconds for a message")
    s.add_argument("--peek", action="store_true", help="do not advance the cursor")
    s.set_defaults(fn=cmd_inbox)
    s = sub.add_parser("hello")
    s.add_argument("--as", dest="name", required=True)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_hello)
    sub.add_parser("daemon").set_defaults(fn=cmd_daemon)
    sub.add_parser("install-daemon").set_defaults(fn=cmd_install_daemon)
    a = p.parse_args()
    try:
        a.fn(a)
    except ApiError as e:
        die(1, f"Discord said no: {e}")


if __name__ == "__main__":
    main()
