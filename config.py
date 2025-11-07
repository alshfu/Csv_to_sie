import os

basedir = os.path.abspath(os.path.dirname(__file__))

#
# ===============================================================
#  Шаг 1: Явно определяем ВСЕ абсолютные пути
# ===============================================================
#
INSTANCE_FOLDER = os.path.join(basedir, 'instance')
DB_PATH = os.path.join(INSTANCE_FOLDER, 'app.db')
UPLOAD_FOLDER = os.path.join(basedir, 'bokforing_app', 'static', 'uploads')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'en-mycket-hemlig-nyckel-som-du-bor-andra'

    # Говорим SQLAlchemy использовать ТОЧНЫЙ, абсолютный путь к файлу
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + DB_PATH

    # Говорим Flask использовать ТОЧНЫЙ, абсолютный путь для загрузок
    UPLOAD_FOLDER = UPLOAD_FOLDER