from manage import app
from methods import *
from tqdm import tqdm
import checker

with app.app_context():
    codes = get_all_codes()

    db.session.query(similarities_table).delete()
    db.session.commit()


    for code in tqdm(codes):
        if not code.similarity_checked:
            # Collect all similarities above threshold for summary notification
            found_similarities = []
            
            for code2 in codes:
                if code2.id == code.id:
                    continue

                n = checker.similarity(code.code, code2.code)

                if n >= SIMILARITY_LEVEL:
                    # Save similarity without sending individual notification
                    save_similarity(code, code2, n, send_notification=False)
                    found_similarities.append((code2, n))

            # Send single summary notification for all similarities
            if found_similarities:
                send_similarity_summary_notification(code, found_similarities)
            
            code.similarity_checked = True

    db.session.commit()
