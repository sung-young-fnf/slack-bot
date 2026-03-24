import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from handlers.briefing import register_handlers

load_dotenv()

app = App(token=os.environ["SLACK_BOT_TOKEN"])

register_handlers(app)

if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("Slack Briefing Bot is running...")
    handler.start()
