"""Apply the approved 2611/2915 course split after deploying the checkers.

Only task definitions change; student results are updated by the normal recheck.
The original records are saved locally before any write. Re-running is safe.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def query(system, sql):
    container, user, database = {
        "cp": ("codingprojects-db", "codingprojects", "codingprojects"),
        "gp": ("geekpastev2-postgres-1", "postgres", "geekpaste"),
    }[system]
    command = shlex.join(["docker", "exec", "-i", container, "psql", "-X", "-A", "-t",
                          "-v", "ON_ERROR_STOP=1", "-U", user, "-d", database])
    return subprocess.check_output(["ssh", "geekclass.ru", command], input=sql, text=True)


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    snapshot = {}
    for system in ("cp", "gp"):
        rows = query(system, "SELECT row_to_json(t) FROM tasks t WHERE id IN (2611,2915) ORDER BY id;")
        snapshot[system] = [json.loads(line) for line in rows.splitlines()]
        assert snapshot[system][0]["id"] == 2611
        assert snapshot[system][0]["name"] == "Магический квадрат"
        if len(snapshot[system]) == 2:
            assert "первое расхождение" in snapshot[system][1]["name"], "ID 2915 is occupied"
    assert snapshot["cp"][0]["step_id"] == 4453
    # Do not silently discard marks awarded under the old maximum.
    assert query("cp", "SELECT count(*) FROM solutions WHERE task_id=2611 AND mark>5;").strip() == "0"
    assert query("gp", "SELECT count(*) FROM codes WHERE task_id=2611 AND check_points>5;").strip() == "0"
    snapshot["solution"] = query("cp", "SELECT row_to_json(s) FROM solutions s WHERE geekpaste_code_id='JJKFHG';")
    snapshot["code"] = query("gp", "SELECT row_to_json(c) FROM codes c WHERE id='JJKFHG';")
    backup = Path(tempfile.mkdtemp(prefix="magic-square-split-backup-")) / "records.json"
    backup.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Backup:", backup)
    if not args.apply:
        print("Dry run: no database changes")
        return
    base = literal((ROOT / "docs/tasks/2611.md").read_text(encoding="utf-8"))
    bonus = literal((ROOT / "docs/tasks/2915.md").read_text(encoding="utf-8"))
    # Both existing and new checker modules must already be deployed.
    subprocess.run(["ssh", "geekclass.ru", "docker exec geekpastev2-worker-1 python -c " +
                    shlex.quote("from environments.grade8_2026_chapters_1_4 import TASKS; "
                                "assert TASKS[2611][0] == TASKS[2915][0] == 5")], check=True)
    print(query("gp", f"""BEGIN;
        UPDATE tasks SET text={base},points=5,check_type='tests',lang='cpp' WHERE id=2611;
        INSERT INTO tasks(id,name,text,points,lang,check_type,bypass_similarity_check)
        VALUES (2915,'★ Магический квадрат: первое расхождение',{bonus},5,'cpp','tests',false)
        ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,text=EXCLUDED.text,
            points=EXCLUDED.points,lang=EXCLUDED.lang,check_type=EXCLUDED.check_type;
        SELECT setval(pg_get_serial_sequence('tasks','id'),
            GREATEST((SELECT max(id) FROM tasks), (SELECT last_value FROM tasks_id_seq)));
        COMMIT;"""))
    print(query("cp", f"""BEGIN;
        UPDATE tasks SET text={base},max_mark=5,updated_at=NOW() WHERE id=2611;
        INSERT INTO tasks(id,name,text,step_id,max_mark,is_star,is_code,is_hidden,sort_index,
            only_remote,only_class,is_quiz,price,is_demo,is_training,penalty,
            xp_booster_enabled,generates_ai_achievement,created_at,updated_at)
        VALUES (2915,'Магический квадрат: первое расхождение',{bonus},4453,5,true,true,false,150,
            false,false,false,0,false,false,1,false,false,NOW(),NOW())
        ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,text=EXCLUDED.text,
            max_mark=5,is_star=true,is_code=true,is_hidden=false,sort_index=150,updated_at=NOW();
        COMMIT;"""))
    for system in ("cp", "gp"):
        print(system, query(system, "SELECT id,name FROM tasks WHERE id IN (2611,2915) ORDER BY id;"))


if __name__ == "__main__":
    main()
