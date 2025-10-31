import discord
from discord.ext import tasks, commands
import cloudscraper
from datetime import datetime, timedelta, timezone
import asyncio

TOKEN = "MTQzMzc1MzcyNDQ3NTQxMjQ4MA.GzUhbv.SDrl7v_lUD4qWpyNR67K8qNayHEjGDSo3HFBfQ"
CHANNEL_ID = 1385559078801244180  # <-- Replace with your channel ID
API_URL = "https://api.garmoth.com/api/events?region=asia&lang=us"

UTC_PLUS_8 = timezone(timedelta(hours=8))
scraper = cloudscraper.create_scraper()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def to_kst(iso_str):
    try:
        utc_time = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        local_time = utc_time.replace(tzinfo=timezone.utc).astimezone(UTC_PLUS_8)
        return local_time.strftime("%Y-%m-%d %H:%M UTC+8")
    except Exception:
        return "No date"

def to_kst_fixed_end(iso_str):
    try:
        utc_time = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        local_time = utc_time.replace(tzinfo=timezone.utc).astimezone(UTC_PLUS_8)
        return local_time
    except Exception:
        return None

def days_left_str(end_time):
    if not end_time:
        return "Unknown"
    now = datetime.now(UTC_PLUS_8)
    delta = end_time - now
    days_left = delta.total_seconds() / 86400
    if days_left <= 0:
        return "Ended"
    elif days_left < 1:
        return "Ends today"
    else:
        return f"{int(days_left)} days left"

@tasks.loop(hours=24)
async def update_events():
    """Fetch events and post updates once per day."""
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("⚠️ Channel not found!")
        return

    resp = scraper.get(API_URL)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch API ({resp.status_code})")
        return

    events = resp.json()
    await channel.purge(limit=50)  # clear old posts

    count = 0
    for e in events:
        end_at = e.get("end_at")
        if not end_at or end_at in ["null", "None", None]:
            continue

        end_time = to_kst_fixed_end(end_at)
        if not end_time or end_time.strftime("%Y-%m-%d") == "2025-12-31":
            continue

        embed = discord.Embed(
            description=(
                f"🗓️ **{e['title']}**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📅 **Start:** {to_kst(e.get('created_at', ''))}\n"
                f"⏰ **End:** {end_time.strftime('%Y-%m-%d %H:%M UTC+8')}\n"
                f"⏳ **{days_left_str(end_time)}**\n"
                f"🌏 **Region:** {e['region'].upper()}\n"
                f"[🔗 View Details]({e['link']})"
            ),
            color=0x00b0f4
        )
        embed.set_thumbnail(url=e["img"])
        await channel.send(embed=embed)
        count += 1
        await asyncio.sleep(1)

    print(f"✅ Posted {count} events!")

@update_events.before_loop
async def before_update():
    now = datetime.now(UTC_PLUS_8)
    next_midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    wait_seconds = (next_midnight - now).total_seconds()
    print(f"🕒 Waiting {wait_seconds/3600:.1f} hours until next update...")
    await asyncio.sleep(wait_seconds)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    update_events.start()  # Start the midnight loop

bot.run(TOKEN)
