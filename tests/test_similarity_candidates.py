import unittest

from flask import Flask
from models import Code, db
from similarity_candidates import similarity_candidates_query


class SimilarityCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["TESTING"] = True
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _code(self, code_id, user_id, task_id, course_id, lang):
        return Code(
            id=code_id,
            code="print(1)",
            user_id=user_id,
            task_id=task_id,
            course_id=course_id,
            lang=lang,
            similarity_checked=False,
        )

    def test_candidates_are_limited_to_same_task_course_and_language(self):
        target = self._code("target", 1, 10, 20, "python")
        included = self._code("included", 2, 10, 20, "python")
        same_user = self._code("same-user", 1, 10, 20, "python")
        other_task = self._code("other-task", 2, 11, 20, "python")
        other_course = self._code("other-course", 2, 10, 21, "python")
        other_lang = self._code("other-lang", 2, 10, 20, "cpp")
        anonymous = self._code("anonymous", None, 10, 20, "python")
        db.session.add_all([target, included, same_user, other_task, other_course, other_lang, anonymous])
        db.session.commit()

        ids = [code.id for code in similarity_candidates_query(target).order_by(Code.id).all()]

        self.assertEqual(ids, ["included"])

    def test_none_values_must_match_none_values(self):
        target = self._code("target", 1, None, None, None)
        included = self._code("included", 2, None, None, None)
        with_task = self._code("with-task", 2, 10, None, None)
        with_course = self._code("with-course", 2, None, 20, None)
        with_lang = self._code("with-lang", 2, None, None, "python")
        db.session.add_all([target, included, with_task, with_course, with_lang])
        db.session.commit()

        ids = [code.id for code in similarity_candidates_query(target).order_by(Code.id).all()]

        self.assertEqual(ids, ["included"])


if __name__ == "__main__":
    unittest.main()
