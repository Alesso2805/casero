from datetime import timedelta
from uuid import UUID

DELETION_GRACE = timedelta(days=30)


def anonymized_email(user_id: UUID) -> str:
    return f"deleted+{user_id}@invalid"
