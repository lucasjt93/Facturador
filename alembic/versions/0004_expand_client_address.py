"""expand client address fields"""

from alembic import op
import sqlalchemy as sa

revision = "0004_expand_client_address"
down_revision = "0003_add_postal_and_payment_terms_days"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clients", sa.Column("address_line1", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("address_line2", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("city", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("country", sa.String(length=100), nullable=True))
    op.add_column("clients", sa.Column("phone", sa.String(length=100), nullable=True))


def downgrade():
    op.drop_column("clients", "phone")
    op.drop_column("clients", "country")
    op.drop_column("clients", "city")
    op.drop_column("clients", "address_line2")
    op.drop_column("clients", "address_line1")
