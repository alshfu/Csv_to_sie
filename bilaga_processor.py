import os
import uuid
from werkzeug.utils import secure_filename

# Список разрешенных расширений
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}

def _is_allowed_file(filename):
    """Проверяет, имеет ли файл разрешенное расширение."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_bilaga_file(file, company_id, base_upload_path):
    """
    Безопасно сохраняет файл в папку, специфичную для компании,
    и возвращает уникальное имя файла и относительный путь.
    """
    if not file or file.filename == '':
        raise ValueError("Файл отсутствует")

    if not _is_allowed_file(file.filename):
        raise ValueError(f"Недопустимый тип файла. Разрешены: {list(ALLOWED_EXTENSIONS)}")

    # Получаем исходное имя файла и расширение
    original_filename = secure_filename(file.filename)
    filename, extension = os.path.splitext(original_filename)

    # Создаем уникальное имя файла, чтобы избежать перезаписи
    # Пример: faktura_a1b2c3d4.pdf
    unique_suffix = uuid.uuid4().hex[:8]
    unique_filename = f"{filename}_{unique_suffix}{extension}"

    # Создаем путь для сохранения
    company_folder_name = f'company_{company_id}'
    company_folder_path = os.path.join(base_upload_path, company_folder_name)
    os.makedirs(company_folder_path, exist_ok=True)

    # Сохраняем файл
    absolute_filepath = os.path.join(company_folder_path, unique_filename)
    file.save(absolute_filepath)

    # Формируем относительный путь для сохранения в БД
    relative_filepath = os.path.join(company_folder_name, unique_filename)

    # Возвращаем ОРИГИНАЛЬНОЕ имя для отображения и относительный путь для хранения
    return original_filename, relative_filepath
