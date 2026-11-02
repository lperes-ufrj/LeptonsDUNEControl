"""Lotes do programa de chegada de lotes (lotes.db, só leitura) e os lotes escolhidos em cada deposição.

Uma entrada da deposição é um dict:
  tipo ('opto' ou 'limpeza'), lote_id, codigo_lote (lote OPTO; 'Leptons cleaning' para limpeza),
  interno_id, codigo_interno (ex.: DUNE-CX-0004 ou o código do lote de limpeza), chegada, empresa, filtros.
"""
import sqlite3

from . import dados

LIMPEZA = "Leptons cleaning"


def _conectar():
    if not dados.DB_LOTES.exists():
        return None
    return dados._conectar(dados.DB_LOTES)


def opto():
    """Lotes OPTO (mais recentes primeiro), com os nomes de coluna das várias versões do programa de lotes."""
    con = _conectar()
    if con is None:
        return []
    try:
        cols = {c[1].lower(): c[1] for c in con.execute("PRAGMA table_info(lotes)")}

        def col(*nomes):
            return next((cols[n.lower()] for n in nomes if n.lower() in cols), None)

        mapa = {
            "id": col("id"),
            "lote": col("lote_geral", "lote", "batch", "internal_lab_batch", "lote_interno", "general_batch",
                        "tracking_id"),
            "chegada": col("data_recebimento", "data", "arrival_date", "data_chegada", "receiving_date", "date",
                           "data_hora_registro"),
            "empresa": col("Fornecedor", "fornecedor", "supplier", "producer", "company"),
            "tracking": col("tracking_id", "tracking", "codigo_rastreio"),
            "lote_empresa": col("lote_fornecedor", "supplier_batch", "company_batch", "opto_batch", "lote_empresa"),
            "filtros": col("total_filtros", "total_filters", "Quantidade", "quantidade", "quantity",
                           "quantity_received"),
            "caixas": col("numero_caixas_menores", "small_boxes", "number_of_small_boxes", "caixas_menores",
                          "small_boxes_count", "box_quantity"),
            "inspecao": col("resultado_inspecao", "inspection_result", "status_inspecao", "inspection_status"),
            "arquivo": col("arquivo_controle", "control_file", "supplier_control_file"),
        }
        sql = "SELECT " + ", ".join(f'"{real}" AS "{alias}"' if real else f'NULL AS "{alias}"'
                                    for alias, real in mapa.items()) + " FROM lotes"
        ordem = mapa["id"] or mapa["chegada"]
        if ordem:
            sql += f' ORDER BY "{ordem}" DESC'
        return [dict(r) for r in con.execute(sql)]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def _sql_internos():
    return "SELECT id, numero_caixa AS caixa, codigo_interno AS codigo, quantidade_filtros AS filtros, " \
           "observacoes AS obs, id_lote FROM lotes_internos"


def internos(id_lote):
    """Lotes internos (um por caixa menor, ex.: DUNE-CX-0004) de um lote OPTO."""
    con = _conectar()
    if con is None or id_lote is None:
        return []
    try:
        return [dict(r) for r in con.execute(_sql_internos() + " WHERE id_lote = ? ORDER BY numero_caixa",
                                             (id_lote,))]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def interno(interno_id, codigo, id_lote=None):
    """Um lote interno pelo ID (ou, se não achar, pelo código dentro do lote OPTO). None se não existir."""
    con = _conectar()
    if con is None:
        return None
    try:
        r = None
        if interno_id is not None:
            r = con.execute(_sql_internos() + " WHERE id = ?", (interno_id,)).fetchone()
        if r is None and codigo:
            if id_lote is not None:
                r = con.execute(_sql_internos() + " WHERE codigo_interno = ? AND id_lote = ?", (codigo, id_lote)).fetchone()
            else:
                r = con.execute(_sql_internos() + " WHERE codigo_interno = ?", (codigo,)).fetchone()
        return dict(r) if r else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


_SQL_LIMPEZA = ("SELECT id, codigo_interno AS codigo, data_limpeza AS data, responsavel, quantidade_filtros AS filtros, "
                "origem, remocao_ptp AS ptp, procedimento AS proc, resultado, observacoes AS obs FROM lotes_limpeza")


def limpezas():
    """Lotes de limpeza do Leptons (material que passou por remoção de PTP e nova limpeza), mais recentes primeiro."""
    con = _conectar()
    if con is None:
        return []
    try:
        return [dict(r) for r in con.execute(_SQL_LIMPEZA + " ORDER BY id DESC")]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def limpeza(limpeza_id, codigo):
    con = _conectar()
    if con is None:
        return None
    try:
        r = None
        if limpeza_id is not None:
            r = con.execute(_SQL_LIMPEZA + " WHERE id = ?", (limpeza_id,)).fetchone()
        if r is None and codigo:
            r = con.execute(_SQL_LIMPEZA + " WHERE codigo_interno = ?", (codigo,)).fetchone()
        return dict(r) if r else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def inteiro(valor):
    try:
        return int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        return None


# ---------------- entradas da deposição ----------------
def entrada_opto(lote, int_=None):
    """Entrada para um lote OPTO (dict de opto()) e, se houver, um lote interno (dict de internos())."""
    filtros = int_["filtros"] if int_ and int_.get("filtros") not in (None, "") else lote.get("filtros")
    return {"tipo": "opto", "lote_id": lote.get("id"), "codigo_lote": lote.get("lote") or "",
            "interno_id": int_["id"] if int_ else None, "codigo_interno": (int_ or {}).get("codigo") or "",
            "chegada": lote.get("chegada") or "", "empresa": lote.get("empresa") or "", "filtros": inteiro(filtros)}


def entrada_limpeza(limp):
    return {"tipo": "limpeza", "lote_id": None, "codigo_lote": LIMPEZA, "interno_id": limp.get("id"),
            "codigo_interno": limp.get("codigo") or "", "chegada": limp.get("data") or "", "empresa": "Leptons Lab",
            "filtros": inteiro(limp.get("filtros"))}


def entradas_gravadas(linhas, lote_id_legado=None, codigo_legado=None):
    """Entradas de linhas de tarefa_lotes (dicts), com os dados atuais do cadastro de lotes.
    Registros antigos têm um lote só, na própria tarefa; lotes removidos do cadastro mantêm o código gravado."""
    if not linhas and (lote_id_legado is not None or codigo_legado):
        linhas = [{"lote_id": lote_id_legado, "codigo_lote": codigo_legado, "lote_interno_id": None,
                   "codigo_lote_interno": None, "tipo_lote": "opto"}]
    todos = opto()
    resultado = []
    for l in linhas:
        lid, cod, iid, icod = l.get("lote_id"), l.get("codigo_lote"), l.get("lote_interno_id"), l.get("codigo_lote_interno")
        if l.get("tipo_lote") == "limpeza":
            limp = limpeza(iid, icod) or {"id": iid, "codigo": icod}
            resultado.append(entrada_limpeza(limp))
            continue
        lote = next((x for x in todos if (lid is not None and x["id"] == lid) or (cod and x["lote"] == cod)), None)
        lote = lote or {"id": lid, "lote": cod}
        int_ = None
        if iid is not None or icod:
            int_ = interno(iid, icod, lote.get("id")) or {"id": iid, "codigo": icod, "filtros": None}
        resultado.append(entrada_opto(lote, int_))
    return resultado


def pids_que_usaram(con_tarefas, interno_id, ignorar_tarefa=None, tipo="opto"):
    """PIDs das deposições que já usaram este lote interno (ou lote de limpeza, com tipo='limpeza')."""
    if interno_id is None:
        return []
    return [str(r[0]) for r in con_tarefas.execute("""
        SELECT DISTINCT t.codigo_tarefa FROM tarefa_lotes tl JOIN tarefas t ON t.id = tl.id_tarefa
        WHERE tl.lote_interno_id = ? AND COALESCE(tl.tipo_lote, 'opto') = ? AND (? IS NULL OR tl.id_tarefa != ?)
    """, (interno_id, tipo, ignorar_tarefa, ignorar_tarefa)) if r[0]]


def catalogo(ignorar_tarefa=None):
    """Tudo o que a janela 'Add batch / internal lot' precisa: lotes OPTO com os lotes internos e os lotes
    de limpeza, cada um com os PIDs que já o usaram (fora a tarefa aberta)."""
    con = dados._conectar(dados.DB_TAREFAS)
    try:
        lista = []
        for lote in opto():
            ints = internos(lote["id"])
            for i in ints:
                i["usado"] = pids_que_usaram(con, i["id"], ignorar_tarefa)
                i["entrada"] = entrada_opto(lote, i)
            lista.append(dict(lote, internos=ints, entrada=entrada_opto(lote)))
        limps = limpezas()
        for l in limps:
            l["usado"] = pids_que_usaram(con, l["id"], ignorar_tarefa, "limpeza")
            l["entrada"] = entrada_limpeza(l)
    finally:
        con.close()
    return {"opto": lista, "limpeza": limps}
