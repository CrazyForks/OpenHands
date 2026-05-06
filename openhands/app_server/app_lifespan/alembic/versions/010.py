"""Add ACP session columns to conversation_metadata

Revision ID: 010
Revises: 009
Create Date: 2026-05-04 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'conversation_metadata',
        sa.Column('acp_session_id', sa.String(), nullable=True),
    )
    op.add_column(
        'conversation_metadata',
        sa.Column('acp_session_cwd', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversation_metadata', 'acp_session_cwd')
    op.drop_column('conversation_metadata', 'acp_session_id')
