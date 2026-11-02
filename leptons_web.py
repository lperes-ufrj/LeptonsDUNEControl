"""Abre o Deposition Control System no navegador (só neste PC).

    python leptons_web.py            (ou F5 em "Browser app" no VS Code)

O programa fica rodando enquanto esta janela/terminal estiver aberta; o botão Quit no navegador o fecha.
"""
import socket
import sys
import threading
import webbrowser

from webapp.app import criar_app, tarefas_ao_abrir

PORTA = 8780


def porta_livre(inicio):
    """A primeira porta livre a partir de 'inicio' (outro programa pode já estar usando a 8780)."""
    for porta in range(inicio, inicio + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    raise SystemExit("No free port found.")


if __name__ == "__main__":
    porta = porta_livre(PORTA)
    url = f"http://127.0.0.1:{porta}/"
    print(f"Deposition Control System running at {url}  (Ctrl+C or the Quit button to stop)")
    app = criar_app()
    # servidor dos links do QR code (rede local) e backup semanal, como no programa de mesa
    for aviso in tarefas_ao_abrir():
        print("Backup warning:", aviso)
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # 127.0.0.1: o aplicativo só abre neste computador (os links do QR usam o servidor próprio, só de leitura)
    app.run(host="127.0.0.1", port=porta, debug=False, use_reloader=False, threaded=True)
