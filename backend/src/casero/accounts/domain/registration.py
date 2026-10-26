from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import UUID

RegistrationMode = Literal["closed", "invite", "open"]
DocumentKind = Literal["terms", "privacy", "sensitive_consent"]
REQUIRED_DOCUMENTS: tuple[DocumentKind, ...] = ("terms", "privacy", "sensitive_consent")
TRIAL_DAYS = 30
TRIAL_PLAN = "casero"
INVITE_LIFETIME = timedelta(days=14)


@dataclass(frozen=True)
class LegalVersion:
    kind: DocumentKind
    document_id: UUID
