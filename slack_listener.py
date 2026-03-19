"""Slack listener — forwards messages from #jarvis to jarvis ask and replies."""

import os
import subprocess
import sys
import time
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

if not BOT_TOKEN or not APP_TOKEN:
    logger.error("SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set.")
    sys.exit(1)


JARVIS_EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Scripts", "jarvis.exe")


def ask_jarvis(question: str) -> str:
    """Call jarvis ask and return the response text."""
    import re
    # Strip Slack mention tags like <@U0ANC3QJRK2>
    question = re.sub(r"<@[A-Z0-9]+>", "", question).strip()
    if not question:
        return ""
    try:
        result = subprocess.run(
            [JARVIS_EXE, "ask", question],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        logger.info("jarvis stdout: %s", result.stdout[:200])
        logger.info("jarvis stderr: %s", result.stderr[:200])
        return (result.stdout or "").strip() or "(no response)"
    except subprocess.TimeoutExpired:
        return "Request timed out."
    except Exception as exc:
        logger.exception("jarvis ask failed")
        return f"Error: {exc}"


def send_slack_message(channel: str, text: str) -> None:
    """Post a message to a Slack channel via Web API."""
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
        if req.type == "events_api":
            event = req.payload.get("event", {})
            # Ignore bot's own messages and subtypes (edits, joins, etc.)
            if (
                event.get("type") == "message"
                and "subtype" not in event
                and event.get("user") != bot_id
            ):
                text = event.get("text", "").strip()
                channel = event.get("channel", "")
                logger.info("Received: %s", text)
                if text:
                    response = ask_jarvis(text)
                    logger.info("Responding: %s", response[:80])
                    send_slack_message(channel, response)
            client_obj.send_socket_mode_response(
                SocketModeResponse(envelope_id=req.envelope_id)
            )

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
