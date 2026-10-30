"""Parse declared dividend amounts without inventing cash-payment dates."""
from decimal import Decimal
import re


def dividend_amount(text):
    """Rupees per then-existing share, or None when terms cannot be parsed.

    'Including special dividend' is a component of the stated total; 'and
    special dividend' is additional. Original wording must accompany the result.
    """
    lowered = text.lower()
    if 'dividend' not in lowered and not re.search(r'\bdiv\b',lowered):
        return None
    total_text = re.split(r'\bincluding\b', lowered, maxsplit=1)[0]
    amounts = re.findall(r'\b(?:rs|re)\.?\s*[-:]?\s*(\d+(?:\.\d+)?)', total_text)
    if not amounts:
        # NSE sometimes omits the currency prefix, e.g. Dividend - 0.40 Per Share.
        amounts = re.findall(r'\bdividend\s*[-:]?\s*(\d+(?:\.\d+)?)\s*(?:/-)?\s*per\s',total_text)
    if not amounts:
        return None
    return float(sum((Decimal(x) for x in amounts),Decimal(0)))
