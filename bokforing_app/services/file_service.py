import os
from werkzeug.utils import secure_filename


# Denna fil behöver inte längre 'current_app'
def save_bilaga_file(file, company_id, base_upload_path):
    if not file or file.filename == '':
        raise ValueError("Fil saknas")

    filename = secure_filename(file.filename)
    company_folder_name = f'company_{company_id}'
    company_folder_path = os.path.join(base_upload_path, company_folder_name)

    os.makedirs(company_folder_path, exist_ok=True)

    absolute_filepath = os.path.join(company_folder_path, filename)
    file.save(absolute_filepath)

    # Relativ sökväg för DB (t.ex. 'company_1/faktura.pdf')
    relative_filepath = os.path.join(company_folder_name, filename)

    return filename, relative_filepath, absolute_filepath