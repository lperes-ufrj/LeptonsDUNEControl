from tkinter import filedialog
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import qrcode
import os
import subprocess
import sys
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageChops
import io
import socket
import threading
import hmac
import hashlib
import secrets
import html
import base64
import webbrowser
import re
import urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

try:
    import leptons_auth
except ImportError:
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror("Missing file", "The file leptons_auth.py must be in the same folder as this program.")
    raise SystemExit(1)

# =====================================================
# CONFIGURAÇÕES
# =====================================================
DB_TAREFAS = "rastreabilidade.db"
DB_LOTES = "lotes.db"  # banco gerado pelo programa de controle de lotes
PROGRAMA_LOTES = "controle_lotes_chegada_opto_v13_login_22-10-2026.py"
AREA_FILTRO_MM2 = 77.00 * 100.00
AREA_FILTRO_CM2 = AREA_FILTRO_MM2 / 100.0

anexos_lista = []
tarefa_em_edicao_id = None

# ---- Relatório / QR code ----
# O QR code aponta para uma página com opções (incluindo o relatório no formato do formulário).
# Modo 1 (padrão): URL_BASE_RELATORIO vazio -> o programa abre um servidor leve na porta abaixo e o link
#                  funciona para celulares/computadores na mesma rede, enquanto o programa estiver aberto.
# Modo 2: preencha URL_BASE_RELATORIO com o endereço onde a pasta de relatórios será publicada
#         (ex.: "https://servidor.exemplo.br/relatorios"). Os arquivos HTML são gerados em PASTA_RELATORIOS
#         e basta copiá-los para esse endereço (ou apontar PASTA_RELATORIOS para a pasta compartilhada).
SERVIDOR_PORTA = 8765
URL_BASE_RELATORIO = ""
PASTA_RELATORIOS = "relatorios"
PASTA_PDF = "relatorios_pdf"          # onde o botão "Print report (PDF)" grava os PDFs
servidor_http = None

# ---- Inspeção visual (Deposition Inspection Record) ----
N_FILTROS = 28

CAMPOS_FILTRO = ["visual", "uniformity", "stains", "particles", "edge", "finger", "other", "comments", "classification"]
CAMPOS_OBRIGATORIOS = [c for c in CAMPOS_FILTRO if c != "comments"]
CAMPOS_CABECALHO = ["box_pid", "run_evaporation", "inspector", "pid_p02", "pid_p03", "pid_p14", "notes",
                    "data_inspecao", "operador", "supervisor", "data_revisao", "revisado"]

SIM_NAO = {"Sim": "Yes", "Não": "No"}
CORES_CLASSE = {"A": "#c62828", "B": "#ef6c00", "C": "#2e7d32"}

# (campo, título, largura em px, opções)
COLUNAS_INSPECAO = [
    ("filter", "Filter nº", 60, None),
    ("visual", "Visual\nStatus", 100, ["Pass", "Fail"]),
    ("uniformity", "Uniformity", 165, ["OK", "Minor", "Major"]),
    ("stains", "Stains", 90, ["Yes", "No"]),
    ("particles", "Particles", 90, ["Yes", "No"]),
    ("edge", "Edge\nDefects", 90, ["Yes", "No"]),
    ("finger", "Finger\nDefects", 90, ["Yes", "No"]),
    ("other", "Other\nDefects", 90, ["Yes", "No"]),
    ("comments", "Comments", 200, None),
    ("classification", "Classification", 130, ["A", "B", "C"]),
    ("clear", "", 36, None),
]

# ---- Imersão criogênica ----
LIMITE_PERDA_PCT = 5.0                      # perda de massa máxima aceitável (%)
AMOSTRAS_IMERSAO = ["P02", "P03", "P14"]    # substratos de controle

# (chave, item, critério de aceitação, condição de rejeição)
ITENS_IMERSAO = [
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

imersao_vars = {}
janela_imersao = None
txt_obs_imersao = None
widgets_imersao = {}

# ---- Eficiência óptica (VUV) ----
LIMITE_EFICIENCIA = 0.75                    # eficiência mínima aceita por amostra (x >= 0.75)
MIN_AMOSTRAS_EFICIENCIA = 2                 # o procedimento usa 2 amostras de QC por evaporação
IDADE_MAX_REFERENCIA_DIAS = 183             # vida máxima do substrato de referência (6 meses)
AMOSTRAS_EFICIENCIA = ["P02", "P03", "P14"]
CAMPOS_EF_TESTE = ["data_teste", "ref_id", "ref_data", "temp", "umid",
                   "supervisor", "data_revisao", "revisado", "obs", "operador"]
CAMPOS_EF_AMOSTRA = ["testada", "comp", "larg", "antes", "depois", "x"]

ef_vars = {}
janela_eficiencia = None
txt_obs_eficiencia = None
widgets_ef = {}

inspecao_vars = {}          # StringVars da inspeção (vivem enquanto o programa estiver aberto)
janela_inspecao = None
txt_notas_inspecao = None
lbl_resumo_visual_win = None

lotes_selecionados = []     # lotes de filtros escolhidos para a deposição (pode ser mais de um)

# =====================================================
# BANCO DE DADOS
# =====================================================
def _abrir_banco(caminho):
    """Abre o banco com WAL, gravação segura e espera se estiver ocupado."""
    con = sqlite3.connect(caminho, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")      # leituras e gravações não se bloqueiam; mais seguro contra queda
    con.execute("PRAGMA synchronous=FULL")      # confirma cada gravação no disco
    con.execute("PRAGMA busy_timeout=30000")    # espera até 30 s se o banco estiver ocupado
    return con


def conectar():
    return _abrir_banco(DB_TAREFAS)


def conectar_lotes():
    return _abrir_banco(DB_LOTES)


def coluna_existe(cur, tabela, coluna):
    cur.execute(f"PRAGMA table_info({tabela})")
    return coluna in [c[1] for c in cur.fetchall()]


def adicionar_coluna_se_precisar(cur, tabela, coluna, tipo):
    if not coluna_existe(cur, tabela, coluna):
        cur.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def inicializar_banco():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_tarefa TEXT,
            responsavel TEXT,
            data_inicio TEXT,
            status TEXT,
            descricao TEXT,
            lote_entrada_id INTEGER,
            codigo_lote TEXT,
            position_range TEXT,
            observacoes TEXT,
            anexos_txt TEXT,
            eficiencia_optica_ok TEXT,
            valor_eficiencia TEXT,
            imersao_criogenica_ok TEXT,
            data_hora_registro TEXT,
            massa_ptp_g TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS massa_posicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            posicao INTEGER,
            massa_antes TEXT,
            massa_depois TEXT,
            densidade_massa_ug_cm2 TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspecao_visual_cab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            box_pid TEXT,
            run_evaporation TEXT,
            inspector TEXT,
            pid_p02 TEXT,
            pid_p03 TEXT,
            pid_p14 TEXT,
            notes TEXT,
            data_inspecao TEXT,
            operador TEXT,
            supervisor TEXT,
            data_revisao TEXT,
            revisado TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inspecao_visual_filtros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            filtro INTEGER,
            visual_status TEXT,
            uniformity TEXT,
            stains TEXT,
            particles TEXT,
            edge_defects TEXT,
            finger_defects TEXT,
            other_defects TEXT,
            comments TEXT,
            classification TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS imersao_massas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            amostra TEXT,
            massa_antes TEXT,
            massa_depois TEXT,
            diferenca_g TEXT,
            diferenca_pct TEXT,
            aprovado TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS imersao_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            item TEXT,
            aprovado TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tarefa_lotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            lote_id INTEGER,
            codigo_lote TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS eficiencia_teste (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            data_teste TEXT,
            ref_id TEXT,
            ref_data TEXT,
            temperatura_c TEXT,
            umidade_pct TEXT,
            supervisor TEXT,
            data_revisao TEXT,
            revisado TEXT,
            observacoes TEXT,
            operador TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS eficiencia_amostras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_tarefa INTEGER,
            amostra TEXT,
            testada TEXT,
            comprimento_mm TEXT,
            largura_mm TEXT,
            massa_antes TEXT,
            massa_depois TEXT,
            area_cm2 TEXT,
            densidade_ug_cm2 TEXT,
            eficiencia TEXT,
            aprovado TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS config_sistema (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)

    # Migração para bancos já existentes
    for coluna, tipo in [
        ("codigo_lote", "TEXT"),
        ("eficiencia_optica_ok", "TEXT"),
        ("valor_eficiencia", "TEXT"),
        ("imersao_criogenica_ok", "TEXT"),
        ("data_hora_registro", "TEXT"),
        ("anexos_txt", "TEXT"),
        ("position_range", "TEXT"),
        ("observacoes", "TEXT"),
        ("massa_ptp_g", "TEXT"),
        ("imersao_observacoes", "TEXT"),
        ("imersao_data", "TEXT"),
        ("imersao_operador", "TEXT"),
        ("imersao_supervisor", "TEXT"),
        ("imersao_data_revisao", "TEXT"),
        ("imersao_revisado", "TEXT"),
        ("qa_signoff_por", "TEXT"),
        ("qa_signoff_data", "TEXT"),
    ]:
        adicionar_coluna_se_precisar(cur, "tarefas", coluna, tipo)

    adicionar_coluna_se_precisar(cur, "massa_posicoes", "densidade_massa_ug_cm2", "TEXT")
    adicionar_coluna_se_precisar(cur, "eficiencia_amostras", "testada", "TEXT")
    adicionar_coluna_se_precisar(cur, "inspecao_visual_cab", "data_inspecao", "TEXT")
    adicionar_coluna_se_precisar(cur, "inspecao_visual_cab", "operador", "TEXT")
    adicionar_coluna_se_precisar(cur, "inspecao_visual_cab", "supervisor", "TEXT")
    adicionar_coluna_se_precisar(cur, "inspecao_visual_cab", "data_revisao", "TEXT")
    adicionar_coluna_se_precisar(cur, "inspecao_visual_cab", "revisado", "TEXT")
    adicionar_coluna_se_precisar(cur, "eficiencia_teste", "operador", "TEXT")
    adicionar_coluna_se_precisar(cur, "tarefa_lotes", "lote_interno_id", "INTEGER")
    adicionar_coluna_se_precisar(cur, "tarefa_lotes", "codigo_lote_interno", "TEXT")
    adicionar_coluna_se_precisar(cur, "tarefa_lotes", "tipo_lote", "TEXT")      # 'opto' ou 'limpeza' (Leptons)

    conn.commit()
    conn.close()


def carregar_lotes():
    """Carrega os lotes do banco do sistema de chegada.

    Retorna sempre tuplas no formato:
    (id, internal_lab_batch, arrival_date, company, tracking_compat,
     company_batch, total_filters, small_boxes, inspection_result, arquivo_controle)
    """
    if not os.path.exists(DB_LOTES):
        return []

    try:
        conn = conectar_lotes()
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(lotes)")
        colunas = [c[1] for c in cur.fetchall()]
        mapa = {c.lower(): c for c in colunas}

        def col(*nomes):
            for nome in nomes:
                if nome.lower() in mapa:
                    return mapa[nome.lower()]
            return None

        c_id = col("id")
        c_internal_lab_batch = col(
            "lote_geral", "lote", "batch", "internal_lab_batch", "lote_interno",
            "general_batch", "tracking_id"
        )
        c_arrival_date = col(
            "data_recebimento", "data", "arrival_date", "data_chegada", "receiving_date",
            "date", "data_hora_registro"
        )
        c_company = col("Fornecedor", "fornecedor", "supplier", "producer", "company")
        c_tracking = col("tracking_id", "tracking", "codigo_rastreio")
        c_company_batch = col(
            "lote_fornecedor", "supplier_batch", "company_batch", "opto_batch",
            "lote_empresa"
        )
        c_total_filters = col(
            "total_filtros", "total_filters", "Quantidade",
            "quantidade", "quantity", "quantity_received"
        )
        c_small_boxes = col(
            "numero_caixas_menores", "small_boxes", "number_of_small_boxes", "caixas_menores",
            "small_boxes_count", "box_quantity"
        )
        c_inspection = col("resultado_inspecao", "inspection_result", "status_inspecao", "inspection_status")
        c_arquivo = col("arquivo_controle", "control_file", "supplier_control_file")

        aliases = [
            ("id", c_id),
            ("internal_lab_batch", c_internal_lab_batch),
            ("arrival_date", c_arrival_date),
            ("company", c_company),
            ("tracking_compat", c_tracking),
            ("company_batch", c_company_batch),
            ("total_filters", c_total_filters),
            ("small_boxes", c_small_boxes),
            ("inspection_result", c_inspection),
            ("arquivo_controle", c_arquivo),
        ]

        select_cols = []
        for alias, coluna_real in aliases:
            if coluna_real:
                select_cols.append(f'"{coluna_real}" AS "{alias}"')
            else:
                select_cols.append(f'NULL AS "{alias}"')

        order_col = c_id if c_id else c_arrival_date
        sql = f"SELECT {', '.join(select_cols)} FROM lotes"
        if order_col:
            sql += f' ORDER BY "{order_col}" DESC'

        cur.execute(sql)
        dados = cur.fetchall()
        conn.close()
        return dados

    except Exception as e:
        mensagem = "Nao foi possivel ler o banco " + DB_LOTES + "." + chr(10) + chr(10) + str(e)
        messagebox.showerror("Erro ao carregar lotes", mensagem)
        return []


def buscar_dados_qr(tarefa_id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT codigo_tarefa, responsavel, data_inicio, descricao,
               codigo_lote, position_range, observacoes,
               eficiencia_optica_ok, valor_eficiencia,
               imersao_criogenica_ok, data_hora_registro, massa_ptp_g
        FROM tarefas
        WHERE id = ?
    """, (tarefa_id,))
    dados = cur.fetchone()
    conn.close()
    return dados


def codigos_atuais_lotes_internos():
    """({id: código} dos lotes internos, {id: código} dos lotes de limpeza) como estão hoje no lotes.db.

    Se um código for renomeado no programa de lotes (o ID continua o mesmo), a lista mostra o código novo."""
    internos, limpezas = {}, {}
    if os.path.exists(DB_LOTES):
        try:
            conn = conectar_lotes()
            cur = conn.cursor()
            cur.execute("SELECT id, codigo_interno FROM lotes_internos")
            internos = {i: c for i, c in cur.fetchall()}
            try:
                cur.execute("SELECT id, codigo_interno FROM lotes_limpeza")
                limpezas = {i: c for i, c in cur.fetchall()}
            except Exception:
                pass
            conn.close()
        except Exception:
            pass
    return internos, limpezas


def carregar_tarefas():
    for i in tabela.get_children():
        tabela.delete(i)

    conn = conectar()
    cur = conn.cursor()

    # lote interno (caixa menor) usado em cada tarefa: código atual do cadastro de lotes
    internos_atuais, limpezas_atuais = codigos_atuais_lotes_internos()
    codigos_por_tarefa = {}
    cur.execute("SELECT id_tarefa, lote_interno_id, codigo_lote_interno, tipo_lote FROM tarefa_lotes ORDER BY id")
    for id_t, iid, icod, tipo in cur.fetchall():
        if iid is None and not icod:
            continue
        origem = limpezas_atuais if tipo == "limpeza" else internos_atuais
        codigo = origem.get(iid) or icod
        if codigo:
            codigos_por_tarefa.setdefault(id_t, []).append(codigo)

    cur.execute("""
        SELECT t.id, t.codigo_tarefa, t.codigo_lote, t.responsavel, t.data_inicio,
               (SELECT COUNT(*) FROM inspecao_visual_filtros f
                 WHERE f.id_tarefa = t.id AND f.classification <> ''),
               t.eficiencia_optica_ok, t.imersao_criogenica_ok
        FROM tarefas t
        ORDER BY t.id DESC
    """)

    for row in cur.fetchall():
        valores = list(row)
        if row[0] in codigos_por_tarefa:
            valores[2] = "; ".join(codigos_por_tarefa[row[0]])       # Internal Batch (ex.: DUNE-CX-0001)
        valores[5] = f"{row[5]}/{N_FILTROS}"
        tabela.insert("", "end", values=valores)

    conn.close()


def texto_lote_combo(l):
    """Texto exibido no combobox de lotes."""
    try:
        internal_lab_batch = l[1] or "-"
        arrival_date = l[2] or "-"
        company = l[3] or "-"
        company_batch = l[5] or "-"
        total = l[6] or "-"
        boxes = l[7] or "-"

        return (
            f"Internal Lab Batch: {internal_lab_batch} | "
            f"Company/OPTO Batch: {company_batch} | "
            f"Arrival: {arrival_date} | "
            f"Company: {company} | "
            f"Filters: {total} | "
            f"Small boxes: {boxes}"
        )
    except Exception:
        return str(l)


def montar_entrada_lote(lote, interno=None):
    """Entrada da lista da deposição: lote (10 campos) + lote interno escolhido.

    Posições extras: 10 = id do lote interno, 11 = código do lote interno (ex.: DUNE-CX-0004),
    12 = filtros do lote interno.
    'interno' = (id, numero_caixa, codigo, filtros, observacoes) como vem do programa de lotes."""
    base = tuple(lote)[:10]
    if interno is None:
        return base + (None, None, None, "opto")
    return base + (interno[0], interno[2], interno[3], "opto")


def _interno_da_entrada(l):
    """(id, código, filtros) do lote interno de uma entrada (None se não houver)."""
    if len(l) > 12:
        return l[10], l[11], l[12]
    return None, None, None


def _tipo_da_entrada(l):
    """'limpeza' para lote de limpeza do Leptons; 'opto' para lote OPTO / lote interno."""
    return "limpeza" if len(l) > 13 and l[13] == "limpeza" else "opto"


def montar_entrada_limpeza(limp):
    """Entrada da lista para um lote de limpeza do Leptons.

    limp = (id, codigo, data, responsavel, filtros, origem, remocao_ptp, resultado, observacoes)."""
    lote_falso = (None, "Leptons cleaning", limp[2], "Leptons Lab", None, "-", limp[4], "-", limp[7], "-")
    return lote_falso + (limp[0], limp[1], limp[4], "limpeza")


def _filtros_da_entrada(l):
    """Filtros desta entrada: os do lote interno, se houver; senão o total do lote."""
    _, _, filtros_interno = _interno_da_entrada(l)
    valor = filtros_interno if filtros_interno not in (None, "") else l[6]
    try:
        return int(float(str(valor).replace(",", ".")))
    except Exception:
        return None


def atualizar_info_lote_selecionado(event=None):
    """Resumo das entradas selecionadas: lote(s) interno(s) usado(s) e total de filtros."""
    try:
        n = len(lotes_selecionados)
        if n == 0:
            lbl_info_lote.config(text="No batch selected")
            return
        filtros = [_filtros_da_entrada(l) for l in lotes_selecionados]
        validos = [x for x in filtros if x is not None]
        total = sum(validos) if validos else "-"
        codigos = [c for c in (_interno_da_entrada(l)[1] for l in lotes_selecionados) if c]
        if codigos:
            texto = ", ".join(codigos[:4]) + (f" (+{len(codigos) - 4})" if len(codigos) > 4 else "")
            interno_txt = ("Internal lot used: " if len(codigos) == 1 else "Internal lots used: ") + texto
        else:
            interno_txt = "No internal lot selected"
        lbl_info_lote.config(text=f"{n} selected   |   {interno_txt}   |   Total filters: {total}")
    except Exception:
        pass


def atualizar_lista_lotes_selecionados():
    """Redesenha a lista de lotes/lotes internos escolhidos na tela principal."""
    for i in tab_lotes_sel.get_children():
        tab_lotes_sel.delete(i)
    for i, l in enumerate(lotes_selecionados):
        _, codigo_interno, _ = _interno_da_entrada(l)
        filtros = _filtros_da_entrada(l)
        valores = (l[1], codigo_interno, l[2], l[3], filtros)
        tab_lotes_sel.insert("", "end", iid=str(i), values=tuple("-" if v in (None, "") else v for v in valores))
    atualizar_info_lote_selecionado()


def definir_lotes_selecionados(lista):
    lotes_selecionados[:] = list(lista)
    atualizar_lista_lotes_selecionados()


def obter_lotes_selecionados():
    return list(lotes_selecionados)


def remover_lotes_selecionados():
    sel = tab_lotes_sel.selection()
    if not sel:
        messagebox.showwarning("Warning", "Select the batch(es) to remove from the list")
        return
    remover = {int(i) for i in sel}
    lotes_selecionados[:] = [l for i, l in enumerate(lotes_selecionados) if i not in remover]
    atualizar_lista_lotes_selecionados()


def _sql_lotes_internos(cur=None):
    """SELECT dos lotes internos (caixas menores, ex.: DUNE-CX-0004) do programa de lotes."""
    return "SELECT id, numero_caixa, codigo_interno, quantidade_filtros, observacoes FROM lotes_internos"


def carregar_lotes_internos(id_lote):
    """Lotes internos (um por caixa menor) registrados no programa de controle de lotes.

    Retorna linhas (id, numero_caixa, codigo_interno, quantidade_filtros, observacoes)."""
    if id_lote is None or not os.path.exists(DB_LOTES):
        return []
    try:
        conn = conectar_lotes()
        cur = conn.cursor()
        cur.execute(_sql_lotes_internos(cur) + " WHERE id_lote = ? ORDER BY numero_caixa", (id_lote,))
        linhas = cur.fetchall()
        conn.close()
        return linhas
    except Exception:
        return []


def buscar_lote_interno(interno_id, codigo, id_lote=None):
    """Um lote interno pelo ID (ou, se não achar, pelo código dentro do lote OPTO). None se não existir."""
    if not os.path.exists(DB_LOTES):
        return None
    try:
        conn = conectar_lotes()
        cur = conn.cursor()
        row = None
        if interno_id is not None:
            cur.execute(_sql_lotes_internos(cur) + " WHERE id = ?", (interno_id,))
            row = cur.fetchone()
        if row is None and codigo:
            if id_lote is not None:
                cur.execute(_sql_lotes_internos(cur) + " WHERE codigo_interno = ? AND id_lote = ?", (codigo, id_lote))
            else:
                cur.execute(_sql_lotes_internos(cur) + " WHERE codigo_interno = ?", (codigo,))
            row = cur.fetchone()
        conn.close()
        return row
    except Exception:
        return None


def carregar_lotes_limpeza():
    """Lotes de limpeza realizada no Leptons (material que passou por remoção de PTP e nova limpeza).

    Retorna linhas (id, codigo, data, responsavel, filtros, origem, remocao_ptp, resultado, observacoes)."""
    if not os.path.exists(DB_LOTES):
        return []
    try:
        conn = conectar_lotes()
        cur = conn.cursor()
        cur.execute("SELECT id, codigo_interno, data_limpeza, responsavel, quantidade_filtros, origem, remocao_ptp, "
                    "resultado, observacoes FROM lotes_limpeza ORDER BY id DESC")
        linhas = cur.fetchall()
        conn.close()
        return linhas
    except Exception:
        return []


def buscar_lote_limpeza(limpeza_id, codigo):
    """Um lote de limpeza pelo ID (ou pelo código). None se não existir."""
    if not os.path.exists(DB_LOTES):
        return None
    try:
        conn = conectar_lotes()
        cur = conn.cursor()
        base = ("SELECT id, codigo_interno, data_limpeza, responsavel, quantidade_filtros, origem, remocao_ptp, "
                "resultado, observacoes FROM lotes_limpeza")
        row = None
        if limpeza_id is not None:
            cur.execute(base + " WHERE id = ?", (limpeza_id,))
            row = cur.fetchone()
        if row is None and codigo:
            cur.execute(base + " WHERE codigo_interno = ?", (codigo,))
            row = cur.fetchone()
        conn.close()
        return row
    except Exception:
        return None


def pids_que_usaram_lote_interno(interno_id, ignorar_tarefa=None, tipo="opto"):
    """PIDs das deposições que já usaram este lote interno (ou lote de limpeza, com tipo='limpeza')."""
    if interno_id is None:
        return []
    try:
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT t.codigo_tarefa
            FROM tarefa_lotes tl JOIN tarefas t ON t.id = tl.id_tarefa
            WHERE tl.lote_interno_id = ? AND COALESCE(tl.tipo_lote, 'opto') = ?
                  AND (? IS NULL OR tl.id_tarefa != ?)
        """, (interno_id, tipo, ignorar_tarefa, ignorar_tarefa))
        pids = [str(r[0]) for r in cur.fetchall() if r[0]]
        conn.close()
        return pids
    except Exception:
        return []


def salvar_lotes_db(cur, tarefa_id, lotes_sel):
    cur.execute("DELETE FROM tarefa_lotes WHERE id_tarefa = ?", (tarefa_id,))
    for l in lotes_sel:
        interno_id, codigo_interno, _ = _interno_da_entrada(l)
        cur.execute("INSERT INTO tarefa_lotes (id_tarefa, lote_id, codigo_lote, lote_interno_id, "
                    "codigo_lote_interno, tipo_lote) VALUES (?, ?, ?, ?, ?, ?)",
                    (tarefa_id, l[0], l[1], interno_id, codigo_interno, _tipo_da_entrada(l)))


def buscar_lotes_da_tarefa(tarefa_id, lote_id_legado, codigo_legado):
    """Lotes (e lotes internos / limpeza) gravados para a tarefa; registros antigos têm um lote só, em tarefas."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT lote_id, codigo_lote, lote_interno_id, codigo_lote_interno, tipo_lote "
                "FROM tarefa_lotes WHERE id_tarefa = ? ORDER BY id", (tarefa_id,))
    salvos = cur.fetchall()
    conn.close()

    if not salvos and (lote_id_legado is not None or codigo_legado):
        salvos = [(lote_id_legado, codigo_legado, None, None, "opto")]

    resultado = []
    for lid, cod, iid, icod, tipo in salvos:
        if tipo == "limpeza":
            limp = buscar_lote_limpeza(iid, icod)
            if limp is None:
                # lote de limpeza removido do cadastro: mantém o código gravado
                limp = (iid, icod, "-", None, None, None, None, None, None)
            resultado.append(montar_entrada_limpeza(limp))
            continue

        achado = next(
            (l for l in lotes if (lid is not None and l[0] == lid) or (cod and l[1] == cod)),
            None
        )
        if achado is None:
            # lote que não existe mais em lotes.db: mantém o que foi gravado
            achado = (lid, cod, "-", "-", None, "-", "-", "-", "-", "-")
        interno = None
        if iid is not None or icod:
            interno = buscar_lote_interno(iid, icod, lid)
            if interno is None:
                interno = (iid, None, icod, None, None)     # lote interno removido: mantém o código gravado
        resultado.append(montar_entrada_lote(achado, interno))
    return resultado


# =====================================================
# FUNÇÕES DA INTERFACE
# =====================================================
def atualizar_relogio():
    lbl_relogio.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    janela.after(1000, atualizar_relogio)


def adicionar_anexo():
    arquivos = filedialog.askopenfilenames(
        title="Selecionar arquivos",
        filetypes=[
            ("Imagens", "*.jpg *.jpeg *.png"),
            ("PDF", "*.pdf"),
            ("Todos", "*.*")
        ]
    )
    for arq in arquivos:
        anexos_lista.append(arq)
    lbl_anexos["text"] = f"{len(anexos_lista)} arquivo(s) anexado(s)"


def atualizar_lotes():
    global lotes
    lotes = carregar_lotes()


def abrir_sistema_lotes():
    """Abre o primeiro programa para cadastrar/consultar lotes."""
    caminho_local = os.path.join(os.getcwd(), PROGRAMA_LOTES)
    caminho_mnt = os.path.join("/mnt/data", PROGRAMA_LOTES)

    if os.path.exists(caminho_local):
        caminho = caminho_local
    elif os.path.exists(caminho_mnt):
        caminho = caminho_mnt
    else:
        messagebox.showwarning(
            "Programa não encontrado",
            f"Não encontrei o arquivo {PROGRAMA_LOTES}.\n"
            "Selecione manualmente o programa de controle de lotes."
        )
        caminho = filedialog.askopenfilename(
            title="Selecionar programa de controle de lotes",
            filetypes=[("Python", "*.py"), ("Todos", "*.*")]
        )
        if not caminho:
            return

    try:
        subprocess.Popen([sys.executable, caminho])
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível abrir o programa de lotes.\n\n{e}")


def selecionar_lote_em_janela():
    """Escolhe o lote OPTO + lote interno (DUNE-CX-000X) ou um lote de limpeza do Leptons para a deposição."""
    atualizar_lotes()
    limpezas = carregar_lotes_limpeza()
    if not lotes and not limpezas:
        messagebox.showwarning(
            "Nenhum lote encontrado",
            "Não encontrei lotes cadastrados no banco lotes.db.\n"
            "Abra o sistema de controle de lotes e cadastre/atualize os lotes."
        )
        return

    fundo = "#f4f6f8"
    win = tk.Toplevel(janela)
    win.title("Select batch and internal lot")
    win.geometry("1100x700")
    win.configure(bg=fundo)
    win.transient(janela)
    win.grab_set()

    nb = ttk.Notebook(win)
    nb.pack(fill="both", expand=True, padx=10, pady=(10, 0))
    aba_opto = tk.Frame(nb, bg=fundo)
    aba_limp = tk.Frame(nb, bg=fundo)
    nb.add(aba_opto, text="OPTO batch / internal lot")
    nb.add(aba_limp, text="Leptons cleaning lot")

    # ---------------- aba 1: lote OPTO -> lote interno ----------------
    tk.Label(aba_opto, text="1) Select the OPTO batch:", bg=fundo,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8, pady=(10, 2))
    cols = ("ID", "OPTO Batch", "Arrival Date", "Company", "QR/Tracking Code",
            "Total Filters", "Small Boxes", "Inspection", "Control File")
    tab = ttk.Treeview(aba_opto, columns=cols, show="headings", height=6, selectmode="browse")
    tab.pack(fill="x", padx=8)
    for c, largura in zip(cols, (40, 150, 100, 110, 170, 90, 80, 110, 120)):
        tab.heading(c, text=c)
        tab.column(c, anchor="center", width=largura)
    for idx, lote in enumerate(lotes):
        tab.insert("", "end", iid=str(idx),
                   values=["-" if v is None else v for k, v in enumerate(lote) if k != 5])

    tk.Label(aba_opto, text="2) Select the internal lot(s) (small boxes, e.g. DUNE-CX-0004) used in this deposition "
                            "(Ctrl / Shift + click):", bg=fundo,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8, pady=(12, 2))
    cols_i = ("Box", "Internal Lot", "Filters", "Notes", "Status")
    tab_i = ttk.Treeview(aba_opto, columns=cols_i, show="headings", height=8, selectmode="extended")
    tab_i.pack(fill="both", expand=True, padx=8)
    for c, largura in zip(cols_i, (60, 230, 80, 300, 300)):
        tab_i.heading(c, text=c)
        tab_i.column(c, anchor="center", width=largura)

    lbl_aviso = tk.Label(aba_opto, text="", bg=fundo, fg="#c62828", font=("Segoe UI", 9), wraplength=1000, justify="left")
    lbl_aviso.pack(anchor="w", padx=8, pady=(4, 6))

    internos_atuais = []

    def mostrar_internos(event=None):
        for i in tab_i.get_children():
            tab_i.delete(i)
        internos_atuais.clear()
        sel = tab.selection()
        if not sel:
            lbl_aviso.config(text="")
            return
        lote = lotes[int(sel[0])]
        linhas = carregar_lotes_internos(lote[0])
        internos_atuais.extend(linhas)
        if not linhas:
            lbl_aviso.config(text="No internal lots are registered for this batch. Register them in the batch control "
                                  "program, or add the batch without an internal lot.")
            return
        lbl_aviso.config(text="")
        escolhidos = {(l[0], _interno_da_entrada(l)[0]) for l in lotes_selecionados if _tipo_da_entrada(l) == "opto"}
        for idx, (iid, caixa, codigo, filtros, obs) in enumerate(linhas):
            if (lote[0], iid) in escolhidos:
                status = "Selected in this deposition"
            else:
                pids = pids_que_usaram_lote_interno(iid, tarefa_em_edicao_id)
                status = ("Used in PID " + ", ".join(pids)) if pids else "Available"
            tab_i.insert("", "end", iid=str(idx), values=(
                str(caixa).zfill(2) if caixa is not None else "-", codigo or "-",
                filtros or "-", obs or "", status))

    # ---------------- aba 2: lote de limpeza do Leptons ----------------
    tk.Label(aba_limp, text="Select the Leptons cleaning lot(s): material that went through PTP removal and a new "
                            "cleaning at Leptons Lab (Ctrl / Shift + click):", bg=fundo,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8, pady=(10, 2))
    cols_l = ("Cleaning lot", "Date", "Responsible", "Filters", "Origin", "PTP removed", "Result", "Status")
    tab_l = ttk.Treeview(aba_limp, columns=cols_l, show="headings", height=14, selectmode="extended")
    tab_l.pack(fill="both", expand=True, padx=8)
    for c, largura in zip(cols_l, (130, 90, 120, 70, 230, 90, 140, 190)):
        tab_l.heading(c, text=c)
        tab_l.column(c, anchor="center", width=largura)
    lbl_aviso_l = tk.Label(aba_limp, text="", bg=fundo, fg="#c62828", font=("Segoe UI", 9), wraplength=1000, justify="left")
    lbl_aviso_l.pack(anchor="w", padx=8, pady=(4, 6))

    def mostrar_limpezas():
        for i in tab_l.get_children():
            tab_l.delete(i)
        if not limpezas:
            lbl_aviso_l.config(text="No Leptons cleaning lots are registered. Register them in the batch control "
                                    "program (Leptons Cleaning button).")
            return
        lbl_aviso_l.config(text="")
        escolhidos = {_interno_da_entrada(l)[0] for l in lotes_selecionados if _tipo_da_entrada(l) == "limpeza"}
        for idx, (cid, codigo, data, resp, filtros, origem, ptp, resultado, obs) in enumerate(limpezas):
            if cid in escolhidos:
                status = "Selected in this deposition"
            else:
                pids = pids_que_usaram_lote_interno(cid, tarefa_em_edicao_id, "limpeza")
                status = ("Used in PID " + ", ".join(pids)) if pids else "Available"
            tab_l.insert("", "end", iid=str(idx), values=(
                codigo or "-", data or "-", resp or "-", filtros or "-", origem or "-", ptp or "-",
                resultado or "-", status))

    # ---------------- adicionar ----------------
    def adicionar():
        existentes = {(l[0], l[1], _interno_da_entrada(l)[0], _tipo_da_entrada(l)) for l in lotes_selecionados}

        if nb.index(nb.select()) == 0:
            sel = tab.selection()
            if not sel:
                messagebox.showwarning("Warning", "Select a batch first", parent=win)
                return
            lote = lotes[int(sel[0])]
            if not internos_atuais:
                entrada = montar_entrada_lote(lote)
                if (entrada[0], entrada[1], None, "opto") not in existentes:
                    lotes_selecionados.append(entrada)
            else:
                marcados = tab_i.selection()
                if not marcados:
                    messagebox.showwarning("Warning", "Select at least one internal lot", parent=win)
                    return
                for item in marcados:
                    interno = internos_atuais[int(item)]
                    status = tab_i.set(item, "Status")
                    if status.startswith("Used in PID"):
                        if not messagebox.askyesno(
                                "Internal lot already used",
                                "Internal lot " + str(interno[2]) + " was already used (" + status + ").\n\n"
                                "Use it again in this deposition?", parent=win):
                            continue
                    entrada = montar_entrada_lote(lote, interno)
                    chave = (entrada[0], entrada[1], entrada[10], "opto")
                    if chave not in existentes:
                        lotes_selecionados.append(entrada)
                        existentes.add(chave)
        else:
            marcados = tab_l.selection()
            if not marcados:
                messagebox.showwarning("Warning", "Select at least one cleaning lot", parent=win)
                return
            for item in marcados:
                limp = limpezas[int(item)]
                status = tab_l.set(item, "Status")
                resultado = (limp[7] or "").strip()
                if resultado and resultado.lower() != "approved":
                    if not messagebox.askyesno(
                            "Cleaning result", "Cleaning lot " + str(limp[1]) + " has result '" + resultado + "'.\n\n"
                            "Use it in this deposition anyway?", parent=win):
                        continue
                if status.startswith("Used in PID"):
                    if not messagebox.askyesno(
                            "Cleaning lot already used",
                            "Cleaning lot " + str(limp[1]) + " was already used (" + status + ").\n\n"
                            "Use it again in this deposition?", parent=win):
                        continue
                entrada = montar_entrada_limpeza(limp)
                chave = (None, entrada[1], entrada[10], "limpeza")
                if chave not in existentes:
                    lotes_selecionados.append(entrada)
                    existentes.add(chave)

        atualizar_lista_lotes_selecionados()
        mostrar_internos()
        mostrar_limpezas()

    tab.bind("<<TreeviewSelect>>", mostrar_internos)
    tab_i.bind("<Double-1>", lambda event: adicionar())
    tab_l.bind("<Double-1>", lambda event: adicionar())

    # já abre no lote da última entrada escolhida
    if lotes_selecionados:
        ultimo = lotes_selecionados[-1]
        if _tipo_da_entrada(ultimo) == "limpeza":
            nb.select(aba_limp)
        else:
            for idx, lote in enumerate(lotes):
                if lote[0] == ultimo[0] and lote[1] == ultimo[1]:
                    tab.selection_set(str(idx))
                    tab.see(str(idx))
                    break
    mostrar_internos()
    mostrar_limpezas()

    botoes = tk.Frame(win, bg=fundo)
    botoes.pack(pady=10)
    ttk.Button(botoes, text="Add selected", command=adicionar).pack(side="left", padx=6)
    ttk.Button(botoes, text="Done", command=win.destroy).pack(side="left", padx=6)


def _responsavel_padrao():
    """Preenche Responsible com o usuário logado (campo continua editável)."""
    if not entry_resp.get().strip():
        entry_resp.insert(0, leptons_auth.nome_responsavel())


def limpar_campos():
    global tarefa_em_edicao_id, anexos_lista
    tarefa_em_edicao_id = None
    anexos_lista = []

    definir_lotes_selecionados([])
    entry_data.delete(0, tk.END)
    entry_data.insert(0, datetime.today().strftime("%Y-%m-%d"))
    entry_resp.delete(0, tk.END)
    entry_resp.insert(0, leptons_auth.nome_responsavel())
    tipo_var.set("Substrate")
    entry_posicao.delete(0, tk.END)
    entry_obs.delete("1.0", tk.END)

    fechar_janelas_teste()
    limpar_inspecao()
    limpar_imersao()
    limpar_eficiencia()
    limpar_signoff()

    for e in [entry_a2, entry_d2, entry_a3, entry_d3, entry_a14, entry_d14, entry_ptp_mass]:
        e.delete(0, tk.END)

    for var in densidade_vars.values():
        var.set("")

    eficiencia_var.set("Não")
    valor_ef_var.set("")
    imersao_var.set("Não")
    lbl_anexos["text"] = "No files"
    lbl_modo["text"] = "Mode: new record"
    atualizar_resumos()



def converter_float(valor):
    """Aceita vírgula ou ponto como separador decimal."""
    valor = str(valor).strip().replace(",", ".")
    if not valor:
        raise ValueError("valor vazio")
    return float(valor)


def calcular_densidade_massa(antes, depois):
    """Calcula (massa depois - massa antes)/área em µg/cm²."""
    massa_antes = converter_float(antes)
    massa_depois = converter_float(depois)
    diferenca_g = massa_depois - massa_antes
    return (diferenca_g * 1_000_000.0) / AREA_FILTRO_CM2


def atualizar_densidades(*args):
    if "densidade_vars" not in globals():
        return
    pares = {
        2: (entry_a2, entry_d2),
        3: (entry_a3, entry_d3),
        14: (entry_a14, entry_d14),
    }
    for pos, (entry_antes, entry_depois) in pares.items():
        try:
            densidade = calcular_densidade_massa(entry_antes.get(), entry_depois.get())
            densidade_vars[pos].set(f"{densidade:.2f}")
        except Exception:
            densidade_vars[pos].set("")

def validar_campos():
    lotes_sel = obter_lotes_selecionados()
    if not lotes_sel:
        messagebox.showwarning("Warning", "Select at least one batch")
        return None

    serial = inspecao_vars["cab"]["box_pid"].get().strip()   # PID identifica a tarefa
    if not serial:
        messagebox.showwarning("Warning", "Enter the PID")
        return None

    if bool(signoff_vars["por"].get().strip()) != bool(signoff_vars["data"].get().strip()):
        messagebox.showwarning("Warning", "Final QA Sign-Off: enter both the name and the date (or leave both empty).")
        return None

    massas = {
        2: (entry_a2.get().strip(), entry_d2.get().strip()),
        3: (entry_a3.get().strip(), entry_d3.get().strip()),
        14: (entry_a14.get().strip(), entry_d14.get().strip())
    }

    densidades = {}
    for pos, (antes, depois) in massas.items():
        if not antes or not depois:
            messagebox.showwarning("Erro", f"Massas faltando na posição {pos} - {nomes_posicoes[pos]}")
            return None
        try:
            densidades[pos] = f"{calcular_densidade_massa(antes, depois):.2f}"
        except Exception:
            messagebox.showwarning("Erro", f"Confira as massas da posição {pos}. Use apenas números.")
            return None

    return {
        "lote_id": lotes_sel[0][0],
        "codigo_lote": "; ".join(
            str(l[1]) + (" (" + str(_interno_da_entrada(l)[1]) + ")" if _interno_da_entrada(l)[1] else "")
            for l in lotes_sel if l[1]),
        "lotes": lotes_sel,
        "serial": serial,
        "data": entry_data.get().strip(),
        "resp": entry_resp.get().strip(),
        "tipo": tipo_var.get(),
        "posicao": entry_posicao.get().strip(),
        "obs": entry_obs.get("1.0", "end").strip(),
        "anexos_txt": ";".join(anexos_lista),
        "eficiencia_ok": eficiencia_var.get(),
        "valor_eficiencia": valor_ef_var.get().strip(),
        "imersao_ok": imersao_var.get(),
        "data_hora_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "massa_ptp_g": entry_ptp_mass.get().strip(),
        "massas": massas,
        "densidades": densidades
    }

# =====================================================
# SALVAR / EDITAR / EXCLUIR
# =====================================================
def salvar_tarefa():
    dados = validar_campos()
    if dados is None:
        return

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO tarefas
        (codigo_tarefa, responsavel, data_inicio, status, descricao,
         lote_entrada_id, codigo_lote, position_range, observacoes, anexos_txt,
         eficiencia_optica_ok, valor_eficiencia, imersao_criogenica_ok, data_hora_registro, massa_ptp_g)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        dados["serial"], dados["resp"], dados["data"], "Cadastrada", dados["tipo"],
        dados["lote_id"], dados["codigo_lote"], dados["posicao"], dados["obs"], dados["anexos_txt"],
        dados["eficiencia_ok"], dados["valor_eficiencia"], dados["imersao_ok"], dados["data_hora_registro"],
        dados["massa_ptp_g"]
    ))

    tarefa_id = cur.lastrowid
    salvar_lotes_db(cur, tarefa_id, dados["lotes"])

    for pos, (antes, depois) in dados["massas"].items():
        cur.execute("""
            INSERT INTO massa_posicoes (id_tarefa, posicao, massa_antes, massa_depois, densidade_massa_ug_cm2)
            VALUES (?, ?, ?, ?, ?)
        """, (tarefa_id, pos, antes, depois, dados["densidades"][pos]))

    salvar_inspecao_db(cur, tarefa_id)
    salvar_imersao_db(cur, tarefa_id)
    salvar_eficiencia_db(cur, tarefa_id)
    salvar_signoff_db(cur, tarefa_id)

    conn.commit()
    conn.close()

    leptons_auth.registrar("TASK_CREATE", f"id={tarefa_id} PID={dados['serial']}")
    messagebox.showinfo("Sucesso", "Tarefa cadastrada!")
    limpar_campos()
    carregar_tarefas()


def carregar_para_edicao():
    global tarefa_em_edicao_id, anexos_lista

    item = tabela.selection()
    if not item:
        messagebox.showwarning("Warning", "Please select a task to edit")
        return

    tarefa_id = tabela.item(item[0], "values")[0]

    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT codigo_tarefa, responsavel, data_inicio, descricao,
               lote_entrada_id, codigo_lote, position_range, observacoes,
               anexos_txt, eficiencia_optica_ok, valor_eficiencia,
               imersao_criogenica_ok, massa_ptp_g
        FROM tarefas
        WHERE id = ?
    """, (tarefa_id,))
    row = cur.fetchone()

    cur.execute("SELECT posicao, massa_antes, massa_depois, densidade_massa_ug_cm2 FROM massa_posicoes WHERE id_tarefa = ?", (tarefa_id,))
    massas = {p: (a, d, dens) for p, a, d, dens in cur.fetchall()}
    conn.close()

    if not row:
        messagebox.showerror("Erro", "Registro não encontrado.")
        return

    limpar_campos()
    tarefa_em_edicao_id = tarefa_id

    conn_i = conectar()
    carregar_inspecao_db(conn_i.cursor(), tarefa_id)
    carregar_imersao_db(conn_i.cursor(), tarefa_id)
    carregar_eficiencia_db(conn_i.cursor(), tarefa_id)
    carregar_signoff_db(conn_i.cursor(), tarefa_id)
    conn_i.close()

    serial, resp, data, tipo, lote_id, codigo_lote, posicao, obs, anexos_txt, ef_ok, val_ef, im_ok, massa_ptp = row

    atualizar_lotes()
    definir_lotes_selecionados(buscar_lotes_da_tarefa(tarefa_id, lote_id, codigo_lote))

    inspecao_vars["cab"]["box_pid"].set(serial or "")
    entry_data.delete(0, tk.END)
    entry_data.insert(0, data or "")
    entry_resp.delete(0, tk.END)
    entry_resp.insert(0, resp or "")
    tipo_var.set(TIPOS_ANTIGOS.get(tipo, tipo) or "Substrate")
    entry_posicao.insert(0, posicao or "")
    entry_obs.insert("1.0", obs or "")

    for pos, (entry_antes, entry_depois) in {
        2: (entry_a2, entry_d2),
        3: (entry_a3, entry_d3),
        14: (entry_a14, entry_d14)
    }.items():
        if pos in massas:
            entry_antes.insert(0, massas[pos][0] or "")
            entry_depois.insert(0, massas[pos][1] or "")
            densidade_vars[pos].set(massas[pos][2] or "")

    eficiencia_var.set(ef_ok or "Não")
    valor_ef_var.set(val_ef or "")
    imersao_var.set(im_ok or "Não")
    entry_ptp_mass.insert(0, massa_ptp or "")
    atualizar_densidades()
    atualizar_resumos()

    anexos_lista = anexos_txt.split(";") if anexos_txt else []
    lbl_anexos["text"] = f"{len(anexos_lista)} arquivo(s) anexado(s)" if anexos_lista else "No files"
    lbl_modo["text"] = f"Mode: editing ID {tarefa_id}"


def editar_tarefa():
    global tarefa_em_edicao_id

    if tarefa_em_edicao_id is None:
        messagebox.showwarning("Warning", "Load a selected task for editing first.")
        return

    dados = validar_campos()
    if dados is None:
        return

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        UPDATE tarefas
        SET codigo_tarefa = ?, responsavel = ?, data_inicio = ?, descricao = ?,
            lote_entrada_id = ?, codigo_lote = ?, position_range = ?, observacoes = ?,
            anexos_txt = ?, eficiencia_optica_ok = ?, valor_eficiencia = ?,
            imersao_criogenica_ok = ?, data_hora_registro = ?, massa_ptp_g = ?
        WHERE id = ?
    """, (
        dados["serial"], dados["resp"], dados["data"], dados["tipo"],
        dados["lote_id"], dados["codigo_lote"], dados["posicao"], dados["obs"],
        dados["anexos_txt"], dados["eficiencia_ok"], dados["valor_eficiencia"],
        dados["imersao_ok"], dados["data_hora_registro"], dados["massa_ptp_g"], tarefa_em_edicao_id
    ))

    salvar_lotes_db(cur, tarefa_em_edicao_id, dados["lotes"])

    cur.execute("DELETE FROM massa_posicoes WHERE id_tarefa = ?", (tarefa_em_edicao_id,))
    for pos, (antes, depois) in dados["massas"].items():
        cur.execute("""
            INSERT INTO massa_posicoes (id_tarefa, posicao, massa_antes, massa_depois, densidade_massa_ug_cm2)
            VALUES (?, ?, ?, ?, ?)
        """, (tarefa_em_edicao_id, pos, antes, depois, dados["densidades"][pos]))

    salvar_inspecao_db(cur, tarefa_em_edicao_id)
    salvar_imersao_db(cur, tarefa_em_edicao_id)
    salvar_eficiencia_db(cur, tarefa_em_edicao_id)
    salvar_signoff_db(cur, tarefa_em_edicao_id)

    conn.commit()
    conn.close()

    leptons_auth.registrar("TASK_UPDATE", f"id={tarefa_em_edicao_id} PID={dados['serial']}")
    messagebox.showinfo("Sucesso", "Registro atualizado!")
    limpar_campos()
    carregar_tarefas()


def excluir_tarefa():
    item = tabela.selection()
    if not item:
        messagebox.showwarning("Warning", "Please select a task to delete")
        return

    tarefa_id = tabela.item(item[0], "values")[0]
    ok = messagebox.askyesno("Confirmar exclusão", f"Excluir a tarefa ID {tarefa_id}?")
    if not ok:
        return

    conn = conectar()
    cur = conn.cursor()
    _pid_excluido = (cur.execute("SELECT codigo_tarefa FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone() or ("",))[0]
    cur.execute("DELETE FROM massa_posicoes WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM inspecao_visual_cab WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM inspecao_visual_filtros WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM imersao_massas WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM imersao_itens WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM tarefa_lotes WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM eficiencia_teste WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM eficiencia_amostras WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM tarefas WHERE id = ?", (tarefa_id,))
    conn.commit()
    conn.close()
    leptons_auth.registrar("TASK_DELETE", f"id={tarefa_id} PID={_pid_excluido}")

    messagebox.showinfo("Sucesso", "Registro excluído.")
    limpar_campos()
    carregar_tarefas()

# =====================================================
# QR CODE / DETALHES
# =====================================================
def _tarefa_selecionada():
    item = tabela.selection()
    if not item:
        messagebox.showwarning("Warning", "Please select a task")
        return None
    return int(tabela.item(item[0], "values")[0])


def _fonte_qr(tamanho, negrito=True):
    """Fonte TrueType disponível no sistema (Windows/Linux/macOS), com fallback."""
    nomes = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf"] if negrito
             else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"])
    for n in nomes:
        try:
            return ImageFont.truetype(n, tamanho)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=tamanho)
    except Exception:
        return ImageFont.load_default()


def gerar_imagem_qr(url, pid, caminho):
    """Cria o PNG do QR com o PID da tarefa impresso logo abaixo."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    larg, alt = img_qr.size
    pid = (pid or "").strip()
    if not pid:
        img_qr.save(caminho)
        return caminho

    margem = 20
    tam = 44
    fonte = _fonte_qr(tam)
    medidor = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while tam > 12:
        caixa = medidor.textbbox((0, 0), pid, font=fonte)
        if caixa[2] - caixa[0] <= larg - 2 * margem:
            break
        tam -= 2
        fonte = _fonte_qr(tam)
    caixa = medidor.textbbox((0, 0), pid, font=fonte)
    larg_txt, alt_txt = caixa[2] - caixa[0], caixa[3] - caixa[1]

    faixa = alt_txt + 2 * margem
    final = Image.new("RGB", (larg, alt + faixa), "white")
    final.paste(img_qr, (0, 0))
    d = ImageDraw.Draw(final)
    # a borda branca do QR (4 módulos) já separa o texto; sobe um pouco o texto
    x = (larg - larg_txt) // 2 - caixa[0]
    y = alt - 10 + (faixa - alt_txt) // 2 - caixa[1]
    d.text((x, y), pid, fill="black", font=fonte)
    final.save(caminho)
    return caminho


def gerar_qr():
    """Gera o QR code que abre a página de opções do relatório da tarefa selecionada."""
    tarefa_id = _tarefa_selecionada()
    if tarefa_id is None:
        return

    preparado = _preparar_relatorio(tarefa_id)
    if preparado is None:
        return
    url, preview, aviso = preparado

    dados_qr = coletar_dados_relatorio(tarefa_id) or {}
    pid = ((dados_qr.get("tarefa") or {}).get("codigo_tarefa") or "").strip()
    nome = f"qr_tarefa_{tarefa_id}.png"
    gerar_imagem_qr(url, pid, nome)

    win = tk.Toplevel(janela)
    win.title(f"QR Code - task {tarefa_id}")
    win.configure(bg="#f4f6f8")
    win.transient(janela)
    win.resizable(False, False)

    try:
        imagem = Image.open(nome)
        proporcao = 300 / imagem.size[0]
        foto = ImageTk.PhotoImage(imagem.resize((300, max(1, int(imagem.size[1] * proporcao)))))
        lbl = tk.Label(win, image=foto, bg="#f4f6f8")
        lbl.image = foto
        lbl.pack(padx=20, pady=(16, 6))
    except Exception:
        pass

    tk.Label(win, text="Scan to open the report options", bg="#f4f6f8",
             font=("Segoe UI", 10, "bold")).pack()
    var_url = tk.StringVar(value=url)
    ent = ttk.Entry(win, textvariable=var_url, width=62, state="readonly")
    ent.pack(padx=20, pady=(8, 4))
    tk.Label(win, text=aviso, bg="#f4f6f8", fg="#555555", font=("Segoe UI", 8),
             wraplength=440, justify="left").pack(padx=20, pady=(0, 6))
    tk.Label(win, text=f"QR image saved as: {os.path.abspath(nome)}", bg="#f4f6f8", fg="#555555",
             font=("Segoe UI", 8), wraplength=440, justify="left").pack(padx=20)

    def copiar():
        janela.clipboard_clear()
        janela.clipboard_append(url)

    botoes = tk.Frame(win, bg="#f4f6f8")
    botoes.pack(pady=12)
    ttk.Button(botoes, text="Copy link", command=copiar).pack(side="left", padx=6)
    ttk.Button(botoes, text="Open report", command=lambda: webbrowser.open(preview)).pack(side="left", padx=6)
    ttk.Button(botoes, text="Close", command=win.destroy).pack(side="left", padx=6)


def abrir_relatorio():
    """Abre no navegador a página de opções (relatório) da tarefa selecionada."""
    tarefa_id = _tarefa_selecionada()
    if tarefa_id is None:
        return
    preparado = _preparar_relatorio(tarefa_id)
    if preparado is not None:
        webbrowser.open(preparado[1])


def abrir_detalhes_tarefa():
    item = tabela.selection()
    if not item:
        messagebox.showwarning("Warning", "Please select a task")
        return

    tarefa_id = tabela.item(item[0], "values")[0]
    dados = buscar_dados_qr(tarefa_id)

    if not dados:
        messagebox.showinfo("Info", "No data found")
        return

    win = tk.Toplevel(janela)
    win.title(f"Task {dados[0]}")
    win.geometry("560x780")
    win.configure(bg="#f4f6f8")

    tk.Label(win, text="Task Details", font=("Segoe UI", 14, "bold"), bg="#f4f6f8").pack(pady=12)
    frame_info = tk.Frame(win, bg="#f4f6f8", padx=20, pady=10)
    frame_info.pack(fill="both", expand=True)

    def linha(rotulo, valor):
        tk.Label(frame_info, text=rotulo, font=("Segoe UI", 10, "bold"), bg="#f4f6f8").pack(anchor="w", pady=(8, 0))
        tk.Label(frame_info, text=valor if valor else "-", font=("Segoe UI", 10), bg="#f4f6f8").pack(anchor="w")

    linha("PID:", dados[0])
    linha("Responsible:", dados[1])
    linha("Deposition date:", dados[2])
    linha("Filter type:", dados[3])
    try:
        entradas_t = buscar_lotes_da_tarefa(int(tarefa_id), None, None)
    except Exception:
        entradas_t = []
    codigos_usados = [_interno_da_entrada(l)[1] for l in entradas_t if _interno_da_entrada(l)[1]]
    lote_txt = "; ".join(
        str(l[1]) + (" (" + str(_interno_da_entrada(l)[1]) + ")" if _interno_da_entrada(l)[1] else "")
        for l in entradas_t if l[1]) or dados[4]
    linha("Batch:", lote_txt)
    linha("Internal lot used:", ", ".join(codigos_usados))
    linha("Positions:", dados[5])
    linha("Observations:", dados[6])
    linha("Optical efficiency approved?", SIM_NAO.get(dados[7], dados[7]))
    linha("Efficiency value:", dados[8])
    linha("Cryogenic immersion OK?", SIM_NAO.get(dados[9], dados[9]))
    linha("Record date/time:", dados[10])
    linha("PTP Mass (g):", dados[11])

    tk.Button(win, text="Close", command=win.destroy, bg="#2e6f95", fg="white", relief="flat", padx=14, pady=5).pack(pady=15)

# =====================================================
# INSPEÇÃO VISUAL / TESTES DE QUALIDADE
# =====================================================
def criar_variaveis_inspecao():
    """Cria as variáveis da inspeção visual (precisa da janela principal já criada)."""
    inspecao_vars["cab"] = {k: tk.StringVar(master=janela, value="") for k in CAMPOS_CABECALHO}
    inspecao_vars["filtros"] = {
        n: {c: tk.StringVar(master=janela, value="") for c in CAMPOS_FILTRO}
        for n in range(1, N_FILTROS + 1)
    }
    for linha in inspecao_vars["filtros"].values():
        for var in linha.values():
            var.trace_add("write", atualizar_resumos)


def limpar_inspecao(cabecalho=True, filtros=True):
    if not inspecao_vars:
        return
    if cabecalho:
        for var in inspecao_vars["cab"].values():
            var.set("")
    if filtros:
        for linha in inspecao_vars["filtros"].values():
            for var in linha.values():
                var.set("")


def inspecao_para_dict():
    cab = {k: inspecao_vars["cab"][k].get().strip() for k in CAMPOS_CABECALHO}
    cab["inspector"] = entry_resp.get().strip()      # "Inspector name" do formulário = Responsible
    filtros = {
        n: {c: inspecao_vars["filtros"][n][c].get().strip() for c in CAMPOS_FILTRO}
        for n in range(1, N_FILTROS + 1)
    }
    return cab, filtros


def salvar_inspecao_db(cur, tarefa_id):
    cab, filtros = inspecao_para_dict()

    cur.execute("DELETE FROM inspecao_visual_cab WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM inspecao_visual_filtros WHERE id_tarefa = ?", (tarefa_id,))

    cur.execute("""
        INSERT INTO inspecao_visual_cab
        (id_tarefa, box_pid, run_evaporation, inspector, pid_p02, pid_p03, pid_p14, notes,
         data_inspecao, operador, supervisor, data_revisao, revisado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (tarefa_id, *[cab[k] for k in CAMPOS_CABECALHO]))

    for n, v in filtros.items():
        cur.execute("""
            INSERT INTO inspecao_visual_filtros
            (id_tarefa, filtro, visual_status, uniformity, stains, particles,
             edge_defects, finger_defects, other_defects, comments, classification)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tarefa_id, n, *[v[c] for c in CAMPOS_FILTRO]))


def carregar_inspecao_db(cur, tarefa_id):
    limpar_inspecao()

    cur.execute("""
        SELECT box_pid, run_evaporation, inspector, pid_p02, pid_p03, pid_p14, notes,
               data_inspecao, operador, supervisor, data_revisao, revisado
        FROM inspecao_visual_cab WHERE id_tarefa = ?
    """, (tarefa_id,))
    row = cur.fetchone()
    if row:
        for k, valor in zip(CAMPOS_CABECALHO, row):
            inspecao_vars["cab"][k].set(valor or "")

    cur.execute("""
        SELECT filtro, visual_status, uniformity, stains, particles,
               edge_defects, finger_defects, other_defects, comments, classification
        FROM inspecao_visual_filtros WHERE id_tarefa = ?
    """, (tarefa_id,))
    for row in cur.fetchall():
        n = row[0]
        if n in inspecao_vars["filtros"]:
            for c, valor in zip(CAMPOS_FILTRO, row[1:]):
                inspecao_vars["filtros"][n][c].set(valor or "")


def texto_resumo_inspecao():
    completos = 0
    algum = False
    contagem = {"A": 0, "B": 0, "C": 0}
    for n in range(1, N_FILTROS + 1):
        v = inspecao_vars["filtros"][n]
        valores = [v[c].get() for c in CAMPOS_OBRIGATORIOS]
        if all(valores):
            completos += 1
        if any(valores) or v["comments"].get():
            algum = True
        if v["classification"].get() in contagem:
            contagem[v["classification"].get()] += 1
    if not algum:
        return "Not filled"
    return f"{completos}/{N_FILTROS} filters complete  |  A: {contagem['A']}   B: {contagem['B']}   C: {contagem['C']}"


def atualizar_resumos(*args):
    """Atualiza os textos de status dos botões do painel Quality Test."""
    if not inspecao_vars:
        return
    try:
        texto = texto_resumo_inspecao()
        lbl_status_visual.config(text=texto)
        lbl_status_crio.config(text=texto_resumo_imersao())
        lbl_status_ef.config(text=texto_resumo_eficiencia())
    except (NameError, tk.TclError):
        return
    if lbl_resumo_visual_win is not None:
        try:
            lbl_resumo_visual_win.config(text=texto)
        except tk.TclError:
            pass


def fechar_janela_inspecao(salvar_notas=True):
    global janela_inspecao, txt_notas_inspecao, lbl_resumo_visual_win
    if janela_inspecao is not None:
        try:
            if salvar_notas and txt_notas_inspecao is not None:
                inspecao_vars["cab"]["notes"].set(txt_notas_inspecao.get("1.0", "end").strip())
            if janela_inspecao.winfo_exists():
                janela_inspecao.destroy()
        except tk.TclError:
            pass
    janela_inspecao = None
    txt_notas_inspecao = None
    lbl_resumo_visual_win = None


def fechar_janelas_teste():
    fechar_janela_inspecao(salvar_notas=False)
    fechar_janela_imersao(salvar_obs=False)
    fechar_janela_eficiencia(salvar_obs=False)


def _montar_revisao_supervisor(win, bg, var_nome, var_data, var_revisado):
    """Bloco 'Technical Supervisor review' (igual ao da eficiência óptica), empacotado na parte de baixo."""
    quadro = tk.LabelFrame(win, text="Technical Supervisor review", bg=bg,
                           font=("Segoe UI", 10, "bold"), padx=10, pady=6)
    quadro.pack(side="bottom", fill="x", padx=12, pady=(4, 0))
    tk.Label(quadro, text="Name:", bg=bg, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Entry(quadro, textvariable=var_nome, width=28).grid(row=0, column=1, padx=(6, 20))
    tk.Label(quadro, text="Date:", bg=bg, font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w")
    ttk.Entry(quadro, textvariable=var_data, width=14).grid(row=0, column=3, padx=(6, 4))
    ttk.Button(quadro, text="Today", width=7,
               command=lambda: var_data.set(datetime.today().strftime("%Y-%m-%d"))).grid(row=0, column=4, padx=(0, 20))
    tk.Checkbutton(quadro, text="Reviewed and signed", variable=var_revisado, onvalue="Yes", offvalue="",
                   bg=bg, activebackground=bg, font=("Segoe UI", 9, "bold")).grid(row=0, column=5)
    tk.Label(quadro, text="The decision is final only after the Technical Supervisor signs the record.",
             bg=bg, fg="#777777", font=("Segoe UI", 8)).grid(row=1, column=0, columnspan=6, sticky="w", pady=(4, 0))
    return quadro


def abrir_inspecao_visual():
    """Janela com o formulário 'Deposition Inspection Record' (28 filtros)."""
    global janela_inspecao, txt_notas_inspecao, lbl_resumo_visual_win

    if janela_inspecao is not None and janela_inspecao.winfo_exists():
        janela_inspecao.deiconify()
        janela_inspecao.lift()
        janela_inspecao.focus_force()
        return

    BG = "#f4f6f8"
    win = tk.Toplevel(janela)
    janela_inspecao = win
    win.title("Visual Inspection - Deposition Inspection Record")
    win.geometry("1200x860")
    win.configure(bg=BG)
    win.transient(janela)
    win.protocol("WM_DELETE_WINDOW", fechar_janela_inspecao)

    # ---------- título ----------
    topo = tk.Frame(win, bg="#1f3a5f")
    topo.pack(fill="x")
    tk.Label(topo, text="DUNE HD – X-ARAPUCA PTP FILMS", fg="white", bg="#1f3a5f",
             font=("Segoe UI", 13, "bold")).pack(pady=(8, 0))
    tk.Label(topo, text="DEPOSITION INSPECTION RECORD  |  Inspection of Evaporated PTP Film",
             fg="#d6e2f0", bg="#1f3a5f", font=("Segoe UI", 10)).pack(pady=(0, 8))

    # ---------- data e responsável pelo procedimento ----------
    cv = inspecao_vars["cab"]
    quadro_proc = tk.LabelFrame(win, text="Procedure", bg=BG, font=("Segoe UI", 10, "bold"), padx=10, pady=6)
    quadro_proc.pack(fill="x", padx=12, pady=(10, 0))
    tk.Label(quadro_proc, text="Inspection date (YYYY-MM-DD):", bg=BG, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Entry(quadro_proc, textvariable=cv["data_inspecao"], width=14).grid(row=0, column=1, padx=(6, 4))
    ttk.Button(quadro_proc, text="Today", width=7,
               command=lambda: cv["data_inspecao"].set(datetime.today().strftime("%Y-%m-%d"))).grid(row=0, column=2, padx=(0, 28))
    tk.Label(quadro_proc, text="Performed by (operator):", bg=BG, font=("Segoe UI", 9, "bold")).grid(row=0, column=3, sticky="w")
    ttk.Entry(quadro_proc, textvariable=cv["operador"], width=32).grid(row=0, column=4, padx=6)

    # ---------- rodapé (empacotado antes da tabela para ficar sempre visível) ----------
    barra_inf = tk.Frame(win, bg=BG)
    barra_inf.pack(side="bottom", fill="x", padx=12, pady=(4, 10))

    lbl_resumo_visual_win = tk.Label(barra_inf, text=texto_resumo_inspecao(), bg=BG, fg="#1f3a5f",
                                     font=("Segoe UI", 10, "bold"))
    lbl_resumo_visual_win.pack(side="left")

    ttk.Button(barra_inf, text="Save & close", command=fechar_janela_inspecao).pack(side="right", padx=(8, 0))

    def limpar_tabela():
        if messagebox.askyesno("Clear table", "Clear all 28 rows of the inspection table?", parent=win):
            limpar_inspecao(cabecalho=False, filtros=True)

    ttk.Button(barra_inf, text="Clear table", command=limpar_tabela).pack(side="right")
    tk.Label(barra_inf, text="Data is stored in the database when you use Save / Edit on the main screen.   ",
             bg=BG, fg="#777777", font=("Segoe UI", 8)).pack(side="right")

    # ---------- revisão do supervisor técnico ----------
    _montar_revisao_supervisor(win, BG, cv["supervisor"], cv["data_revisao"], cv["revisado"])

    # ---------- legenda de classificação ----------
    legenda = tk.LabelFrame(win, text="Classification", bg=BG, font=("Segoe UI", 10, "bold"), padx=10, pady=4)
    legenda.pack(side="bottom", fill="x", padx=12, pady=(4, 0))
    linhas_legenda = [
        ("A", "Defects affecting coating integrity, adhesion, or optical performance.", "Reject glass substrate"),
        ("B", "Localized defects with limited impact requiring evaluation.", "QA/QC review"),
        ("C", "Minor cosmetic defects with no expected impact on performance.", "Accept"),
    ]
    for i, (cl, desc, disp) in enumerate(linhas_legenda):
        tk.Label(legenda, text=cl, bg=BG, fg=CORES_CLASSE[cl], font=("Segoe UI", 10, "bold"), width=3).grid(row=i, column=0)
        tk.Label(legenda, text=desc, bg=BG, anchor="w", font=("Segoe UI", 9)).grid(row=i, column=1, sticky="w", padx=6)
        tk.Label(legenda, text="→  " + disp, bg=BG, anchor="w", font=("Segoe UI", 9, "bold")).grid(row=i, column=2, sticky="w", padx=12)

    # ---------- 2. tabela de inspeção visual ----------
    quadro_tab = tk.LabelFrame(win, text="Visual inspection table", bg=BG,
                               font=("Segoe UI", 10, "bold"), padx=6, pady=6)
    quadro_tab.pack(fill="both", expand=True, padx=12, pady=(10, 4))

    cab_tab = tk.Frame(quadro_tab, bg="#1f3a5f")
    cab_tab.pack(fill="x")
    for i, (campo, titulo, largura, opcoes) in enumerate(COLUNAS_INSPECAO):
        cel = tk.Frame(cab_tab, width=largura, height=38, bg="#1f3a5f")
        cel.grid(row=0, column=i, padx=(0, 1))
        cel.pack_propagate(False)
        tk.Label(cel, text=titulo, bg="#1f3a5f", fg="white", font=("Segoe UI", 9, "bold")).pack(expand=True)

    corpo = tk.Frame(quadro_tab, bg=BG)
    corpo.pack(fill="both", expand=True)
    canvas = tk.Canvas(corpo, bg=BG, highlightthickness=0)
    barra_rolagem = ttk.Scrollbar(corpo, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=barra_rolagem.set)
    barra_rolagem.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    interno = tk.Frame(canvas, bg=BG)
    canvas.create_window((0, 0), window=interno, anchor="nw")
    interno.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    def rolar(event):
        if getattr(event, "num", None) == 4:
            canvas.yview_scroll(-2, "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(2, "units")
        else:
            canvas.yview_scroll(-2 if event.delta > 0 else 2, "units")

    win.bind("<MouseWheel>", rolar)
    win.bind("<Button-4>", rolar)
    win.bind("<Button-5>", rolar)

    def limpar_linha(n):
        for c in CAMPOS_FILTRO:
            inspecao_vars["filtros"][n][c].set("")

    for n in range(1, N_FILTROS + 1):
        v = inspecao_vars["filtros"][n]
        bg = "#ffffff" if n % 2 else "#e8eef5"
        for i, (campo, titulo, largura, opcoes) in enumerate(COLUNAS_INSPECAO):
            cel = tk.Frame(interno, width=largura, height=30, bg=bg)
            cel.grid(row=n - 1, column=i, padx=(0, 1), pady=(0, 1))
            cel.pack_propagate(False)

            if campo == "filter":
                tk.Label(cel, text=f"{n:02d}", bg=bg, font=("Segoe UI", 9, "bold")).pack(expand=True)
            elif opcoes:
                for op in opcoes:
                    tk.Radiobutton(
                        cel, text=op, value=op, variable=v[campo],
                        bg=bg, activebackground=bg, selectcolor="white",
                        fg=CORES_CLASSE.get(op, "#000000") if campo == "classification" else "#000000",
                        font=("Segoe UI", 8, "bold" if campo == "classification" else "normal"),
                        bd=0, highlightthickness=0, padx=2,
                        tristatevalue="__none__"
                    ).pack(side="left", expand=True)
            elif campo == "comments":
                tk.Entry(cel, textvariable=v["comments"], font=("Segoe UI", 9), relief="solid", bd=1).pack(
                    fill="both", expand=True, padx=2, pady=2)
            elif campo == "clear":
                tk.Button(cel, text="✕", command=lambda n=n: limpar_linha(n), bg=bg, fg="#888888",
                          relief="flat", bd=0, font=("Segoe UI", 8), cursor="hand2").pack(expand=True)


# ---------------- Imersão criogênica ----------------
def criar_variaveis_imersao():
    """Variáveis da imersão criogênica (precisa da janela principal já criada)."""
    imersao_vars["massas"] = {
        amostra: {
            "antes": tk.StringVar(master=janela, value=""),
            "depois": tk.StringVar(master=janela, value=""),
            "dif": tk.StringVar(master=janela, value="-"),
            "cond": tk.StringVar(master=janela, value="-"),
        }
        for amostra in AMOSTRAS_IMERSAO
    }
    imersao_vars["itens"] = {chave: tk.StringVar(master=janela, value="") for chave, *_ in ITENS_IMERSAO}
    imersao_vars["obs"] = tk.StringVar(master=janela, value="")
    imersao_vars["data"] = tk.StringVar(master=janela, value="")
    imersao_vars["operador"] = tk.StringVar(master=janela, value="")
    imersao_vars["supervisor"] = tk.StringVar(master=janela, value="")
    imersao_vars["data_revisao"] = tk.StringVar(master=janela, value="")
    imersao_vars["revisado"] = tk.StringVar(master=janela, value="")
    imersao_vars["revisado"].trace_add("write", recalcular_imersao)

    for v in imersao_vars["massas"].values():
        v["antes"].trace_add("write", recalcular_imersao)
        v["depois"].trace_add("write", recalcular_imersao)
    for var in imersao_vars["itens"].values():
        var.trace_add("write", recalcular_imersao)


def limpar_imersao():
    if not imersao_vars:
        return
    for v in imersao_vars["massas"].values():
        v["antes"].set("")
        v["depois"].set("")
    for var in imersao_vars["itens"].values():
        var.set("")
    imersao_vars["obs"].set("")
    imersao_vars["data"].set("")
    imersao_vars["operador"].set("")
    imersao_vars["supervisor"].set("")
    imersao_vars["data_revisao"].set("")
    imersao_vars["revisado"].set("")


def calcular_amostra_imersao(antes, depois):
    """Retorna (diferença em g, diferença em %, aprovado). Aprovado se a perda de massa <= 5 %."""
    massa_antes = converter_float(antes)
    massa_depois = converter_float(depois)
    if massa_antes <= 0:
        raise ValueError("massa antes deve ser maior que zero")
    dif = massa_depois - massa_antes
    pct = dif / massa_antes * 100.0
    return dif, pct, round(pct, 6) >= -LIMITE_PERDA_PCT


def estado_imersao():
    """Retorna (estado, preenchidos, total); estado em empty / partial / approved / rejected."""
    total = len(AMOSTRAS_IMERSAO) + len(ITENS_IMERSAO)
    preenchidos = 0
    reprovado = False
    algum = bool(imersao_vars["obs"].get().strip())

    for amostra in AMOSTRAS_IMERSAO:
        v = imersao_vars["massas"][amostra]
        if v["antes"].get().strip() or v["depois"].get().strip():
            algum = True
        try:
            _, _, ok = calcular_amostra_imersao(v["antes"].get(), v["depois"].get())
            preenchidos += 1
            if not ok:
                reprovado = True
        except Exception:
            pass

    for chave, *_ in ITENS_IMERSAO:
        valor = imersao_vars["itens"][chave].get()
        if valor:
            algum = True
            preenchidos += 1
        if valor == "No":
            reprovado = True

    if reprovado:
        return "rejected", preenchidos, total
    if preenchidos == total:
        return "approved", preenchidos, total
    return ("partial" if algum else "empty"), preenchidos, total


def texto_resumo_imersao():
    if not imersao_vars:
        return ""
    estado, preenchidos, total = estado_imersao()
    pendente = "" if imersao_vars["revisado"].get() else "  – pending review"
    if estado == "approved":
        return "Approved  (all criteria met)" + pendente
    if estado == "rejected":
        return f"Rejected  ({preenchidos}/{total} items filled)" + pendente
    if estado == "partial":
        return f"In progress: {preenchidos}/{total} items filled"
    # sem dados novos: mantém o valor manual de registros antigos
    return "Immersion OK: Yes" if imersao_var.get() == "Sim" else "Not filled"


def _pintar_imersao():
    """Atualiza cores e o resultado geral na janela de imersão (se estiver aberta)."""
    cores = {"Approved": "#2e7d32", "Rejected": "#c62828"}
    for amostra in AMOSTRAS_IMERSAO:
        lbl = widgets_imersao.get(amostra)
        if lbl is not None:
            try:
                lbl.config(fg=cores.get(imersao_vars["massas"][amostra]["cond"].get(), "#888888"))
            except tk.TclError:
                pass

    lbl = widgets_imersao.get("resultado")
    if lbl is not None:
        estado, preenchidos, total = estado_imersao()
        revisao = "reviewed" if imersao_vars["revisado"].get() else "pending supervisor review"
        textos = {
            "approved": ("Overall result: APPROVED  (" + revisao + ")", "#2e7d32"),
            "rejected": ("Overall result: REJECTED  (" + revisao + ")", "#c62828"),
            "partial": (f"Overall result: in progress ({preenchidos}/{total} filled)", "#1f3a5f"),
            "empty": ("Overall result: not evaluated", "#888888"),
        }
        texto, cor = textos[estado]
        try:
            lbl.config(text=texto, fg=cor)
        except tk.TclError:
            pass


def recalcular_imersao(*args):
    """Recalcula diferença/condição de cada amostra e o resultado geral."""
    if not imersao_vars:
        return
    for amostra in AMOSTRAS_IMERSAO:
        v = imersao_vars["massas"][amostra]
        try:
            dif, pct, ok = calcular_amostra_imersao(v["antes"].get(), v["depois"].get())
            v["dif"].set(f"{dif:+.5f} g   ({pct:+.2f} %)")
            v["cond"].set("Approved" if ok else "Rejected")
        except Exception:
            v["dif"].set("-")
            v["cond"].set("-")

    _pintar_imersao()

    estado, _, _ = estado_imersao()
    novo = "Sim" if estado == "approved" else "Não"
    if imersao_var.get() != novo:
        imersao_var.set(novo)      # dispara atualizar_resumos
    atualizar_resumos()


def salvar_imersao_db(cur, tarefa_id):
    cur.execute("DELETE FROM imersao_massas WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM imersao_itens WHERE id_tarefa = ?", (tarefa_id,))

    for amostra in AMOSTRAS_IMERSAO:
        v = imersao_vars["massas"][amostra]
        try:
            dif, pct, ok = calcular_amostra_imersao(v["antes"].get(), v["depois"].get())
            dif_g, dif_pct, aprovado = f"{dif:.5f}", f"{pct:.2f}", ("Yes" if ok else "No")
        except Exception:
            dif_g, dif_pct, aprovado = "", "", ""
        cur.execute("""
            INSERT INTO imersao_massas
            (id_tarefa, amostra, massa_antes, massa_depois, diferenca_g, diferenca_pct, aprovado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tarefa_id, amostra, v["antes"].get().strip(), v["depois"].get().strip(), dif_g, dif_pct, aprovado))

    for chave, *_ in ITENS_IMERSAO:
        cur.execute("INSERT INTO imersao_itens (id_tarefa, item, aprovado) VALUES (?, ?, ?)",
                    (tarefa_id, chave, imersao_vars["itens"][chave].get()))

    cur.execute("UPDATE tarefas SET imersao_observacoes = ?, imersao_data = ?, imersao_operador = ?, "
                "imersao_supervisor = ?, imersao_data_revisao = ?, imersao_revisado = ? WHERE id = ?",
                (imersao_vars["obs"].get().strip(), imersao_vars["data"].get().strip(),
                 imersao_vars["operador"].get().strip(), imersao_vars["supervisor"].get().strip(),
                 imersao_vars["data_revisao"].get().strip(), imersao_vars["revisado"].get().strip(), tarefa_id))


def carregar_imersao_db(cur, tarefa_id):
    limpar_imersao()

    cur.execute("SELECT amostra, massa_antes, massa_depois FROM imersao_massas WHERE id_tarefa = ?", (tarefa_id,))
    for amostra, antes, depois in cur.fetchall():
        if amostra in imersao_vars["massas"]:
            imersao_vars["massas"][amostra]["antes"].set(antes or "")
            imersao_vars["massas"][amostra]["depois"].set(depois or "")

    cur.execute("SELECT item, aprovado FROM imersao_itens WHERE id_tarefa = ?", (tarefa_id,))
    for chave, aprovado in cur.fetchall():
        if chave in imersao_vars["itens"]:
            imersao_vars["itens"][chave].set(aprovado or "")

    cur.execute("SELECT imersao_observacoes, imersao_data, imersao_operador, imersao_supervisor, "
                "imersao_data_revisao, imersao_revisado FROM tarefas WHERE id = ?", (tarefa_id,))
    row = cur.fetchone()
    for chave, indice in (("obs", 0), ("data", 1), ("operador", 2), ("supervisor", 3),
                          ("data_revisao", 4), ("revisado", 5)):
        imersao_vars[chave].set((row[indice] if row else "") or "")


def fechar_janela_imersao(salvar_obs=True):
    global janela_imersao, txt_obs_imersao
    if janela_imersao is not None:
        try:
            if salvar_obs and txt_obs_imersao is not None:
                imersao_vars["obs"].set(txt_obs_imersao.get("1.0", "end").strip())
            if janela_imersao.winfo_exists():
                janela_imersao.destroy()
        except tk.TclError:
            pass
    janela_imersao = None
    txt_obs_imersao = None
    widgets_imersao.clear()


def abrir_imersao_criogenica():
    """Janela de imersão criogênica: massas dos substratos de controle + critérios de aceitação."""
    global janela_imersao, txt_obs_imersao

    if janela_imersao is not None and janela_imersao.winfo_exists():
        janela_imersao.deiconify()
        janela_imersao.lift()
        janela_imersao.focus_force()
        return

    BG = "#f4f6f8"
    AZUL = "#1f3a5f"
    LINHA_ALT = "#dce6f2"

    win = tk.Toplevel(janela)
    janela_imersao = win
    win.title("Cryogenic Immersion")
    win.geometry("1040x860")
    win.configure(bg=BG)
    win.transient(janela)
    win.protocol("WM_DELETE_WINDOW", fechar_janela_imersao)

    # ---------- título ----------
    topo = tk.Frame(win, bg=AZUL)
    topo.pack(fill="x")
    tk.Label(topo, text="CRYOGENIC IMMERSION", fg="white", bg=AZUL,
             font=("Segoe UI", 13, "bold")).pack(pady=(8, 0))
    tk.Label(topo, text="Control substrates P02, P03, P14  |  Mass loss and post-immersion inspection",
             fg="#d6e2f0", bg=AZUL, font=("Segoe UI", 10)).pack(pady=(0, 8))

    # ---------- data e responsável pelo procedimento ----------
    quadro_proc = tk.LabelFrame(win, text="Procedure", bg=BG, font=("Segoe UI", 10, "bold"), padx=10, pady=6)
    quadro_proc.pack(fill="x", padx=12, pady=(10, 0))
    tk.Label(quadro_proc, text="Test date (YYYY-MM-DD):", bg=BG, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Entry(quadro_proc, textvariable=imersao_vars["data"], width=14).grid(row=0, column=1, padx=(6, 4))
    ttk.Button(quadro_proc, text="Today", width=7,
               command=lambda: imersao_vars["data"].set(datetime.today().strftime("%Y-%m-%d"))).grid(row=0, column=2, padx=(0, 28))
    tk.Label(quadro_proc, text="Performed by (operator):", bg=BG, font=("Segoe UI", 9, "bold")).grid(row=0, column=3, sticky="w")
    ttk.Entry(quadro_proc, textvariable=imersao_vars["operador"], width=32).grid(row=0, column=4, padx=6)

    # ---------- rodapé e observações (empacotados antes, para ficarem sempre visíveis) ----------
    barra_inf = tk.Frame(win, bg=BG)
    barra_inf.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
    lbl_resultado = tk.Label(barra_inf, text="", bg=BG, font=("Segoe UI", 11, "bold"))
    lbl_resultado.pack(side="left")
    widgets_imersao["resultado"] = lbl_resultado
    ttk.Button(barra_inf, text="Save & close", command=fechar_janela_imersao).pack(side="right", padx=(8, 0))
    tk.Label(barra_inf, text="Data is stored in the database when you use Save / Edit on the main screen.   ",
             bg=BG, fg="#777777", font=("Segoe UI", 8)).pack(side="right")

    quadro_obs = tk.LabelFrame(win, text="Observations", bg=BG, font=("Segoe UI", 10, "bold"), padx=10, pady=6)
    quadro_obs.pack(side="bottom", fill="x", padx=12, pady=(4, 0))
    txt_obs_imersao = tk.Text(quadro_obs, height=3, font=("Segoe UI", 9), bd=1, relief="solid")
    txt_obs_imersao.pack(fill="x")
    txt_obs_imersao.insert("1.0", imersao_vars["obs"].get())
    txt_obs_imersao.bind(
        "<KeyRelease>",
        lambda e: imersao_vars["obs"].set(txt_obs_imersao.get("1.0", "end").strip())
    )

    # ---------- revisão do supervisor técnico ----------
    _montar_revisao_supervisor(win, BG, imersao_vars["supervisor"], imersao_vars["data_revisao"],
                               imersao_vars["revisado"])

    # ---------- tabela de massas ----------
    quadro_m = tk.LabelFrame(win, text="Mass control of the control substrates", bg=BG,
                             font=("Segoe UI", 10, "bold"), padx=8, pady=8)
    quadro_m.pack(fill="x", padx=12, pady=(10, 4))
    for c, peso in enumerate([1, 1, 1, 2, 1]):
        quadro_m.grid_columnconfigure(c, weight=peso, uniform="colm")

    cabecalhos = ["Control position", "Mass before (g)", "Mass after (g)",
                  "Difference (after − before)", f"Condition (loss ≤ {LIMITE_PERDA_PCT:g} %)"]
    for c, titulo in enumerate(cabecalhos):
        tk.Label(quadro_m, text=titulo, bg=AZUL, fg="white", font=("Segoe UI", 9, "bold"),
                 pady=6).grid(row=0, column=c, sticky="nsew", padx=(0, 1))

    for i, amostra in enumerate(AMOSTRAS_IMERSAO, start=1):
        v = imersao_vars["massas"][amostra]
        bg = "#ffffff" if i % 2 else LINHA_ALT
        tk.Label(quadro_m, text=amostra, bg=bg, font=("Segoe UI", 10, "bold"),
                 pady=5).grid(row=i, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
        for c, chave in ((1, "antes"), (2, "depois")):
            cel = tk.Frame(quadro_m, bg=bg)
            cel.grid(row=i, column=c, sticky="nsew", padx=(0, 1), pady=(0, 1))
            ttk.Entry(cel, textvariable=v[chave], width=16, justify="center").pack(pady=3)
        tk.Label(quadro_m, textvariable=v["dif"], bg=bg, font=("Segoe UI", 10)).grid(
            row=i, column=3, sticky="nsew", padx=(0, 1), pady=(0, 1))
        lbl_cond = tk.Label(quadro_m, textvariable=v["cond"], bg=bg, font=("Segoe UI", 10, "bold"))
        lbl_cond.grid(row=i, column=4, sticky="nsew", padx=(0, 1), pady=(0, 1))
        widgets_imersao[amostra] = lbl_cond

    # ---------- legenda ----------
    legenda = tk.LabelFrame(win, text="Legend – conditions considered", bg=BG,
                            font=("Segoe UI", 10, "bold"), padx=10, pady=6)
    legenda.pack(fill="x", padx=12, pady=(4, 4))
    tk.Label(
        legenda, bg=BG, justify="left", anchor="w", wraplength=980, font=("Segoe UI", 9),
        text=(f"•  Mass loss (%) = (mass after − mass before) / mass before × 100.   "
              f"Loss ≤ {LIMITE_PERDA_PCT:g} %  →  Approved.   Loss > {LIMITE_PERDA_PCT:g} %  →  Rejected (non-conforming).\n"
              f"•  Overall result is APPROVED only if all {len(AMOSTRAS_IMERSAO)} control substrates are Approved "
              f"and all {len(ITENS_IMERSAO)} inspection items below are marked Yes.")
    ).pack(anchor="w")

    # ---------- tabela de critérios (Approved? Yes / No) ----------
    quadro_c = tk.LabelFrame(win, text="Post-immersion inspection – acceptance criteria", bg=BG,
                             font=("Segoe UI", 10, "bold"), padx=8, pady=8)
    quadro_c.pack(fill="both", expand=True, padx=12, pady=(4, 4))
    for c, (peso, minimo) in enumerate([(0, 190), (1, 330), (1, 330), (0, 120)]):
        quadro_c.grid_columnconfigure(c, weight=peso, minsize=minimo)

    for c, titulo in enumerate(["Inspection Item", "Acceptance Criteria", "Rejected Condition", "Approved?"]):
        tk.Label(quadro_c, text=titulo, bg=AZUL, fg="white", font=("Segoe UI", 9, "bold"),
                 pady=6).grid(row=0, column=c, sticky="nsew", padx=(0, 1))

    for i, (chave, titulo, aceite, rejeitado) in enumerate(ITENS_IMERSAO, start=1):
        bg = "#ffffff" if i % 2 else LINHA_ALT
        tk.Label(quadro_c, text=titulo, bg=bg, font=("Segoe UI", 9, "bold"), wraplength=180,
                 justify="center").grid(row=i, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
        for c, texto in ((1, aceite), (2, rejeitado)):
            tk.Label(quadro_c, text=texto, bg=bg, font=("Segoe UI", 9), wraplength=320, justify="left",
                     anchor="w", padx=6, pady=3).grid(row=i, column=c, sticky="nsew", padx=(0, 1), pady=(0, 1))
        cel = tk.Frame(quadro_c, bg=bg)
        cel.grid(row=i, column=3, sticky="nsew", padx=(0, 1), pady=(0, 1))
        interno = tk.Frame(cel, bg=bg)
        interno.pack(expand=True)
        for op, cor in (("Yes", "#2e7d32"), ("No", "#c62828")):
            tk.Radiobutton(
                interno, text=op, value=op, variable=imersao_vars["itens"][chave],
                bg=bg, activebackground=bg, selectcolor="white", fg=cor,
                font=("Segoe UI", 9, "bold"), bd=0, highlightthickness=0, tristatevalue="__none__"
            ).pack(side="left", padx=4)

    _pintar_imersao()

    # ajusta o tamanho da janela ao conteúdo
    win.update_idletasks()
    win.geometry(f"{max(1040, win.winfo_reqwidth())}x{win.winfo_reqheight()}")


# ---------------- Eficiência óptica ----------------
def criar_variaveis_eficiencia():
    """Variáveis da eficiência óptica (precisa da janela principal já criada)."""
    ef_vars["teste"] = {k: tk.StringVar(master=janela, value="") for k in CAMPOS_EF_TESTE}
    ef_vars["amostras"] = {}
    for amostra in AMOSTRAS_EFICIENCIA:
        v = {c: tk.StringVar(master=janela, value="") for c in CAMPOS_EF_AMOSTRA}
        v["area"] = tk.StringVar(master=janela, value="-")
        v["dens"] = tk.StringVar(master=janela, value="-")
        v["cond"] = tk.StringVar(master=janela, value="-")
        ef_vars["amostras"][amostra] = v

    for k, var in ef_vars["teste"].items():
        if k != "obs":
            var.trace_add("write", recalcular_eficiencia)
    for v in ef_vars["amostras"].values():
        for c in CAMPOS_EF_AMOSTRA:
            v[c].trace_add("write", recalcular_eficiencia)


def limpar_eficiencia():
    if not ef_vars:
        return
    for var in ef_vars["teste"].values():
        var.set("")
    for v in ef_vars["amostras"].values():
        for c in reversed(CAMPOS_EF_AMOSTRA):      # "testada" por último, para não ser marcada de novo sozinha
            v[c].set("")


def _valor_x(v):
    """Eficiência x da amostra (float) ou None se vazio/inválido."""
    try:
        return converter_float(v["x"].get())
    except Exception:
        return None


def estado_eficiencia():
    """Retorna (estado, medidas, necessárias); estado em empty / partial / approved / rejected.

    Só entram na avaliação as amostras marcadas como testadas (Tested? = Yes)."""
    testadas = 0
    medidas = 0
    reprovado = False
    algum = any(var.get().strip() for var in ef_vars["teste"].values())

    for amostra in AMOSTRAS_EFICIENCIA:
        v = ef_vars["amostras"][amostra]
        if any(v[c].get().strip() for c in CAMPOS_EF_AMOSTRA):
            algum = True
        if v["testada"].get() != "Yes":
            continue
        testadas += 1
        x = _valor_x(v)
        if x is not None:
            medidas += 1
            if round(x, 6) < LIMITE_EFICIENCIA:
                reprovado = True

    necessarias = max(MIN_AMOSTRAS_EFICIENCIA, testadas)
    if reprovado:
        return "rejected", medidas, necessarias
    if medidas >= MIN_AMOSTRAS_EFICIENCIA and medidas == testadas:
        return "approved", medidas, necessarias
    return ("partial" if algum else "empty"), medidas, necessarias


def texto_resumo_eficiencia():
    if not ef_vars:
        return ""
    estado, medidas, necessarias = estado_eficiencia()
    pendente = "" if ef_vars["teste"]["revisado"].get() else "  – pending review"
    if estado == "approved":
        return f"Approved  ({medidas} tested samples ≥ {LIMITE_EFICIENCIA:g}){pendente}"
    if estado == "rejected":
        return f"Rejected  (x < {LIMITE_EFICIENCIA:g}){pendente}"
    if estado == "partial":
        return f"In progress: {medidas}/{necessarias} samples measured"
    # sem dados novos: mantém o valor manual de registros antigos
    valor = valor_ef_var.get().strip()
    if eficiencia_var.get() == "Sim" or valor:
        return "Measured: Yes" + (f"  |  Value: {valor}" if valor else "")
    return "Not filled"


def _parse_data(texto):
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto.strip(), formato)
        except Exception:
            pass
    return None


def texto_idade_referencia():
    """Aviso sobre o tempo de uso do substrato de referência (máx. 6 meses). Retorna (texto, cor)."""
    instalacao = _parse_data(ef_vars["teste"]["ref_data"].get())
    if instalacao is None:
        return "", "#888888"
    teste = _parse_data(ef_vars["teste"]["data_teste"].get()) or datetime.now()
    dias = (teste - instalacao).days
    if dias < 0:
        return "⚠ installation date is after the test date", "#c62828"
    if dias > IDADE_MAX_REFERENCIA_DIAS:
        return f"⚠ reference in use for {dias} days (limit: 6 months)", "#c62828"
    return f"Reference in use for {dias} days (limit: 6 months)", "#2e7d32"


def _pintar_eficiencia():
    """Atualiza cores, campos habilitados, aviso da referência e resultado geral (se a janela estiver aberta)."""
    cores = {"Approved": "#2e7d32", "Rejected": "#c62828"}
    for amostra in AMOSTRAS_EFICIENCIA:
        v = ef_vars["amostras"][amostra]
        estado_campos = "disabled" if v["testada"].get() == "No" else "normal"

        for chave in ["cond_" + amostra]:
            lbl = widgets_ef.get(chave)
            if lbl is not None:
                try:
                    lbl.config(fg=cores.get(v["cond"].get(), "#888888"))
                except tk.TclError:
                    pass

        campos = list(widgets_ef.get("ent_" + amostra, []))
        if widgets_ef.get("ef_" + amostra) is not None:
            campos.append(widgets_ef["ef_" + amostra])
        for ent in campos:
            try:
                ent.config(state=estado_campos)
            except tk.TclError:
                pass

    lbl = widgets_ef.get("ref_aviso")
    if lbl is not None:
        texto, cor = texto_idade_referencia()
        try:
            lbl.config(text=texto, fg=cor)
        except tk.TclError:
            pass

    lbl = widgets_ef.get("resultado")
    if lbl is not None:
        estado, medidas, necessarias = estado_eficiencia()
        revisao = "reviewed" if ef_vars["teste"]["revisado"].get() else "pending supervisor review"
        textos = {
            "approved": (f"Overall result: APPROVED  ({revisao})", "#2e7d32"),
            "rejected": (f"Overall result: REJECTED  ({revisao})", "#c62828"),
            "partial": (f"Overall result: in progress ({medidas}/{necessarias} samples measured)", "#1f3a5f"),
            "empty": ("Overall result: not evaluated", "#888888"),
        }
        texto, cor = textos[estado]
        try:
            lbl.config(text=texto, fg=cor)
        except tk.TclError:
            pass


def recalcular_eficiencia(*args):
    """Recalcula área, densidade de massa e condição de cada amostra, e o resultado geral."""
    if not ef_vars:
        return

    valores = []
    for amostra in AMOSTRAS_EFICIENCIA:
        v = ef_vars["amostras"][amostra]

        # se digitou a eficiência sem responder "Tested?", considera a amostra testada
        if not v["testada"].get() and v["x"].get().strip():
            v["testada"].set("Yes")

        try:
            area = converter_float(v["comp"].get()) * converter_float(v["larg"].get()) / 100.0   # mm² -> cm²
            if area <= 0:
                raise ValueError("área inválida")
            v["area"].set(f"{area:.2f}")
        except Exception:
            area = None
            v["area"].set("-")

        try:
            if area is None:
                raise ValueError("sem área")
            dens = (converter_float(v["depois"].get()) - converter_float(v["antes"].get())) * 1_000_000.0 / area
            v["dens"].set(f"{dens:.2f}")
        except Exception:
            v["dens"].set("-")

        x = _valor_x(v)
        if v["testada"].get() == "No":
            v["cond"].set("Not tested")
        elif x is None:
            v["cond"].set("-")
        else:
            v["cond"].set("Approved" if round(x, 6) >= LIMITE_EFICIENCIA else "Rejected")
            valores.append(f"{amostra}: {v['x'].get().strip()}")

    _pintar_eficiencia()

    estado, _, _ = estado_eficiencia()
    novo_ok = "Sim" if estado == "approved" else "Não"
    if eficiencia_var.get() != novo_ok:
        eficiencia_var.set(novo_ok)
    novo_valor = "; ".join(valores)
    if valor_ef_var.get() != novo_valor:
        valor_ef_var.set(novo_valor)
    atualizar_resumos()


def salvar_eficiencia_db(cur, tarefa_id):
    cur.execute("DELETE FROM eficiencia_teste WHERE id_tarefa = ?", (tarefa_id,))
    cur.execute("DELETE FROM eficiencia_amostras WHERE id_tarefa = ?", (tarefa_id,))

    t = ef_vars["teste"]
    cur.execute("""
        INSERT INTO eficiencia_teste
        (id_tarefa, data_teste, ref_id, ref_data, temperatura_c, umidade_pct,
         supervisor, data_revisao, revisado, observacoes, operador)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (tarefa_id, *[t[k].get().strip() for k in CAMPOS_EF_TESTE]))

    for amostra in AMOSTRAS_EFICIENCIA:
        v = ef_vars["amostras"][amostra]
        area = "" if v["area"].get() == "-" else v["area"].get()
        dens = "" if v["dens"].get() == "-" else v["dens"].get()
        aprovado = {"Approved": "Yes", "Rejected": "No"}.get(v["cond"].get(), "")
        cur.execute("""
            INSERT INTO eficiencia_amostras
            (id_tarefa, amostra, testada, comprimento_mm, largura_mm, massa_antes, massa_depois,
             area_cm2, densidade_ug_cm2, eficiencia, aprovado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tarefa_id, amostra, v["testada"].get(),
              v["comp"].get().strip(), v["larg"].get().strip(),
              v["antes"].get().strip(), v["depois"].get().strip(),
              area, dens,
              v["x"].get().strip(),
              aprovado))


def carregar_eficiencia_db(cur, tarefa_id):
    limpar_eficiencia()

    cur.execute("""
        SELECT data_teste, ref_id, ref_data, temperatura_c, umidade_pct,
               supervisor, data_revisao, revisado, observacoes, operador
        FROM eficiencia_teste WHERE id_tarefa = ?
    """, (tarefa_id,))
    row = cur.fetchone()
    if row:
        for k, valor in zip(CAMPOS_EF_TESTE, row):
            ef_vars["teste"][k].set(valor or "")

    cur.execute("""
        SELECT amostra, testada, comprimento_mm, largura_mm, massa_antes, massa_depois,
               eficiencia
        FROM eficiencia_amostras WHERE id_tarefa = ?
    """, (tarefa_id,))
    for row in cur.fetchall():
        if row[0] in ef_vars["amostras"]:
            for c, valor in zip(CAMPOS_EF_AMOSTRA, row[1:]):
                ef_vars["amostras"][row[0]][c].set(valor or "")


def fechar_janela_eficiencia(salvar_obs=True):
    global janela_eficiencia, txt_obs_eficiencia
    if janela_eficiencia is not None:
        try:
            if salvar_obs and txt_obs_eficiencia is not None:
                ef_vars["teste"]["obs"].set(txt_obs_eficiencia.get("1.0", "end").strip())
            if janela_eficiencia.winfo_exists():
                janela_eficiencia.destroy()
        except tk.TclError:
            pass
    janela_eficiencia = None
    txt_obs_eficiencia = None
    widgets_ef.clear()


def abrir_eficiencia_optica():
    """Janela do teste de eficiência óptica de conversão VUV (Seção 4 do procedimento)."""
    global janela_eficiencia, txt_obs_eficiencia

    if janela_eficiencia is not None and janela_eficiencia.winfo_exists():
        janela_eficiencia.deiconify()
        janela_eficiencia.lift()
        janela_eficiencia.focus_force()
        return

    BG = "#f4f6f8"
    AZUL = "#1f3a5f"
    LINHA_ALT = "#dce6f2"
    hoje = lambda: datetime.today().strftime("%Y-%m-%d")

    win = tk.Toplevel(janela)
    janela_eficiencia = win
    win.title("Optical Efficiency")
    win.geometry("1100x840")
    win.configure(bg=BG)
    win.transient(janela)
    win.protocol("WM_DELETE_WINDOW", fechar_janela_eficiencia)

    tv = ef_vars["teste"]

    # ---------- título ----------
    topo = tk.Frame(win, bg=AZUL)
    topo.pack(fill="x")
    tk.Label(topo, text="VUV OPTICAL CONVERSION EFFICIENCY", fg="white", bg=AZUL,
             font=("Segoe UI", 13, "bold")).pack(pady=(8, 0))
    tk.Label(topo, text=f"QC samples from control positions P02, P03, P14  |  Acceptance: x ≥ {LIMITE_EFICIENCIA:g}",
             fg="#d6e2f0", bg=AZUL, font=("Segoe UI", 10)).pack(pady=(0, 8))

    # ---------- rodapé, observações e revisão (empacotados antes) ----------
    barra_inf = tk.Frame(win, bg=BG)
    barra_inf.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
    lbl_resultado = tk.Label(barra_inf, text="", bg=BG, font=("Segoe UI", 11, "bold"))
    lbl_resultado.pack(side="left")
    widgets_ef["resultado"] = lbl_resultado
    ttk.Button(barra_inf, text="Save & close", command=fechar_janela_eficiencia).pack(side="right", padx=(8, 0))
    tk.Label(barra_inf, text="Data is stored in the database when you use Save / Edit on the main screen.   ",
             bg=BG, fg="#777777", font=("Segoe UI", 8)).pack(side="right")

    quadro_obs = tk.LabelFrame(win, text="Observations", bg=BG, font=("Segoe UI", 10, "bold"), padx=10, pady=6)
    quadro_obs.pack(side="bottom", fill="x", padx=12, pady=(4, 0))
    txt_obs_eficiencia = tk.Text(quadro_obs, height=3, font=("Segoe UI", 9), bd=1, relief="solid")
    txt_obs_eficiencia.pack(fill="x")
    txt_obs_eficiencia.insert("1.0", tv["obs"].get())
    txt_obs_eficiencia.bind(
        "<KeyRelease>",
        lambda e: tv["obs"].set(txt_obs_eficiencia.get("1.0", "end").strip())
    )

    quadro_rev = tk.LabelFrame(win, text="Technical Supervisor review", bg=BG,
                               font=("Segoe UI", 10, "bold"), padx=10, pady=6)
    quadro_rev.pack(side="bottom", fill="x", padx=12, pady=(4, 0))
    tk.Label(quadro_rev, text="Name:", bg=BG, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Entry(quadro_rev, textvariable=tv["supervisor"], width=28).grid(row=0, column=1, padx=(6, 20))
    tk.Label(quadro_rev, text="Date:", bg=BG, font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w")
    ttk.Entry(quadro_rev, textvariable=tv["data_revisao"], width=14).grid(row=0, column=3, padx=(6, 4))
    ttk.Button(quadro_rev, text="Today", width=7,
               command=lambda: tv["data_revisao"].set(hoje())).grid(row=0, column=4, padx=(0, 20))
    tk.Checkbutton(quadro_rev, text="Reviewed and signed", variable=tv["revisado"], onvalue="Yes", offvalue="",
                   bg=BG, activebackground=BG, font=("Segoe UI", 9, "bold")).grid(row=0, column=5)
    tk.Label(quadro_rev, text="The batch decision is final only after the Technical Supervisor signs the record.",
             bg=BG, fg="#777777", font=("Segoe UI", 8)).grid(row=1, column=0, columnspan=6, sticky="w", pady=(4, 0))

    # ---------- dados do teste ----------
    quadro_t = tk.LabelFrame(win, text="Test data", bg=BG, font=("Segoe UI", 10, "bold"), padx=10, pady=8)
    quadro_t.pack(fill="x", padx=12, pady=(10, 4))

    def rot(r, c, texto):
        tk.Label(quadro_t, text=texto, bg=BG, font=("Segoe UI", 9, "bold")).grid(
            row=r, column=c, sticky="w", padx=(0, 6), pady=3)

    rot(0, 0, "Test date (YYYY-MM-DD):")
    cel_data = tk.Frame(quadro_t, bg=BG)
    cel_data.grid(row=0, column=1, sticky="w", padx=(0, 24))
    ttk.Entry(cel_data, textvariable=tv["data_teste"], width=14).pack(side="left")
    ttk.Button(cel_data, text="Today", width=7, command=lambda: tv["data_teste"].set(hoje())).pack(side="left", padx=4)

    rot(0, 2, "Reference substrate ID:")
    ttk.Entry(quadro_t, textvariable=tv["ref_id"], width=18).grid(row=0, column=3, sticky="w", padx=(0, 24))
    rot(0, 4, "Installation date:")
    ttk.Entry(quadro_t, textvariable=tv["ref_data"], width=14).grid(row=0, column=5, sticky="w")

    lbl_ref = tk.Label(quadro_t, text="", bg=BG, font=("Segoe UI", 9, "bold"))
    lbl_ref.grid(row=1, column=2, columnspan=4, sticky="w", pady=(0, 3))
    widgets_ef["ref_aviso"] = lbl_ref

    rot(2, 0, "Mean room temperature (°C):")
    ttk.Entry(quadro_t, textvariable=tv["temp"], width=10).grid(row=2, column=1, sticky="w")
    rot(2, 2, "Mean relative humidity (%):")
    ttk.Entry(quadro_t, textvariable=tv["umid"], width=10).grid(row=2, column=3, sticky="w")
    rot(2, 4, "Performed by (operator):")
    ttk.Entry(quadro_t, textvariable=tv["operador"], width=22).grid(row=2, column=5, sticky="w")

    # ---------- caracterização das amostras ----------
    quadro_c = tk.LabelFrame(win, text="QC samples – dimensions and mass", bg=BG,
                             font=("Segoe UI", 10, "bold"), padx=8, pady=8)
    quadro_c.pack(fill="x", padx=12, pady=(4, 4))
    for c in range(8):
        quadro_c.grid_columnconfigure(c, weight=1, uniform="colc")

    cab_c = ["Control position", "Tested?", "Length (mm)", "Width (mm)", "Mass before (g)", "Mass after (g)",
             "Area (cm²)", "Mass density\n(µg/cm²)"]
    for c, titulo in enumerate(cab_c):
        tk.Label(quadro_c, text=titulo, bg=AZUL, fg="white", font=("Segoe UI", 9, "bold"),
                 pady=6).grid(row=0, column=c, sticky="nsew", padx=(0, 1))

    for i, amostra in enumerate(AMOSTRAS_EFICIENCIA, start=1):
        v = ef_vars["amostras"][amostra]
        bg = "#ffffff" if i % 2 else LINHA_ALT
        tk.Label(quadro_c, text=amostra, bg=bg, font=("Segoe UI", 10, "bold"), pady=8).grid(
            row=i, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))

        cel_t = tk.Frame(quadro_c, bg=bg)
        cel_t.grid(row=i, column=1, sticky="nsew", padx=(0, 1), pady=(0, 1))
        interno_t = tk.Frame(cel_t, bg=bg)
        interno_t.pack(expand=True)
        for op in ("Yes", "No"):
            tk.Radiobutton(
                interno_t, text=op, value=op, variable=v["testada"],
                bg=bg, activebackground=bg, selectcolor="white", font=("Segoe UI", 9, "bold"),
                bd=0, highlightthickness=0, tristatevalue="__none__"
            ).pack(side="left", padx=4)

        entradas = []
        for c, chave in ((2, "comp"), (3, "larg"), (4, "antes"), (5, "depois")):
            cel = tk.Frame(quadro_c, bg=bg)
            cel.grid(row=i, column=c, sticky="nsew", padx=(0, 1), pady=(0, 1))
            ent = ttk.Entry(cel, textvariable=v[chave], width=11, justify="center")
            ent.pack(pady=6)
            entradas.append(ent)
        widgets_ef["ent_" + amostra] = entradas

        for c, chave in ((6, "area"), (7, "dens")):
            tk.Label(quadro_c, textvariable=v[chave], bg=bg, font=("Segoe UI", 10)).grid(
                row=i, column=c, sticky="nsew", padx=(0, 1), pady=(0, 1))

    # ---------- eficiência por amostra ----------
    quadro_e = tk.LabelFrame(win, text="Efficiency analysis", bg=BG,
                             font=("Segoe UI", 10, "bold"), padx=8, pady=8)
    quadro_e.pack(fill="x", padx=12, pady=(4, 4))
    for c in range(3):
        quadro_e.grid_columnconfigure(c, weight=1, uniform="cole")

    cab_e = ["Control position", "Efficiency", f"Condition (x ≥ {LIMITE_EFICIENCIA:g})"]
    for c, titulo in enumerate(cab_e):
        tk.Label(quadro_e, text=titulo, bg=AZUL, fg="white", font=("Segoe UI", 9, "bold"),
                 pady=6).grid(row=0, column=c, sticky="nsew", padx=(0, 1))

    for i, amostra in enumerate(AMOSTRAS_EFICIENCIA, start=1):
        v = ef_vars["amostras"][amostra]
        bg = "#ffffff" if i % 2 else LINHA_ALT
        tk.Label(quadro_e, text=amostra, bg=bg, font=("Segoe UI", 10, "bold"), pady=8).grid(
            row=i, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
        cel = tk.Frame(quadro_e, bg=bg)
        cel.grid(row=i, column=1, sticky="nsew", padx=(0, 1), pady=(0, 1))
        ent_x = ttk.Entry(cel, textvariable=v["x"], width=12, justify="center")
        ent_x.pack(pady=6)
        widgets_ef["ef_" + amostra] = ent_x
        lbl_cond = tk.Label(quadro_e, textvariable=v["cond"], bg=bg, font=("Segoe UI", 10, "bold"))
        lbl_cond.grid(row=i, column=2, sticky="nsew", padx=(0, 1), pady=(0, 1))
        widgets_ef["cond_" + amostra] = lbl_cond

    # ---------- legenda ----------
    legenda = tk.LabelFrame(win, text="Legend – conditions considered", bg=BG,
                            font=("Segoe UI", 10, "bold"), padx=10, pady=6)
    legenda.pack(fill="x", padx=12, pady=(4, 4))
    tk.Label(
        legenda, bg=BG, justify="left", anchor="w", wraplength=1040, font=("Segoe UI", 9),
        text=(f"•  Tested? = Yes when the control sample was tested in this run. Only samples marked Yes are evaluated; "
              f"samples marked No are ignored (not every control position is tested in every run).\n"
              f"•  x = UV transmission efficiency relative to the reference substrate (chi-squared fit).   "
              f"x ≥ {LIMITE_EFICIENCIA:g}  →  Approved;   x < {LIMITE_EFICIENCIA:g}  →  Rejected;   no upper bound.\n"
              f"•  Batch APPROVED only if at least {MIN_AMOSTRAS_EFICIENCIA} samples are tested and every tested sample has "
              f"x ≥ {LIMITE_EFICIENCIA:g}; one tested sample below {LIMITE_EFICIENCIA:g} rejects the entire batch.\n"
              f"•  Mass density = (mass after − mass before) / area, area = length × width "
              f"(same as the main screen, for these smaller samples).")
    ).pack(anchor="w")

    _pintar_eficiencia()

    # ajusta o tamanho da janela ao conteúdo (evita cortar a legenda em telas diferentes)
    win.update_idletasks()
    win.geometry(f"{max(1100, win.winfo_reqwidth())}x{win.winfo_reqheight()}")


# =====================================================
# RELATÓRIO HTML / SERVIDOR LOCAL
# =====================================================
CSS_RELATORIO = """
body{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#e9edf1;color:#222;font-size:14px}
.pagina{max-width:1100px;margin:0 auto;background:#fff;padding:16px 20px 28px}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #9aa7b5;padding:4px 6px;text-align:center;vertical-align:middle;font-size:12.5px}
th{background:#1f3a5f;color:#fff}
td.l{text-align:left}
.zebra tr:nth-child(even) td{background:#eef3f9}
.topo{border-bottom:3px solid #1f3a5f;margin-bottom:12px}
.topo td{border:0;padding:4px}
.topo img{height:46px}
.topo h1{margin:0;font-size:18px;color:#1f3a5f}
.topo p{margin:2px 0 0;font-size:12px;color:#555}
h2{background:#1f3a5f;color:#fff;font-size:14px;margin:18px 0 8px;padding:6px 10px}
h3{font-size:13px;color:#1f3a5f;margin:14px 0 6px}
.scroll{overflow-x:auto}
.campos td{border:0;border-bottom:1px solid #cfd6de;text-align:left;font-size:13px;padding:5px 6px}
.campos b{color:#1f3a5f}
.ok{color:#2e7d32;font-weight:700}
.ruim{color:#c62828;font-weight:700}
.neutro{color:#888}
.caixa{border:2px solid #1f3a5f;padding:10px 14px;margin:12px 0}
.caixa .titulo{font-size:12px;color:#555}
.caixa .valor{font-size:24px;font-weight:700}
.resumo td{text-align:left;font-size:13px}
.sel{display:inline-block;border:2px solid;border-radius:10px;padding:0 6px;font-weight:700}
.nota{font-size:11.5px;color:#555;margin:6px 0}
.botao{display:block;border:1px solid #1f3a5f;border-left:8px solid #1f3a5f;padding:12px 14px;margin:10px 0;
       text-decoration:none;color:#1f3a5f;background:#f4f6f8}
.botao b{font-size:15px;display:block}
.botao span{font-size:12px;color:#555}
.acoes{margin:10px 0}
.acoes a,.acoes button{font-size:12px;margin-right:8px;padding:5px 10px;border:1px solid #1f3a5f;background:#fff;
       color:#1f3a5f;text-decoration:none;cursor:pointer}
.rodape{margin-top:22px;font-size:11px;color:#777;border-top:1px solid #ccc;padding-top:6px}
@media (max-width:600px){.topo td.logo{display:none}.topo h1{font-size:15px}.pagina{padding:12px}}
@media print{
  body{background:#fff}.pagina{max-width:none;padding:0}.acoes{display:none}
  th,h2{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  tr{page-break-inside:avoid}
}
"""

PAGINAS_RELATORIO = ("index", "completo", "visual", "crio", "eficiencia")
_cache_logos = {}


def _esc(v):
    return html.escape("" if v is None else str(v))


def _logo_b64(nome):
    if nome not in _cache_logos:
        try:
            with open(nome, "rb") as f:
                _cache_logos[nome] = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
        except Exception:
            _cache_logos[nome] = ""
    return _cache_logos[nome]


def obter_segredo():
    """Segredo usado para gerar o código do link (evita que alguém adivinhe o ID de outras tarefas)."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO config_sistema (chave, valor) VALUES ('segredo_qr', ?)",
                (secrets.token_hex(16),))
    conn.commit()
    cur.execute("SELECT valor FROM config_sistema WHERE chave = 'segredo_qr'")
    segredo = cur.fetchone()[0]
    conn.close()
    return segredo


def token_tarefa(tarefa_id):
    return hmac.new(obter_segredo().encode(), str(tarefa_id).encode(), hashlib.sha256).hexdigest()[:12]


# ---------------- dados ----------------
def _lista_dict(cur, sql, params):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def coletar_dados_relatorio(tarefa_id):
    """Lê do banco tudo o que entra no relatório (não depende da tela)."""
    conn = conectar()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM tarefas WHERE id = ?", (tarefa_id,))
    t = cur.fetchone()
    if t is None:
        conn.close()
        return None
    t = dict(t)

    cur.execute("SELECT lote_id, codigo_lote, lote_interno_id, codigo_lote_interno, tipo_lote FROM tarefa_lotes "
                "WHERE id_tarefa = ? ORDER BY id", (tarefa_id,))
    salvos = [tuple(r) for r in cur.fetchall()]
    if not salvos and (t.get("lote_entrada_id") is not None or t.get("codigo_lote")):
        salvos = [(t.get("lote_entrada_id"), t.get("codigo_lote"), None, None, "opto")]

    lotes_info = []
    for lid, cod, iid, icod, tipo in salvos:
        if tipo == "limpeza":
            limp = buscar_lote_limpeza(iid, icod)
            lotes_info.append({"interno": "Leptons cleaning", "chegada": (limp[2] if limp else "") or "",
                               "empresa": "Leptons Lab", "lote_empresa": "", "lote_interno": (limp[1] if limp and limp[1] else icod),
                               "filtros": (limp[4] if limp else "") or "", "tipo": "limpeza"})
            continue
        achado = next((l for l in lotes if (lid is not None and l[0] == lid) or (cod and l[1] == cod)), None)
        interno = buscar_lote_interno(iid, icod, lid) if (iid is not None or icod) else None
        filtros_interno = interno[3] if interno and interno[3] not in (None, "") else None
        if achado is not None:
            lotes_info.append({"interno": achado[1], "chegada": achado[2], "empresa": achado[3],
                               "lote_empresa": achado[5], "tipo": "opto",
                               "lote_interno": (interno[2] if interno and interno[2] else icod),
                               "filtros": filtros_interno if filtros_interno is not None else achado[6]})
        else:
            lotes_info.append({"interno": cod, "chegada": "", "empresa": "", "lote_empresa": "",
                               "lote_interno": (interno[2] if interno and interno[2] else icod), "tipo": "opto",
                               "filtros": filtros_interno or ""})

    d = {
        "id": tarefa_id,
        "tarefa": t,
        "lotes": lotes_info,
        "massas": _lista_dict(cur, "SELECT posicao, massa_antes, massa_depois, densidade_massa_ug_cm2 "
                                   "FROM massa_posicoes WHERE id_tarefa = ? ORDER BY posicao", (tarefa_id,)),
        "filtros": {r["filtro"]: r for r in _lista_dict(
            cur, "SELECT * FROM inspecao_visual_filtros WHERE id_tarefa = ? ORDER BY filtro", (tarefa_id,))},
        "im_massas": {r["amostra"]: r for r in _lista_dict(
            cur, "SELECT * FROM imersao_massas WHERE id_tarefa = ?", (tarefa_id,))},
        "im_itens": {r["item"]: r["aprovado"] for r in _lista_dict(
            cur, "SELECT item, aprovado FROM imersao_itens WHERE id_tarefa = ?", (tarefa_id,))},
        "im_obs": t.get("imersao_observacoes") or "",
        "ef_amostras": {r["amostra"]: r for r in _lista_dict(
            cur, "SELECT * FROM eficiencia_amostras WHERE id_tarefa = ?", (tarefa_id,))},
    }
    cab = _lista_dict(cur, "SELECT * FROM inspecao_visual_cab WHERE id_tarefa = ?", (tarefa_id,))
    d["cab"] = cab[0] if cab else {}
    ef = _lista_dict(cur, "SELECT * FROM eficiencia_teste WHERE id_tarefa = ?", (tarefa_id,))
    d["ef_teste"] = ef[0] if ef else {}
    conn.close()
    return d


# ---------------- estados (a partir dos dados gravados) ----------------
def resumo_visual_dados(d):
    obrigatorios = ("visual_status", "uniformity", "stains", "particles", "edge_defects",
                    "finger_defects", "other_defects", "classification")
    completos = 0
    contagem = {"A": 0, "B": 0, "C": 0}
    algum = False
    for n in range(1, N_FILTROS + 1):
        f = d["filtros"].get(n, {})
        valores = [(f.get(k) or "") for k in obrigatorios]
        if all(valores):
            completos += 1
        if any(valores) or (f.get("comments") or ""):
            algum = True
        if f.get("classification") in contagem:
            contagem[f["classification"]] += 1
    return completos, contagem, algum


def estado_imersao_dados(d):
    valores = []
    for amostra in AMOSTRAS_IMERSAO:
        valores.append((d["im_massas"].get(amostra) or {}).get("aprovado") or "")
    for chave, *_ in ITENS_IMERSAO:
        valores.append(d["im_itens"].get(chave) or "")
    if "No" in valores:
        return "rejected"
    if all(v == "Yes" for v in valores):
        return "approved"
    return "partial" if any(valores) or d["im_obs"] else "empty"


def estado_eficiencia_dados(d):
    testadas = 0
    medidas = 0
    reprovado = False
    algum = False
    for amostra in AMOSTRAS_EFICIENCIA:
        r = d["ef_amostras"].get(amostra) or {}
        if any((r.get(k) or "") for k in ("testada", "comprimento_mm", "largura_mm", "massa_antes",
                                            "massa_depois", "eficiencia")):
            algum = True
        if r.get("testada") != "Yes":
            continue
        testadas += 1
        try:
            x = converter_float(r.get("eficiencia"))
        except Exception:
            continue
        medidas += 1
        if round(x, 6) < LIMITE_EFICIENCIA:
            reprovado = True
    if reprovado:
        return "rejected"
    if medidas >= MIN_AMOSTRAS_EFICIENCIA and medidas == testadas:
        return "approved"
    return "partial" if algum else "empty"


def decisao_lote(estado_im, estado_ef):
    if "rejected" in (estado_im, estado_ef):
        return "REJECTED"
    if estado_im == "approved" and estado_ef == "approved":
        return "APPROVED"
    return "PENDING"


TXT_ESTADO = {"approved": "APPROVED", "rejected": "REJECTED", "partial": "IN PROGRESS", "empty": "NOT FILLED"}
CLS_ESTADO = {"approved": "ok", "rejected": "ruim", "partial": "neutro", "empty": "neutro"}


# ---------------- blocos HTML ----------------
def _cx(opcoes, escolhido):
    """Caixas de seleção no estilo do formulário."""
    partes = []
    for o in opcoes:
        marca = "&#9745; <b>" + _esc(o) + "</b>" if o == escolhido else "&#9744; " + _esc(o)
        partes.append(marca)
    return "<br>".join(partes)


def _cabecalho_pagina(subtitulo):
    esq = _logo_b64("esquerda.png")
    dir_ = _logo_b64("direita.png")
    img_esq = '<img src="' + esq + '" alt="">' if esq else ""
    img_dir = '<img src="' + dir_ + '" alt="">' if dir_ else ""
    return (
        '<table class="topo"><tr>'
        '<td class="logo" style="width:120px">' + img_esq + '</td>'
        '<td style="text-align:center"><h1>DUNE HD – X-ARAPUCA PTP FILMS<br>DEPOSITION INSPECTION RECORD</h1>'
        '<p>' + _esc(subtitulo) + '</p></td>'
        '<td class="logo" style="width:120px;text-align:right">' + img_dir + '</td>'
        '</tr></table>'
    )


def _linha_proc(data, quem):
    return ("<p><b>Date:</b> " + (_esc(data) or "-") + " &nbsp;|&nbsp; <b>Performed by:</b> " + (_esc(quem) or "-") + "</p>")


def _linha_rev(supervisor, data, revisado):
    if revisado == "Yes":
        return ("<p><b>Technical Supervisor review:</b> signed by " + (_esc(supervisor) or "-")
                + " on " + (_esc(data) or "-") + "</p>")
    return "<p><b>Technical Supervisor review:</b> <span class='neutro'>pending</span></p>"


def _celula_campo(rotulo, valor):
    return "<b>" + _esc(rotulo) + ":</b> " + (_esc(valor) if valor not in (None, "") else "-")


def _bloco_info(d):
    t = d["tarefa"]
    c = d["cab"]
    inspetor = c.get("inspector") or t.get("responsavel")
    lotes_txt = "<br>".join(
        _esc(l["interno"])
        + (" &nbsp;|&nbsp; internal lot <b>" + _esc(l.get("lote_interno")) + "</b>" if l.get("lote_interno") else "")
        + (" &nbsp;|&nbsp; " + ("cleaned on " if l.get("tipo") == "limpeza" else "arrival ") + _esc(l["chegada"])
           if l["chegada"] else "")
        + (" &nbsp;|&nbsp; " + _esc(l["filtros"]) + " filters" if l["filtros"] not in ("", None) else "")
        for l in d["lotes"]
    ) or "-"

    linhas = [
        (_celula_campo("BOX PID", t.get("codigo_tarefa")), _celula_campo("DEPOSITION DATE", t.get("data_inicio"))),
        (_celula_campo("RUN EVAPORATION", c.get("run_evaporation")), _celula_campo("POSITION FILTERS", t.get("position_range"))),
        (_celula_campo("PTP MASS (g)", t.get("massa_ptp_g")), _celula_campo("INSPECTOR NAME", inspetor)),
        (_celula_campo("FILTER TYPE", t.get("descricao")), _celula_campo("RECORDED", t.get("data_hora_registro"))),
    ]
    tab = "".join("<tr><td>" + a + "</td><td>" + b + "</td></tr>" for a, b in linhas)
    tab += "<tr><td colspan='2'><b>BATCHES:</b><br>" + lotes_txt + "</td></tr>"
    tab += ("<tr><td colspan='2'><b>CHILDREN PID&#39;S:</b> &nbsp; P02: " + _esc(c.get("pid_p02") or "-")
            + " &nbsp; P03: " + _esc(c.get("pid_p03") or "-") + " &nbsp; P14: " + _esc(c.get("pid_p14") or "-") + "</td></tr>")
    tab += "<tr><td colspan='2'><b>NOTES:</b> " + (_esc(t.get("observacoes")) or "-") + "</td></tr>"

    massas = ""
    if d["massas"]:
        linhas_m = "".join(
            "<tr><td>" + _esc(m["posicao"]) + "</td><td>" + _esc(m["massa_antes"]) + "</td><td>"
            + _esc(m["massa_depois"]) + "</td><td>" + _esc(m["densidade_massa_ug_cm2"]) + "</td></tr>"
            for m in d["massas"])
        massas = ("<h3>Mass control by position</h3><div class='scroll'><table class='zebra'><tr><th>Position</th>"
                  "<th>Mass before (g)</th><th>Mass after (g)</th><th>Mass density (&micro;g/cm&sup2;)</th></tr>"
                  + linhas_m + "</table></div>")
    return ("<h2>1. SHIPMENT CONTAINER INFORMATION</h2><table class='campos'>" + tab + "</table>" + massas)


def _signoff_dados(t):
    return (t.get("qa_signoff_por") or "").strip(), (t.get("qa_signoff_data") or "").strip()


def _bloco_signoff(d):
    """Último tópico do relatório completo: aval final do QA."""
    por, data = _signoff_dados(d["tarefa"])
    return ("<h2 id='signoff'>5. FINAL QA SIGN-OFF</h2><table class='campos'><tr>"
            "<td><b>Final QA Sign-Off by:</b> " + (_esc(por) or "______________________________") + "</td>"
            "<td><b>Date:</b> " + (_esc(data) or "____ / ____ / ________") + "</td></tr></table>")


def _bloco_decisao(d):
    ei = estado_imersao_dados(d)
    ee = estado_eficiencia_dados(d)
    dec = decisao_lote(ei, ee)
    cor = {"APPROVED": "#2e7d32", "REJECTED": "#c62828"}.get(dec, "#1f3a5f")
    completos, cont, algum = resumo_visual_dados(d)
    rev = d["ef_teste"]
    if rev.get("revisado") == "Yes":
        assinatura = "Signed by " + _esc(rev.get("supervisor") or "-") + " on " + _esc(rev.get("data_revisao") or "-")
    else:
        assinatura = "Pending Technical Supervisor review"
    visual_txt = (str(completos) + "/" + str(N_FILTROS) + " substrates classified &nbsp;|&nbsp; A: " + str(cont["A"])
                  + " (reject) &nbsp; B: " + str(cont["B"]) + " (QA/QC review) &nbsp; C: " + str(cont["C"]) + " (accept)")
    por_so, data_so = _signoff_dados(d["tarefa"])
    if por_so:
        signoff_html = "<b>" + _esc(por_so) + "</b> &nbsp;|&nbsp; Date: " + (_esc(data_so) or "-")
    else:
        signoff_html = "<span class='neutro'>Pending final QA sign-off</span>"
    signoff_row = '<tr><td><b>QA Sign-off by</b></td><td>' + signoff_html + '</td></tr>'
    return (
        '<div class="caixa" style="border-color:' + cor + '">'
        '<div class="titulo">BATCH DECISION (cryogenic immersion + optical efficiency)</div>'
        '<div class="valor" style="color:' + cor + '">' + dec + '</div>'
        '<table class="resumo">'
        '<tr><td><b>Visual inspection</b></td><td>' + visual_txt + '</td></tr>'
        '<tr><td><b>Cryogenic immersion</b></td><td class="' + CLS_ESTADO[ei] + '">' + TXT_ESTADO[ei] + '</td></tr>'
        '<tr><td><b>Optical efficiency</b></td><td class="' + CLS_ESTADO[ee] + '">' + TXT_ESTADO[ee] + '</td></tr>'
        + signoff_row +
        '</table></div>'
    )


def _bloco_visual(d):
    linhas = []
    for n in range(1, N_FILTROS + 1):
        f = d["filtros"].get(n, {})

        def v(k, f=f):
            return f.get(k) or ""

        classes = []
        for cl in ("A", "B", "C"):
            if v("classification") == cl:
                classes.append('<span class="sel" style="color:' + CORES_CLASSE[cl] + '">' + cl + '</span>')
            else:
                classes.append(cl)
        linhas.append(
            "<tr><td><b>" + format(n, "02d") + "</b></td>"
            "<td class='l'>" + _cx(["Pass", "Fail"], v("visual_status")) + "</td>"
            "<td class='l'>" + _cx(["OK", "Minor", "Major"], v("uniformity")) + "</td>"
            + "".join("<td class='l'>" + _cx(["Yes", "No"], v(k)) + "</td>"
                      for k in ("stains", "particles", "edge_defects", "finger_defects", "other_defects"))
            + "<td class='l'>" + _esc(v("comments")) + "</td>"
            "<td>" + " / ".join(classes) + "</td></tr>"
        )
    cab = "".join("<th>" + h + "</th>" for h in (
        "Filter n&ordm;", "Visual Status", "Uniformity", "Stains", "Particles", "Edge Defects",
        "Finger Defects", "Other Defects", "Comments", "Classification"))
    legenda = (
        "<h3>Classification</h3><table><tr><th>Class</th><th>Description</th><th>Disposition</th></tr>"
        "<tr><td><b>A</b></td><td class='l'>Defects affecting coating integrity, adhesion, or optical performance.</td><td>Reject glass substrate</td></tr>"
        "<tr><td><b>B</b></td><td class='l'>Localized defects with limited impact requiring evaluation.</td><td>QA/QC review</td></tr>"
        "<tr><td><b>C</b></td><td class='l'>Minor cosmetic defects with no expected impact on performance.</td><td>Accept</td></tr></table>"
    )
    return ("<h2 id='visual'>2. VISUAL INSPECTION TABLE</h2>" + _linha_proc(d["cab"].get("data_inspecao"), d["cab"].get("operador"))
            + "<div class='scroll'><table class='zebra'><tr>" + cab + "</tr>"
            + "".join(linhas) + "</table></div>" + legenda
            + _linha_rev(d["cab"].get("supervisor"), d["cab"].get("data_revisao"), d["cab"].get("revisado")))


def _bloco_crio(d):
    linhas = ""
    for amostra in AMOSTRAS_IMERSAO:
        r = d["im_massas"].get(amostra) or {}
        if r.get("diferenca_g"):
            dif = _esc(r["diferenca_g"]) + " g (" + _esc(r.get("diferenca_pct")) + " %)"
        else:
            dif = "-"
        ap = r.get("aprovado") or ""
        cond = '<span class="ok">Approved</span>' if ap == "Yes" else ('<span class="ruim">Rejected</span>' if ap == "No" else "-")
        linhas += ("<tr><td><b>" + amostra + "</b></td><td>" + (_esc(r.get("massa_antes")) or "-") + "</td><td>"
                   + (_esc(r.get("massa_depois")) or "-") + "</td><td>" + dif + "</td><td>" + cond + "</td></tr>")
    massas = ("<div class='scroll'><table class='zebra'><tr><th>Sample Control</th><th>Mass Before (g)</th><th>Mass After (g)</th>"
              "<th>Difference (after &minus; before)</th><th>Condition (loss &le; " + format(LIMITE_PERDA_PCT, "g") + " %)</th></tr>"
              + linhas + "</table></div>")
    nota = ("<p class='nota'>Accept criteria: a maximum mass loss of " + format(LIMITE_PERDA_PCT, "g")
            + "% is acceptable. Any control substrate with a mass loss greater than "
            + format(LIMITE_PERDA_PCT, "g") + "% is non-conforming.</p>")

    itens = ""
    for chave, titulo, aceite, rejeitado in ITENS_IMERSAO:
        itens += ("<tr><td><b>" + _esc(titulo) + "</b></td><td class='l'>" + _esc(aceite) + "</td><td class='l'>"
                  + _esc(rejeitado) + "</td><td class='l'>" + _cx(["Yes", "No"], d["im_itens"].get(chave) or "") + "</td></tr>")
    criterios = ("<h3>Post-immersion inspection</h3><div class='scroll'><table class='zebra'><tr><th>Inspection Item</th>"
                 "<th>Acceptance Criteria</th><th>Rejected Condition</th><th>Approved?</th></tr>" + itens + "</table></div>")
    obs = "<p><b>Notes:</b> " + (_esc(d["im_obs"]) or "-") + "</p>"
    est = estado_imersao_dados(d)
    res = "<p><b>Result:</b> <span class='" + CLS_ESTADO[est] + "'>" + TXT_ESTADO[est] + "</span></p>"
    proc = _linha_proc(d["tarefa"].get("imersao_data"), d["tarefa"].get("imersao_operador"))
    rev = _linha_rev(d["tarefa"].get("imersao_supervisor"), d["tarefa"].get("imersao_data_revisao"),
                     d["tarefa"].get("imersao_revisado"))
    return "<h2 id='crio'>3. CRYOGENIC IMMERSION</h2>" + proc + massas + nota + criterios + obs + res + rev


def _bloco_ef(d):
    te = d["ef_teste"]
    campos = [
        (_celula_campo("TEST DATE", te.get("data_teste")), _celula_campo("REFERENCE SUBSTRATE ID", te.get("ref_id"))),
        (_celula_campo("REFERENCE INSTALLATION DATE", te.get("ref_data")),
         _celula_campo("MEAN ROOM TEMPERATURE (°C)", te.get("temperatura_c"))),
        (_celula_campo("MEAN RELATIVE HUMIDITY (%)", te.get("umidade_pct")),
         _celula_campo("PERFORMED BY (OPERATOR)", te.get("operador"))),
    ]
    tab_t = "<table class='campos'>" + "".join("<tr><td>" + a + "</td><td>" + b + "</td></tr>" for a, b in campos) + "</table>"

    l_c = ""
    l_e = ""
    for amostra in AMOSTRAS_EFICIENCIA:
        r = d["ef_amostras"].get(amostra) or {}
        testada = r.get("testada") or ""
        try:
            area = converter_float(r.get("comprimento_mm")) * converter_float(r.get("largura_mm")) / 100.0
            area_txt = format(area, ".2f")
        except Exception:
            area_txt = "-"
        dens = r.get("densidade_ug_cm2") or "-"
        l_c += ("<tr><td><b>" + amostra + "</b></td><td class='l'>" + _cx(["Yes", "No"], testada) + "</td><td>"
                + (_esc(r.get("comprimento_mm")) or "-") + "</td><td>" + (_esc(r.get("largura_mm")) or "-") + "</td><td>"
                + (_esc(r.get("massa_antes")) or "-") + "</td><td>" + (_esc(r.get("massa_depois")) or "-") + "</td><td>"
                + _esc(area_txt) + "</td><td>" + _esc(dens) + "</td></tr>")
        if testada == "No":
            cond = "<span class='neutro'>Not tested</span>"
        elif (r.get("aprovado") or "") == "Yes":
            cond = "<span class='ok'>Approved</span>"
        elif (r.get("aprovado") or "") == "No":
            cond = "<span class='ruim'>Rejected</span>"
        else:
            cond = "-"
        l_e += ("<tr><td><b>" + amostra + "</b></td><td>" + (_esc(r.get("eficiencia")) or "-") + "</td><td>" + cond + "</td></tr>")

    tab_c = ("<h3>QC samples &ndash; dimensions and mass</h3><div class='scroll'><table class='zebra'><tr><th>Control position</th>"
             "<th>Tested?</th><th>Length (mm)</th><th>Width (mm)</th><th>Mass before (g)</th><th>Mass after (g)</th>"
             "<th>Area (cm&sup2;)</th><th>Mass density (&micro;g/cm&sup2;)</th></tr>" + l_c + "</table></div>")
    tab_e = ("<h3>Efficiency analysis</h3><div class='scroll'><table class='zebra'><tr><th>Control position</th><th>Efficiency</th>"
             "<th>Condition (x &ge; " + format(LIMITE_EFICIENCIA, "g") + ")</th></tr>" + l_e + "</table></div>")
    nota = ("<p class='nota'>Only samples marked Tested = Yes are evaluated. x = UV transmission efficiency relative to the "
            "reference substrate; x &ge; " + format(LIMITE_EFICIENCIA, "g") + " is approved (no upper bound). The batch is approved only "
            "if at least " + str(MIN_AMOSTRAS_EFICIENCIA) + " samples are tested and all tested samples pass.</p>")
    obs = "<p><b>Notes:</b> " + (_esc(te.get("observacoes")) or "-") + "</p>"
    est = estado_eficiencia_dados(d)
    res = "<p><b>Result:</b> <span class='" + CLS_ESTADO[est] + "'>" + TXT_ESTADO[est] + "</span></p>"
    if te.get("revisado") == "Yes":
        rev = ("<p><b>Technical Supervisor review:</b> signed by " + _esc(te.get("supervisor") or "-")
               + " on " + _esc(te.get("data_revisao") or "-") + "</p>")
    else:
        rev = "<p><b>Technical Supervisor review:</b> <span class='neutro'>pending</span></p>"
    return ("<h2 id='eficiencia'>4. VUV OPTICAL EFFICIENCY</h2>" + tab_t + tab_c + tab_e + nota + res + obs + rev)


def _documento(titulo, corpo):
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>' + _esc(titulo) + '</title><style>' + CSS_RELATORIO + '</style></head>'
            '<body><div class="pagina">' + corpo + '</div></body></html>')


def _rodape():
    return ('<div class="rodape">Generated on ' + datetime.now().strftime("%Y-%m-%d %H:%M")
            + ' by Deposition Control System for DUNE.</div>')


def pagina_relatorio(d, secao):
    titulos = {
        "completo": "Deposition Inspection Record",
        "visual": "Visual inspection",
        "crio": "Cryogenic immersion",
        "eficiencia": "Optical efficiency",
    }
    titulo = titulos[secao]
    acoes = ('<div class="acoes"><a href="index.html">&larr; Options</a>'
             '<button onclick="window.print()">Print / Save as PDF</button></div>')
    corpo = _cabecalho_pagina("Inspection of Evaporated PTP Film – " + titulo) + acoes + _bloco_info(d)
    if secao == "completo":
        corpo += _bloco_decisao(d) + _bloco_visual(d) + _bloco_crio(d) + _bloco_ef(d) + _bloco_signoff(d)
    elif secao == "visual":
        corpo += _bloco_visual(d)
    elif secao == "crio":
        corpo += _bloco_crio(d)
    else:
        corpo += _bloco_ef(d)
    return _documento(titulo + " – " + str(d["tarefa"].get("codigo_tarefa") or ""), corpo + _rodape())


def pagina_menu(d):
    t = d["tarefa"]
    c = d["cab"]
    ei = estado_imersao_dados(d)
    ee = estado_eficiencia_dados(d)
    completos, cont, algum = resumo_visual_dados(d)
    lotes_txt = ", ".join(
        _esc(l["interno"]) + (" / " + _esc(l.get("lote_interno")) if l.get("lote_interno") else "")
        for l in d["lotes"] if l["interno"]) or "-"

    resumo = (
        "<table class='campos'>"
        "<tr><td>" + _celula_campo("PID", t.get("codigo_tarefa")) + "</td><td>" + _celula_campo("Date", t.get("data_inicio")) + "</td></tr>"
        "<tr><td>" + _celula_campo("Run", c.get("run_evaporation")) + "</td><td>" + _celula_campo("Positions", t.get("position_range")) + "</td></tr>"
        "<tr><td colspan='2'><b>Batches:</b> " + lotes_txt + "</td></tr></table>"
    )
    dec = decisao_lote(ei, ee)
    cor = {"APPROVED": "#2e7d32", "REJECTED": "#c62828"}.get(dec, "#1f3a5f")
    por_so, data_so = _signoff_dados(t)
    if por_so:
        linha_so = ('<div class="titulo">QA Sign-off by: <b>' + _esc(por_so) + '</b> &nbsp;|&nbsp; Date: '
                    + (_esc(data_so) or "-") + '</div>')
    else:
        linha_so = '<div class="titulo">QA Sign-off: <span class="neutro">pending</span></div>'
    caixa = ('<div class="caixa" style="border-color:' + cor + '"><div class="titulo">BATCH DECISION</div>'
             '<div class="valor" style="color:' + cor + '">' + dec + '</div>' + linha_so + '</div>')

    def botao(nome, titulo, detalhe):
        return '<a class="botao" href="' + nome + '.html"><b>' + titulo + '</b><span>' + detalhe + '</span></a>'

    botoes = (
        botao("completo", "Deposition Inspection Record (full report)",
              "Container information, visual inspection, cryogenic immersion and optical efficiency")
        + botao("visual", "Visual inspection",
                str(completos) + "/" + str(N_FILTROS) + " substrates classified – A: " + str(cont["A"])
                + ", B: " + str(cont["B"]) + ", C: " + str(cont["C"]))
        + botao("crio", "Cryogenic immersion", TXT_ESTADO[ei])
        + botao("eficiencia", "Optical efficiency", TXT_ESTADO[ee])
    )
    corpo = (_cabecalho_pagina("Report options") + resumo + caixa + "<h3>Choose a report</h3>" + botoes + _rodape())
    return _documento("Report options – " + str(t.get("codigo_tarefa") or ""), corpo)


def renderizar_pagina(tarefa_id, nome):
    d = coletar_dados_relatorio(tarefa_id)
    if d is None:
        return _documento("Not found", "<p>Task not found.</p>")
    if nome == "index":
        return pagina_menu(d)
    return pagina_relatorio(d, nome)


# ---------------- servidor local ----------------
class _HandlerRelatorio(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _enviar(self, codigo, texto):
        dados = texto.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        caminho = urllib.parse.urlparse(self.path).path
        m = re.fullmatch(r"/t/(\d+)/([0-9a-f]{12})/(?:(index|completo|visual|crio|eficiencia)\.html)?", caminho)
        if not m:
            self._enviar(404, _documento("Not found", "<p>Not found.</p>"))
            return
        tarefa_id = int(m.group(1))
        try:
            if not hmac.compare_digest(m.group(2), token_tarefa(tarefa_id)):
                self._enviar(404, _documento("Not found", "<p>Not found.</p>"))
                return
            self._enviar(200, renderizar_pagina(tarefa_id, m.group(3) or "index"))
        except Exception:
            self._enviar(500, _documento("Error", "<p>Could not generate the report.</p>"))


def iniciar_servidor_relatorios():
    """Inicia o servidor leve em segundo plano (modo 1). Retorna True se estiver ativo."""
    global servidor_http
    if URL_BASE_RELATORIO or servidor_http is not None:
        return servidor_http is not None
    try:
        servidor_http = ThreadingHTTPServer(("0.0.0.0", SERVIDOR_PORTA), _HandlerRelatorio)
    except OSError:
        servidor_http = None
        return False
    threading.Thread(target=servidor_http.serve_forever, daemon=True).start()
    return True


def ip_local():
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(("10.255.255.255", 1))     # não envia nada; só descobre a interface de rede usada
        ip = sk.getsockname()[0]
        sk.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def url_relatorio(tarefa_id, nome="index"):
    tok = token_tarefa(tarefa_id)
    if URL_BASE_RELATORIO:
        return URL_BASE_RELATORIO.rstrip("/") + "/" + str(tarefa_id) + "_" + tok + "/" + nome + ".html"
    return "http://" + ip_local() + ":" + str(SERVIDOR_PORTA) + "/t/" + str(tarefa_id) + "/" + tok + "/" + nome + ".html"


def gerar_arquivos_relatorio(tarefa_id):
    """Grava as páginas HTML da tarefa em PASTA_RELATORIOS (modo 2). Retorna a pasta."""
    pasta = os.path.join(PASTA_RELATORIOS, str(tarefa_id) + "_" + token_tarefa(tarefa_id))
    os.makedirs(pasta, exist_ok=True)
    d = coletar_dados_relatorio(tarefa_id)
    for nome in PAGINAS_RELATORIO:
        texto = pagina_menu(d) if nome == "index" else pagina_relatorio(d, nome)
        with open(os.path.join(pasta, nome + ".html"), "w", encoding="utf-8") as f:
            f.write(texto)
    return pasta


def _preparar_relatorio(tarefa_id):
    """Retorna (url do QR, url/arquivo para abrir agora, aviso) ou None se não for possível."""
    atualizar_lotes()
    if URL_BASE_RELATORIO:
        pasta = gerar_arquivos_relatorio(tarefa_id)
        preview = Path(pasta, "index.html").resolve().as_uri()
        aviso = ("Report files saved in: " + os.path.abspath(pasta) + ". Publish this folder at "
                 + URL_BASE_RELATORIO + " so the QR link works.")
        return url_relatorio(tarefa_id), preview, aviso

    if not iniciar_servidor_relatorios():
        messagebox.showwarning(
            "Report server",
            "Could not start the report server on port " + str(SERVIDOR_PORTA) + " (port in use?).\n"
            "Change SERVIDOR_PORTA in the code or set URL_BASE_RELATORIO."
        )
        return None
    preview = ("http://127.0.0.1:" + str(SERVIDOR_PORTA) + "/t/" + str(tarefa_id) + "/"
               + token_tarefa(tarefa_id) + "/index.html")
    aviso = ("The link works on devices connected to the same network as this computer, while this program is open. "
             "If it does not open, allow Python through the firewall for private networks.")
    return url_relatorio(tarefa_id), preview, aviso


# =====================================================
# RELATÓRIO EM PDF (todas as informações do cadastro)
# =====================================================
def _registrar_fontes_pdf():
    """Procura uma fonte TrueType com boa cobertura de caracteres; senão usa Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidatos = [
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for normal, negrito in candidatos:
        if os.path.exists(normal) and os.path.exists(negrito):
            try:
                pdfmetrics.registerFont(TTFont("RelFonte", normal))
                pdfmetrics.registerFont(TTFont("RelFonte-Bold", negrito))
                pdfmetrics.registerFontFamily("RelFonte", normal="RelFonte", bold="RelFonte-Bold",
                                              italic="RelFonte", boldItalic="RelFonte-Bold")
                return "RelFonte", "RelFonte-Bold"
            except Exception:
                pass
    return "Helvetica", "Helvetica-Bold"


def gerar_pdf_relatorio(tarefa_id, caminho):
    """Gera o PDF com todas as informações gravadas da tarefa (usa o pacote reportlab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer,
                                    Image as RLImage, PageBreak, CondPageBreak)
    from xml.sax.saxutils import escape as xesc

    d = coletar_dados_relatorio(tarefa_id)
    if d is None:
        raise ValueError("Task not found")
    t = d["tarefa"]
    cab = d["cab"]
    fonte, negrito = _registrar_fontes_pdf()

    AZUL = colors.HexColor("#1f3a5f")
    ZEBRA = colors.HexColor("#eef3f9")
    GRADE = colors.HexColor("#9aa7b5")
    VERDE = colors.HexColor("#2e7d32")
    VERMELHO = colors.HexColor("#c62828")
    LARANJA = colors.HexColor("#ef6c00")
    CINZA = colors.HexColor("#888888")
    largura = A4[0] - 24 * mm

    base = ParagraphStyle("base", fontName=fonte, fontSize=8, leading=10)
    est_cel = ParagraphStyle("cel", parent=base, fontSize=7.5, leading=9)
    est_cab = ParagraphStyle("cab", parent=est_cel, fontName=negrito, textColor=colors.white, alignment=TA_CENTER)
    est_titulo = ParagraphStyle("tit", parent=base, fontName=negrito, fontSize=13, leading=16,
                                alignment=TA_CENTER, textColor=AZUL)
    est_sub = ParagraphStyle("sub", parent=base, alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
    est_sec = ParagraphStyle("sec", parent=base, fontName=negrito, fontSize=10, leading=12, textColor=colors.white)
    est_h3 = ParagraphStyle("h3", parent=base, fontName=negrito, fontSize=8.5, textColor=AZUL, spaceBefore=6, spaceAfter=3)
    est_nota = ParagraphStyle("nota", parent=base, fontSize=7, leading=8.5, textColor=colors.HexColor("#555555"))

    def txt(v, vazio="-"):
        v = "" if v is None else str(v).strip()
        return xesc(v).replace("\n", "<br/>") if v else vazio

    def P(v, estilo=None, vazio="-"):
        return Paragraph(txt(v, vazio), estilo or est_cel)

    def M(markup, estilo=None):
        return Paragraph(markup, estilo or est_cel)

    def H(texto):
        return Paragraph(xesc(texto), est_cab)

    def secao(titulo):
        tb = Table([[Paragraph(xesc(titulo), est_sec)]], colWidths=[largura])
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AZUL), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return tb

    def tabela(linhas, larguras, extra=None, cabecalho=True):
        tb = Table(linhas, colWidths=[w * mm for w in larguras], repeatRows=1 if cabecalho else 0)
        estilo = [("FONTNAME", (0, 0), (-1, -1), fonte), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                  ("GRID", (0, 0), (-1, -1), 0.4, GRADE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                  ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        if cabecalho:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA])]
        if extra:
            estilo += extra
        tb.setStyle(TableStyle(estilo))
        return tb

    def hexcor(c):
        return "#" + c.hexval()[2:]

    def rev_pdf(supervisor, data, revisado):
        if revisado == "Yes":
            return M("<b>Technical Supervisor review:</b> signed by " + txt(supervisor) + " on " + txt(data))
        return M("<b>Technical Supervisor review:</b> pending")

    def proc(data, quem):
        return M("<b>Date:</b> " + txt(data) + " &nbsp;&nbsp;|&nbsp;&nbsp; <b>Performed by:</b> " + txt(quem))

    def logo(nome, alinhamento):
        """Logo sem as margens brancas do arquivo, com até 22 mm de altura e 35 mm de largura."""
        try:
            with Image.open(nome) as im:
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

    cor_estado = {"approved": VERDE, "rejected": VERMELHO}
    story = []

    # ---------------- cabeçalho ----------------
    topo = Table([[logo("esquerda.png", "CENTER"),
                   [Paragraph("DUNE HD – X-ARAPUCA PTP FILMS", est_titulo),
                    Paragraph("DEPOSITION INSPECTION RECORD", est_titulo),
                    Paragraph("Inspection of Evaporated PTP Film", est_sub)],
                   logo("direita.png", "RIGHT")]],
                 colWidths=[40 * mm, largura - 80 * mm, 40 * mm])
    topo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.5, AZUL),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("ALIGN", (0, 0), (0, 0), "CENTER")]))
    story += [topo, Spacer(1, 6)]

    # ---------------- 1. informações da caixa ----------------
    inspetor = cab.get("inspector") or t.get("responsavel")

    def campo(rot, val):
        return M("<b>" + xesc(rot) + ":</b> " + txt(val))

    linhas = [
        [campo("BOX PID", t.get("codigo_tarefa")), campo("DEPOSITION DATE", t.get("data_inicio"))],
        [campo("RUN EVAPORATION", cab.get("run_evaporation")), campo("POSITION FILTERS", t.get("position_range"))],
        [campo("PTP MASS (g)", t.get("massa_ptp_g")), campo("INSPECTOR NAME (RESPONSIBLE)", inspetor)],
        [campo("FILTER TYPE", t.get("descricao")), campo("RECORDED", t.get("data_hora_registro"))],
        [M("<b>CHILDREN PID'S:</b> &nbsp; P02: " + txt(cab.get("pid_p02")) + " &nbsp;&nbsp; P03: " + txt(cab.get("pid_p03"))
           + " &nbsp;&nbsp; P14: " + txt(cab.get("pid_p14"))), ""],
        [campo("NOTES", t.get("observacoes")), ""],
    ]
    anexos = [os.path.basename(a) for a in (t.get("anexos_txt") or "").split(";") if a.strip()]
    linhas.append([campo("ATTACHED FILES", ", ".join(anexos)), ""])
    story += [secao("1. SHIPMENT CONTAINER INFORMATION"), Spacer(1, 3)]
    story.append(tabela(linhas, [93, 93], cabecalho=False,
                        extra=[("SPAN", (0, 4), (1, 4)), ("SPAN", (0, 5), (1, 5)), ("SPAN", (0, 6), (1, 6))]))

    # lotes
    story.append(Paragraph("Batches", est_h3))
    linhas_l = [[H("OPTO Batch"), H("Internal Lot"), H("Arrival / Cleaned"), H("Company"), H("Filters")]]
    for l in d["lotes"]:
        linhas_l.append([P(l["interno"]), P(l.get("lote_interno")), P(l["chegada"]),
                         P(l["empresa"]), P(l["filtros"])])
    if len(linhas_l) == 1:
        linhas_l.append([P("-")] * 5)
    story.append(tabela(linhas_l, [40, 40, 36, 50, 20]))

    # massas por posição
    story.append(Paragraph("Mass control by position", est_h3))
    linhas_m = [[H("Position"), H("Mass before (g)"), H("Mass after (g)"), H("Mass density (µg/cm²)")]]
    for m in d["massas"]:
        try:
            nome_pos = nomes_posicoes.get(int(m["posicao"]), "")
        except Exception:
            nome_pos = ""
        linhas_m.append([P(str(m["posicao"]) + (" - " + nome_pos if nome_pos else "")), P(m["massa_antes"]),
                         P(m["massa_depois"]), P(m["densidade_massa_ug_cm2"])])
    if len(linhas_m) == 1:
        linhas_m.append([P("-")] * 4)
    story.append(tabela(linhas_m, [46, 46, 46, 48]))
    story.append(Spacer(1, 8))

    # ---------------- decisão do lote ----------------
    ei = estado_imersao_dados(d)
    ee = estado_eficiencia_dados(d)
    dec = decisao_lote(ei, ee)
    cor_dec = {"APPROVED": VERDE, "REJECTED": VERMELHO}.get(dec, AZUL)
    completos, cont, _ = resumo_visual_dados(d)
    rev = d["ef_teste"]
    if rev.get("revisado") == "Yes":
        assinatura = "Signed by " + txt(rev.get("supervisor")) + " on " + txt(rev.get("data_revisao"))
    else:
        assinatura = "Pending Technical Supervisor review"
    visual_txt = (str(completos) + "/" + str(N_FILTROS) + " substrates classified  |  A: " + str(cont["A"])
                  + " (reject)  B: " + str(cont["B"]) + " (QA/QC review)  C: " + str(cont["C"]) + " (accept)")

    def estado_markup(e):
        return '<font color="' + hexcor(cor_estado.get(e, CINZA)) + '"><b>' + TXT_ESTADO[e] + "</b></font>"

    por_so = (t.get("qa_signoff_por") or "").strip()
    data_so = (t.get("qa_signoff_data") or "").strip()
    signoff_pdf = ("<b>" + xesc(por_so) + "</b>  |  Date: " + txt(data_so)) if por_so else "Pending final QA sign-off"
    linhas_d = [
        [M('<font size="7" color="#555555">BATCH DECISION (cryogenic immersion + optical efficiency)</font>'), ""],
        [M('<font size="16" color="' + hexcor(cor_dec) + '"><b>' + dec + "</b></font>", ParagraphStyle("dec", parent=base, leading=20)), ""],
        [M("<b>Visual inspection</b>"), M(visual_txt)],
        [M("<b>Cryogenic immersion</b>"), M(estado_markup(ei))],
        [M("<b>Optical efficiency</b>"), M(estado_markup(ee))],
        [M("<b>QA Sign-off by</b>"), M(signoff_pdf)],
    ]
    tb_dec = Table(linhas_d, colWidths=[45 * mm, largura - 45 * mm])
    tb_dec.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.5, cor_dec), ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1)),
                                ("LINEABOVE", (0, 2), (-1, 2), 0.4, GRADE), ("INNERGRID", (0, 2), (-1, -1), 0.3, GRADE),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(tb_dec)

    # ---------------- 2. inspeção visual ----------------
    story += [PageBreak(), secao("2. VISUAL INSPECTION TABLE"), Spacer(1, 3),
              proc(cab.get("data_inspecao"), cab.get("operador")), Spacer(1, 4)]
    cabecalho_v = [H(x) for x in ("Filter nº", "Visual Status", "Uniformity", "Stains", "Particles", "Edge Defects",
                                  "Finger Defects", "Other Defects", "Comments", "Class.")]
    linhas_v = [cabecalho_v]
    extra_v = [("FONTNAME", (0, 1), (-1, -1), fonte), ("FONTSIZE", (0, 1), (-1, -1), 7.5),
               ("ALIGN", (0, 1), (-1, -1), "CENTER"), ("FONTNAME", (0, 1), (0, -1), negrito)]
    cores_valor = {"Fail": VERMELHO, "Major": VERMELHO, "Minor": LARANJA, "Yes": LARANJA,
                   "A": VERMELHO, "B": LARANJA, "C": VERDE}
    chaves = ("visual_status", "uniformity", "stains", "particles", "edge_defects", "finger_defects",
              "other_defects")
    for n in range(1, N_FILTROS + 1):
        f = d["filtros"].get(n, {})
        linha = [format(n, "02d")] + [(f.get(k) or "-") for k in chaves]
        linha.append(P(f.get("comments"), ParagraphStyle("cm", parent=est_cel, fontSize=6.8, leading=8), vazio=""))
        linha.append(f.get("classification") or "-")
        linhas_v.append(linha)
        for c in list(range(1, 8)) + [9]:
            cor = cores_valor.get(linha[c])
            if cor is not None:
                extra_v.append(("TEXTCOLOR", (c, n), (c, n), cor))
                extra_v.append(("FONTNAME", (c, n), (c, n), negrito))
    story.append(tabela(linhas_v, [11, 16, 20, 14, 17, 14, 14, 14, 44, 22], extra=extra_v))

    story.append(Paragraph("Classification", est_h3))
    linhas_c = [[H("Class"), H("Description"), H("Disposition")],
                [P("A", est_cel), P("Defects affecting coating integrity, adhesion, or optical performance."), P("Reject glass substrate")],
                [P("B", est_cel), P("Localized defects with limited impact requiring evaluation."), P("QA/QC review")],
                [P("C", est_cel), P("Minor cosmetic defects with no expected impact on performance."), P("Accept")]]
    story.append(tabela(linhas_c, [14, 120, 52]))
    story.append(Spacer(1, 4))
    story.append(rev_pdf(cab.get("supervisor"), cab.get("data_revisao"), cab.get("revisado")))

    # ---------------- 3. imersão criogênica ----------------
    story += [Spacer(1, 10), CondPageBreak(95 * mm), secao("3. CRYOGENIC IMMERSION"), Spacer(1, 3),
              proc(t.get("imersao_data"), t.get("imersao_operador")), Spacer(1, 4)]
    linhas_i = [[H("Sample Control"), H("Mass Before (g)"), H("Mass After (g)"), H("Difference (after - before)"),
                 H("Condition (loss <= " + format(LIMITE_PERDA_PCT, "g") + " %)")]]
    extra_i = [("ALIGN", (0, 1), (-1, -1), "CENTER")]
    for i, amostra in enumerate(AMOSTRAS_IMERSAO, start=1):
        r = d["im_massas"].get(amostra) or {}
        dif = (txt(r.get("diferenca_g")) + " g (" + txt(r.get("diferenca_pct")) + " %)") if r.get("diferenca_g") else "-"
        ap = r.get("aprovado") or ""
        cond = M('<font color="' + hexcor(VERDE) + '"><b>Approved</b></font>', ParagraphStyle("c1", parent=est_cel, alignment=TA_CENTER)) if ap == "Yes" else (
            M('<font color="' + hexcor(VERMELHO) + '"><b>Rejected</b></font>', ParagraphStyle("c2", parent=est_cel, alignment=TA_CENTER)) if ap == "No" else
            P("-", est_cel))
        linhas_i.append([P(amostra, est_cel), P(r.get("massa_antes")), P(r.get("massa_depois")), P(dif), cond])
    story.append(tabela(linhas_i, [30, 34, 34, 50, 38], extra=extra_i))
    story.append(Spacer(1, 3))
    story.append(Paragraph("Accept criteria: a maximum mass loss of " + format(LIMITE_PERDA_PCT, "g")
                           + "% is acceptable. Any control substrate with a mass loss greater than "
                           + format(LIMITE_PERDA_PCT, "g") + "% is non-conforming.", est_nota))

    story.append(Paragraph("Post-immersion inspection", est_h3))
    linhas_k = [[H("Inspection Item"), H("Acceptance Criteria"), H("Rejected Condition"), H("Approved?")]]
    extra_k = [("ALIGN", (3, 1), (3, -1), "CENTER")]
    for i, (chave, titulo, aceite, rejeitado) in enumerate(ITENS_IMERSAO, start=1):
        valor = d["im_itens"].get(chave) or ""
        linhas_k.append([M("<b>" + xesc(titulo) + "</b>"), P(aceite), P(rejeitado), valor or "-"])
        if valor in ("Yes", "No"):
            extra_k += [("TEXTCOLOR", (3, i), (3, i), VERDE if valor == "Yes" else VERMELHO), ("FONTNAME", (3, i), (3, i), negrito)]
    story.append(tabela(linhas_k, [36, 62, 62, 26], extra=extra_k))
    story.append(Spacer(1, 3))
    story.append(M("<b>Notes:</b> " + txt(d["im_obs"])))
    story.append(M("<b>Result:</b> " + estado_markup(ei)))
    story.append(rev_pdf(t.get("imersao_supervisor"), t.get("imersao_data_revisao"), t.get("imersao_revisado")))

    # ---------------- 4. eficiência óptica ----------------
    te = d["ef_teste"]
    story += [Spacer(1, 10), CondPageBreak(110 * mm), secao("4. VUV OPTICAL EFFICIENCY"), Spacer(1, 3)]
    linhas_t = [
        [campo("TEST DATE", te.get("data_teste")), campo("PERFORMED BY (OPERATOR)", te.get("operador"))],
        [campo("REFERENCE SUBSTRATE ID", te.get("ref_id")), campo("REFERENCE INSTALLATION DATE", te.get("ref_data"))],
        [campo("MEAN ROOM TEMPERATURE (°C)", te.get("temperatura_c")), campo("MEAN RELATIVE HUMIDITY (%)", te.get("umidade_pct"))],
    ]
    story.append(tabela(linhas_t, [93, 93], cabecalho=False))

    story.append(Paragraph("QC samples - dimensions and mass", est_h3))
    linhas_s = [[H("Control position"), H("Tested?"), H("Length (mm)"), H("Width (mm)"), H("Mass before (g)"),
                 H("Mass after (g)"), H("Area (cm²)"), H("Mass density (µg/cm²)")]]
    linhas_x = [[H("Control position"), H("Efficiency"), H("Condition (x >= " + format(LIMITE_EFICIENCIA, "g") + ")")]]
    extra_x = [("ALIGN", (0, 1), (-1, -1), "CENTER")]
    for i, amostra in enumerate(AMOSTRAS_EFICIENCIA, start=1):
        r = d["ef_amostras"].get(amostra) or {}
        try:
            area = format(converter_float(r.get("comprimento_mm")) * converter_float(r.get("largura_mm")) / 100.0, ".2f")
        except Exception:
            area = "-"
        linhas_s.append([P(amostra), P(r.get("testada")), P(r.get("comprimento_mm")), P(r.get("largura_mm")),
                         P(r.get("massa_antes")), P(r.get("massa_depois")), P(area), P(r.get("densidade_ug_cm2"))])
        if r.get("testada") == "No":
            cond_txt, cor_c = "Not tested", CINZA
        elif (r.get("aprovado") or "") == "Yes":
            cond_txt, cor_c = "Approved", VERDE
        elif (r.get("aprovado") or "") == "No":
            cond_txt, cor_c = "Rejected", VERMELHO
        else:
            cond_txt, cor_c = "-", CINZA
        linhas_x.append([amostra, r.get("eficiencia") or "-", cond_txt])
        extra_x += [("TEXTCOLOR", (2, i), (2, i), cor_c), ("FONTNAME", (2, i), (2, i), negrito)]
    story.append(tabela(linhas_s, [24, 18, 22, 22, 25, 25, 22, 28],
                        extra=[("ALIGN", (0, 1), (-1, -1), "CENTER")]))
    story.append(Paragraph("Efficiency analysis", est_h3))
    story.append(tabela(linhas_x, [50, 68, 68], extra=extra_x))
    story.append(Spacer(1, 3))
    story.append(Paragraph("Only samples marked Tested = Yes are evaluated. x = UV transmission efficiency relative to the "
                           "reference substrate; x >= " + format(LIMITE_EFICIENCIA, "g") + " is approved (no upper bound). "
                           "The batch is approved only if at least " + str(MIN_AMOSTRAS_EFICIENCIA)
                           + " samples are tested and all tested samples pass.", est_nota))
    story.append(Spacer(1, 3))
    story.append(M("<b>Result:</b> " + estado_markup(ee)))
    story.append(M("<b>Notes:</b> " + txt(te.get("observacoes"))))
    story.append(rev_pdf(rev.get("supervisor"), rev.get("data_revisao"), rev.get("revisado")))

    # ---------------- 5. aval final do QA ----------------
    story += [Spacer(1, 12), CondPageBreak(30 * mm), secao("5. FINAL QA SIGN-OFF"), Spacer(1, 3)]
    story.append(tabela([[campo("FINAL QA SIGN-OFF BY", por_so or "________________________________"),
                          campo("DATE", data_so or "____ / ____ / ________")]], [124, 62], cabecalho=False))

    # ---------------- rodapé e gravação ----------------
    pid_txt = str(t.get("codigo_tarefa") or "")

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont(fonte, 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(12 * mm, 8 * mm, "PID " + pid_txt + "  |  Generated on " + datetime.now().strftime("%Y-%m-%d %H:%M")
                          + "  |  Deposition Control System for DUNE")
        canvas.drawRightString(A4[0] - 12 * mm, 8 * mm, "Page " + str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(caminho, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=15 * mm,
                            title="Deposition Inspection Record - " + pid_txt,
                            author="Deposition Control System for DUNE")
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    return caminho


def imprimir_relatorio_pdf():
    """Gera o PDF do cadastro selecionado e abre no visualizador."""
    tarefa_id = _tarefa_selecionada()
    if tarefa_id is None:
        return

    try:
        import reportlab  # noqa: F401
    except ImportError:
        messagebox.showerror(
            "PDF",
            "The 'reportlab' package is required to create PDFs.\n"
            "Install it with:  pip install reportlab\n\n"
            "Meanwhile the HTML report will be opened (use Print > Save as PDF in the browser)."
        )
        abrir_relatorio()
        return

    atualizar_lotes()
    d = coletar_dados_relatorio(tarefa_id)
    if d is None:
        messagebox.showwarning("PDF", "Task not found in the database")
        return
    pid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(d["tarefa"].get("codigo_tarefa") or "task"))
    os.makedirs(PASTA_PDF, exist_ok=True)
    caminho = os.path.join(PASTA_PDF, "Report_" + pid + "_task" + str(tarefa_id) + ".pdf")
    try:
        gerar_pdf_relatorio(tarefa_id, caminho)
    except PermissionError:
        messagebox.showerror("PDF", "Could not write the file. Close the PDF if it is open and try again:\n"
                             + os.path.abspath(caminho))
        return
    except Exception as erro:
        messagebox.showerror("PDF", "Could not generate the PDF:\n" + str(erro))
        return

    webbrowser.open(Path(caminho).resolve().as_uri())
    messagebox.showinfo("PDF", "Report saved at:\n" + os.path.abspath(caminho))


def gerar_todos_pdfs():
    """Gera, de uma vez, o PDF de todas as deposições cadastradas (para arquivo)."""
    try:
        import reportlab  # noqa: F401
    except ImportError:
        messagebox.showerror("PDF", "The 'reportlab' package is required to create PDFs.\n"
                             "Install it with:  python -m pip install reportlab")
        return
    con = conectar()
    tarefas_ids = con.execute("SELECT id, codigo_tarefa FROM tarefas ORDER BY id").fetchall()
    con.close()
    if not tarefas_ids:
        messagebox.showinfo("PDF", "There are no depositions registered yet.")
        return
    if not messagebox.askyesno("Export all PDFs",
                               f"Generate the PDF report of all {len(tarefas_ids)} depositions?\n"
                               "This may take a few minutes."):
        return

    atualizar_lotes()
    pasta = os.path.join(PASTA_PDF, "todas_" + datetime.now().strftime("%Y-%m-%d_%H%M"))
    os.makedirs(pasta, exist_ok=True)

    win = tk.Toplevel(janela)
    win.title("Export all PDFs")
    win.transient(janela)
    win.resizable(False, False)
    lbl = tk.Label(win, text="", width=60, anchor="w")
    lbl.pack(padx=20, pady=(16, 6))
    barra = ttk.Progressbar(win, length=420, maximum=len(tarefas_ids))
    barra.pack(padx=20, pady=6)
    estado = {"cancelar": False}
    tk.Button(win, text="Cancel", width=12, command=lambda: estado.update(cancelar=True)).pack(pady=(6, 14))
    win.protocol("WM_DELETE_WINDOW", lambda: estado.update(cancelar=True))

    feitos, erros = 0, []
    for n, (tid, pid_bruto) in enumerate(tarefas_ids, 1):
        if estado["cancelar"]:
            break
        pid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(pid_bruto or "task"))
        lbl.config(text=f"{n}/{len(tarefas_ids)}  {pid}")
        barra["value"] = n - 1
        win.update()
        try:
            gerar_pdf_relatorio(tid, os.path.join(pasta, "Report_" + pid + "_task" + str(tid) + ".pdf"))
            feitos += 1
        except Exception as erro:
            erros.append(f"task {tid} ({pid}): {erro}")
    win.destroy()

    texto = f"{feitos} PDF(s) saved in:\n{os.path.abspath(pasta)}"
    if estado["cancelar"]:
        texto += "\n\nCancelled before finishing."
    if erros:
        texto += f"\n\n{len(erros)} failed:\n" + "\n".join(erros[:8]) + ("\n..." if len(erros) > 8 else "")
    (messagebox.showwarning if erros else messagebox.showinfo)("Export all PDFs", texto)


# =====================================================
# FINAL QA SIGN-OFF (aval do chefe ao final de todos os testes)
# =====================================================
signoff_vars = {}


def criar_variaveis_signoff():
    signoff_vars["por"] = tk.StringVar(master=janela, value="")
    signoff_vars["data"] = tk.StringVar(master=janela, value="")
    for var in signoff_vars.values():
        var.trace_add("write", atualizar_status_signoff)


def limpar_signoff():
    if signoff_vars:
        for var in signoff_vars.values():
            var.set("")


def salvar_signoff_db(cur, tarefa_id):
    cur.execute("UPDATE tarefas SET qa_signoff_por = ?, qa_signoff_data = ? WHERE id = ?",
                (signoff_vars["por"].get().strip(), signoff_vars["data"].get().strip(), tarefa_id))


def carregar_signoff_db(cur, tarefa_id):
    cur.execute("SELECT qa_signoff_por, qa_signoff_data FROM tarefas WHERE id = ?", (tarefa_id,))
    row = cur.fetchone()
    signoff_vars["por"].set((row[0] if row else "") or "")
    signoff_vars["data"].set((row[1] if row else "") or "")


def atualizar_status_signoff(*args):
    try:
        por = signoff_vars["por"].get().strip()
        data = signoff_vars["data"].get().strip()
        if por and data:
            lbl_status_signoff.config(text="Signed", fg="#2e7d32")
        else:
            lbl_status_signoff.config(text="Pending", fg="#888888")
    except (NameError, tk.TclError):
        pass


# =====================================================
# INTERFACE
# =====================================================
inicializar_banco()

# ---------------------------------------------------------------------------
# BACKUP AUTOMÁTICO (semanal) dos bancos de dados
# ---------------------------------------------------------------------------
PASTA_BACKUP = "backups"        # pasta local onde ficam as cópias (criada ao lado dos bancos)
DIAS_ENTRE_BACKUPS = 7          # intervalo mínimo entre backups
BACKUPS_MANTIDOS = 30           # quantas cópias de cada banco manter (as mais antigas são removidas)
BANCOS_BACKUP = ("lotes.db", "rastreabilidade.db", "usuarios.db")


def _exportar_xlsx(banco, caminho):
    """Grava todas as tabelas de um banco SQLite em uma planilha .xlsx (uma aba por tabela)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    ilegais = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

    def limpo(v):
        if isinstance(v, (bytes, bytearray)):
            return "<binary>"
        if isinstance(v, str):
            return ilegais.sub("", v)[:32000]
        return v

    con = sqlite3.connect(banco)
    try:
        wb = Workbook()
        wb.remove(wb.active)
        tabelas = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for nome in tabelas:
            ws = wb.create_sheet(nome[:31])
            cur = con.execute('SELECT * FROM "' + nome + '"')
            ws.append([d[0] for d in cur.description])
            for linha in cur:
                ws.append([limpo(v) for v in linha])
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="2E6F95")
            ws.freeze_panes = "A2"
            for i, col in enumerate(ws.columns, 1):
                larg = max((len(str(c.value)) for c in list(col)[:200] if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(i)].width = min(max(larg + 2, 8), 50)
        if not wb.sheetnames:
            wb.create_sheet("empty")
        wb.save(caminho)
    finally:
        con.close()


def _datas_backups(prefixo):
    """Arquivos de backup existentes de um banco, do mais recente para o mais antigo."""
    if not os.path.isdir(PASTA_BACKUP):
        return []
    achados = [os.path.join(PASTA_BACKUP, n) for n in os.listdir(PASTA_BACKUP)
               if n.startswith(prefixo + "_") and n.endswith(".db")]
    return sorted(achados, key=os.path.getmtime, reverse=True)


def fazer_backup(forcar=False):
    """Copia cada banco para PASTA_BACKUP se o último backup tem mais de DIAS_ENTRE_BACKUPS dias.

    Usa a API de backup do SQLite (cópia consistente mesmo com o programa aberto) e confere a
    cópia com PRAGMA integrity_check. Retorna (lista_de_arquivos_criados, lista_de_erros).
    """
    criados, erros = [], []
    agora = datetime.now()
    for banco in BANCOS_BACKUP:
        if not os.path.exists(banco):
            continue
        prefixo = os.path.splitext(os.path.basename(banco))[0]
        existentes = _datas_backups(prefixo)
        if existentes and not forcar:
            idade = (agora.timestamp() - os.path.getmtime(existentes[0])) / 86400
            if idade < DIAS_ENTRE_BACKUPS:
                continue
        destino = os.path.join(PASTA_BACKUP, prefixo + "_" + agora.strftime("%Y-%m-%d_%H%M%S") + ".db")
        origem = destino_con = None
        try:
            os.makedirs(PASTA_BACKUP, exist_ok=True)
            origem = sqlite3.connect(banco)
            destino_con = sqlite3.connect(destino)
            origem.backup(destino_con)
            ok = destino_con.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise RuntimeError("integrity_check: " + str(ok))
            criados.append(destino)
        except Exception as e:
            erros.append(banco + ": " + str(e))
            try:
                if destino_con is not None:
                    destino_con.close()
                    destino_con = None
                if os.path.exists(destino):
                    os.remove(destino)
            except Exception:
                pass
        finally:
            for c in (origem, destino_con):
                try:
                    if c is not None:
                        c.close()
                except Exception:
                    pass
        if criados and criados[-1] == destino and prefixo != "usuarios":   # a planilha não inclui senhas
            try:
                _exportar_xlsx(destino, destino[:-3] + ".xlsx")
            except ImportError:
                erros.append("Excel não gerado: instale o pacote openpyxl  (python -m pip install openpyxl)")
            except Exception as e:
                erros.append(banco + " (Excel): " + str(e))
        for antigo in _datas_backups(prefixo)[BACKUPS_MANTIDOS:]:
            for arq in (antigo, antigo[:-3] + ".xlsx"):
                try:
                    if os.path.exists(arq):
                        os.remove(arq)
                except Exception:
                    pass
    return criados, erros


INDICES_BANCO = {
    "rastreabilidade.db": [("massa_posicoes", "id_tarefa"), ("inspecao_visual_cab", "id_tarefa"),
                           ("inspecao_visual_filtros", "id_tarefa"), ("imersao_massas", "id_tarefa"),
                           ("imersao_itens", "id_tarefa"), ("tarefa_lotes", "id_tarefa"),
                           ("eficiencia_teste", "id_tarefa"), ("eficiencia_amostras", "id_tarefa")],
    "lotes.db": [("lotes_internos", "id_lote")],
}


def criar_indices():
    """Índices nas colunas de ligação: mantêm listas e relatórios rápidos com muitos registros."""
    for banco, lista in INDICES_BANCO.items():
        if not os.path.exists(banco):
            continue
        con = None
        try:
            con = sqlite3.connect(banco, timeout=30)
            for tabela_, col in lista:
                try:
                    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{tabela_}_{col} ON {tabela_}({col})")
                except sqlite3.Error:
                    pass          # tabela ainda não existe neste banco
            con.commit()
        except Exception:
            pass
        finally:
            if con is not None:
                con.close()


TIPOS_ANTIGOS = {"Substrato": "Substrate", "Substrato+dicroico": "Substrate + dichroic"}


def migrar_textos_antigos():
    """Registros antigos guardavam o tipo de filtro em português; passa para o inglês."""
    if not os.path.exists("rastreabilidade.db"):
        return
    con = None
    try:
        con = sqlite3.connect("rastreabilidade.db", timeout=30)
        for antigo, novo in TIPOS_ANTIGOS.items():
            con.execute("UPDATE tarefas SET descricao = ? WHERE descricao = ?", (novo, antigo))
        con.commit()
    except Exception:
        pass
    finally:
        if con is not None:
            con.close()


def backup_ao_abrir():
    """Chamado ao abrir o programa: faz o backup semanal e avisa só se algo falhar."""
    criar_indices()
    try:
        _, erros = fazer_backup()
    except Exception as e:
        erros = [str(e)]
    migrar_textos_antigos()
    if erros:
        messagebox.showwarning("Backup", "Atenção no backup automático:\n\n" + "\n".join(erros))


def backup_agora():
    """Botão 'Backup now': copia os bancos (.db) e gera as planilhas Excel imediatamente."""
    leptons_auth.registrar("BACKUP_NOW")
    try:
        criados, erros = fazer_backup(forcar=True)
    except Exception as e:
        criados, erros = [], [str(e)]
    texto = ""
    if criados:
        texto += "Backup saved in:\n" + os.path.abspath(PASTA_BACKUP) + "\n\n" + "\n".join(os.path.basename(c) for c in criados)
    if erros:
        texto += ("\n\n" if texto else "") + "Warnings:\n" + "\n".join(erros)
    if erros:
        messagebox.showwarning("Backup", texto or "Backup failed.")
    else:
        messagebox.showinfo("Backup", texto or "No database found to back up.")


janela = tk.Tk()
leptons_auth.iniciar(janela, "Deposition Control System")
janela.title("Deposition Control System for DUNE")
janela.geometry("1350x900")
janela.configure(bg="#f4f6f8")

style = ttk.Style()
style.theme_use("clam")
style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6)
style.configure("Titulo.TLabel", font=("Segoe UI", 14, "bold"))
style.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

eficiencia_var = tk.StringVar(value="Não")
imersao_var = tk.StringVar(value="Não")
valor_ef_var = tk.StringVar(value="")
criar_variaveis_inspecao()
criar_variaveis_imersao()
criar_variaveis_eficiencia()
criar_variaveis_signoff()

# ---------- BARRA SUPERIOR ----------
barra = tk.Frame(janela, bg="#1f3a5f", height=72)
barra.pack(fill="x")
barra.pack_propagate(False)
barra.grid_columnconfigure(0, weight=1)
barra.grid_columnconfigure(1, weight=2)
barra.grid_columnconfigure(2, weight=1)

# Logos com fallback, para o sistema abrir mesmo se a imagem não estiver na pasta.
def inserir_logo(nome_arquivo, coluna, sticky):
    try:
        img = Image.open(nome_arquivo).resize((110, 48))
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(barra, image=photo, bg="#1f3a5f")
        label.image = photo
    except Exception:
        label = tk.Label(barra, text="", bg="#1f3a5f")
    label.grid(row=0, column=coluna, sticky=sticky, padx=15)

inserir_logo("esquerda.png", 0, "w")

tk.Label(
    barra,
    text="Deposition Control System for DUNE",
    fg="white",
    bg="#1f3a5f",
    font=("Segoe UI", 15, "bold")
).grid(row=0, column=1)

frame_relogio = tk.Frame(barra, bg="#1f3a5f")
frame_relogio.grid(row=0, column=2, sticky="e", padx=15)
lbl_relogio = tk.Label(frame_relogio, text="", fg="white", bg="#1f3a5f", font=("Segoe UI", 10, "bold"))
lbl_relogio.pack(anchor="e")
inserir_logo("direita.png", 3, "e")   # logo na coluna própria; o relógio fica à esquerda dela

# ---------- CONTEÚDO ----------
frame = tk.Frame(janela, bg="#f4f6f8", padx=20, pady=10)
frame.pack(fill="both", expand=True)
frame.grid_columnconfigure(1, weight=1)
frame.grid_columnconfigure(2, weight=1)

# ---------- DADOS PRINCIPAIS ----------
quadro_dados = tk.LabelFrame(frame, text="Deposition Data", bg="#f4f6f8", font=("Segoe UI", 11, "bold"), padx=15, pady=12)
quadro_dados.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=(0, 15))

cab_vars = inspecao_vars["cab"]


def rotulo_dados(linha, texto, sticky="w"):
    tk.Label(quadro_dados, text=texto, bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(
        row=linha, column=0, sticky=sticky, pady=6, padx=(0, 10))


# Lotes (uma deposição pode usar mais de um lote de filtros)
rotulo_dados(0, "Batches:", sticky="nw")
lotes = carregar_lotes()

frame_lote = tk.Frame(quadro_dados, bg="#f4f6f8")
frame_lote.grid(row=0, column=1, sticky="w", pady=(2, 6))

cols_lotes = ("OPTO Batch", "Internal Lot", "Arrival", "Company", "Filters")
tab_lotes_sel = ttk.Treeview(frame_lote, columns=cols_lotes, show="headings", height=3, selectmode="extended")
for c, largura in zip(cols_lotes, (180, 180, 110, 170, 70)):
    tab_lotes_sel.heading(c, text=c)
    tab_lotes_sel.column(c, anchor="center", width=largura)
tab_lotes_sel.grid(row=0, column=0, sticky="w")
sb_lotes = ttk.Scrollbar(frame_lote, orient="vertical", command=tab_lotes_sel.yview)
tab_lotes_sel.configure(yscrollcommand=sb_lotes.set)
sb_lotes.grid(row=0, column=1, sticky="ns")

botoes_lote = tk.Frame(frame_lote, bg="#f4f6f8")
botoes_lote.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
ttk.Button(botoes_lote, text="Add batch / internal lot...", command=selecionar_lote_em_janela).pack(side="left", padx=(0, 6))
ttk.Button(botoes_lote, text="Remove selected", command=remover_lotes_selecionados).pack(side="left", padx=6)
ttk.Button(botoes_lote, text="Open batch system", command=abrir_sistema_lotes).pack(side="left", padx=6)
ttk.Button(botoes_lote, text="↻", width=3, command=atualizar_lotes).pack(side="left", padx=6)

lbl_info_lote = tk.Label(frame_lote, text="No batch selected", bg="#f4f6f8", fg="#1f3a5f",
                         anchor="w", font=("Segoe UI", 10, "bold"))
lbl_info_lote.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

# Run
rotulo_dados(1, "Run:")
entry_run = ttk.Entry(quadro_dados, textvariable=cab_vars["run_evaporation"], width=35)
entry_run.grid(row=1, column=1, sticky="w", pady=6)

# Date
rotulo_dados(2, "Date:")
entry_data = ttk.Entry(quadro_dados, width=35)
entry_data.insert(0, datetime.today().strftime("%Y-%m-%d"))
entry_data.grid(row=2, column=1, sticky="w", pady=6)

# PID
rotulo_dados(3, "PID:")
entry_pid = ttk.Entry(quadro_dados, textvariable=cab_vars["box_pid"], width=35)
entry_pid.grid(row=3, column=1, sticky="w", pady=6)

# PID CONTROL (P02, P03, P14)
rotulo_dados(4, "PID CONTROL:")
frame_pid_ctrl = tk.Frame(quadro_dados, bg="#f4f6f8")
frame_pid_ctrl.grid(row=4, column=1, sticky="w", pady=6)
for i, (rotulo_p, chave_p) in enumerate((("P02", "pid_p02"), ("P03", "pid_p03"), ("P14", "pid_p14"))):
    tk.Label(frame_pid_ctrl, text=f"{rotulo_p}:", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(
        row=0, column=2 * i, sticky="e", padx=(0 if i == 0 else 16, 4))
    ttk.Entry(frame_pid_ctrl, textvariable=cab_vars[chave_p], width=18).grid(row=0, column=2 * i + 1)

# Position
rotulo_dados(5, "Position (ex: 1-28):")
entry_posicao = ttk.Entry(quadro_dados, width=35)
entry_posicao.grid(row=5, column=1, sticky="w", pady=6)

# Responsible
rotulo_dados(6, "Responsible:")
entry_resp = ttk.Entry(quadro_dados, width=35)
entry_resp.grid(row=6, column=1, sticky="w", pady=6)

# Campos que já existiam e continuam abaixo
rotulo_dados(7, "Filter type:")
tipo_var = tk.StringVar(value="Substrate")
frame_tipo = tk.Frame(quadro_dados, bg="#f4f6f8")
frame_tipo.grid(row=7, column=1, sticky="w")
ttk.Radiobutton(frame_tipo, text="Substrate", variable=tipo_var, value="Substrate").pack(side="left", padx=(0, 15))
ttk.Radiobutton(frame_tipo, text="Substrate + dichroic", variable=tipo_var, value="Substrate + dichroic").pack(side="left")

rotulo_dados(8, "Observations:", sticky="nw")
entry_obs = tk.Text(quadro_dados, height=4, width=70, font=("Segoe UI", 9), bd=1, relief="solid")
entry_obs.grid(row=8, column=1, sticky="w", pady=6)

frame_anexo = tk.Frame(quadro_dados, bg="#f4f6f8")
frame_anexo.grid(row=9, column=0, columnspan=2, sticky="w", pady=6)
btn_anexo = tk.Button(frame_anexo, text="📎 Attach images / files", command=adicionar_anexo, bg="#e0e6ed", relief="flat", padx=10, pady=4)
btn_anexo.pack(side="left")
lbl_anexos = tk.Label(frame_anexo, text="No files", bg="#f4f6f8")
lbl_anexos.pack(side="left", padx=10)

# ---------- TESTE DE QUALIDADE À DIREITA ----------
quadro_qualidade = tk.LabelFrame(frame, text="Quality Test", bg="#f4f6f8", font=("Segoe UI", 11, "bold"), padx=15, pady=12)
quadro_qualidade.grid(row=0, column=2, sticky="nsew")


def criar_botao_teste(linha, titulo, comando, cor):
    tk.Button(
        quadro_qualidade, text=titulo, command=comando, bg=cor, fg="white",
        font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2",
        width=26, pady=9, activebackground=cor, activeforeground="white"
    ).grid(row=linha, column=0, sticky="w", pady=(10, 2))
    lbl = tk.Label(quadro_qualidade, text="", bg="#f4f6f8", fg="#1f3a5f", font=("Segoe UI", 9), anchor="w")
    lbl.grid(row=linha + 1, column=0, sticky="w", pady=(0, 6))
    return lbl


lbl_status_visual = criar_botao_teste(0, "Visual Inspection", abrir_inspecao_visual, "#2e6f95")
lbl_status_crio = criar_botao_teste(2, "Cryogenic Immersion", abrir_imersao_criogenica, "#1f77b4")
lbl_status_ef = criar_botao_teste(4, "Optical Efficiency", abrir_eficiencia_optica, "#00838f")

eficiencia_var.trace_add("write", atualizar_resumos)
imersao_var.trace_add("write", atualizar_resumos)
valor_ef_var.trace_add("write", atualizar_resumos)
atualizar_resumos()

# ---------- Final QA Sign-Off (aval final, depois de todos os testes) ----------
quadro_signoff = tk.LabelFrame(quadro_qualidade, text="Final QA Sign-Off", bg="#f4f6f8",
                               font=("Segoe UI", 10, "bold"), padx=8, pady=6)
quadro_signoff.grid(row=6, column=0, sticky="we", pady=(14, 0))
tk.Label(quadro_signoff, text="Final QA Sign-Off by:", bg="#f4f6f8", font=("Segoe UI", 9, "bold")).grid(
    row=0, column=0, columnspan=3, sticky="w")
ttk.Entry(quadro_signoff, textvariable=signoff_vars["por"], width=36).grid(
    row=1, column=0, columnspan=3, sticky="we", pady=(2, 6))
tk.Label(quadro_signoff, text="Date:", bg="#f4f6f8", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w")
ttk.Entry(quadro_signoff, textvariable=signoff_vars["data"], width=14).grid(row=2, column=1, padx=(6, 4))
ttk.Button(quadro_signoff, text="Today", width=7,
           command=lambda: signoff_vars["data"].set(datetime.today().strftime("%Y-%m-%d"))).grid(row=2, column=2)
lbl_status_signoff = tk.Label(quadro_signoff, text="Pending", bg="#f4f6f8", fg="#888888", font=("Segoe UI", 9, "bold"))
lbl_status_signoff.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
atualizar_status_signoff()

lbl_modo = tk.Label(quadro_qualidade, text="Mode: new record", bg="#f4f6f8", fg="#1f3a5f", font=("Segoe UI", 10, "bold"))
lbl_modo.grid(row=7, column=0, sticky="w", pady=(18, 0))

tk.Label(quadro_qualidade, text="Current date/time:", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=8, column=0, sticky="w", pady=(14, 2))
lbl_relogio_tela = tk.Label(quadro_qualidade, text="", bg="#f4f6f8", fg="#333333", font=("Segoe UI", 10))
lbl_relogio_tela.grid(row=9, column=0, sticky="w")

def atualizar_relogio_tela():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    lbl_relogio_tela.config(text=agora)
    lbl_relogio.config(text=agora)
    janela.after(1000, atualizar_relogio_tela)

# ---------- MASSAS ----------
quadro_massas = tk.LabelFrame(frame, text="Mass Control by Position", bg="#f4f6f8", font=("Segoe UI", 11, "bold"), padx=15, pady=12)
quadro_massas.grid(row=1, column=0, columnspan=3, pady=18, sticky="ew")

tk.Label(quadro_massas, text="Position", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=20)
tk.Label(quadro_massas, text="Mass Before (g)", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=1, padx=25)
tk.Label(quadro_massas, text="Mass After (g)", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, padx=25)
tk.Label(quadro_massas, text="Mass density (µg/cm²)", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).grid(row=0, column=3, padx=25)

nomes_posicoes = {2: "Center", 3: "Middle", 14: "External"}
densidade_vars = {2: tk.StringVar(), 3: tk.StringVar(), 14: tk.StringVar()}

def linha_massa(pos, row):
    texto = f"{pos} - {nomes_posicoes.get(pos, '')}"
    tk.Label(quadro_massas, text=texto, bg="#f4f6f8", font=("Segoe UI", 10)).grid(row=row, column=0, pady=8)
    a = ttk.Entry(quadro_massas, width=14)
    a.grid(row=row, column=1, pady=8)
    d = ttk.Entry(quadro_massas, width=14)
    d.grid(row=row, column=2, pady=8)

    lbl_dens = tk.Label(quadro_massas, textvariable=densidade_vars[pos], width=18,
                        bg="white", relief="solid", bd=1, font=("Segoe UI", 9))
    lbl_dens.grid(row=row, column=3, pady=8)

    a.bind("<KeyRelease>", atualizar_densidades)
    d.bind("<KeyRelease>", atualizar_densidades)
    a.bind("<FocusOut>", atualizar_densidades)
    d.bind("<FocusOut>", atualizar_densidades)
    return a, d

entry_a2, entry_d2 = linha_massa(2, 1)
entry_a3, entry_d3 = linha_massa(3, 2)
entry_a14, entry_d14 = linha_massa(14, 3)

frame_ptp_mass = tk.Frame(quadro_massas, bg="#f4f6f8")
frame_ptp_mass.grid(row=1, column=4, rowspan=3, sticky="n", padx=(45, 10), pady=6)
tk.Label(frame_ptp_mass, text="PTP Mass:", bg="#f4f6f8", font=("Segoe UI", 10, "bold")).pack(anchor="w")
linha_ptp = tk.Frame(frame_ptp_mass, bg="#f4f6f8")
linha_ptp.pack(anchor="w", pady=(6, 0))
entry_ptp_mass = ttk.Entry(linha_ptp, width=16)
entry_ptp_mass.pack(side="left")
tk.Label(linha_ptp, text="g", bg="#f4f6f8").pack(side="left", padx=(6, 0))
tk.Label(frame_ptp_mass, text=f"Area: {AREA_FILTRO_MM2:.0f} mm² = {AREA_FILTRO_CM2:.1f} cm²", bg="#f4f6f8", fg="#555555", font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))
tk.Label(frame_ptp_mass, text="density = (after − before) / area", bg="#f4f6f8", fg="#555555", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

# ---------- BOTÕES ----------
btn = tk.Frame(frame, bg="#f4f6f8")
btn.grid(row=2, column=0, columnspan=3, pady=12)
btn1 = tk.Frame(btn, bg="#f4f6f8")
btn1.pack(side="top")
btn2 = tk.Frame(btn, bg="#f4f6f8")
btn2.pack(side="top", pady=(8, 0))

tk.Button(btn1, text="Save", command=salvar_tarefa, bg="#2e6f95", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
tk.Button(btn1, text="Load for edit", command=carregar_para_edicao, bg="#1f77b4", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
tk.Button(btn1, text="Edit / Update", command=editar_tarefa, bg="#ef6c00", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
tk.Button(btn1, text="Clear", command=limpar_campos, bg="#607d8b", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
tk.Button(btn1, text="Delete", command=excluir_tarefa, bg="#c62828", fg="white", font=("Segoe UI", 10, "bold"), padx=15, pady=6, relief="flat").pack(side="left", padx=8)
ttk.Button(btn1, text="Generate QR Code", command=gerar_qr).pack(side="left", padx=8, ipadx=10)
ttk.Button(btn1, text="Print report (PDF)", command=imprimir_relatorio_pdf).pack(side="left", padx=8, ipadx=10)
ttk.Button(btn2, text="Export all PDFs", command=gerar_todos_pdfs).pack(side="left", padx=8, ipadx=10)
ttk.Button(btn2, text="Backup now", command=backup_agora).pack(side="left", padx=8, ipadx=10)
ttk.Button(btn1, text="View details", command=abrir_detalhes_tarefa).pack(side="left", padx=8, ipadx=10)

# ---------- TABELA ----------
cols = ("ID", "PID", "Internal Batch", "Responsible", "Deposition Date", "Visual Inspection", "Optical Efficiency", "Cryogenic Immersion")
tabela = ttk.Treeview(frame, columns=cols, show="headings", height=8)
tabela.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=10)

for c in cols:
    tabela.heading(c, text=c)
    tabela.column(c, anchor="center", width=120)

tabela.column("Internal Batch", width=240)      # lote interno (caixa menor) usado na deposição
tabela.bind("<Double-1>", lambda event: carregar_para_edicao())

frame.rowconfigure(3, weight=1)
frame.columnconfigure(1, weight=1)

carregar_tarefas()
atualizar_relogio_tela()
iniciar_servidor_relatorios()
_responsavel_padrao()
janela.after(500, backup_ao_abrir)
janela.mainloop()
