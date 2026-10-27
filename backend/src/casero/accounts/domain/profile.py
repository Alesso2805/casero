from dataclasses import dataclass, fields
from typing import Literal

TaxpayerKind = Literal["person", "estate"]
RucGroup = Literal["0", "1", "2-3", "4-5", "6-7", "8-9", "bc"]

GOOD_TAXPAYER_GROUP: RucGroup = "bc"
RUC_LENGTH = 11
# SUNAT doesn't publish the algorithm; the unit tests pin it with real RUCs, SUNAT's own included.
RUC_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
# Groups of the monthly schedule by the RUC's last digit (R.S. N.° 000281-2022/SUNAT).
GROUP_BY_LAST_DIGIT: dict[str, RucGroup] = {
    "0": "0",
    "1": "1",
    "2": "2-3",
    "3": "2-3",
    "4": "4-5",
    "5": "4-5",
    "6": "6-7",
    "7": "6-7",
    "8": "8-9",
    "9": "8-9",
}


def ruc_check_digit(first_ten: str) -> int:
    total = sum(int(digit) * weight for digit, weight in zip(first_ten, RUC_WEIGHTS, strict=True))
    return (11 - total % 11) % 10


def is_valid_ruc(ruc: str) -> bool:
    if len(ruc) != RUC_LENGTH or not ruc.isascii() or not ruc.isdigit():
        return False
    return ruc_check_digit(ruc[:-1]) == int(ruc[-1])


def ruc_group(ruc: str, good_taxpayer: bool) -> RucGroup:
    return GOOD_TAXPAYER_GROUP if good_taxpayer else GROUP_BY_LAST_DIGIT[ruc[-1]]


@dataclass(frozen=True)
class Profile:
    display_name: str
    taxpayer_kind: TaxpayerKind
    ruc: str | None
    ruc_group: RucGroup | None
    daily_digest: bool

    def changed_fields(self, other: Profile) -> list[str]:
        return [
            field.name
            for field in fields(self)
            if getattr(self, field.name) != getattr(other, field.name)
        ]
