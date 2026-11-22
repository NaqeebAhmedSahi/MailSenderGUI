"""Persist app session: account, recipients, message, and send progress."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        data_dir = Path.home() / ".mailflow-pro"
    else:
        data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _session_path() -> Path:
    return get_data_dir() / "session.json"


def _empty_session() -> dict[str, Any]:
    return {
        "account": {
            "sender": "",
            "app_password": "",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
        },
        "recipients": {
            "excel_path": "",
            "column_name": "",
            "all_recipients": [],
            "skipped_invalid": [],
        },
        "message": {
            "subject": "",
            "body_html": "",
            "cc": [],
            "bcc": [],
            "attachments": [],
            "signature_enabled": False,
            "signature_mode": "off",
            "signature_html": "",
            "signature_image": "",
        },
        "campaign": {
            "sent": [],
            "failed": [],
        },
    }


class SessionStore:
    def __init__(self) -> None:
        self._path = _session_path()
        self.data = self.load_all()

    def load_all(self) -> dict[str, Any]:
        if not self._path.exists():
            return _empty_session()
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return _empty_session()

        session = _empty_session()
        for section, defaults in session.items():
            if section in loaded and isinstance(loaded[section], dict):
                session[section].update(loaded[section])
        return session

    def save_all(self) -> None:
        self._write(self.data)

    def save_section(self, section: str) -> None:
        if section not in self.data:
            raise KeyError(f"Unknown section: {section}")
        self._write(self.data)

    def _write(self, payload: dict[str, Any]) -> None:
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def get_section(self, section: str) -> dict[str, Any]:
        return self.data[section]

    def update_section(self, section: str, values: dict[str, Any]) -> None:
        self.data[section].update(values)

    @staticmethod
    def pending_recipients(all_recipients: list[str], sent: list[str]) -> list[str]:
        sent_lower = {email.lower() for email in sent}
        return [email for email in all_recipients if email.lower() not in sent_lower]
