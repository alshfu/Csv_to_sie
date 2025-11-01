import os
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from models import db, Company, BankTransaction, Bilaga
import pandas as pd
from datetime import datetime

# --- Настройка Flask ---

# АБСОЛЮТНЫЙ путь к папке, где лежит app.py
basedir = os.path.abspath(os.path.dirname(__file__))
# Создаем путь к нашей папке 'instance'
instance_folder = os.path.join(basedir, 'instance')
# Создаем путь к самому файлу .db
db_path = os.path.join(instance_folder, 'app.db')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-super-secret-key'  # Замените на свой ключ
# Используем АБСОЛЮТНЫЙ путь к базе данных
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db.init_app(app)


@app.before_request
def create_tables():
    # Создаем папки, используя абсолютные пути
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(instance_folder, exist_ok=True)

    # Гарантируем, что таблицы создаются в контексте приложения
    with app.app_context():
        db.create_all()


# --- Страница 1: Список фирм и форма добавления ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            new_company = Company(
                name=request.form['name'],
                org_nummer=request.form['org_nummer'],
                gata=request.form['gata'],
                postkod=request.form['postkod'],
                ort=request.form['ort']
            )
            db.session.add(new_company)
            db.session.commit()
            flash(f"Фирма '{new_company.name}' создана.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка: {e}", "danger")
        return redirect(url_for('index'))

    companies = Company.query.all()
    return render_template('companies.html', companies=companies)


# --- Страница 2: Загрузка CSV и просмотр транзакций ---
@app.route('/company/<int:company_id>', methods=['GET'])
def upload_page(company_id):
    company = Company.query.get_or_404(company_id)
    # Показываем только необработанные транзакции
    transactions = BankTransaction.query.filter_by(
        company_id=company_id,
        status='unprocessed'
    ).order_by(BankTransaction.bokforingsdag.desc()).all()

    return render_template('transactions.html', company=company, transactions=transactions)


@app.route('/company/<int:company_id>/upload_csv', methods=['POST'])
def upload_csv(company_id):
    company = Company.query.get_or_404(company_id)

    # ... (проверки файла) ...
    file = request.files['csv_file']
    # ...

    try:
        #
        # --->>> УБЕДИТЕСЬ, ЧТО ВСЕ ЭТИ СТРОКИ ИМЕЮТ ОДИНАКОВЫЙ ОТСТУП (4 пробела)
        #
        # --- Парсинг CSV ---
        df = pd.read_csv(file, sep=';', header=1, decimal=',', encoding='latin-1')

        df = df.dropna(subset=['Bokföringsdag']) # Фильтруем пустые строки

        for _, row in df.iterrows():
            amount = float(row['Insättning/Uttag'])

            # Логика счетов по умолчанию
            default_contra_konto = '1799' if amount > 0 else '1798' # 1799 (debit) / 1798 (kredit)

            new_trans = BankTransaction(
                company_id=company.id,
                bokforingsdag=datetime.strptime(row['Bokföringsdag'], '%Y-%m-%d').date(),
                referens=str(row['Referens']),
                belopp=amount,
                konto_contra=default_contra_konto,
                status='unprocessed' # Явно указываем статус
            )
            db.session.add(new_trans)

        db.session.commit()
        flash("CSV успешно загружен.", "success")
        #
        # --->>> КОНЕЦ БЛОКА С ОТСТУПОМ
        #

    except Exception as e: # <-- Эта строка должна быть на том же уровне, что и 'try'
        db.session.rollback()
        flash(f"Ошибка при обработке CSV: {e}", "danger")

    return redirect(url_for('upload_page', company_id=company_id))

# --- Генерация SIE ---

def generate_sie_content(company_id):
    company = Company.query.get_or_404(company_id)
    # Берем ВСЕ транзакции (и обработанные, и нет)
    transactions = BankTransaction.query.filter_by(
        company_id=company_id
    ).order_by(BankTransaction.bokforingsdag).all()

    if not transactions:
        return None, "Нет транзакций для экспорта"

    # Определяем финансовый год
    first_date = transactions[0].bokforingsdag
    year_start = first_date.strftime('%Y') + '0101'
    year_end = first_date.strftime('%Y') + '1231'

    # Собираем уникальные счета
    konton = {'1930': 'Bankkonto'}
    for t in transactions:
        if t.konto_contra not in konton:
            konton[t.konto_contra] = f"Konto {t.konto_contra}"

    sie_data = []

    # Заголовки
    sie_data.append('#FLAGGA 0')
    sie_data.append('#PROGRAM "CSV-to-SIE App" 1.0')
    sie_data.append('#FORMAT PC8')
    sie_data.append(f'#GEN {datetime.now().strftime("%Y%m%d")} "Admin"')
    sie_data.append('#SIETYP 4')
    sie_data.append(f'#FNAMN "{company.name}"')
    sie_data.append(f'#ORGNR {company.org_nummer}')
    postadr = f'"{company.postkod} {company.ort}"'
    sie_data.append(f'#ADRESS "" "{company.gata}" {postadr} ""')
    sie_data.append(f'#RAR 0 {year_start} {year_end}')

    # Контоплан
    for konto_nr, konto_namn in konton.items():
        sie_data.append(f'#KONTO {konto_nr} "{konto_namn}"')

    # Транзакции
    ver_nr = 1  # Сквозной номер верификации

    for trans in transactions:
        ver_date = trans.bokforingsdag.strftime('%Y%m%d')
        ver_text = str(trans.referens).replace('"', '')  # Убираем кавычки

        sie_data.append(f'#VER "B" {ver_nr} {ver_date} "{ver_text}"')
        sie_data.append('{')

        amount = trans.belopp

        if amount > 0:
            # Debet 1930, Kredit XXXX
            sie_data.append(f'#TRANS {trans.konto_bank} {{}} {"%.2f" | format(amount)}')
            sie_data.append(f'#TRANS {trans.konto_contra} {{}} {"%.2f" | format(-amount)}')
        else:
            # Kredit 1930, Debet XXXX
            sie_data.append(f'#TRANS {trans.konto_bank} {{}} {"%.2f" | format(amount)}')
            sie_data.append(f'#TRANS {trans.konto_contra} {{}} {"%.2f" | format(-amount)}')

        sie_data.append('}')
        ver_nr += 1

    return "\r\n".join(sie_data), None


@app.route('/company/<int:company_id>/generate_sie', methods=['POST'])
def generate_sie(company_id):
    content, error = generate_sie_content(company_id)

    if error:
        flash(error, "danger")
        return redirect(url_for('upload_page', company_id=company_id))

    filename = f"import_{company_id}_{datetime.now().strftime('%Y%m%d')}.si"

    response = make_response(content)
    # Используем кодировку IBM PC 8-bit (Codepage 437)
    response.charset = 'cp437'
    response.mimetype = 'text/plain'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    return response


if __name__ == '__main__':
    app.run(debug=True)