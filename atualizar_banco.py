import sqlite3

conn = sqlite3.connect("rastreabilidade.db")
cursor = conn.cursor()

# adiciona campos se não existirem
try:
    cursor.execute("ALTER TABLE tarefas ADD COLUMN position_range TEXT")
except:
    pass

try:
    cursor.execute("ALTER TABLE tarefas ADD COLUMN observacoes TEXT")
except:
    pass

conn.commit()
conn.close()

print("Banco atualizado com novos campos!")
