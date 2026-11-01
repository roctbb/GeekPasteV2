"""Remember author names received during GeekClass login."""
from alembic import op
import sqlalchemy as sa

revision = 'd1f5a7b9c234'
down_revision = 'c0e4f6a8b123'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
    )


def downgrade():
    op.drop_table('user_profiles')
