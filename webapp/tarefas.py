"""Tarefa como formulário (ler do banco / do navegador / de um .json), validação e gravação.

Mesmas regras do programa de mesa: o PID identifica a tarefa, ao menos um lote, massas das posições 2/3/14;
densidades, perdas de massa da imersão e condições da eficiência são calculadas ao gravar; gravar uma tarefa já
revisada apaga a revisão (volta a 'To be reviewed').
"""
import json
import re
import sqlite3
from datetime import datetime

from . import banco, dados, lotes

AMOSTRAS = dados.AMOSTRAS
POSICOES = dados.POSICOES
LIMITE_PERDA_PCT = dados.LIMITE_PERDA_PCT
LIMITE_EFICIENCIA = dados.LIMITE_EFICIENCIA
IDADE_MAX_REFERENCIA_DIAS = 183             # vida máxima do substrato de referência (6 meses)
TIPOS_FILTRO = ("Substrate", "Substrate + dichroic")

# campos de cada filtro da inspeção visual: (nome no formulário, coluna no banco, opções)
CAMPOS_FILTRO = [
    ("visual", "visual_status", ("Pass", "Fail")),
    ("uniformity", "uniformity", ("OK", "Minor", "Major")),
    ("stains", "stains", ("Yes", "No")),
    ("particles", "particles", ("Yes", "No")),
    ("edge", "edge_defects", ("Yes", "No")),
    ("finger", "finger_defects", ("Yes", "No")),
    ("other", "other_defects", ("Yes", "No")),
    ("comments", "comments", None),
    ("classification", "classification", ("A", "B", "C")),
]
CAMPOS_INSPECAO = ("data_inspecao", "operador", "supervisor", "data_revisao", "revisado", "notes")
# imersão: chave no formulário -> coluna em tarefas
CAMPOS_IMERSAO = {"data": "imersao_data", "operador": "imersao_operador", "supervisor": "imersao_supervisor",
                  "data_revisao": "imersao_data_revisao", "revisado": "imersao_revisado", "obs": "imersao_observacoes"}
# eficiência: chave no formulário -> coluna em eficiencia_teste
CAMPOS_EF = {"data_teste": "data_teste", "ref_id": "ref_id", "ref_data": "ref_data", "temp": "temperatura_c",
             "umid": "umidade_pct", "operador": "operador", "supervisor": "supervisor",
             "data_revisao": "data_revisao", "revisado": "revisado", "obs": "observacoes"}
CAMPOS_EF_AMOSTRA = ("testada", "antes", "depois", "area", "x")


def hoje():
    return datetime.today().strftime("%Y-%m-%d")


def _txt(v):
    return "" if v is None else str(v).strip()


# ---------------- cálculos ----------------
def densidade_massa(antes, depois):
    """(massa depois - massa antes)/área do filtro, em µg/cm² com 2 casas; '' se faltar valor."""
    d = dados.densidade(antes, depois)
    return "" if d is None else f"{d:.2f}"


def amostra_imersao(antes, depois):
    """(diferença em g, diferença em %, aprovado) ou None. Aprovado se a perda de massa <= 5 %."""
    a, d = dados.numero(antes), dados.numero(depois)
    if a is None or d is None or a <= 0:
        return None
    dif = d - a
    pct = dif / a * 100.0
    return dif, pct, round(pct, 6) >= -LIMITE_PERDA_PCT


def amostra_eficiencia(r):
    """(diferença de massa, densidade, condição) de uma amostra {testada, antes, depois, area, x}."""
    a, d, area, x = (dados.numero(r.get(k)) for k in ("antes", "depois", "area", "x"))
    dif = d - a if a is not None and d is not None else None
    dens = dif * 1e6 / area if dif is not None and area and area > 0 else None
    if r.get("testada") == "No":
        cond = "Not tested"
    elif x is None:
        cond = ""
    else:
        cond = "Approved" if round(x, 6) >= LIMITE_EFICIENCIA else "Rejected"
    return dif, dens, cond


# ---------------- formulário ----------------
def vazio(responsavel=""):
    """Tarefa nova: data de hoje e o usuário logado como responsável."""
    return {
        "id": None, "lotes": [], "origens": {}, "run": "", "data": hoje(), "pid": "", "pid_p02": "", "pid_p03": "", "pid_p14": "",
        "posicao": "", "responsavel": responsavel, "tipo": "Substrate", "obs": "", "anexos": [],
        "massas": {p: {"antes": "", "depois": ""} for p in POSICOES}, "massa_ptp": "", "lote_ptp": "",
        "insp": {k: "" for k in CAMPOS_INSPECAO},
        "filtros": {n: {c: "" for c, _, _ in CAMPOS_FILTRO} for n in range(1, dados.N_FILTROS + 1)},
        "im": {k: "" for k in CAMPOS_IMERSAO}, "im_massas": {a: {"antes": "", "depois": ""} for a in AMOSTRAS},
        "im_itens": {k: "" for k, *_ in dados.ITENS_IMERSAO},
        "ef": {k: "" for k in CAMPOS_EF}, "ef_amostras": {a: {c: "" for c in CAMPOS_EF_AMOSTRA} for a in AMOSTRAS},
        "signoff": {"por": "", "data": ""},
        "legado": {"eficiencia_ok": "Não", "valor_eficiencia": "", "imersao_ok": "Não"},
    }


def _um(con, sql, params):
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else {}


def de_conexao(con, tarefa_id):
    """Formulário com a tarefa lida da conexão (banco real ou cópia em memória vinda de um .json); None se não existir."""
    con.row_factory = sqlite3.Row
    t = _um(con, "SELECT * FROM tarefas WHERE id = ?", (tarefa_id,))
    if not t:
        return None
    f = vazio()
    f["id"] = tarefa_id
    linhas_lotes = [dict(r) for r in con.execute("SELECT * FROM tarefa_lotes WHERE id_tarefa = ? ORDER BY id", (tarefa_id,))]
    f["lotes"] = lotes.entradas_gravadas(linhas_lotes, t.get("lote_entrada_id"), t.get("codigo_lote"))
    # de onde veio cada filtro (só com mais de um lote): {nº do filtro: índice em f["lotes"]}
    for r in con.execute("SELECT * FROM filtro_origem WHERE id_tarefa = ? ORDER BY filtro", (tarefa_id,)):
        i = next((i for i, e in enumerate(f["lotes"]) if lotes.mesma_origem(dict(r), e)), None)
        if i is not None and r["filtro"] in range(1, dados.N_FILTROS + 1):
            f["origens"][r["filtro"]] = i
    f.update(data=_txt(t.get("data_inicio")), pid=_txt(t.get("codigo_tarefa")), posicao=_txt(t.get("position_range")),
             responsavel=_txt(t.get("responsavel")), obs=_txt(t.get("observacoes")),
             tipo=banco.TIPOS_ANTIGOS.get(t.get("descricao"), t.get("descricao")) or "Substrate",
             massa_ptp=_txt(t.get("massa_ptp_g")), lote_ptp=_txt(t.get("lote_ptp")),
             anexos=[a for a in (t.get("anexos_txt") or "").split(";") if a.strip()])
    for r in con.execute("SELECT * FROM massa_posicoes WHERE id_tarefa = ?", (tarefa_id,)):
        if r["posicao"] in f["massas"]:
            f["massas"][r["posicao"]] = {"antes": _txt(r["massa_antes"]), "depois": _txt(r["massa_depois"])}

    cab = _um(con, "SELECT * FROM inspecao_visual_cab WHERE id_tarefa = ? ORDER BY id LIMIT 1", (tarefa_id,))
    f["run"] = _txt(cab.get("run_evaporation"))
    f["pid"] = f["pid"] or _txt(cab.get("box_pid"))
    for k in ("pid_p02", "pid_p03", "pid_p14"):
        f[k] = _txt(cab.get(k))
    f["insp"] = {k: _txt(cab.get(k)) for k in CAMPOS_INSPECAO}
    for r in con.execute("SELECT * FROM inspecao_visual_filtros WHERE id_tarefa = ?", (tarefa_id,)):
        if r["filtro"] in f["filtros"]:
            f["filtros"][r["filtro"]] = {c: _txt(r[col]) for c, col, _ in CAMPOS_FILTRO}

    f["im"] = {k: _txt(t.get(col)) for k, col in CAMPOS_IMERSAO.items()}
    for r in con.execute("SELECT * FROM imersao_massas WHERE id_tarefa = ?", (tarefa_id,)):
        if r["amostra"] in f["im_massas"]:
            f["im_massas"][r["amostra"]] = {"antes": _txt(r["massa_antes"]), "depois": _txt(r["massa_depois"])}
    for r in con.execute("SELECT item, aprovado FROM imersao_itens WHERE id_tarefa = ?", (tarefa_id,)):
        if r["item"] in f["im_itens"]:
            f["im_itens"][r["item"]] = _txt(r["aprovado"])

    te = _um(con, "SELECT * FROM eficiencia_teste WHERE id_tarefa = ? ORDER BY id LIMIT 1", (tarefa_id,))
    f["ef"] = {k: _txt(te.get(col)) for k, col in CAMPOS_EF.items()}
    for r in con.execute("SELECT * FROM eficiencia_amostras WHERE id_tarefa = ?", (tarefa_id,)):
        if r["amostra"] in f["ef_amostras"]:
            r = dict(r)
            f["ef_amostras"][r["amostra"]] = {"testada": _txt(r["testada"]), "antes": _txt(r["massa_antes"]),
                                              "depois": _txt(r["massa_depois"]), "area": dados.area_amostra_ef(r),
                                              "x": _txt(r["eficiencia"])}
    f["signoff"] = {"por": _txt(t.get("qa_signoff_por")), "data": _txt(t.get("qa_signoff_data"))}
    f["legado"] = {"eficiencia_ok": t.get("eficiencia_optica_ok") or "Não",
                   "valor_eficiencia": _txt(t.get("valor_eficiencia")), "imersao_ok": t.get("imersao_criogenica_ok") or "Não"}
    return f


def ler(tarefa_id):
    con = banco.conectar()
    try:
        return de_conexao(con, tarefa_id)
    finally:
        con.close()


def de_formulario(form):
    """Formulário vindo do navegador (request.form)."""
    g = lambda nome: _txt(form.get(nome))
    f = vazio()
    try:
        f["lotes"] = [l for l in json.loads(form.get("lotes_json") or "[]") if isinstance(l, dict)]
    except ValueError:
        f["lotes"] = []
    try:
        brutas = json.loads(form.get("origens_json") or "{}")
    except ValueError:
        brutas = {}
    indice = {lotes.chave(l): i for i, l in enumerate(f["lotes"])}
    f["origens"] = {int(n): indice[k] for n, k in (brutas.items() if isinstance(brutas, dict) else ())
                    if str(n).isdigit() and 1 <= int(n) <= dados.N_FILTROS and k in indice}
    for k in ("run", "data", "pid", "pid_p02", "pid_p03", "pid_p14", "posicao", "responsavel", "obs",
              "massa_ptp", "lote_ptp"):
        f[k] = g(k)
    f["tipo"] = g("tipo") if g("tipo") in TIPOS_FILTRO else "Substrate"
    f["anexos"] = [a for a in form.getlist("anexo") if a.strip()]
    for p in POSICOES:
        f["massas"][p] = {"antes": g(f"m_antes_{p}"), "depois": g(f"m_depois_{p}")}
    f["insp"] = {k: g("insp_" + k) for k in CAMPOS_INSPECAO}
    for n in f["filtros"]:
        f["filtros"][n] = {c: g(f"f{n}_{c}") for c, _, _ in CAMPOS_FILTRO}
    f["im"] = {k: g("im_" + k) for k in CAMPOS_IMERSAO}
    for a in AMOSTRAS:
        f["im_massas"][a] = {"antes": g(f"im_antes_{a}"), "depois": g(f"im_depois_{a}")}
        f["ef_amostras"][a] = {c: g(f"efa_{a}_{c}") for c in CAMPOS_EF_AMOSTRA}
    for k in f["im_itens"]:
        f["im_itens"][k] = g("im_item_" + k)
    f["ef"] = {k: g("ef_" + k) for k in CAMPOS_EF}
    f["legado"] = {k: g("legado_" + k) for k in f["legado"]}
    f["legado"]["eficiencia_ok"] = f["legado"]["eficiencia_ok"] or "Não"
    f["legado"]["imersao_ok"] = f["legado"]["imersao_ok"] or "Não"
    return f


def validar(f):
    """Erros que impedem gravar (os mesmos do programa de mesa)."""
    erros = []
    if not f["lotes"]:
        erros.append("Select at least one batch.")
    if not f["pid"]:
        erros.append("Enter the PID.")
    for p, nome in POSICOES.items():
        m = f["massas"][p]
        if not m["antes"] or not m["depois"]:
            erros.append(f"Mass control: masses missing at position {p} – {nome}.")
        elif dados.numero(m["antes"]) is None or dados.numero(m["depois"]) is None:
            erros.append(f"Mass control: check the masses at position {p} – use numbers only.")
    return erros


def outras_com_run(f):
    """Outras tarefas com o mesmo número de run (o ID mostrado vem dele)."""
    numero = dados.numero_run(f["run"])
    if not numero:
        return []
    con = banco.conectar()
    try:
        return [r["id_tarefa"] for r in con.execute("SELECT id_tarefa, run_evaporation FROM inspecao_visual_cab")
                if dados.numero_run(r["run_evaporation"]) == numero and r["id_tarefa"] != f["id"]]
    finally:
        con.close()


def revisao_gravada(tarefa_id):
    """(revisado por, data) gravados, ou None se a tarefa não foi revisada."""
    if tarefa_id is None:
        return None
    con = banco.conectar()
    try:
        r = con.execute("SELECT qa_signoff_por, qa_signoff_data FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone()
    finally:
        con.close()
    return (r[0], r[1]) if r and (r[0] or "").strip() else None


# ---------------- gravação ----------------
def _estado_imersao(f):
    d = {"im_massas": {}, "im_itens": f["im_itens"], "tarefa": {"imersao_observacoes": f["im"]["obs"]}}
    for a, m in f["im_massas"].items():
        r = amostra_imersao(m["antes"], m["depois"])
        d["im_massas"][a] = {"aprovado": ("Yes" if r[2] else "No") if r else ""}
    return dados.estado_imersao(d)


def _estado_eficiencia(f):
    d = {"ef_amostras": {a: {"testada": r["testada"], "area_cm2": r["area"], "massa_antes": r["antes"],
                             "massa_depois": r["depois"], "eficiencia": r["x"]} for a, r in f["ef_amostras"].items()}}
    return dados.estado_eficiencia(d)


def gravar(f, tarefa_id=None):
    """Grava a tarefa (nova se tarefa_id for None) numa transação só. Retorna o id."""
    for r in f["ef_amostras"].values():          # eficiência digitada sem responder "Tested?": amostra testada
        if not r["testada"] and r["x"]:
            r["testada"] = "Yes"
    lotes_sel = f["lotes"]
    codigo_lote = "; ".join(str(l.get("codigo_lote")) + (f" ({l['codigo_interno']})" if l.get("codigo_interno") else "")
                            for l in lotes_sel if l.get("codigo_lote"))

    # resumo antigo da tabela tarefas (Sim/Não): calculado dos testes; sem dados novos, mantém o valor antigo
    est_im, est_ef = _estado_imersao(f), _estado_eficiencia(f)
    imersao_ok = f["legado"]["imersao_ok"] if est_im == "empty" else ("Sim" if est_im == "approved" else "Não")
    if est_ef == "empty":
        eficiencia_ok, valor_ef = f["legado"]["eficiencia_ok"], f["legado"]["valor_eficiencia"]
    else:
        eficiencia_ok = "Sim" if est_ef == "approved" else "Não"
        valor_ef = "; ".join(f"{a}: {r['x']}" for a, r in f["ef_amostras"].items()
                             if amostra_eficiencia(r)[2] in ("Approved", "Rejected"))

    valores = {
        "codigo_tarefa": f["pid"], "responsavel": f["responsavel"], "data_inicio": f["data"], "descricao": f["tipo"],
        "lote_entrada_id": lotes_sel[0].get("lote_id") if lotes_sel else None, "codigo_lote": codigo_lote,
        "position_range": f["posicao"], "observacoes": f["obs"], "anexos_txt": ";".join(f["anexos"]),
        "eficiencia_optica_ok": eficiencia_ok, "valor_eficiencia": valor_ef, "imersao_criogenica_ok": imersao_ok,
        "data_hora_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "massa_ptp_g": f["massa_ptp"],
        "lote_ptp": f["lote_ptp"], "qa_signoff_por": f["signoff"]["por"], "qa_signoff_data": f["signoff"]["data"],
        **{col: f["im"][k] for k, col in CAMPOS_IMERSAO.items()},
    }
    con = banco.conectar()
    try:
        cur = con.cursor()
        if tarefa_id is None:
            valores["status"] = dados.STATUS_INCOMPLETO
            cur.execute(f"INSERT INTO tarefas ({', '.join(valores)}) VALUES ({', '.join('?' * len(valores))})",
                        tuple(valores.values()))
            tarefa_id = cur.lastrowid
        else:
            cur.execute(f"UPDATE tarefas SET {', '.join(k + ' = ?' for k in valores)} WHERE id = ?",
                        (*valores.values(), tarefa_id))
        for tabela in ("tarefa_lotes", "filtro_origem", "massa_posicoes", "inspecao_visual_cab", "inspecao_visual_filtros",
                       "imersao_massas", "imersao_itens", "eficiencia_teste", "eficiencia_amostras"):
            cur.execute(f"DELETE FROM {tabela} WHERE id_tarefa = ?", (tarefa_id,))

        for l in lotes_sel:
            cur.execute("INSERT INTO tarefa_lotes (id_tarefa, lote_id, codigo_lote, lote_interno_id, codigo_lote_interno, "
                        "tipo_lote) VALUES (?, ?, ?, ?, ?, ?)",
                        (tarefa_id, l.get("lote_id"), l.get("codigo_lote"), l.get("interno_id"),
                         l.get("codigo_interno") or None, "limpeza" if l.get("tipo") == "limpeza" else "opto"))
        if len(lotes_sel) > 1:            # com um lote só, todos os filtros vêm dele
            for n, i in sorted(f["origens"].items()):
                l = lotes_sel[i]
                cur.execute("INSERT INTO filtro_origem (id_tarefa, filtro, tipo_lote, lote_id, codigo_lote, lote_interno_id, "
                            "codigo_lote_interno) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (tarefa_id, n, "limpeza" if l.get("tipo") == "limpeza" else "opto", l.get("lote_id"),
                             l.get("codigo_lote"), l.get("interno_id"), l.get("codigo_interno") or None))
        for p, m in f["massas"].items():
            cur.execute("INSERT INTO massa_posicoes (id_tarefa, posicao, massa_antes, massa_depois, densidade_massa_ug_cm2) "
                        "VALUES (?, ?, ?, ?, ?)", (tarefa_id, p, m["antes"], m["depois"], densidade_massa(m["antes"], m["depois"])))

        i = f["insp"]
        cur.execute("""INSERT INTO inspecao_visual_cab (id_tarefa, box_pid, run_evaporation, inspector, pid_p02, pid_p03,
                       pid_p14, notes, data_inspecao, operador, supervisor, data_revisao, revisado)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tarefa_id, f["pid"], f["run"], f["responsavel"], f["pid_p02"], f["pid_p03"], f["pid_p14"],
                     i["notes"], i["data_inspecao"], i["operador"], i["supervisor"], i["data_revisao"], i["revisado"]))
        for n, v in f["filtros"].items():
            cur.execute(f"""INSERT INTO inspecao_visual_filtros (id_tarefa, filtro, {', '.join(col for _, col, _ in CAMPOS_FILTRO)})
                            VALUES (?, ?, {', '.join('?' * len(CAMPOS_FILTRO))})""",
                        (tarefa_id, n, *[v[c] for c, _, _ in CAMPOS_FILTRO]))

        for a, m in f["im_massas"].items():
            r = amostra_imersao(m["antes"], m["depois"])
            dif_g, dif_pct, aprovado = (f"{r[0]:.5f}", f"{r[1]:.2f}", "Yes" if r[2] else "No") if r else ("", "", "")
            cur.execute("INSERT INTO imersao_massas (id_tarefa, amostra, massa_antes, massa_depois, diferenca_g, "
                        "diferenca_pct, aprovado) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (tarefa_id, a, m["antes"], m["depois"], dif_g, dif_pct, aprovado))
        for k, v in f["im_itens"].items():
            cur.execute("INSERT INTO imersao_itens (id_tarefa, item, aprovado) VALUES (?, ?, ?)", (tarefa_id, k, v))

        cur.execute(f"INSERT INTO eficiencia_teste (id_tarefa, {', '.join(CAMPOS_EF.values())}) "
                    f"VALUES (?, {', '.join('?' * len(CAMPOS_EF))})", (tarefa_id, *[f["ef"][k] for k in CAMPOS_EF]))
        for a, r in f["ef_amostras"].items():
            _, dens, cond = amostra_eficiencia(r)
            cur.execute("""INSERT INTO eficiencia_amostras (id_tarefa, amostra, testada, comprimento_mm, largura_mm,
                           massa_antes, massa_depois, area_cm2, densidade_ug_cm2, eficiencia, aprovado)
                           VALUES (?, ?, ?, '', '', ?, ?, ?, ?, ?, ?)""",
                        (tarefa_id, a, r["testada"], r["antes"], r["depois"], r["area"],
                         "" if dens is None else f"{dens:.2f}", r["x"], {"Approved": "Yes", "Rejected": "No"}.get(cond, "")))
        con.commit()
    finally:
        con.close()
    return tarefa_id


def atualizar_status(tarefa_id):
    """Recalcula e grava a situação da tarefa. Retorna (status, pendências)."""
    d = dados.ler_tarefa(tarefa_id)
    if d is None:
        return None, []
    if d["tarefa"].get("status") != d["status"]:
        con = banco.conectar()
        try:
            con.execute("UPDATE tarefas SET status = ? WHERE id = ?", (d["status"], tarefa_id))
            con.commit()
        finally:
            con.close()
    return d["status"], d["pendencias"]


def excluir(tarefa_id):
    """Apaga a tarefa e tudo ligado a ela. Retorna o PID apagado (None se não existia)."""
    con = banco.conectar()
    try:
        r = con.execute("SELECT codigo_tarefa FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone()
        if r is None:
            return None
        for tabela in TABELAS_TAREFA:
            con.execute(f"DELETE FROM {tabela} WHERE id_tarefa = ?", (tarefa_id,))
        con.execute("DELETE FROM tarefas WHERE id = ?", (tarefa_id,))
        con.commit()
        return r[0] or ""
    finally:
        con.close()


def marcar_revisada(tarefa_id, nome):
    """QA sign-off (nome e data de hoje): a tarefa passa a Completed."""
    con = banco.conectar()
    try:
        con.execute("UPDATE tarefas SET qa_signoff_por = ?, qa_signoff_data = ?, status = ? WHERE id = ?",
                    (nome, hoje(), dados.STATUS_COMPLETO, tarefa_id))
        con.commit()
    finally:
        con.close()


def limpar_revisao(tarefa_id):
    con = banco.conectar()
    try:
        con.execute("UPDATE tarefas SET qa_signoff_por = '', qa_signoff_data = '' WHERE id = ?", (tarefa_id,))
        con.commit()
    finally:
        con.close()


# ---------------- exportar / importar (.json) ----------------
FORMATO_JSON = "leptons-deposition-task"
# tabelas ligadas à tarefa por id_tarefa (a linha da própria tarefa fica em "task")
TABELAS_TAREFA = ["tarefa_lotes", "filtro_origem", "massa_posicoes", "inspecao_visual_cab", "inspecao_visual_filtros",
                  "imersao_massas", "imersao_itens", "eficiencia_teste", "eficiencia_amostras"]


def nome_arquivo(texto):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(texto or "sample"))


def exportar_json(tarefa_id, exportado_por):
    """Tudo o que o banco tem da tarefa, no mesmo formato do programa de mesa (pode ser importado de volta)."""
    con = banco.conectar()
    try:
        t = con.execute("SELECT * FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone()
        if t is None:
            return None
        return {
            "format": FORMATO_JSON, "version": 1, "pid": t["codigo_tarefa"],
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "exported_by": exportado_por,
            "source_task_id": tarefa_id,
            "task": {k: t[k] for k in t.keys() if k != "id"},
            "tables": {tab: [{k: r[k] for k in r.keys() if k not in ("id", "id_tarefa")}
                             for r in con.execute(f"SELECT * FROM {tab} WHERE id_tarefa = ? ORDER BY id", (tarefa_id,))]
                       for tab in TABELAS_TAREFA},
        }
    finally:
        con.close()


def ler_json(texto):
    """Confere o arquivo exportado. Retorna o dict ou levanta ValueError."""
    try:
        d = json.loads(texto)
    except ValueError as e:
        raise ValueError("The file is not valid JSON: " + str(e))
    if not isinstance(d, dict) or d.get("format") != FORMATO_JSON or not isinstance(d.get("task"), dict):
        raise ValueError("This file is not a sample exported by the Deposition Control System.")
    return d


def tarefas_com_pid(pid):
    if not pid:
        return []
    con = banco.conectar()
    try:
        return [r[0] for r in con.execute("SELECT id FROM tarefas WHERE codigo_tarefa = ? ORDER BY id", (pid,))]
    finally:
        con.close()


def formulario_do_json(d):
    """Formulário com a tarefa do arquivo (cópia em memória com o mesmo formato do banco). Os IDs dos lotes mudam
    entre computadores: os lotes são achados pelos códigos."""
    con = banco.conectar()
    try:
        esquema = {r[0]: r[1] for r in con.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'")}
    finally:
        con.close()
    mem = sqlite3.connect(":memory:")
    try:
        def inserir(tab, linha):
            colunas = [c[1] for c in mem.execute(f"PRAGMA table_info({tab})")]
            linha = {k: v for k, v in linha.items() if k in colunas and k != "id"}
            if linha:
                mem.execute(f"INSERT INTO {tab} ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
                            tuple(linha.values()))
            else:
                mem.execute(f"INSERT INTO {tab} DEFAULT VALUES")

        for tab in ["tarefas"] + TABELAS_TAREFA:
            mem.execute(esquema[tab])
        inserir("tarefas", dict(d["task"], lote_entrada_id=None))
        for tab in TABELAS_TAREFA:
            for linha in (d.get("tables") or {}).get(tab) or []:
                linha = dict(linha, id_tarefa=1)
                if tab in ("tarefa_lotes", "filtro_origem"):
                    linha.update(lote_id=None, lote_interno_id=None)
                inserir(tab, linha)
        f = de_conexao(mem, 1)
    finally:
        mem.close()
    if f is None:
        raise ValueError("The file has no sample data.")
    f["id"] = None
    return f


def lotes_ausentes(d):
    """Códigos de lotes do arquivo que não existem no cadastro de lotes deste computador."""
    todos = {l["lote"] for l in lotes.opto()}
    ausentes = []
    for l in (d.get("tables") or {}).get("tarefa_lotes") or []:
        codigo, interno = l.get("codigo_lote"), l.get("codigo_lote_interno")
        if l.get("tipo_lote") == "limpeza":
            if interno and lotes.limpeza(None, interno) is None:
                ausentes.append(interno)
            continue
        if codigo and codigo not in todos:
            ausentes.append(codigo)
        if interno and lotes.interno(None, interno) is None:
            ausentes.append(interno)
    return list(dict.fromkeys(ausentes))
