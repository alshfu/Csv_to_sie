from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from bokforing_app import db

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

    filepath = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default='unassigned')
    fakturanr = db.Column(db.String(50), nullable=True)
    fakturadatum = db.Column(db.Date, nullable=True)
    forfallodag = db.Column(db.Date, nullable=True)
    ocr = db.Column(db.String(50), nullable=True)
    brutto_amount = db.Column(db.Float, nullable=True)
    netto_amount = db.Column(db.Float, nullable=True)
    moms_amount = db.Column(db.Float, nullable=True)
    suggested_konto = db.Column(db.String(10), nullable=True)

    company = db.relationship('Company', back_populates='bilagor')
    transaction = db.relationship('BankTransaction', back_populates='attachments')

class Konto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    konto_nr = db.Column(db.String(10), unique=True, nullable=False)
    beskrivning = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f"<Konto {self.konto_nr} - {self.beskrivning}>"

class Association(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), nullable=False, unique=True) # Keyword must be unique across all accounts
    konto_nr = db.Column(db.String(10), db.ForeignKey('konto.konto_nr'), nullable=False)
    rule = db.Column(db.Text, nullable=True)

    konto = db.relationship('Konto', backref='associations')

    def __repr__(self):
        return f"<Association '{self.keyword}' -> {self.konto_nr}>"

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<Setting {self.key}>"
