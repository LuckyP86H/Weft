"""Table-driven tests for the scrubber: the core privacy rules, one case per row."""

import pytest

from weft.scrub import scrub


def categories(result):
    """Map a result's report to {category: count} for easy assertions."""
    return {r.category: r.count for r in result.redactions}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("my key is sk-abc123XYZ today", "my key is [REDACTED:credential] today"),
        ("token ghp_abcdefghijklmnopqrstuvwxyz0123", "token [REDACTED:credential]"),
        ("slack xoxb-1234567890-abcdef", "slack [REDACTED:credential]"),
        ("aws AKIAABCDEFGHIJKLMNOP key", "aws [REDACTED:credential] key"),
        ("Authorization: Bearer abc.def-ghi_123=", "Authorization: [REDACTED:credential]"),
        ("password: hunter2 is bad", "[REDACTED:credential] is bad"),
        ("API_KEY=abcd1234", "[REDACTED:credential]"),
        (
            "-----BEGIN RSA PRIVATE KEY-----\nMIIB\n-----END RSA PRIVATE KEY-----",
            "[REDACTED:credential]",
        ),
    ],
)
def test_credentials_are_redacted(text, expected):
    """Each credential shape is replaced by a visible marker."""
    assert scrub(text).scrubbed_text == expected


@pytest.mark.parametrize(
    "text",
    ["write to paul@example.com today", "a.b+tag@sub.example.co.uk"],
)
def test_emails_are_redacted(text):
    """Email addresses are replaced and counted once each."""
    result = scrub(text)
    assert "@" not in result.scrubbed_text
    assert categories(result) == {"email": 1}


@pytest.mark.parametrize(
    "text",
    ["call +1 415 555 0132 now", "tel: (415) 555-0132", "+44 20 7946 0958"],
)
def test_phone_numbers_are_redacted(text):
    """Common phone formats are redacted."""
    result = scrub(text)
    assert "[REDACTED:phone]" in result.scrubbed_text
    assert categories(result) == {"phone": 1}


@pytest.mark.parametrize(
    "text",
    [
        "meeting on 2026-10-14 at 09:30",
        "version 3.14.2 shipped",
        "port 8080 and 443",
        "I had 3 notes",
    ],
)
def test_ordinary_numbers_are_left_alone(text):
    """Dates, versions and short numbers are not mistaken for phone numbers."""
    result = scrub(text)
    assert result.scrubbed_text == text
    assert not result.redactions


def test_clean_text_passes_through_unchanged():
    """Text with nothing sensitive is returned as-is, with an empty report."""
    text = "Deterministic tools beat clever prompts for filing."
    result = scrub(text)
    assert result.scrubbed_text == text
    assert not result.redactions


def test_report_counts_each_category():
    """The report counts by category; it never includes the matched text."""
    text = "a@x.com and b@y.org, key sk-abc123XYZ"
    result = scrub(text)
    assert categories(result) == {"credential": 1, "email": 2}
    assert "a@x.com" not in repr(result.redactions)


def test_configured_terms_are_redacted_case_insensitively():
    """User-configured terms are matched literally, ignoring case."""
    result = scrub("Acme Corp rollout, acme corp budget", terms=["Acme Corp"])
    assert result.scrubbed_text == "[REDACTED:term] rollout, [REDACTED:term] budget"
    assert categories(result) == {"term": 2}


def test_longer_terms_win_over_shorter_ones():
    """A term that contains another term is redacted as one span."""
    result = scrub("Project Falcon Core", terms=["Falcon", "Project Falcon"])
    assert result.scrubbed_text == "[REDACTED:term] Core"
    assert categories(result) == {"term": 1}


def test_terms_are_escaped_not_treated_as_regex():
    """A term with regex metacharacters is matched literally."""
    result = scrub("cost is a+b today", terms=["a+b"])
    assert result.scrubbed_text == "cost is [REDACTED:term] today"


def test_empty_terms_are_ignored():
    """Blank entries in redact_terms must not match everywhere."""
    result = scrub("unchanged text", terms=["", ""])
    assert result.scrubbed_text == "unchanged text"
    assert not result.redactions
