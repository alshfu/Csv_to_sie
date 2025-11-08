from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from bokforing_app import db  # <-- Импорт из __init__


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    org_nummer = db.Column(db.String(20), unique=True, nullable=False)
    gata = db.Column(db.String(100))
    postkod = db.Column(db.String(20))
    ort = db.Column(db.String(50))

    transactions = db.relationship('BankTransaction', back_populates='company', lazy=True)
    bilagor = db.relationship('Bilaga', back_populates='company', lazy=True)


class BankTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    bokforingsdag = db.Column(db.Date, nullable=False)
    referens = db.Column(db.String(200))
    belopp = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='unprocessed')

    company = db.relationship('Company', back_populates='transactions')
    entries = db.relationship('BookkeepingEntry', backref='bank_transaction', lazy=True, cascade="all, delete-orphan")
    attachments = db.relationship('Bilaga', back_populates='transaction', lazy=True)


class BookkeepingEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transaction.id'), nullable=False)
    konto = db.Column(db.String(10), nullable=False)
    debet = db.Column(db.Float, default=0.0)
    kredit = db.Column(db.Float, default=0.0)


class Bilaga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transaction.id'), nullable=True)

    # --- Метаданные файла ---
    filepath = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default='unassigned')

    # --- Новые поля из Gemini ---
    fakturanr = db.Column(db.String(50), nullable=True)
    fakturadatum = db.Column(db.Date, nullable=True)
    forfallodag = db.Column(db.Date, nullable=True)
    ocr = db.Column(db.String(50), nullable=True)
    total_netto = db.Column(db.String(50), nullable=True)
    total_moms = db.Column(db.String(50), nullable=True)
    total_brutto = db.Column(db.String(50), nullable=True)
    att_betala = db.Column(db.String(50), nullable=True)

    # Данные клиента (Kund)
    kund_namn = db.Column(db.String(200), nullable=True)
    kund_orgnr = db.Column(db.String(20), nullable=True)
    kund_nummer = db.Column(db.String(50), nullable=True)
    kund_adress = db.Column(db.String(200), nullable=True)

    # Данные продавца (Säljare)
    saljare_namn = db.Column(db.String(200), nullable=True)
    saljare_orgnr = db.Column(db.String(20), nullable=True)
    saljare_momsregnr = db.Column(db.String(50), nullable=True)
    saljare_bankgiro = db.Column(db.String(20), nullable=True)

    # Суммы (числовые)
    brutto_amount = db.Column(db.Float, nullable=True)
    netto_amount = db.Column(db.Float, nullable=True)
    moms_amount = db.Column(db.Float, nullable=True)

    # Бухгалтерия
    suggested_konto = db.Column(db.String(10), nullable=True)

    # --- Связи (Relationships) ---
    company = db.relationship('Company', back_populates='bilagor')
    transaction = db.relationship('BankTransaction', back_populates='attachments')
