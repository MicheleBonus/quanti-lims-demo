"""Tests for app utility functions."""


def test_parse_de_date_valid():
    from app import parse_de_date
    assert parse_de_date("14.10.2026") == "2026-10-14"


def test_parse_de_date_iso_passthrough():
    from app import parse_de_date
    assert parse_de_date("2026-10-14") == "2026-10-14"


def test_parse_de_date_blank():
    from app import parse_de_date
    assert parse_de_date("") is None
    assert parse_de_date(None) is None


def test_parse_de_date_invalid():
    from app import parse_de_date
    assert parse_de_date("not-a-date") is None
