from manage import app
from methods import *
from tqdm import tqdm
import checker

with app.app_context():
    codes = get_all_codes()

    for code in tqdm(codes):
        if not code.user_id:
            continue

        if not code.similarity_checked:
            if code.task and code.task.bypass_similarity_check:
                print(f"Bypass code ID {code.id}")
                continue

            print(f"Checking code ID {code.id}")

            for code2 in codes:
                if not code2.user_id:
                    continue

                if code2.id == code.id:
                    continue

                n = checker.similarity(code.code, code2.code)

                if n >= SIMILARITY_LEVEL:
                    save_similarity(code, code2, n)

            code.similarity_checked = True

    db.session.commit()
