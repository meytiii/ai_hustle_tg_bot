"""Order number and reference code generator."""

import secrets
import string

# Unambiguous alphanumeric characters (excluding 0, O, 1, I to prevent customer confusion)
UNAMBIGUOUS_CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_order_number(prefix: str = "ASH", length: int = 5) -> str:
    """Generates a cryptographically random, unambiguous short order number.

    Example: ASH-7K2P9
    """
    code = "".join(secrets.choice(UNAMBIGUOUS_CHARS) for _ in range(length))
    return f"{prefix}-{code}"
