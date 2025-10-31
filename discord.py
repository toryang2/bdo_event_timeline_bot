import discord
from discord.ext import tasks, commands
import cloudscraper
from datetime import datetime, timedelta, timezone
import os
import json
import asyncio

# Bot configuration
BOT_TOKEN = "MTQzMzc1MzcyNDQ3NTQxMjQ4MA.GzUhbv.SDrl7v_lUD4qWpyNR67K8qNayHEjGDSo3HFBfQ"  # Replace with your bot token
API_URL = "https://api.garmoth.com/api/events?region=asia&lang=us"
MESSAGE_FILE = "posted_messages.json"
CHANNEL_FILE = "tracking_channels.json"  # Stores channels where bot should post

UTC_PLUS_8 = timezone(timedelta(hours=8))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def to_kst(iso_str):
    """Convert UTC → UTC+8 (no adjustment)."""
    try:
        utc_time = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        local_time = utc_time.replace(tzinfo=timezone.utc).astimezone(UTC_PLUS_8)
        return local_time.strftime("%Y-%m-%d %H:%M UTC+8")
    except Exception:
        return "No date"

def to_kst_fixed_end(iso_str):
    """Convert UTC → UTC+8 and return as datetime object."""
    try:
        utc_time = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        local_time = utc_time.replace(tzinfo=timezone.utc).astimezone(UTC_PLUS_8)
        return local_time
    except Exception:
        return None

def days_left_str(end_time):
    """Calculate days remaining until the event ends."""
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

def load_tracking_channels():
    """Load channels where bot should post events."""
    if os.path.exists(CHANNEL_FILE):
        with open(CHANNEL_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tracking_channels(channels):
    """Save tracking channels to file."""
    with open(CHANNEL_FILE, "w") as f:
        json.dump(channels, f)

def load_message_ids():
    """Load stored message IDs."""
    if os.path.exists(MESSAGE_FILE):
        with open(MESSAGE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_message_ids(message_ids):
    """Save message IDs to file."""
    with open(MESSAGE_FILE, "w") as f:
        json.dump(message_ids, f)

async def delete_previous_messages():
    """Delete all previously posted messages."""
    message_ids = load_message_ids()
    
    for channel_id, msg_id in message_ids.items():
        try:
            channel = bot.get_channel(int(channel_id))
            if channel:
                msg = await channel.fetch_message(int(msg_id))
                await msg.delete()
                print(f"🗑️ Deleted message {msg_id} from channel {channel_id}")
        except Exception as e:
            print(f"⚠️ Could not delete message {msg_id}: {e}")
        await asyncio.sleep(0.5)
    
    # Clear message IDs
    save_message_ids({})

async def post_events():
    """Post events to all tracking channels."""
    scraper = cloudscraper.create_scraper()
    resp = scraper.get(API_URL)
    
    if resp.status_code != 200:
        print("❌ Failed to fetch events from API")
        return
    
    events = resp.json()
    tracking_channels = load_tracking_channels()
    
    if not tracking_channels:
        print("ℹ️ No channels set for event tracking")
        return
    
    # Delete old messages first
    await delete_previous_messages()
    
    message_ids = {}
    
    for channel_id in tracking_channels.keys():
        channel = bot.get_channel(int(channel_id))
        if not channel:
            print(f"⚠️ Channel {channel_id} not found")
            continue
            
        count = 0
        for e in events:
            end_at = e.get("end_at")
            
            # Skip events without valid end date
            if not end_at or end_at in ["null", "None", None]:
                continue
                
            try:
                end_time = to_kst_fixed_end(end_at)
                if not end_time:
                    continue
                if end_time.strftime("%Y-%m-%d") == "2025-12-31":
                    continue
            except Exception:
                continue
            
            # Create embed
            days_text = days_left_str(end_time)
            start_date = to_kst(e.get("created_at", ""))
            end_date = end_time.strftime("%Y-%m-%d %H:%M UTC+8")
            
            description = (
                f"🗓️ **{e['title']}**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📅 **Start:** {start_date}\n"
                f"⏰ **End:** {end_date}\n"
                f"⏳ **{days_text}**\n"
                f"🌏 **Region:** {e['region'].upper()}\n"
                f"[🔗 View Details]({e['link']})"
            )
            
            embed = discord.Embed(
                description=description,
                color=0x00b0f4
            )
            embed.set_thumbnail(url=e["img"])
            
            try:
                msg = await channel.send(embed=embed)
                message_ids[str(channel.id)] = str(msg.id)
                count += 1
                await asyncio.sleep(1)  # Rate limiting
            except Exception as e:
                print(f"❌ Failed to post in {channel.name}: {e}")
        
        print(f"✅ Posted {count} events to #{channel.name}")
    
    save_message_ids(message_ids)

@bot.event
async def on_ready():
    print(f'✅ Bot is online as {bot.user.name}')
    print(f'📊 Connected to {len(bot.guilds)} servers')
    
    # Start the background task
    if not post_events_task.is_running():
        post_events_task.start()

@bot.command()
async def track(ctx):
    """Set current channel for event tracking"""
    channels = load_tracking_channels()
    channels[str(ctx.channel.id)] = True
    save_tracking_channels(channels)
    
    embed = discord.Embed(
        title="✅ Event Tracking Enabled",
        description="This channel will now receive Garmoth event updates.",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command()
async def untrack(ctx):
    """Remove current channel from event tracking"""
    channels = load_tracking_channels()
    if str(ctx.channel.id) in channels:
        del channels[str(ctx.channel.id)]
        save_tracking_channels(channels)
    
    embed = discord.Embed(
        title="✅ Event Tracking Disabled",
        description="This channel will no longer receive Garmoth event updates.",
        color=0xff0000
    )
    await ctx.send(embed=embed)

@bot.command()
async def update(ctx):
    """Manually trigger event update"""
    await ctx.send("🔄 Updating events...")
    await post_events()
    await ctx.send("✅ Events updated!")

@bot.command()
async def info(ctx):
    """Show bot information"""
    channels = load_tracking_channels()
    embed = discord.Embed(
        title="Garmoth Event Tracker",
        description="Automatically posts BDO events from Garmoth.com",
        color=0x00b0f4
    )
    embed.add_field(
        name="Tracking Channels",
        value=f"{len(channels)} channel(s)" if channels else "No channels set",
        inline=False
    )
    embed.add_field(
        name="Commands",
        value="`!track` - Enable tracking in this channel\n`!untrack` - Disable tracking\n`!update` - Manual update\n`!info` - This info",
        inline=False
    )
    await ctx.send(embed=embed)

@tasks.loop(hours=1)
async def post_events_task():
    """Background task to update events every hour"""
    await post_events()

# Run the bot
if __name__ == "__main__":
    bot.run(BOT_TOKEN)