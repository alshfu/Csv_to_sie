from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    org_nummer = db.Column(db.String(20), unique=True, nullable=False)
    gata = db.Column(db.String(100))
    postkod = db.Column(db.String(20))
    ort = db.Column(db.String(50))

    transactions = db.relationship('BankTransaction', back_populates='company', lazy=True)


class BankTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    # Данные из CSV
    bokforingsdag = db.Column(db.Date, nullable=False)
    referens = db.Column(db.String(200))
    belopp = db.Column(db.Float, nullable=False)

    # Статус
    status = db.Column(db.String(20), default='unprocessed')  # unprocessed / processed

    company = db.relationship('Company', back_populates='transactions')

    # Эта строка требует, чтобы класс 'Bilaga' существовал
    attachments = db.relationship('Bilaga', backref='transaction', lazy=True)

    # Связь с бух. записями
    entries = db.relationship('BookkeepingEntry', backref='bank_transaction', lazy=True, cascade="all, delete-orphan")


# Таблица для двойной записи
class BookkeepingEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transaction.id'), nullable=False)

    konto = db.Column(db.String(10), nullable=False)
    debet = db.Column(db.Float, default=0.0)
    kredit = db.Column(db.Float, default=0.0)


#
# --->>> ВОТ ИСПРАВЛЕНИЕ: Я ДОБАВИЛ ЭТОТ КЛАСС НАЗАД
#
class Bilaga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transaction.id'), nullable=False)
    filepath = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(200))