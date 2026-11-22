"""Shared mail and Excel parsing logic for CLI and GUI."""

from __future__ import annotations

import html as html_lib
import mimetypes
import re
import smtplib
import time
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import Callable, Mapping, Sequence

import openpyxl

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
SIGNATURE_IMAGE_CID = "mailflow-signature"
# Placeholder put in the body where the user dropped the signature block.
SIGNATURE_MARKER = "{{SIGNATURE}}"
# Placeholder inside the signature where the logo image goes.
LOGO_MARKER = "{{LOGO}}"

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
SEND_DELAY_SECONDS = 1.0

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
SIGNATURE_TEXT_EXTENSIONS = {".txt", ".html", ".htm"}


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email.strip()))


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
    for part in re.split(r"[,;]", text):
        email = part.strip()
        if email:
            emails.append(email)
    return emails


def collect_recipients(
    sheet,
    column_index: int,
    on_invalid: Callable[[str], None] | None = None,
) -> tuple[list[str], dict[str, int]]:
    seen = set()
    recipients = []
    stats = {
        "rows_scanned": 0,
        "raw_found": 0,
        "invalid": 0,
        "duplicates": 0,
    }

    excel_col = column_index + 1
    for row in sheet.iter_rows(
        min_row=2,
        min_col=excel_col,
        max_col=excel_col,
        values_only=True,
    ):
        stats["rows_scanned"] += 1
        cell_value = row[0] if row else None
        for email in split_emails(cell_value):
            stats["raw_found"] += 1
            normalized = email.lower()
            if normalized in seen:
                stats["duplicates"] += 1
                continue
            if not EMAIL_PATTERN.match(email):
                stats["invalid"] += 1
                if on_invalid:
                    on_invalid(email)
                continue
            seen.add(normalized)
            recipients.append(email)

    return recipients, stats


def _plain_to_html_fragment(text: str) -> str:
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    return f"<p>{escaped}</p>"


def _html_to_plain_fragment(html_body: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_body)
    text = re.sub(r"(?i)<[^>]+>", "", text)
    return text.strip()


def strip_signature_marker(text: str | None) -> str:
    return (text or "").replace(SIGNATURE_MARKER, "")


def append_signature(
    body_plain: str,
    body_html: str | None,
    signature_plain: str = "",
    signature_html: str = "",
    signature_image_cid: str | None = None,
    signature_image_name: str = "signature",
    signature_image_src: str | None = None,
    signature_image_size: tuple[int, int] | None = None,
) -> tuple[str, str]:
    """Insert an optional text/HTML/image signature into plain and HTML bodies.

    If the body contains SIGNATURE_MARKER the signature replaces it in place;
    otherwise it is appended at the bottom.

    ``signature_image_src`` overrides the ``cid:`` reference (used for the
    local preview, where the image is loaded from disk).

    Always returns a non-None HTML string so clients that prefer HTML still
    show signature text (Gmail ignores plain when an HTML part exists).
    """
    sig_plain = (signature_plain or "").strip()
    sig_html = (signature_html or "").strip()

    if not sig_plain and sig_html:
        sig_plain = _html_to_plain_fragment(sig_html)
    if not sig_html and sig_plain:
        sig_html = _plain_to_html_fragment(sig_plain)

    if signature_image_cid or signature_image_src:
        src = signature_image_src or f"cid:{signature_image_cid}"
        size_attrs = ""
        if signature_image_size:
            width, height = signature_image_size
            size_attrs = f' width="{int(width)}" height="{int(height)}"'
        image_note = f"[Signature image: {signature_image_name}]"
        image_html = (
            f'<div style="margin-top:8px;">'
            f'<img src="{html_lib.escape(src, quote=True)}" alt="Signature"{size_attrs} '
            f'style="max-width:320px;height:auto;" />'
            f"</div>"
        )
        if LOGO_MARKER in sig_html:
            # Logo positioned by the user inside the signature.
            inline_img = (
                f'<img src="{html_lib.escape(src, quote=True)}" alt="Logo"{size_attrs} '
                f'style="display:block;max-width:320px;height:auto;margin:4px 0;" />'
            )
            sig_html = sig_html.replace(LOGO_MARKER, inline_img, 1)
            sig_plain = sig_plain.replace(LOGO_MARKER, image_note, 1)
        elif sig_plain:
            if image_note not in sig_plain:
                sig_plain = f"{sig_plain}\n{image_note}"
        else:
            sig_plain = image_note
        if LOGO_MARKER not in (signature_html or ""):
            # No position chosen: append the image after the text.
            if sig_html and image_note in sig_plain and "<img" not in sig_html:
                sig_html = f"{sig_html}{image_html}"
            elif not sig_html:
                sig_html = image_html
    sig_html = sig_html.replace(LOGO_MARKER, "")
    sig_plain = sig_plain.replace(LOGO_MARKER, "").strip()

    html_base = (body_html or "").strip()
    if not html_base and (body_plain or "").strip():
        html_base = _plain_to_html_fragment(body_plain.strip())

    # Signature placed somewhere inside the body.
    if SIGNATURE_MARKER in html_base or SIGNATURE_MARKER in (body_plain or ""):
        # The signature is a block, so a line break right after it would
        # only add an empty line.
        html_base = re.sub(re.escape(SIGNATURE_MARKER) + r"\s*<br\s*/?>", SIGNATURE_MARKER, html_base, count=1)
        html_out = html_base.replace(SIGNATURE_MARKER, sig_html, 1).replace(SIGNATURE_MARKER, "")
        plain = (body_plain or "")
        if SIGNATURE_MARKER in plain:
            plain = plain.replace(SIGNATURE_MARKER, sig_plain, 1).replace(SIGNATURE_MARKER, "")
        elif sig_plain:
            plain = f"{plain.rstrip()}\n\n--\n{sig_plain}"
        return plain, html_out

    if not sig_plain and not sig_html:
        return body_plain or "", html_base

    plain = (body_plain or "").rstrip()
    if sig_plain:
        plain = f"{plain}\n\n--\n{sig_plain}" if plain else f"--\n{sig_plain}"

    if sig_html:
        if html_base:
            html_out = (
                f"{html_base}"
                f'<br><br><hr style="border:none;border-top:1px solid #ccc;margin:16px 0;">'
                f"{sig_html}"
            )
        else:
            html_out = sig_html
    else:
        html_out = html_base

    return plain, html_out


def _attach_file(message: MIMEMultipart, path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Attachment not found: {path}")

    mime_type, _encoding = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "application/octet-stream"
    maintype, subtype = mime_type.split("/", 1)

    with path.open("rb") as handle:
        payload = handle.read()

    if maintype == "application":
        part = MIMEApplication(payload, Name=path.name)
    else:
        part = MIMEBase(maintype, subtype)
        part.set_payload(payload)
        encoders.encode_base64(part)

    part.add_header("Content-Disposition", "attachment", filename=path.name)
    message.attach(part)


def _inline_image(path: Path, content_id: str) -> MIMEImage | MIMEBase:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Inline image not found: {path}")

    mime_type, _encoding = mimetypes.guess_type(str(path))
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"
    subtype = mime_type.split("/", 1)[1]

    with path.open("rb") as handle:
        payload = handle.read()

    part = MIMEImage(payload, _subtype=subtype)
    part.add_header("Content-ID", f"<{content_id}>")
    part.add_header("Content-Disposition", "inline", filename=path.name)
    return part


def _build_body_part(
    body_plain: str,
    body_html: str | None,
    inline_images: Mapping[str, str | Path] | None,
) -> MIMEMultipart:
    """Build a Gmail-friendly body tree.

    Preferred shape:
      multipart/alternative
        text/plain
        [multipart/related: text/html + inline images]
        OR text/html alone
    """
    plain = body_plain or ""
    html = (body_html or "").strip()
    if not html and plain.strip():
        html = _plain_to_html_fragment(plain.strip())
    if not plain.strip() and html:
        plain = _html_to_plain_fragment(html)

    images = {
        cid: Path(path)
        for cid, path in (inline_images or {}).items()
        if cid and path and Path(path).exists()
    }

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(plain, "plain", "utf-8"))

    if images and html:
        related = MIMEMultipart("related")
        related.attach(MIMEText(html, "html", "utf-8"))
        for content_id, path in images.items():
            related.attach(_inline_image(path, content_id))
        alternative.attach(related)
    elif html:
        alternative.attach(MIMEText(html, "html", "utf-8"))

    return alternative


def create_message(
    sender: str,
    recipient: str,
    subject: str,
    body_plain: str,
    body_html: str | None = None,
    cc: Sequence[str] | None = None,
    bcc: Sequence[str] | None = None,
    attachments: Sequence[str | Path] | None = None,
    inline_images: Mapping[str, str | Path] | None = None,
) -> MIMEMultipart:
    cc_list = [email.strip() for email in (cc or []) if email and email.strip()]
    attachment_paths = [Path(path) for path in (attachments or [])]
    body_part = _build_body_part(body_plain, body_html, inline_images)

    if attachment_paths:
        message = MIMEMultipart("mixed")
        message.attach(body_part)
        for path in attachment_paths:
            _attach_file(message, path)
    else:
        message = body_part

    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    # BCC intentionally omitted from headers; included only in SMTP envelope.
    return message


def envelope_recipients(
    recipient: str,
    cc: Sequence[str] | None = None,
    bcc: Sequence[str] | None = None,
) -> list[str]:
    cc_list = [email.strip() for email in (cc or []) if email and email.strip()]
    bcc_list = [email.strip() for email in (bcc or []) if email and email.strip()]
    return [recipient] + cc_list + bcc_list


def send_email(
    smtp_host: str,
    smtp_port: int,
    sender: str,
    app_password: str,
    recipient: str,
    subject: str,
    body_plain: str,
    body_html: str | None = None,
    cc: Sequence[str] | None = None,
    bcc: Sequence[str] | None = None,
    attachments: Sequence[str | Path] | None = None,
    inline_images: Mapping[str, str | Path] | None = None,
) -> None:
    message = create_message(
        sender,
        recipient,
        subject,
        body_plain,
        body_html,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
        inline_images=inline_images,
    )
    password = (app_password or "").strip()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender, password)
        server.sendmail(
            sender,
            envelope_recipients(recipient, cc=cc, bcc=bcc),
            message.as_bytes(),
        )


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
    cc: Sequence[str] | None = None,
    bcc: Sequence[str] | None = None,
    attachments: Sequence[str | Path] | None = None,
    inline_images: Mapping[str, str | Path] | None = None,
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
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                inline_images=inline_images,
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
