"""add cascade relation for invoice_lines"""

from alembic import op
import sqlalchemy as sa

revision = "0008_add_cascade_invoice_lines"
down_revision = "0007_create_invoice_lines"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite requiere recrear la tabla para cambiar ondelete; batch con recreate.
    with op.batch_alter_table("invoice_lines", recreate="always") as batch_op:
        batch_op.create_foreign_key(
            "invoice_lines_invoice_id_fkey",
            "invoices",
            ["invoice_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade():
    with op.batch_alter_table("invoice_lines", recreate="always") as batch_op:
        batch_op.create_foreign_key(
            "invoice_lines_invoice_id_fkey",
            "invoices",
            ["invoice_id"],
            ["id"],
        )
