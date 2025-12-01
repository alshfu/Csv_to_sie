import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config, INSTANCE_FOLDER, UPLOAD_FOLDER

db = SQLAlchemy()
migrate = Migrate()

def format_currency(value):
    if value is None:
        return ""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")

def create_app(config_class=Config):
    """Application Factory-funktion"""

    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(INSTANCE_FOLDER, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    app.jinja_env.filters['currency'] = format_currency

    from bokforing_app.main.routes import bp as main_bp
    app.register_blueprint(main_bp)

    from bokforing_app.api.routes import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    with app.app_context():
        db.create_all() # Create database tables if they don't exist
        # Lägg till denna utskrift för att se vilken databasfil som används
        print(f"--- DEBUG: SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']} ---")
        from bokforing_app.services.accounting_config import load_accounting_config
        load_accounting_config()

    return app