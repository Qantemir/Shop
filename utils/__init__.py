from .security import check_admin_session

def format_price(price):
    """Format price with decimal points"""
    return f"{float(price):.2f}"

__all__ = [
    'format_price',
    'check_admin_session'
] 