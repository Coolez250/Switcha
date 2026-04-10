"""
TrafficSwitch License Bot (with HWID locking)
──────────────────────────────────────────────
Requirements:
    pip install discord.py aiohttp

Setup:
    Set your bot token as an environment variable:
        Windows:  set TRAFFICSWITCH_BOT_TOKEN=your_token_here
        Linux:    export TRAFFICSWITCH_BOT_TOKEN=your_token_here

Commands (in your private keys channel):
  !addkey XXXX-XXXX-XXXX-XXXX   — add a key (no HWID locked yet)
  !removekey XXXX-XXXX-XXXX-XXXX — revoke a key
  !listkeys                      — see all active keys
  !genkey                        — generate a random key
  !resetkey XXXX-XXXX-XXXX-XXXX  — reset the HWID for a key
  !checkkey XXXX-XXXX-XXXX-XXXX  — check key status and HWID
"""

import discord
import asyncio
import json
import os
from aiohttp import web
from discord.ext import commands

# ── CONFIG ────────────────────────────────────────────────────────
# FIX: Token now loaded from environment variable — never hardcode it.
# Go to discord.com/developers, regenerate your token, then set the env var.
BOT_TOKEN       = os.environ.get("TRAFFICSWITCH_BOT_TOKEN", "")
KEYS_CHANNEL_ID = 1491887016944861286
HOST            = "0.0.0.0"
PORT            = 5000
# FIX: Use paths relative to this script so it works on any machine
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, "keys.txt")
HWID_FILE = os.path.join(BASE_DIR, "hwids.json")
# ─────────────────────────────────────────────────────────────────

if not BOT_TOKEN:
    raise RuntimeError(
        "Bot token not set. Run: set TRAFFICSWITCH_BOT_TOKEN=your_token_here"
    )

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def load_keys() -> set:
    if not os.path.exists(KEYS_FILE):
        return set()
    with open(KEYS_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}


def save_keys(keys: set):
    with open(KEYS_FILE, "w") as f:
        f.write("\n".join(sorted(keys)))


def load_hwids() -> dict:
    if not os.path.exists(HWID_FILE):
        return {}
    with open(HWID_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {}


def save_hwids(hwids: dict):
    with open(HWID_FILE, "w") as f:
        json.dump(hwids, f, indent=2)


# ── HTTP validation endpoint ──────────────────────────────────────
async def handle_validate(request: web.Request) -> web.Response:
    try:
        data  = await request.json()
        key   = str(data.get("key",  "")).strip()
        hwid  = str(data.get("hwid", "")).strip()

        keys  = load_keys()
        hwids = load_hwids()

        if key not in keys:
            return web.Response(
                text=json.dumps({"valid": False, "reason": "invalid"}),
                status=403, content_type="application/json")

        # First time this key is used — lock it to this HWID
        if key not in hwids:
            hwids[key] = hwid
            save_hwids(hwids)
            print(f"[hwid] key {key} locked to HWID {hwid}")

        # HWID mismatch
        if hwids[key] != hwid:
            print(f"[hwid] mismatch for key {key}: expected {hwids[key]}, got {hwid}")
            return web.Response(
                text=json.dumps({"valid": False, "reason": "hwid"}),
                status=403, content_type="application/json")

        return web.Response(
            text=json.dumps({"valid": True}),
            status=200, content_type="application/json")

    except Exception as e:
        return web.Response(
            text=json.dumps({"valid": False, "error": str(e)}),
            status=400, content_type="application/json")


async def start_http():
    app = web.Application()
    app.router.add_post("/validate", handle_validate)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    print(f"[key server] listening on {HOST}:{PORT}")


# ── Discord commands ──────────────────────────────────────────────
def is_keys_channel(ctx):
    return ctx.channel.id == KEYS_CHANNEL_ID


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f"[bot] logged in as {bot.user}")
    await start_http()


@bot.command(name="addkey")
@commands.check(is_keys_channel)
async def add_key(ctx, key: str = None):
    if key is None:
        await ctx.send("❌ usage: `!addkey XXXX-XXXX-XXXX-XXXX`"); return
    keys = load_keys()
    if key in keys:
        await ctx.send(f"⚠️ key `{key}` already exists"); return
    keys.add(key)
    save_keys(keys)
    await ctx.send(f"✅ key added: `{key}`")


@bot.command(name="removekey")
@commands.check(is_keys_channel)
async def remove_key(ctx, key: str = None):
    if key is None:
        await ctx.send("❌ usage: `!removekey XXXX-XXXX-XXXX-XXXX`"); return
    keys = load_keys()
    if key not in keys:
        await ctx.send(f"⚠️ key `{key}` not found"); return
    keys.discard(key)
    save_keys(keys)
    # also remove HWID binding
    hwids = load_hwids()
    if key in hwids:
        del hwids[key]
        save_hwids(hwids)
    await ctx.send(f"🗑️ key removed: `{key}`")


@bot.command(name="listkeys")
@commands.check(is_keys_channel)
async def list_keys(ctx):
    keys  = load_keys()
    hwids = load_hwids()
    if not keys:
        await ctx.send("📭 no active keys"); return
    lines = []
    for k in sorted(keys):
        hwid = hwids.get(k, "not locked yet")
        lines.append(f"• `{k}` — HWID: `{hwid}`")
    await ctx.send(f"🔑 **active keys ({len(keys)}):**\n" + "\n".join(lines))


@bot.command(name="genkey")
@commands.check(is_keys_channel)
async def gen_key(ctx):
    import random, string
    def seg(): return "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    key = "-".join(seg() for _ in range(4))
    keys = load_keys(); keys.add(key); save_keys(keys)
    await ctx.send(f"✨ generated and added key: `{key}`")


@bot.command(name="resetkey")
@commands.check(is_keys_channel)
async def reset_key(ctx, key: str = None):
    if key is None:
        await ctx.send("❌ usage: `!resetkey XXXX-XXXX-XXXX-XXXX`"); return
    keys = load_keys()
    if key not in keys:
        await ctx.send(f"⚠️ key `{key}` not found"); return
    hwids = load_hwids()
    if key in hwids:
        del hwids[key]
        save_hwids(hwids)
        await ctx.send(f"🔄 HWID reset for key `{key}` — next login will lock to new PC")
    else:
        await ctx.send(f"ℹ️ key `{key}` had no HWID locked")


@bot.command(name="checkkey")
@commands.check(is_keys_channel)
async def check_key(ctx, key: str = None):
    if key is None:
        await ctx.send("❌ usage: `!checkkey XXXX-XXXX-XXXX-XXXX`"); return
    keys  = load_keys()
    hwids = load_hwids()
    if key not in keys:
        await ctx.send(f"❌ key `{key}` does not exist"); return
    hwid = hwids.get(key, "not locked yet")
    await ctx.send(f"🔍 key `{key}` — HWID: `{hwid}`")


@add_key.error
@remove_key.error
@list_keys.error
@gen_key.error
@reset_key.error
@check_key.error
async def cmd_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ wrong channel")


bot.run(BOT_TOKEN)
