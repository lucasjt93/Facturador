"""add postal codes and payment terms days"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_postal_and_payment_terms_days"
down_revision = "0002_create_company"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clients", sa.Column("postal_code", sa.String(length=20), nullable=True))
    op.add_column("clients", sa.Column("payment_terms_days", sa.Integer(), nullable=True))
    op.add_column("company", sa.Column("postal_code", sa.String(length=20), nullable=True))
    op.add_column("company", sa.Column("payment_terms_days", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("company", "payment_terms_days")
    op.drop_column("company", "postal_code")
    op.drop_column("clients", "payment_terms_days")
    op.drop_column("clients", "postal_code")
