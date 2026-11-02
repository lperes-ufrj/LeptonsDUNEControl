# App_controle_LEPTONS — VS Code setup

1. In Google Drive, right-click the App_controle_LEPTONS folder > Download. Unzip it
   (e.g. to C:\Leptons\App_controle_LEPTONS).
2. Copy everything from this kit (including the hidden .vscode folder) into that same folder,
   next to the .py and .db files.
3. Install Python 3.10+ (python.org; on Windows tick "Add python.exe to PATH") and VS Code
   with the Python extension.
4. Run setup_windows.bat (Windows) or ./setup_linux_mac.sh (Linux/macOS/WSL).
   Alternatively in VS Code: Terminal > Run Task > "Setup: create .venv ...".
5. File > Open Folder > App_controle_LEPTONS. If asked, select the interpreter in .venv
   (Ctrl+Shift+P > "Python: Select Interpreter").
6. Run and Debug (Ctrl+Shift+D) > choose "Deposition tasks" or "Batch arrival control" > F5.

Notes
- The old "venv" folder from Drive won't work on another computer; it's ignored. A fresh .venv
  is created instead. You can delete the *Zone.Identifier files too (Windows download markers).
- The programs read lotes.db, rastreabilidade.db and usuarios.db from the folder they run in,
  so always launch from the project folder (the launch configs already do this).
- The deposition program starts a small report server on port 8765 for the QR codes; allow it
  through the firewall if phones on the network need to open the links.

Browser app (branch browser-app)
- Run and Debug > "Browser app" > F5, or in a terminal from the project folder:
      .venv/bin/python leptons_web.py          (Linux/macOS)
      .venv\Scripts\python leptons_web.py      (Windows)
  It opens http://127.0.0.1:8780 in the default browser. Only this computer can open it.
- The browser first asks for username and password: the same users as the desktop programs
  (usuarios.db). Logins, failures and logouts go to the same audit log. Quitting the program logs everyone out.
- It does everything the desktop deposition program does, on the same rastreabilidade.db. Each record is a
  deposition sample from a batch (the desktop program calls it a "task"): new sample / edit (deposition, visual
  inspection, cryogenic immersion, optical efficiency, attachments), review (QA sign-off), report pages, PDF,
  QR code, export/import sample (JSON, same format as the desktop "task" files), Sync Leptons Control Sheet,
  Export all PDFs, Backup now, and for Admins the Users and Audit log pages (actions keep their TASK_* codes).
  Attached files are copied to the "anexos" folder.
- Like the desktop program it starts the QR report server on port 8765 (phones on the same network) and makes
  the weekly backup when it opens. If the desktop program is open at the same time, its server answers the
  QR links instead (same links).
- The Batches tab (next to Samples) does everything the batch arrival program does, on the same lotes.db: OPTO batches
  with their small boxes (internal lots DUNE-CX-000X), arrival inspection, supplier control file, batch PDF report,
  Export CSV, and the Leptons cleaning lots (DUNE-LP-000X) with their PDF list. Each batch page lists the samples
  deposited from each box. Same audit codes (BATCH_CREATE/UPDATE/DELETE, CLEANING_LOT_SAVE/DELETE). Uploaded
  supplier files are copied to the "arquivos_lotes" folder.
- Two user roles: Admin and Operator. Only an Admin manages users, reviews samples (QA sign-off) and sees
  the audit log.
- Only an Admin can delete (samples, batches, cleaning lots), and must type their own password to confirm.
  Other roles do not see the Delete buttons. Refused attempts go to the audit log as DELETE_DENIED; 5 wrong
  passwords lock the account for 5 minutes, like the login.
- A completed sample (Final QA signed off) can only be changed by an Admin – edit, .json import over it or sheet
  sync (for an Operator the sync skips it). Saving any change removes the sign-off: the sample goes back to
  "To be reviewed" and needs a new Final QA sign-off. Refused attempts are logged as EDIT_DENIED.
- Closing the browser tab does not stop it: use the Quit button (or Ctrl+C in the terminal).
- Testing: set LEPTONS_DADOS=/path/to/a/copy to run it on a copy of the .db files instead of the real ones.
