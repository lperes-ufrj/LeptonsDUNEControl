"""Filtros retirados de uma sample na inspeção visual (classe A ou B): descartados ou mandados para limpeza.

Cada linha de filtro_retirado acompanha um filtro físico:
  sample de origem + posição (id_tarefa, filtro) -> descartado, ou aguardando limpeza -> lote de limpeza
  (limpeza_id, codigo_limpeza; o lote fica em lotes_limpeza) -> posição de uma nova sample (usado_tarefa_id, usado_filtro).
A posição de origem fica vazia (a inspeção dela continua gravada). A linha guarda o PID e a run copiados
(origem_pid, origem_run), que continuam valendo se a sample for apagada depois que o filtro entrou num lote.
"""
from datetime import datetime

from . import dados, db
from .i18n import t

DESCARTE, LIMPEZA = "Discarded", "Cleaning"
CLASSES_RETIRAVEIS = ("A", "B")

_SQL = """
    SELECT r.*, (SELECT codigo_tarefa FROM tarefas WHERE id = r.id_tarefa) AS pid_atual,
           (SELECT run_evaporation FROM inspecao_visual_cab WHERE id_tarefa = r.id_tarefa ORDER BY id LIMIT 1) AS run_atual,
           (SELECT codigo_tarefa FROM tarefas WHERE id = r.usado_tarefa_id) AS usado_pid,
           (SELECT run_evaporation FROM inspecao_visual_cab WHERE id_tarefa = r.usado_tarefa_id ORDER BY id LIMIT 1) AS usado_run_ev,
           EXISTS (SELECT 1 FROM tarefas WHERE id = r.id_tarefa) AS existe
    FROM filtro_retirado r"""


def _linha(r):
    r = dict(r)
    r["run"] = dados.numero_run(r.pop("run_atual")) or r["origem_run"] or ""
    r["pid"] = r.pop("pid_atual") or r["origem_pid"] or ""
    r["usado_run"] = dados.numero_run(r.pop("usado_run_ev")) if r["usado_tarefa_id"] else ""
    if r["destino"] == DESCARTE:
        r["situacao"] = "descartado"
    elif r["usado_tarefa_id"]:
        r["situacao"] = "reusado"
    elif r["limpeza_id"] is not None:
        r["situacao"] = "no_lote"
    else:
        r["situacao"] = "aguardando"
    r["rotulo"] = t("Run {run} · filter {n}", run=r["run"] or "–", n=r["filtro"])
    return r


def _listar(onde="", params=(), con=None):
    proprio = con is None
    con = con or db.conectar()
    try:
        return [_linha(r) for r in con.execute(_SQL + " " + onde, params)]
    finally:
        if proprio:
            con.close()


def ordem(r):
    return r["run"] == "", int(r["run"] or 0), r["filtro"]


def da_amostra(tarefa_id):
    """{posição: linha} dos filtros retirados desta sample."""
    return {r["filtro"]: r for r in _listar("WHERE r.id_tarefa = ?", (tarefa_id,))}


def reusados(tarefa_id):
    """{posição: linha} dos filtros limpos que esta sample recebeu."""
    return {r["usado_filtro"]: r for r in _listar("WHERE r.usado_tarefa_id = ?", (tarefa_id,))}


def aguardando():
    return sorted(_listar("WHERE r.destino = ? AND r.limpeza_id IS NULL", (LIMPEZA,)), key=ordem)


def descartados():
    return sorted(_listar("WHERE r.destino = ?", (DESCARTE,)), key=ordem)


def da_limpeza(limpeza_id):
    return sorted(_listar("WHERE r.limpeza_id = ?", (limpeza_id,)), key=ordem)


def por_limpeza():
    """{id do lote de limpeza: [linhas]} de todos os lotes."""
    saida = {}
    for r in _listar("WHERE r.limpeza_id IS NOT NULL"):
        saida.setdefault(r["limpeza_id"], []).append(r)
    return {k: sorted(v, key=ordem) for k, v in saida.items()}


def um(retirado_id):
    linhas = _listar("WHERE r.id = ?", (retirado_id,))
    return linhas[0] if linhas else None


def rotulo_auditoria(r):
    """Rótulo do filtro para a auditoria (sempre em inglês)."""
    return f"Run {r['run'] or '-'}/filter {r['filtro']}"


def lista_auditoria(ids):
    return ", ".join(rotulo_auditoria(r) for r in sorted(filter(None, map(um, ids)), key=ordem)) or "-"


def mudancas_reuso(antes, depois):
    """Texto (inglês) do que mudou nos filtros limpos de uma sample: posição <- filtro (lote), posições soltas."""
    partes = []
    for n in sorted(set(antes) | set(depois)):
        if antes.get(n) == depois.get(n):
            continue
        r = um(depois[n]) if n in depois else None
        if r:
            partes.append(f"slot {n} <- {rotulo_auditoria(r)} ({r['codigo_limpeza'] or 'cleaning lot'})")
        else:
            partes.append(f"slot {n} released")
    return "; ".join(partes)


# ---------------- retirar / desfazer (página da sample) ----------------
def retirar(d, filtro, destino, obs, usuario):
    """Retira o filtro da sample d (dados.ler_tarefa). Retorna (linha gravada, erro)."""
    if destino not in (DESCARTE, LIMPEZA):
        return None, t("Choose Discard or Send to cleaning.")
    if filtro not in range(1, dados.N_FILTROS + 1):
        return None, t("Filter {n} does not exist.", n=filtro)
    classe = (d["filtros"].get(filtro) or {}).get("classification") or ""
    if classe not in CLASSES_RETIRAVEIS:
        return None, t("Only filters classified A or B can be removed (filter {n} is {classe}).", n=filtro, classe=classe or "–")
    con = db.conectar()
    try:
        if con.execute("SELECT 1 FROM filtro_retirado WHERE id_tarefa = ? AND filtro = ?", (d["id"], filtro)).fetchone():
            return None, t("Filter {n} was already removed from this sample.", n=filtro)
        with con:
            cur = con.execute("""INSERT INTO filtro_retirado (id_tarefa, filtro, classe, destino, observacao, data_hora,
                                 usuario, origem_pid, origem_run) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (d["id"], filtro, classe, destino, obs, datetime.now().strftime("%Y-%m-%d %H:%M"), usuario,
                               d["tarefa"].get("codigo_tarefa") or "", d["numero"] or ""))
        return _listar("WHERE r.id = ?", (cur.lastrowid,), con)[0], None
    finally:
        con.close()


def desfazer(retirado_id):
    """Põe o filtro de volta na sample (só antes de entrar num lote de limpeza). Retorna (linha apagada, erro)."""
    r = um(retirado_id)
    if r is None:
        return None, t("This removed filter no longer exists.")
    if r["limpeza_id"] is not None:
        return r, t("Filter {rotulo} is already in cleaning lot {codigo}: remove it from the lot first.",
                    rotulo=r["rotulo"], codigo=r["codigo_limpeza"] or "?")
    con = db.conectar()
    try:
        with con:
            con.execute("DELETE FROM filtro_retirado WHERE id = ?", (retirado_id,))
    finally:
        con.close()
    return r, None


# ---------------- lotes de limpeza (aba Cleaning) ----------------
def validar_limpeza(limpeza_id, ids):
    """Os filtros marcados para o lote: só os que aguardam limpeza ou que já estão nele. Retorna o erro ou None."""
    for i in ids:
        r = um(i)
        if r is None or r["destino"] != LIMPEZA or (r["limpeza_id"] is not None and r["limpeza_id"] != limpeza_id):
            return t("A chosen filter is no longer waiting for cleaning (it was put back or went to another lot). "
                     "Reload the page and choose again.")
    return None


def definir_limpeza(limpeza_id, codigo, ids):
    """O lote passa a ter os filtros ids; os que saíram (e não foram usados) voltam a aguardar limpeza.
    Retorna (ids que entraram, ids que saíram)."""
    ids = set(ids)
    con = db.conectar()
    try:
        atuais = {r["id"]: r for r in _listar("WHERE r.limpeza_id = ?", (limpeza_id,), con)}
        saem = [i for i, r in atuais.items() if i not in ids and not r["usado_tarefa_id"]]
        entram = [i for i in ids if i not in atuais]
        with con:
            for i in saem:
                con.execute("UPDATE filtro_retirado SET limpeza_id = NULL, codigo_limpeza = NULL WHERE id = ?", (i,))
            for i in entram:
                con.execute("UPDATE filtro_retirado SET limpeza_id = ? WHERE id = ? AND destino = ? AND limpeza_id IS NULL",
                            (limpeza_id, i, LIMPEZA))
            con.execute("UPDATE filtro_retirado SET codigo_limpeza = ? WHERE limpeza_id = ?", (codigo, limpeza_id))
        return entram, saem
    finally:
        con.close()


def soltar_limpeza(limpeza_id):
    """Lote de limpeza apagado: os filtros ainda não usados voltam a aguardar limpeza (os usados guardam o código)."""
    con = db.conectar()
    try:
        with con:
            return con.execute("UPDATE filtro_retirado SET limpeza_id = NULL, codigo_limpeza = NULL "
                               "WHERE limpeza_id = ? AND usado_tarefa_id IS NULL", (limpeza_id,)).rowcount
    finally:
        con.close()


def origem_texto(linhas):
    """'Run 12 (filters 3, 7); Run 14 (filter 1)' para o campo Origin do lote de limpeza."""
    from .lotes import faixas
    por_run = {}
    for r in sorted(linhas, key=ordem):
        por_run.setdefault(r["run"] or "–", []).append(r["filtro"])
    return "; ".join(f"Run {run} (filter{'s' if len(ns) > 1 else ''} {faixas(ns)})" for run, ns in por_run.items())


# ---------------- filtros limpos numa nova sample (formulário) ----------------
def disponiveis(tarefa_id=None):
    """{id do lote de limpeza: [{id, rotulo, classe}]}: filtros limpos ainda não usados (ou usados por esta sample)."""
    saida = {}
    for r in sorted(_listar("WHERE r.limpeza_id IS NOT NULL AND (r.usado_tarefa_id IS NULL OR r.usado_tarefa_id <=> ?)",
                            (tarefa_id,)), key=ordem):
        saida.setdefault(r["limpeza_id"], []).append({"id": r["id"], "rotulo": r["rotulo"], "classe": r["classe"]})
    return saida


def lote_da_posicao(f, n):
    """A entrada (f["lotes"]) de onde veio a posição n: o único lote, ou o escolhido na janela Filter origin."""
    if len(f["lotes"]) == 1:
        return f["lotes"][0]
    i = f["origens"].get(n)
    return f["lotes"][i] if i is not None else None


def validar_reuso(f, tarefa_id):
    """Fica só com as posições que vêm de um lote de limpeza e com filtros limpos desse lote, livres e sem repetir.
    Retorna (reuso válido, avisos)."""
    livres = {p["id"]: lid for lid, ps in disponiveis(tarefa_id).items() for p in ps}
    valido, vistos, avisos = {}, set(), []
    for n, rid in sorted(f["reuso"].items()):
        e = lote_da_posicao(f, n)
        if not e or e.get("tipo") != "limpeza" or rid in vistos:
            continue
        if livres.get(rid) != e.get("interno_id"):
            avisos.append(t("Filter {n}: the chosen cleaned filter is no longer available in {codigo} – choose another one.",
                            n=n, codigo=e.get("codigo_interno") or "?"))
            continue
        valido[n] = rid
        vistos.add(rid)
    # posições de um lote de limpeza com filtros controlados, mas sem o filtro limpo escolhido
    controlados = por_limpeza()
    for e in f["lotes"]:
        if e.get("tipo") != "limpeza" or e.get("interno_id") not in controlados:
            continue
        sem = [n for n in range(1, dados.N_FILTROS + 1) if lote_da_posicao(f, n) is e and n not in valido]
        if sem:
            avisos.append(t("{n} filter(s) from cleaning lot {codigo} have no cleaned filter chosen – use "
                            "Edit sample › Cleaned filters…", n=len(sem), codigo=e.get("codigo_interno") or "?"))
    return valido, avisos


def gravar_reuso(cur, tarefa_id, reuso):
    """Dentro da gravação da sample (mesma conexão): solta os filtros que ela tinha e grava os escolhidos."""
    cur.execute("UPDATE filtro_retirado SET usado_tarefa_id = NULL, usado_filtro = NULL WHERE usado_tarefa_id = ?", (tarefa_id,))
    for n, rid in reuso.items():
        cur.execute("UPDATE filtro_retirado SET usado_tarefa_id = ?, usado_filtro = ? WHERE id = ? AND usado_tarefa_id IS NULL",
                    (tarefa_id, n, rid))


def ao_excluir_amostra(cur, tarefa_id):
    """Sample apagada: os filtros limpos que ela usava ficam livres de novo; os que ela retirou e ainda não entraram
    num lote de limpeza somem (os que já estão num lote continuam lá, com o PID e a run copiados)."""
    cur.execute("UPDATE filtro_retirado SET usado_tarefa_id = NULL, usado_filtro = NULL WHERE usado_tarefa_id = ?", (tarefa_id,))
    cur.execute("DELETE FROM filtro_retirado WHERE id_tarefa = ? AND limpeza_id IS NULL", (tarefa_id,))


def nota(r, para="origem"):
    """Texto curto (em inglês, para relatório e PDF) da situação de um filtro retirado ou recebido."""
    if para == "destino":
        return f"Cleaned filter from Run {r['run'] or '-'} · filter {r['filtro']} ({r['codigo_limpeza'] or 'cleaning lot'})"
    if r["situacao"] == "descartado":
        return f"REMOVED – discarded ({r['data_hora'][:10]})"
    if r["situacao"] == "aguardando":
        return f"REMOVED – waiting for cleaning ({r['data_hora'][:10]})"
    texto = f"REMOVED – cleaning lot {r['codigo_limpeza'] or '?'}"
    return texto + (f", reused in Run {r['usado_run'] or '-'} · filter {r['usado_filtro']}" if r["usado_tarefa_id"] else "")
