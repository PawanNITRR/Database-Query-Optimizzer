"""Three small natural-language intents backed by transparent query templates."""
import re
from pathlib import Path

REPORTS = dict(re.findall(r'(sales|products|payments): `([^`]+)`',
    (Path(__file__).parent / 'static/examples.js').read_text(encoding='utf-8')))


def query_from_input(text):
    if re.match(r'^\s*(SELECT|WITH|DELETE|UPDATE|INSERT|DROP|CREATE|ALTER|TRUNCATE|--|/\*|\()', text, flags=re.I):
        return text, None
    lower = text.lower()
    if any(word in lower for word in ('payment', 'paid', 'transaction')):
        intent = 'payments'
    elif any(word in lower for word in ('product', 'category', 'units')):
        intent = 'products'
    elif any(word in lower for word in ('sales', 'revenue', 'dashboard', 'monthly')):
        intent = 'sales'
    else:
        raise ValueError('Enter SELECT SQL, or ask about monthly sales, products, or payments. Natural-language support uses these three demo reports.')
    query = REPORTS[intent]
    if 'weekly' in lower or 'week' in lower:
        # Fixed week within the synthetic demo's date range, shown to the user.
        dates = re.findall(r'2025-\d{2}-01', query)
        query = query.replace(dates[0], '2025-06-23').replace(dates[1], '2025-06-30')
        intent = 'weekly_' + intent
    return query, intent
