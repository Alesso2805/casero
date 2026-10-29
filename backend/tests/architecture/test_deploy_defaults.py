from pathlib import Path

DEPLOY_COMPOSE = Path(__file__).parents[3] / "infra" / "deploy" / "docker-compose.yml"


def test_production_registration_is_closed_unless_the_owner_opens_it() -> None:
    """CI's Edge job opens registration for the E2E; the deployed default must stay closed."""
    assert "REGISTRATION_MODE: ${REGISTRATION_MODE:-closed}" in DEPLOY_COMPOSE.read_text(
        encoding="utf-8"
    )
