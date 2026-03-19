"""Slack listener — forwards messages from #jarvis to OpenRouter and replies."""

import os
import re
import sys
import time
import threading
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("slack_listener.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

if not BOT_TOKEN or not APP_TOKEN:
    logger.error("SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set.")
    sys.exit(1)

if not OPENROUTER_API_KEY:
    logger.error("OPENROUTER_API_KEY must be set.")
    sys.exit(1)

# Deduplicate events by Slack message timestamp
_seen_ts: set = set()
_seen_lock = threading.Lock()


def already_seen(ts: str) -> bool:
    with _seen_lock:
        if ts in _seen_ts:
            return True
        _seen_ts.add(ts)
        # Keep set small — drop old entries beyond 500
        if len(_seen_ts) > 500:
            _seen_ts.pop()
        return False


def ask_openrouter(question: str) -> str:
    """Call OpenRouter directly — no engine health checks, fast response."""
    import httpx
    question = re.sub(r"<@[A-Z0-9]+>", "", question).strip()
    if not question:
        return ""
    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "x-ai/grok-4.1-fast",
                "messages": [{"role": "user", "content": question}],
            },
            timeout=30.0,
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.exception("OpenRouter call failed")
        return f"Error: {exc}"


def send_slack_message(channel: str, text: str) -> None:
    import httpx
    resp = httpx.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {BOT_TOKEN}", "Content-Type": "application/json"},
        json={"channel": channel, "text": text},
        timeout=10.0,
    )
    data = resp.json()
    if not data.get("ok"):
        logger.warning("Slack send error: %s", data.get("error"))


def process_message(text: str, channel: str) -> None:
    """Run in a thread so the socket ack is not blocked."""
    logger.info("Received: %s", text)
    response = ask_openrouter(text)
    if response:
        logger.info("Responding: %s", response[:80])
        send_slack_message(channel, response)


def main() -> None:
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web import WebClient

    bot_id = WebClient(token=BOT_TOKEN).auth_test().get("user_id", "")
    logger.info("Connected as bot user_id=%s", bot_id)

    client = SocketModeClient(
        app_token=APP_TOKEN,
        web_client=WebClient(token=BOT_TOKEN),
    )

    def handle(client_obj: SocketModeClient, req: SocketModeRequest) -> None:
        # Acknowledge immediately to prevent Slack retries
        client_obj.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id)
        )
        if req.type == "events_api":
            event = req.payload.get("event", {})
            if (
                event.get("type") == "message"
                and "subtype" not in event
                and event.get("user") != bot_id
            ):
                ts = event.get("ts", "")
                if ts and already_seen(ts):
                    logger.info("Duplicate event ts=%s, skipping", ts)
                    return
                text = event.get("text", "").strip()
                channel = event.get("channel", "")
                if text:
                    threading.Thread(
                        target=process_message, args=(text, channel), daemon=True
                    ).start()

    client.socket_mode_request_listeners.append(handle)
    client.connect()
    logger.info("Slack listener running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping.")
        client.disconnect()


if __name__ == "__main__":
    main()
