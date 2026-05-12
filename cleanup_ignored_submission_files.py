import argparse
import json

from sqlalchemy import create_engine, text

from config import CONNECTION_STRING
from submission_file_filter import should_ignore_submission_file


def parse_args():
    parser = argparse.ArgumentParser(
        description="Удалить служебные файлы из уже сохранённых zip/github решений."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Сохранить изменения в базе. Без флага выполняется только dry-run.",
    )
    parser.add_argument(
        "--id",
        dest="code_id",
        help="Обработать только одну посылку по ID.",
    )
    parser.add_argument(
        "--lang",
        choices=["zip", "github"],
        help="Ограничить обработку одним типом посылок.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Ограничить количество записей для обработки.",
    )
    parser.add_argument(
        "--reset-similarity",
        action="store_true",
        help="Для изменённых записей сбросить similarity_checked, чтобы их можно было пересчитать.",
    )
    parser.add_argument(
        "--print-files",
        action="store_true",
        help="Печатать имена удаляемых файлов.",
    )
    parser.add_argument(
        "--database-url",
        default=CONNECTION_STRING,
        help="SQLAlchemy URL базы. По умолчанию берётся CONNECTION_STRING из окружения.",
    )
    return parser.parse_args()


def filter_files(files):
    kept_files = []
    removed_files = []

    for file_item in files:
        file_name = file_item.get("name") or ""
        if should_ignore_submission_file(file_name):
            removed_files.append(file_name or "<unknown>")
        else:
            kept_files.append(file_item)

    return kept_files, removed_files


def cleanup_zip_submission(code_text):
    files = json.loads(code_text or "[]")
    if not isinstance(files, list):
        return None

    kept_files, removed_files = filter_files(files)
    if not removed_files:
        return None

    return json.dumps(kept_files, ensure_ascii=False), removed_files


def cleanup_github_submission(code_text):
    payload = json.loads(code_text or "{}")
    if not isinstance(payload, dict):
        return None

    files = payload.get("files", [])
    if not isinstance(files, list):
        return None

    kept_files, removed_files = filter_files(files)
    if not removed_files:
        return None

    payload["files"] = kept_files
    return json.dumps(payload, ensure_ascii=False), removed_files


def cleanup_submission(lang, code_text):
    if lang == "zip":
        return cleanup_zip_submission(code_text)
    if lang == "github":
        return cleanup_github_submission(code_text)
    return None


def build_select_query(args):
    params = {}
    conditions = []
    if args.code_id:
        conditions.append("id = :code_id")
        params["code_id"] = args.code_id
    elif args.lang:
        conditions.append("lang = :lang")
        params["lang"] = args.lang
    else:
        conditions.append("lang IN ('zip', 'github')")

    sql = "SELECT id, lang, code FROM codes"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id ASC"
    if args.limit:
        sql += " LIMIT :limit"
        params["limit"] = args.limit

    return text(sql), params


def update_cleaned_code(connection, code_id, cleaned_code, reset_similarity):
    if reset_similarity:
        connection.execute(
            text("DELETE FROM similarities WHERE code_id = :code_id OR code_id2 = :code_id"),
            {"code_id": code_id},
        )
        connection.execute(
            text(
                """
                UPDATE codes
                SET code = :code,
                    similarity_checked = false,
                    has_similarity_warning = false,
                    has_critical_similarity_warning = false
                WHERE id = :code_id
                """
            ),
            {"code": cleaned_code, "code_id": code_id},
        )
        return

    connection.execute(
        text("UPDATE codes SET code = :code WHERE id = :code_id"),
        {"code": cleaned_code, "code_id": code_id},
    )


def main():
    args = parse_args()
    scanned = 0
    changed = 0
    removed_total = 0
    broken = 0

    engine = create_engine(args.database_url)
    connection = engine.connect()
    transaction = connection.begin()

    try:
        query, params = build_select_query(args)
        for code in connection.execute(query, params).mappings():
            scanned += 1
            try:
                result = cleanup_submission(code["lang"], code["code"])
            except Exception as exc:
                broken += 1
                print(f"{code['id']}: не удалось разобрать сохранённые файлы ({exc})")
                continue

            if not result:
                continue

            cleaned_code, removed_files = result
            changed += 1
            removed_total += len(removed_files)
            print(f"{code['id']}: будет удалено файлов: {len(removed_files)}")
            if args.print_files:
                for file_name in removed_files:
                    print(f"  - {file_name}")

            if args.apply:
                update_cleaned_code(connection, code["id"], cleaned_code, args.reset_similarity)

        if args.apply:
            transaction.commit()
        else:
            transaction.rollback()
    except Exception:
        transaction.rollback()
        raise
    finally:
        connection.close()

    mode = "apply" if args.apply else "dry-run"
    print(
        f"{mode}: просмотрено {scanned}, изменено {changed}, "
        f"удалено файлов {removed_total}, ошибок {broken}"
    )


if __name__ == "__main__":
    main()
