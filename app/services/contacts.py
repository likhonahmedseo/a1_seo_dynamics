from __future__ import annotations

from io import BytesIO
from typing import Iterable

import pandas as pd

from app.models import Contact


REQUIRED_COLUMNS = {"email"}
OPTIONAL_COLUMNS = ["first_name", "last_name", "company", "role", "website", "notes"]


def load_contacts_from_csv(file_bytes: bytes) -> list[Contact]:
    dataframe = pd.read_csv(BytesIO(file_bytes))
    dataframe.columns = [str(column).strip().lower() for column in dataframe.columns]

    missing = REQUIRED_COLUMNS - set(dataframe.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Missing required column(s): {missing_text}")

    normalized = dataframe.fillna("")

    contacts: list[Contact] = []
    for row in normalized.to_dict(orient="records"):
        email = str(row.get("email", "")).strip()
        if not email:
            continue

        contacts.append(
            Contact(
                email=email,
                first_name=str(row.get("first_name", "")).strip(),
                last_name=str(row.get("last_name", "")).strip(),
                company=str(row.get("company", "")).strip(),
                role=str(row.get("role", "")).strip(),
                website=str(row.get("website", "")).strip(),
                notes=str(row.get("notes", "")).strip(),
            )
        )

    return deduplicate_contacts(contacts)


def deduplicate_contacts(contacts: Iterable[Contact]) -> list[Contact]:
    seen: set[str] = set()
    unique: list[Contact] = []

    for contact in contacts:
        key = contact.email.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(contact)

    return unique
