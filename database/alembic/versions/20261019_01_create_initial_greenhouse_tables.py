"""Create the initial greenhouse tables.

Revision ID: 20261019_01
Revises:
Create Date: 2026-10-19 21:33:43
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261019_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.create_index(
            "ix_alert_device_active", ["device_id", "active"], unique=False
        )
        batch_op.create_index(
            "ix_alert_device_started", ["device_id", "started_at"], unique=False
        )

    op.create_table(
        "command_logs",
        sa.Column("command_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("device", sa.String(length=16), nullable=False),
        sa.Column("requested_on", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("command_id"),
    )
    with op.batch_alter_table("command_logs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_command_device_requested",
            ["device_id", "requested_at"],
            unique=False,
        )
        batch_op.create_index("ix_command_status", ["status"], unique=False)

    op.create_table(
        "device_configs",
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("temp_on_c", sa.Float(), nullable=False),
        sa.Column("temp_off_c", sa.Float(), nullable=False),
        sa.Column("humidity_on_pct", sa.Float(), nullable=False),
        sa.Column("humidity_off_pct", sa.Float(), nullable=False),
        sa.Column("light_on_lux", sa.Float(), nullable=False),
        sa.Column("light_off_lux", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("device_id"),
    )

    op.create_table(
        "device_states",
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("fan", sa.Boolean(), nullable=False),
        sa.Column("mist", sa.Boolean(), nullable=False),
        sa.Column("lamp", sa.Boolean(), nullable=False),
        sa.Column("failsafe_active", sa.Boolean(), nullable=False),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_command_id", sa.String(length=64), nullable=True),
        sa.Column("last_command_result", sa.String(length=16), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("device_id"),
    )

    op.create_table(
        "telemetry_readings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("humidity_pct", sa.Float(), nullable=True),
        sa.Column("light_lux", sa.Float(), nullable=True),
        sa.Column("water_ok", sa.Boolean(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "humidity_pct IS NULL OR (humidity_pct >= 0 AND humidity_pct <= 100)",
            name="ck_telemetry_humidity_range",
        ),
        sa.CheckConstraint(
            "light_lux IS NULL OR light_lux >= 0",
            name="ck_telemetry_light_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("telemetry_readings", schema=None) as batch_op:
        batch_op.create_index(
            "ix_telemetry_device_received",
            ["device_id", "received_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("telemetry_readings", schema=None) as batch_op:
        batch_op.drop_index("ix_telemetry_device_received")
    op.drop_table("telemetry_readings")

    op.drop_table("device_states")
    op.drop_table("device_configs")

    with op.batch_alter_table("command_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_command_status")
        batch_op.drop_index("ix_command_device_requested")
    op.drop_table("command_logs")

    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.drop_index("ix_alert_device_started")
        batch_op.drop_index("ix_alert_device_active")
    op.drop_table("alerts")
