from manage import app
from methods import *
from tqdm import tqdm
import checker

with app.app_context():
    codes = get_all_codes()

    def bypass(code):
        return (code.task and code.task.bypass_similarity_check) or not code.user_id

    def should_check(code):
        return not bypass(code)

    codes = list(filter(should_check, codes))
    unchecked_codes = list(filter(lambda c: not c.similarity_checked, codes))

    for code in tqdm(unchecked_codes):
        for code2 in codes:
            if code2.id == code.id:
                continue

            n = checker.similarity(code.code, code2.code)

            if n >= SIMILARITY_LEVEL:
                save_similarity(code, code2, n)

        code.similarity_checked = True
        db.session.commit()
