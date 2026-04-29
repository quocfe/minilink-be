"""remove tokens from user

Revision ID: 2f8a1b2c3d4e
Revises: a1b2c3d4e5f6
Create Date: 2026-04-29 09:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f8a1b2c3d4e'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove access_token and refresh_token from users table
    op.drop_column('users', 'access_token')
    op.drop_column('users', 'refresh_token')


def downgrade() -> None:
    # Re-add access_token and refresh_token to users table
    op.add_column('users', sa.Column('access_token', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('refresh_token', sa.Text(), nullable=True))
