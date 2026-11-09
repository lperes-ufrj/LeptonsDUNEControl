"""Leitura das amostras (tarefas) e as regras de situação de cada uma.

Regras: pendências, estados da imersão criogênica e da eficiência óptica, Incomplete -> To be reviewed -> Completed.
"""
import re
from pathlib import Path

from . import config, db
from .i18n import t as tr

BASE = Path(__file__).resolve().parent.parent          # pasta do projeto (logos)
PASTA = config.PASTA_DADOS                             # arquivos gerados e enviados (PDFs, anexos...)

AREA_FILTRO_CM2 = 77.0
N_FILTROS = 28
LIMITE_EFICIENCIA = 0.75
MIN_AMOSTRAS_EFICIENCIA = 2
LIMITE_PERDA_PCT = 5.0
AMOSTRAS = ["P02", "P03", "P14"]
POSICOES = {2: "Center", 3: "Middle", 14: "External"}

COLUNAS_INSPECAO = [          # (coluna no banco, título)
    ("visual_status", "Visual"), ("uniformity", "Uniformity"), ("stains", "Stains"), ("particles", "Particles"),
    ("edge_defects", "Edge"), ("finger_defects", "Finger"), ("other_defects", "Other"),
]
OBRIGATORIOS_FILTRO = [c for c, _ in COLUNAS_INSPECAO] + ["classification"]

ITENS_IMERSAO = [             # (chave, item, critério de aceitação, condição de rejeição)
    ("film_adhesion", "PTP Film Adhesion",
     "No evidence of film peeling, delamination, or detachment.",
     "Any visible peeling, delamination, or film detachment."),
    ("film_integrity", "Film Integrity",
     "No visible cracks, fractures, or discontinuities in the deposited layer.",
     "Visible cracks, fractures, or discontinuities in the deposited layer."),
    ("surface_condition", "Surface Condition",
     "No discoloration, whitening, blistering, or degradation attributable to cryogenic exposure.",
     "Discoloration, blistering, whitening, or other signs of degradation after testing."),
    ("substrate_integrity", "Substrate Integrity",
     "No cracks, fractures, chipping, or structural damage to the glass substrate.",
     "Any crack, fracture, chipping, or structural damage."),
    ("cryo_compatibility", "Cryogenic Compatibility",
     "No visible changes indicating failure during cooling, immersion, or recovery stages.",
     "Any visible alteration indicating failure during cooling, immersion, or recovery."),
    ("post_test", "Post-Test Visual Inspection",
     "Glass substrate appearance consistent with pre-test condition, excluding normal handling marks.",
     "Any defect not present before testing and attributable to cryogenic exposure."),
]

STATUS_INCOMPLETO = "Incomplete"
STATUS_REVISAR = "To be reviewed"
STATUS_COMPLETO = "Completed"
STATUS_TODOS = (STATUS_INCOMPLETO, STATUS_REVISAR, STATUS_COMPLETO)
TXT_ESTADO = {"approved": "Approved", "rejected": "Rejected", "partial": "In progress", "empty": "Not filled"}


def _linhas(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params)]


def numero_run(run):
    """Número da evaporação (DUNE_EVAP_#0032# -> "32"): é o ID da tarefa."""
    numeros = re.findall(r"\d+", str(run or ""))
    return str(int(numeros[-1])) if numeros else ""


def numero(valor):
    """Aceita vírgula ou ponto; None se vazio ou inválido."""
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def area_amostra_ef(r):
    """Área (cm²) gravada da amostra; registros antigos sem área usam comprimento x largura (mm)."""
    area = str(r.get("area_cm2") or "").strip()
    if area:
        return area
    c, l = numero(r.get("comprimento_mm")), numero(r.get("largura_mm"))
    return format(c * l / 100.0, ".2f") if c is not None and l is not None else ""


def densidade(antes, depois, area_cm2=AREA_FILTRO_CM2):
    """Densidade de massa (µg/cm²) = (depois - antes) / área."""
    a, d, ar = numero(antes), numero(depois), numero(area_cm2)
    if a is None or d is None or not ar:
        return None
    return (d - a) * 1e6 / ar


# ---------------- lotes (aba Batches) ----------------
def codigos_lotes_internos():
    """Códigos atuais dos lotes internos e de limpeza ({id: código}), que podem ter sido renomeados."""
    conn = db.conectar()
    try:
        internos = {r["id"]: r["codigo_interno"] for r in conn.execute("SELECT id, codigo_interno FROM lotes_internos")}
        limpezas = {r["id"]: r["codigo_interno"] for r in conn.execute("SELECT id, codigo_interno FROM lotes_limpeza")}
    finally:
        conn.close()
    return internos, limpezas


def lotes_opto():
    """{código do lote OPTO: dados do lote}."""
    conn = db.conectar()
    try:
        return {r["lote_geral"]: {"lote": r["lote_geral"], "chegada": r["data_recebimento"] or "",
                                  "empresa": r["fornecedor"] or "", "lote_empresa": r["lote_fornecedor"] or "",
                                  "filtros": r["total_filtros"] or ""}
                for r in conn.execute("SELECT lote_geral, data_recebimento, fornecedor, lote_fornecedor, total_filtros "
                                      "FROM lotes")}
    finally:
        conn.close()


def _lotes_por_tarefa(conn):
    """{id da tarefa: [{opto, interno, tipo}]} com os códigos atuais dos lotes internos."""
    internos, limpezas = codigos_lotes_internos()
    por_tarefa = {}
    for r in conn.execute("SELECT id_tarefa, codigo_lote, lote_interno_id, codigo_lote_interno, tipo_lote "
                          "FROM tarefa_lotes ORDER BY id"):
        tipo = r["tipo_lote"] or "opto"
        origem = limpezas if tipo == "limpeza" else internos
        por_tarefa.setdefault(r["id_tarefa"], []).append({
            "opto": "Leptons cleaning" if tipo == "limpeza" else (r["codigo_lote"] or ""),
            "interno": origem.get(r["lote_interno_id"]) or r["codigo_lote_interno"] or "",
            "tipo": tipo,
        })
    for r in conn.execute("SELECT id, codigo_lote FROM tarefas WHERE COALESCE(codigo_lote, '') <> ''"):
        por_tarefa.setdefault(r["id"], [{"opto": r["codigo_lote"], "interno": "", "tipo": "opto"}])   # registros antigos
    return por_tarefa


# ---------------- amostras ----------------
def dados_tarefas(conn, tarefa_id=None):
    """Tudo o que o banco tem de cada tarefa (ou só de tarefa_id), no formato das regras abaixo.

    Lê cada tabela uma vez para todas as tarefas: com o banco em outro servidor, uma consulta por tarefa e por
    tabela deixaria a lista lenta com muitas amostras."""
    onde, params = ("WHERE id_tarefa = ?", (tarefa_id,)) if tarefa_id is not None else ("", ())

    def por_tarefa(tabela, ordem):
        grupos = {}
        for r in _linhas(conn, f"SELECT * FROM {tabela} {onde} ORDER BY {ordem}", params):
            grupos.setdefault(r["id_tarefa"], []).append(r)
        return lambda tid: grupos.get(tid, [])

    tarefas = _linhas(conn, "SELECT * FROM tarefas" + (" WHERE id = ?" if tarefa_id is not None else ""), params)
    lotes = _lotes_por_tarefa(conn)
    cab, ef = por_tarefa("inspecao_visual_cab", "id"), por_tarefa("eficiencia_teste", "id")
    massas, filtros = por_tarefa("massa_posicoes", "posicao, id"), por_tarefa("inspecao_visual_filtros", "filtro, id")
    im_massas, im_itens = por_tarefa("imersao_massas", "id"), por_tarefa("imersao_itens", "id")
    ef_amostras = por_tarefa("eficiencia_amostras", "id")
    return [{
        "id": t["id"],
        "tarefa": t,
        "lotes": lotes.get(t["id"], []),
        "cab": (cab(t["id"]) or [{}])[0],
        "massas": {r["posicao"]: r for r in massas(t["id"])},
        "filtros": {r["filtro"]: r for r in filtros(t["id"])},
        "im_massas": {r["amostra"]: r for r in im_massas(t["id"])},
        "im_itens": {r["item"]: r["aprovado"] for r in im_itens(t["id"])},
        "ef_teste": (ef(t["id"]) or [{}])[0],
        "ef_amostras": {r["amostra"]: r for r in ef_amostras(t["id"])},
    } for t in tarefas]


def resumo_visual(d):
    """(filtros completos, {A, B, C}, algo preenchido)."""
    completos, contagem, algum = 0, {"A": 0, "B": 0, "C": 0}, False
    for n in range(1, N_FILTROS + 1):
        f = d["filtros"].get(n, {})
        valores = [(f.get(k) or "") for k in OBRIGATORIOS_FILTRO]
        completos += all(valores)
        algum = algum or any(valores) or bool(f.get("comments"))
        if f.get("classification") in contagem:
            contagem[f["classification"]] += 1
    return completos, contagem, algum


def estado_imersao(d):
    valores = [(d["im_massas"].get(a) or {}).get("aprovado") or "" for a in AMOSTRAS]
    valores += [d["im_itens"].get(chave) or "" for chave, *_ in ITENS_IMERSAO]
    if "No" in valores:
        return "rejected"
    if all(v == "Yes" for v in valores):
        return "approved"
    return "partial" if any(valores) or d["tarefa"].get("imersao_observacoes") else "empty"


def estado_eficiencia(d):
    testadas = medidas = 0
    reprovado = algum = False
    for amostra in AMOSTRAS:
        r = d["ef_amostras"].get(amostra) or {}
        if any((r.get(k) or "") for k in ("testada", "area_cm2", "comprimento_mm", "largura_mm",
                                            "massa_antes", "massa_depois", "eficiencia")):
            algum = True
        if r.get("testada") != "Yes":
            continue
        testadas += 1
        x = numero(r.get("eficiencia"))
        if x is None:
            continue
        medidas += 1
        reprovado = reprovado or round(x, 6) < LIMITE_EFICIENCIA
    if reprovado:
        return "rejected"
    if medidas >= MIN_AMOSTRAS_EFICIENCIA and medidas == testadas:
        return "approved"
    return "partial" if algum else "empty"


def decisao_lote(estado_im, estado_ef):
    if "rejected" in (estado_im, estado_ef):
        return "Rejected"
    if estado_im == "approved" and estado_ef == "approved":
        return "Approved"
    return "Pending"


def pendencias(d):
    """O que ainda falta para a tarefa ficar completa (lista vazia = pronta para revisão)."""
    t, c, te = d["tarefa"], d["cab"], d["ef_teste"]
    falta = []

    def exige(valor, secao, texto):
        if not str(valor or "").strip():
            falta.append(secao + ": " + tr(texto))

    exige(t.get("codigo_tarefa"), "Deposition", "PID")
    exige(t.get("data_inicio"), "Deposition", "deposition date")
    exige(t.get("responsavel"), "Deposition", "responsible")
    if not d["lotes"]:
        falta.append("Deposition: " + tr("batch / internal lot"))
    exige(t.get("position_range"), "Deposition", "position filters")
    exige(t.get("massa_ptp_g"), "Deposition", "PTP mass")
    for pos in POSICOES:
        m = d["massas"].get(pos) or {}
        if not (str(m.get("massa_antes") or "").strip() and str(m.get("massa_depois") or "").strip()):
            falta.append("Mass control: " + tr("position {pos}", pos=pos))

    for chave, texto in (("run_evaporation", "run evaporation"), ("inspector", "inspector"),
                         ("pid_p02", "P02 PID"), ("pid_p03", "P03 PID"), ("pid_p14", "P14 PID"),
                         ("data_inspecao", "inspection date"), ("operador", "performed by")):
        exige(c.get(chave), "Visual inspection", texto)
    completos, _, _ = resumo_visual(d)
    if completos < N_FILTROS:
        falta.append("Visual inspection: " + tr("{n} of {total} filters not fully classified",
                                                n=N_FILTROS - completos, total=N_FILTROS))

    exige(t.get("imersao_data"), "Cryogenic immersion", "test date")
    exige(t.get("imersao_operador"), "Cryogenic immersion", "performed by")
    sem_massa = [a for a in AMOSTRAS if not (d["im_massas"].get(a) or {}).get("aprovado")]
    if sem_massa:
        falta.append("Cryogenic immersion: " + tr("masses of {amostras}", amostras=", ".join(sem_massa)))
    sem_item = [chave for chave, *_ in ITENS_IMERSAO if not d["im_itens"].get(chave)]
    if sem_item:
        falta.append("Cryogenic immersion: " + tr("{n} of {total} post-immersion checks",
                                                  n=len(sem_item), total=len(ITENS_IMERSAO)))

    for chave, texto in (("data_teste", "test date"), ("ref_id", "reference substrate ID"),
                         ("ref_data", "reference installation date"), ("temperatura_c", "room temperature"),
                         ("umidade_pct", "relative humidity"), ("operador", "performed by")):
        exige(te.get(chave), "Optical efficiency", texto)
    testadas = 0
    for amostra in AMOSTRAS:
        r = d["ef_amostras"].get(amostra) or {}
        if r.get("testada") == "No":
            continue
        if r.get("testada") != "Yes":
            falta.append(f"Optical efficiency: {amostra} – " + tr("Tested? not answered"))
            continue
        testadas += 1
        faltam = [tr(nome) for chave, nome in (("massa_antes", "mass before"), ("massa_depois", "mass after"))
                  if not str(r.get(chave) or "").strip()]
        if not area_amostra_ef(r):
            faltam.append(tr("area"))
        if not str(r.get("eficiencia") or "").strip():
            faltam.append(tr("relative efficiency"))
        if faltam:
            falta.append(f"Optical efficiency: {amostra} – " + ", ".join(faltam))
    if testadas < MIN_AMOSTRAS_EFICIENCIA:
        falta.append("Optical efficiency: " + tr("at least {n} tested samples", n=MIN_AMOSTRAS_EFICIENCIA))
    return falta


def status(d, falta=None):
    """Incomplete (falta informação) -> To be reviewed (tudo preenchido) -> Completed (QA sign-off)."""
    if pendencias(d) if falta is None else falta:
        return STATUS_INCOMPLETO
    return STATUS_COMPLETO if (d["tarefa"].get("qa_signoff_por") or "").strip() else STATUS_REVISAR


def _resumo(d):
    """Linha da lista de tarefas."""
    t, c = d["tarefa"], d["cab"]
    completos, contagem, _ = resumo_visual(d)
    falta = pendencias(d)
    run = c.get("run_evaporation") or ""
    return {
        "id": d["id"], "numero": numero_run(run), "run": run, "pid": t.get("codigo_tarefa") or "",
        "box_pid": c.get("box_pid") or "", "pids_ctrl": " ".join(c.get(k) or "" for k in ("pid_p02", "pid_p03", "pid_p14")),
        "status": status(d, falta), "pendencias": len(falta),
        "lotes": d["lotes"], "responsavel": t.get("responsavel") or "", "data": t.get("data_inicio") or "",
        "visual": completos, "classes": contagem,
        "imersao": estado_imersao(d), "eficiencia": estado_eficiencia(d),
        "signoff": (t.get("qa_signoff_por") or "").strip(),
    }


def listar_tarefas():
    """Todas as tarefas (maior run primeiro; tarefas sem run no topo)."""
    conn = db.conectar()
    try:
        tarefas = [_resumo(d) for d in dados_tarefas(conn)]
    finally:
        conn.close()
    tarefas.sort(key=lambda r: (r["numero"] == "", int(r["numero"] or 0), r["id"]), reverse=True)
    return tarefas


def _origem_filtros(conn, tarefa_id):
    """{nº do filtro: {tipo, opto, interno}} gravados na janela Filter origin (códigos atuais dos lotes internos)."""
    internos, limpezas = codigos_lotes_internos()
    linhas = conn.execute("SELECT filtro, tipo_lote, codigo_lote, lote_interno_id, codigo_lote_interno "
                          "FROM filtro_origem WHERE id_tarefa = ?", (tarefa_id,)).fetchall()
    origem = {}
    for r in linhas:
        tipo = r["tipo_lote"] or "opto"
        codigos = limpezas if tipo == "limpeza" else internos
        origem[r["filtro"]] = {"tipo": tipo, "opto": "Leptons cleaning" if tipo == "limpeza" else (r["codigo_lote"] or ""),
                               "interno": codigos.get(r["lote_interno_id"]) or r["codigo_lote_interno"] or ""}
    return origem


def ler_tarefa(tarefa_id):
    """Tudo de uma tarefa, com os estados e as pendências já calculados; None se não existir."""
    conn = db.conectar()
    try:
        achadas = dados_tarefas(conn, tarefa_id)
        if not achadas:
            return None
        d = achadas[0]
        origem = _origem_filtros(conn, tarefa_id)
    finally:
        conn.close()
    opto = lotes_opto()
    for l in d["lotes"]:
        l.update({k: v for k, v in (opto.get(l["opto"]) or {}).items() if k != "lote"})
    # de onde veio cada filtro: só conta com mais de um lote (com um lote só, todos vêm dele)
    for l in d["lotes"]:
        l["filtros_origem"] = sorted(n for n, o in origem.items() if len(d["lotes"]) > 1
                                     and (o["tipo"], o["opto"], o["interno"]) == (l["tipo"], l["opto"], l["interno"]))
    d["sem_origem"] = (N_FILTROS - sum(len(l["filtros_origem"]) for l in d["lotes"])) if len(d["lotes"]) > 1 else 0
    d["pendencias"] = pendencias(d)
    d["status"] = status(d, d["pendencias"])
    d["numero"] = numero_run(d["cab"].get("run_evaporation"))
    d["visual"] = resumo_visual(d)
    d["estado_imersao"] = estado_imersao(d)
    d["estado_eficiencia"] = estado_eficiencia(d)
    d["decisao"] = decisao_lote(d["estado_imersao"], d["estado_eficiencia"])
    return d
