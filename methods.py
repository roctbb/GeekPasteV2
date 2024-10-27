import string
import random
import datetime
from sqlalchemy import *
from models import *
from config import *


def create_id():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def get_code(id):
    return Code.query.filter_by(id=id).first()


def save_code(code, lang, client_ip, id=None, user_id=None):
    if not id:
        while True:
            id = create_id()

            if not get_code(id):
                break

    code = Code(id=id, code=code, lang=lang, ip=client_ip, views=0, user_id=user_id)
    db.session.add(code)
    db.session.commit()

    return id


def get_all_codes(lang=None):
    if not lang:
        return Code.query.all()
    return Code.query.filter_by(lang=lang).all()


def add_view(code):
    code.views += 1
    db.session.commit()


def save_similarity(new_code, similar_code, percent):
    similarity_entry = similarities_table.insert().values(
        code_id=new_code.id,
        code_id2=similar_code.id,
        percent=percent
    )

    db.session.execute(similarity_entry)
    db.session.commit()
