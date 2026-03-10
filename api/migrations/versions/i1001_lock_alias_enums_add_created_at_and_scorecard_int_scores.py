"""lock alias enums, add created_at fields, evidence category, and int score scale

Revision ID: i1001
Revises: h1002
Create Date: 2026-03-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i1001"
down_revision: Union[str, None] = "h1002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_scorecard_scores_convertible() -> None:
    bind = op.get_bind()
    invalid_fit = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM scorecards
            WHERE NOT (
                (fit_score >= 0.0 AND fit_score <= 1.0)
                OR (
                    fit_score >= 0.0
                    AND fit_score <= 100.0
                    AND fit_score = FLOOR(fit_score)
                )
            )
            """
        )
    ).scalar_one()
    invalid_intent = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM scorecards
            WHERE NOT (
                (intent_score >= 0.0 AND intent_score <= 1.0)
                OR (
                    intent_score >= 0.0
                    AND intent_score <= 100.0
                    AND intent_score = FLOOR(intent_score)
                )
            )
            """
        )
    ).scalar_one()
    if invalid_fit or invalid_intent:
        raise RuntimeError(
            "scorecards contain non-convertible score values; manual review required "
            "before migrating to INT 0..100"
        )


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.add_column(
        "approval_decisions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_check_constraint(
        "ck_account_aliases_alias_type",
        "account_aliases",
        "alias_type IN ('registry', 'domain', 'legal_name_normalized')",
    )
    op.create_check_constraint(
        "ck_contact_aliases_alias_type",
        "contact_aliases",
        "alias_type IN ('email_normalized', 'linkedin_url_normalized')",
    )

    op.add_column("evidence", sa.Column("category", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE evidence
        SET category = CASE
            WHEN lower(coalesce(provenance_json->>'category', '')) IN
                ('firmographic', 'persona_fit', 'trigger', 'technographic')
                THEN lower(provenance_json->>'category')
            WHEN lower(source_type) LIKE 'registry%' THEN 'firmographic'
            ELSE NULL
        END
        """
    )
    op.create_check_constraint(
        "ck_evidence_category",
        "evidence",
        "("
        "category IS NULL OR "
        "category IN ('firmographic', 'persona_fit', 'trigger', 'technographic')"
        ")",
    )

    _assert_scorecard_scores_convertible()
    op.drop_constraint("ck_scorecards_fit_score_range", "scorecards", type_="check")
    op.drop_constraint("ck_scorecards_intent_score_range", "scorecards", type_="check")
    op.alter_column(
        "scorecards",
        "fit_score",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        postgresql_using="""
        CASE
            WHEN fit_score >= 0.0 AND fit_score <= 1.0
                THEN CAST(FLOOR((fit_score * 100.0) + 0.5) AS INTEGER)
            WHEN fit_score >= 0.0 AND fit_score <= 100.0 AND fit_score = FLOOR(fit_score)
                THEN CAST(fit_score AS INTEGER)
            ELSE NULL
        END
        """,
    )
    op.alter_column(
        "scorecards",
        "intent_score",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        postgresql_using="""
        CASE
            WHEN intent_score >= 0.0 AND intent_score <= 1.0
                THEN CAST(FLOOR((intent_score * 100.0) + 0.5) AS INTEGER)
            WHEN intent_score >= 0.0 AND intent_score <= 100.0 AND intent_score = FLOOR(intent_score)
                THEN CAST(intent_score AS INTEGER)
            ELSE NULL
        END
        """,
    )
    op.create_check_constraint(
        "ck_scorecards_fit_score_range",
        "scorecards",
        "fit_score >= 0 AND fit_score <= 100",
    )
    op.create_check_constraint(
        "ck_scorecards_intent_score_range",
        "scorecards",
        "intent_score >= 0 AND intent_score <= 100",
    )


def downgrade() -> None:
    op.drop_constraint("ck_scorecards_intent_score_range", "scorecards", type_="check")
    op.drop_constraint("ck_scorecards_fit_score_range", "scorecards", type_="check")
    op.alter_column(
        "scorecards",
        "intent_score",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        postgresql_using="CAST(intent_score AS DOUBLE PRECISION) / 100.0",
    )
    op.alter_column(
        "scorecards",
        "fit_score",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        postgresql_using="CAST(fit_score AS DOUBLE PRECISION) / 100.0",
    )
    op.create_check_constraint(
        "ck_scorecards_fit_score_range",
        "scorecards",
        "fit_score >= 0.0 AND fit_score <= 1.0",
    )
    op.create_check_constraint(
        "ck_scorecards_intent_score_range",
        "scorecards",
        "intent_score >= 0.0 AND intent_score <= 1.0",
    )

    op.drop_constraint("ck_evidence_category", "evidence", type_="check")
    op.drop_column("evidence", "category")

    op.drop_constraint(
        "ck_contact_aliases_alias_type", "contact_aliases", type_="check"
    )
    op.drop_constraint(
        "ck_account_aliases_alias_type", "account_aliases", type_="check"
    )

    op.drop_column("approval_decisions", "created_at")
    op.drop_column("contacts", "created_at")
    op.drop_column("accounts", "created_at")
