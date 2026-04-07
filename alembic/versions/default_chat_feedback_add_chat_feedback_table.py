"""add_chat_feedback_table

Revision ID: default_chat_feedback
Revises: 59d3d7658f0b
Create Date: 2026-04-05 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from src.providers.database.models import GUID, JSONText

# revision identifiers, used by Alembic.
revision = 'default_chat_feedback'
down_revision = '59d3d7658f0b'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('chat_feedback',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('thread_id', sa.String(length=255), nullable=False),
        sa.Column('message_id', sa.String(length=255), nullable=True),
        sa.Column('user_prompt', sa.Text(), nullable=True),
        sa.Column('ai_response', sa.Text(), nullable=True),
        sa.Column('tools_used', JSONText(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('user_correction', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_feedback_thread_id'), 'chat_feedback', ['thread_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_chat_feedback_thread_id'), table_name='chat_feedback')
    op.drop_table('chat_feedback')
