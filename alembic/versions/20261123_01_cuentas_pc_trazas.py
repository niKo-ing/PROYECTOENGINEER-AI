"""Cuentas propias (reemplazan a Supabase Auth), «Mis computadores» y trazas de la IA (observabilidad).

Bases ya creadas con ``create_all`` pueden tener estas tablas: por eso cada una se crea solo si falta.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261123_01_cuentas_pc_trazas"
down_revision = "20260920_01_agent_tables"
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, 'user_accounts'):
        op.create_table('user_accounts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_user_accounts_email'), 'user_accounts', ['email'], unique=True)
    if not _has_table(bind, 'pc_builds'):
        op.create_table('pc_builds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('use_case', sa.String(length=32), nullable=True),
        sa.Column('budget_clp', sa.Integer(), nullable=True),
        sa.Column('items', sa.JSON(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('last_report', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_pc_builds_user_id'), 'pc_builds', ['user_id'], unique=False)
        op.create_index('ix_pc_builds_user_kind', 'pc_builds', ['user_id', 'kind'], unique=False)
    if not _has_table(bind, 'agent_runs'):
        op.create_table('agent_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=32), nullable=False),
        sa.Column('flow', sa.String(length=32), nullable=False),
        sa.Column('user_hash', sa.String(length=16), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('latency_ms', sa.Float(), nullable=False),
        sa.Column('cpu_ms', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error_type', sa.String(length=80), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('model', sa.String(length=64), nullable=True),
        sa.Column('llm_calls', sa.Integer(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('tool_calls', sa.Integer(), nullable=False),
        sa.Column('tool_errors', sa.Integer(), nullable=False),
        sa.Column('tools', sa.JSON(), nullable=False),
        sa.Column('steps', sa.Integer(), nullable=False),
        sa.Column('replans', sa.Integer(), nullable=False),
        sa.Column('plan_source', sa.String(length=16), nullable=True),
        sa.Column('input_chars', sa.Integer(), nullable=False),
        sa.Column('output_chars', sa.Integer(), nullable=False),
        sa.Column('input_preview', sa.String(length=240), nullable=True),
        sa.Column('guardrails', sa.JSON(), nullable=False),
        sa.Column('quality', sa.JSON(), nullable=False),
        sa.Column('eval_tag', sa.String(length=64), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_agent_runs_eval_tag'), 'agent_runs', ['eval_tag'], unique=False)
        op.create_index('ix_agent_runs_flow_started', 'agent_runs', ['flow', 'started_at'], unique=False)
        op.create_index(op.f('ix_agent_runs_run_id'), 'agent_runs', ['run_id'], unique=True)
        op.create_index(op.f('ix_agent_runs_started_at'), 'agent_runs', ['started_at'], unique=False)
        op.create_index(op.f('ix_agent_runs_user_hash'), 'agent_runs', ['user_hash'], unique=False)
    if not _has_table(bind, 'agent_spans'):
        op.create_table('agent_spans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=32), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('start_ms', sa.Float(), nullable=False),
        sa.Column('duration_ms', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['agent_runs.run_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_agent_spans_run_id'), 'agent_spans', ['run_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    for name in ("agent_spans", "agent_runs", "pc_builds", "user_accounts"):
        if _has_table(bind, name):
            op.drop_table(name)
