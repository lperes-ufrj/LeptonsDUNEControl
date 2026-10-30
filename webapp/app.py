"""Aplicativo no navegador (Flask) para consultar as deposições. Roda só neste PC (127.0.0.1)."""
import os
import threading
from datetime import datetime

from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for

from . import dados

LOGOS = ("esquerda.png", "direita.png")


def criar_app():
    app = Flask(__name__)

    @app.template_filter("num")
    def formatar_numero(valor, casas=None):
        """Número como gravado (casas=None) ou com 'casas' decimais; '–' se vazio."""
        x = dados.numero(valor)
        if x is None:
            return valor if str(valor or "").strip() else "–"
        return format(x, f".{casas}f") if casas is not None else str(valor).strip()

    @app.template_filter("ou_traco")
    def ou_traco(valor):
        return valor if str(valor or "").strip() else "–"

    @app.context_processor
    def globais():
        return {"STATUS_TODOS": dados.STATUS_TODOS, "TXT_ESTADO": dados.TXT_ESTADO, "N_FILTROS": dados.N_FILTROS,
                "agora": datetime.now().strftime("%Y-%m-%d %H:%M")}

    def lateral(tarefas, st="", lote=None, interno="", q=""):
        """Barra lateral (situações e árvore lote OPTO -> lote interno, com o nº de tarefas) e a seleção atual."""
        lotes = {}
        for t in tarefas:
            for l in t["lotes"] or [{"opto": "", "interno": ""}]:
                grupo = lotes.setdefault(l["opto"] or "", {"total": 0, "internos": {}})
                grupo["total"] += 1
                if l["interno"]:
                    grupo["internos"][l["interno"]] = grupo["internos"].get(l["interno"], 0) + 1
        return {"arvore": sorted(lotes.items(), key=lambda kv: (kv[0] == "", kv[0])), "total": len(tarefas),
                "contagem": {s: sum(1 for t in tarefas if t["status"] == s) for s in dados.STATUS_TODOS},
                "st": st, "lote": lote, "interno": interno, "q": q}

    @app.route("/")
    def lista():
        todas = dados.listar_tarefas()
        q = request.args.get("q", "").strip()
        st = request.args.get("status", "")
        lote = request.args.get("lote")
        interno = request.args.get("interno", "")
        run = request.args.get("run", "")
        termos = q.upper().replace("_", "-").split()

        def bate(t):
            if st and t["status"] != st:
                return False
            if lote is not None and not any((l["opto"] or "") == lote for l in t["lotes"] or [{"opto": ""}]):
                return False
            if interno and not any(l["interno"] == interno for l in t["lotes"]):
                return False
            if run and t["numero"] != run:
                return False
            texto = " ".join(str(v) for v in (t["numero"], t["run"], t["pid"], t["box_pid"], t["pids_ctrl"],
                                               t["responsavel"], t["data"], t["status"],
                                               *[l["opto"] + " " + l["interno"] for l in t["lotes"]]))
            texto = texto.upper().replace("_", "-")
            return all(termo in texto for termo in termos)

        return render_template("lista.html", tarefas=[t for t in todas if bate(t)],
                               run=run, **lateral(todas, st, lote, interno, q))

    @app.route("/task/<int:tarefa_id>")
    def tarefa(tarefa_id):
        d = dados.ler_tarefa(tarefa_id)
        if d is None:
            abort(404)
        todas = dados.listar_tarefas()
        ordem = [t["id"] for t in todas]          # maior run primeiro: "anterior" = run menor
        i = ordem.index(tarefa_id)
        l0 = d["lotes"][0] if d["lotes"] else {"opto": "", "interno": ""}
        return render_template("tarefa.html", d=d, t=d["tarefa"], c=d["cab"], te=d["ef_teste"], dados=dados,
                               anterior=todas[i + 1] if i + 1 < len(todas) else None,
                               proxima=todas[i - 1] if i > 0 else None,
                               **lateral(todas, lote=l0["opto"], interno=l0["interno"]))

    @app.route("/run/<numero>")
    def run(numero):
        """/run/32 abre a tarefa da run 32 (ou a lista, se houver mais de uma)."""
        achadas = [t for t in dados.listar_tarefas() if t["numero"] == str(int(numero))] if numero.isdigit() else []
        if len(achadas) == 1:
            return redirect(url_for("tarefa", tarefa_id=achadas[0]["id"]))
        return redirect(url_for("lista", run=str(int(numero))) if numero.isdigit() else url_for("lista", q=numero))

    @app.route("/logo/<nome>")
    def logo(nome):
        if nome not in LOGOS:
            abort(404)
        return send_from_directory(dados.BASE, nome)

    @app.route("/quit", methods=["POST"])
    def sair():
        """Botão Quit: fecha o programa (fechar a aba do navegador não fecha o servidor)."""
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return render_template("sair.html")

    @app.errorhandler(404)
    def nao_achado(_e):
        return render_template("erro.html", mensagem="Task not found.", **lateral(dados.listar_tarefas())), 404

    return app
