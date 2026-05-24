#!/usr/bin/env python3
"""Premium GUI for Excel bulk mail sending."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from html_editor import HtmlEditor
from session_store import SessionStore
from mail_core import (
    DEFAULT_SMTP_HOST,
    DEFAULT_SMTP_PORT,
    collect_recipients,
    list_columns,
    load_workbook,
    send_bulk_emails,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg": "#0B0F19",
    "surface": "#111827",
    "surface_alt": "#1A2234",
    "border": "#243047",
    "text": "#F8FAFC",
    "muted": "#94A3B8",
    "accent": "#6366F1",
    "accent_hover": "#818CF8",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
}

SCROLL_STEP = 3


def _widget_contains(root_widget, event_widget) -> bool:
    current = event_widget
    while current is not None:
        if current == root_widget:
            return True
        try:
            current = current.master
        except tk.TclError:
            break
    return False


def _wheel_delta(event) -> int:
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1
    if not getattr(event, "delta", 0):
        return 0
    if sys.platform.startswith("win"):
        return -int(event.delta / 120) if event.delta else 0
    if sys.platform == "darwin":
        return -event.delta
    return -int(event.delta)


def enable_textbox_scroll(textbox: ctk.CTkTextbox, step: int = SCROLL_STEP) -> None:
    inner = textbox._textbox

    def _scroll(direction: int, event) -> str:
        first, last = inner.yview()
        if direction < 0 and first <= 0.0:
            return ""
        if direction > 0 and last >= 1.0:
            return ""
        inner.yview_scroll(direction * step, "units")
        return "break"

    def on_wheel(event):
        direction = _wheel_delta(event)
        if direction:
            return _scroll(direction, event)
        return "break"

    targets = {textbox, inner, textbox._canvas}
    for widget in targets:
        widget.bind("<MouseWheel>", on_wheel, add="+")
        widget.bind("<Button-4>", lambda e: _scroll(-1, e), add="+")
        widget.bind("<Button-5>", lambda e: _scroll(1, e), add="+")


def enable_tktext_scroll(text_widget: tk.Text, step: int = SCROLL_STEP) -> None:
    def _scroll(direction: int, _event) -> str:
        first, last = text_widget.yview()
        if direction < 0 and first <= 0.0:
            return "break"
        if direction > 0 and last >= 1.0:
            return "break"
        text_widget.yview_scroll(direction * step, "units")
        return "break"

    def on_wheel(event):
        direction = _wheel_delta(event)
        if direction:
            return _scroll(direction, event)
        return "break"

    text_widget.bind("<MouseWheel>", on_wheel, add="+")
    text_widget.bind("<Button-4>", lambda e: _scroll(-1, e), add="+")
    text_widget.bind("<Button-5>", lambda e: _scroll(1, e), add="+")


def enable_scrollable_frame(
    frame: ctk.CTkScrollableFrame,
    textboxes: list[ctk.CTkTextbox] | None = None,
    step: int = SCROLL_STEP,
) -> None:
    canvas = frame._parent_canvas
    textboxes = textboxes or []

    def _textbox_can_scroll(event_widget, direction: int) -> ctk.CTkTextbox | None:
        for textbox in textboxes:
            if not _widget_contains(textbox, event_widget):
                continue
            inner = textbox._textbox
            first, last = inner.yview()
            if direction < 0 and first > 0.0:
                return textbox
            if direction > 0 and last < 1.0:
                return textbox
        return None

    def _scroll_frame(direction: int) -> None:
        if frame._orientation != "vertical":
            return
        first, last = canvas.yview()
        if direction < 0 and first <= 0.0:
            return
        if direction > 0 and last >= 1.0:
            return
        canvas.yview_scroll(direction * step, "units")

    def on_wheel(event):
        direction = _wheel_delta(event)
        if not direction:
            return "break"

        active_textbox = _textbox_can_scroll(event.widget, direction)
        if active_textbox is not None:
            active_textbox._textbox.yview_scroll(direction * step, "units")
            return "break"

        if frame.check_if_master_is_canvas(event.widget):
            _scroll_frame(direction)
        return "break"

    frame.bind_all("<MouseWheel>", on_wheel, add="+")
    frame.bind_all("<Button-4>", on_wheel, add="+")
    frame.bind_all("<Button-5>", on_wheel, add="+")


class Card(ctk.CTkFrame):
    def __init__(
        self,
        master,
        title: str,
        subtitle: str = "",
        on_save=None,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
            **kwargs,
        )

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 12))

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        if on_save is not None:
            ctk.CTkButton(
                title_row,
                text="Save",
                width=88,
                height=32,
                corner_radius=8,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                font=ctk.CTkFont(size=12, weight="bold"),
                command=on_save,
            ).pack(side="right")

        if subtitle:
            ctk.CTkLabel(
                header,
                text=subtitle,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=COLORS["muted"],
                anchor="w",
            ).pack(fill="x", pady=(4, 0))

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=24, pady=(0, 24))


class MailSenderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MailFlow Pro — Bulk Mail Sender")
        self.geometry("1120x780")
        self.minsize(980, 680)
        self.configure(fg_color=COLORS["bg"])

        self.recipients: list[str] = []
        self.skipped_invalid: list[str] = []
        self.sent_recipients: list[str] = []
        self.failed_recipients: list[str] = []
        self._stop_requested = False
        self._sending = False
        self.session = SessionStore()

        self._build_layout()
        self.after(100, self._load_session)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_panel()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self,
            width=260,
            corner_radius=0,
            fg_color=COLORS["surface_alt"],
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=28, pady=(32, 28))

        ctk.CTkLabel(
            brand,
            text="MailFlow Pro",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            brand,
            text="Excel-powered bulk delivery",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(6, 0))

        accent = ctk.CTkFrame(brand, height=3, fg_color=COLORS["accent"], corner_radius=2)
        accent.pack(fill="x", pady=(18, 0))

        steps = [
            ("1", "Connect your mailbox"),
            ("2", "Import recipients"),
            ("3", "Compose your message"),
            ("4", "Review and send"),
        ]
        for number, label in steps:
            row = ctk.CTkFrame(sidebar, fg_color="transparent")
            row.pack(fill="x", padx=28, pady=8)

            badge = ctk.CTkLabel(
                row,
                text=number,
                width=28,
                height=28,
                corner_radius=14,
                fg_color=COLORS["accent"],
                text_color=COLORS["text"],
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            badge.pack(side="left")

            ctk.CTkLabel(
                row,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COLORS["muted"],
                anchor="w",
            ).pack(side="left", padx=(12, 0))

        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=28, pady=28)

        ctk.CTkLabel(
            footer,
            text="Supports comma-separated\nemails in a single cell",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
            justify="left",
            anchor="w",
        ).pack(fill="x")

    def _build_main_panel(self) -> None:
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        main = self.main_scroll
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=8)
        main.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=(24, 32), pady=(12, 20))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top,
            text="Campaign Setup",
            font=ctk.CTkFont(family="Segoe UI", size=30, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            top,
            text="Configure SMTP, load Excel recipients, and launch your campaign.",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=COLORS["muted"],
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self._build_account_card(main, row=1)
        self._build_recipients_card(main, row=2)
        self._build_compose_card(main, row=3)
        self._build_send_card(main, row=4)
        self._enable_scrolling()

    def _enable_scrolling(self) -> None:
        textboxes = [self.preview_box, self.log_box, self.body_editor.source_box]
        for textbox in textboxes:
            enable_textbox_scroll(textbox)
        enable_tktext_scroll(self.body_editor.visual_editor)
        enable_scrollable_frame(self.main_scroll, textboxes=textboxes)

    def _labeled_entry(
        self,
        parent,
        label: str,
        placeholder: str = "",
        show: str | None = None,
        default: str = "",
    ) -> ctk.CTkEntry:
        ctk.CTkLabel(
            parent,
            text=label,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            height=42,
            corner_radius=10,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_alt"],
            text_color=COLORS["text"],
            show=show,
        )
        entry.pack(fill="x", pady=(0, 14))
        if default:
            entry.insert(0, default)
        return entry

    def _build_account_card(self, parent, row: int) -> None:
        card = Card(
            parent,
            title="Mailbox Connection",
            subtitle="Use your email and app password. Gmail users need an App Password.",
            on_save=self._save_account,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        card.grid_columnconfigure((0, 1), weight=1)

        left = ctk.CTkFrame(card.body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = ctk.CTkFrame(card.body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        self.sender_entry = self._labeled_entry(left, "Sender Email", "you@company.com")
        self.password_entry = self._labeled_entry(
            left, "App Password", "••••••••••••••••", show="•"
        )
        self.smtp_host_entry = self._labeled_entry(
            right, "SMTP Host", DEFAULT_SMTP_HOST, default=DEFAULT_SMTP_HOST
        )
        self.smtp_port_entry = self._labeled_entry(
            right, "SMTP Port", str(DEFAULT_SMTP_PORT), default=str(DEFAULT_SMTP_PORT)
        )

    def _build_recipients_card(self, parent, row: int) -> None:
        card = Card(
            parent,
            title="Recipient List",
            subtitle="Load an Excel file and choose the column that contains email addresses.",
            on_save=self._save_recipients,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 16))

        file_row = ctk.CTkFrame(card.body, fg_color="transparent")
        file_row.pack(fill="x", pady=(0, 12))

        self.excel_path_var = tk.StringVar()
        self.excel_entry = ctk.CTkEntry(
            file_row,
            textvariable=self.excel_path_var,
            placeholder_text="Select .xlsx file...",
            height=42,
            corner_radius=10,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_alt"],
            text_color=COLORS["text"],
        )
        self.excel_entry.pack(side="left", fill="x", expand=True, padx=(0, 12))

        ctk.CTkButton(
            file_row,
            text="Browse",
            width=110,
            height=42,
            corner_radius=10,
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["border"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._browse_excel,
        ).pack(side="left")

        meta_row = ctk.CTkFrame(card.body, fg_color="transparent")
        meta_row.pack(fill="x")
        meta_row.grid_columnconfigure(0, weight=1)

        col_frame = ctk.CTkFrame(meta_row, fg_color="transparent")
        col_frame.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        ctk.CTkLabel(
            col_frame,
            text="Email Column",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        self.column_menu = ctk.CTkOptionMenu(
            col_frame,
            values=["Load Excel first..."],
            height=42,
            corner_radius=10,
            fg_color=COLORS["surface_alt"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["surface_alt"],
            command=self._on_column_selected,
        )
        self.column_menu.pack(fill="x")

        ctk.CTkButton(
            meta_row,
            text="Load Recipients",
            width=160,
            height=42,
            corner_radius=10,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            command=self._load_recipients,
        ).grid(row=0, column=1, sticky="e")

        stats = ctk.CTkFrame(card.body, fg_color=COLORS["surface_alt"], corner_radius=12)
        stats.pack(fill="x", pady=(16, 12))

        self.recipient_count_label = ctk.CTkLabel(
            stats,
            text="0 recipients ready",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        )
        self.recipient_count_label.pack(fill="x", padx=16, pady=(14, 4))

        self.skipped_label = ctk.CTkLabel(
            stats,
            text="No file loaded yet",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.skipped_label.pack(fill="x", padx=16, pady=(0, 14))

        self.sent_count_label = ctk.CTkLabel(
            stats,
            text="Sent: 0  |  Pending: 0  |  Failed: 0",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.sent_count_label.pack(fill="x", padx=16, pady=(0, 14))

        self.preview_box = ctk.CTkTextbox(
            card.body,
            height=120,
            corner_radius=12,
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(family="Consolas", size=12),
            activate_scrollbars=True,
        )
        self.preview_box.pack(fill="x")
        self.preview_box.insert("1.0", "Recipient preview will appear here...")
        self.preview_box.configure(state="disabled")

        self._column_names: list[str] = []

    def _build_compose_card(self, parent, row: int) -> None:
        card = Card(
            parent,
            title="Message",
            subtitle="Compose rich HTML emails with the visual editor, source code, or preview.",
            on_save=self._save_message,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 16))

        ctk.CTkLabel(
            card.body,
            text="Subject",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        self.subject_entry = ctk.CTkEntry(
            card.body,
            placeholder_text="Your email subject",
            height=42,
            corner_radius=10,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_alt"],
            text_color=COLORS["text"],
        )
        self.subject_entry.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            card.body,
            text="Email Body",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        self.body_editor = HtmlEditor(card.body, colors=COLORS, height=360)
        self.body_editor.pack(fill="x")

    def _build_send_card(self, parent, row: int) -> None:
        card = Card(
            parent,
            title="Delivery",
            subtitle="Review progress and launch the campaign. Already-sent emails are skipped.",
            on_save=self._save_campaign,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 24))

        actions = ctk.CTkFrame(card.body, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 12))

        self.send_button = ctk.CTkButton(
            actions,
            text="Start Sending",
            height=46,
            corner_radius=12,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            command=self._start_sending,
        )
        self.send_button.pack(side="left")

        self.stop_button = ctk.CTkButton(
            actions,
            text="Stop",
            height=46,
            width=120,
            corner_radius=12,
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["danger"],
            border_width=1,
            border_color=COLORS["border"],
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self._request_stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(12, 0))

        ctk.CTkButton(
            actions,
            text="Reset Campaign",
            height=46,
            width=150,
            corner_radius=12,
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["warning"],
            border_width=1,
            border_color=COLORS["border"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._reset_campaign,
        ).pack(side="left", padx=(12, 0))

        self.progress = ctk.CTkProgressBar(
            card.body,
            height=10,
            corner_radius=8,
            progress_color=COLORS["accent"],
            fg_color=COLORS["surface_alt"],
        )
        self.progress.pack(fill="x", pady=(0, 8))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            card.body,
            text="Ready to send",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 10))

        self.log_box = ctk.CTkTextbox(
            card.body,
            height=180,
            corner_radius=12,
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text"],
            font=ctk.CTkFont(family="Consolas", size=12),
            activate_scrollbars=True,
        )
        self.log_box.pack(fill="x")
        self.log_box.configure(state="disabled")

    def _pending_recipients(self) -> list[str]:
        return SessionStore.pending_recipients(self.recipients, self.sent_recipients)

    def _save_account(self, *, silent: bool = False) -> None:
        self.session.update_section(
            "account",
            {
                "sender": self.sender_entry.get().strip(),
                "app_password": self.password_entry.get(),
                "smtp_host": self.smtp_host_entry.get().strip() or DEFAULT_SMTP_HOST,
                "smtp_port": self.smtp_port_entry.get().strip() or str(DEFAULT_SMTP_PORT),
            },
        )
        self.session.save_section("account")
        if not silent:
            messagebox.showinfo("Saved", "Mailbox settings saved.")

    def _save_recipients(self, *, silent: bool = False) -> None:
        self.session.update_section(
            "recipients",
            {
                "excel_path": self.excel_path_var.get().strip(),
                "column_name": self.column_menu.get(),
                "all_recipients": self.recipients,
                "skipped_invalid": self.skipped_invalid,
            },
        )
        self.session.save_section("recipients")
        if not silent:
            messagebox.showinfo("Saved", "Recipient list saved.")

    def _save_message(self, *, silent: bool = False) -> None:
        self.session.update_section(
            "message",
            {
                "subject": self.subject_entry.get().strip(),
                "body_html": self.body_editor.get_html(),
            },
        )
        self.session.save_section("message")
        if not silent:
            messagebox.showinfo("Saved", "Message saved.")

    def _save_campaign(self) -> None:
        self.session.update_section(
            "campaign",
            {
                "sent": self.sent_recipients,
                "failed": self.failed_recipients,
            },
        )
        self.session.save_section("campaign")
        messagebox.showinfo("Saved", "Campaign progress saved.")

    def _persist_campaign(self) -> None:
        self.session.update_section(
            "campaign",
            {
                "sent": self.sent_recipients,
                "failed": self.failed_recipients,
            },
        )
        self.session.save_section("campaign")

    def _load_session(self) -> None:
        account = self.session.get_section("account")
        if account.get("sender"):
            self.sender_entry.insert(0, account["sender"])
        if account.get("app_password"):
            self.password_entry.insert(0, account["app_password"])
        if account.get("smtp_host"):
            self.smtp_host_entry.delete(0, "end")
            self.smtp_host_entry.insert(0, account["smtp_host"])
        if account.get("smtp_port"):
            self.smtp_port_entry.delete(0, "end")
            self.smtp_port_entry.insert(0, str(account["smtp_port"]))

        recipients = self.session.get_section("recipients")
        if recipients.get("excel_path"):
            self.excel_path_var.set(recipients["excel_path"])
            self._load_columns_only()
            column_name = recipients.get("column_name", "")
            if column_name and column_name in self._column_names:
                self.column_menu.set(column_name)
            if recipients.get("all_recipients"):
                self.recipients = list(recipients["all_recipients"])
                self.skipped_invalid = list(recipients.get("skipped_invalid", []))

        message = self.session.get_section("message")
        if message.get("subject"):
            self.subject_entry.insert(0, message["subject"])
        if message.get("body_html"):
            self.body_editor.set_html(message["body_html"])

        campaign = self.session.get_section("campaign")
        self.sent_recipients = list(campaign.get("sent", []))
        self.failed_recipients = list(campaign.get("failed", []))

        self._update_recipient_preview()
        pending = self._pending_recipients()
        if self.recipients:
            self._append_log(
                f"Session restored: {len(self.sent_recipients)} sent, "
                f"{len(pending)} pending, {len(self.failed_recipients)} failed."
            )

    def _reset_campaign(self) -> None:
        if not messagebox.askyesno(
            "Reset Campaign",
            "Clear sent and failed history? All recipients will become pending again.",
        ):
            return
        self.sent_recipients = []
        self.failed_recipients = []
        self._persist_campaign()
        self._update_recipient_preview()
        self._append_log("Campaign progress reset. All recipients are pending again.")

    def _browse_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if path:
            self.excel_path_var.set(path)
            self._load_columns_only()

    def _load_columns_only(self) -> None:
        path_text = self.excel_path_var.get().strip()
        if not path_text:
            return

        try:
            workbook = load_workbook(Path(path_text))
            sheet = workbook.active
            self._column_names = list_columns(sheet)
            workbook.close()
            self.column_menu.configure(values=self._column_names)
            self.column_menu.set(self._column_names[0])
        except Exception as exc:
            messagebox.showerror("Excel Error", str(exc))

    def _on_column_selected(self, _value: str) -> None:
        if self.excel_path_var.get().strip():
            self._load_recipients()

    def _load_recipients(self) -> None:
        path_text = self.excel_path_var.get().strip()
        if not path_text:
            messagebox.showwarning("Missing File", "Please select an Excel file first.")
            return

        column_name = self.column_menu.get()
        if column_name == "Load Excel first..." or not self._column_names:
            self._load_columns_only()
            column_name = self.column_menu.get()

        try:
            column_index = self._column_names.index(column_name)
        except ValueError:
            messagebox.showerror("Column Error", "Please choose a valid email column.")
            return

        self.skipped_invalid = []

        try:
            workbook = load_workbook(Path(path_text))
            sheet = workbook.active
            self.recipients = collect_recipients(
                sheet,
                column_index,
                on_invalid=lambda email: self.skipped_invalid.append(email),
            )
            workbook.close()
        except Exception as exc:
            messagebox.showerror("Excel Error", str(exc))
            return

        recipient_lower = {email.lower() for email in self.recipients}
        self.sent_recipients = [
            email for email in self.sent_recipients if email.lower() in recipient_lower
        ]
        self.failed_recipients = [
            email for email in self.failed_recipients if email.lower() in recipient_lower
        ]
        self._persist_campaign()

        self._update_recipient_preview()
        self._save_recipients(silent=True)
        self._append_log(f"Loaded {len(self.recipients)} recipient(s) from column '{column_name}'.")

    def _update_recipient_preview(self) -> None:
        pending = self._pending_recipients()
        total = len(self.recipients)
        sent_count = len(self.sent_recipients)
        failed_count = len(self.failed_recipients)
        pending_count = len(pending)

        self.recipient_count_label.configure(
            text=f"{total} total recipient{'s' if total != 1 else ''}",
            text_color=COLORS["success"] if total else COLORS["warning"],
        )

        if self.skipped_invalid:
            skipped_text = f"{len(self.skipped_invalid)} invalid address(es) skipped"
        elif total:
            skipped_text = "All addresses validated successfully"
        else:
            skipped_text = "No file loaded yet"
        self.skipped_label.configure(text=skipped_text)

        self.sent_count_label.configure(
            text=f"Sent: {sent_count}  |  Pending: {pending_count}  |  Failed: {failed_count}",
            text_color=COLORS["success"] if pending_count == 0 and sent_count else COLORS["muted"],
        )

        lines: list[str] = []
        if self.sent_recipients:
            lines.append("--- Already Sent ---")
            lines.extend(self.sent_recipients[:10])
            if len(self.sent_recipients) > 10:
                lines.append(f"... and {len(self.sent_recipients) - 10} more sent")
            lines.append("")

        if pending:
            lines.append("--- Pending ---")
            lines.extend(pending[:15])
            if len(pending) > 15:
                lines.append(f"... and {len(pending) - 15} more pending")
        elif total:
            lines.append("All recipients have been sent.")
        else:
            lines.append("Recipient preview will appear here...")

        text = "\n".join(lines)
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", "end")
        self.preview_box.insert("1.0", text)
        self.preview_box.configure(state="disabled")

    def _append_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _validate_form(self) -> tuple[bool, str]:
        if not self.sender_entry.get().strip():
            return False, "Sender email is required."
        if not self.password_entry.get():
            return False, "App password is required."
        if not self.excel_path_var.get().strip():
            return False, "Please select an Excel file."
        if not self.recipients:
            return False, "Load at least one valid recipient."
        if not self._pending_recipients():
            return False, "All recipients have already been sent. Reset campaign to send again."
        if not self.subject_entry.get().strip():
            return False, "Email subject is required."
        if self.body_editor.is_empty():
            return False, "Email body is required."

        try:
            int(self.smtp_port_entry.get().strip())
        except ValueError:
            return False, "SMTP port must be a number."

        return True, ""

    def _start_sending(self) -> None:
        if self._sending:
            return

        valid, error = self._validate_form()
        if not valid:
            messagebox.showwarning("Incomplete Setup", error)
            return

        pending = self._pending_recipients()
        if not messagebox.askyesno(
            "Confirm Send",
            f"Send to {len(pending)} pending recipient(s)?\n"
            f"({len(self.sent_recipients)} already sent will be skipped)",
        ):
            return

        self._save_account(silent=True)
        self._save_message(silent=True)
        self._save_recipients(silent=True)

        self._stop_requested = False
        self._sending = True
        self.send_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.set(0)
        self.status_label.configure(text="Starting delivery...", text_color=COLORS["muted"])

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        body_html = self.body_editor.get_html()
        body_plain = self.body_editor.get_plain_text()
        pending = list(self._pending_recipients())

        thread = threading.Thread(
            target=self._send_worker,
            args=(body_html, body_plain, pending),
            daemon=True,
        )
        thread.start()

    def _request_stop(self) -> None:
        if self._sending:
            self._stop_requested = True
            self.status_label.configure(text="Stopping after current email...", text_color=COLORS["warning"])
            self._append_log("Stop requested. Finishing current send...")

    def _send_worker(self, body_html: str, body_plain: str, pending: list[str]) -> None:
        sender = self.sender_entry.get().strip()
        app_password = self.password_entry.get()
        subject = self.subject_entry.get().strip()
        smtp_host = self.smtp_host_entry.get().strip() or DEFAULT_SMTP_HOST
        smtp_port = int(self.smtp_port_entry.get().strip())

        def on_progress(current: int, total: int, recipient: str, status: str) -> None:
            self.after(0, lambda: self._handle_progress(current, total, recipient, status))

        sent, failed = send_bulk_emails(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            sender=sender,
            app_password=app_password,
            recipients=pending,
            subject=subject,
            body_plain=body_plain,
            body_html=body_html,
            on_progress=on_progress,
            should_stop=lambda: self._stop_requested,
        )

        self.after(0, lambda: self._finish_sending(sent, failed))

    def _handle_progress(self, current: int, total: int, recipient: str, status: str) -> None:
        progress_value = current / total if total else 0
        self.progress.set(progress_value)

        if status == "sent":
            if recipient not in self.sent_recipients:
                self.sent_recipients.append(recipient)
            if recipient in self.failed_recipients:
                self.failed_recipients.remove(recipient)
            self._persist_campaign()
            self._update_recipient_preview()
            self.status_label.configure(
                text=f"Sent {current} of {total}",
                text_color=COLORS["success"],
            )
            self._append_log(f"[{current}/{total}] Sent to {recipient}")
        elif status == "failed":
            if recipient not in self.failed_recipients:
                self.failed_recipients.append(recipient)
            self._persist_campaign()
            self._update_recipient_preview()
            self.status_label.configure(
                text=f"Failed at {current} of {total}",
                text_color=COLORS["danger"],
            )
            self._append_log(f"[{current}/{total}] Failed for {recipient}")
        elif status == "auth_failed":
            self.status_label.configure(text="Authentication failed", text_color=COLORS["danger"])
            self._append_log("Authentication failed. Check email and app password.")
        elif status == "sending":
            self.status_label.configure(
                text=f"Sending {current} of {total}...",
                text_color=COLORS["muted"],
            )

    def _finish_sending(self, sent: int, failed: int) -> None:
        self._sending = False
        self.send_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

        if self._stop_requested:
            summary = f"Stopped. Sent: {sent}, Failed: {failed}"
            color = COLORS["warning"]
        elif failed == 0:
            summary = f"Complete. Sent: {sent}, Failed: {failed}"
            color = COLORS["success"]
        else:
            summary = f"Finished with errors. Sent: {sent}, Failed: {failed}"
            color = COLORS["danger"]

        self.status_label.configure(text=summary, text_color=color)
        self._append_log(summary)
        self._update_recipient_preview()

        if failed == 0 and not self._stop_requested:
            messagebox.showinfo("Delivery Complete", summary)
        elif failed:
            messagebox.showwarning("Delivery Finished", summary)


def main() -> None:
    app = MailSenderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
