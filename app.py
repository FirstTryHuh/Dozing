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
from datetime import datetime
from flask import Flask

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


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"status": "idle", "ping_time": None, "last_update_id": None, "date": None}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


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
    now = datetime.now()
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
        send_message(YOUR_CHAT_ID, "You awake? Reply anything within 15 min. (or /stop to cancel tonight)")
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
            return "Reply received, back to idle."

        if result == "stop":
            state["status"] = "done"
            save_state(state)
            send_message(YOUR_CHAT_ID, "Stopped for tonight. Sleep well.")
            return "Stopped by user."

        ping_time = datetime.fromisoformat(state["ping_time"])
        elapsed_minutes = (now - ping_time).total_seconds() / 60

        if elapsed_minutes >= WINDOW_MINUTES:
            send_message(HER_CHAT_ID, "Hey — he didn't check in tonight, might've dozed off 💤")
            send_message(YOUR_CHAT_ID, "No reply detected — alert sent. Stopping for tonight.")
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)