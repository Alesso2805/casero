from dataclasses import dataclass


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    reply_to: str | None = None
    unsubscribe_url: str | None = None


class MailDeliveryError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
