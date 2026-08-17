from flask import Blueprint

portal_bp = Blueprint("portal", __name__)

from app.blueprints.portal import routes  # noqa: E402, F401
