"""create company table"""

from alembic import op
import sqlalchemy as sa

revision = "0002_create_company"
down_revision = "0001_create_clients"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("tax_id", sa.String(length=50), nullable=True),
        sa.Column("phone", sa.String(length=100), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("bank_account", sa.String(length=255), nullable=True),
        sa.Column("bank_swift", sa.String(length=255), nullable=True),
        sa.Column("payment_terms", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
    )


def downgrade():
    op.drop_table("company")
