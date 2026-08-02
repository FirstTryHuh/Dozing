"""
Web version of the nightly check-in script.

Instead of running as a standalone script, this exposes an HTTP endpoint
(/tick) that a web-based cron service (e.g. cron-job.org) calls every
15 minutes. Each call runs the same state-machine logic as before.

Deploy this on Render as a free Web Service, then point a free web cron
service at:  https://<your-app>.onrender.com/tick
scheduled every 15 minutes.

Send /stop to the bot at any time to force state to "done" for the night.
"""

import json
import os
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask

VN_TZ = timezone(timedelta(hours=7))

def local_now():
    return datetime.now(VN_TZ)

app = Flask(__name__)

BOT_TOKEN = "8805177798:AAEABDJ3w7HFjaIjwFIxgdKSbpyU0UKxvmE"
YOUR_CHAT_ID = 8437042992
HER_CHAT_ID = 8437042992  # TEST MODE: using your own chat ID for now

WINDOW_MINUTES = 1
START_HOUR = -1   # 10 PM
END_HOUR = 25      # window closes at 6 AM

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(chat_id, text):
    requests.post(f"{API_URL}/sendMessage", data={"chat_id": chat_id, "text": text})


def get_updates(offset=None):
    params = {"timeout": 5}
    if offset:
        params["offset"] = offset
    resp = requests.get(f"{API_URL}/getUpdates", params=params, timeout=10)
    return resp.json().get("result", [])


def get_pinned_state_message():
    """Returns (message_id, state_dict) from the pinned message in YOUR_CHAT_ID, or (None, None)."""
    resp = requests.get(f"{API_URL}/getChat", params={"chat_id": YOUR_CHAT_ID}, timeout=10)
    data = resp.json()
    pinned = data.get("result", {}).get("pinned_message")
    if not pinned:
        return None, None
    text = pinned.get("text", "")
    if not text.startswith("STATE::"):
        return None, None
    try:
        state = json.loads(text[len("STATE::"):])
        return pinned["message_id"], state
    except (json.JSONDecodeError, KeyError):
        return None, None


def load_state():
    _, state = get_pinned_state_message()
    if state is None:
        return {"status": "idle", "ping_time": None, "last_update_id": None, "date": None}
    return state


def save_state(state):
    text = "STATE::" + json.dumps(state)
    message_id, _ = get_pinned_state_message()

    if message_id is None:
        # No pinned state message yet — create and pin one
        resp = requests.post(f"{API_URL}/sendMessage", data={"chat_id": YOUR_CHAT_ID, "text": text})
        new_id = resp.json()["result"]["message_id"]
        requests.post(f"{API_URL}/pinChatMessage", data={
            "chat_id": YOUR_CHAT_ID, "message_id": new_id, "disable_notification": True
        })
    else:
        requests.post(f"{API_URL}/editMessageText", data={
            "chat_id": YOUR_CHAT_ID, "message_id": message_id, "text": text
        })


def in_active_window(now):
    return now.hour >= START_HOUR or now.hour < END_HOUR


def check_for_reply_or_stop(last_update_id):
    updates = get_updates(offset=last_update_id + 1 if last_update_id else None)
    result = "none"
    for u in updates:
        last_update_id = u["update_id"]
        msg = u.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip().lower()

        if chat_id == YOUR_CHAT_ID:
            if text == "/stop":
                result = "stop"
            else:
                result = "replied"
    return result, last_update_id


def run_tick():
    now = local_now()
    today_str = now.strftime("%Y-%m-%d")

    if not in_active_window(now):
        return "Outside active window, nothing to do."

    state = load_state()

    if state.get("date") != today_str and now.hour == START_HOUR:
        state = {"status": "idle", "ping_time": None, "last_update_id": state.get("last_update_id"), "date": today_str}
        save_state(state)

    if state["status"] == "done":
        return "Already resolved for tonight, doing nothing."

    if state["status"] == "idle":
        send_message(YOUR_CHAT_ID, "Còn thức không? Nhắn gì đi!")
        state["status"] = "waiting"
        state["ping_time"] = now.isoformat()
        state["date"] = today_str
        save_state(state)
        return "Ping sent, now waiting."

    if state["status"] == "waiting":
        result, new_update_id = check_for_reply_or_stop(state.get("last_update_id"))
        state["last_update_id"] = new_update_id

        if result == "replied":
            state["status"] = "idle"
            save_state(state)
            return run_tick()

        if result == "stop":
            state["status"] = "done"
            save_state(state)
            send_message(YOUR_CHAT_ID, "Stopped for tonight. Sleep well.")
            return "Stopped by user."

        ping_time = datetime.fromisoformat(state["ping_time"])
        elapsed_minutes = (now - ping_time).total_seconds() / 60

        if elapsed_minutes >= WINDOW_MINUTES:
            send_message(HER_CHAT_ID, "Môm iuuuu uii:3")
            send_message(HER_CHAT_ID, "Bé ngụ quên gồi bé xin lỗiii:(((")
            send_message(HER_CHAT_ID, "Môm iuuuu tha lỗi choa bé nhóooo:(((")
            send_message(HER_CHAT_ID, "Hoi môm đi ngụ đi đừn đựi bé nhóo:3")
            send_message(YOUR_CHAT_ID, "Mày ngủ quên rồi sáng mai no đòn >:3")
            state["status"] = "done"
            save_state(state)
            return "No reply in time, alert sent, done for tonight."
        else:
            save_state(state)
            return "Still within window, waiting."


@app.route("/tick")
def tick():
    result = run_tick()
    return {"result": result}


@app.route("/")
def home():
    return {"status": "check-in bot is running"}

@app.route("/flip")
def flip():
    state = load_state()
    if state["status"]=="done":
        state["status"] = "idle"
    else:
        state["status"] = "done"
    save_state(state)
    return {"result": state["status"]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

