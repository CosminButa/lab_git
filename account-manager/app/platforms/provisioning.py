"""Step-by-step provisioning with explicit verification after every change.

Every operation returns a Report: an ordered list of steps, each with a status
(ok / exists / skipped / error) and a message, so the operator sees exactly what
happened and what was verified.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from ..security import EMAIL_RE, USERNAME_RE, generate_password
from .base import PlatformClient, PlatformError, PlatformUser

OK, EXISTS, SKIPPED, ERROR = "ok", "exists", "skipped", "error"


@dataclass
class Step:
    name: str
    status: str
    message: str


@dataclass
class Report:
    platform: str
    username: str
    steps: list[Step] = field(default_factory=list)
    user: PlatformUser | None = None
    created: bool = False
    password: str | None = None  # set only when a new password was actually applied; shown once

    def add(self, name: str, status: str, message: str) -> None:
        self.steps.append(Step(name, status, message))

    def skip(self, names: list[str], reason: str = "Nu s-a încercat.") -> Report:
        for name in names:
            self.add(name, SKIPPED, reason)
        return self

    @property
    def has_errors(self) -> bool:
        return any(s.status == ERROR for s in self.steps)

    @property
    def outcome(self) -> str:
        return ERROR if self.has_errors else OK

    def summary(self) -> str:
        return "; ".join(f"{s.name}={s.status}" for s in self.steps)


def _lookup(client: PlatformClient, report: Report, username: str) -> PlatformUser | None | bool:
    """Read the user. Returns the user, None when absent, or False when the platform failed."""
    try:
        return client.user_exists(username)
    except PlatformError as exc:
        report.add("Verificare utilizator", ERROR, str(exc))
        return False


def add_to_group(client: PlatformClient, report: Report, user: PlatformUser, group_id: str) -> None:
    """Add `user` to a group, verifying the group exists, current membership and the result."""
    label = f"Grup {group_id}"
    try:
        group = client.find_group(group_id)
        if group is None:
            report.add(label, ERROR, f"Grupul '{group_id}' nu există în {client.label}.")
            return
        if any(g.id == group.id for g in user.groups):
            report.add(label, EXISTS, f"'{user.username}' este deja membru în '{group.name}'.")
            return
        client.add_to_group(user.username, group.id)
        user.groups = client.get_user(user.username).groups  # read back
    except PlatformError as exc:
        report.add(label, ERROR, str(exc))
        return
    if any(g.id == group.id for g in user.groups):
        report.add(label, OK, f"'{user.username}' a fost adăugat și verificat în '{group.name}'.")
    else:
        report.add(label, ERROR, f"Platforma a acceptat cererea, dar '{user.username}' nu apare în '{group.name}'.")


def provision_user(
    client: PlatformClient, username: str, email: str, first_name: str, last_name: str, password: str | None, groups: list[str]
) -> Report:
    """Create a user (if missing) and add it to the requested groups, verifying each step."""
    report = Report(client.key, username)
    group_steps = [f"Grup {g}" for g in groups]
    try:
        client.health()
    except PlatformError as exc:
        report.add("Conexiune", ERROR, str(exc))
        return report.skip(["Creare utilizator", *group_steps], "Nu s-a încercat: platforma nu răspunde.")
    report.add("Conexiune", OK, f"{client.label} răspunde.")

    user = _lookup(client, report, username)
    if user is False:
        return report.skip(["Creare utilizator", *group_steps])
    if user:
        report.add("Creare utilizator", EXISTS, f"Utilizatorul '{username}' există deja în {client.label}; nu a fost creat din nou.")
    else:
        try:
            client.create_user(username, email, first_name, last_name, password)
        except PlatformError as exc:
            report.add("Creare utilizator", ERROR, str(exc))
            return report.skip(group_steps, "Nu s-a încercat: utilizatorul nu a fost creat.")
        report.add("Creare utilizator", OK, f"Cererea de creare pentru '{username}' a fost acceptată.")
        user = _lookup(client, report, username)
        if not user:
            if user is None:
                report.add("Verificare utilizator", ERROR, f"Utilizatorul '{username}' nu a fost găsit după creare.")
            return report.skip(group_steps, "Nu s-a încercat: utilizatorul nu a putut fi verificat.")
        report.add("Verificare utilizator", OK, f"Utilizatorul '{username}' există și este {'activ' if user.enabled else 'dezactivat'}.")
        report.created, report.password = True, password

    report.user = user
    for group_id in groups:
        add_to_group(client, report, user, group_id)
    return report


def assign_group(client: PlatformClient, username: str, group_id: str) -> Report:
    """Add an existing user to a group, with the same verification steps."""
    report = Report(client.key, username)
    user = _lookup(client, report, username)
    if user is False:
        return report.skip([f"Grup {group_id}"])
    if user is None:
        report.add("Verificare utilizator", ERROR, f"Utilizatorul '{username}' nu există în {client.label}; nu poate fi asociat grupului.")
        return report.skip([f"Grup {group_id}"])
    report.add("Verificare utilizator", OK, f"Utilizatorul '{username}' există.")
    report.user = user
    add_to_group(client, report, user, group_id)
    return report


def reset_password(client: PlatformClient, username: str) -> Report:
    """Set a new generated password on an existing user."""
    report = Report(client.key, username)
    user = _lookup(client, report, username)
    if user is False:
        return report.skip(["Resetare parolă"])
    if user is None:
        report.add("Verificare utilizator", ERROR, f"Utilizatorul '{username}' nu există în {client.label}.")
        return report.skip(["Resetare parolă"])
    report.add("Verificare utilizator", OK, f"Utilizatorul '{username}' există.")
    report.user = user
    password = generate_password()
    try:
        client.reset_password(username, password)
    except PlatformError as exc:
        report.add("Resetare parolă", ERROR, str(exc))
        return report
    report.add("Resetare parolă", OK, "Parola a fost schimbată; utilizatorul va trebui să o schimbe la prima autentificare acolo unde platforma o permite.")
    report.password = password
    return report


# ---------------------------------------------------------------- CSV import
CSV_COLUMNS = ("username", "email", "first_name", "last_name", "groups")
GROUP_SEPARATOR = "|"


@dataclass
class CsvRow:
    line: int
    username: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    groups: list[str] = field(default_factory=list)
    error: str = ""


def parse_csv(text: str, max_rows: int) -> list[CsvRow]:
    """Parse a CSV with header `username,email,first_name,last_name,groups` (`,` or `;` delimited).

    Groups inside a cell are separated by `|`. Invalid rows are returned with `error` set so the
    caller can report them next to the valid ones instead of aborting the whole import.
    """
    text = text.lstrip("﻿")
    sample = text[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [h.strip().lower() for h in reader.fieldnames or []]
    if "username" not in headers:
        return [CsvRow(1, error=f"Antetul trebuie să conțină coloana 'username'. Coloane acceptate: {', '.join(CSV_COLUMNS)}.")]
    reader.fieldnames = headers
    rows: list[CsvRow] = []
    for raw in reader:
        if len(rows) >= max_rows:
            rows.append(CsvRow(reader.line_num, error=f"Fișierul depășește limita de {max_rows} rânduri; restul a fost ignorat."))
            break
        get = lambda k: (raw.get(k) or "").strip()  # noqa: E731
        if not any(get(k) for k in CSV_COLUMNS):
            continue  # blank line
        row = CsvRow(
            reader.line_num,
            username=get("username"),
            email=get("email"),
            first_name=get("first_name"),
            last_name=get("last_name"),
            groups=[g.strip() for g in get("groups").split(GROUP_SEPARATOR) if g.strip()],
        )
        if not USERNAME_RE.match(row.username):
            row.error = f"Utilizator invalid: '{row.username}'."
        elif row.email and not EMAIL_RE.match(row.email):
            row.error = f"E-mail invalid: '{row.email}'."
        rows.append(row)
    return rows


def import_rows(client: PlatformClient, rows: list[CsvRow], with_password: bool) -> list[Report]:
    """Provision every valid row; invalid rows become one-step error reports. Duplicates are skipped."""
    reports, seen = [], set()
    for row in rows:
        report = Report(client.key, row.username or f"linia {row.line}")
        if row.error:
            report.add("Validare", ERROR, f"Linia {row.line}: {row.error}")
        elif row.username in seen:
            report.add("Validare", ERROR, f"Linia {row.line}: '{row.username}' apare de mai multe ori în fișier.")
        else:
            seen.add(row.username)
            password = generate_password() if with_password else None
            report = provision_user(client, row.username, row.email, row.first_name, row.last_name, password, row.groups)
        reports.append(report)
    return reports
