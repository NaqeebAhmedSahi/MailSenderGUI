# Excel Bulk Mail Sender

Send emails one by one to addresses stored in an Excel (`.xlsx`) file. Available as a **premium GUI app** or a **CLI script**.

Multiple emails in a single cell (comma-separated) are treated as separate recipients.

## Requirements

- Python 3.9+ (64-bit recommended on Windows)
- **Linux GUI:** install Tkinter first: `sudo apt install python3-tk`
- **Windows:** Tkinter is included with the standard Python installer from [python.org](https://www.python.org/downloads/)
- Gmail or any SMTP provider that supports TLS
- For Gmail: use an [App Password](https://support.google.com/accounts/answer/185833), not your normal login password

## Excel format

- First row must be column headers
- Choose the column that contains email addresses
- Data starts from row 2
- One email per cell, or multiple comma-separated emails in one cell

Example:

| Name  | Email                         |
|-------|-------------------------------|
| Alice | alice@example.com             |
| Bob   | bob@example.com, bob2@mail.com |

---

## GUI App (recommended)

Professional desktop interface with sidebar navigation, HTML editor, session save/load, and send progress tracking.

```bash
cd mailautomation
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python mail_sender_gui.py
```

### GUI features

- Mailbox connection panel (email, app password, SMTP host/port)
- Excel file browser with column selector
- HTML email editor (Visual / HTML Source / Preview)
- Save button on every section + auto-load on startup
- Sent / pending / failed tracking (no duplicate sends after restart)
- Progress bar, live log, and stop button

### Run GUI executable

**Linux / macOS:**
```bash
./dist/mail-sender-gui
```

**Windows:**
```powershell
dist\mail-sender-gui.exe
```

---

## Build executables with PyInstaller

### Windows (recommended)

1. Install **Python 3.9+** from [python.org](https://www.python.org/downloads/)
2. During install, check **"Add python.exe to PATH"**
3. Copy the project folder to your PC (e.g. `C:\mailautomation`)
4. Open **Command Prompt** or **PowerShell** in that folder
5. Run:

```bat
build.bat
```

Or step by step:

```powershell
cd C:\path\to\mailautomation
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python build.py
```

**Output:**
```text
dist\mail-sender.exe       # CLI
dist\mail-sender-gui.exe   # GUI (no console window)
```

**Session data on Windows** (saved settings + send progress):
```text
C:\Users\<YourName>\.mailflow-pro\session.json
```

### Linux / macOS

```bash
chmod +x build.sh
./build.sh
```

Or:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build.py
```

**Output:**
```text
dist/mail-sender       # CLI
dist/mail-sender-gui   # GUI
```

### Build files

| File | Purpose |
|------|---------|
| `build.bat` | One-click Windows build |
| `build.sh` | Linux/macOS build |
| `build.py` | Cross-platform build script (used by both) |
| `mail-sender.spec` | PyInstaller config for CLI |
| `mail-sender-gui.spec` | PyInstaller config for GUI |

### PyInstaller options used

| Flag / setting | Purpose |
|----------------|---------|
| `--onefile` | Single `.exe` file on Windows |
| `console=False` | GUI runs without a black terminal window |
| `collect_all(customtkinter)` | Bundles theme assets |
| `collect_all(tkhtmlview)` | Bundles HTML preview support |
| Hidden imports | `mail_core`, `html_editor`, `session_store`, `openpyxl` |

Rebuild from scratch:
```powershell
python build.py
```

---

## CLI Script

```bash
python send_mails.py
```

---

## SMTP settings

| Provider | SMTP host | Port |
|----------|-----------|------|
| Gmail | `smtp.gmail.com` | `587` |
| Outlook | `smtp-mail.outlook.com` | `587` |
| Yahoo | `smtp.mail.yahoo.com` | `587` |

## Project files

| File | Description |
|------|-------------|
| `mail_sender_gui.py` | Premium GUI application |
| `send_mails.py` | CLI version |
| `mail_core.py` | Shared mail and Excel logic |
| `html_editor.py` | HTML email editor widget |
| `session_store.py` | Save/load session and campaign progress |
| `sample_recipients.xlsx` | Example Excel file |

## Troubleshooting

**Authentication failed**

- Confirm you are using an app password, not your regular password
- For Gmail, enable 2-Step Verification first

**Windows: `python` is not recognized**

- Reinstall Python and enable **Add to PATH**, or use `py -3 build.bat`

**Windows: SmartScreen / antivirus blocks the `.exe`**

- Normal for unsigned PyInstaller apps. Click **More info → Run anyway**, or add an exception in your antivirus.

**Windows: GUI opens then closes immediately**

- Rebuild with `python build.py`
- Run from Command Prompt to see errors: `dist\mail-sender-gui.exe`
- For debugging, temporarily set `console=True` in `mail-sender-gui.spec` and rebuild

**GUI does not open after PyInstaller build (Linux)**

- Install Tkinter: `sudo apt install python3-tk`
- Rebuild with `python build.py`

**Excel file error**

- Use `.xlsx` format (not `.xls`)
- Close the file in Excel before running the app

**Session not restoring**

- Click **Save** on each section, or send emails (auto-saves progress)
- Check `%USERPROFILE%\.mailflow-pro\session.json` on Windows
