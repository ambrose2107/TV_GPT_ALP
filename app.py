from flask import Flask
from core.database import init_db
from core.logger import get_logger
from webhook.routes import webhook_bp
from dashboard.routes import dashboard_bp
import os

logger = get_logger(__name__)

def create_app():
    app = Flask(__name__,
        template_folder="dashboard/templates",
        static_folder="dashboard/static")
    app.secret_key = os.environ.get("APP_SECRET_KEY", "change-me-in-production")
    app.config["SESSION_TYPE"] = "filesystem"
    init_db()
    app.register_blueprint(webhook_bp)
    app.register_blueprint(dashboard_bp)
    logger.info("App created.")
    return app
