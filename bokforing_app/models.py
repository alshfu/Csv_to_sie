from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from bokforing_app import db

# Association table for the many-to-many relationship between Invoice and BankTransaction
invoice_transaction_association = db.Table('invoice_transaction_association',
    db.Column('invoice_id', db.Integer, db.ForeignKey('invoice.id'), primary_key=True),
    db.Column('bank_transaction_id', db.Integer, db.ForeignKey('bank_transaction.id'), primary_key=True)
)

# Association table for the many-to-many relationship between Bilaga and BankTransaction
bilaga_transaction_association = db.Table('bilaga_transaction_association',
    db.Column('bilaga_id', db.Integer, db.ForeignKey('bilaga.id'), primary_key=True),
    db.Column('bank_transaction_id', db.Integer, db.ForeignKey('bank_transaction.id'), primary_key=True)
)

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    org_nummer = db.Column(db.String(20), unique=True, nullable=False)
    gata = db.Column(db.String(100))
    postkod = db.Column(db.String(20))
    ort = db.Column(db.String(50))
    
    accounting_method = db.Column(db.String(20), default='faktura', nullable=False)
    fakturanu_key_id = db.Column(db.String(100), nullable=True)
    fakturanu_password = db.Column(db.String(100), nullable=True)

    transactions = db.relationship('BankTransaction', back_populates='company', lazy=True)
    bilagor = db.relationship('Bilaga', back_populates='company', lazy=True)
    invoices = db.relationship('Invoice', back_populates='company', lazy=True)
    clients = db.relationship('Client', back_populates='company', lazy=True)

class BankTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    # invoice_id is now handled by the association table
    bokforingsdag = db.Column(db.Date, nullable=False)
    referens = db.Column(db.String(200))
    belopp = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='unprocessed')

    company = db.relationship('Company', back_populates='transactions')
    entries = db.relationship('BookkeepingEntry', backref='bank_transaction', lazy=True, cascade="all, delete-orphan")
    
    # Many-to-many relationships
    attachments = db.relationship('Bilaga', secondary=bilaga_transaction_association, back_populates='transactions')
    invoices = db.relationship('Invoice', secondary=invoice_transaction_association, back_populates='transactions')

class BookkeepingEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transaction.id'), nullable=False)
    konto = db.Column(db.String(10), nullable=False)
    debet = db.Column(db.Float, default=0.0)
    kredit = db.Column(db.Float, default=0.0)

class Bilaga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    # bank_transaction_id is now handled by the association table

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
    transactions = db.relationship('BankTransaction', secondary=bilaga_transaction_association, back_populates='attachments')

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fakturanu_id = db.Column(db.Integer, unique=True, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    number = db.Column(db.String(50))
    date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    our_reference = db.Column(db.String(100))
    your_reference = db.Column(db.String(100))
    paid_at = db.Column(db.Date, nullable=True)
    locale = db.Column(db.String(10))
    currency = db.Column(db.String(10))
    sum = db.Column(db.Float)
    net = db.Column(db.Float)
    tax = db.Column(db.Float)
    status = db.Column(db.String(20))
    reverse_charge = db.Column(db.Boolean, default=False)

    company = db.relationship('Company', back_populates='invoices')
    client = db.relationship('Client', back_populates='invoices')
    transactions = db.relationship('BankTransaction', secondary=invoice_transaction_association, back_populates='invoices')
    rows = db.relationship('InvoiceRow', back_populates='invoice', lazy=True, cascade="all, delete-orphan")

class InvoiceRow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    product_id = db.Column(db.Integer)
    product_code = db.Column(db.String(50))
    product_name = db.Column(db.String(200))
    product_unit = db.Column(db.String(20))
    discount = db.Column(db.Float)
    amount = db.Column(db.Float)
    price = db.Column(db.Float)
    tax_rate = db.Column(db.Integer)

    invoice = db.relationship('Invoice', back_populates='rows')

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fakturanu_id = db.Column(db.Integer, unique=True, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    name = db.Column(db.String(100))
    org_number = db.Column(db.String(50))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    street_address = db.Column(db.String(100))
    zip_code = db.Column(db.String(20))
    city = db.Column(db.String(50))
    country = db.Column(db.String(50))

    company = db.relationship('Company', back_populates='clients')
    invoices = db.relationship('Invoice', back_populates='client', lazy=True)

class Konto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    konto_nr = db.Column(db.String(10), unique=True, nullable=False)
    beskrivning = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f"<Konto {self.konto_nr} - {self.beskrivning}>"

class Association(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), nullable=False, unique=True)
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
