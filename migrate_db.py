import sqlite3

DB_NAME = "database.db"

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

# Ongeza columns kama hazipo
columns = ["image2", "image3", "image4", "image5"]
for col in columns:
    try:
        c.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT;")
        print(f"✅ Column {col} added.")
    except sqlite3.OperationalError:
        print(f"⚠️ Column {col} tayari ipo.")

conn.commit()
conn.close()

print("✅ Migration complete!")
