"""migrate payment terms to days and drop legacy column"""

from alembic import op
import sqlalchemy as sa

revision = "0005_drop_company_payment_terms_string"
down_revision = "0004_expand_client_address"
branch_labels = None
depends_on = None


def upgrade():
    # Move numeric values from legacy string column into payment_terms_days if present.
    op.execute(
        """
        UPDATE company
        SET payment_terms_days = CAST(payment_terms AS INTEGER)
        WHERE payment_terms IS NOT NULL
          AND TRIM(payment_terms) != ''
          AND payment_terms GLOB '[0-9]*'
        """
    )
    with op.batch_alter_table("company") as batch_op:
        batch_op.drop_column("payment_terms")


def downgrade():
    with op.batch_alter_table("company") as batch_op:
        batch_op.add_column(sa.Column("payment_terms", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE company
        SET payment_terms = CAST(payment_terms_days AS VARCHAR)
        WHERE payment_terms_days IS NOT NULL
        """
    )
