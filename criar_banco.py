import sqlite3

conn = sqlite3.connect("rastreabilidade.db")
cursor = conn.cursor()

# Tabela de Lotes de Entrada
cursor.execute("""
CREATE TABLE IF NOT EXISTS lotes_entrada (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_lote TEXT,
    material TEXT,
    fornecedor TEXT,
    data_recebimento TEXT,
    quantidade INTEGER,
    observacoes TEXT
)
""")

# Tabela de Tarefas
cursor.execute("""
CREATE TABLE IF NOT EXISTS tarefas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_tarefa TEXT,
    lote_entrada_id INTEGER,
    descricao TEXT,
    responsavel TEXT,
    data_inicio TEXT,
    data_fim TEXT,
    status TEXT,
    FOREIGN KEY(lote_entrada_id) REFERENCES lotes_entrada(id)
)
""")

# Caixas (nível 2)
cursor.execute("""
CREATE TABLE IF NOT EXISTS caixas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_caixa TEXT,
    data_criacao TEXT,
    destino TEXT,
    observacoes TEXT
)
""")

# Relação tarefas ↔ caixas
cursor.execute("""
CREATE TABLE IF NOT EXISTS caixa_tarefas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caixa_id INTEGER,
    tarefa_id INTEGER,
    FOREIGN KEY(caixa_id) REFERENCES caixas(id),
    FOREIGN KEY(tarefa_id) REFERENCES tarefas(id)
)
""")

# Envios (nível 3)
cursor.execute("""
CREATE TABLE IF NOT EXISTS envios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_envio TEXT,
    destino TEXT,
    responsavel TEXT,
    data_envio TEXT,
    observacoes TEXT
)
""")

# Relação caixas ↔ envios
cursor.execute("""
CREATE TABLE IF NOT EXISTS envio_caixas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    envio_id INTEGER,
    caixa_id INTEGER,
    FOREIGN KEY(envio_id) REFERENCES envios(id),
    FOREIGN KEY(caixa_id) REFERENCES caixas(id)
)
""")

conn.commit()
conn.close()

print("Banco criado com sucesso!")
