from manage import app
from methods import *
from tqdm import tqdm
import checker

with app.app_context():
    codes = get_all_codes()

    db.session.query(similarities_table).delete()
    db.session.commit()


    for code in tqdm(codes):
        if not code.checked:
            for code2 in codes:
                if code2.id == code.id:
                    continue

                n = checker.similarity(code.code, code2.code)
                code.similarity_checked = True

                if n >= SIMILARITY_LEVEL:
                    save_similarity(code, code2, n)

    db.session.commit()
