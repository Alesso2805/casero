import base64
import binascii
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx2
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

AWS_SNS_HOST = re.compile(r"sns\.[a-z0-9-]+\.amazonaws\.com")

# Fields signed by SNS, in this order; Subject only when present
# (https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html).
SIGNED_FIELDS = {
    "Notification": ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"),
    "SubscriptionConfirmation": (
        "Message",
        "MessageId",
        "SubscribeURL",
        "Timestamp",
        "Token",
        "TopicArn",
        "Type",
    ),
    "UnsubscribeConfirmation": (
        "Message",
        "MessageId",
        "SubscribeURL",
        "Timestamp",
        "Token",
        "TopicArn",
        "Type",
    ),
}


def is_sns_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    return parts.scheme == "https" and AWS_SNS_HOST.fullmatch(parts.hostname or "") is not None


def string_to_sign(message: Mapping[str, Any]) -> bytes | None:
    fields = SIGNED_FIELDS.get(str(message.get("Type")))
    if fields is None:
        return None
    parts = []
    for field in fields:
        value = message.get(field)
        if value is None and field == "Subject":
            continue
        if not isinstance(value, str):
            return None
        parts.append(f"{field}\n{value}\n")
    return "".join(parts).encode()


class SnsSignatureVerifier:
    """Checks SNS signatures. The topic must use SignatureVersion 2 (SHA-256)."""

    def __init__(self, client: httpx2.AsyncClient) -> None:
        self._client = client
        self._keys: dict[str, rsa.RSAPublicKey] = {}

    async def verify(self, message: Mapping[str, Any]) -> bool:
        cert_url = message.get("SigningCertURL")
        payload = string_to_sign(message)
        if message.get("SignatureVersion") != "2" or payload is None:
            return False
        if not is_sns_url(cert_url) or not str(cert_url).endswith(".pem"):
            return False
        try:
            signature = base64.b64decode(str(message.get("Signature", "")), validate=True)
            key = await self._public_key(str(cert_url))
            key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
        except binascii.Error, InvalidSignature, ValueError, httpx2.HTTPError:
            return False
        return True

    async def confirm(self, subscribe_url: str) -> None:
        if not is_sns_url(subscribe_url):
            raise ValueError("SubscribeURL is not an SNS endpoint")
        response = await self._client.get(subscribe_url)
        response.raise_for_status()

    async def _public_key(self, cert_url: str) -> rsa.RSAPublicKey:
        if cert_url not in self._keys:
            response = await self._client.get(cert_url)
            response.raise_for_status()
            key = x509.load_pem_x509_certificate(response.content).public_key()
            if not isinstance(key, rsa.RSAPublicKey):
                raise ValueError("SNS signs with RSA")
            self._keys[cert_url] = key
        return self._keys[cert_url]
