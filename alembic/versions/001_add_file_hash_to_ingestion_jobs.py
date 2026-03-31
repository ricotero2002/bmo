"""Revision: add file_hash to ingestion_jobs

Revision ID: 001
Revises: 
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("file_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_ingestion_jobs_file_hash",
        "ingestion_jobs",
        ["file_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_file_hash", table_name="ingestion_jobs")
    op.drop_column("ingestion_jobs", "file_hash")
