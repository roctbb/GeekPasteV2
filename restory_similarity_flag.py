from manage import app
from models import Code, db

with app.app_context():
    for code in Code.query.filter_by(similarity_checked=True).all():
        if len(code.similar_codes) > 0:
            code.has_similarity_warning = True
    db.session.commit()