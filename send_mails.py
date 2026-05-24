#!/usr/bin/env python3
"""Send emails to recipients listed in an Excel column (CLI)."""

import getpass
import smtplib
import sys
from pathlib import Path

from mail_core import (
    DEFAULT_SMTP_HOST,
    DEFAULT_SMTP_PORT,
    collect_recipients,
    list_columns,
    load_workbook,
    send_bulk_emails,
)


def prompt(text: str, *, required: bool = True) -> str:
    while True:
        value = input(text).strip()
        if value or not required:
            return value
        print("This field is required. Please try again.")


def prompt_yes_no(text: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        value = input(text + suffix).strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Please enter y or n.")


def choose_column(columns: list[str]) -> int:
    print("\nAvailable columns:")
    for index, name in enumerate(columns, start=1):
        print(f"  {index}. {name}")

    while True:
        choice = prompt("\nEnter column number or exact column name for email addresses: ")
        if choice.isdigit():
            column_index = int(choice) - 1
            if 0 <= column_index < len(columns):
                return column_index
        else:
            for index, name in enumerate(columns):
                if name.lower() == choice.lower():
                    return index
        print("Invalid column. Choose a number or exact name from the list above.")


def main() -> int:
    print("=" * 60)
    print("Excel Bulk Mail Sender")
    print("=" * 60)

    sender = prompt("\nSender email address: ")
    app_password = getpass.getpass("App password: ")
    if not app_password:
        print("App password is required.")
        return 1

    excel_path = Path(prompt("Path to Excel file (.xlsx): "))
    subject = prompt("Email subject: ")
    print("\nEnter email body. Finish with an empty line:")
    body_lines = []
    while True:
        line = input()
        if not line:
            break
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    if not body:
        print("Email body is required.")
        return 1

    smtp_host = prompt(f"SMTP host [{DEFAULT_SMTP_HOST}]: ", required=False) or DEFAULT_SMTP_HOST
    smtp_port_text = prompt(f"SMTP port [{DEFAULT_SMTP_PORT}]: ", required=False) or str(DEFAULT_SMTP_PORT)
    try:
        smtp_port = int(smtp_port_text)
    except ValueError:
        print("SMTP port must be a number.")
        return 1

    try:
        workbook = load_workbook(excel_path)
        sheet = workbook.active
        columns = list_columns(sheet)
        column_index = choose_column(columns)
        recipients = collect_recipients(
            sheet,
            column_index,
            on_invalid=lambda email: print(f"Skipping invalid email: {email}"),
        )
        workbook.close()
    except Exception as exc:
        print(f"Error reading Excel file: {exc}")
        return 1

    if not recipients:
        print("No valid email addresses found in the selected column.")
        return 1

    print(f"\nFound {len(recipients)} unique recipient(s).")
    for index, email in enumerate(recipients[:10], start=1):
        print(f"  {index}. {email}")
    if len(recipients) > 10:
        print(f"  ... and {len(recipients) - 10} more")

    if not prompt_yes_no("\nStart sending emails?", default=True):
        print("Cancelled.")
        return 0

    def on_progress(current: int, total: int, recipient: str, status: str) -> None:
        if status == "sent":
            print(f"[{current}/{total}] Sending to {recipient}... OK")
        elif status == "failed":
            print(f"[{current}/{total}] Sending to {recipient}... FAILED")
        elif status == "auth_failed":
            print(f"[{current}/{total}] Sending to {recipient}... FAILED")
            print("\nAuthentication failed. Check your email and app password.")

    sent, failed = send_bulk_emails(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        sender=sender,
        app_password=app_password,
        recipients=recipients,
        subject=subject,
        body_plain=body,
        on_progress=on_progress,
    )

    print("\n" + "=" * 60)
    print(f"Done. Sent: {sent}, Failed: {failed}, Total: {len(recipients)}")
    print("=" * 60)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
        raise SystemExit(130)
