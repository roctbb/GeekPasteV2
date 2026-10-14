"""Add web-configured input/output tests without changing existing checkers."""
from alembic import op
import sqlalchemy as sa


revision = 'a8c2e4f6b901'
down_revision = 'f3a5c7e9b1d4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('test_mode', sa.String(20), nullable=False,
                                   server_default='environment'))
    op.add_column('tasks', sa.Column('test_config', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('tasks', 'test_config')
    op.drop_column('tasks', 'test_mode')
