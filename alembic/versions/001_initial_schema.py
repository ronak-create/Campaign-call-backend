"""initial schema

Revision ID: 001
Create Date: 2025-01-01
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table('campaigns',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('created_at', sa.Text, nullable=False),
        sa.Column('status', sa.Text, server_default='pending'),
        sa.Column('total_calls', sa.Integer, server_default='0'),
        sa.Column('completed_calls', sa.Integer, server_default='0'),
        sa.Column('failed_calls', sa.Integer, server_default='0'),
        sa.Column('active', sa.Integer, server_default='1'),
    )
    op.create_table('calls',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('campaign_id', sa.Text, sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('phone', sa.Text, nullable=False),
        sa.Column('status', sa.Text, server_default='pending'),
        sa.Column('feedback', sa.Text),
        sa.Column('timestamp', sa.Text),
        sa.Column('recording_url', sa.Text),
        sa.Column('call_sid', sa.Text),
        sa.Column('conversation_id', sa.Text),
        sa.Column('duration', sa.Integer),
        sa.Column('error_message', sa.Text),
        sa.Column('retry_count', sa.Integer, server_default='0'),
        sa.Column('preferred_city', sa.Text),
        sa.Column('interested', sa.Text),
        sa.Column('transcript', sa.Text),
        sa.Column('analysis_status', sa.Text, server_default='pending'),
    )
    op.create_table('campaign_state',
        sa.Column('campaign_id', sa.Text, sa.ForeignKey('campaigns.id'), primary_key=True),
        sa.Column('is_running', sa.Integer, server_default='0'),
        sa.Column('current_index', sa.Integer, server_default='0'),
        sa.Column('analysis_status', sa.Text, server_default='not_started'),
        sa.Column('last_updated', sa.Text),
    )

def downgrade():
    op.drop_table('campaign_state')
    op.drop_table('calls')
    op.drop_table('campaigns')
