from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    org_nummer = db.Column(db.String(20), unique=True, nullable=False)
    gata = db.Column(db.String(100))
    postkod = db.Column(db.String(20))
    ort = db.Column(db.String(50))

    # Связь с транзакциями
    transactions = db.relationship('BankTransaction', back_populates='company', lazy=True)


class BankTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

    bokforingsdag = db.Column(db.Date, nullable=False)
    referens = db.Column(db.String(200))
    belopp = db.Column(db.Float, nullable=False)  # Сумма (Insättning/Uttag)

    # Статус для бухгалтерии
    status = db.Column(db.String(20), default='unprocessed')  # unprocessed, processed

    # Бухгалтерские счета (по умолчанию)
    # По вашей логике: 1930 (банк) и 1798/1799 (некатегоризированные)
    konto_bank = db.Column(db.String(10), default='1930')
    konto_contra = db.Column(db.String(10))  # Будет 1798 или 1799

    company = db.relationship('Company', back_populates='transactions')
    attachments = db.relationship('Bilaga', backref='transaction', lazy=True)


class Bilaga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('bank_transaction.id'), nullable=False)
    filepath = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(200))