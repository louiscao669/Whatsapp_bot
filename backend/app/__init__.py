from flask import Flask
from app.config import load_configurations, configure_logging
from .admin_views import admin_blueprint
from .api import api_blueprint
from app.services.reminder_service import start_reminder_scheduler
from .views import webhook_blueprint


def create_app():
    app = Flask(__name__)

    # Load configurations and logging settings
    load_configurations(app)
    configure_logging()

    # Import and register blueprints, if any
    app.register_blueprint(webhook_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(admin_blueprint)
    start_reminder_scheduler(app)

    return app
