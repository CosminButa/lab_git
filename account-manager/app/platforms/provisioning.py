"""Step-by-step provisioning with explicit verification after every change.

Every operation returns a Report: an ordered list of steps, each with a status
(ok / exists / skipped / error) and a human-readable message, so the operator
sees exactly what happened and what was verified.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base import Group, PlatformClient, PlatformError, PlatformUser

OK = "ok"          # action done and verified
EXISTS = "exists"  # nothing to do, the state was already there
SKIPPED = "skipped"  # not attempted because an earlier step failed
ERROR = "error"


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

    def add(self, name: str, status: str, message: str) -> Step:
        step = Step(name, status, message)
        self.steps.append(step)
        return step

    @property
    def has_errors(self) -> bool:
        return any(s.status == ERROR for s in self.steps)

    @property
    def outcome(self) -> str:
        return "error" if self.has_errors else "ok"

    def summary(self) -> str:
        return "; ".join(f"{s.name}={s.status}" for s in self.steps)


def _health(client: PlatformClient, report: Report) -> bool:
    try:
        client.health()
    except PlatformError as exc:
        report.add("Conexiune", ERROR, str(exc))
        return False
    report.add("Conexiune", OK, f"{client.label} răspunde.")
    return True


def _verify_user(client: PlatformClient, report: Report, username: str, expect: bool) -> PlatformUser | None:
    """Confirm the user does / does not exist by reading it back."""
    try:
        user = client.user_exists(username)
    except PlatformError as exc:
        report.add("Verificare utilizator", ERROR, str(exc))
        return None
    if expect and user is None:
        report.add("Verificare utilizator", ERROR, f"Utilizatorul '{username}' nu a fost găsit după creare.")
    elif expect and user is not None:
        report.add("Verificare utilizator", OK, f"Utilizatorul '{username}' există și este {'activ' if user.enabled else 'dezactivat'}.")
    return user


def add_to_group(client: PlatformClient, report: Report, user: PlatformUser, group_id: str) -> None:
    """Add `user` to `group_id`, verifying group existence, current membership and the result."""
    label = f"Grup {group_id}"
    try:
        group = client.find_group(group_id)
    except PlatformError as exc:
        report.add(label, ERROR, f"Nu s-au putut citi grupurile: {exc}")
        return
    if group is None:
        report.add(label, ERROR, f"Grupul '{group_id}' nu există în {client.label}.")
        return
    if any(g.id == group.id for g in user.groups):
        report.add(label, EXISTS, f"'{user.username}' este deja membru în '{group.name}'.")
        return
    try:
        client.add_to_group(user.username, group.id)
    except PlatformError as exc:
        report.add(label, ERROR, f"Adăugarea în '{group.name}' a eșuat: {exc}")
        return
    # Verify by reading the membership back.
    try:
        fresh = client.get_user(user.username)
    except PlatformError as exc:
        report.add(label, ERROR, f"Adăugat, dar verificarea a eșuat: {exc}")
        return
    if any(g.id == group.id for g in fresh.groups):
        user.groups = fresh.groups
        report.add(label, OK, f"'{user.username}' a fost adăugat și verificat în '{group.name}'.")
    else:
        report.add(label, ERROR, f"Platforma a acceptat cererea, dar '{user.username}' nu apare în '{group.name}'.")


def provision_user(
    client: PlatformClient,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    password: str | None,
    groups: list[str],
) -> Report:
    """Create a user (if missing) and add it to the requested groups, verifying each step."""
    report = Report(platform=client.key, username=username)
    if not _health(client, report):
        report.add("Creare utilizator", SKIPPED, "Nu s-a încercat: platforma nu răspunde.")
        for g in groups:
            report.add(f"Grup {g}", SKIPPED, "Nu s-a încercat.")
        return report

    try:
        existing = client.user_exists(username)
    except PlatformError as exc:
        report.add("Verificare utilizator", ERROR, str(exc))
        report.add("Creare utilizator", SKIPPED, "Nu s-a încercat: verificarea prealabilă a eșuat.")
        for g in groups:
            report.add(f"Grup {g}", SKIPPED, "Nu s-a încercat.")
        return report

    if existing is not None:
        report.add("Creare utilizator", EXISTS, f"Utilizatorul '{username}' există deja în {client.label}; nu a fost creat din nou.")
        user = existing
    else:
        try:
            client.create_user(username, email, first_name, last_name, password)
        except PlatformError as exc:
            report.add("Creare utilizator", ERROR, str(exc))
            for g in groups:
                report.add(f"Grup {g}", SKIPPED, "Nu s-a încercat: utilizatorul nu a fost creat.")
            return report
        report.add("Creare utilizator", OK, f"Cererea de creare pentru '{username}' a fost acceptată.")
        user = _verify_user(client, report, username, expect=True)
        if user is None:
            for g in groups:
                report.add(f"Grup {g}", SKIPPED, "Nu s-a încercat: utilizatorul nu a putut fi verificat.")
            return report
        report.created = True

    report.user = user
    for group_id in groups:
        add_to_group(client, report, user, group_id)
    return report


def assign_group(client: PlatformClient, username: str, group_id: str) -> Report:
    """Add an existing user to a group, with the same verification steps."""
    report = Report(platform=client.key, username=username)
    try:
        user = client.user_exists(username)
    except PlatformError as exc:
        report.add("Verificare utilizator", ERROR, str(exc))
        report.add(f"Grup {group_id}", SKIPPED, "Nu s-a încercat.")
        return report
    if user is None:
        report.add("Verificare utilizator", ERROR, f"Utilizatorul '{username}' nu există în {client.label}; nu poate fi asociat grupului.")
        report.add(f"Grup {group_id}", SKIPPED, "Nu s-a încercat.")
        return report
    report.add("Verificare utilizator", OK, f"Utilizatorul '{username}' există.")
    report.user = user
    add_to_group(client, report, user, group_id)
    return report
