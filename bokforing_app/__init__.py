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

        # Importera Company-modellen här för att undvika cirkulära importer
        from .models import Company
        
        # Skapa ett standardföretag om det inte redan finns
        default_org_nummer = "559017-1137"
        if not Company.query.filter_by(org_nummer=default_org_nummer).first():
            default_company = Company(
                name="TMR Bygg & Renovering AB",
                org_nummer=default_org_nummer,
                gata="EKBACKEN 3 A",
                postkod="374 50",
                ort="Asarum",
                fakturanu_key_id="WGsm2ZJlM4FstYuFlkvm",
                fakturanu_password="jP_N1hJR3ROb1NBzdKRef6bUdaKSnnrzto6jmrhf"
            )
            db.session.add(default_company)
            db.session.commit()
            print(f"--- DEBUG: Skapade standardföretaget '{default_company.name}' med API-nycklar. ---")


        # Lägg till denna utskrift för att se vilken databasfil som används
        print(f"--- DEBUG: SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']} ---")
        from bokforing_app.services.accounting_config import load_accounting_config
        load_accounting_config()

    return app
