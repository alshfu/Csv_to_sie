from flask import Blueprint

bp = Blueprint('main', __name__)

from bokforing_app.main import routes