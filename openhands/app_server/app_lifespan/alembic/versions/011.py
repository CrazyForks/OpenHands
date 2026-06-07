"""Add sandbox_template to v1_remote_sandbox table

Revision ID: 011
Revises: 010
Create Date: 2026-06-07

Adds the Runtime API V2 discriminator column to the shared StoredRemoteSandbox
model. A non-null ``sandbox_template`` marks a sandbox as started via Runtime
API V2 (the warm-pool / template name) and routes its whole lifecycle to the V2
endpoint; NULL means a V1 sandbox.

The V2 opt-in feature itself is SaaS-only and OSS never populates this column.
It exists in the OSS chain solely to keep the shared model's schema consistent
for remote-runtime self-hosters, whose SELECTs would otherwise reference a
column that doesn't exist. Nullable and unused in OSS -> behaviour unchanged.
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: str | None = '010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sandbox_template column to v1_remote_sandbox table."""
    with op.batch_alter_table('v1_remote_sandbox') as batch_op:
        batch_op.add_column(sa.Column('sandbox_template', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove sandbox_template column from v1_remote_sandbox table."""
    with op.batch_alter_table('v1_remote_sandbox') as batch_op:
        batch_op.drop_column('sandbox_template')
