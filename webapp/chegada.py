"""Cadastro de lotes no navegador: o mesmo do programa de chegada de lotes (controle_lotes v13), no mesmo lotes.db.

Lote OPTO (lote geral) com as caixas menores, cada uma registrada como lote interno DUNE-CX-000X, e os lotes de
limpeza do Leptons (DUNE-LP-000X). Mesmas tabelas, regras, códigos de auditoria e PDFs do programa de mesa.
"""
import csv
import io
import re
from datetime import datetime

from PIL import Image, ImageChops

from . import banco, dados, pdf
from .i18n import t

PREFIXO_CAIXA = "DUNE-CX-"            # caixas menores (lotes internos): DUNE-CX-0001, DUNE-CX-0002, ...
PREFIXO_LIMPEZA = "DUNE-LP-"          # lotes de limpeza realizada no Leptons
DIGITOS_CAIXA = 4
CAPACIDADE_PADRAO = 28                # filtros por caixa menor
ACABAMENTOS = ["Raw", "Lapped", "Polished", "Other"]
RESULTADOS = ["Approved", "Approved with observations", "Rejected", "Under inspection"]
RESULTADOS_LIMPEZA = RESULTADOS
PASTA_ARQUIVOS = dados.PASTA / "arquivos_lotes"     # arquivos de controle do fornecedor enviados pelo navegador

CAMPOS_LOTE = ("lote_geral", "lote_fornecedor", "data_recebimento", "responsavel", "fornecedor", "total_filtros",
               "numero_caixas_menores", "capacidade_caixa_menor", "material", "dimensoes", "espessura",
               "tipo_acabamento", "filtros_quebrados", "quantidade_confere", "procedimento_limpeza",
               "resultado_inspecao", "arquivo_controle", "observacoes", "data_hora_registro")
CAMPOS_LIMPEZA = ("num", "data", "resp", "filtros", "origem", "ptp", "proc", "resultado", "obs")


def conectar():
    return banco.abrir(dados.DB_LOTES)


def inicializar():
    """Cria/atualiza as tabelas do lotes.db como o programa de mesa (os dois abrem o mesmo arquivo)."""
    con = conectar()
    try:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tracking_id TEXT, lote_geral TEXT, lote_fornecedor TEXT,
                data_recebimento TEXT, responsavel TEXT, fornecedor TEXT, total_filtros TEXT,
                numero_caixas_menores TEXT, capacidade_caixa_menor TEXT, material TEXT, dimensoes TEXT,
                espessura TEXT, tipo_acabamento TEXT, filtros_quebrados TEXT, quantidade_confere TEXT,
                procedimento_limpeza TEXT, resultado_inspecao TEXT, arquivo_controle TEXT, observacoes TEXT,
                qr_code_path TEXT, qrcodes_caixas_dir TEXT, data_hora_registro TEXT);
            CREATE TABLE IF NOT EXISTS lotes_internos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, id_lote INTEGER, numero_caixa INTEGER, codigo_interno TEXT,
                quantidade_filtros TEXT, observacoes TEXT, lote_fornecedor TEXT);
            CREATE TABLE IF NOT EXISTS lotes_limpeza (
                id INTEGER PRIMARY KEY AUTOINCREMENT, codigo_interno TEXT, data_limpeza TEXT, responsavel TEXT,
                quantidade_filtros TEXT, origem TEXT, remocao_ptp TEXT, procedimento TEXT, resultado TEXT,
                observacoes TEXT, data_hora_registro TEXT);
        """)
        # bancos antigos: o SQLite não diferencia maiúsculas em nomes de colunas (Fornecedor = fornecedor)
        existentes = {c[1].lower() for c in con.execute("PRAGMA table_info(lotes)")}
        for nome in CAMPOS_LOTE + ("tracking_id", "qr_code_path", "qrcodes_caixas_dir"):
            if nome not in existentes:
                con.execute(f"ALTER TABLE lotes ADD COLUMN {nome} TEXT")
                existentes.add(nome)
        if "lote_fornecedor" not in {c[1].lower() for c in con.execute("PRAGMA table_info(lotes_internos)")}:
            con.execute("ALTER TABLE lotes_internos ADD COLUMN lote_fornecedor TEXT")
        con.commit()
    finally:
        con.close()


def data_hora_atual():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def data_atual():
    return datetime.now().strftime("%d/%m/%Y")


def gerar_tracking_id(registro_id):
    return f"DUNE-HD-{datetime.now().year}-{registro_id:04d}"


def inteiro_positivo(texto):
    try:
        valor = int(str(texto).strip())
        return valor if valor > 0 else None
    except ValueError:
        return None


def codigo_do_numero(numero, prefixo=PREFIXO_CAIXA):
    """'4' -> 'DUNE-CX-0004' (vazio se não houver número)."""
    numero = str(numero).strip()
    return prefixo + numero.zfill(DIGITOS_CAIXA) if numero else ""


def numero_do_codigo(codigo, prefixo=PREFIXO_CAIXA):
    """'DUNE-CX-0004' -> '0004'; código fora do padrão -> ''."""
    m = re.fullmatch(re.escape(prefixo) + r"(\d+)", str(codigo or "").strip(), flags=re.IGNORECASE)
    return m.group(1) if m else ""


# =====================================================================
# LOTES OPTO
# =====================================================================
_SQL_LISTA = """
    SELECT id, tracking_id, lote_geral, fornecedor AS fornecedor, total_filtros, numero_caixas_menores,
           (SELECT COUNT(*) FROM lotes_internos li WHERE li.id_lote = lotes.id) AS n_internos,
           data_recebimento, responsavel, resultado_inspecao, data_hora_registro
    FROM lotes
"""          # "fornecedor AS": bancos antigos têm a coluna Fornecedor e o SQLite devolve o nome declarado


def listar(termo=""):
    """Lotes, mais recentes primeiro; a busca é a mesma do programa de mesa (inclui os códigos internos)."""
    if not dados.DB_LOTES.exists():
        return []
    con = dados._conectar(dados.DB_LOTES)
    try:
        if not termo:
            return dados._linhas(con, _SQL_LISTA + " ORDER BY id DESC")
        t = "%" + termo + "%"
        return dados._linhas(con, _SQL_LISTA + """
            WHERE tracking_id LIKE ? OR lote_geral LIKE ? OR lote_fornecedor LIKE ?
                  OR fornecedor LIKE ? OR responsavel LIKE ?
                  OR id IN (SELECT id_lote FROM lotes_internos WHERE codigo_interno LIKE ?)
            ORDER BY id DESC""", (t,) * 6)
    finally:
        con.close()


def internos(con, registro_id):
    return dados._linhas(con, "SELECT id, numero_caixa AS caixa, codigo_interno AS codigo, quantidade_filtros AS filtros, "
                              "observacoes AS obs FROM lotes_internos WHERE id_lote = ? ORDER BY numero_caixa",
                         (registro_id,))


def ler(registro_id):
    """O lote gravado (todas as colunas) com os lotes internos; None se não existir."""
    if not dados.DB_LOTES.exists():
        return None
    con = dados._conectar(dados.DB_LOTES)
    try:
        r = con.execute("SELECT * FROM lotes WHERE id = ?", (registro_id,)).fetchone()
        if r is None:
            return None
        lote = {k.lower(): v for k, v in dict(r).items()}
        lote["internos"] = internos(con, registro_id)
        lote["soma_filtros"] = sum(int(i["filtros"]) for i in lote["internos"] if str(i["filtros"] or "").isdigit())
        return lote
    finally:
        con.close()


def vazio(responsavel):
    """Formulário de um lote novo, com os valores iniciais do programa de mesa."""
    f = {c: "" for c in CAMPOS_LOTE}
    f.update(id=None, data_recebimento=data_atual(), responsavel=responsavel, fornecedor="OPTO",
             capacidade_caixa_menor=str(CAPACIDADE_PADRAO), tipo_acabamento="Polished", resultado_inspecao="Approved",
             filtros_quebrados="No", quantidade_confere="Yes", procedimento_limpeza="Yes", internos=[])
    return f


def formulario(registro_id):
    """Formulário de um lote gravado. Registros antigos sem capacidade usam a padrão, como no programa de mesa."""
    lote = ler(registro_id)
    if lote is None:
        return None
    f = {c: lote.get(c) or "" for c in CAMPOS_LOTE}
    f["id"] = registro_id
    f["capacidade_caixa_menor"] = f["capacidade_caixa_menor"] or str(CAPACIDADE_PADRAO)
    f["tipo_acabamento"] = f["tipo_acabamento"] or "Polished"
    f["resultado_inspecao"] = f["resultado_inspecao"] or "Approved"
    f["filtros_quebrados"] = f["filtros_quebrados"] or "No"
    f["quantidade_confere"] = f["quantidade_confere"] or "Yes"
    f["procedimento_limpeza"] = f["procedimento_limpeza"] or "Yes"
    f["internos"] = [{"caixa": i["caixa"], "codigo": i["codigo"] or "", "filtros": i["filtros"] or "", "obs": i["obs"] or ""}
                     for i in lote["internos"]]
    for it in f["internos"]:
        it["num"] = numero_do_codigo(it["codigo"]) or it["codigo"]
        it["orig"] = "" if numero_do_codigo(it["codigo"]) else it["codigo"]
    ajustar_caixas(f)
    return f


def filtros_padrao(f, i, n):
    """Filtros da caixa i (de n): a capacidade. Registro antigo com a última caixa parcial mantém o resto."""
    cap = inteiro_positivo(f["capacidade_caixa_menor"])
    if cap is None:
        return ""
    total = inteiro_positivo(f["total_filtros"])
    if i == n and total is not None and cap * (n - 1) < total < cap * n:
        return str(total - cap * (n - 1))
    return str(cap)


def ajustar_caixas(f):
    """Uma linha por caixa menor (1..n), mantendo o que já foi digitado; filtros vazios recebem o padrão."""
    n = inteiro_positivo(f["numero_caixas_menores"]) or 0
    por_caixa = {it["caixa"]: it for it in f["internos"]}
    nova = []
    for i in range(1, n + 1):
        it = por_caixa.get(i) or {"caixa": i, "codigo": "", "num": "", "orig": "", "filtros": "", "obs": ""}
        if not str(it["filtros"]).strip():
            it["filtros"] = filtros_padrao(f, i, n)
        nova.append(it)
    f["internos"] = nova


def total_das_caixas(f):
    """Soma dos filtros de cada caixa (vazio = capacidade); None sem capacidade ou sem caixas."""
    cap = inteiro_positivo(f["capacidade_caixa_menor"])
    if cap is None or not f["internos"]:
        return None
    return sum(int(it["filtros"]) if str(it["filtros"]).strip().isdigit() else cap for it in f["internos"])


def de_formulario(form):
    """Formulário enviado pelo navegador -> dict do lote. Erros de digitação das caixas vão para f['erros_caixas']."""
    f = {c: form.get(c, "").strip() for c in CAMPOS_LOTE}
    f["id"] = form.get("lote_id", type=int)
    f["internos"], erros = [], []
    n = inteiro_positivo(f["numero_caixas_menores"]) or 0
    for i in range(1, n + 1):
        numero = form.get(f"cx_num_{i}", "").strip()
        original = form.get(f"cx_orig_{i}", "").strip()       # código gravado fora do padrão DUNE-CX-000X
        filtros = form.get(f"cx_filtros_{i}", "").strip()
        if numero.isdigit():
            codigo = codigo_do_numero(numero)
        elif numero and numero == original:
            codigo = original
        else:
            codigo = ""
            if numero:
                erros.append(t("Box {i:02d}: type only the number (digits), e.g. 0004.", i=i))
        if filtros and not filtros.isdigit():
            erros.append(t("Filters in box {i:02d} must be an integer.", i=i))
        f["internos"].append({"caixa": i, "codigo": codigo, "num": numero, "orig": original, "filtros": filtros,
                              "obs": form.get(f"cx_obs_{i}", "").strip()})
    f["erros_caixas"] = erros
    ajustar_caixas(f)
    total = total_das_caixas(f)
    f["total_filtros"] = "" if total is None else str(total)
    return f


def conflito_codigos(itens):
    """Mensagem se um código estiver repetido dentro do mesmo lote OPTO; senão None."""
    vistos = {}
    for it in itens:
        codigo = it["codigo"].strip()
        if not codigo:
            continue
        if codigo.lower() in vistos:
            return t("Internal lot code '{codigo}' is used by boxes {a:02d} and {b:02d}.", codigo=codigo, a=vistos[codigo.lower()],
                     b=it["caixa"])
        vistos[codigo.lower()] = it["caixa"]
    return None


def validar(f):
    """Erros que impedem a gravação (as mesmas regras do programa de mesa)."""
    erros = list(f.get("erros_caixas") or [])
    if not f["lote_geral"]:
        erros.append(t("Enter the OPTO batch (general batch ID)."))
    if inteiro_positivo(f["numero_caixas_menores"]) is None:
        erros.append(t("Number of small boxes must be an integer greater than zero."))
    if inteiro_positivo(f["capacidade_caixa_menor"]) is None:
        erros.append(t("Small box capacity must be an integer greater than zero."))
    elif not f["total_filtros"]:
        erros.append(t("Enter the small box capacity and the number of small boxes "
                       "(the total number of filters is calculated from them)."))
    conflito = conflito_codigos(f["internos"])
    if conflito:
        erros.append(conflito)
    return erros


def caixas_sem_codigo(f):
    return [it for it in f["internos"] if not it["codigo"].strip()]


def preencher_codigos(f):
    """Caixas sem código recebem DUNE-CX-000X com o número da caixa (o 'Yes' do programa de mesa)."""
    for it in caixas_sem_codigo(f):
        it["codigo"] = codigo_do_numero(it["caixa"])
        it["num"] = numero_do_codigo(it["codigo"])


def gravar(f, registro_id=None):
    """Grava o lote e os lotes internos numa transação. Os lotes internos mantêm o ID (a deposição guarda esse ID).
    Retorna (id, tracking_id)."""
    f["data_hora_registro"] = data_hora_atual()
    valores = tuple(f[c] for c in CAMPOS_LOTE)
    con = conectar()
    try:
        with con:
            if registro_id is None:
                cur = con.execute(f"INSERT INTO lotes ({', '.join(CAMPOS_LOTE)}) VALUES ({', '.join('?' * len(CAMPOS_LOTE))})",
                                  valores)
                registro_id = cur.lastrowid
                tracking = gerar_tracking_id(registro_id)
            else:
                r = con.execute("SELECT tracking_id FROM lotes WHERE id = ?", (registro_id,)).fetchone()
                tracking = (r and r[0]) or gerar_tracking_id(registro_id)
                con.execute(f"UPDATE lotes SET {', '.join(c + ' = ?' for c in CAMPOS_LOTE)} WHERE id = ?",
                            valores + (registro_id,))
            con.execute("UPDATE lotes SET tracking_id = ? WHERE id = ?", (tracking, registro_id))

            n = len(f["internos"])
            existentes = {num: id_ for id_, num in con.execute(
                "SELECT id, numero_caixa FROM lotes_internos WHERE id_lote = ?", (registro_id,))}
            for it in f["internos"]:
                codigo = it["codigo"].strip()
                if not codigo:
                    if it["caixa"] in existentes:
                        con.execute("DELETE FROM lotes_internos WHERE id = ?", (existentes[it["caixa"]],))
                    continue
                vals = (codigo, str(it["filtros"]).strip(), it["obs"].strip())
                if it["caixa"] in existentes:
                    con.execute("UPDATE lotes_internos SET codigo_interno = ?, quantidade_filtros = ?, observacoes = ? "
                                "WHERE id = ?", vals + (existentes[it["caixa"]],))
                else:
                    con.execute("INSERT INTO lotes_internos (id_lote, numero_caixa, codigo_interno, quantidade_filtros, "
                                "observacoes) VALUES (?, ?, ?, ?, ?)", (registro_id, it["caixa"]) + vals)
            con.execute("DELETE FROM lotes_internos WHERE id_lote = ? AND numero_caixa > ?", (registro_id, n))
    finally:
        con.close()
    return registro_id, tracking


def excluir(registro_id):
    """Apaga o lote e os lotes internos. Retorna (tracking_id, lote OPTO) ou None se não existir."""
    con = conectar()
    try:
        r = con.execute("SELECT tracking_id, lote_geral FROM lotes WHERE id = ?", (registro_id,)).fetchone()
        if r is None:
            return None
        with con:
            con.execute("DELETE FROM lotes WHERE id = ?", (registro_id,))
            con.execute("DELETE FROM lotes_internos WHERE id_lote = ?", (registro_id,))
        return r[0] or "", r[1] or ""
    finally:
        con.close()


def usos(registro_id=None, limpeza_id=None):
    """Amostras de deposição que usaram o lote OPTO (ou o lote de limpeza): [(id da amostra, id do lote interno)]."""
    con = dados._conectar(dados.DB_TAREFAS)
    try:
        if limpeza_id is not None:
            return [tuple(r) for r in con.execute(
                "SELECT id_tarefa, lote_interno_id FROM tarefa_lotes WHERE tipo_lote = 'limpeza' AND lote_interno_id = ?",
                (limpeza_id,))]
        linhas = [tuple(r) for r in con.execute(
            "SELECT id_tarefa, lote_interno_id FROM tarefa_lotes WHERE COALESCE(tipo_lote, 'opto') = 'opto' AND lote_id = ?",
            (registro_id,))]
        com_lotes = {r[0] for r in con.execute("SELECT DISTINCT id_tarefa FROM tarefa_lotes")}
        # registros antigos: um lote só, gravado na própria tarefa
        linhas += [(r[0], None) for r in con.execute("SELECT id FROM tarefas WHERE lote_entrada_id = ?", (registro_id,))
                   if r[0] not in com_lotes]
        return linhas
    finally:
        con.close()


def usos_todos():
    """[(id da amostra, id do lote OPTO)] de todas as deposições (para contar as amostras de cada lote)."""
    con = dados._conectar(dados.DB_TAREFAS)
    try:
        linhas = [tuple(r) for r in con.execute(
            "SELECT id_tarefa, lote_id FROM tarefa_lotes WHERE COALESCE(tipo_lote, 'opto') = 'opto' AND lote_id IS NOT NULL")]
        com_lotes = {r[0] for r in con.execute("SELECT DISTINCT id_tarefa FROM tarefa_lotes")}
        linhas += [tuple(r) for r in con.execute("SELECT id, lote_entrada_id FROM tarefas WHERE lote_entrada_id IS NOT NULL")
                   if r[0] not in com_lotes]
        return linhas
    finally:
        con.close()


def csv_texto():
    """Exportação CSV com as mesmas colunas do programa de mesa."""
    con = dados._conectar(dados.DB_LOTES)
    try:
        linhas = con.execute("""
            SELECT id, tracking_id, lote_geral, data_recebimento, responsavel, fornecedor, total_filtros,
                   numero_caixas_menores, capacidade_caixa_menor, material, dimensoes, espessura, tipo_acabamento,
                   filtros_quebrados, quantidade_confere, procedimento_limpeza, resultado_inspecao, arquivo_controle,
                   observacoes, data_hora_registro,
                   (SELECT GROUP_CONCAT(codigo_interno, '; ') FROM lotes_internos li WHERE li.id_lote = lotes.id)
            FROM lotes ORDER BY id DESC""").fetchall()
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Tracking ID", "OPTO Batch", "Arrival Date", "Responsible", "Supplier", "Total Number of Filters",
                "Number of Small Boxes", "Small Box Capacity", "Material", "Dimensions", "Thickness", "Finishing Type",
                "Broken Filters?", "Quantity Matches?", "Cleaning Procedure Verified?", "Inspection Result",
                "Supplier Control File", "Observations", "Record Date/Time", "Internal Lots"])
    w.writerows(tuple(r) for r in linhas)
    return buf.getvalue()


# =====================================================================
# LOTES DE LIMPEZA DO LEPTONS
# =====================================================================
def proximo_numero_limpeza():
    con = dados._conectar(dados.DB_LOTES)
    try:
        maior = 0
        for (codigo,) in con.execute("SELECT codigo_interno FROM lotes_limpeza"):
            n = numero_do_codigo(codigo, PREFIXO_LIMPEZA)
            if n:
                maior = max(maior, int(n))
        return str(maior + 1).zfill(DIGITOS_CAIXA)
    finally:
        con.close()


def limpeza_vazia(responsavel):
    return {"id": None, "num": proximo_numero_limpeza(), "data": data_atual(), "resp": responsavel, "filtros": "",
            "origem": "", "ptp": "Yes", "proc": "", "resultado": "Under inspection", "obs": ""}


def limpeza_formulario(limp):
    """dict de lotes.limpezas() -> formulário."""
    return {"id": limp["id"], "num": numero_do_codigo(limp["codigo"], PREFIXO_LIMPEZA) or (limp["codigo"] or ""),
            "data": limp["data"] or "", "resp": limp["responsavel"] or "", "filtros": limp["filtros"] or "",
            "origem": limp["origem"] or "", "ptp": limp["ptp"] or "", "proc": limp["proc"] or "",
            "resultado": limp["resultado"] or "", "obs": limp["obs"] or ""}


def limpeza_de_formulario(form):
    f = {c: form.get(c, "").strip() for c in CAMPOS_LIMPEZA}
    f["id"] = form.get("limpeza_id", type=int)
    return f


def validar_limpeza(f):
    """Retorna (código, erro); erro None se puder gravar."""
    if not f["num"].isdigit():
        return "", t("Type only the number of the cleaning lot (e.g. 0001).")
    codigo = codigo_do_numero(f["num"], PREFIXO_LIMPEZA)
    if not f["data"] or not f["resp"]:
        return codigo, t("Enter the cleaning date and the responsible.")
    if inteiro_positivo(f["filtros"]) is None:
        return codigo, t("Number of filters must be an integer greater than zero.")
    if not f["resultado"]:
        return codigo, t("Select the result after cleaning.")
    con = dados._conectar(dados.DB_LOTES)
    try:
        if con.execute("SELECT id FROM lotes_limpeza WHERE lower(codigo_interno) = lower(?) AND id IS NOT ?",
                       (codigo, f["id"])).fetchone():
            return codigo, t("The cleaning lot {codigo} already exists.", codigo=codigo)
    finally:
        con.close()
    return codigo, None


def gravar_limpeza(f, codigo):
    """Grava o lote de limpeza; retorna o id (novo ou o mesmo)."""
    valores = (codigo, f["data"], f["resp"], f["filtros"], f["origem"], f["ptp"], f["proc"], f["resultado"], f["obs"])
    con = conectar()
    try:
        with con:
            if f["id"] is None:
                con.execute("""INSERT INTO lotes_limpeza (codigo_interno, data_limpeza, responsavel, quantidade_filtros,
                               origem, remocao_ptp, procedimento, resultado, observacoes, data_hora_registro)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", valores + (data_hora_atual(),))
                return con.execute("SELECT last_insert_rowid()").fetchone()[0]
            else:
                con.execute("""UPDATE lotes_limpeza SET codigo_interno = ?, data_limpeza = ?, responsavel = ?,
                               quantidade_filtros = ?, origem = ?, remocao_ptp = ?, procedimento = ?, resultado = ?,
                               observacoes = ? WHERE id = ?""", valores + (f["id"],))
                return f["id"]
    finally:
        con.close()


def excluir_limpeza(limpeza_id):
    """Apaga o lote de limpeza; retorna o código, ou None se não existir."""
    con = conectar()
    try:
        r = con.execute("SELECT codigo_interno FROM lotes_limpeza WHERE id = ?", (limpeza_id,)).fetchone()
        if r is None:
            return None
        with con:
            con.execute("DELETE FROM lotes_limpeza WHERE id = ?", (limpeza_id,))
        return r[0] or ""
    finally:
        con.close()


# =====================================================================
# PDFs PARA ARQUIVO (iguais aos do programa de mesa)
# =====================================================================
def _kit_pdf(landscape_pagina=False):
    """Estilos e funções auxiliares comuns aos PDFs de lotes."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
    from xml.sax.saxutils import escape as xesc

    pagina = landscape(A4) if landscape_pagina else A4
    largura = pagina[0] - 24 * mm
    fonte, negrito = pdf._registrar_fontes_pdf()
    azul = colors.HexColor("#1f3a5f")
    zebra = colors.HexColor("#eef3f9")
    grade = colors.HexColor("#9aa7b5")

    base = ParagraphStyle("base", fontName=fonte, fontSize=8, leading=10)
    est_cel = ParagraphStyle("cel", parent=base, fontSize=7.5, leading=9)
    est_cab = ParagraphStyle("cab", parent=est_cel, fontName=negrito, textColor=colors.white, alignment=TA_CENTER)
    est_titulo = ParagraphStyle("tit", parent=base, fontName=negrito, fontSize=13, leading=16,
                                alignment=TA_CENTER, textColor=azul)
    est_sub = ParagraphStyle("sub", parent=base, alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
    est_sec = ParagraphStyle("sec", parent=base, fontName=negrito, fontSize=10, leading=12, textColor=colors.white)

    def txt(v, vazio="-"):
        v = "" if v is None else str(v).strip()
        return xesc(v).replace("\n", "<br/>") if v else vazio

    def P(v, estilo=None, vazio="-"):
        return Paragraph(txt(v, vazio), estilo or est_cel)

    def H(texto):
        return Paragraph(xesc(texto), est_cab)

    def campo(rotulo, valor):
        return Paragraph("<b>" + xesc(rotulo) + ":</b> " + txt(valor), est_cel)

    def secao(titulo):
        tb = Table([[Paragraph(xesc(titulo), est_sec)]], colWidths=[largura])
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), azul), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return tb

    def tabela(linhas, larguras, cabecalho=True, extra=None):
        tb = Table(linhas, colWidths=[w * mm for w in larguras], repeatRows=1 if cabecalho else 0)
        estilo = [("FONTNAME", (0, 0), (-1, -1), fonte), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                  ("GRID", (0, 0), (-1, -1), 0.4, grade), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                  ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        if cabecalho:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), azul),
                       ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, zebra])]
        if extra:
            estilo += extra
        tb.setStyle(TableStyle(estilo))
        return tb

    return {"pagina": pagina, "mm": mm, "largura": largura, "fonte": fonte, "colors": colors,
            "est_titulo": est_titulo, "est_sub": est_sub, "Spacer": Spacer, "Table": Table, "TableStyle": TableStyle,
            "Paragraph": Paragraph, "P": P, "H": H, "campo": campo, "secao": secao, "tabela": tabela, "azul": azul}


def _cabecalho_pdf(k, titulo, subtitulo):
    """Cabeçalho com os logos (esquerda.png / direita.png da pasta do programa)."""
    from reportlab.platypus import Image as RLImage
    mm = k["mm"]

    def logo(nome, alinhamento):
        """Logo sem as margens brancas do arquivo, com até 22 mm de altura e 35 mm de largura."""
        try:
            with Image.open(dados.BASE / nome) as im:
                im = im.convert("RGB")
            branco = Image.new("RGB", im.size, (255, 255, 255))
            caixa = ImageChops.difference(im, branco).point(lambda p: 255 if p > 20 else 0).getbbox()
            if caixa:
                im = im.crop(caixa)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            buf.seek(0)
            w, h = im.size
            escala = min(22 * mm / h, 35 * mm / w)
            return RLImage(buf, width=w * escala, height=h * escala, hAlign=alinhamento)
        except Exception:
            return ""

    topo = k["Table"]([[logo("esquerda.png", "CENTER"),
                        [k["Paragraph"](titulo[0], k["est_titulo"]), k["Paragraph"](titulo[1], k["est_titulo"]),
                         k["Paragraph"](subtitulo, k["est_sub"])],
                        logo("direita.png", "RIGHT")]],
                      colWidths=[40 * mm, k["largura"] - 80 * mm, 40 * mm])
    topo.setStyle(k["TableStyle"]([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("LINEBELOW", (0, 0), (-1, 0), 1.5, k["azul"]),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                                   ("ALIGN", (0, 0), (0, 0), "CENTER")]))
    return topo


def _gravar_pdf(k, story, caminho, titulo_doc, rodape_esq):
    from reportlab.platypus import SimpleDocTemplate
    mm, colors, fonte, pagina = k["mm"], k["colors"], k["fonte"], k["pagina"]

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont(fonte, 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(12 * mm, 8 * mm, rodape_esq + "  |  Generated on " + data_hora_atual()
                          + "  |  Batch Control for DUNE")
        canvas.drawRightString(pagina[0] - 12 * mm, 8 * mm, "Page " + str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(caminho, pagesize=pagina, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=15 * mm, title=titulo_doc,
                            author="Batch Control for DUNE")
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)


def nome_pdf_lote(registro_id, opto):
    return "Batch_" + re.sub(r"[^A-Za-z0-9_.-]", "_", str(opto or "batch")) + "_id" + str(registro_id) + ".pdf"


def gerar_pdf_lote(registro_id, caminho):
    """PDF de arquivo com tudo o que foi registrado para o lote OPTO (e suas caixas/lotes internos)."""
    lote = ler(registro_id)
    if lote is None:
        raise ValueError("Batch not found")
    k = _kit_pdf()
    P, H, campo, secao, tabela, Spacer = k["P"], k["H"], k["campo"], k["secao"], k["tabela"], k["Spacer"]
    g = lote.get
    opto, n_caixas, forn_legado = g("lote_geral"), g("numero_caixas_menores"), g("lote_fornecedor")

    story = [_cabecalho_pdf(k, ("DUNE HD – X-ARAPUCA PTP FILMS", "OPTO BATCH ARRIVAL RECORD"),
                            "Registered data of the batch received from OPTO"), Spacer(1, 6)]

    story += [secao("1. OPTO BATCH INFORMATION"), Spacer(1, 3)]
    story.append(tabela([
        [campo("OPTO BATCH", opto), campo("TRACKING ID", g("tracking_id"))],
        [campo("SUPPLIER / COMPANY", g("fornecedor")), campo("ARRIVAL DATE", g("data_recebimento"))],
        [campo("RESPONSIBLE", g("responsavel")), campo("RECORDED", g("data_hora_registro"))],
        [campo("TOTAL FILTERS", g("total_filtros")), campo("SMALL BOXES", n_caixas)],
        [campo("SMALL BOX CAPACITY (filters per box)", g("capacidade_caixa_menor")),
         (campo("SUPPLIER BATCH (old records)", forn_legado) if forn_legado else "")],
    ], [93, 93], cabecalho=False))

    story += [Spacer(1, 6), secao("2. SUBSTRATE INFORMATION"), Spacer(1, 3)]
    story.append(tabela([[campo("MATERIAL", g("material")), campo("DIMENSIONS", g("dimensoes"))],
                         [campo("THICKNESS", g("espessura")), campo("FINISHING TYPE", g("tipo_acabamento"))]],
                        [93, 93], cabecalho=False))

    story += [Spacer(1, 6), secao("3. ARRIVAL INSPECTION"), Spacer(1, 3)]
    story.append(tabela([[campo("BROKEN FILTERS?", g("filtros_quebrados")),
                          campo("QUANTITY MATCHES SUPPLIER?", g("quantidade_confere"))],
                         [campo("CLEANING PROCEDURE VERIFIED?", g("procedimento_limpeza")),
                          campo("INSPECTION RESULT", g("resultado_inspecao"))]],
                        [93, 93], cabecalho=False))

    story += [Spacer(1, 6), secao("4. INTERNAL LOTS (SMALL BOXES)"), Spacer(1, 3)]
    ints = lote["internos"]
    linhas_i = [[H("Box"), H("OPTO Batch"), H("Internal Lot"), H("Filters"), H("Notes")]]
    for it in ints:
        linhas_i.append([P(str(it["caixa"]).zfill(2)), P(opto), P(it["codigo"]), P(it["filtros"]), P(it["obs"])])
    if len(linhas_i) == 1:
        linhas_i.append([P("-")] * 5)
    soma = sum(int(it["filtros"]) for it in ints if str(it["filtros"] or "").isdigit())
    story.append(tabela(linhas_i, [14, 50, 45, 25, 52]))
    story.append(Spacer(1, 2))
    story.append(P("Registered: " + str(len(ints)) + " of " + str(n_caixas or 0) + " small boxes  |  filters in the "
                   "registered boxes: " + str(soma)))

    story += [Spacer(1, 6), secao("5. TRACEABILITY AND NOTES"), Spacer(1, 3)]
    story.append(tabela([[campo("SUPPLIER CONTROL FILE", g("arquivo_controle")), ""],
                         [campo("OBSERVATIONS", g("observacoes")), ""]],
                        [93, 93], cabecalho=False, extra=[("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1))]))

    _gravar_pdf(k, story, caminho, "OPTO batch record - " + str(opto), "OPTO batch " + str(opto))
    return caminho


def gerar_pdf_limpeza(caminho):
    """PDF de arquivo com a lista de todos os lotes de limpeza do Leptons."""
    k = _kit_pdf(landscape_pagina=True)
    P, H, secao, tabela, Spacer = k["P"], k["H"], k["secao"], k["tabela"], k["Spacer"]
    con = dados._conectar(dados.DB_LOTES)
    try:
        registros = con.execute("""
            SELECT codigo_interno, data_limpeza, responsavel, quantidade_filtros, origem, remocao_ptp,
                   procedimento, resultado, observacoes
            FROM lotes_limpeza ORDER BY id""").fetchall()
    finally:
        con.close()
    linhas = [[H("Cleaning lot"), H("Date"), H("Responsible"), H("Filters"), H("Origin"), H("PTP removed"),
               H("Procedure"), H("Result"), H("Notes")]]
    linhas += [[P(x) for x in r] for r in registros]
    if len(linhas) == 1:
        linhas.append([P("-")] * 9)
    story = [_cabecalho_pdf(k, ("DUNE HD – X-ARAPUCA PTP FILMS", "LEPTONS CLEANING LOTS"),
                            "Material cleaned again at Leptons Lab after PTP removal"), Spacer(1, 6),
             secao("CLEANING LOTS (internal lots selectable in the deposition program)"), Spacer(1, 3),
             tabela(linhas, [28, 20, 28, 14, 50, 20, 46, 26, 35])]
    _gravar_pdf(k, story, caminho, "Leptons cleaning lots", "Leptons cleaning lots")
    return caminho
