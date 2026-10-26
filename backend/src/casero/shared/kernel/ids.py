from uuid import UUID, uuid7


def new_id() -> UUID:
    return uuid7()
