import re

def generate_account_number(landlord_id: str, building_name: str, unit_number: str) -> str:
    """Generates unique tenant account number: LND-{landlord_short}-{building_short}-{unit}"""
    landlord_short = landlord_id[-3:].upper() if len(landlord_id) >= 3 else "001"
    clean_bldg = re.sub(r'[^A-Za-z0-9]', '', building_name)[:4].upper()
    clean_unit = re.sub(r'[^A-Za-z0-9]', '', unit_number).upper()
    return f"LND-{landlord_short}-{clean_bldg}-{clean_unit}"

def calculate_tenant_ledger(monthly_rent: float, approved_payments: list) -> dict:
    """Calculates total paid, current balance/arrears status for partial payment tracking."""
    total_paid = sum(p.get("amount_paid", 0) for p in approved_payments if p.get("status") == "approved")
    balance = monthly_rent - total_paid
    is_in_arrears = balance > 0
    return {
        "monthly_rent": monthly_rent,
        "total_paid": total_paid,
        "balance": max(0.0, balance),
        "is_in_arrears": is_in_arrears,
        "status_label": f"In Arrears (KES {balance:,.2f})" if is_in_arrears else "Fully Paid"
    }
