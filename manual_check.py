from manage import app
from methods import *
from tqdm import tqdm
import checker
import argparse
from datetime import datetime

# Парсинг аргументов командной строки
parser = argparse.ArgumentParser(description='Проверка схожести кода')
parser.add_argument('--after-date', type=str, help='Проверять только код, созданный после указанной даты (формат: YYYY-MM-DD)')
args = parser.parse_args()

with app.app_context():
    codes = get_all_codes()

    def bypass(code):
        return (code.task and code.task.bypass_similarity_check) or not code.user_id

    def should_check(code):
        return not bypass(code)

    codes = list(filter(should_check, codes))

    # Фильтрация по дате, если указан аргумент --after-date
    if args.after_date:
        try:
            after_date = datetime.strptime(args.after_date, '%Y-%m-%d')
            codes = list(filter(lambda c: c.created_at and c.created_at >= after_date, codes))
            print(f"Фильтрация кодов после {args.after_date}: найдено {len(codes)} записей")
        except ValueError:
            print("Ошибка: Неверный формат даты. Используйте формат YYYY-MM-DD")
            exit(1)

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