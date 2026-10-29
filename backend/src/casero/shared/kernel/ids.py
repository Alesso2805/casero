from uuid import UUID, uuid7

UUID_V7 = 7


def new_id() -> UUID:
    return uuid7()


def client_generated(value: UUID) -> UUID:
    """What the landlord creates gets its id from the client, as a uuid v7 (CLAUDE.md, rule 5)."""
    if value.version != UUID_V7:
        raise ValueError("the id must be a uuid v7 generated when the form opens")
    return value
