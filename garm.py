import requests
import cloudscraper
from datetime import datetime, timedelta, timezone
import os
import json
import time

WEBHOOK_URL = "https://discord.com/api/webhooks/1433715302935564380/3w2b9mA-8yEgAQbYVRGjNmpoPu3iQdylGaRZx6Q9mPjD-GR7eyj7sCvOCByeO5XKoY8i"
API_URL = "https://api.garmoth.com/api/events?region=asia&lang=us"
MESSAGE_FILE = "posted_messages.json"  # store all message IDs

UTC_PLUS_8 = timezone(timedelta(hours=8))

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

def delete_previous_messages():
    """Delete all previously posted messages from file."""
    if not os.path.exists(MESSAGE_FILE):
        return

    try:
        with open(MESSAGE_FILE, "r") as f:
            message_ids = json.load(f)

        if not message_ids:
            return

        for msg_id in message_ids:
            delete_url = f"{WEBHOOK_URL}/messages/{msg_id}"
            r = requests.delete(delete_url)
            if r.status_code == 204:
                print(f"🗑️ Deleted message {msg_id}")
            else:
                print(f"⚠️ Failed to delete message {msg_id} ({r.status_code})")
            time.sleep(0.5)  # prevent rate limits

        os.remove(MESSAGE_FILE)
    except Exception as e:
        print("⚠️ Could not delete previous messages:", e)

def save_message_id(msg_id):
    """Append message ID to file."""
    data = []
    if os.path.exists(MESSAGE_FILE):
        with open(MESSAGE_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []

    data.append(msg_id)
    with open(MESSAGE_FILE, "w") as f:
        json.dump(data, f)

# ==== MAIN ====

scraper = cloudscraper.create_scraper()
resp = scraper.get(API_URL)

if resp.status_code == 200:
    delete_previous_messages()  # delete old posts before sending new ones

    events = resp.json()
    skipped = []
    count = 0

    for e in events:
        end_at = e.get("end_at")

        # Skip events without valid end date
        if not end_at or end_at in ["null", "None", None]:
            skipped.append(e["title"])
            continue

        try:
            end_time = to_kst_fixed_end(end_at)
            if not end_time:
                skipped.append(e["title"])
                continue
            if end_time.strftime("%Y-%m-%d") == "2025-12-31":
                skipped.append(e["title"])
                continue
        except Exception:
            skipped.append(e["title"])
            continue

        # Pill-style embed like Garmoth
        days_text = days_left_str(end_time)
        start_date = to_kst(e.get("created_at", ""))
        end_date = end_time.strftime("%Y-%m-%d %H:%M UTC+8")

        # Garmoth-like pill summary
        description = (
            f"🗓️ **{e['title']}**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📅 **Start:** {start_date}\n"
            f"⏰ **End:** {end_date}\n"
            f"⏳ **{days_text}**\n"
            f"🌏 **Region:** {e['region'].upper()}\n"
            f"[🔗 View Details]({e['link']})"
        )

        embed = {
            "description": description,
            "color": 0x00b0f4,
            "thumbnail": {"url": e["img"]}  # smaller thumbnail like Garmoth pill
        }

        r = requests.post(WEBHOOK_URL + "?wait=true", json={"embeds": [embed]})

        if r.status_code in [200, 204]:
            try:
                msg_data = r.json()
                if "id" in msg_data:
                    save_message_id(msg_data["id"])
                    count += 1
            except Exception:
                print("⚠️ Could not save message ID (no JSON response).")
        else:
            print(f"❌ Failed to post {e['title']} ({r.status_code})")

        time.sleep(1)  # prevent Discord rate limits

    print(f"✅ Sent {count} pill-style events to Discord!")
    if skipped:
        print("⏭️ Skipped:", ", ".join(skipped))

else:
    print("❌ Failed to get data:", resp.status_code)
