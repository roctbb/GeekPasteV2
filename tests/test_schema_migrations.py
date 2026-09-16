import io
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from flask import Flask
from flask_migrate import Migrate, upgrade
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as sa


MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
DEPLOYED_HEAD = "f3a5c7e9b1d4"


@contextmanager
def database_at(revision, *, rate_limit_exists):
    with tempfile.TemporaryDirectory() as directory:
        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = (
            f"sqlite:///{Path(directory) / 'migration-test.sqlite'}"
        )
        db = SQLAlchemy(app)
        Migrate(app, db, directory=str(MIGRATIONS))
        with app.app_context():
            metadata = sa.MetaData()
            tasks = sa.Table(
                "tasks", metadata,
                sa.Column("id", sa.Integer, primary_key=True),
                sa.Column("name", sa.String),
                sa.Column("gpt_model", sa.String),
            )
            if rate_limit_exists:
                tasks.append_column(sa.Column("gpt_rate_limit", sa.Integer))
            versions = sa.Table(
                "alembic_version", metadata,
                sa.Column("version_num", sa.String(32), primary_key=True),
            )
            metadata.create_all(db.engine)
            with db.engine.begin() as connection:
                connection.execute(versions.insert(), {"version_num": revision})
                row = {"id": 1, "name": "Existing task", "gpt_model": "custom"}
                if rate_limit_exists:
                    row["gpt_rate_limit"] = 12
                connection.execute(tasks.insert(), row)
            try:
                yield db.engine
            finally:
                db.session.remove()
                db.engine.dispose()


class SchemaMigrationTests(unittest.TestCase):
    def test_deployed_head_upgrade_is_a_noop(self):
        with database_at(DEPLOYED_HEAD, rate_limit_exists=True) as engine:
            statements = []

            def capture(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)

            sa.event.listen(engine, "before_cursor_execute", capture)
            upgrade(directory=str(MIGRATIONS))
            sa.event.remove(engine, "before_cursor_execute", capture)

            for statement in statements:
                self.assertNotRegex(
                    statement,
                    r"(?i)^\s*(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE)\b",
                )
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(sa.text("SELECT * FROM tasks")).one(),
                    (1, "Existing task", "custom", 12),
                )
                self.assertEqual(
                    connection.execute(sa.text(
                        "SELECT version_num FROM alembic_version"
                    )).scalar_one(),
                    DEPLOYED_HEAD,
                )

    def test_last_schema_upgrade_preserves_existing_tasks(self):
        with database_at("5613318ab013", rate_limit_exists=False) as engine:
            upgrade(directory=str(MIGRATIONS))

            columns = {
                column["name"]: column
                for column in sa.inspect(engine).get_columns("tasks")
            }
            self.assertIsInstance(columns["gpt_rate_limit"]["type"], sa.Integer)
            self.assertTrue(columns["gpt_rate_limit"]["nullable"])
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(sa.text("SELECT * FROM tasks")).one(),
                    (1, "Existing task", "custom", None),
                )
                self.assertEqual(
                    connection.execute(sa.text(
                        "SELECT version_num FROM alembic_version"
                    )).scalar_one(),
                    DEPLOYED_HEAD,
                )

    def test_fresh_postgres_schema_has_no_application_data_updates(self):
        config = Config()
        config.set_main_option("script_location", str(MIGRATIONS))
        scripts = ScriptDirectory.from_config(config)
        self.assertEqual(scripts.get_heads(), [DEPLOYED_HEAD])
        output = io.StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql",
            opts={"as_sql": True, "output_buffer": output},
        )
        with Operations.context(context):
            for revision in reversed(list(scripts.walk_revisions())):
                revision.module.upgrade()

        sql = output.getvalue()
        for table in ("tasks", "codes", "similarities"):
            self.assertIn(f"CREATE TABLE {table}", sql)
        self.assertEqual(sql.count("ADD COLUMN gpt_rate_limit INTEGER"), 1)
        self.assertNotRegex(sql, r"(?mi)^\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b")


if __name__ == "__main__":
    unittest.main()
