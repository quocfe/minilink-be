"""add_status_to_codes

Revision ID: a1b2c3d4e5f6
Revises: 50a58b641213
Create Date: 2026-04-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '50a58b641213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

verification_code_status = sa.Enum(
    'PENDING', 'VERIFIED', 'USED',
    name='verificationcodestatus',
)


def upgrade() -> None:
    # Create enum type
    verification_code_status.create(op.get_bind(), checkfirst=True)

    # Add status column (default PENDING for existing rows)
    op.add_column(
        'codes',
        sa.Column(
            'status',
            sa.Enum('PENDING', 'VERIFIED', 'USED', name='verificationcodestatus'),
            nullable=False,
            server_default='PENDING',
        ),
    )

    # Migrate existing data: is_used=True → USED, is_used=False → PENDING
    op.execute(
        "UPDATE codes SET status = 'USED' WHERE is_used = TRUE"
    )

    # Drop old column
    op.drop_column('codes', 'is_used')

    # Remove server_default now that data is migrated
    op.alter_column('codes', 'status', server_default=None)


def downgrade() -> None:
    # Re-add is_used column
    op.add_column(
        'codes',
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default='false'),
    )

    # Migrate back: USED → True, others → False
    op.execute(
        "UPDATE codes SET is_used = TRUE WHERE status = 'USED'"
    )

    # Drop status column
    op.drop_column('codes', 'status')

    # Drop enum type
    verification_code_status.drop(op.get_bind(), checkfirst=True)

    # Remove server_default
    op.alter_column('codes', 'is_used', server_default=None)

