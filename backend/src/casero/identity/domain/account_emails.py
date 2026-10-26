from datetime import datetime, timedelta
from typing import Literal

from casero.shared.kernel.email import Email

TokenPurpose = Literal["verify_email", "reset_password"]

VERIFICATION_LIFETIME = timedelta(days=7)
RESET_LIFETIME = timedelta(minutes=30)
UNVERIFIED_GRACE = timedelta(days=7)
VERIFICATION_EMAILS_PER_HOUR = 3
RESET_EMAILS_PER_HOUR = 3


def verification_email(to: str, link: str) -> Email:
    text = (
        "Hola:\n\n"
        "Para confirmar tu correo en Casero, abre este enlace:\n\n"
        f"{link}\n\n"
        "El enlace vence en 7 días. Si no creaste una cuenta en Casero, ignora este correo.\n"
    )
    return Email(to=to, subject="Confirma tu correo en Casero", text=text)


def password_reset_email(to: str, link: str) -> Email:
    text = (
        "Hola:\n\n"
        "Recibimos un pedido para cambiar tu contraseña de Casero. Para elegir una nueva, "
        "abre este enlace:\n\n"
        f"{link}\n\n"
        "Vence en 30 minutos y sirve una sola vez. Si no lo pediste, ignora este correo: "
        "tu contraseña no cambia.\n"
    )
    return Email(to=to, subject="Cambia tu contraseña de Casero", text=text)


def verify_by(created_at: datetime, email_verified: bool) -> datetime | None:
    """Unverified accounts can use the app for UNVERIFIED_GRACE after registering (SPEC)."""
    return None if email_verified else created_at + UNVERIFIED_GRACE


def access_blocked(created_at: datetime, email_verified: bool, now: datetime) -> bool:
    deadline = verify_by(created_at, email_verified)
    return deadline is not None and now >= deadline
