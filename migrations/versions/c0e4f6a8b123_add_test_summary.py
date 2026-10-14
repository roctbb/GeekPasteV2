"""Keep test counts and public examples separate from large private suites."""
from alembic import op
import sqlalchemy as sa

revision = 'c0e4f6a8b123'
down_revision = 'b9d3f5a7c012'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('test_summary', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('tasks', 'test_summary')
