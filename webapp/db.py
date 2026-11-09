"""Banco de dados MariaDB: conexão (PyMySQL), as tabelas e um adaptador com a forma do sqlite3 usada no código.

O SQL do programa usa '?' nos parâmetros (como antes, no SQLite); aqui eles viram o '%s' do PyMySQL. Cada linha
lida aceita r["coluna"] (sem diferenciar maiúsculas), r[0], dict(r) e desempacotamento (a, b = r). Uma conexão
usada em "with con:" grava tudo ao sair do bloco, ou desfaz tudo se houver erro.
"""
import pymysql

from . import config

Erro = pymysql.MySQLError
ErroIntegridade = pymysql.err.IntegrityError

_FIM = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

# Todas as tabelas. Valores digitados ficam em TEXT, como estavam no SQLite: o programa compara e mostra o texto
# gravado (ex.: massas com vírgula), e as contas convertem com dados.numero().
TABELAS = {
    # ---------------- amostras de deposição (tarefas) ----------------
    "tarefas": """
        id INT AUTO_INCREMENT PRIMARY KEY, codigo_tarefa TEXT, descricao TEXT, responsavel TEXT, data_inicio TEXT,
        status TEXT, lote_entrada_id INT, codigo_lote TEXT, position_range TEXT, observacoes TEXT, anexos_txt TEXT,
        eficiencia_optica_ok TEXT, valor_eficiencia TEXT, imersao_criogenica_ok TEXT, data_hora_registro TEXT,
        massa_ptp_g TEXT, lote_ptp TEXT, imersao_observacoes TEXT, imersao_data TEXT, imersao_operador TEXT,
        imersao_supervisor TEXT, imersao_data_revisao TEXT, imersao_revisado TEXT, qa_signoff_por TEXT,
        qa_signoff_data TEXT""",
    "massa_posicoes": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, posicao INT, massa_antes TEXT, massa_depois TEXT,
        densidade_massa_ug_cm2 TEXT, INDEX (id_tarefa)""",
    "inspecao_visual_cab": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, box_pid TEXT, run_evaporation TEXT, inspector TEXT,
        pid_p02 TEXT, pid_p03 TEXT, pid_p14 TEXT, notes TEXT, data_inspecao TEXT, operador TEXT, supervisor TEXT,
        data_revisao TEXT, revisado TEXT, INDEX (id_tarefa)""",
    "inspecao_visual_filtros": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, filtro INT, visual_status TEXT, uniformity TEXT, stains TEXT,
        particles TEXT, edge_defects TEXT, finger_defects TEXT, other_defects TEXT, comments TEXT,
        classification TEXT, INDEX (id_tarefa)""",
    "imersao_massas": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, amostra TEXT, massa_antes TEXT, massa_depois TEXT,
        diferenca_g TEXT, diferenca_pct TEXT, aprovado TEXT, INDEX (id_tarefa)""",
    "imersao_itens": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, item TEXT, aprovado TEXT, INDEX (id_tarefa)""",
    "tarefa_lotes": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, lote_id INT, codigo_lote TEXT, lote_interno_id INT,
        codigo_lote_interno TEXT, tipo_lote TEXT, INDEX (id_tarefa)""",
    "filtro_origem": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, filtro INT, tipo_lote TEXT, lote_id INT, codigo_lote TEXT,
        lote_interno_id INT, codigo_lote_interno TEXT, INDEX (id_tarefa)""",
    "eficiencia_teste": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, data_teste TEXT, ref_id TEXT, ref_data TEXT,
        temperatura_c TEXT, umidade_pct TEXT, operador TEXT, supervisor TEXT, data_revisao TEXT, revisado TEXT,
        observacoes TEXT, INDEX (id_tarefa)""",
    "eficiencia_amostras": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, amostra TEXT, testada TEXT, comprimento_mm TEXT,
        largura_mm TEXT, massa_antes TEXT, massa_depois TEXT, area_cm2 TEXT, densidade_ug_cm2 TEXT, eficiencia TEXT,
        aprovado TEXT, INDEX (id_tarefa)""",
    # filtros retirados na inspeção visual (descarte / limpeza / reuso), ver retirados.py
    "filtro_retirado": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_tarefa INT, filtro INT, classe TEXT, destino TEXT, observacao TEXT,
        data_hora TEXT, usuario TEXT, origem_pid TEXT, origem_run TEXT, limpeza_id INT, codigo_limpeza TEXT,
        usado_tarefa_id INT, usado_filtro INT, INDEX (id_tarefa), INDEX (limpeza_id), INDEX (usado_tarefa_id)""",
    "config_sistema": """
        chave VARCHAR(64) PRIMARY KEY, valor TEXT""",
    # ---------------- lotes OPTO (caixas menores = lotes internos) e lotes de limpeza ----------------
    "lotes": """
        id INT AUTO_INCREMENT PRIMARY KEY, tracking_id TEXT, lote_geral TEXT, lote_fornecedor TEXT,
        data_recebimento TEXT, responsavel TEXT, fornecedor TEXT, total_filtros TEXT, numero_caixas_menores TEXT,
        capacidade_caixa_menor TEXT, material TEXT, dimensoes TEXT, espessura TEXT, tipo_acabamento TEXT,
        filtros_quebrados TEXT, quantidade_confere TEXT, procedimento_limpeza TEXT, resultado_inspecao TEXT,
        arquivo_controle TEXT, observacoes TEXT, data_hora_registro TEXT""",
    # lote_fornecedor: o código como foi digitado nas primeiras versões (ex.: DUNE_cx_0001), guardado como histórico
    "lotes_internos": """
        id INT AUTO_INCREMENT PRIMARY KEY, id_lote INT, numero_caixa INT, codigo_interno TEXT,
        quantidade_filtros TEXT, observacoes TEXT, lote_fornecedor TEXT, INDEX (id_lote)""",
    "lotes_limpeza": """
        id INT AUTO_INCREMENT PRIMARY KEY, codigo_interno TEXT, data_limpeza TEXT, responsavel TEXT,
        quantidade_filtros TEXT, origem TEXT, remocao_ptp TEXT, procedimento TEXT, resultado TEXT, observacoes TEXT,
        data_hora_registro TEXT""",
    # ---------------- usuários e auditoria ----------------
    "usuarios": """
        id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(64) NOT NULL UNIQUE, nome TEXT NOT NULL,
        perfil TEXT NOT NULL, senha_hash TEXT NOT NULL, salt TEXT NOT NULL, iteracoes INT NOT NULL,
        ativo INT NOT NULL DEFAULT 1, trocar_senha INT NOT NULL DEFAULT 0, falhas INT NOT NULL DEFAULT 0,
        bloqueado_ate TEXT, criado_em TEXT, ultimo_login TEXT""",
    "auditoria": """
        id INT AUTO_INCREMENT PRIMARY KEY, quando VARCHAR(19) NOT NULL, usuario TEXT, nome TEXT, programa TEXT,
        acao TEXT NOT NULL, detalhe TEXT, INDEX (quando)""",
}


class Linha:
    """Uma linha lida, com o acesso do sqlite3.Row."""
    __slots__ = ("_nomes", "_indice", "_valores")

    def __init__(self, nomes, indice, valores):
        self._nomes, self._indice, self._valores = nomes, indice, valores

    def keys(self):
        return list(self._nomes)

    def __getitem__(self, chave):
        if isinstance(chave, (int, slice)):
            return self._valores[chave]
        return self._valores[self._indice[chave.lower()]]

    def __iter__(self):
        return iter(self._valores)

    def __len__(self):
        return len(self._valores)

    def __repr__(self):
        return "Linha(" + repr(dict(zip(self._nomes, self._valores))) + ")"


def _sql(sql, params):
    """SQL com '?' -> SQL do PyMySQL ('%s'; um '%' do próprio texto vira '%%')."""
    if not params:
        return sql, None
    return sql.replace("%", "%%").replace("?", "%s"), tuple(params)


class Cursor:
    def __init__(self, cur):
        self._cur = cur
        self._nomes, self._indice = (), {}

    def execute(self, sql, params=()):
        self._cur.execute(*_sql(sql, params))
        if self._cur.description:
            self._nomes = tuple(d[0] for d in self._cur.description)
            # nomes repetidos (ex.: SELECT r.*, ...): vale a primeira coluna, como no sqlite3
            self._indice = {n.lower(): i for i, n in reversed(list(enumerate(self._nomes)))}
        return self

    def _linha(self, valores):
        return None if valores is None else Linha(self._nomes, self._indice, valores)

    def fetchone(self):
        return self._linha(self._cur.fetchone())

    def fetchall(self):
        return [self._linha(v) for v in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount


class Conexao:
    def __init__(self):
        self._con = pymysql.connect(**config.BANCO, charset="utf8mb4", autocommit=False, connect_timeout=10)

    def cursor(self):
        return Cursor(self._con.cursor())

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._con.commit()

    def rollback(self):
        self._con.rollback()

    def close(self):
        self._con.close()

    def __enter__(self):
        return self

    def __exit__(self, tipo, *_):
        if tipo is None:
            self.commit()
        else:
            self.rollback()
        return False


def conectar():
    return Conexao()


def criar_tabelas():
    """Cria as tabelas que ainda não existem (ao iniciar o programa)."""
    con = conectar()
    try:
        for nome, colunas in TABELAS.items():
            con.execute(f"CREATE TABLE IF NOT EXISTS {nome} ({colunas}) {_FIM}")
        con.commit()
    finally:
        con.close()
