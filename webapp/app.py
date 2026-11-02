"""Deposition Control System no navegador (Flask). Roda só neste PC (127.0.0.1).

Faz tudo o que os programas de mesa faziam: lista e cadastro de tarefas (deposição, inspeção visual, imersão
criogênica, eficiência óptica), revisão (QA sign-off), relatórios HTML/PDF e QR code, exportar/importar .json,
sincronizar a planilha DUNE_Control, backup, usuários e registro de auditoria; e, na aba Batches, o cadastro de
chegada de lotes OPTO (caixas menores / lotes internos) e os lotes de limpeza do Leptons.
"""
import csv
import io
import json
import os
import secrets
import threading
import zipfile
from datetime import datetime
from functools import lru_cache, wraps
from pathlib import Path

from flask import (Flask, Response, abort, flash, redirect, render_template, request, send_file, send_from_directory,
                   session, url_for)
from PIL import Image, ImageChops
from werkzeug.utils import secure_filename

import leptons_auth

from . import backup, banco, chegada, dados, inicio, lotes, pdf, planilha, relatorio, tarefas

LOGOS = ("esquerda.png", "direita.png")
PROGRAMA = "Deposition Control (browser)"
LIVRES = {"login", "static", "logo", "sair"}         # páginas que abrem sem login
PERFIS_REVISORES = ("Admin",)                        # quem pode marcar uma tarefa como revisada
PASTA_JSON = dados.PASTA / "tarefas_json"
PASTA_ANEXOS = dados.PASTA / "anexos"

# dados guardados entre duas páginas (importação de .json, sincronização da planilha), por código aleatório
_IMPORTACOES = {}
_SINCRONIZACOES = {}


def criar_app():
    app = Flask(__name__)
    # chave nova a cada execução: fechar o programa encerra todos os logins
    app.secret_key = secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                      MAX_CONTENT_LENGTH=200 * 1024 * 1024)
    # mesma lista de usuários dos programas de mesa, qualquer que seja a pasta de onde se rodou
    leptons_auth.DB_USUARIOS = str(dados.DB_USUARIOS)
    leptons_auth._programa = PROGRAMA
    leptons_auth.criar_tabelas()
    chegada.inicializar()
    banco.inicializar_banco()

    def usuario():
        return session.get("usuario")

    def registrar(acao, detalhe=""):
        leptons_auth.registrar_como(usuario(), acao, detalhe)

    def nome_usuario():
        u = usuario() or {}
        return u.get("nome") or u.get("username") or ""

    def eh_admin():
        return (usuario() or {}).get("perfil") == "Admin"

    def so_admin(funcao):
        @wraps(funcao)
        def envolvida(*args, **kwargs):
            if not eh_admin():
                abort(403)
            return funcao(*args, **kwargs)
        return envolvida

    def edicao_bloqueada(tarefa_id, o_que):
        """Tarefa revisada (Completed): só um Admin altera, e a alteração exige um novo Final QA sign-off.
        None = pode alterar; senão a mensagem (a tentativa vai para a auditoria)."""
        revisada = tarefas.revisao_gravada(tarefa_id)
        if not revisada or eh_admin():
            return None
        registrar("EDIT_DENIED", f"id={tarefa_id} {o_que}: signed off, not an Admin")
        return (f"This sample was signed off (Final QA) by {revisada[0]} on {revisada[1] or '-'}. "
                "Only an Admin can change a completed sample.")

    def confirmar_exclusao(o_que, voltar):
        """Só um Admin exclui, e confirma com a própria senha. None = pode excluir; senão a resposta a devolver."""
        if not eh_admin():
            registrar("DELETE_DENIED", f"{o_que}: not an Admin")
            return erro_pagina("Only an Admin can delete records.", 403)
        ok, msg, _u = leptons_auth.autenticar(usuario()["username"], request.form.get("senha", ""))
        if ok:
            return None
        registrar("DELETE_DENIED", f"{o_que}: wrong password")
        flash("Password not confirmed – nothing was deleted. "
              + (msg if "attempts" in msg else "The password is incorrect."), "erro")
        return redirect(voltar)

    @app.before_request
    def exigir_login():
        if request.endpoint in LIVRES or usuario():
            return None
        destino = request.full_path if request.method == "GET" else None
        return redirect(url_for("login", proxima=destino.rstrip("?")) if destino else url_for("login"))

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

    @app.template_filter("basename")
    def basename(caminho):
        return os.path.basename(str(caminho).replace("\\", "/"))

    @app.context_processor
    def globais():
        return {"STATUS_TODOS": dados.STATUS_TODOS, "TXT_ESTADO": dados.TXT_ESTADO, "N_FILTROS": dados.N_FILTROS,
                "agora": datetime.now().strftime("%Y-%m-%d %H:%M"), "usuario": usuario(), "eh_admin": eh_admin(),
                "min_senha": leptons_auth.MIN_SENHA, "chegada_resultados": chegada.RESULTADOS}

    def lateral(tarefas_, st="", lote=None, interno="", q=""):
        """Barra lateral (situações e árvore lote OPTO -> lote interno, com o nº de tarefas) e a seleção atual."""
        grupos = {}
        for t in tarefas_:
            for l in t["lotes"] or [{"opto": "", "interno": ""}]:
                grupo = grupos.setdefault(l["opto"] or "", {"total": 0, "internos": {}})
                grupo["total"] += 1
                if l["interno"]:
                    grupo["internos"][l["interno"]] = grupo["internos"].get(l["interno"], 0) + 1
        return {"arvore": sorted(grupos.items(), key=lambda kv: (kv[0] == "", kv[0])), "total": len(tarefas_),
                "contagem": {s: sum(1 for t in tarefas_ if t["status"] == s) for s in dados.STATUS_TODOS},
                "st": st, "lote": lote, "interno": interno, "q": q}

    def id_mostrado(tarefa_id):
        """ID mostrado ao usuário (número da run) de uma tarefa gravada; '-' se ela ainda não tem run."""
        d = dados.ler_tarefa(tarefa_id)
        return (d and d["numero"]) or "-"

    def texto_status(status, pend):
        """Mensagem mostrada depois de gravar a tarefa."""
        if status == dados.STATUS_INCOMPLETO:
            return f"Status: {status} – {len(pend)} item(s) of information still missing (listed on the sample page)."
        if status == dados.STATUS_REVISAR:
            return f"Status: {status} – all the information is filled. An Admin can now review it."
        return f"Status: {status}"

    # =====================================================================
    # LISTA E PÁGINA DA TAREFA
    # =====================================================================
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

    @app.route("/sample/<int:tarefa_id>")
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
                               anexos=[a for a in (d["tarefa"].get("anexos_txt") or "").split(";") if a.strip()],
                               pode_revisar=usuario()["perfil"] in PERFIS_REVISORES,
                               **lateral(todas, lote=l0["opto"], interno=l0["interno"]))

    @app.route("/run/<numero>")
    def run(numero):
        """/run/32 abre a tarefa da run 32 (ou a lista, se houver mais de uma)."""
        achadas = [t for t in dados.listar_tarefas() if t["numero"] == str(int(numero))] if numero.isdigit() else []
        if len(achadas) == 1:
            return redirect(url_for("tarefa", tarefa_id=achadas[0]["id"]))
        return redirect(url_for("lista", run=str(int(numero))) if numero.isdigit() else url_for("lista", q=numero))

    # =====================================================================
    # CADASTRO: NOVA / EDITAR / GRAVAR / EXCLUIR
    # =====================================================================
    def formulario(f, erros=(), avisos=(), importacao="", confirmar_run=False):
        revisada = tarefas.revisao_gravada(f["id"])
        return render_template("editar.html", f=f, dados=dados, tarefas=tarefas, erros=erros, avisos=avisos,
                               importacao=importacao, confirmar_run=confirmar_run, revisada=revisada,
                               numero=id_mostrado(f["id"]) if f["id"] else "",
                               lotes_json=json.dumps(f["lotes"]))

    @app.route("/sample/new")
    def nova_tarefa():
        return formulario(tarefas.vazio(nome_usuario()))

    @app.route("/sample/<int:tarefa_id>/edit")
    def editar_tarefa(tarefa_id):
        f = tarefas.ler(tarefa_id)
        if f is None:
            abort(404)
        bloqueio = edicao_bloqueada(tarefa_id, "edit")
        if bloqueio:
            flash(bloqueio, "erro")
            return redirect(url_for("tarefa", tarefa_id=tarefa_id))
        return formulario(f)

    def salvar_envio(arq, pasta):
        """Grava um arquivo enviado pelo navegador em 'pasta' (nome com data e hora) e retorna o caminho."""
        pasta.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome = secure_filename(arq.filename) or "file"
        destino = pasta / f"{carimbo}_{nome}"
        n = 1
        while destino.exists():
            destino = pasta / f"{carimbo}_{n}_{nome}"
            n += 1
        arq.save(str(destino))
        return str(destino)

    def guardar_anexos(f):
        """Arquivos enviados no formulário: gravados em anexos/ (o banco guarda o caminho, como no programa de mesa)."""
        for arq in request.files.getlist("novos_anexos"):
            if arq and arq.filename:
                f["anexos"].append(salvar_envio(arq, PASTA_ANEXOS))

    @app.route("/sample/save", methods=["POST"])
    def gravar_tarefa():
        tarefa_id = request.form.get("tarefa_id", type=int)
        if tarefa_id is not None and dados.ler_tarefa(tarefa_id) is None:
            abort(404)
        bloqueio = edicao_bloqueada(tarefa_id, "save")
        if bloqueio:
            return erro_pagina(bloqueio, 403)
        f = tarefas.de_formulario(request.form)
        f["id"] = tarefa_id
        token = request.form.get("importacao", "")
        imp = _IMPORTACOES.get(token) if token else None
        guardar_anexos(f)

        erros = tarefas.validar(f)
        if erros:
            return formulario(f, erros=erros, importacao=token), 400
        outras = tarefas.outras_com_run(f)
        if outras and "1" not in request.form.getlist("confirmar_run"):
            return formulario(f, importacao=token, confirmar_run=True, avisos=[
                f"ID {dados.numero_run(f['run'])} (run {f['run']}) is already used by another sample ({len(outras)}). "
                "The ID comes from the run number, so two samples would show the same ID. "
                "Click Save anyway to keep it."]), 409

        revisada = tarefas.revisao_gravada(tarefa_id)
        if revisada:
            # tarefa já revisada (só um Admin chega aqui): qualquer alteração exige um novo Final QA sign-off
            if "1" not in request.form.getlist("confirmar_revisao"):
                return formulario(f, importacao=token, avisos=[
                    "This sample was signed off. Saving removes the Final QA sign-off; confirm when saving."]), 409
            f["signoff"] = {"por": "", "data": ""}
            registrar("TASK_REVIEW_CLEARED", f"id={tarefa_id} PID={f['pid']} "
                                             f"(was reviewed by {revisada[0]} on {revisada[1]})")
        elif imp is not None:
            f["signoff"] = imp["signoff"]          # tarefa importada: mantém a revisão do arquivo
        elif tarefa_id is not None:
            antiga = tarefas.ler(tarefa_id)
            f["signoff"] = antiga["signoff"]

        nova = tarefa_id is None
        tarefa_id = tarefas.gravar(f, tarefa_id)
        status, pend = tarefas.atualizar_status(tarefa_id)
        registrar("TASK_CREATE" if nova else "TASK_UPDATE", f"id={tarefa_id} PID={f['pid']} status={status}")
        if imp is not None:
            _IMPORTACOES.pop(token, None)
        flash(("Sample saved. " if nova else "Sample updated. ") + texto_status(status, pend),
              "ok" if status != dados.STATUS_INCOMPLETO else "aviso")
        return redirect(url_for("tarefa", tarefa_id=tarefa_id))

    @app.route("/sample/<int:tarefa_id>/delete", methods=["POST"])
    def excluir_tarefa(tarefa_id):
        if dados.ler_tarefa(tarefa_id) is None:
            abort(404)
        negado = confirmar_exclusao(f"sample id={tarefa_id}", url_for("tarefa", tarefa_id=tarefa_id))
        if negado:
            return negado
        numero = id_mostrado(tarefa_id)
        pid = tarefas.excluir(tarefa_id)
        if pid is None:
            abort(404)
        registrar("TASK_DELETE", f"id={tarefa_id} PID={pid}")
        flash(f"Sample ID {numero} ({pid or '-'}) deleted.", "ok")
        return redirect(url_for("lista"))

    @app.route("/sample/<int:tarefa_id>/attachment")
    def anexo(tarefa_id):
        """Arquivo anexado à tarefa (só os caminhos gravados nela)."""
        d = dados.ler_tarefa(tarefa_id)
        caminho = request.args.get("file", "")
        if d is None or caminho not in (d["tarefa"].get("anexos_txt") or "").split(";") or not os.path.isfile(caminho):
            abort(404)
        return send_file(caminho)

    @app.route("/api/batches")
    def api_lotes():
        """Lotes OPTO / internos / de limpeza para a janela 'Add batch / internal lot'."""
        return lotes.catalogo(request.args.get("sample", type=int))

    # =====================================================================
    # LOTES: chegada de lotes OPTO (caixas menores = lotes internos) e lotes de limpeza do Leptons
    # (os nomes das páginas começam com "lote": é assim que a barra superior marca a aba Batches)
    # =====================================================================
    def lateral_lotes(atual=None, res=""):
        """Barra lateral da aba Batches: resultado da inspeção, lotes OPTO e lotes de limpeza."""
        todos = chegada.listar()
        return {"lat_lotes": todos, "lote_atual": atual, "res": res, "n_limpezas": len(lotes.limpezas()),
                "contagem_res": {r: sum(1 for l in todos if l["resultado_inspecao"] == r) for r in chegada.RESULTADOS}}

    def amostras_que_usaram(usos):
        """[(id da amostra, id do lote interno)] -> {id do lote interno: [amostras]} e o nº de amostras diferentes."""
        amostras = {t["id"]: t for t in dados.listar_tarefas()}
        por_interno, vistas = {}, set()
        for tid, iid in usos:
            if tid in amostras and amostras[tid] not in por_interno.setdefault(iid, []):
                por_interno[iid].append(amostras[tid])
                vistas.add(tid)
        return por_interno, len(vistas)

    @app.route("/batches")
    def lotes_lista():
        q = request.args.get("q", "").strip()
        res = request.args.get("result", "")
        achados = chegada.listar(q)
        if res:
            achados = [l for l in achados if l["resultado_inspecao"] == res]
        n_amostras = {}
        for tid, lote_id in chegada.usos_todos():
            n_amostras.setdefault(lote_id, set()).add(tid)
        return render_template("lotes.html", lista_lotes=achados, q=q,
                               n_amostras={k: len(v) for k, v in n_amostras.items()}, **lateral_lotes(res=res))

    @app.route("/batch/<int:lote_id>")
    def lote(lote_id):
        l = chegada.ler(lote_id)
        if l is None:
            abort(404)
        por_interno, n_amostras = amostras_que_usaram(chegada.usos(lote_id))
        arquivo = l.get("arquivo_controle") or ""
        return render_template("lote.html", l=l, por_interno=por_interno, n_amostras=n_amostras,
                               arquivo_existe=bool(arquivo) and caminho_arquivo(arquivo).is_file(),
                               **lateral_lotes(lote_id))

    def caminho_arquivo(caminho):
        """Caminho gravado no lote (o programa de mesa grava o caminho completo; relativo = pasta dos dados)."""
        p = Path(caminho).expanduser()
        return p if p.is_absolute() else dados.PASTA / p

    @app.route("/batch/<int:lote_id>/control-file")
    def lote_arquivo(lote_id):
        """Arquivo de controle do fornecedor gravado no lote."""
        l = chegada.ler(lote_id)
        caminho = (l or {}).get("arquivo_controle") or ""
        if not caminho or not caminho_arquivo(caminho).is_file():
            abort(404)
        return send_file(str(caminho_arquivo(caminho)))

    def formulario_lote(f, erros=(), avisos=(), faltando=0):
        tracking = (chegada.ler(f["id"]) or {}).get("tracking_id") if f["id"] else ""
        return render_template("lote_editar.html", f=f, chegada=chegada, erros=erros, avisos=avisos, faltando=faltando,
                               tracking=tracking, **lateral_lotes(f["id"]))

    @app.route("/batch/new")
    def lote_novo():
        return formulario_lote(chegada.vazio(nome_usuario()))

    @app.route("/batch/<int:lote_id>/edit")
    def lote_editar(lote_id):
        f = chegada.formulario(lote_id)
        if f is None:
            abort(404)
        return formulario_lote(f)

    @app.route("/batch/save", methods=["POST"])
    def lote_gravar():
        f = chegada.de_formulario(request.form)
        if f["id"] is not None and chegada.ler(f["id"]) is None:
            abort(404)
        arq = request.files.get("arquivo_novo")
        if arq and arq.filename:
            f["arquivo_controle"] = salvar_envio(arq, chegada.PASTA_ARQUIVOS)
        erros = chegada.validar(f)
        if erros:
            return formulario_lote(f, erros=erros), 400
        faltando = chegada.caixas_sem_codigo(f)
        escolha = request.form.get("faltando")
        if faltando and escolha == "preencher":
            chegada.preencher_codigos(f)
            conflito = chegada.conflito_codigos(f["internos"])
            if conflito:
                return formulario_lote(f, erros=[conflito]), 400
        elif faltando and escolha != "deixar":
            return formulario_lote(f, faltando=len(faltando)), 409

        novo = f["id"] is None
        lote_id, tracking = chegada.gravar(f, f["id"])
        registrar("BATCH_CREATE" if novo else "BATCH_UPDATE", f"id={lote_id} {tracking} OPTO batch={f['lote_geral']}")
        flash(f"Batch {f['lote_geral']} ({tracking}) " + ("saved." if novo else "updated."), "ok")
        return redirect(url_for("lote", lote_id=lote_id))

    @app.route("/batch/<int:lote_id>/delete", methods=["POST"])
    def lote_excluir(lote_id):
        if chegada.ler(lote_id) is None:
            abort(404)
        negado = confirmar_exclusao(f"batch id={lote_id}", url_for("lote", lote_id=lote_id))
        if negado:
            return negado
        info = chegada.excluir(lote_id)
        if info is None:
            abort(404)
        registrar("BATCH_DELETE", f"id={lote_id} {info[0]} OPTO batch={info[1]}")
        flash(f"Batch {info[1] or '-'} ({info[0] or 'ID ' + str(lote_id)}) deleted.", "ok")
        return redirect(url_for("lotes_lista"))

    @app.route("/batch/<int:lote_id>/report.pdf")
    def lote_pdf(lote_id):
        l = chegada.ler(lote_id)
        if l is None:
            abort(404)
        pdf.PASTA_PDF.mkdir(parents=True, exist_ok=True)
        nome = chegada.nome_pdf_lote(lote_id, l.get("lote_geral"))
        caminho = pdf.PASTA_PDF / nome
        try:
            chegada.gerar_pdf_lote(lote_id, str(caminho))
        except PermissionError:
            return erro_pagina(f"Could not write the file. Close the PDF if it is open and try again: {caminho}")
        return send_file(str(caminho), mimetype="application/pdf", download_name=nome)

    @app.route("/batches.csv")
    def lotes_csv():
        return Response(chegada.csv_texto(), mimetype="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="opto_batches.csv"'})

    def pagina_limpeza(f, erro=None):
        todas = lotes.limpezas()
        usado = {l["id"]: amostras_que_usaram(chegada.usos(limpeza_id=l["id"]))[0].get(l["id"], []) for l in todas}
        return render_template("limpeza.html", f=f, limpezas=todas, usado=usado, erro=erro, chegada=chegada,
                               **lateral_lotes())

    @app.route("/batches/cleaning")
    def lotes_limpeza():
        editar = request.args.get("edit", type=int)
        if editar is None:
            return pagina_limpeza(chegada.limpeza_vazia(nome_usuario()))
        limp = lotes.limpeza(editar, None)
        if limp is None:
            abort(404)
        return pagina_limpeza(chegada.limpeza_formulario(limp))

    @app.route("/batches/cleaning/save", methods=["POST"])
    def lotes_limpeza_gravar():
        f = chegada.limpeza_de_formulario(request.form)
        if f["id"] is not None and lotes.limpeza(f["id"], None) is None:
            abort(404)
        codigo, erro = chegada.validar_limpeza(f)
        if erro:
            return pagina_limpeza(f, erro), 400
        chegada.gravar_limpeza(f, codigo)
        registrar("CLEANING_LOT_SAVE", codigo)
        flash(f"Cleaning lot {codigo} saved.", "ok")
        return redirect(url_for("lotes_limpeza"))

    @app.route("/batches/cleaning/<int:limpeza_id>/delete", methods=["POST"])
    def lotes_limpeza_excluir(limpeza_id):
        if lotes.limpeza(limpeza_id, None) is None:
            abort(404)
        negado = confirmar_exclusao(f"cleaning lot id={limpeza_id}", url_for("lotes_limpeza", edit=limpeza_id))
        if negado:
            return negado
        codigo = chegada.excluir_limpeza(limpeza_id)
        if codigo is None:
            abort(404)
        registrar("CLEANING_LOT_DELETE", codigo)
        flash(f"Cleaning lot {codigo} deleted. Depositions that already used it keep the code in their records.", "ok")
        return redirect(url_for("lotes_limpeza"))

    @app.route("/batches/cleaning.pdf")
    def lotes_limpeza_pdf():
        pdf.PASTA_PDF.mkdir(parents=True, exist_ok=True)
        caminho = pdf.PASTA_PDF / "Leptons_cleaning_lots.pdf"
        try:
            chegada.gerar_pdf_limpeza(str(caminho))
        except PermissionError:
            return erro_pagina(f"Could not write the file. Close the PDF if it is open and try again: {caminho}")
        return send_file(str(caminho), mimetype="application/pdf", download_name=caminho.name)

    # =====================================================================
    # REVISÃO (FINAL QA SIGN-OFF)
    # =====================================================================
    @app.route("/sample/<int:tarefa_id>/review", methods=["GET", "POST"])
    def revisar(tarefa_id):
        d = dados.ler_tarefa(tarefa_id)
        if d is None:
            abort(404)
        pode = usuario()["perfil"] in PERFIS_REVISORES
        if request.method == "POST":
            if not pode:
                flash("Only " + " or ".join(PERFIS_REVISORES) + " users can review samples.", "erro")
            elif d["status"] != dados.STATUS_REVISAR:
                flash("This sample is not ready for review (or was already reviewed).", "erro")
            else:
                tarefas.marcar_revisada(tarefa_id, nome_usuario())
                registrar("TASK_REVIEWED", f"id={tarefa_id} PID={d['tarefa'].get('codigo_tarefa') or ''}")
                flash(f"Sample {d['tarefa'].get('codigo_tarefa') or ''} reviewed – status: {dados.STATUS_COMPLETO}.", "ok")
                return redirect(url_for("tarefa", tarefa_id=tarefa_id))
        return render_template("revisar.html", d=d, t=d["tarefa"], pode_revisar=pode, perfis=PERFIS_REVISORES,
                               nome=nome_usuario(), hoje=tarefas.hoje())

    # =====================================================================
    # RELATÓRIOS: HTML, PDF, QR CODE
    # =====================================================================
    @app.route("/sample/<int:tarefa_id>/report/")
    @app.route("/sample/<int:tarefa_id>/report/<nome>.html")
    def relatorio_html(tarefa_id, nome="index"):
        if nome not in relatorio.PAGINAS_RELATORIO or dados.ler_tarefa(tarefa_id) is None:
            abort(404)
        return relatorio.renderizar_pagina(tarefa_id, nome)

    @app.route("/sample/<int:tarefa_id>/report.pdf")
    def relatorio_pdf(tarefa_id):
        d = dados.ler_tarefa(tarefa_id)
        if d is None:
            abort(404)
        pdf.PASTA_PDF.mkdir(parents=True, exist_ok=True)
        nome = f"Report_{tarefas.nome_arquivo(d['tarefa'].get('codigo_tarefa'))}_sample{tarefa_id}.pdf"
        caminho = pdf.PASTA_PDF / nome
        try:
            pdf.gerar_pdf_relatorio(tarefa_id, str(caminho))
        except PermissionError:
            return erro_pagina(f"Could not write the file. Close the PDF if it is open and try again: {caminho}")
        return send_file(str(caminho), mimetype="application/pdf", download_name=nome)

    @app.route("/sample/<int:tarefa_id>/qr")
    def qr(tarefa_id):
        d = dados.ler_tarefa(tarefa_id)
        if d is None:
            abort(404)
        if relatorio.URL_BASE_RELATORIO:
            pasta = relatorio.gerar_arquivos_relatorio(tarefa_id)
            aviso = (f"Report files saved in: {pasta}. Publish this folder at {relatorio.URL_BASE_RELATORIO} "
                     "so the QR link works.")
        elif servidor_relatorios_ativo():
            aviso = ("The link works on devices connected to the same network as this computer, while this program "
                     "is open. If it does not open, allow Python through the firewall for private networks.")
        else:
            aviso = (f"The report server could not start on port {relatorio.SERVIDOR_PORTA} (port in use – is the "
                     "desktop program open? It serves the same links while it is open).")
        return render_template("qr.html", d=d, url=relatorio.url_relatorio(tarefa_id), aviso=aviso)

    @app.route("/sample/<int:tarefa_id>/qr.png")
    def qr_png(tarefa_id):
        d = dados.ler_tarefa(tarefa_id)
        if d is None:
            abort(404)
        buf = io.BytesIO()
        relatorio.gerar_imagem_qr(relatorio.url_relatorio(tarefa_id), d["tarefa"].get("codigo_tarefa") or "", buf)
        buf.seek(0)
        baixar = bool(request.args.get("download"))
        return send_file(buf, mimetype="image/png", as_attachment=baixar,
                         download_name=f"qr_{tarefas.nome_arquivo(d['tarefa'].get('codigo_tarefa'))}.png")

    @app.route("/pdfs/all", methods=["POST"])
    def todos_pdfs():
        """Gera, de uma vez, o PDF de todas as deposições cadastradas (para arquivo)."""
        con = banco.conectar()
        ids = con.execute("SELECT id, codigo_tarefa FROM tarefas ORDER BY id").fetchall()
        con.close()
        pasta = pdf.PASTA_PDF / ("todas_" + datetime.now().strftime("%Y-%m-%d_%H%M%S"))
        pasta.mkdir(parents=True, exist_ok=True)
        feitos, erros = 0, []
        for tid, pid in ids:
            nome = f"Report_{tarefas.nome_arquivo(pid)}_sample{tid}.pdf"
            try:
                pdf.gerar_pdf_relatorio(tid, str(pasta / nome))
                feitos += 1
            except Exception as e:
                erros.append(f"sample {tid} ({pid}): {e}")
        registrar("EXPORT_ALL_PDFS", f"{feitos} file(s) in {pasta.name}")
        return render_template("pdfs.html", feitos=feitos, erros=erros, pasta=pasta)

    @app.route("/pdfs/<pasta>.zip")
    def zip_pdfs(pasta):
        origem = pdf.PASTA_PDF / secure_filename(pasta)
        if not pasta.startswith("todas_") or not origem.is_dir():
            abort(404)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for arq in sorted(origem.glob("*.pdf")):
                z.write(arq, arq.name)
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=pasta + ".zip")

    # =====================================================================
    # EXPORTAR / IMPORTAR TAREFA (.json)
    # =====================================================================
    @app.route("/sample/<int:tarefa_id>/export.json")
    def exportar_json(tarefa_id):
        d = tarefas.exportar_json(tarefa_id, nome_usuario())
        if d is None:
            abort(404)
        nome = f"Sample_{tarefas.nome_arquivo(d['pid'])}_sample{tarefa_id}.json"
        texto = json.dumps(d, ensure_ascii=False, indent=2)
        PASTA_JSON.mkdir(parents=True, exist_ok=True)         # cópia local, como no programa de mesa
        (PASTA_JSON / nome).write_text(texto, encoding="utf-8")
        registrar("TASK_EXPORT_JSON", f"id={tarefa_id} PID={d['pid']} file={nome}")
        return Response(texto, mimetype="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.route("/import", methods=["GET", "POST"])
    def importar_json():
        """Carrega uma tarefa exportada (.json) no formulário para revisão; só grava com Save."""
        if request.method == "GET":
            return render_template("importar.html")
        arq = request.files.get("arquivo")
        if not arq or not arq.filename:
            return render_template("importar.html", erro="Choose a .json file."), 400
        try:
            d = tarefas.ler_json(arq.read().decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as e:
            return render_template("importar.html", erro="Could not read the file: " + str(e)), 400
        token = secrets.token_urlsafe(12)
        pid = str(d["task"].get("codigo_tarefa") or "").strip()
        _IMPORTACOES[token] = {"dados": d, "arquivo": secure_filename(arq.filename) or "sample.json", "pid": pid}
        existentes = tarefas.tarefas_com_pid(pid)
        if existentes:
            alvo = d.get("source_task_id") if d.get("source_task_id") in existentes else existentes[-1]
            return render_template("importar.html", escolher=True, token=token, pid=pid, alvo=alvo,
                                   numero_alvo=id_mostrado(alvo),
                                   existentes=", ".join(id_mostrado(t) for t in existentes))
        return redirect(url_for("formulario_importado", token=token))

    @app.route("/import/<token>")
    def formulario_importado(token):
        imp = _IMPORTACOES.get(token)
        if imp is None:
            flash("The imported file is no longer available – import it again.", "erro")
            return redirect(url_for("importar_json"))
        destino = request.args.get("into", type=int)
        if destino is not None and destino not in tarefas.tarefas_com_pid(imp["pid"]):
            abort(404)
        bloqueio = edicao_bloqueada(destino, "import .json")
        if bloqueio:
            flash(bloqueio + " Import it as a new sample instead.", "erro")
            return redirect(url_for("importar_json"))
        try:
            f = tarefas.formulario_do_json(imp["dados"])
        except Exception as e:
            flash("Could not load the sample from the file: " + str(e), "erro")
            return redirect(url_for("importar_json"))
        imp["signoff"] = f["signoff"]
        f["id"] = destino
        registrar("TASK_IMPORT_JSON", f"PID={imp['pid']} file={imp['arquivo']} "
                                      f"into={'new' if destino is None else 'id=' + str(destino)}")
        avisos = [f"Sample {imp['pid'] or '-'} loaded from {imp['arquivo']}. Review the data, then click "
                  + ("Save to create it." if destino is None else f"Save to overwrite sample ID {id_mostrado(destino)}.")]
        ausentes = tarefas.lotes_ausentes(imp["dados"])
        if ausentes:
            avisos.append("These batches are not registered on this computer (they are kept with their codes): "
                          + ", ".join(ausentes))
        return formulario(f, avisos=avisos, importacao=token)

    # =====================================================================
    # PLANILHA DUNE_Control (Sync Leptons Control Sheet)
    # =====================================================================
    @app.route("/sync", methods=["GET", "POST"])
    def sincronizar():
        ultimo = banco.ler_config("planilha_eficiencia")
        if request.method == "GET":
            return render_template("sync.html", ultimo=ultimo)
        arq = request.files.get("arquivo")
        caminho_txt = request.form.get("caminho", "").strip()
        temporario = None
        try:
            if arq and arq.filename:
                temporario = dados.PASTA / f".sync_{secrets.token_hex(6)}.xlsx"
                arq.save(str(temporario))
                caminho, nome = temporario, arq.filename
            elif caminho_txt:
                caminho, nome = Path(caminho_txt).expanduser(), os.path.basename(caminho_txt)
                if not caminho.is_file():
                    return render_template("sync.html", ultimo=ultimo, erro=f"File not found: {caminho_txt}"), 400
            else:
                return render_template("sync.html", ultimo=ultimo, erro="Choose the spreadsheet file."), 400
            try:
                abas, linhas_ef, deps = planilha.ler_planilha(str(caminho))
            except Exception as e:
                return render_template("sync.html", ultimo=ultimo, erro="Could not read the spreadsheet: " + str(e)), 400
        finally:
            if temporario is not None and temporario.exists():
                temporario.unlink()
        if caminho_txt and not (arq and arq.filename):
            banco.gravar_config("planilha_eficiencia", str(caminho))
        mudancas, n_tarefas = planilha.mudancas_planilha(linhas_ef, deps)
        if not mudancas:
            flash(f"Everything is up to date: no differences between {', '.join(abas)} and the {n_tarefas} saved samples.",
                  "ok")
            return redirect(url_for("lista"))
        token = secrets.token_urlsafe(12)
        _SINCRONIZACOES[token] = {"mudancas": mudancas, "arquivo": nome}
        grupos = {}
        for m in sorted(mudancas, key=lambda m: isinstance(m["alvo"], tuple)):    # existentes primeiro
            grupos.setdefault(m["alvo"], []).append(dict(m, nome_campo=planilha._nome_campo_sync(m)))
        numeros = {a: id_mostrado(a) for a in grupos if isinstance(a, int)}
        return render_template("sync_mudancas.html", token=token, arquivo=nome, abas=abas, n_tarefas=n_tarefas,
                               grupos=grupos, numeros=numeros,
                               novas=sum(1 for a in grupos if isinstance(a, tuple)),
                               existentes=sum(1 for a in grupos if not isinstance(a, tuple)),
                               n_exist=sum(1 for m in mudancas if not isinstance(m["alvo"], tuple)),
                               revisadas=sorted({m["pid"] for m in mudancas if m["revisada"]}))

    @app.route("/sync/apply", methods=["POST"])
    def aplicar_sincronizacao():
        sinc = _SINCRONIZACOES.pop(request.form.get("token", ""), None)
        if sinc is None:
            flash("These changes were already applied or expired – run the sync again.", "erro")
            return redirect(url_for("sincronizar"))
        mudancas, puladas = sinc["mudancas"], []
        if not eh_admin():            # amostras revisadas (Completed): só um Admin altera
            puladas = sorted({m["pid"] for m in mudancas if m["revisada"]})
            mudancas = [m for m in mudancas if not m["revisada"]]
            if puladas:
                registrar("EDIT_DENIED", f"sheet sync: {', '.join(puladas)} signed off, not an Admin")
        n, criadas = planilha.aplicar_mudancas_planilha(mudancas, sinc["arquivo"], registrar,
                                                        bool(request.form.get("criar_novas")))
        flash(f"Synced from {sinc['arquivo']}: {n} change(s) applied"
              + (f", {criadas} new sample(s) created" if criadas else "") + "."
              + (f" Not changed (signed off – only an Admin can change them): {', '.join(puladas)}." if puladas else ""),
              "aviso" if puladas else "ok")
        return redirect(url_for("lista"))

    # =====================================================================
    # BACKUP
    # =====================================================================
    @app.route("/backup", methods=["POST"])
    def backup_agora():
        """Copia os bancos (.db) e gera as planilhas Excel imediatamente."""
        registrar("BACKUP_NOW")
        try:
            criados, erros = backup.fazer_backup(forcar=True)
        except Exception as e:
            criados, erros = [], [str(e)]
        if criados:
            flash(f"Backup saved in {backup.PASTA_BACKUP}: " + ", ".join(os.path.basename(c) for c in criados), "ok")
        for e in erros:
            flash("Backup warning: " + e, "erro")
        if not criados and not erros:
            flash("No database found to back up.", "aviso")
        return redirect(request.referrer or url_for("lista"))

    # =====================================================================
    # CONTA, USUÁRIOS E AUDITORIA
    # =====================================================================
    @app.route("/account/password", methods=["GET", "POST"])
    def trocar_senha():
        u = usuario()
        if request.method == "POST":
            f = request.form
            ok, _m, _u = leptons_auth.autenticar(u["username"], f.get("atual", ""))
            erro = ("Current password is incorrect." if not ok else
                    "The new passwords do not match." if f.get("nova") != f.get("nova2") else
                    leptons_auth.validar_senha(f.get("nova", ""), u["username"]))
            if erro:
                return render_template("senha.html", erro=erro), 400
            leptons_auth.definir_senha(u["id"], f["nova"], trocar_senha=False, username=u["username"])
            registrar("PASSWORD_CHANGE")
            flash("Password changed.", "ok")
            return redirect(url_for("lista"))
        return render_template("senha.html")

    @app.route("/users")
    @so_admin
    def usuarios():
        return render_template("usuarios.html", lista=leptons_auth.listar_usuarios(), perfis=leptons_auth.PERFIS)

    @app.route("/users/new", methods=["POST"])
    @so_admin
    def novo_usuario():
        f = request.form
        try:
            if f.get("senha") != f.get("senha2"):
                raise ValueError("The passwords do not match.")
            leptons_auth.criar_usuario(f.get("username"), f.get("nome"), f.get("perfil"), f.get("senha", ""),
                                       trocar_senha=True)
        except ValueError as e:
            flash(str(e), "erro")
            return redirect(url_for("usuarios"))
        registrar("USER_CREATE", f"{f.get('username', '').strip()} ({f.get('perfil')})")
        flash("User created. The person must choose a new password at the first login.", "ok")
        return redirect(url_for("usuarios"))

    def _usuario_por_id(user_id):
        u = next((u for u in leptons_auth.listar_usuarios() if u[0] == user_id), None)
        if u is None:
            abort(404)
        return u

    @app.route("/users/<int:user_id>/edit", methods=["POST"])
    @so_admin
    def editar_usuario(user_id):
        _id, user, nome, perfil, _ativo, _ult = _usuario_por_id(user_id)
        novo_nome, novo_perfil = request.form.get("nome", "").strip(), request.form.get("perfil")
        try:
            leptons_auth.alterar_usuario(user_id, nome=novo_nome, perfil=novo_perfil)
        except ValueError as e:
            flash(str(e), "erro")
            return redirect(url_for("usuarios"))
        registrar("USER_UPDATE", f"{user}: {nome}/{perfil} -> {novo_nome or nome}/{novo_perfil}")
        if user_id == usuario()["id"]:
            session["usuario"] = dict(usuario(), nome=novo_nome or nome, perfil=novo_perfil)
        flash(f"User {user} updated.", "ok")
        return redirect(url_for("usuarios"))

    @app.route("/users/<int:user_id>/reset", methods=["POST"])
    @so_admin
    def redefinir_senha(user_id):
        _id, user, *_ = _usuario_por_id(user_id)
        f = request.form
        erro = ("The passwords do not match." if f.get("senha") != f.get("senha2")
                else leptons_auth.validar_senha(f.get("senha", ""), user))
        if erro:
            flash(f"{user}: {erro}", "erro")
            return redirect(url_for("usuarios"))
        leptons_auth.definir_senha(user_id, f["senha"], trocar_senha=True, username=user)
        registrar("PASSWORD_RESET", user)
        flash(f"Temporary password set for {user}. The user must change it at the next login.", "ok")
        return redirect(url_for("usuarios"))

    @app.route("/users/<int:user_id>/toggle", methods=["POST"])
    @so_admin
    def ativar_desativar(user_id):
        _id, user, _nome, _perfil, ativo, _ult = _usuario_por_id(user_id)
        if user_id == usuario()["id"] and ativo:
            flash("You cannot deactivate your own account.", "erro")
            return redirect(url_for("usuarios"))
        try:
            leptons_auth.alterar_usuario(user_id, ativo=not ativo)
        except ValueError as e:
            flash(str(e), "erro")
            return redirect(url_for("usuarios"))
        registrar("USER_DEACTIVATE" if ativo else "USER_ACTIVATE", user)
        flash(f"User {user} {'deactivated' if ativo else 'activated'}.", "ok")
        return redirect(url_for("usuarios"))

    def linhas_auditoria(termo):
        t = "%" + termo + "%"
        con = leptons_auth._con()
        try:
            return con.execute(
                "SELECT quando, usuario, programa, acao, detalhe FROM auditoria "
                "WHERE usuario LIKE ? OR programa LIKE ? OR acao LIKE ? OR detalhe LIKE ? OR quando LIKE ? "
                "ORDER BY id DESC LIMIT 2000", (t, t, t, t, t)).fetchall()
        finally:
            con.close()

    @app.route("/audit")
    @so_admin
    def auditoria():
        q = request.args.get("q", "").strip()
        return render_template("auditoria.html", linhas=linhas_auditoria(q), busca=q)

    @app.route("/audit.csv")
    @so_admin
    def auditoria_csv():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(("When", "User", "Program", "Action", "Details"))
        w.writerows(linhas_auditoria(request.args.get("q", "").strip()))
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="audit_log.csv"'})

    # =====================================================================
    # LOGIN / SAIR
    # =====================================================================
    @app.route("/logo/<nome>")
    def logo(nome):
        """Logos da Unicamp e do DUNE; com ?recorte=1, sem as margens brancas do arquivo (tela de login)."""
        if nome not in LOGOS:
            abort(404)
        if request.args.get("recorte"):
            return send_file(io.BytesIO(logo_recortado(nome)), mimetype="image/png", max_age=3600)
        return send_from_directory(dados.BASE, nome)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """Usuário e senha (os mesmos dos programas de mesa); senha temporária obriga a escolher uma nova."""
        proxima = request.values.get("proxima", "")
        if not proxima.startswith("/") or proxima.startswith("//"):
            proxima = url_for("lista")                 # só volta para páginas deste programa
        if usuario():
            return redirect(proxima)
        if leptons_auth.contar_usuarios() == 0:
            return render_template("login.html", sem_usuarios=True)
        f = request.form
        username = f.get("username", "").strip()
        if request.method == "GET":
            return render_template("login.html", proxima=proxima)

        ok, msg, u = leptons_auth.autenticar(username, f.get("senha", ""))
        if not ok:
            leptons_auth.registrar_como({"id": None, "username": username, "nome": "", "perfil": ""},
                                        "LOGIN_FAILED", msg)
            return render_template("login.html", proxima=proxima, username=username, erro=msg), 401
        if u["trocar_senha"]:
            if "nova" not in f:
                return render_template("login.html", proxima=proxima, username=username, trocar=True,
                                       senha=f.get("senha", ""))
            erro = ("The new passwords do not match." if f["nova"] != f.get("nova2") else
                    "Choose a password different from the current one." if f["nova"] == f.get("senha") else
                    leptons_auth.validar_senha(f["nova"], u["username"]))
            if erro:
                return render_template("login.html", proxima=proxima, username=username, trocar=True,
                                       senha=f.get("senha", ""), erro=erro), 400
            leptons_auth.definir_senha(u["id"], f["nova"], trocar_senha=False, username=u["username"])
            leptons_auth.registrar_como(u, "PASSWORD_CHANGE", "first access / temporary password")
        session.clear()
        session["usuario"] = {"id": u["id"], "username": u["username"], "nome": u["nome"], "perfil": u["perfil"]}
        leptons_auth.registrar_como(u, "LOGIN")
        return redirect(url_for("entrando", proxima=proxima))

    @app.route("/starting")
    def entrando():
        """Tela de entrada com o logo animado; enquanto aparece, a página chama /api/starting."""
        proxima = request.args.get("proxima", "")
        if not proxima.startswith("/") or proxima.startswith("//"):
            proxima = url_for("lista")
        return render_template("entrando.html", proxima=proxima)

    @app.route("/api/starting", methods=["POST"])
    def api_entrando():
        """Passos feitos ao entrar (hoje: conferir os bancos; no futuro: sincronizar com o banco de dados)."""
        try:
            return {"ok": True, "passos": inicio.ao_entrar(usuario())}
        except Exception as e:
            return {"ok": False, "erro": str(e)}, 500

    @app.route("/logout", methods=["POST"])
    def logout():
        if usuario():
            leptons_auth.registrar_como(usuario(), "LOGOUT")
        session.clear()
        return redirect(url_for("login"))

    @app.route("/quit", methods=["POST"])
    def sair():
        """Botão Quit: fecha o programa (fechar a aba do navegador não fecha o servidor)."""
        if usuario():
            leptons_auth.registrar_como(usuario(), "LOGOUT", "quit")
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return render_template("sair.html")

    def erro_pagina(mensagem, codigo=400):
        return render_template("erro.html", mensagem=mensagem), codigo

    @app.errorhandler(403)
    def proibido(_e):
        return erro_pagina("Only an Admin can open this page.", 403)

    @app.errorhandler(404)
    def nao_achado(_e):
        return erro_pagina("Not found.", 404)

    return app


@lru_cache(maxsize=None)
def logo_recortado(nome):
    """PNG do logo sem as margens brancas (o mesmo recorte do cabeçalho dos PDFs)."""
    with Image.open(dados.BASE / nome) as im:
        im = im.convert("RGB")
    caixa = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).point(
        lambda p: 255 if p > 20 else 0).getbbox()
    if caixa:
        im = im.crop(caixa)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


# =====================================================================
# SERVIDOR DO QR CODE E BACKUP AO ABRIR
# =====================================================================
def servidor_relatorios_ativo():
    return relatorio.iniciar_servidor_relatorios()


def tarefas_ao_abrir():
    """Ao abrir o programa: servidor dos links do QR code e o backup semanal. Retorna os avisos do backup."""
    servidor_relatorios_ativo()
    try:
        _, erros = backup.fazer_backup()
    except Exception as e:
        erros = [str(e)]
    return erros
