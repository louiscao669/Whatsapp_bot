from flask import Flask

from backend.admin.api import api_blueprint
from backend.shared.config import configure_logging, load_configurations
from backend.pilot.routes import pilot_blueprint
from backend.admin.spa_views import spa_blueprint
from backend.user_dashboard.routes import user_dashboard_blueprint


def create_app():
    app = Flask(__name__)
    load_configurations(app)
    configure_logging()
    app.register_blueprint(api_blueprint)
    app.register_blueprint(user_dashboard_blueprint)
    app.register_blueprint(pilot_blueprint)
    app.register_blueprint(spa_blueprint)
    return app
