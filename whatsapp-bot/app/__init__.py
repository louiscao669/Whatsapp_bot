from flask import Flask

from app.config import configure_logging, load_configurations
from app.services.reminders import start_reminder_scheduler
from app.webhook.routes import webhook_blueprint


def create_app():
    app = Flask(__name__)
    load_configurations(app)
    configure_logging()
    app.register_blueprint(webhook_blueprint)
    start_reminder_scheduler(app)
    return app
