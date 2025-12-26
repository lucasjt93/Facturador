"""create invoices table"""

from alembic import op
import sqlalchemy as sa

revision = "0006_create_invoices"
down_revision = "0005_drop_company_payment_terms_string"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("series", sa.String(length=20), nullable=True),
        sa.Column("number", sa.String(length=20), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="EUR"),
        sa.Column("igi_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=500), nullable=True),
    )


def downgrade():
    op.drop_table("invoices")
