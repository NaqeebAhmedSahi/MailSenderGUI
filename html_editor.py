"""Rich HTML email editor widgets.

* ``HtmlEditor``      - body editor with Visual / HTML Source / Preview tabs and
                        a draggable signature block.
* ``SignatureEditor`` - compact rich editor for the signature (bold, italic,
                        underline, colour, links and an inline logo).

Formatting lives in ``tk.Text`` tags and is converted to/from email-safe HTML
with ``text_widget_to_html`` and ``html_into_text_widget``.
"""

from __future__ import annotations

import html
import re
import tempfile
import tkinter as tk
import webbrowser
from pathlib import Path
import tkinter.font as tkfont
from html.parser import HTMLParser
from tkinter import colorchooser, messagebox, simpledialog
from typing import Callable

import customtkinter as ctk

try:
    from tkhtmlview import HTMLLabel
except ImportError:  # pragma: no cover
    HTMLLabel = None


PLACEHOLDER_VISUAL = "Write your email content here..."
PLACEHOLDER_SOURCE = "<p>Start writing your HTML email...</p>"
PLACEHOLDER_SOURCE_PLAIN = "Start writing your HTML email..."
SIGNATURE_MARKER = "{{SIGNATURE}}"
LOGO_MARKER = "{{LOGO}}"
LOGO_IMAGE_NAME = "sig_logo"
FONT_FAMILY = "Segoe UI"
# One-click text colours: signature navy, link blue, then common choices.
COLOR_SWATCHES = [
    ("#1f4e79", "Navy (signature)"),
    ("#1155cc", "Link blue"),
    ("#111827", "Black"),
    ("#6b7280", "Grey"),
    ("#c0392b", "Red"),
    ("#1e8449", "Green"),
    ("#d35400", "Orange"),
    ("#7d3c98", "Purple"),
]


# ----------------------------------------------------------------------
# Plain-text helpers
# ----------------------------------------------------------------------
def html_to_plain(html_body: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_body)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</h[1-6]>", "\n\n", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?i)</div>", "\n", text)
    text = re.sub(r"(?i)<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def wrap_email_html(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return ""
    if stripped.startswith("<"):
        return stripped
    return f"<div>{stripped}</div>"


# ----------------------------------------------------------------------
# Tag <-> HTML mapping
# ----------------------------------------------------------------------
def _link_tag_name(url: str) -> str:
    return "link_" + url.replace(":", "_COLON_").replace(" ", "_")


def _link_from_tag(tag_name: str) -> str:
    if not tag_name.startswith("link_"):
        return "#"
    return tag_name[5:].replace("_COLON_", ":")


def _tag_rank(tag: str) -> int | None:
    """Nesting order for exported tags (outermost first); None = not exported."""
    if tag.startswith("align_"):
        return 0
    if tag in {"h1", "h2", "h3"}:
        return 1
    if tag.startswith("link_"):
        return 2
    if tag.startswith("fg_"):
        return 3
    if tag.startswith("bg_"):
        return 4
    order = {"bold": 5, "italic": 6, "underline": 7, "strikethrough": 8}
    return order.get(tag)


def _open_tag(tag_name: str) -> str:
    if tag_name == "bold":
        return "<strong>"
    if tag_name == "italic":
        return "<em>"
    if tag_name == "underline":
        return "<u>"
    if tag_name == "strikethrough":
        return "<s>"
    if tag_name in {"h1", "h2", "h3"}:
        return f"<{tag_name}>"
    if tag_name.startswith("link_"):
        href = html.escape(_link_from_tag(tag_name), quote=True)
        return f'<a href="{href}" style="text-decoration:underline;">'
    if tag_name.startswith("fg_"):
        return f'<span style="color:{tag_name[3:]};">'
    if tag_name.startswith("bg_"):
        return f'<span style="background-color:{tag_name[3:]};">'
    if tag_name.startswith("align_"):
        return f'<div style="text-align:{tag_name[6:]};">'
    return ""


def _close_tag(tag_name: str) -> str:
    mapping = {
        "bold": "</strong>",
        "italic": "</em>",
        "underline": "</u>",
        "strikethrough": "</s>",
    }
    if tag_name in mapping:
        return mapping[tag_name]
    if tag_name in {"h1", "h2", "h3"}:
        return f"</{tag_name}>"
    if tag_name.startswith("link_"):
        return "</a>"
    if tag_name.startswith("fg_") or tag_name.startswith("bg_"):
        return "</span>"
    if tag_name.startswith("align_"):
        return "</div>"
    return ""


_BLOCK_CLOSES = ("</h1>", "</h2>", "</h3>", "</div>")


def text_widget_to_html(widget: tk.Text) -> str:
    """Serialise a tk.Text (text + formatting tags) to well-nested HTML.

    Embedded windows become SIGNATURE_MARKER and embedded images LOGO_MARKER.
    """
    dump = widget.dump("1.0", "end-1c", text=True, tag=True, window=True, image=True)
    if not dump:
        return ""

    out: list[str] = []
    active: set[str] = set()
    stack: list[str] = []

    def sync() -> None:
        desired = sorted(
            (tag for tag in active if _tag_rank(tag) is not None),
            key=lambda tag: (_tag_rank(tag), tag),
        )
        keep = 0
        while keep < len(stack) and keep < len(desired) and stack[keep] == desired[keep]:
            keep += 1
        for tag in reversed(stack[keep:]):
            out.append(_close_tag(tag))
        for tag in desired[keep:]:
            out.append(_open_tag(tag))
        stack[:] = desired

    for kind, value, _position in dump:
        if kind == "tagon":
            active.add(value)
        elif kind == "tagoff":
            active.discard(value)
        elif kind == "text":
            sync()
            for i, segment in enumerate(value.split("\n")):
                if i > 0 and not (out and out[-1] in _BLOCK_CLOSES):
                    out.append("<br>")
                if segment:
                    out.append(html.escape(segment))
        elif kind == "window":
            sync()
            out.append(SIGNATURE_MARKER)
        elif kind == "image":
            sync()
            out.append(LOGO_MARKER)

    active.clear()
    sync()
    return wrap_email_html("".join(out))


def _css_color(value: str) -> str | None:
    value = value.strip().lower()
    match = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)[^)]*\)", value)
    if match:
        return "#%02x%02x%02x" % tuple(min(255, int(part)) for part in match.groups())
    if re.fullmatch(r"#[0-9a-f]{3}([0-9a-f]{3})?", value) or re.fullmatch(r"[a-z]+", value):
        return value
    return None


class _HtmlImporter(HTMLParser):
    """Turn (our subset of) HTML into (text, tags) runs for a tk.Text."""

    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "li", "ul", "ol", "table", "tr"}
    VOID = {"br", "img", "hr", "meta", "link", "input"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.runs: list[tuple[str, tuple[str, ...]]] = []
        self.stack: list[tuple[str, list[str]]] = []

    def _at_line_start(self) -> bool:
        return not self.runs or self.runs[-1][0].endswith("\n")

    def _line_break(self) -> None:
        if not self._at_line_start():
            self.runs.append(("\n", ()))

    def _active_tags(self) -> tuple[str, ...]:
        tags: list[str] = []
        for _name, extra in self.stack:
            for tag in extra:
                # An inner colour overrides the outer one (e.g. blue link in navy text).
                for prefix in ("fg_", "bg_"):
                    if tag.startswith(prefix):
                        tags = [t for t in tags if not t.startswith(prefix)]
                if tag not in tags:
                    tags.append(tag)
        return tuple(tags)

    def handle_starttag(self, tag, attrs) -> None:
        attributes = {key: (value or "") for key, value in attrs}
        if tag == "br":
            self.runs.append(("\n", self._active_tags()))
            return
        if tag == "img":
            self.runs.append((LOGO_MARKER, ()))
            return
        if tag == "hr":
            self._line_break()
            return
        if tag in self.BLOCK:
            self._line_break()

        tags: list[str] = []
        if tag in {"b", "strong"}:
            tags.append("bold")
        elif tag in {"i", "em"}:
            tags.append("italic")
        elif tag == "u":
            tags.append("underline")
        elif tag in {"s", "strike", "del"}:
            tags.append("strikethrough")
        elif tag in {"h1", "h2", "h3"}:
            tags.append(tag)
        elif tag == "a" and attributes.get("href"):
            tags.append(_link_tag_name(attributes["href"]))

        if tag == "font" and attributes.get("color"):
            color = _css_color(attributes["color"])
            if color:
                tags.append(f"fg_{color}")
        for declaration in attributes.get("style", "").split(";"):
            if ":" not in declaration:
                continue
            prop, value = (part.strip().lower() for part in declaration.split(":", 1))
            if prop == "color":
                color = _css_color(value)
                if color:
                    tags.append(f"fg_{color}")
            elif prop in {"background-color", "background"}:
                color = _css_color(value)
                if color:
                    tags.append(f"bg_{color}")
            elif prop == "text-align" and value in {"left", "center", "right"}:
                tags.append(f"align_{value}")
            elif prop == "font-weight" and (value == "bold" or value.isdigit() and int(value) >= 600):
                tags.append("bold")
            elif prop == "font-style" and value == "italic":
                tags.append("italic")
            elif prop == "text-decoration" and "underline" in value and tag != "a":
                tags.append("underline")  # links are underlined by default
            elif prop == "text-decoration" and "line-through" in value:
                tags.append("strikethrough")

        if tag not in self.VOID:
            self.stack.append((tag, tags))

    def handle_endtag(self, tag) -> None:
        for position in range(len(self.stack) - 1, -1, -1):
            if self.stack[position][0] == tag:
                del self.stack[position:]
                break
        if tag in self.BLOCK:
            self._line_break()

    def handle_data(self, data) -> None:
        text = re.sub(r"\s+", " ", data)
        if self._at_line_start():
            text = text.lstrip()
        if text:
            self.runs.append((text, self._active_tags()))


def html_into_text_widget(
    widget: tk.Text,
    content: str,
    style_tag: Callable[[str], None],
    at: str = "end",
) -> None:
    """Insert HTML (or plain text if it has no tags) into ``widget``."""
    content = content or ""
    if "<" not in content:
        widget.insert(at, content)
        return
    importer = _HtmlImporter()
    importer.feed(content)
    importer.close()
    runs = importer.runs
    # Trim trailing line breaks produced by closing block tags.
    while runs and runs[-1][0] == "\n":
        runs.pop()
    for text, tags in runs:
        for tag in tags:
            style_tag(tag)
        widget.insert(at, text, tags)


def copy_rich_text(src: tk.Text, dst: tk.Text, style_tag: Callable[[str], None]) -> None:
    """Copy text, tags and images from ``src`` into ``dst``."""
    active: list[str] = []
    for kind, value, _position in src.dump("1.0", "end-1c", text=True, tag=True, image=True):
        if kind == "tagon":
            active.append(value)
            style_tag(value)
        elif kind == "tagoff" and value in active:
            active.remove(value)
        elif kind == "text":
            dst.insert("end", value, tuple(active))
        elif kind == "image":
            dst.image_create("end", image=src.image_cget(value, "image"))


class _Tooltip:
    """Minimal hover tooltip."""

    def __init__(self, widget, text: str) -> None:
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 4
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg="#111827", fg="#F8FAFC",
                 font=(FONT_FAMILY, 9), padx=6, pady=2).pack()

    def _hide(self, _event=None) -> None:
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


# ----------------------------------------------------------------------
# Shared formatting behaviour
# ----------------------------------------------------------------------
class RichTextMixin:
    """Formatting commands for a tk.Text stored in ``self._rt``."""

    _rt: tk.Text
    colors: dict[str, str]
    on_change: Callable[[], None] | None = None

    def _configure_base_tags(self, size: int) -> None:
        text = self._rt
        text.tag_configure("bold", font=(FONT_FAMILY, size, "bold"))
        text.tag_configure("italic", font=(FONT_FAMILY, size, "italic"))
        text.tag_configure("underline", underline=True)
        text.tag_configure("strikethrough", overstrike=True)
        text.tag_configure("h1", font=(FONT_FAMILY, size + 9, "bold"), spacing3=8)
        text.tag_configure("h2", font=(FONT_FAMILY, size + 5, "bold"), spacing3=6)
        text.tag_configure("h3", font=(FONT_FAMILY, size + 2, "bold"), spacing3=4)
        text.tag_configure("align_center", justify="center")
        text.tag_configure("align_right", justify="right")
        text.tag_configure("align_left", justify="left")

    def _style_tag(self, tag: str, text: tk.Text | None = None) -> None:
        """Give dynamic tags (links/colours) their on-screen look."""
        text = text or self._rt
        try:
            if tag.startswith("link_"):
                text.tag_configure(tag, foreground="#3B82F6", underline=True)
                self._bind_link_cursor(text, tag)
            elif tag.startswith("fg_"):
                text.tag_configure(tag, foreground=tag[3:])
            elif tag.startswith("bg_"):
                text.tag_configure(tag, background=tag[3:])
        except tk.TclError:
            pass  # unknown colour name - keep the tag, skip the styling
        # Character formatting must win over colour tags for fonts.
        for raised in ("bold", "italic", "underline", "strikethrough"):
            try:
                text.tag_raise(raised)
            except tk.TclError:
                pass

    @staticmethod
    def _bind_link_cursor(text: tk.Text, tag: str) -> None:
        """Show a hand cursor while the mouse is over a link."""
        if getattr(text, "_link_cursor_tags", None) is None:
            text._link_cursor_tags = set()
        if tag in text._link_cursor_tags:
            return
        text._link_cursor_tags.add(tag)

        def on_enter(_event, widget=text):
            if not hasattr(widget, "_cursor_before_link"):
                widget._cursor_before_link = widget.cget("cursor")
            widget.configure(cursor="hand2")

        def on_leave(_event, widget=text):
            widget.configure(cursor=getattr(widget, "_cursor_before_link", "xterm"))
            if hasattr(widget, "_cursor_before_link"):
                del widget._cursor_before_link

        text.tag_bind(tag, "<Enter>", on_enter)
        text.tag_bind(tag, "<Leave>", on_leave)

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def _selection_range(self):
        text = self._rt
        if text.tag_ranges(tk.SEL):
            return text.index("sel.first"), text.index("sel.last")
        cursor = text.index("insert")
        return cursor, cursor

    def _toggle_tag(self, tag: str) -> None:
        start, end = self._selection_range()
        if start == end:
            return
        if tag in self._rt.tag_names(start):
            self._rt.tag_remove(tag, start, end)
        else:
            self._rt.tag_add(tag, start, end)
        self._changed()

    def _apply_heading(self, tag: str) -> None:
        start, _end = self._selection_range()
        line = start.split(".")[0]
        for heading in ("h1", "h2", "h3"):
            self._rt.tag_remove(heading, f"{line}.0", f"{line}.end")
        self._rt.tag_add(tag, f"{line}.0", f"{line}.end")
        self._changed()

    def _clear_format(self) -> None:
        start, end = self._selection_range()
        if start == end:
            line = start.split(".")[0]
            start, end = f"{line}.0", f"{line}.end"
        for tag in self._rt.tag_names():
            if tag not in (tk.SEL, "sig_drop"):
                self._rt.tag_remove(tag, start, end)
        self._changed()

    def _line_prefix(self, prefix: str) -> None:
        line = self._rt.index("insert").split(".")[0]
        self._rt.insert(f"{line}.0", prefix)
        self._changed()

    def _bullet_list(self) -> None:
        self._line_prefix("• ")

    def _number_list(self) -> None:
        line = int(self._rt.index("insert").split(".")[0])
        self._line_prefix(f"{line}. ")

    def _insert_link(self) -> None:
        start, end = self._selection_range()
        url = simpledialog.askstring(
            "Insert Link",
            "Enter URL (https://..., mailto:..., tel:...):",
            parent=self._rt.winfo_toplevel(),
        )
        if not url:
            return
        url = url.strip()
        if start == end:
            self._rt.insert(start, url)
            end = self._rt.index(f"{start}+{len(url)}c")
        for tag in self._rt.tag_names(start):
            if tag.startswith("link_"):
                self._rt.tag_remove(tag, start, end)
        tag = _link_tag_name(url)
        self._style_tag(tag)
        self._rt.tag_add(tag, start, end)
        self._changed()

    def _require_selection(self):
        start, end = self._selection_range()
        if start == end:
            messagebox.showinfo(
                "Select text first",
                "Highlight the text you want to change, then click the colour.",
                parent=self._rt.winfo_toplevel(),
            )
            return None
        return start, end

    def _set_color(self, prefix: str, color: str, start: str, end: str) -> None:
        for tag in self._rt.tag_names():
            if tag.startswith(prefix):
                self._rt.tag_remove(tag, start, end)
        tag = f"{prefix}{color.lower()}"
        self._style_tag(tag)
        self._rt.tag_add(tag, start, end)
        self._changed()

    def _apply_color_tag(self, prefix: str, title: str) -> None:
        selection = self._require_selection()
        if selection is None:
            return
        color = colorchooser.askcolor(title=title, parent=self._rt.winfo_toplevel())
        if not color or not color[1]:
            return
        self._set_color(prefix, color[1], *selection)

    def _apply_swatch(self, color: str) -> None:
        selection = self._require_selection()
        if selection is not None:
            self._set_color("fg_", color, *selection)

    def _color_swatches(self, parent, label: str = "Text color:") -> None:
        """Row of one-click colour buttons (plus the Color... picker)."""
        ctk.CTkLabel(parent, text=label, text_color=self.colors["muted"],
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 6))
        for color, name in COLOR_SWATCHES:
            swatch = ctk.CTkButton(
                parent,
                text="",
                width=24,
                height=24,
                corner_radius=6,
                fg_color=color,
                hover_color=color,
                border_width=2,
                border_color=self.colors["border"],
                command=lambda c=color: self._apply_swatch(c),
            )
            swatch.pack(side="left", padx=2)
            _Tooltip(swatch, name)
        self._tool_btn(parent, "More colors...", self._pick_text_color, width=110)

    def _pick_text_color(self) -> None:
        self._apply_color_tag("fg_", "Text color")

    def _pick_highlight(self) -> None:
        self._apply_color_tag("bg_", "Highlight color")

    def _align(self, direction: str) -> None:
        start, _end = self._selection_range()
        line = start.split(".")[0]
        for tag in ("align_left", "align_center", "align_right"):
            self._rt.tag_remove(tag, f"{line}.0", f"{line}.end")
        self._rt.tag_add(f"align_{direction}", f"{line}.0", f"{line}.end")
        self._changed()

    def _tool_btn(self, parent, text: str, command, width: int = 52) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=30,
            corner_radius=8,
            fg_color=self.colors["surface_alt"],
            hover_color=self.colors["border"],
            border_width=1,
            border_color=self.colors["border"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=command,
        )
        btn.pack(side="left", padx=3)
        return btn

    def _tool_sep(self, parent) -> None:
        sep = ctk.CTkFrame(parent, width=2, height=24, fg_color=self.colors["border"])
        sep.pack(side="left", padx=6)

    def _make_text(self, parent, size: int, height: int) -> tk.Text:
        return tk.Text(
            parent,
            wrap=tk.WORD,
            undo=True,
            maxundo=-1,
            padx=14,
            pady=12,
            relief=tk.FLAT,
            borderwidth=0,
            height=height,
            bg=self.colors["surface_alt"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.colors["text"],
            inactiveselectbackground=self.colors["border"],
            font=(FONT_FAMILY, size),
        )


# ----------------------------------------------------------------------
# Body editor
# ----------------------------------------------------------------------
class HtmlEditor(RichTextMixin, ctk.CTkFrame):
    """Three-tab HTML editor: visual toolbar, raw HTML, and live preview."""

    def __init__(self, master, colors: dict[str, str], height: int = 340, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.colors = colors
        self._height = height
        self._active_tab = "Visual Editor"
        self._source_synced = ""
        # Signature block support (set by the host app).
        self.signature_renderer: Callable[[tk.Widget], None] | None = None
        self.preview_builder: Callable[[str], str] | None = None
        self._signature_block: tk.Frame | None = None
        self._drag_active = False
        self._drag_start = (0, 0)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(
            self,
            height=height,
            fg_color=colors["surface_alt"],
            segmented_button_fg_color=colors["surface"],
            segmented_button_selected_color=colors["accent"],
            segmented_button_selected_hover_color=colors["accent_hover"],
            segmented_button_unselected_color=colors["surface"],
            segmented_button_unselected_hover_color=colors["border"],
            text_color=colors["text"],
            command=self._on_tab_change,
        )
        self.tabs.grid(row=0, column=0, sticky="nsew")
        self.tabs.add("Visual Editor")
        self.tabs.add("HTML Source")
        self.tabs.add("Preview")

        self._build_visual_tab(self.tabs.tab("Visual Editor"))
        self._build_source_tab(self.tabs.tab("HTML Source"))
        self._build_preview_tab(self.tabs.tab("Preview"))

    def _build_visual_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(parent, fg_color=self.colors["surface"], corner_radius=10)
        toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))

        row1 = ctk.CTkFrame(toolbar, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=(8, 4))
        row2 = ctk.CTkFrame(toolbar, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(0, 4))
        row3 = ctk.CTkFrame(toolbar, fg_color="transparent")
        row3.pack(fill="x", padx=8, pady=(0, 8))
        self._color_swatches(row3)

        for label, tag in [("B", "bold"), ("I", "italic"), ("U", "underline"), ("S", "strikethrough")]:
            self._tool_btn(row1, label, lambda t=tag: self._toggle_tag(t))
        self._tool_sep(row1)
        for label, tag in [("H1", "h1"), ("H2", "h2"), ("H3", "h3")]:
            self._tool_btn(row1, label, lambda t=tag: self._apply_heading(t))
        self._tool_sep(row1)
        self._tool_btn(row1, "Clear", self._clear_format)

        self._tool_btn(row2, "• List", self._bullet_list)
        self._tool_btn(row2, "1. List", self._number_list)
        self._tool_btn(row2, "Link", self._insert_link)
        self._tool_btn(row2, "Highlight", self._pick_highlight)
        self._tool_sep(row2)
        self._tool_btn(row2, "Left", lambda: self._align("left"))
        self._tool_btn(row2, "Center", lambda: self._align("center"))
        self._tool_btn(row2, "Right", lambda: self._align("right"))

        editor_shell = tk.Frame(
            parent,
            bg=self.colors["surface_alt"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        editor_shell.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))

        self.visual_editor = self._make_text(editor_shell, size=13, height=12)
        # White page so text colours look exactly like in the email.
        self.visual_editor.configure(bg="#FFFFFF", fg="#111827", insertbackground="#111827",
                                     selectforeground="#FFFFFF")
        editor_shell.configure(bg="#FFFFFF")
        self._rt = self.visual_editor
        self.visual_editor.pack(fill="both", expand=True)
        self.visual_editor.insert("1.0", PLACEHOLDER_VISUAL)
        self.visual_editor.bind("<FocusIn>", self._clear_visual_placeholder)
        self._visual_has_placeholder = True

        self._configure_base_tags(13)
        self.visual_editor.tag_configure("sig_drop", background=self.colors["accent"])

    def _build_source_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self.source_box = ctk.CTkTextbox(
            parent,
            corner_radius=10,
            fg_color=self.colors["surface_alt"],
            border_color=self.colors["border"],
            border_width=1,
            text_color=self.colors["text"],
            font=ctk.CTkFont(family="Consolas", size=12),
            activate_scrollbars=True,
        )
        self.source_box.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.source_box.insert("1.0", PLACEHOLDER_SOURCE)
        self.source_box.bind("<FocusIn>", self._clear_source_placeholder)
        self._source_has_placeholder = True

    def _build_preview_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        ctk.CTkLabel(
            bar,
            text="Quick preview. For the exact look in Gmail/Outlook use Open in Browser.",
            text_color=self.colors["muted"],
            font=ctk.CTkFont(size=11),
        ).pack(side="left")
        ctk.CTkButton(
            bar,
            text="Open in Browser",
            width=140,
            height=30,
            corner_radius=8,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
            command=self.open_in_browser,
        ).pack(side="right")

        shell = tk.Frame(
            parent,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        shell.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        if HTMLLabel is not None:
            self.preview_label = HTMLLabel(
                shell,
                html=self._preview_document("<p>Preview will appear here.</p>"),
                background="#FFFFFF",
            )
            self.preview_label.pack(fill="both", expand=True, padx=12, pady=10)
        else:
            self.preview_label = tk.Label(
                shell,
                text="Install tkhtmlview for live HTML preview.",
                bg=self.colors["surface_alt"],
                fg=self.colors["muted"],
                font=(FONT_FAMILY, 12),
                justify=tk.LEFT,
                anchor="nw",
            )
            self.preview_label.pack(fill="both", expand=True, padx=12, pady=12)

    def _preview_document(self, body: str) -> str:
        """HTML for tkhtmlview, which supports inline styles only (no <style>)."""
        # tkhtmlview adds a line break per closing </div>: unwrap the logo.
        body = re.sub(r"(?is)(?:<div[^>]*>\s*)+(<img[^>]*>)(?:\s*</div>)+", r"\1<br>", body)
        # ...and drops empty lines (even &nbsp;), so hold them open with an
        # invisible white character. Preview only, never sent.
        body = re.sub(r"(?i)<br\s*/?>(?=\s*<br)", '<br><span style="color:#ffffff;">.</span>', body)
        body = re.sub(
            r"(?i)<hr[^>]*>",
            '<div style="color:#cccccc;">' + "\u2500" * 60 + "</div>",
            body,
        )
        return (
            '<div style="font-family:Calibri,Segoe UI,Arial;font-size:11px;color:#111827;">'
            f"{body}</div>"
        )

    def _email_document(self, body: str) -> str:
        """Full HTML page that looks like the email in a mail client."""
        def to_uri(match: re.Match) -> str:
            src = html.unescape(match.group(1))
            if re.match(r"(?i)^(https?|cid|file|data):", src):
                return match.group(0)
            try:
                return f'src="{Path(src).resolve().as_uri()}"'
            except ValueError:
                return match.group(0)

        body = re.sub(r'src="([^"]+)"', to_uri, body)
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Email preview</title>"
            "<style>body{margin:0;background:#f1f3f4;}"
            ".mail{max-width:760px;margin:24px auto;background:#fff;padding:28px 32px;"
            "border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.15);"
            "font-family:Calibri,'Segoe UI',Arial,sans-serif;font-size:15px;color:#111827;}"
            "</style></head>"
            f"<body><div class='mail'>{body}</div></body></html>"
        )

    def _current_preview_body(self) -> str:
        content = self.get_html()
        if self.preview_builder is not None:
            return self.preview_builder(content)
        return content.replace(SIGNATURE_MARKER, "")

    def open_in_browser(self) -> None:
        path = Path(tempfile.gettempdir()) / "mailflow_email_preview.html"
        path.write_text(self._email_document(self._current_preview_body()), encoding="utf-8")
        webbrowser.open(path.as_uri())

    # -- placeholders ---------------------------------------------------
    def _clear_visual_placeholder(self, _event=None) -> None:
        if not self._visual_has_placeholder:
            return
        current = self.visual_editor.get("1.0", "end-1c")
        if current.strip() == PLACEHOLDER_VISUAL:
            self.visual_editor.delete("1.0", "end")
        self._visual_has_placeholder = False

    def _clear_source_placeholder(self, _event=None) -> None:
        if not self._source_has_placeholder:
            return
        current = self.source_box.get("1.0", "end").strip()
        if current == PLACEHOLDER_SOURCE or html_to_plain(current) == PLACEHOLDER_SOURCE_PLAIN:
            self.source_box.delete("1.0", "end")
        self._source_has_placeholder = False

    def _visual_plain(self) -> str:
        return self.visual_editor.get("1.0", "end-1c").strip()

    def _source_raw(self) -> str:
        return self.source_box.get("1.0", "end").strip()

    def _is_visual_empty(self) -> bool:
        text = self._visual_plain()
        return not text or text == PLACEHOLDER_VISUAL

    def _is_source_empty(self) -> bool:
        text = self._source_raw()
        if not text or text == PLACEHOLDER_SOURCE:
            return True
        plain = html_to_plain(text)
        return not plain or plain == PLACEHOLDER_SOURCE_PLAIN

    # -- tabs -----------------------------------------------------------
    def _on_tab_change(self) -> None:
        tab = self.tabs.get()
        if tab == "HTML Source" and self._active_tab == "Visual Editor":
            html_body = text_widget_to_html(self.visual_editor)
            self.source_box.delete("1.0", "end")
            self.source_box.insert("1.0", html_body)
            self._source_synced = html_body
            self._source_has_placeholder = False
        elif tab == "Visual Editor" and self._active_tab == "HTML Source":
            # Bring hand-edited HTML back into the visual editor.
            source = self._source_raw()
            if source != self._source_synced and not self._is_source_empty():
                self._load_visual(source)
                self._source_synced = source
        elif tab == "Preview":
            self._refresh_preview()
        if tab != "Preview":
            self._active_tab = tab

    def _refresh_preview(self) -> None:
        content = self._current_preview_body()
        if HTMLLabel is not None and isinstance(self.preview_label, HTMLLabel):
            self.preview_label.set_html(self._preview_document(content))
            # Roomier lines, closer to how the email reads.
            self.preview_label.configure(spacing1=3, spacing3=3, background="#FFFFFF")

    # -- public API -----------------------------------------------------
    def get_html(self) -> str:
        self._clear_visual_placeholder()
        self._clear_source_placeholder()

        visual_empty = self._is_visual_empty() and not self.has_signature_block()
        source_empty = self._is_source_empty()

        if self._active_tab == "HTML Source" and not source_empty:
            return wrap_email_html(self._source_raw())
        if not visual_empty:
            return text_widget_to_html(self.visual_editor)
        if not source_empty:
            return wrap_email_html(self._source_raw())
        return ""

    def get_plain_text(self) -> str:
        html_body = self.get_html()
        return html_to_plain(html_body) if html_body else ""

    def is_empty(self) -> bool:
        self._clear_visual_placeholder()
        self._clear_source_placeholder()
        return self._is_visual_empty() and self._is_source_empty()

    def _remove_text(self, needle: str) -> None:
        text = self.visual_editor
        while True:
            found = text.search(needle, "1.0", "end")
            if not found:
                return
            text.delete(found, f"{found}+{len(needle)}c")

    def _load_visual(self, html_content: str) -> None:
        text = self.visual_editor
        self._signature_block = None
        text.delete("1.0", "end")
        html_into_text_widget(text, html_content, self._style_tag)
        self._remove_text(LOGO_MARKER)  # no meaning in the body
        marker = text.search(SIGNATURE_MARKER, "1.0", "end")
        if marker:
            text.delete(marker, f"{marker}+{len(SIGNATURE_MARKER)}c")
            self._remove_text(SIGNATURE_MARKER)
            if self.signature_renderer is not None:
                self._visual_has_placeholder = False
                self.insert_signature_block(marker, own_line=False)
        if text.get("1.0", "end-1c").strip() or self.has_signature_block():
            self._visual_has_placeholder = False
        else:
            text.delete("1.0", "end")
            text.insert("1.0", PLACEHOLDER_VISUAL)
            self._visual_has_placeholder = True

    def set_html(self, html_content: str) -> None:
        html_content = (html_content or "").strip()
        self.source_box.delete("1.0", "end")
        self.source_box.insert("1.0", html_content or PLACEHOLDER_SOURCE)
        self._source_has_placeholder = not html_content
        self._source_synced = html_content
        self._load_visual(html_content)
        self._active_tab = "Visual Editor"
        self.tabs.set("Visual Editor")

    def get_scroll_widgets(self) -> list:
        return [self.source_box, self.visual_editor]

    # ------------------------------------------------------------------
    # Draggable signature block
    # ------------------------------------------------------------------
    def has_signature_block(self) -> bool:
        block = self._signature_block
        if block is None:
            return False
        try:
            if not block.winfo_exists():
                raise tk.TclError
            self.visual_editor.index(block)
        except tk.TclError:
            # User deleted it with Backspace/Delete.
            self._signature_block = None
            return False
        return True

    def insert_signature_block(self, index: str | None = None, own_line: bool = True) -> None:
        """Embed the signature block at ``index`` (default: cursor, else end)."""
        if self.signature_renderer is None:
            return
        self._clear_visual_placeholder()
        self.remove_signature_block()
        text = self.visual_editor
        if index is None:
            index = text.index("insert") if text.get("1.0", "end-1c") else "1.0"
        index = text.index(index)
        if own_line:
            index = text.index(f"{index} linestart")
            if text.get(index, f"{index} lineend"):
                text.insert(index, "\n")
        block = self._build_signature_block()
        text.window_create(index, window=block, align="top", padx=2, pady=4)
        self._signature_block = block
        if self._active_tab == "HTML Source":
            self._active_tab = "Visual Editor"

    def remove_signature_block(self) -> None:
        if not self.has_signature_block():
            self._signature_block = None
            return
        text = self.visual_editor
        index = text.index(self._signature_block)
        text.delete(index)  # destroys the embedded frame
        self._signature_block = None
        if not text.get(f"{index} linestart", f"{index} lineend") and text.compare(
            f"{index} lineend", "<", "end-1c"
        ):
            text.delete(f"{index} lineend")

    def refresh_signature_block(self) -> None:
        """Re-render the block in place after the signature changed."""
        if not self.has_signature_block():
            return
        text = self.visual_editor
        index = text.index(self._signature_block)
        text.delete(index)
        block = self._build_signature_block()
        text.window_create(index, window=block, align="top", padx=2, pady=4)
        self._signature_block = block

    def _build_signature_block(self) -> tk.Frame:
        colors = self.colors
        block = tk.Frame(
            self.visual_editor,
            bg=colors["surface"],
            highlightthickness=2,
            highlightbackground=colors["accent"],
            highlightcolor=colors["accent"],
            cursor="fleur",
        )
        handle = tk.Label(
            block,
            text="✥  Signature — drag to move",
            bg=colors["accent"],
            fg="#FFFFFF",
            font=(FONT_FAMILY, 9, "bold"),
            anchor="w",
            padx=8,
            pady=2,
            cursor="fleur",
        )
        handle.pack(fill="x")
        content = tk.Frame(block, bg="#FFFFFF", cursor="fleur")
        content.pack(fill="both", expand=True, padx=2, pady=2)
        if self.signature_renderer is not None:
            self.signature_renderer(content)
        self._bind_drag(block)
        return block

    def _bind_drag(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._on_sig_press, add="+")
        widget.bind("<B1-Motion>", self._on_sig_motion, add="+")
        widget.bind("<ButtonRelease-1>", self._on_sig_release, add="+")
        for child in widget.winfo_children():
            self._bind_drag(child)

    def _drop_index(self, event) -> str:
        text = self.visual_editor
        x = event.x_root - text.winfo_rootx()
        y = event.y_root - text.winfo_rooty()
        height = text.winfo_height()
        if y < 10:
            text.yview_scroll(-1, "units")
        elif y > height - 10:
            text.yview_scroll(1, "units")
        x = max(0, min(x, text.winfo_width() - 1))
        y = max(0, min(y, height - 1))
        return text.index(f"@{x},{y} linestart")

    def _on_sig_press(self, event) -> str:
        self._drag_start = (event.x_root, event.y_root)
        self._drag_active = False
        return "break"

    def _on_sig_motion(self, event) -> str:
        dx = abs(event.x_root - self._drag_start[0])
        dy = abs(event.y_root - self._drag_start[1])
        if not self._drag_active and max(dx, dy) < 6:
            return "break"
        self._drag_active = True
        text = self.visual_editor
        target = self._drop_index(event)
        text.tag_remove("sig_drop", "1.0", "end")
        text.tag_add("sig_drop", target, f"{target} lineend+1c")
        return "break"

    def _on_sig_release(self, event) -> str:
        text = self.visual_editor
        text.tag_remove("sig_drop", "1.0", "end")
        if not self._drag_active or not self.has_signature_block():
            return "break"
        self._drag_active = False
        target = self._drop_index(event)
        current = text.index(self._signature_block)
        if text.index(f"{current} linestart") == target:
            return "break"
        text.mark_set("sig_target", target)
        text.mark_gravity("sig_target", "left")
        self.remove_signature_block()
        self.insert_signature_block(text.index("sig_target"))
        text.mark_unset("sig_target")
        return "break"


# ----------------------------------------------------------------------
# Signature editor
# ----------------------------------------------------------------------
class SignatureEditor(RichTextMixin, ctk.CTkFrame):
    """Compact rich editor for the email signature with an inline logo."""

    FONT_SIZE = 11

    def __init__(
        self,
        master,
        colors: dict[str, str],
        on_logo_request: Callable[[], None] | None = None,
        height: int = 9,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.colors = colors
        self.on_change = None
        self._on_logo_request = on_logo_request
        self._logo_photo = None

        toolbar = ctk.CTkFrame(self, fg_color=colors["surface"], corner_radius=10)
        toolbar.pack(fill="x", pady=(0, 6))
        row = ctk.CTkFrame(toolbar, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(6, 3))
        swatch_row = ctk.CTkFrame(toolbar, fg_color="transparent")
        swatch_row.pack(fill="x", padx=8, pady=(0, 6))
        self._color_swatches(swatch_row)

        self._tool_btn(row, "B", lambda: self._toggle_tag("bold"), width=34)
        self._tool_btn(row, "I", lambda: self._toggle_tag("italic"), width=34)
        self._tool_btn(row, "U", lambda: self._toggle_tag("underline"), width=34)
        self._tool_sep(row)
        self._tool_btn(row, "Link", self._insert_link, width=52)
        self._tool_sep(row)
        self._tool_btn(row, "Insert Logo Here", self._request_logo, width=130)
        self._tool_btn(row, "Clear", self._clear_format, width=56)

        shell = tk.Frame(self, bg="#FFFFFF", highlightthickness=1,
                         highlightbackground=colors["border"])
        shell.pack(fill="x")
        self.text = self._make_text(shell, size=self.FONT_SIZE, height=height)
        # White page so colours look like they will in the email.
        self.text.configure(bg="#FFFFFF", fg="#111827", insertbackground="#111827",
                            selectforeground="#FFFFFF")
        self.text.pack(fill="both", expand=True)
        self._rt = self.text
        self._configure_base_tags(self.FONT_SIZE)
        self.text.bind("<<Modified>>", self._on_modified)

    def _on_modified(self, _event=None) -> None:
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._changed()

    def _request_logo(self) -> None:
        if self._on_logo_request is not None:
            self._on_logo_request()

    # -- content --------------------------------------------------------
    def is_empty(self) -> bool:
        return not self.text.get("1.0", "end-1c").strip() and not self.has_logo()

    def get_html(self) -> str:
        if self.is_empty():
            return ""
        return text_widget_to_html(self.text)

    def set_content(self, content: str) -> None:
        self.text.delete("1.0", "end")
        html_into_text_widget(self.text, content or "", self._style_tag)
        self._place_logo_at_marker()
        self.text.edit_reset()
        self._changed()

    def _place_logo_at_marker(self) -> None:
        """Swap a typed {{LOGO}} placeholder for the logo image (once one exists)."""
        if self._logo_photo is None:
            return  # keep the placeholder visible until a logo is uploaded
        marker = self.text.search(LOGO_MARKER, "1.0", "end")
        while marker:
            self.text.delete(marker, f"{marker}+{len(LOGO_MARKER)}c")
            if not self.has_logo():
                self.text.image_create(marker, image=self._logo_photo, name=LOGO_IMAGE_NAME)
            marker = self.text.search(LOGO_MARKER, "1.0", "end")

    # -- logo -----------------------------------------------------------
    def has_logo(self) -> bool:
        try:
            self.text.index(LOGO_IMAGE_NAME)
        except tk.TclError:
            return False
        return True

    def set_logo_photo(self, photo) -> None:
        """Remember the logo image; replace an existing logo in place."""
        self._logo_photo = photo
        if self.has_logo():
            index = self.text.index(LOGO_IMAGE_NAME)
            self.text.delete(index)
            if photo is not None:
                self.text.image_create(index, image=photo, name=LOGO_IMAGE_NAME)
            self._changed()
        elif photo is not None and self.text.search(LOGO_MARKER, "1.0", "end"):
            self._place_logo_at_marker()
            self._changed()

    def has_logo_position(self) -> bool:
        return self.has_logo() or bool(self.text.search(LOGO_MARKER, "1.0", "end"))

    def insert_logo(self, at: str | None = None) -> None:
        """Place the logo at ``at`` (default: cursor) on its own line."""
        if self._logo_photo is None:
            return
        self.remove_logo()
        text = self.text
        index = text.index(at or "insert")
        if text.get(f"{index} linestart", index).strip():
            text.insert(index, "\n")
            index = text.index(f"{index}+1c")
        text.image_create(index, image=self._logo_photo, name=LOGO_IMAGE_NAME)
        after = text.index(f"{LOGO_IMAGE_NAME}+1c")
        if text.get(after, f"{after} lineend").strip():
            text.insert(after, "\n")
        self._changed()

    def remove_logo(self) -> None:
        if self.has_logo():
            self.text.delete(self.text.index(LOGO_IMAGE_NAME))
            self._changed()

    # -- rendering for the draggable card -------------------------------
    def render_into(self, parent: tk.Widget) -> None:
        """Draw a read-only copy of the signature (text, colours, logo)."""
        if self.is_empty():
            tk.Label(parent, text="(empty signature)", bg="#FFFFFF", fg="#64748B",
                     font=(FONT_FAMILY, 10, "italic"), cursor="fleur").pack(anchor="w", padx=8, pady=6)
            return
        size = self.FONT_SIZE
        normal = tkfont.Font(family=FONT_FAMILY, size=size)
        bold = tkfont.Font(family=FONT_FAMILY, size=size, weight="bold")
        line_px = max(normal.metrics("linespace"), bold.metrics("linespace"))
        image_lines: dict[int, tuple[int, int]] = {}
        for _kind, value, position in self.text.dump("1.0", "end-1c", image=True):
            photo = self.text.image_cget(value, "image")
            line = int(position.split(".")[0])
            image_lines[line] = (
                int(self.text.tk.call("image", "width", photo)),
                int(self.text.tk.call("image", "height", photo)),
            )
        lines = self.text.get("1.0", "end-1c").split("\n")
        height = 0
        width = 0
        for number, line in enumerate(lines, start=1):
            img_w, img_h = image_lines.get(number, (0, 0))
            height += max(line_px, img_h + 4)
            width = max(width, bold.measure(line) + img_w)

        holder = tk.Frame(parent, bg="#FFFFFF", width=min(width + 30, 640),
                          height=height + 16, cursor="fleur")
        holder.pack_propagate(False)
        holder.pack(anchor="w")
        copy = tk.Text(holder, wrap=tk.NONE, relief=tk.FLAT, borderwidth=0, padx=8, pady=6,
                       bg="#FFFFFF", fg="#111827", font=(FONT_FAMILY, size), cursor="fleur",
                       highlightthickness=0)
        copy.pack(fill="both", expand=True)
        saved = self._rt
        self._rt = copy
        self._configure_base_tags(size)
        self._rt = saved
        copy_rich_text(self.text, copy, lambda tag: self._style_tag(tag, copy))
        copy.configure(state="disabled")
