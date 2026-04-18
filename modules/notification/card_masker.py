"""Card number masking: show BIN (first 6) + last 4, mask middle with *.
Example: 4111111111111111 → 411111******1234
"""
import re


def mask_card_number(card_number: str) -> str:
    """Mask card number keeping first 6 (BIN) and last 4 digits visible.
    Input can be plain or spaced/dashed (e.g. '4111 1111 1111 1111').
    Returns: '411111******1234' format.
    """
    digits = re.sub(r'[\s\-]', '', card_number)
    if len(digits) < 10:
        return '*' * len(digits)
    return digits[:6] + '*' * (len(digits) - 10) + digits[-4:]
