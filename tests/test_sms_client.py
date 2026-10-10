import pytest

import sms_client


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("9876543210", "+919876543210"),
        ("+919876543210", "+919876543210"),
        ("+91 98765-43210", "+919876543210"),
        ("1234567890", None),
        ("+911234567890", None),
        ("+14155550123", None),
        ("person@example.com", None),
    ],
)
def test_normalize_phone_number_accepts_indian_mobile_numbers_only(value, expected):
    assert sms_client.normalize_phone_number(value) == expected


def test_match_message_is_tentative_and_includes_emoji():
    message = sms_client.build_match_message(
        "wallet", "the library", "2026-10-10"
    )

    assert "🔎" in message
    assert "may match" in message
    assert "Not confirmed" in message


def test_match_message_includes_finder_contact_only_with_consent():
    message = sms_client.build_match_message(
        "wallet",
        "the library",
        "2026-10-10",
        reporter_name="Riya",
        reporter_contact="+919876543210",
        share_contact=True,
    )
    private_message = sms_client.build_match_message(
        "wallet",
        "the library",
        "2026-10-10",
        reporter_name="Riya",
        reporter_contact="+919876543210",
        share_contact=False,
    )

    assert "Riya" in message
    assert "+919876543210" in message
    assert "Riya" not in private_message
    assert "+919876543210" not in private_message


def test_send_sms_requires_twilio_configuration(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)

    with pytest.raises(sms_client.SmsConfigurationError):
        sms_client.send_sms("+919876543210", "test")
