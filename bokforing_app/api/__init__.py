from flask import Blueprint
from flask_cors import CORS

bp = Blueprint('api', __name__)

# Aktivera CORS för alla routes i detta blueprint.
# Detta tillåter webbläsaren att ta emot svar från API:et.
CORS(bp)

from bokforing_app.api import routes
