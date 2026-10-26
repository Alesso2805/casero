CENTS_PER_SOL = 100


def format_soles(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    soles, rest = divmod(abs(cents), CENTS_PER_SOL)
    return f"{sign}S/ {soles:,}.{rest:02d}"
