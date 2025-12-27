"""add invoice numbering and sequence"""

from alembic import op
import sqlalchemy as sa

revision = "0009_invoice_numbering"
down_revision = "0008_add_cascade_invoice_lines"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS invoice_sequences")
    op.create_table(
        "invoice_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year_full", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("year_full"),
    )
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("invoices")}
    if "number" not in columns:
        op.add_column("invoices", sa.Column("number", sa.Integer(), nullable=True))
    if "invoice_number" not in columns:
        op.add_column("invoices", sa.Column("invoice_number", sa.String(length=20), nullable=True))
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("invoices")}
    if "idx_invoice_number_unique" not in existing_indexes:
        op.create_index(
            "idx_invoice_number_unique",
            "invoices",
            ["invoice_number"],
            unique=True,
        )


def downgrade():
    op.drop_index("idx_invoice_number_unique", table_name="invoices")
    op.drop_column("invoices", "invoice_number")
    op.drop_column("invoices", "number")
    op.drop_table("invoice_sequences")
