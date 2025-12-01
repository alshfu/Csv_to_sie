import os
from bokforing_app import create_app, db
from bokforing_app.models import Konto, Association
from bokforing_app.services.accounting_config import KONTOPLAN, ASSOCIATION_MAP

# Skapa en Flask-applikationskontext
app = create_app()
app.app_context().push()

def migrate_config_to_db():
    print("Starting migration of accounting config to database...")

    # Migrera KONTOPLAN
    print("Migrating KONTOPLAN...")
    for konto_nr, beskrivning in KONTOPLAN.items():
        existing_konto = Konto.query.filter_by(konto_nr=konto_nr).first()
        if not existing_konto:
            new_konto = Konto(konto_nr=konto_nr, beskrivning=beskrivning)
            db.session.add(new_konto)
            print(f"  Added Konto: {konto_nr} - {beskrivning}")
        else:
            print(f"  Konto {konto_nr} already exists. Skipping.")
    db.session.commit()
    print("KONTOPLAN migration complete.")

    # Migrera ASSOCIATION_MAP
    print("Migrating ASSOCIATION_MAP...")
    for keyword, konto_nr in ASSOCIATION_MAP.items():
        existing_association = Association.query.filter_by(keyword=keyword).first()
        if not existing_association:
            new_association = Association(keyword=keyword, konto_nr=konto_nr)
            db.session.add(new_association)
            print(f"  Added Association: '{keyword}' -> {konto_nr}")
        else:
            print(f"  Association '{keyword}' already exists. Skipping.")
    db.session.commit()
    print("ASSOCIATION_MAP migration complete.")

    print("All accounting config migration finished.")

if __name__ == "__main__":
    migrate_config_to_db()
