import os
from werkzeug.utils import secure_filename
from flask import current_app


def save_bilaga_file(file, company_id, base_upload_path):
    """
    Безопасно сохраняет файл в папку,
    специфичную для компании, и возвращает пути.
    """
    if not file or file.filename == '':
        raise ValueError("Fil saknas")

    filename = secure_filename(file.filename)

    company_folder_name = f'company_{company_id}'

    # Используем 'base_upload_path' вместо 'current_app'
    company_folder_path = os.path.join(base_upload_path, company_folder_name)

    os.makedirs(company_folder_path, exist_ok=True)

    absolute_filepath = os.path.join(company_folder_path, filename)

    file.save(absolute_filepath)

    relative_filepath = os.path.join(company_folder_name, filename)

    return filename, relative_filepath


def analyze_bilaga_pdf(filepath):
    """
    ЗАГОТОВКА НА БУДУЩЕЕ.
    """
    print(f"Анализируем файл: {filepath}")
    return None
