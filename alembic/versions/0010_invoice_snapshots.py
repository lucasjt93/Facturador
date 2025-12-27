"""add invoice snapshots"""

from alembic import op
import sqlalchemy as sa

revision = "0010_invoice_snapshots"
down_revision = "0009_invoice_numbering"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("client_name_snapshot", sa.String(length=255), nullable=True))
    op.add_column("invoices", sa.Column("client_tax_id_snapshot", sa.String(length=50), nullable=True))
    op.add_column("invoices", sa.Column("subtotal_snapshot", sa.Numeric(12, 2), nullable=True))
    op.add_column("invoices", sa.Column("igi_amount_snapshot", sa.Numeric(12, 2), nullable=True))
    op.add_column("invoices", sa.Column("total_snapshot", sa.Numeric(12, 2), nullable=True))
    op.add_column("invoices", sa.Column("payment_terms_days_applied", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("igi_rate_snapshot", sa.Numeric(5, 2), nullable=True))


def downgrade():
    op.drop_column("invoices", "igi_rate_snapshot")
    op.drop_column("invoices", "payment_terms_days_applied")
    op.drop_column("invoices", "total_snapshot")
    op.drop_column("invoices", "igi_amount_snapshot")
    op.drop_column("invoices", "subtotal_snapshot")
    op.drop_column("invoices", "client_tax_id_snapshot")
    op.drop_column("invoices", "client_name_snapshot")
