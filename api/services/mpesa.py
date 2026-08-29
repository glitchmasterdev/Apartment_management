"""Small server-only Safaricom Daraja STK Push client."""
import base64
from datetime import datetime
from urllib.parse import quote

import requests

from api.config import settings


def _base_url() -> str:
    return (
        "https://sandbox.safaricom.co.ke"
        if settings.MPESA_ENVIRONMENT == "sandbox"
        else "https://api.safaricom.co.ke"
    )


def configured() -> bool:
    return all((
        settings.MPESA_CONSUMER_KEY,
        settings.MPESA_CONSUMER_SECRET,
        settings.MPESA_SHORTCODE,
        settings.MPESA_PASSKEY,
        settings.MPESA_CALLBACK_SECRET,
        settings.APP_URL,
    ))


def normalise_kenyan_phone(phone: str) -> str:
    digits = "".join(char for char in str(phone or "") if char.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif digits.startswith("7") and len(digits) == 9:
        digits = "254" + digits
    if len(digits) != 12 or not digits.startswith("2547"):
        raise ValueError("Use a valid Kenyan M-Pesa number, for example 0712345678.")
    return digits


def _access_token() -> str:
    response = requests.get(
        f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials",
        auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
        timeout=20,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Safaricom did not return an access token.")
    return token


def initiate_stk_push(phone_number: str, amount: float, account_reference: str, description: str) -> dict:
    if not configured():
        raise RuntimeError("M-Pesa payments have not been configured.")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}".encode()
    ).decode()
    callback_url = (
        f"{settings.APP_URL.rstrip('/')}/api/payments/mpesa/stk-callback"
        f"?token={quote(settings.MPESA_CALLBACK_SECRET, safe='')}"
    )
    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(round(amount)),
        "PartyA": phone_number,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": callback_url,
        "AccountReference": account_reference[:12],
        "TransactionDesc": description[:13] or "Rent payment",
    }
    response = requests.post(
        f"{_base_url()}/mpesa/stkpush/v1/processrequest",
        headers={"Authorization": f"Bearer {_access_token()}"},
        json=payload,
        timeout=25,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("ResponseCode") != "0" or not result.get("CheckoutRequestID"):
        raise RuntimeError(result.get("errorMessage") or result.get("ResponseDescription") or "Safaricom could not start the payment.")
    return result
