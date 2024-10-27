from fiona.fio.helpers import nullable
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import *

db = SQLAlchemy()

similarities_table = db.Table('similarities',
                              db.Column('code_id', db.String, db.ForeignKey('codes.id', ondelete='CASCADE'),
                                        primary_key=True),
                              db.Column('code_id2', db.String, db.ForeignKey('codes.id', ondelete='CASCADE'),
                                        primary_key=True),
                              db.Column('percent', db.Integer)
                              )

class Code(db.Model):
    __tablename__ = 'codes'

    id = db.Column(db.String(), primary_key=True)
    lang = db.Column(db.String(), nullable=True)
    code = db.Column(db.Text(), nullable=True)
    ip = db.Column(db.String(), nullable=True)
    created_at = db.Column(db.DateTime(), nullable=True, default=db.func.current_timestamp())
    views = db.Column(db.Integer(), nullable=True, default=0)
    checked = db.Column(db.Boolean(), nullable=False, server_default='false')
    user_id = db.Column(db.Integer, nullable=True)

    similar_codes = db.relationship('Code',
                                    secondary=similarities_table,
                                    primaryjoin=id == similarities_table.c.code_id,
                                    secondaryjoin=id == similarities_table.c.code_id2,
                                    backref='related_codes')

    def get_similar_codes_sorted(self):
        results = (db.session.query(Code, similarities_table.c.percent)
                   .join(similarities_table, Code.id == similarities_table.c.code_id2)
                   .filter(similarities_table.c.code_id == self.id)
                   .order_by(similarities_table.c.percent.desc())
                   .all())

        return [{'code': result[0], 'percent': result[1]} for result in results]
