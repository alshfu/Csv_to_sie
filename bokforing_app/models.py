# -*- coding: utf-8 -*-
"""
Definierar databasmodellerna för applikationen med SQLAlchemy.

Denna fil innehåller alla ORM-klasser (Object-Relational Mapping) som representerar
tabellerna i databasen. Varje klass motsvarar en tabell och definierar dess
kolumner, relationer och beteenden.

Modeller:
- Company: Representerar ett företag/klient i systemet.
- BankTransaction: Representerar en enskild banktransaktion (verifikation).
- BookkeepingEntry: Representerar en rad i en verifikation (debet/kredit).
- Bilaga: Representerar ett uppladdat underlag (t.ex. kvitto, PDF).
- Invoice: Representerar en kundfaktura, synkroniserad från Fakturan.nu.
- InvoiceRow: En rad på en kundfaktura.
- Client: En kund till ett företag, synkroniserad från Fakturan.nu.
- Matchning: En kopplingstabell med belopp för att matcha transaktioner med fakturor/bilagor.
- Association: En regel för att automatiskt koppla transaktionsreferenser till konton.
- Setting: En tabell för generella systeminställningar.
- Konto: Representerar ett konto i BAS-kontoplanen.
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from bokforing_app import db

# --- Association Tables for Many-to-Many Relationships ---

# NOT: Dessa tabeller är för en äldre datamodell men behålls för att undvika
# dataförlust om en migrering tillbaka skulle behövas. Ny funktionalitet
# använder primärt `Matchning`-modellen.
invoice_transaction_association = db.Table('invoice_transaction_association',
    db.Column('invoice_id', db.Integer, db.ForeignKey('invoice.id'), primary_key=True),
    db.Column('bank_transaction_id', db.Integer, db.ForeignKey('bank_transaction.id'), primary_key=True)
)

bilaga_transaction_association = db.Table('bilaga_transaction_association',
    db.Column('bilaga_id', db.Integer, db.ForeignKey('bilaga.id'), primary_key=True),
    db.Column('bank_transaction_id', db.Integer, db.ForeignKey('bank_transaction.id'), primary_key=True)
)

# --- Main Models ---

class Company(db.Model):
    """
    Representerar ett företag som använder bokföringssystemet.
    Detta är huvudmodellen som allt annat är kopplat till.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    org_nummer = db.Column(db.String(20), unique=True, nullable=False)
    gata = db.Column(db.String(100))
    postkod = db.Column(db.String(20))
    ort = db.Column(db.String(50))
    
    # Inställningar för företaget
    accounting_method = db.Column(db.String(20), default='faktura', nullable=False)  # 'faktura' eller 'kontant'
    fakturanu_key_id = db.Column(db.String(100), nullable=True)
    fakturanu_password = db.Column(db.String(100), nullable=True)

    # Relationer till andra modeller
    transactions = db.relationship('BankTransaction', back_populates='company', lazy=True)
    bilagor = db.relationship('Bilaga', back_populates='company', lazy=True)
    invoices = db.relationship('Invoice', back_populates='company', lazy=True)
    clients = db.relationship('Client', back_populates='company', lazy=True)

class BankTransaction(db.Model):
    """
    Representerar en verifikation i bokföringen.
    Detta kan vara en bankhändelse, en manuell verifikation, eller en bokförd faktura/bilaga.
    """
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    bokforingsdag = db.Column(db.Date, nullable=False)
    referens = db.Column(db.String(200))
    belopp = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='unprocessed') # Ex: 'unprocessed', 'processed', 'pending_duplicate'

    company = db.relationship('Company', back_populates='transactions')
    entries = db.relationship('BookkeepingEntry', backref='bank_transaction', lazy=True, cascade="all, delete-orphan")
    
    # Äldre M2M-relationer (behålls för kompatibilitet)
    attachments = db.relationship('Bilaga', secondary=bilaga_transaction_association, back_populates='transactions')
    invoices = db.relationship('Invoice', secondary=invoice_transaction_association, back_populates='transactions')
    
    # Ny relation för delbetalningar/matchningar
    matchningar = db.relationship('Matchning', back_populates='transaction', lazy=True, cascade="all, delete-orphan")

class BookkeepingEntry(db.Model):
    """
    Representerar en enskild rad (post) i en verifikation.
    Varje verifikation består av minst två sådana rader (debet och kredit).
    """
    id = db.Column(db.Integer, primary_key=True)
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transaction.id'), nullable=False)
    konto = db.Column(db.String(10), nullable=False)
    debet = db.Column(db.Float, default=0.0)
    kredit = db.Column(db.Float, default=0.0)

class Bilaga(db.Model):
    """
    Representerar ett uppladdat underlag, t.ex. ett kvitto eller en leverantörsfaktura.
    Kan kopplas till en eller flera transaktioner via `Matchning`-modellen.
    """
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    filepath = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default='unassigned') # Ex: 'unassigned', 'matched'
    
    # Metadata som kan extraheras från bilagan
    fakturanr = db.Column(db.String(50), nullable=True)
    fakturadatum = db.Column(db.Date, nullable=True)
    forfallodag = db.Column(db.Date, nullable=True)
    ocr = db.Column(db.String(50), nullable=True)
    brutto_amount = db.Column(db.Float, nullable=True)
    netto_amount = db.Column(db.Float, nullable=True)
    moms_amount = db.Column(db.Float, nullable=True)
    suggested_konto = db.Column(db.String(10), nullable=True)
    omvand_skattskyldighet = db.Column(db.Boolean, default=False, nullable=False) # Flagga för omvänd skattskyldighet

    company = db.relationship('Company', back_populates='bilagor')
    transactions = db.relationship('BankTransaction', secondary=bilaga_transaction_association, back_populates='attachments')
    matchningar = db.relationship('Matchning', back_populates='bilaga', lazy=True, cascade="all, delete-orphan")

class Invoice(db.Model):
    """
    Representerar en kundfaktura, oftast synkroniserad från ett externt system som Fakturan.nu.
    Kan kopplas till en eller flera betalningstransaktioner via `Matchning`-modellen.
    """
    id = db.Column(db.Integer, primary_key=True)
    fakturanu_id = db.Column(db.Integer, unique=True, nullable=False) # ID från externa systemet
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
    status = db.Column(db.String(20)) # Ex: 'utkast', 'skickad', 'betald'
    reverse_charge = db.Column(db.Boolean, default=False) # Flagga för omvänd skattskyldighet
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


    company = db.relationship('Company', back_populates='invoices')
    client = db.relationship('Client', back_populates='invoices')
    rows = db.relationship('InvoiceRow', back_populates='invoice', lazy=True, cascade="all, delete-orphan")
    transactions = db.relationship('BankTransaction', secondary=invoice_transaction_association, back_populates='invoices')
    matchningar = db.relationship('Matchning', back_populates='invoice', lazy=True, cascade="all, delete-orphan")

class InvoiceRow(db.Model):
    """Representerar en rad på en kundfaktura."""
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    product_name = db.Column(db.String(200))
    amount = db.Column(db.Float)
    price = db.Column(db.Float)
    tax_rate = db.Column(db.Integer)
    # ... andra fält från Fakturan.nu
    product_id = db.Column(db.Integer)
    product_code = db.Column(db.String(50))
    product_unit = db.Column(db.String(20))
    discount = db.Column(db.Float)

    invoice = db.relationship('Invoice', back_populates='rows')

class Client(db.Model):
    """Representerar en kund till ett företag."""
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

class Matchning(db.Model):
    """
    Representerar en koppling (matchning) mellan en transaktion och ett underlag.
    Detta är kärnan i systemet för delbetalningar, där varje rad i denna tabell
    representerar en specifik summa som kopplar ihop en transaktion med en faktura eller en bilaga.
    """
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)  # Det specifikt matchade beloppet
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys: En matchning måste alltid ha en transaktion.
    transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transaction.id'), nullable=False)
    # En matchning kan ha antingen en faktura ELLER en bilaga.
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=True)
    bilaga_id = db.Column(db.Integer, db.ForeignKey('bilaga.id'), nullable=True)
    
    # Relationer tillbaka till huvudmodellerna
    transaction = db.relationship('BankTransaction', back_populates='matchningar')
    invoice = db.relationship('Invoice', back_populates='matchningar')
    bilaga = db.relationship('Bilaga', back_populates='matchningar')

    def __repr__(self):
        return f'<Matchning {self.id}: {self.amount}kr - Trans {self.transaction_id} -> {"Invoice" if self.invoice else "Bilaga"} {self.invoice_id or self.bilaga_id}>'

class Konto(db.Model):
    """Representerar ett konto i BAS-kontoplanen."""
    id = db.Column(db.Integer, primary_key=True)
    konto_nr = db.Column(db.String(10), unique=True, nullable=False)
    beskrivning = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f'<Konto {self.konto_nr}: {self.beskrivning}>'

class Association(db.Model):
    """
    Representerar en regel för att automatiskt föreslå ett konto
    baserat på ett nyckelord i en transaktionsreferens.
    """
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), nullable=False, unique=True)
    konto_nr = db.Column(db.String(10), db.ForeignKey('konto.konto_nr'), nullable=False)
    rule = db.Column(db.Text, nullable=True) # JSON-sträng med avancerade regler

    konto = db.relationship('Konto', backref='associations')

    def __repr__(self):
        return f"<Association '{self.keyword}' -> {self.konto_nr}>"

class Setting(db.Model):
    """En enkel nyckel-värde-tabell för generella systeminställningar."""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<Setting {self.key}>"
