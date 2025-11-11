import sqlite3

conn = sqlite3.connect("libreria.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT UNIQUE NOT NULL,
    valor TEXT
);
""")

conn.commit()
conn.close()

print("✅ Tabla 'config' creada correctamente.")
