"""AUTO-3: optional Mailpit is free/local and not a paid ESP bake-in."""

from pathlib import Path


def compose_text() -> str:
    path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    return path.read_text(encoding="utf-8")


def test_mailpit_is_optional_profile_and_free_image() -> None:
    text = compose_text()
    lowered = text.lower()

    assert "mailpit:" in text
    assert 'profiles: ["mail"]' in text or "profiles: ['mail']" in text
    assert "axllent/mailpit" in text
    assert "8025" in text
    assert "1025" in text

    # No paid ESP images or SMTP vendors in compose.
    for banned in (
        "sendgrid",
        "mailgun",
        "postmark",
        "ses",
        "amazonaws",
        "smtp.sendgrid",
        "mailchimp",
    ):
        assert banned not in lowered
