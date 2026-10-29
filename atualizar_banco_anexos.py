import sqlite3

conn = sqlite3.connect("rastreabilidade.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE tarefas ADD COLUMN anexos TEXT")
except:
    pass

conn.commit()
conn.close()

print("Campo de anexos criado!")
