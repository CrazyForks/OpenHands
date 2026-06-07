"""Add Runtime API V2 opt-in columns

Adds the per-user opt-in for routing sandboxes through Runtime API V2 (SaaS
only) and the per-sandbox version discriminator:

- ``user.use_runtime_v2`` (BOOLEAN): whether the user opted into V2. Added with
  ``server_default false`` so existing rows backfill to opted-out and
  SaasSettingsStore.load() reads a real bool (never NULL) for the non-optional
  ``Settings.use_runtime_v2`` field — mirrors ``user.enable_sound_notifications``.
- ``user.warm_runtime_config`` (VARCHAR, nullable): the chosen SandboxWarmPool /
  ``sandbox_template`` name. Maps to ``Settings.warm_runtime_config`` (Optional,
  so NULL is fine). Mirrors the existing ``sandbox_grouping_strategy`` column.
- ``v1_remote_sandbox.sandbox_template`` (VARCHAR, nullable): non-null marks a
  sandbox as started via V2, routing its lifecycle to the V2 endpoint.

SaasSettingsStore maps user columns to the Settings model by name on both read
and write, so no store code changes are needed. No backfill beyond the boolean
default: existing rows read back as the Settings defaults and as V1 sandboxes,
leaving current behaviour unchanged.

Revision ID: 118
Revises: 117
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '118'
down_revision: Union[str, None] = '117'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user',
        sa.Column(
            'use_runtime_v2',
            sa.Boolean(),
            nullable=True,
            server_default=sa.text('false'),
        ),
    )
    op.add_column(
        'user',
        sa.Column('warm_runtime_config', sa.String(), nullable=True),
    )
    op.add_column(
        'v1_remote_sandbox',
        sa.Column('sandbox_template', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('v1_remote_sandbox', 'sandbox_template')
    op.drop_column('user', 'warm_runtime_config')
    op.drop_column('user', 'use_runtime_v2')
