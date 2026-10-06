"""0001 initial schema — all Radar tables.

Revision ID: 0001
Revises: None
Create Date: 2026-10-06

Mirrors CONTRACT.md §2 and radar_api.models exactly.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

TSTZ = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    # --- repositories ------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("created_at", TSTZ, nullable=False),
        sa.Column("pushed_at", TSTZ, nullable=True),
        sa.Column("detected_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("license", sa.Text(), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fork", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("current_stars", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("current_forks", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("topics", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("poll_interval_seconds", sa.Integer(), server_default=sa.text("21600"), nullable=False),
        sa.Column("next_poll_at", TSTZ, nullable=True),
        sa.Column("last_snapshot_at", TSTZ, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_id", name="uq_repositories_github_id"),
        sa.UniqueConstraint("full_name", name="uq_repositories_full_name"),
    )
    op.create_index("ix_repositories_github_id", "repositories", ["github_id"])
    op.create_index("ix_repositories_full_name", "repositories", ["full_name"])
    op.create_index("ix_repositories_status", "repositories", ["status"])
    op.create_index("ix_repositories_category", "repositories", ["category"])
    op.create_index("ix_repositories_language", "repositories", ["language"])
    op.create_index(
        "ix_repositories_current_stars_desc",
        "repositories",
        [sa.text("current_stars DESC")],
    )

    # --- repository_snapshots ----------------------------------------------
    op.create_table(
        "repository_snapshots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("ts", TSTZ, nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("forks", sa.Integer(), nullable=False),
        sa.Column("watchers", sa.Integer(), nullable=False),
        sa.Column("open_issues", sa.Integer(), nullable=False),
        sa.Column("open_prs", sa.Integer(), nullable=False),
        sa.Column("contributors_count", sa.Integer(), nullable=True),
        sa.Column("commit_count_7d", sa.Integer(), nullable=True),
        sa.Column("has_release_14d", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "ts", name="uq_repository_snapshots_repo_ts"),
    )
    op.create_index(
        "ix_repository_snapshots_repo_ts",
        "repository_snapshots",
        ["repository_id", sa.text("ts DESC")],
    )

    # --- scores -------------------------------------------------------------
    op.create_table(
        "scores",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("ts", TSTZ, nullable=False),
        sa.Column("star_velocity_1h", sa.Double(), nullable=True),
        sa.Column("star_velocity_6h", sa.Double(), nullable=True),
        sa.Column("star_velocity_24h", sa.Double(), nullable=True),
        sa.Column("star_velocity_7d", sa.Double(), nullable=True),
        sa.Column("acceleration", sa.Double(), nullable=True),
        sa.Column("relative_growth", sa.Double(), nullable=True),
        sa.Column("fork_velocity_24h", sa.Double(), nullable=True),
        sa.Column("fork_star_ratio", sa.Double(), nullable=True),
        sa.Column("activity_score", sa.Double(), nullable=True),
        sa.Column("age_bonus", sa.Double(), nullable=True),
        sa.Column("breakout_score", sa.Double(), nullable=False),
        sa.Column("organic_score", sa.Double(), nullable=True),
        sa.Column("hype_risk", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("score_breakdown", postgresql.JSONB(), nullable=False),
        sa.Column("scoring_version", sa.Text(), server_default=sa.text("'v1'"), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "ts", name="uq_scores_repo_ts"),
    )
    op.create_index("ix_scores_repo_ts", "scores", ["repository_id", sa.text("ts DESC")])
    op.create_index(
        "ix_scores_breakout_ts", "scores", [sa.text("breakout_score DESC"), sa.text("ts DESC")]
    )

    # --- detections ----------------------------------------------------------
    op.create_table(
        "detections",
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("first_detected_at", TSTZ, nullable=False),
        sa.Column("stars_at_detection", sa.Integer(), nullable=False),
        sa.Column("first_emerging_at", TSTZ, nullable=True),
        sa.Column("first_rising_at", TSTZ, nullable=True),
        sa.Column("first_breakout_at", TSTZ, nullable=True),
        sa.Column("first_viral_at", TSTZ, nullable=True),
        sa.Column("peak_score", sa.Double(), nullable=True),
        sa.Column("peak_at", TSTZ, nullable=True),
        sa.Column("growth_since_detection", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("repository_id"),
    )

    # --- rankings ------------------------------------------------------------
    op.create_table(
        "rankings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column("ts", TSTZ, nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket", "ts", "rank", name="uq_rankings_bucket_ts_rank"),
    )
    op.create_index("ix_rankings_bucket_ts_rank", "rankings", ["bucket", "ts", "rank"])

    # --- corpus_stats ---------------------------------------------------------
    op.create_table(
        "corpus_stats",
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("median", sa.Double(), nullable=False),
        sa.Column("mad", sa.Double(), nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("metric"),
    )

    # --- api_request_stats ------------------------------------------------------
    op.create_table(
        "api_request_stats",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("ts", TSTZ, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_request_stats_ts", "api_request_stats", ["ts"])

    # --- external_mentions -----------------------------------------------------
    op.create_table(
        "external_mentions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("ts", TSTZ, nullable=True),
        sa.Column("score", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_mentions_repo_ts", "external_mentions", ["repository_id", "ts"])


def downgrade() -> None:
    op.drop_index("ix_api_request_stats_ts", table_name="api_request_stats")
    op.drop_table("api_request_stats")

    op.drop_index("ix_external_mentions_repo_ts", table_name="external_mentions")
    op.drop_table("external_mentions")

    op.drop_table("corpus_stats")

    op.drop_index("ix_rankings_bucket_ts_rank", table_name="rankings")
    op.drop_table("rankings")

    op.drop_table("detections")

    op.drop_index("ix_scores_breakout_ts", table_name="scores")
    op.drop_index("ix_scores_repo_ts", table_name="scores")
    op.drop_table("scores")

    op.drop_index("ix_repository_snapshots_repo_ts", table_name="repository_snapshots")
    op.drop_table("repository_snapshots")

    op.drop_index("ix_repositories_current_stars_desc", table_name="repositories")
    op.drop_index("ix_repositories_language", table_name="repositories")
    op.drop_index("ix_repositories_category", table_name="repositories")
    op.drop_index("ix_repositories_status", table_name="repositories")
    op.drop_index("ix_repositories_full_name", table_name="repositories")
    op.drop_index("ix_repositories_github_id", table_name="repositories")
    op.drop_table("repositories")
