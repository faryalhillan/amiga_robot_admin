"""Activate the AMIGA-branded voucher layout for new generated PDFs."""

import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    active = (
        connection.execute(sa.text("SELECT version,created_by FROM voucher_templates WHERE is_active=true"))
        .mappings()
        .first()
    )
    bundled = {
        "v1.0",
        "v1.0-id",
        "v2.0-id",
        "v3.0-id",
        "v4.0-authorization",
        "v5.0-corporate",
    }
    activate = active is None or (active["version"] in bundled and active["created_by"] is None)
    if activate:
        op.execute("UPDATE voucher_templates SET is_active=false WHERE is_active=true")
    connection.execute(
        sa.text("""INSERT INTO voucher_templates
        (template_id,version,template_content,is_active,created_at)
        VALUES (:id,'v6.0-amiga-branded',:content,:active,now())"""),
        {
            "id": uuid.uuid4(),
            "active": activate,
            "content": (Path(__file__).resolve().parents[2] / "app/templates/voucher_default.html").read_text(
                encoding="utf-8"
            ),
        },
    )


def downgrade():
    # Keep historical template versions and generated vouchers intact.
    pass
