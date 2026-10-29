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
