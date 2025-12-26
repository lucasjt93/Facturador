"""create invoice lines table"""

from alembic import op
import sqlalchemy as sa

revision = "0007_create_invoice_lines"
down_revision = "0006_create_invoices"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("qty", sa.Numeric(12, 2), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade():
    op.drop_table("invoice_lines")
