"""create clients table"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_create_clients"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tax_id", sa.String(length=50), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_table("clients")
