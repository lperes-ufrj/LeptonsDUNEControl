"""Gravação no banco de tarefas: conexão, criação/migração das tabelas, configurações e o código dos links.

As tabelas e migrações são as mesmas do programa de mesa (inicializar_banco), para os dois poderem abrir o
mesmo rastreabilidade.db.
"""
import hashlib
import hmac
import secrets
import sqlite3

from . import dados

TIPOS_ANTIGOS = {"Substrato": "Substrate", "Substrato+dicroico": "Substrate + dichroic"}


def abrir(caminho):
    """Abre o banco com WAL, gravação segura e espera se estiver ocupado."""
    con = sqlite3.connect(str(caminho), timeout=30)
    con.execute("PRAGMA journal_mode=WAL")      # leituras e gravações não se bloqueiam; mais seguro contra queda
    con.execute("PRAGMA synchronous=FULL")      # confirma cada gravação no disco
    con.execute("PRAGMA busy_timeout=30000")    # espera até 30 s se o banco estiver ocupado
    con.row_factory = sqlite3.Row
    return con


def conectar():
    return abrir(dados.DB_TAREFAS)


def _colunas(cur, tabela):
    return [c[1] for c in cur.execute(f"PRAGMA table_info({tabela})")]


def _adicionar_coluna(cur, tabela, coluna, tipo):
    if coluna not in _colunas(cur, tabela):
        cur.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def inicializar_banco():
    con = conectar()
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, codigo_tarefa TEXT, responsavel TEXT, data_inicio TEXT,
            status TEXT, descricao TEXT, lote_entrada_id INTEGER, codigo_lote TEXT, position_range TEXT,
            observacoes TEXT, anexos_txt TEXT, eficiencia_optica_ok TEXT, valor_eficiencia TEXT,
            imersao_criogenica_ok TEXT, data_hora_registro TEXT, massa_ptp_g TEXT);
        CREATE TABLE IF NOT EXISTS massa_posicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_tarefa INTEGER, posicao INTEGER, massa_antes TEXT,
            massa_depois TEXT, densidade_massa_ug_cm2 TEXT);
        CREATE TABLE IF NOT EXISTS inspecao_visual_cab (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_tarefa INTEGER, box_pid TEXT, run_evaporation TEXT,
            inspector TEXT, pid_p02 TEXT, pid_p03 TEXT, pid_p14 TEXT, notes TEXT, data_inspecao TEXT,
            operador TEXT, supervisor TEXT, data_revisao TEXT, revisado TEXT);
        CREATE TABLE IF NOT EXISTS inspecao_visual_filtros (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_tarefa INTEGER, filtro INTEGER, visual_status TEXT,
            uniformity TEXT, stains TEXT, particles TEXT, edge_defects TEXT, finger_defects TEXT,
            other_defects TEXT, comments TEXT, classification TEXT);
        CREATE TABLE IF NOT EXISTS imersao_massas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_tarefa INTEGER, amostra TEXT, massa_antes TEXT,
            massa_depois TEXT, diferenca_g TEXT, diferenca_pct TEXT, aprovado TEXT);
        CREATE TABLE IF NOT EXISTS imersao_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_tarefa INTEGER, item TEXT, aprovado TEXT);
        CREATE TABLE IF NOT EXISTS tarefa_lotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_tarefa INTEGER, lote_id INTEGER, codigo_lote TEXT);
        CREATE TABLE IF NOT EXISTS eficiencia_teste (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_tarefa INTEGER, data_teste TEXT, ref_id TEXT, ref_data TEXT,
            temperatura_c TEXT, umidade_pct TEXT, supervisor TEXT, data_revisao TEXT, revisado TEXT,
            observacoes TEXT, operador TEXT);
        CREATE TABLE IF NOT EXISTS eficiencia_amostras (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_tarefa INTEGER, amostra TEXT, testada TEXT,
            comprimento_mm TEXT, largura_mm TEXT, massa_antes TEXT, massa_depois TEXT, area_cm2 TEXT,
            densidade_ug_cm2 TEXT, eficiencia TEXT, aprovado TEXT);
        CREATE TABLE IF NOT EXISTS config_sistema (chave TEXT PRIMARY KEY, valor TEXT);
    """)
    # migração para bancos já existentes
    for coluna in ("codigo_lote", "eficiencia_optica_ok", "valor_eficiencia", "imersao_criogenica_ok",
                   "data_hora_registro", "anexos_txt", "position_range", "observacoes", "massa_ptp_g", "lote_ptp",
                   "imersao_observacoes", "imersao_data", "imersao_operador", "imersao_supervisor",
                   "imersao_data_revisao", "imersao_revisado", "qa_signoff_por", "qa_signoff_data"):
        _adicionar_coluna(cur, "tarefas", coluna, "TEXT")
    _adicionar_coluna(cur, "massa_posicoes", "densidade_massa_ug_cm2", "TEXT")
    _adicionar_coluna(cur, "eficiencia_amostras", "testada", "TEXT")
    for coluna in ("data_inspecao", "operador", "supervisor", "data_revisao", "revisado"):
        _adicionar_coluna(cur, "inspecao_visual_cab", coluna, "TEXT")
    _adicionar_coluna(cur, "eficiencia_teste", "operador", "TEXT")
    _adicionar_coluna(cur, "tarefa_lotes", "lote_interno_id", "INTEGER")
    _adicionar_coluna(cur, "tarefa_lotes", "codigo_lote_interno", "TEXT")
    _adicionar_coluna(cur, "tarefa_lotes", "tipo_lote", "TEXT")      # 'opto' ou 'limpeza' (Leptons)
    # registros antigos guardavam o tipo de filtro em português
    for antigo, novo in TIPOS_ANTIGOS.items():
        cur.execute("UPDATE tarefas SET descricao = ? WHERE descricao = ?", (novo, antigo))
    con.commit()
    con.close()
    criar_indices()


INDICES = {
    "rastreabilidade.db": [("massa_posicoes", "id_tarefa"), ("inspecao_visual_cab", "id_tarefa"),
                           ("inspecao_visual_filtros", "id_tarefa"), ("imersao_massas", "id_tarefa"),
                           ("imersao_itens", "id_tarefa"), ("tarefa_lotes", "id_tarefa"),
                           ("eficiencia_teste", "id_tarefa"), ("eficiencia_amostras", "id_tarefa")],
    "lotes.db": [("lotes_internos", "id_lote")],
}


def criar_indices():
    """Índices nas colunas de ligação: mantêm listas e relatórios rápidos com muitos registros."""
    for nome, lista in INDICES.items():
        caminho = dados.PASTA / nome
        if not caminho.exists():
            continue
        con = sqlite3.connect(str(caminho), timeout=30)
        try:
            for tabela, col in lista:
                try:
                    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{tabela}_{col} ON {tabela}({col})")
                except sqlite3.Error:
                    pass          # tabela ainda não existe neste banco
            con.commit()
        finally:
            con.close()


# ---------------- configurações (config_sistema) ----------------
def ler_config(chave):
    con = conectar()
    try:
        row = con.execute("SELECT valor FROM config_sistema WHERE chave = ?", (chave,)).fetchone()
        return row[0] if row else ""
    finally:
        con.close()


def gravar_config(chave, valor):
    con = conectar()
    try:
        con.execute("INSERT OR REPLACE INTO config_sistema (chave, valor) VALUES (?, ?)", (chave, valor))
        con.commit()
    finally:
        con.close()


def token_tarefa(tarefa_id):
    """Código do link do relatório (mesmo segredo do programa de mesa: os QR codes antigos continuam valendo)."""
    con = conectar()
    try:
        con.execute("INSERT OR IGNORE INTO config_sistema (chave, valor) VALUES ('segredo_qr', ?)",
                    (secrets.token_hex(16),))
        con.commit()
        segredo = con.execute("SELECT valor FROM config_sistema WHERE chave = 'segredo_qr'").fetchone()[0]
    finally:
        con.close()
    return hmac.new(segredo.encode(), str(tarefa_id).encode(), hashlib.sha256).hexdigest()[:12]
