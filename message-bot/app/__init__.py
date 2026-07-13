from flask import Flask

from app.config import configure_logging, load_configurations
from app.engagement.outbox import start_outbox_poller
from app.engagement.reminders import start_reminder_scheduler
from app.providers.whatsapp.routes import webhook_blueprint


def create_app():
    app = Flask(__name__)
    load_configurations(app)
    configure_logging()
    app.register_blueprint(webhook_blueprint)
    start_reminder_scheduler(app)
    start_outbox_poller()
    return app
