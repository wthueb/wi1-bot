from flask import Flask, redirect

import flask_admin as admin
from flask_mongoengine import MongoEngine
from flask_admin.contrib.mongoengine import ModelView

from transcoder.transcode_queue import TranscodeItem


app = Flask(__name__)

app.config["SECRET_KEY"] = "123456790"
app.config["MONGODB_SETTINGS"] = {"DB": "transcode_queue"}
app.config["FLASK_ADMIN_SWATCH"] = "cyborg"

db = MongoEngine()
db.init_app(app)


class UserView(ModelView):
    column_filters = ["name"]

    column_searchable_list = ("name", "password")

    form_ajax_refs = {"tags": {"fields": ("name",)}}


@app.route("/")
def index():
    return redirect("/admin", code=301)


if __name__ == "__main__":
    admin = admin.Admin(app, name="wi1-bot", template_mode="bootstrap3")

    admin.add_view(ModelView(TranscodeItem))

    app.run(port=5000, debug=True)
