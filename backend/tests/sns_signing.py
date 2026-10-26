import base64
import json
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import httpx2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from casero.identity.infrastructure.sns import SnsSignatureVerifier, string_to_sign

CERT_URL = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
SUBSCRIBE_URL = "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&Token=t"
VALIDITY = timedelta(days=1)


@cache
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@cache
def certificate_pem() -> bytes:
    key = signing_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    issued = datetime(2026, 1, 1, tzinfo=UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(issued)
        .not_valid_after(issued + VALIDITY)
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM)


def sign(message: dict[str, Any]) -> dict[str, Any]:
    signed = {**message, "SignatureVersion": "2", "SigningCertURL": CERT_URL}
    payload = string_to_sign(signed)
    assert payload is not None
    signature = signing_key().sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return {**signed, "Signature": base64.b64encode(signature).decode()}


def notification(topic_arn: str, event: dict[str, Any]) -> dict[str, Any]:
    return sign(
        {
            "Type": "Notification",
            "MessageId": "00000000-0000-0000-0000-000000000001",
            "TopicArn": topic_arn,
            "Message": json.dumps(event),
            "Timestamp": "2026-10-26T15:00:00.000Z",
        }
    )


def subscription_confirmation(topic_arn: str) -> dict[str, Any]:
    return sign(
        {
            "Type": "SubscriptionConfirmation",
            "MessageId": "00000000-0000-0000-0000-000000000002",
            "Token": "t",
            "TopicArn": topic_arn,
            "Message": "You have chosen to subscribe to the topic.",
            "SubscribeURL": SUBSCRIBE_URL,
            "Timestamp": "2026-10-26T15:00:00.000Z",
        }
    )


def permanent_bounce(*emails: str) -> dict[str, Any]:
    return {
        "notificationType": "Bounce",
        "bounce": {
            "bounceType": "Permanent",
            "bouncedRecipients": [{"emailAddress": email} for email in emails],
        },
    }


class FakeSns:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requested.append(str(request.url))
        if str(request.url) == CERT_URL:
            return httpx2.Response(200, content=certificate_pem())
        if str(request.url) == SUBSCRIBE_URL:
            return httpx2.Response(200)
        return httpx2.Response(404)

    def verifier(self) -> SnsSignatureVerifier:
        return SnsSignatureVerifier(httpx2.AsyncClient(transport=httpx2.MockTransport(self.handle)))
