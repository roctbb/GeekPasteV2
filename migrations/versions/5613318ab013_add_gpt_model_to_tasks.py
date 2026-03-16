"""add gpt_model to tasks

Revision ID: 5613318ab013
Revises: 437fbd10b406
Create Date: 2026-03-16 18:31:22.661740

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5613318ab013'
down_revision = '437fbd10b406'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('gpt_model', sa.String(), nullable=True))


def downgrade():
    op.drop_column('tasks', 'gpt_model')
