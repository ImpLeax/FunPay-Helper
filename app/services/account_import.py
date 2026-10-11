from dataclasses import dataclass, field

from app.db.repository import NewAccount


@dataclass(slots=True)
class ImportResult:
    accounts: list[NewAccount] = field(default_factory=list)
    invalid_line_numbers: list[int] = field(default_factory=list)


def parse_account_lines(lines: list[str]) -> ImportResult:
    """Parse `login:password:email:email_password` lines.

    The email password is the last field, so it may itself contain ':'.
    Line numbers in the result are 1-based, relative to `lines`.
    """
    result = ImportResult()
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split(":", 3)
        if len(parts) != 4 or not all(part.strip() for part in parts):
            result.invalid_line_numbers.append(number)
            continue
        login, password, email, email_password = (part.strip() for part in parts)
        result.accounts.append(NewAccount(login, password, email, email_password))
    return result
