import os
from werkzeug.utils import secure_filename
from flask import current_app


def save_bilaga_file(file, company_id):
    """
    Безопасно сохраняет файл в папку,
    специфичную для компании, и возвращает пути.
    """
    if not file or file.filename == '':
        raise ValueError("Fil saknas")

    filename = secure_filename(file.filename)

    # Мы создаем папку для каждой компании: static/uploads/company_1/
    company_folder_name = f'company_{company_id}'
    company_folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], company_folder_name)

    # Создаем папку, если ее нет
    os.makedirs(company_folder_path, exist_ok=True)

    # Абсолютный путь для сохранения
    absolute_filepath = os.path.join(company_folder_path, filename)

    # Сохраняем файл
    file.save(absolute_filepath)

    # Относительный путь для БД (static/uploads/company_1/faktura.pdf)
    # Этот путь будет использоваться в url_for('static', ...)
    relative_filepath = os.path.join(company_folder_name, filename)

    return filename, relative_filepath


def analyze_bilaga_pdf(filepath):
    """
    ЗАГОТОВКА НА БУДУЩЕЕ.
    Здесь будет логика чтения PDF.

    (потребуется `pip install PyPDF2` или `pip install pdfplumber`)
    """

    # import PyPDF2
    # ... логика ...

    print(f"Анализируем файл: {filepath}")
    # TODO: Реализовать логику извлечения текста

    # Примерный результат:
    extracted_data = {
        "total_amount": 1000.00,
        "moms": 200.00,
        "org_nummer": "556677-8899",
        "date": "2025-10-30"
    }

    # Пока возвращаем None
    return None