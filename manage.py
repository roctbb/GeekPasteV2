import time

from flask import Flask, request, session, abort
from models import db
from config import *
from flask_migrate import Migrate
import jwt

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = CONNECTION_STRING
app.config['SECRET_KEY'] = SECRET  # Set secret key
db.init_app(app)

migrate = Migrate(app, db)

from flask import session, redirect, url_for
from functools import wraps


def make_jwt_auth(token):
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        if time.time() - data['iat'] > 5:
            abort(403)
        session['user_id'] = data['id']
        session['role'] = data['role']
    except Exception as e:
        abort(403)


def login_required(f):
    @wraps(f)
    def F(*args, **kwargs):
        token = request.args.get('token')
        if token:
            make_jwt_auth(token)
            return redirect(url_for(request.endpoint, **{k: v for k, v in request.args.items() if k != 'token'}))

        if 'user_id' not in session:
            return redirect(AUTH_URL + request.url)  # Redirect to login page if user_id is not in session

        return f(*args, **kwargs)

    return F
