import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config, INSTANCE_FOLDER, UPLOAD_FOLDER

db = SQLAlchemy()

def format_currency(value):
    if value is None:
        return ""
    # Format with space as thousand separator and comma as decimal separator
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")

def create_app(config_class=Config):
    """Application Factory-функция"""

    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(INSTANCE_FOLDER, exist_ok=True)

    db.init_app(app)

    # Register custom Jinja2 filter
    app.jinja_env.filters['currency'] = format_currency

    from bokforing_app.main.routes import bp as main_bp
    app.register_blueprint(main_bp)

    from bokforing_app.api.routes import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    with app.app_context():
        db.create_all()

    return app