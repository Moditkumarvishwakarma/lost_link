import os
import re
from typing import Optional

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client


class SmsConfigurationError(RuntimeError):
    """Raised when Twilio SMS credentials or sender number are missing."""


def normalize_phone_number(value: str) -> Optional[str]:
    number = re.sub(r"[\s().-]", "", str(value or ""))
    if re.fullmatch(r"[6-9]\d{9}", number):
        return f"+91{number}"
    if re.fullmatch(r"\+91[6-9]\d{9}", number):
        return number
    return None


def build_match_message(
    category: str,
    location: str,
    found_date: str,
    reporter_name: str = "",
    reporter_contact: str = "",
    share_contact: bool = False,
) -> str:
    message = (
        f"🔎 LostLink AI: A found {category} near {location} on {found_date} "
        "may match your lost-item report. Not confirmed—please verify with campus staff."
    )
    if share_contact and reporter_name.strip() and reporter_contact.strip():
        message += (
            f" Finder: {reporter_name.strip()}. "
            f"Contact: {reporter_contact.strip()}."
        )
    return message


def send_sms(to_number: str, message: str) -> str:
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
    if not account_sid or not auth_token or not from_number:
        raise SmsConfigurationError(
            "SMS is not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "and TWILIO_FROM_NUMBER in your environment or .env file."
        )

    response = Client(account_sid, auth_token).messages.create(
        body=message,
        from_=from_number,
        to=to_number,
    )
    return response.sid
