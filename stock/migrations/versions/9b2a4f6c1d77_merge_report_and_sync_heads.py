"""merge report and instrument sync heads

Revision ID: 9b2a4f6c1d77
Revises: 6f6f3eb7f2d1, 22819fd61e4d
Create Date: 2026-04-21 12:00:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "9b2a4f6c1d77"
down_revision: Union[str, Sequence[str], None] = ("6f6f3eb7f2d1", "22819fd61e4d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge two independent migration heads into a single linear head."""


def downgrade() -> None:
    """Split the merged head back into the two original branches."""
