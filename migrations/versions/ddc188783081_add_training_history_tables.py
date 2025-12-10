"""add training history tables

Revision ID: ddc188783081
Revises: 
Create Date: 2025-12-09 17:32:28.100761

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ddc188783081'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Preserve existing schema; only ensure training history tables exist
    op.execute("""
    CREATE TABLE IF NOT EXISTS training_runs (
        id SERIAL PRIMARY KEY,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP,
        user_id INTEGER REFERENCES users(id),
        filename VARCHAR(255),
        row_count INTEGER,
        col_text VARCHAR(255),
        col_label VARCHAR(255),
        is_applied BOOLEAN DEFAULT FALSE,
        word2vec_model_path VARCHAR(512),
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS training_metrics (
        id SERIAL PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES training_runs(id) ON DELETE CASCADE,
        model_name VARCHAR(50) NOT NULL,
        accuracy FLOAT,
        precision FLOAT,
        recall FLOAT,
        f1 FLOAT,
        confusion_matrix JSON
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_runs_is_applied ON training_runs(is_applied);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_runs_finished_at ON training_runs(finished_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_metrics_run_id ON training_metrics(run_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_training_metrics_model_name ON training_metrics(model_name);")


def downgrade():
    # No-op: preserve schema
    pass
