CENTS_PER_SOL = 100
BASIS_POINTS = 10_000


def format_soles(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    soles, rest = divmod(abs(cents), CENTS_PER_SOL)
    return f"{sign}S/ {soles:,}.{rest:02d}"


def round_half_up_to_sol(numerator: int, denominator: int = 1) -> int:
    """Round numerator / denominator céntimos to whole soles, half up, and return céntimos."""
    if numerator < 0 or denominator <= 0:
        raise ValueError("Only non-negative amounts and positive denominators")
    unit = denominator * CENTS_PER_SOL
    return (2 * numerator + unit) // (2 * unit) * CENTS_PER_SOL
