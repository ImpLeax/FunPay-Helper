import pytest
from cryptography.fernet import Fernet

from app.db.crypto import PasswordCipher
from app.db.models import AccountRegion
from app.db.repository import AccountCredentials
from app.funpay.models import LotForm
from app.services.account_import import parse_account_lines
from app.services.lot_secrets import (
    detect_region,
    format_secret_line,
    parse_login,
    plan_status_sync,
    split_secrets,
)
from app.services.restocker import apply_secrets

ACCOUNT = AccountCredentials(1, "steamuser", "p|ss", "mail@example.com", "mailpass")


@pytest.mark.parametrize(
    ("description", "region"),
    [
        ("Аккаунт Steam, регион Украина", AccountRegion.UKR),
        ("Регион: КАЗАХСТАН", AccountRegion.KAZ),
        ("Steam США", AccountRegion.USA),
        ("Steam account", None),
    ],
)
def test_detect_region(description, region):
    assert detect_region(description) is region


def test_secret_line_round_trip():
    line = format_secret_line(ACCOUNT)
    assert line.startswith("Steam логин: steamuser | ")
    assert parse_login(line) == "steamuser"
    assert parse_login("manually added text") is None


def test_split_secrets_drops_blank_lines():
    assert split_secrets("a\n\n  \nb\n") == ["a", "b"]


def test_plan_status_sync_uses_exact_logins():
    plan = plan_status_sync(
        listed_logins={"bob_2", "carol"},
        selling={1: "bob", 2: "bob_2"},  # "bob" is a substring of "bob_2" but was sold
        unlisted={3: "carol", 4: "dave"},
    )
    assert plan.sold_ids == [1]
    assert plan.relisted_ids == [3]


def test_apply_secrets_enables_delivery():
    form = LotForm(1, {"secrets": "", "amount": "0"})
    apply_secrets(form, ["x", "y"])
    assert form.fields == {
        "secrets": "x\ny",
        "amount": "2",
        "active": "on",
        "auto_delivery": "on",
    }


def test_apply_secrets_empty_disables_delivery():
    form = LotForm(1, {"auto_delivery": "on", "active": "on"})
    apply_secrets(form, [])
    assert "auto_delivery" not in form.fields
    assert form.fields["amount"] == "0"


def test_parse_account_lines():
    result = parse_account_lines(
        ["login:pass:mail@x.com:mail:pass:with:colons", "", "broken:line", "a::b:c"]
    )
    assert len(result.accounts) == 1
    assert result.accounts[0].email_password == "mail:pass:with:colons"
    assert result.invalid_line_numbers == [3, 4]


def test_password_cipher_round_trip():
    cipher = PasswordCipher(Fernet.generate_key().decode())
    token = cipher.encrypt("secret")
    assert token != "secret"
    assert cipher.decrypt(token) == "secret"
    assert cipher.is_encrypted(token)
    assert not cipher.is_encrypted("secret")
