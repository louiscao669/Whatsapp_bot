from flask import Flask

from app.api import api_blueprint
from app.config import configure_logging, load_configurations
from app.spa_views import spa_blueprint


def create_app():
    app = Flask(__name__)
    load_configurations(app)
    configure_logging()
    app.register_blueprint(api_blueprint)
    app.register_blueprint(spa_blueprint)
    return app
