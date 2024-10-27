"""empty message

Revision ID: 8949571042ba
Revises: d58d8479fe79
Create Date: 2024-10-27 14:16:27.075060

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8949571042ba'
down_revision = 'd58d8479fe79'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('codes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('codes', schema=None) as batch_op:
        batch_op.drop_column('user_id')

    # ### end Alembic commands ###