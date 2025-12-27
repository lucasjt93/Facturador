"""add is_deleted to clients"""

from alembic import op
import sqlalchemy as sa

revision = "0011_add_client_is_deleted"
down_revision = "0010_invoice_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "clients",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_clients_is_deleted", "clients", ["is_deleted"])


def downgrade():
    op.drop_index("ix_clients_is_deleted", table_name="clients")
    op.drop_column("clients", "is_deleted")
