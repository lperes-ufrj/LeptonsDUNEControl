import sqlite3

DB = "lotes.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
UPDATE lotes
SET tracking_id = 'DUNE-HD'
WHERE id = 1
""")

conn.commit()

cur.execute("SELECT id, tracking_id, lote_geral FROM lotes")
for row in cur.fetchall():
    print(row)

conn.close()
