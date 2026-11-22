"""Rich HTML email editor widget with visual, source, and preview tabs."""

from __future__ import annotations

import html
import re
import tkinter as tk
from tkinter import colorchooser, simpledialog
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
    return f"<div>{stripped}</div>"


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
    dump = widget.dump("1.0", "end-1c", text=True, tag=True, window=True)
    if not dump:
        return ""

    parts: list[str] = []
    for kind, value, _position in dump:
        if kind == "text":
            parts.append(html.escape(value).replace("\n", "<br>"))
        elif kind == "tagon":
            parts.append(_open_tag(value, widget))
        elif kind == "tagoff":
            parts.append(_close_tag(value))
        elif kind == "window":
            parts.append(SIGNATURE_MARKER)

    body = "".join(parts).replace("<motion>", "")
    return wrap_email_html(body)


class HtmlEditor(ctk.CTkFrame):
    """Three-tab HTML editor: visual toolbar, raw HTML, and live preview."""

    def __init__(self, master, colors: dict[str, str], height: int = 340, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.colors = colors
        self._height = height
        self._active_tab = "Visual Editor"
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
        if self.preview_builder is not None:
            content = self.preview_builder(content)
        else:
            content = content.replace(SIGNATURE_MARKER, "")
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

    def _plain_as_html(self, plain: str) -> str:
        plain = (plain or "").strip()
        if not plain:
            return ""
        return wrap_email_html(
            html.escape(plain).replace("\n", "<br>")
        )

    def get_html(self) -> str:
        self._clear_visual_placeholder()
        self._clear_source_placeholder()

        visual_empty = self._is_visual_empty()
        source_empty = self._is_source_empty()
        tab = self.tabs.get()

        if tab == "HTML Source" and not source_empty:
            return wrap_email_html(self._source_raw())
        if not visual_empty:
            html_body = text_widget_to_html(self.visual_editor)
            if html_body and html_body.strip():
                return html_body
            # Fallback if tag dump fails but text is present.
            return self._plain_as_html(self._visual_plain())
        if not source_empty:
            return wrap_email_html(self._source_raw())
        return ""

    def get_plain_text(self) -> str:
        if self.has_signature_block() and self.tabs.get() != "HTML Source":
            return html_to_plain(text_widget_to_html(self.visual_editor))
        if not self._is_visual_empty():
            visual = self._visual_plain()
            if visual and visual != PLACEHOLDER_VISUAL:
                return visual
        html_body = self.get_html()
        if not html_body:
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

        self._signature_block = None
        self.visual_editor.delete("1.0", "end")
        plain = html_to_plain(html_content)
        marker_at = None
        if SIGNATURE_MARKER in plain:
            before, _sep, after = plain.partition(SIGNATURE_MARKER)
            plain = before + after.replace(SIGNATURE_MARKER, "")
            marker_at = len(before)
        if plain or marker_at is not None:
            self.visual_editor.insert("1.0", plain)
            self._visual_has_placeholder = False
            if marker_at is not None and self.signature_renderer is not None:
                self.insert_signature_block(f"1.0+{marker_at}c", own_line=False)
        else:
            self.visual_editor.insert("1.0", PLACEHOLDER_VISUAL)
            self._visual_has_placeholder = True

        self._active_tab = "HTML Source"
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
            line_has_text = bool(text.get(index, f"{index} lineend"))
            if line_has_text:
                text.insert(index, "\n")
        block = self._build_signature_block()
        text.window_create(index, window=block, align="top", padx=2, pady=4)
        self._signature_block = block
        self._active_tab = "Visual Editor"

    def remove_signature_block(self) -> None:
        if not self.has_signature_block():
            self._signature_block = None
            return
        text = self.visual_editor
        index = text.index(self._signature_block)
        text.delete(index)  # destroys the embedded frame
        self._signature_block = None
        # Drop the empty line the block occupied (if it isn't the last one).
        if not text.get(f"{index} linestart", f"{index} lineend") and text.compare(
            f"{index} lineend", "<", "end-1c"
        ):
            text.delete(f"{index} lineend")

    def refresh_signature_block(self) -> None:
        """Re-render the block in place after the signature text/image changed."""
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
            text="\u2725  Signature \u2014 drag to move",
            bg=colors["accent"],
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            padx=8,
            pady=2,
            cursor="fleur",
        )
        handle.pack(fill="x")
        content = tk.Frame(block, bg=colors["surface"], cursor="fleur")
        content.pack(fill="both", expand=True, padx=10, pady=8)
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
        # A mark follows the text while the old block is removed.
        text.mark_set("sig_target", target)
        text.mark_gravity("sig_target", "left")
        self.remove_signature_block()
        self.insert_signature_block(text.index("sig_target"))
        text.mark_unset("sig_target")
        return "break"

