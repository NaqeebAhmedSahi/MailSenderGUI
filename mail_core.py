"""Shared mail and Excel parsing logic for CLI and GUI."""

import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable

import openpyxl

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
SEND_DELAY_SECONDS = 1.0


def load_workbook(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {path}")
    if path.suffix.lower() not in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        raise ValueError("Only .xlsx Excel files are supported.")
    return openpyxl.load_workbook(path, read_only=True, data_only=True)


def list_columns(sheet) -> list[str]:
    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise ValueError("The Excel sheet is empty.")

    columns = []
    for index, value in enumerate(header_row, start=1):
        label = str(value).strip() if value is not None else ""
        if not label:
            label = f"Column {openpyxl.utils.get_column_letter(index)}"
        columns.append(label)
    return columns


def split_emails(raw_value) -> list[str]:
    if raw_value is None:
        return []

    text = str(raw_value).strip()
    if not text:
        return []

    emails = []
    for part in text.split(","):
        email = part.strip()
        if email:
            emails.append(email)
    return emails


def collect_recipients(
    sheet,
    column_index: int,
    on_invalid: Callable[[str], None] | None = None,
) -> list[str]:
    seen = set()
    recipients = []

    for row in sheet.iter_rows(min_row=2, values_only=True):
        if column_index >= len(row):
            continue

        for email in split_emails(row[column_index]):
            normalized = email.lower()
            if normalized in seen:
                continue
            if not EMAIL_PATTERN.match(email):
                if on_invalid:
                    on_invalid(email)
                continue
            seen.add(normalized)
            recipients.append(email)

    return recipients


def create_message(
    sender: str,
    recipient: str,
    subject: str,
    body_plain: str,
    body_html: str | None = None,
) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.attach(MIMEText(body_plain, "plain", "utf-8"))
    if body_html:
        message.attach(MIMEText(body_html, "html", "utf-8"))
    return message


def send_email(
    smtp_host: str,
    smtp_port: int,
    sender: str,
    app_password: str,
    recipient: str,
    subject: str,
    body_plain: str,
    body_html: str | None = None,
) -> None:
    message = create_message(sender, recipient, subject, body_plain, body_html)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender, app_password)
        server.sendmail(sender, recipient, message.as_string())


def send_bulk_emails(
    *,
    smtp_host: str,
    smtp_port: int,
    sender: str,
    app_password: str,
    recipients: list[str],
    subject: str,
    body_plain: str,
    body_html: str | None = None,
    on_progress: Callable[[int, int, str, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    delay_seconds: float = SEND_DELAY_SECONDS,
) -> tuple[int, int]:
    sent = 0
    failed = 0
    total = len(recipients)

    for index, recipient in enumerate(recipients, start=1):
        if should_stop and should_stop():
            break

        status = "sending"
        try:
            send_email(
                smtp_host,
                smtp_port,
                sender,
                app_password,
                recipient,
                subject,
                body_plain,
                body_html,
            )
            sent += 1
            status = "sent"
        except smtplib.SMTPAuthenticationError:
            failed += 1
            status = "auth_failed"
            if on_progress:
                on_progress(index, total, recipient, status)
            break
        except Exception:
            failed += 1
            status = "failed"

        if on_progress:
            on_progress(index, total, recipient, status)

        if index < total and not (should_stop and should_stop()):
            time.sleep(delay_seconds)

    return sent, failed
