from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parseaddr
from typing import Literal

import aiosmtplib

from casero.shared.kernel.clock import Clock
from casero.shared.kernel.email import Email, MailDeliveryError

SmtpSecurity = Literal["none", "starttls", "tls"]
SMTP_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    security: SmtpSecurity
    username: str | None
    password: str | None
    sender: str


class SmtpMailer:
    def __init__(self, settings: SmtpSettings, clock: Clock) -> None:
        self._settings = settings
        self._clock = clock

    def build(self, email: Email) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._settings.sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message["Date"] = format_datetime(self._clock.now())
        message["Message-ID"] = make_msgid(
            domain=parseaddr(self._settings.sender)[1].rpartition("@")[2]
        )
        if email.reply_to:
            message["Reply-To"] = email.reply_to
        message.set_content(email.text)
        return message

    async def send(self, email: Email) -> None:
        settings = self._settings
        try:
            await aiosmtplib.send(
                self.build(email),
                hostname=settings.host,
                port=settings.port,
                username=settings.username,
                password=settings.password,
                use_tls=settings.security == "tls",
                start_tls=settings.security == "starttls",
                timeout=SMTP_TIMEOUT_SECONDS,
            )
        except (aiosmtplib.SMTPException, OSError) as error:
            raise MailDeliveryError(type(error).__name__) from error
