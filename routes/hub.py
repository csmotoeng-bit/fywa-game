from flask import Blueprint, render_template

hub_bp = Blueprint("hub", __name__)


@hub_bp.route("/")
def index():
    return render_template("hub.html")


@hub_bp.route("/typical")
def typical_menu():
    return render_template("typical/coming_soon.html")