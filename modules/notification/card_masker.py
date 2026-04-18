"""Card masker: keep BIN (first 6) and last 4, mask middle. Example: 411111******1234."""
import re


def mask_card_number(card_number: str) -> str:
    digits = re.sub(r'[\s\-]', '', card_number)
    if len(digits) < 10:
        return '*' * len(digits)
    return digits[:6] + '*' * (len(digits) - 10) + digits[-4:]
