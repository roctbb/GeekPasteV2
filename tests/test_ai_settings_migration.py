from flask_migrate import upgrade, downgrade
import sqlalchemy as sa

from test_schema_migrations import database_at, DEPLOYED_HEAD, MIGRATIONS


def test_ai_settings_upgrade_persists_data_and_can_be_reapplied():
    with database_at(DEPLOYED_HEAD, rate_limit_exists=True) as engine:
        upgrade(directory=str(MIGRATIONS))
        columns = {column['name'] for column in sa.inspect(engine).get_columns('ai_settings')}
        assert columns == {'id', 'encrypted_config', 'updated_by', 'updated_at'}
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO ai_settings (id, encrypted_config, updated_by) VALUES (1, 'encrypted', 42)"))
        upgrade(directory=str(MIGRATIONS))
        with engine.connect() as connection:
            assert connection.execute(sa.text('SELECT encrypted_config, updated_by FROM ai_settings')).one() == ('encrypted', 42)
            assert connection.execute(sa.text('SELECT id, name, gpt_model, gpt_rate_limit FROM tasks')).one() == (1, 'Existing task', 'custom', 12)
        downgrade(directory=str(MIGRATIONS), revision='a8c2e4f6b901')
        assert not sa.inspect(engine).has_table('ai_settings')
        with engine.connect() as connection:
            assert connection.execute(sa.text('SELECT name FROM tasks')).scalar_one() == 'Existing task'
