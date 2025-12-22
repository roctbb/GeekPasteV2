from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

similarities_table = db.Table('similarities',
                              db.Column('code_id', db.String, db.ForeignKey('codes.id', ondelete='CASCADE'),
                                        primary_key=True),
                              db.Column('code_id2', db.String, db.ForeignKey('codes.id', ondelete='CASCADE'),
                                        primary_key=True),
                              db.Column('percent', db.Integer)
                              )


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(), nullable=True)
    lang = db.Column(db.String(), nullable=True)
    points = db.Column(db.Integer(), nullable=True)
    check_type = db.Column(db.String(), nullable=True, server_default='tests')
    text = db.Column(db.Text(), nullable=True)
    bypass_similarity_check = db.Column(db.Boolean(), nullable=False, server_default='false')


class Code(db.Model):
    __tablename__ = 'codes'

    id = db.Column(db.String(), primary_key=True)
    lang = db.Column(db.String(), nullable=True)
    code = db.Column(db.Text(), nullable=True)
    ip = db.Column(db.String(), nullable=True)
    created_at = db.Column(db.DateTime(), nullable=True, default=db.func.current_timestamp())
    views = db.Column(db.Integer(), nullable=True, default=0)
    similarity_checked = db.Column(db.Boolean(), nullable=False, server_default='false')
    user_id = db.Column(db.Integer, nullable=True)

    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    course_id = db.Column(db.Integer, nullable=True)
    check_state = db.Column(db.String(255), nullable=True, server_default='not checked')
    check_comments = db.Column(db.Text(), nullable=True)
    check_points = db.Column(db.Integer(), nullable=True)
    checked_at = db.Column(db.DateTime(), nullable=True)

    has_similarity_warning = db.Column(db.Boolean(), server_default='false', nullable=False)
    has_critical_similarity_warning = db.Column(db.Boolean(), server_default='false', nullable=False)
    viewed_by_teacher = db.Column(db.Boolean(), server_default='false', nullable=False)

    # AI detection fields
    has_ai_warning = db.Column(db.Boolean(), server_default='false', nullable=False)
    ai_warning_reasons = db.Column(db.Text(), nullable=True)
    ai_confidence = db.Column(db.String(20), nullable=True)  # low/medium/high
    gpt_llm_probability = db.Column(db.Integer(), nullable=True)  # 0-100 от GPT проверки

    similar_codes = db.relationship('Code',
                                    secondary=similarities_table,
                                    primaryjoin=id == similarities_table.c.code_id,
                                    secondaryjoin=id == similarities_table.c.code_id2,
                                    backref='related_codes')
    task = db.relationship('Task', backref='solutions')

    def get_similar_codes_sorted(self):
        results = (db.session.query(Code, similarities_table.c.percent)
                   .join(similarities_table, Code.id == similarities_table.c.code_id2)
                   .filter(similarities_table.c.code_id == self.id)
                   .order_by(similarities_table.c.percent.desc())
                   .all())

        return [{'code': result[0], 'percent': result[1]} for result in results]
