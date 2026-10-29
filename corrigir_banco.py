import sqlite3

conn = sqlite3.connect("rastreabilidade.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS massa_posicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tarefa INTEGER,
    posicao INTEGER,
    massa_antes REAL,
    massa_depois REAL,
    FOREIGN KEY(id_tarefa) REFERENCES tarefas(id)
)
""")

conn.commit()
conn.close()

print("Tabela massa_posicoes corrigida!")
