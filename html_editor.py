"""Rich HTML email editor widget with visual, source, and preview tabs."""

from __future__ import annotations

import html
import re
import tkinter as tk
from tkinter import colorchooser, simpledialog

import customtkinter as ctk

try:
    from tkhtmlview import HTMLLabel
except ImportError:  # pragma: no cover
    HTMLLabel = None


PLACEHOLDER_VISUAL = "Write your email content here..."
PLACEHOLDER_SOURCE = "<p>Start writing your HTML email...</p>"
PLACEHOLDER_SOURCE_PLAIN = "Start writing your HTML email..."


def html_to_plain(html_body: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_body)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</h[1-6]>", "\n\n", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?i)<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def wrap_email_html(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return ""
    if stripped.startswith("<"):
        return stripped
    return f"<p>{stripped}</p>"


def _link_tag_name(url: str) -> str:
    return "link_" + url.replace(":", "_COLON_").replace(" ", "_")


def _link_from_tag(tag_name: str) -> str:
    if not tag_name.startswith("link_"):
        return "#"
    return tag_name[5:].replace("_COLON_", ":")


def _open_tag(tag_name: str, _widget: tk.Text) -> str:
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
        return f'<a href="{href}">'
    if tag_name.startswith("fg_"):
        return f'<span style="color:{tag_name[3:]};">'
    if tag_name.startswith("bg_"):
        return f'<span style="background-color:{tag_name[3:]};">'
    if tag_name == "align_center":
        return '<div style="text-align:center;">'
    if tag_name == "align_right":
        return '<motion><motion><div style="text-align:right;">'
    if tag_name == "align_left":
        return '<motion><motion><motion><div style="text-align:left;">'
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


def text_widget_to_html(widget: tk.Text) -> str:
    dump = widget.dump("1.0", "end-1c", text=True, tag=True)
    if not dump:
        return ""

    parts: list[str] = []
    index = 0
    while index < len(dump):
        kind = dump[index]
        if kind == "text":
            chunk = dump[index + 1]
            parts.append(html.escape(chunk).replace("\n", "<br>"))
            index += 2
            continue
        if kind == "tagon":
            parts.append(_open_tag(dump[index + 1], widget))
            index += 2
            continue
        if kind == "tagoff":
            parts.append(_close_tag(dump[index + 1]))
            index += 2
            continue
        index += 2

    body = "".join(parts).replace("<motion>", "")
    return wrap_email_html(body)


class HtmlEditor(ctk.CTkFrame):
    """Three-tab HTML editor: visual toolbar, raw HTML, and live preview."""

    def __init__(self, master, colors: dict[str, str], height: int = 340, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.colors = colors
        self._height = height
        self._active_tab = "Visual Editor"

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
        row2.pack(fill="x", padx=8, pady=(0, 8))

        for label, tag, tip in [
            ("B", "bold", "Bold"),
            ("I", "italic", "Italic"),
            ("U", "underline", "Underline"),
            ("S", "strikethrough", "Strikethrough"),
        ]:
            self._tool_btn(row1, label, lambda t=tag: self._toggle_tag(t), tip)

        self._tool_sep(row1)
        for label, tag, tip in [("H1", "h1", "Heading 1"), ("H2", "h2", "Heading 2"), ("H3", "h3", "Heading 3")]:
            self._tool_btn(row1, label, lambda t=tag: self._apply_heading(t), tip)

        self._tool_sep(row1)
        self._tool_btn(row1, "Clear", self._clear_format, "Clear formatting")

        self._tool_btn(row2, "• List", self._bullet_list, "Bullet list")
        self._tool_btn(row2, "1. List", self._number_list, "Numbered list")
        self._tool_btn(row2, "Link", self._insert_link, "Insert hyperlink")
        self._tool_btn(row2, "Color", self._pick_text_color, "Text color")
        self._tool_btn(row2, "Highlight", self._pick_highlight, "Highlight color")
        self._tool_sep(row2)
        self._tool_btn(row2, "Left", lambda: self._align("left"), "Align left")
        self._tool_btn(row2, "Center", lambda: self._align("center"), "Align center")
        self._tool_btn(row2, "Right", lambda: self._align("right"), "Align right")

        editor_shell = tk.Frame(
            parent,
            bg=self.colors["surface_alt"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        editor_shell.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))

        self.visual_editor = tk.Text(
            editor_shell,
            wrap=tk.WORD,
            undo=True,
            maxundo=-1,
            padx=14,
            pady=12,
            relief=tk.FLAT,
            borderwidth=0,
            height=12,
            bg=self.colors["surface_alt"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground=self.colors["text"],
            font=("Segoe UI", 13),
        )
        self.visual_editor.pack(fill="both", expand=True)
        self.visual_editor.insert("1.0", PLACEHOLDER_VISUAL)
        self.visual_editor.bind("<FocusIn>", self._clear_visual_placeholder)
        self._visual_has_placeholder = True

        self.visual_editor.tag_configure("bold", font=("Segoe UI", 13, "bold"))
        self.visual_editor.tag_configure("italic", font=("Segoe UI", 13, "italic"))
        self.visual_editor.tag_configure("underline", underline=True)
        self.visual_editor.tag_configure("strikethrough", overstrike=True)
        self.visual_editor.tag_configure("h1", font=("Segoe UI", 22, "bold"), spacing3=8)
        self.visual_editor.tag_configure("h2", font=("Segoe UI", 18, "bold"), spacing3=6)
        self.visual_editor.tag_configure("h3", font=("Segoe UI", 15, "bold"), spacing3=4)

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
        parent.grid_rowconfigure(0, weight=1)

        shell = tk.Frame(
            parent,
            bg=self.colors["surface_alt"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        shell.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        if HTMLLabel is not None:
            self.preview_label = HTMLLabel(
                shell,
                html=self._preview_document("<p>Preview will appear here.</p>"),
            )
            self.preview_label.pack(fill="both", expand=True, padx=8, pady=8)
        else:
            self.preview_label = tk.Label(
                shell,
                text="Install tkhtmlview for live HTML preview.",
                bg=self.colors["surface_alt"],
                fg=self.colors["muted"],
                font=("Segoe UI", 12),
                justify=tk.LEFT,
                anchor="nw",
            )
            self.preview_label.pack(fill="both", expand=True, padx=12, pady=12)

    def _preview_document(self, body: str) -> str:
        return (
            "<html><head><meta charset='utf-8'>"
            "<style>body{font-family:Segoe UI,Arial,sans-serif;padding:12px;"
            "background:#F8FAFC;color:#111827;} a{color:#6366F1;} "
            "h1,h2,h3{margin:0.4em 0;}</style></head>"
            f"<body>{body}</body></html>"
        )

    def _tool_btn(self, parent, text: str, command, _tooltip: str) -> None:
        btn = ctk.CTkButton(
            parent,
            text=text,
            width=52,
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

    def _tool_sep(self, parent) -> None:
        sep = ctk.CTkFrame(parent, width=2, height=24, fg_color=self.colors["border"])
        sep.pack(side="left", padx=6)

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
        if not text:
            return True
        if text == PLACEHOLDER_SOURCE:
            return True
        plain = html_to_plain(text)
        return not plain or plain == PLACEHOLDER_SOURCE_PLAIN

    def _on_tab_change(self) -> None:
        tab = self.tabs.get()
        if tab == "HTML Source" and self._active_tab == "Visual Editor":
            html_body = text_widget_to_html(self.visual_editor)
            self.source_box.delete("1.0", "end")
            self.source_box.insert("1.0", html_body)
        elif tab == "Preview":
            self._refresh_preview()
        self._active_tab = tab

    def _refresh_preview(self) -> None:
        content = self.get_html()
        if HTMLLabel is not None and isinstance(self.preview_label, HTMLLabel):
            self.preview_label.set_html(self._preview_document(content))

    def _selection_range(self):
        if self.visual_editor.tag_ranges(tk.SEL):
            return self.visual_editor.index("sel.first"), self.visual_editor.index("sel.last")
        cursor = self.visual_editor.index("insert")
        return cursor, cursor

    def _toggle_tag(self, tag: str) -> None:
        start, end = self._selection_range()
        if start == end:
            return
        if tag in self.visual_editor.tag_names(start):
            self.visual_editor.tag_remove(tag, start, end)
        else:
            self.visual_editor.tag_add(tag, start, end)

    def _apply_heading(self, tag: str) -> None:
        start, _end = self._selection_range()
        line_start = start.split(".")[0] + ".0"
        line_end = start.split(".")[0] + ".end"
        for heading in ("h1", "h2", "h3"):
            self.visual_editor.tag_remove(heading, line_start, line_end)
        self.visual_editor.tag_add(tag, line_start, line_end)

    def _clear_format(self) -> None:
        start, end = self._selection_range()
        if start == end:
            line = start.split(".")[0]
            start = f"{line}.0"
            end = f"{line}.end"
        for tag in self.visual_editor.tag_names():
            if tag != tk.SEL:
                self.visual_editor.tag_remove(tag, start, end)

    def _line_prefix(self, prefix: str) -> None:
        line = self.visual_editor.index("insert").split(".")[0]
        line_start = f"{line}.0"
        self.visual_editor.insert(line_start, prefix)

    def _bullet_list(self) -> None:
        self._line_prefix("• ")

    def _number_list(self) -> None:
        line = int(self.visual_editor.index("insert").split(".")[0])
        self._line_prefix(f"{line}. ")

    def _insert_link(self) -> None:
        url = simpledialog.askstring("Insert Link", "Enter URL:", parent=self.winfo_toplevel())
        if not url:
            return
        start, end = self._selection_range()
        if start == end:
            self.visual_editor.insert(start, url)
            end = self.visual_editor.index(f"{start}+{len(url)}c")
        tag = _link_tag_name(url)
        self.visual_editor.tag_configure(tag, foreground=self.colors["accent_hover"], underline=True)
        self.visual_editor.tag_add(tag, start, end)

    def _pick_text_color(self) -> None:
        color = colorchooser.askcolor(title="Text color", parent=self.winfo_toplevel())
        if not color or not color[1]:
            return
        tag = f"fg_{color[1]}"
        self.visual_editor.tag_configure(tag, foreground=color[1])
        start, end = self._selection_range()
        if start != end:
            self.visual_editor.tag_add(tag, start, end)

    def _pick_highlight(self) -> None:
        color = colorchooser.askcolor(title="Highlight color", parent=self.winfo_toplevel())
        if not color or not color[1]:
            return
        tag = f"bg_{color[1]}"
        self.visual_editor.tag_configure(tag, background=color[1])
        start, end = self._selection_range()
        if start != end:
            self.visual_editor.tag_add(tag, start, end)

    def _align(self, direction: str) -> None:
        start, _end = self._selection_range()
        line = start.split(".")[0]
        line_start = f"{line}.0"
        line_end = f"{line}.end"
        for tag in ("align_left", "align_center", "align_right"):
            self.visual_editor.tag_remove(tag, line_start, line_end)
        self.visual_editor.tag_add(f"align_{direction}", line_start, line_end)

    def get_html(self) -> str:
        self._clear_visual_placeholder()
        self._clear_source_placeholder()

        visual_empty = self._is_visual_empty()
        source_empty = self._is_source_empty()
        tab = self.tabs.get()

        if tab == "HTML Source" and not source_empty:
            return self._source_raw()
        if not visual_empty:
            html = text_widget_to_html(self.visual_editor)
            if html:
                return html
        if not source_empty:
            return self._source_raw()
        return ""

    def get_plain_text(self) -> str:
        html_body = self.get_html()
        if not html_body:
            if not self._is_visual_empty():
                return self._visual_plain()
            return ""
        return html_to_plain(html_body)

    def is_empty(self) -> bool:
        self._clear_visual_placeholder()
        self._clear_source_placeholder()
        return self._is_visual_empty() and self._is_source_empty()

    def set_html(self, html_content: str) -> None:
        html_content = (html_content or "").strip()
        self.source_box.delete("1.0", "end")
        self.source_box.insert("1.0", html_content or PLACEHOLDER_SOURCE)
        self._source_has_placeholder = not html_content

        self.visual_editor.delete("1.0", "end")
        plain = html_to_plain(html_content)
        if plain:
            self.visual_editor.insert("1.0", plain)
            self._visual_has_placeholder = False
        else:
            self.visual_editor.insert("1.0", PLACEHOLDER_VISUAL)
            self._visual_has_placeholder = True

        self._active_tab = "HTML Source"
        self.tabs.set("Visual Editor")

    def get_scroll_widgets(self) -> list:
        return [self.source_box, self.visual_editor]
