RUC_LENGTH = 11
# SUNAT doesn't publish the algorithm; the unit tests pin it with real RUCs, SUNAT's own included.
RUC_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def ruc_check_digit(first_ten: str) -> int:
    total = sum(int(digit) * weight for digit, weight in zip(first_ten, RUC_WEIGHTS, strict=True))
    return (11 - total % 11) % 10


def is_valid_ruc(ruc: str) -> bool:
    if len(ruc) != RUC_LENGTH or not ruc.isascii() or not ruc.isdigit():
        return False
    return ruc_check_digit(ruc[:-1]) == int(ruc[-1])
