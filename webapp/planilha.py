"""Sincronização da planilha DUNE_Control.xlsx (abas Deposition Control e Efficiency Test) com as tarefas.

A planilha nunca apaga o que já foi gravado; as diferenças são mostradas antes de aplicar, e as evaporações que
ainda não estão no programa podem virar tarefas novas.
"""
import re
from datetime import datetime

from . import dados, tarefas
from .db import conectar
from .relatorio import coletar_dados_relatorio, diferenca_massas_ef, estado_eficiencia_dados

AMOSTRAS_EFICIENCIA = dados.AMOSTRAS
LIMITE_EFICIENCIA = dados.LIMITE_EFICIENCIA
STATUS_INCOMPLETO = dados.STATUS_INCOMPLETO
area_amostra_ef = dados.area_amostra_ef


def converter_float(valor):
    """Aceita vírgula ou ponto como separador decimal."""
    valor = str(valor).strip().replace(",", ".")
    if not valor:
        raise ValueError("valor vazio")
    return float(valor)


def calcular_densidade_massa(antes, depois):
    """Calcula (massa depois - massa antes)/área em µg/cm²."""
    return (converter_float(depois) - converter_float(antes)) * 1_000_000.0 / dados.AREA_FILTRO_CM2


# ---- Importação da planilha DUNE_Control.xlsx (aba "Efficiency Test") ----
COLUNAS_PLANILHA_EF = {        # chave -> início do título da coluna na planilha
    "run": "RUN",
    "box": "BOX PID",
    "posicao": "POSITION",
    "ctrl": "CONTROL FILTER PID",
    "antes": "MASS BEFORE",
    "depois": "MASS AFTER",
    "area": "AREA",
    "x": "RELATIVE EFFICIENCY",
}


def _norm_pid(texto):
    """Compara PIDs ignorando maiúsculas, espaços e '_' no lugar de '-' (a planilha usa os dois)."""
    return re.sub(r"\s+", "", str(texto or "")).upper().replace("_", "-")


def _celula_planilha(valor):
    """Valor da célula como texto; vazio para célula em branco, '#'/'###' (não testada) e erros (#VALUE!)."""
    if valor is None:
        return ""
    if isinstance(valor, (int, float)):
        return format(valor, ".10g")
    texto = str(valor).strip()
    return "" if texto.startswith("#") else texto


def ler_planilha_eficiencia(caminho):
    """Lê a aba de eficiência da planilha DUNE_Control. Retorna (nome da aba, linhas das amostras)."""
    from openpyxl import load_workbook
    wb = load_workbook(caminho, data_only=True, read_only=True)
    try:
        aba = next((ws for ws in wb.worksheets if "efficiency" in ws.title.lower()), None)
        if aba is None:
            raise ValueError("The spreadsheet has no 'Efficiency Test' sheet.")
        colunas = None
        linhas = []
        run = box = ""
        for n, row in enumerate(aba.iter_rows(values_only=True), start=1):
            if colunas is None:       # procura a linha de títulos
                titulos = [str(c or "").strip().upper() for c in row]
                achadas = {}
                for chave, inicio in COLUNAS_PLANILHA_EF.items():
                    i = next((i for i, t in enumerate(titulos) if t.startswith(inicio)), None)
                    if i is not None:
                        achadas[chave] = i
                if "ctrl" in achadas and "x" in achadas:
                    colunas = achadas
                continue

            def val(chave):
                i = colunas.get(chave)
                return row[i] if i is not None and i < len(row) else None

            # RUN e BOX PID ficam em células mescladas: só a primeira linha de cada evaporação tem o valor
            if _celula_planilha(val("run")):
                run = str(val("run")).strip()
            if _celula_planilha(val("box")):
                box = str(val("box")).strip()
            ctrl = str(val("ctrl") or "").strip()
            m = re.search(r"P\s*(02|03|14)\b", (str(val("posicao") or "") + " " + ctrl).upper())
            if not ctrl and not m:
                continue
            antes_bruto = val("antes")
            linhas.append({
                "linha": n, "run": run, "box": box, "ctrl": ctrl, "amostra": "P" + m.group(1) if m else "",
                "antes": _celula_planilha(antes_bruto), "depois": _celula_planilha(val("depois")),
                "area": _celula_planilha(val("area")), "x": _celula_planilha(val("x")),
                "nao_testada": isinstance(antes_bruto, str) and antes_bruto.strip().startswith("#"),
            })
        if colunas is None:
            raise ValueError(f"Header row not found in sheet '{aba.title}' "
                             "(expected columns 'CONTROL FILTER PID' and 'RELATIVE EFFICIENCY').")
        return aba.title, linhas
    finally:
        wb.close()


def linhas_da_tarefa(linhas, run, box_pid, pids):
    """Linha da planilha de cada amostra: pelo RUN (ex.: DUNE_EVAP_#0002#) + posição; senão, pelo PID da
    amostra de controle; senão, pelo BOX PID + posição."""
    achadas = {}
    for amostra in AMOSTRAS_EFICIENCIA:
        r = None
        if _norm_pid(run):
            r = next((l for l in linhas
                      if _norm_pid(l["run"]) == _norm_pid(run) and l["amostra"] == amostra), None)
        pid = _norm_pid(pids.get(amostra))
        if r is None and pid:
            r = next((l for l in linhas if _norm_pid(l["ctrl"]) == pid), None)
        if r is None and _norm_pid(box_pid):
            r = next((l for l in linhas
                      if _norm_pid(l["box"]) == _norm_pid(box_pid) and l["amostra"] == amostra), None)
        if r is not None:
            achadas[amostra] = r
    return achadas


# ---- Aba "Deposition Control" da mesma planilha (uma evaporação = 3 linhas: P02, P03, P14) ----
COLUNAS_PLANILHA_DEP = {
    "run": "RUN",
    "box": "BOX PID",
    "qtd": "QUANTITY",
    "data": "EVAP",
    "posicao": "POSITION",
    "antes": "MASS BEFORE",
    "depois": "MASS AFTER",
    "ctrl": "CONTROL FILTER PID",
    "ptp": "PTP BATCH",
    "notas": "NOTES",
}


def ler_planilha_deposicao(caminho):
    """Lê a aba 'Deposition Control'. Retorna (nome da aba, {run normalizado: dados da evaporação}).
    Sem essa aba, retorna (None, {})."""
    from openpyxl import load_workbook
    wb = load_workbook(caminho, data_only=True, read_only=True)
    try:
        aba = next((ws for ws in wb.worksheets if "deposition" in ws.title.lower()), None)
        if aba is None:
            return None, {}
        colunas = None
        runs = {}
        atual = None
        for n, row in enumerate(aba.iter_rows(values_only=True), start=1):
            if colunas is None:       # procura a linha de títulos
                titulos = [str(c or "").strip().upper() for c in row]
                achadas = {}
                for chave, inicio in COLUNAS_PLANILHA_DEP.items():
                    i = next((i for i, t in enumerate(titulos) if t.startswith(inicio)), None)
                    if i is not None:
                        achadas[chave] = i
                if {"run", "posicao", "antes", "depois"} <= set(achadas):
                    colunas = achadas
                continue

            def val(chave):
                i = colunas.get(chave)
                return row[i] if i is not None and i < len(row) else None

            def texto(chave):
                """Texto da célula; vazio para os modelos ainda não preenchidos (DUNE-XA-HD-#####-####)."""
                v = _celula_planilha(val(chave))
                return "" if "#" in v else v

            # RUN fica só na primeira das 3 linhas; 'DUNE_EVAP_#  #' (sem número) é linha-modelo vazia
            run = str(val("run") or "").strip()
            if run:
                if not re.search(r"#\s*\d+\s*#", run):
                    atual = None
                    continue
                data = val("data")
                atual = runs.setdefault(_norm_pid(run), {
                    "run": run, "linha": n, "box": texto("box"), "qtd": texto("qtd"),
                    "data": data.strftime("%Y-%m-%d") if hasattr(data, "strftime") else texto("data"),
                    "ptp": "", "notas": [], "massas": {}, "pids": {}})
            if atual is None:
                continue
            if texto("ptp") and not atual["ptp"]:
                atual["ptp"] = texto("ptp")
            if texto("notas"):
                atual["notas"].append(texto("notas"))
            ctrl = texto("ctrl")
            m = re.search(r"P\s*(02|03|14)\b", (str(val("posicao") or "") + " " + ctrl).upper())
            if not m:
                continue
            atual["massas"][int(m.group(1))] = (_celula_planilha(val("antes")), _celula_planilha(val("depois")), n)
            if ctrl:
                atual["pids"]["P" + m.group(1)] = ctrl
        if colunas is None:
            raise ValueError(f"Header row not found in sheet '{aba.title}' "
                             "(expected columns 'RUN', 'POSITION', 'MASS BEFORE' and 'MASS AFTER').")
        return aba.title, runs
    finally:
        wb.close()


# ---- Sincronização da planilha inteira com as tarefas ----
# campo da amostra de eficiência -> (coluna em eficiencia_amostras, nome mostrado)
CAMPOS_SYNC_EF = {"testada": ("testada", "Tested?"), "antes": ("massa_antes", "Mass before (g)"),
                  "depois": ("massa_depois", "Mass after (g)"), "area": ("area_cm2", "Area (cm²)"),
                  "x": ("eficiencia", "Relative efficiency (x)")}
# identificação (inspeção visual / tela principal) preenchida pela planilha quando estiver vazia
CAMPOS_SYNC_IDENT = {"run_evaporation": "Run", "box_pid": "PID", "pid_p02": "P02 PID", "pid_p03": "P03 PID",
                     "pid_p14": "P14 PID"}
# colunas da tabela tarefas vindas da aba Deposition Control
CAMPOS_SYNC_TAREFA = {"data_inicio": "Deposition date", "position_range": "Position (filters)",
                      "lote_ptp": "PTP batch", "observacoes": "Observations"}
# massas das posições 2, 3 e 14 (Mass Control by Position)
CAMPOS_SYNC_MASSA = {"m_antes": "Mass before (g)", "m_depois": "Mass after (g)"}
POSICAO_AMOSTRA = {2: "P02", 3: "P03", 14: "P14"}


def _mesmo_valor(a, b):
    a, b = str(a or "").strip(), str(b or "").strip()
    if a == b:
        return True
    try:
        return abs(converter_float(a) - converter_float(b)) < 1e-9
    except Exception:
        return False


def valores_planilha_amostra(l, atual):
    """Valores de uma amostra na planilha. A planilha nunca apaga o que já foi gravado: célula vazia é ignorada e
    '#' em MASS BEFORE (amostra não testada) só marca Tested? = No se a amostra ainda não tem medidas."""
    if l["nao_testada"]:
        medida = any(str(atual.get(k) or "").strip() for k in ("antes", "depois", "area", "x"))
        return {} if medida else {"testada": "No"}
    novos = {k: l[k] for k in ("antes", "depois", "area", "x") if l[k]}
    if novos:
        novos["testada"] = "Yes"
    return novos


def _atual_vazio():
    return {"tarefa": {}, "massas": {}, "ident": {}, "ef": {}}


def _atual_db(cur, tid):
    """Valores gravados de uma tarefa, no formato comparado com a planilha."""
    atual = _atual_vazio()
    cur.execute("SELECT data_inicio, position_range, lote_ptp, observacoes FROM tarefas WHERE id = ?", (tid,))
    atual["tarefa"] = {k: (v or "") for k, v in zip(CAMPOS_SYNC_TAREFA, cur.fetchone() or ())}
    cur.execute("SELECT posicao, massa_antes, massa_depois FROM massa_posicoes WHERE id_tarefa = ?", (tid,))
    for pos, antes, depois in cur.fetchall():
        atual["massas"][int(pos)] = {"m_antes": antes or "", "m_depois": depois or ""}
    cur.execute("SELECT run_evaporation, box_pid, pid_p02, pid_p03, pid_p14 FROM inspecao_visual_cab "
                "WHERE id_tarefa = ? ORDER BY id DESC", (tid,))
    atual["ident"] = {k: (v or "") for k, v in zip(CAMPOS_SYNC_IDENT, cur.fetchone() or ())}
    cur.execute("""
        SELECT amostra, testada, massa_antes, massa_depois, area_cm2, eficiencia, comprimento_mm, largura_mm
        FROM eficiencia_amostras WHERE id_tarefa = ?
    """, (tid,))
    for amostra, testada, antes, depois, area, x, comp, larg in cur.fetchall():
        atual["ef"][amostra] = {"testada": testada or "", "antes": antes or "", "depois": depois or "",
                                "area": area_amostra_ef({"area_cm2": area, "comprimento_mm": comp,
                                                         "largura_mm": larg}), "x": x or ""}
    return atual



def _mudancas_alvo(alvo, pid, atual, dep, linhas_ef, revisada=False):
    """Diferenças entre a planilha (evaporação 'dep' da aba Deposition Control + linhas da aba Efficiency Test)
    e um alvo: id da tarefa gravada, None = formulário, ("new", run) = tarefa que será criada."""
    ident = dict(atual["ident"])
    base = {"alvo": alvo, "pid": pid, "revisada": revisada}
    mudancas = []

    def muda(tipo, item, campo, antigo, novo, aba, linha):
        mudancas.append(dict(base, tipo=tipo, item=item, campo=campo, antigo=antigo, novo=novo, aba=aba, linha=linha))

    def preenche_ident(campo, novo, aba, linha):
        if novo and not ident.get(campo, "").strip():
            muda("ident", "", campo, "", novo, aba, linha)
            ident[campo] = novo

    if dep:
        linha = dep["linha"]
        preenche_ident("run_evaporation", dep["run"], "Deposition", linha)
        preenche_ident("box_pid", dep["box"], "Deposition", linha)
        for amostra, ctrl in dep["pids"].items():
            preenche_ident("pid_" + amostra.lower(), ctrl, "Deposition", linha)

        t = atual["tarefa"]
        novos = {"data_inicio": dep["data"], "lote_ptp": dep["ptp"]}
        try:
            if not t.get("position_range"):          # QUANTITY = 28 -> posições 1-28
                novos["position_range"] = f"1-{int(converter_float(dep['qtd']))}"
        except Exception:
            pass
        if not t.get("observacoes") and dep["notas"]:
            novos["observacoes"] = "; ".join(dep["notas"])
        for campo, novo in novos.items():
            if novo and not _mesmo_valor(t.get(campo), novo):
                muda("tarefa", "", campo, t.get(campo, ""), novo, "Deposition", linha)

        for pos, (antes, depois, linha_m) in sorted(dep["massas"].items()):
            m_atual = atual["massas"].get(pos, {})
            for campo, novo in (("m_antes", antes), ("m_depois", depois)):
                if novo and not _mesmo_valor(m_atual.get(campo), novo):
                    muda("massa", pos, campo, m_atual.get(campo, ""), novo, "Deposition", linha_m)

    # aba Efficiency Test: amostras P02/P03/P14 encontradas pelo RUN (ou PIDs) já conhecidos
    pids = {a: ident.get("pid_" + a.lower(), "") for a in AMOSTRAS_EFICIENCIA}
    achadas = linhas_da_tarefa(linhas_ef, ident.get("run_evaporation", ""), ident.get("box_pid", ""), pids)
    for amostra in AMOSTRAS_EFICIENCIA:
        l = achadas.get(amostra)
        if l is None:
            continue
        a_atual = atual["ef"].get(amostra, {})
        for campo, novo in valores_planilha_amostra(l, a_atual).items():
            if not _mesmo_valor(a_atual.get(campo, ""), novo):
                muda("ef", amostra, campo, a_atual.get(campo, ""), novo, "Efficiency", l["linha"])
    if achadas:
        primeira = next(iter(achadas.values()))
        preenche_ident("run_evaporation", primeira["run"], "Efficiency", primeira["linha"])
        preenche_ident("box_pid", primeira["box"], "Efficiency", primeira["linha"])
        for amostra, l in achadas.items():
            preenche_ident("pid_" + amostra.lower(), l["ctrl"], "Efficiency", l["linha"])
    return mudancas


def _dep_da_tarefa(deps, ident, codigo):
    """Evaporação da aba Deposition Control de uma tarefa: pelo RUN; senão, pelo BOX PID."""
    chave = _norm_pid(ident.get("run_evaporation"))
    if chave and chave in deps:
        return chave
    for pid in (ident.get("box_pid"), codigo):
        if _norm_pid(pid):
            achada = next((k for k, d in deps.items() if _norm_pid(d["box"]) == _norm_pid(pid)), None)
            if achada:
                return achada
    return None


def mudancas_planilha(linhas_ef, deps):
    """Compara a planilha com todas as tarefas gravadas e lista as tarefas
    a criar para os runs da aba Deposition Control que ainda não existem. Retorna (mudanças, nº de tarefas)."""
    mudancas = []
    usadas = set()
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT id, codigo_tarefa, COALESCE(qa_signoff_por, '') FROM tarefas ORDER BY id")
    tarefas = cur.fetchall()
    for tid, codigo, signoff in tarefas:
        atual = _atual_db(cur, tid)
        chave = _dep_da_tarefa(deps, atual["ident"], codigo)
        if chave:
            usadas.add(chave)
        mudancas += _mudancas_alvo(tid, codigo or "-", atual, deps.get(chave), linhas_ef, bool(signoff.strip()))
    conn.close()

    for chave, dep in deps.items():
        if chave not in usadas:
            mudancas += _mudancas_alvo(("new", chave), dep["box"] or dep["run"], _atual_vazio(), dep, linhas_ef)
    return mudancas, len(tarefas)


def _criar_tarefa_planilha(cur):
    """Tarefa vazia (sem lote, responsável etc.) que a sincronização vai preencher."""
    cur.execute("""
        INSERT INTO tarefas
        (codigo_tarefa, responsavel, data_inicio, status, descricao, lote_entrada_id, codigo_lote, position_range,
         observacoes, anexos_txt, eficiencia_optica_ok, valor_eficiencia, imersao_criogenica_ok, data_hora_registro,
         massa_ptp_g, lote_ptp)
        VALUES ('', '', '', ?, 'Substrate', NULL, '', '', '', '', 'Não', '', 'Não', ?, '', '')
    """, (STATUS_INCOMPLETO, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return cur.lastrowid


def _gravar_mudanca(cur, tid, m):
    campo = m["campo"]
    if m["tipo"] == "ident":
        cur.execute("SELECT id FROM inspecao_visual_cab WHERE id_tarefa = ?", (tid,))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO inspecao_visual_cab (id_tarefa) VALUES (?)", (tid,))
        cur.execute(f"UPDATE inspecao_visual_cab SET {campo} = ? WHERE id_tarefa = ?", (m["novo"], tid))
        if campo == "box_pid":     # o PID também identifica a tarefa
            cur.execute("UPDATE tarefas SET codigo_tarefa = ? WHERE id = ? AND COALESCE(codigo_tarefa, '') = ''",
                        (m["novo"], tid))
    elif m["tipo"] == "tarefa":
        cur.execute(f"UPDATE tarefas SET {campo} = ? WHERE id = ?", (m["novo"], tid))
    elif m["tipo"] == "massa":
        cur.execute("SELECT id FROM massa_posicoes WHERE id_tarefa = ? AND posicao = ?", (tid, m["item"]))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO massa_posicoes (id_tarefa, posicao, massa_antes, massa_depois, "
                        "densidade_massa_ug_cm2) VALUES (?, ?, '', '', '')", (tid, m["item"]))
        coluna = "massa_antes" if campo == "m_antes" else "massa_depois"
        cur.execute(f"UPDATE massa_posicoes SET {coluna} = ? WHERE id_tarefa = ? AND posicao = ?",
                    (m["novo"], tid, m["item"]))
    else:
        cur.execute("SELECT id FROM eficiencia_amostras WHERE id_tarefa = ? AND amostra = ?", (tid, m["item"]))
        if cur.fetchone() is None:
            cur.execute("""INSERT INTO eficiencia_amostras
                           (id_tarefa, amostra, testada, comprimento_mm, largura_mm, massa_antes, massa_depois,
                            area_cm2, densidade_ug_cm2, eficiencia, aprovado)
                           VALUES (?, ?, '', '', '', '', '', '', '', '', '')""", (tid, m["item"]))
        cur.execute(f"UPDATE eficiencia_amostras SET {CAMPOS_SYNC_EF[campo][0]} = ? WHERE id_tarefa = ? AND amostra = ?",
                    (m["novo"], tid, m["item"]))


def _recalcular_amostras_db(cur, tarefa_id):
    """Densidades e aprovação gravadas (posições 2/3/14 e amostras de eficiência), a partir das massas, área e x."""
    cur.execute("SELECT id, massa_antes, massa_depois FROM massa_posicoes WHERE id_tarefa = ?", (tarefa_id,))
    for rid, antes, depois in cur.fetchall():
        try:
            dens = f"{calcular_densidade_massa(antes, depois):.2f}"
        except Exception:
            dens = ""
        cur.execute("UPDATE massa_posicoes SET densidade_massa_ug_cm2 = ? WHERE id = ?", (dens, rid))

    cur.execute("""SELECT id, testada, massa_antes, massa_depois, area_cm2, comprimento_mm, largura_mm, eficiencia
                   FROM eficiencia_amostras WHERE id_tarefa = ?""", (tarefa_id,))
    for rid, testada, antes, depois, area, comp, larg, x in cur.fetchall():
        r = {"massa_antes": antes, "massa_depois": depois, "area_cm2": area, "comprimento_mm": comp,
             "largura_mm": larg}
        try:
            dens = format(converter_float(diferenca_massas_ef(r)) * 1_000_000.0 / converter_float(area_amostra_ef(r)), ".2f")
        except Exception:
            dens = ""
        try:
            aprovado = ("Yes" if round(converter_float(x), 6) >= LIMITE_EFICIENCIA else "No") if testada == "Yes" else ""
        except Exception:
            aprovado = ""
        cur.execute("UPDATE eficiencia_amostras SET densidade_ug_cm2 = ?, aprovado = ? WHERE id = ?",
                    (dens, aprovado, rid))



def aplicar_mudancas_planilha(mudancas, arquivo, registrar, criar_novas=True):
    """Grava as mudanças nas tarefas (criando as novas, se pedido); registrar(acao, detalhe) vai para a auditoria.
    Retorna (nº de mudanças gravadas, nº de tarefas criadas)."""
    por_alvo = {}
    for m in mudancas:
        por_alvo.setdefault(m["alvo"], []).append(m)

    ids = {}
    conn = conectar()
    cur = conn.cursor()
    for alvo, lista in por_alvo.items():
        if alvo is None:
            continue
        if isinstance(alvo, tuple):
            if not criar_novas:
                continue
            tid = _criar_tarefa_planilha(cur)
        else:
            tid = alvo
        ids[alvo] = tid
        for m in lista:
            _gravar_mudanca(cur, tid, m)
        _recalcular_amostras_db(cur, tid)
        if lista[0]["revisada"]:          # dados mudaram: a revisão anterior deixa de valer
            cur.execute("UPDATE tarefas SET qa_signoff_por = '', qa_signoff_data = '' WHERE id = ?", (tid,))
    conn.commit()
    conn.close()

    # resumo da eficiência na tabela de tarefas e situação (Incomplete / To be reviewed)
    for tid in ids.values():
        d = coletar_dados_relatorio(tid)
        if d is None:
            continue
        ok = "Sim" if estado_eficiencia_dados(d) == "approved" else "Não"
        valor = "; ".join(f"{a}: {r.get('eficiencia')}" for a, r in d["ef_amostras"].items()
                          if r.get("testada") == "Yes" and (r.get("eficiencia") or "").strip())
        conn = conectar()
        conn.execute("UPDATE tarefas SET eficiencia_optica_ok = ?, valor_eficiencia = ? WHERE id = ?", (ok, valor, tid))
        conn.commit()
        conn.close()
        tarefas.atualizar_status(tid)

    novas = sum(1 for a in ids if isinstance(a, tuple))
    for alvo, tid in ids.items():
        lista = por_alvo[alvo]
        registrar("SHEET_SYNC", f"id={tid}{' (new)' if isinstance(alvo, tuple) else ''} "
                                f"PID={lista[0]['pid']} file={arquivo} changes={len(lista)}"
                                + (" review_cleared" if lista[0]["revisada"] else ""))
    return sum(len(por_alvo[a]) for a in ids), novas


def _nome_campo_sync(m):
    return (CAMPOS_SYNC_IDENT.get(m["campo"]) or CAMPOS_SYNC_TAREFA.get(m["campo"])
            or CAMPOS_SYNC_MASSA.get(m["campo"]) or CAMPOS_SYNC_EF[m["campo"]][1])


def ler_planilha(caminho):
    """(nome das abas lidas, linhas da aba Efficiency Test, evaporações da aba Deposition Control)."""
    aba_dep, deps = ler_planilha_deposicao(caminho)
    try:
        aba_ef, linhas_ef = ler_planilha_eficiencia(caminho)
    except ValueError:
        if aba_dep is None:
            raise
        aba_ef, linhas_ef = None, []
    return [a for a in (aba_dep, aba_ef) if a], linhas_ef, deps
