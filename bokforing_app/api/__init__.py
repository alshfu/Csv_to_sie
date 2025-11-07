from flask import Blueprint

bp = Blueprint('api', __name__)

from bokforing_app.api import routes