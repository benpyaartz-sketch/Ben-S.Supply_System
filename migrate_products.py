import sqlite3

# Fungua connection
conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Rename table ya zamani
cursor.execute("ALTER TABLE products RENAME TO old_products;")

# Unda table mpya (image columns nullable)
cursor.execute("""
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    image1 TEXT,
    image2 TEXT,
    image3 TEXT,
    image4 TEXT,
    image5 TEXT
);
""")

# Hamisha data kutoka table ya zamani
cursor.execute("""
INSERT INTO products (id, name, price, image1, image2, image3, image4, image5)
SELECT id, name, price, image_filename, image2, image3, image4, image5
FROM old_products;
""")

# Futa table ya zamani
cursor.execute("DROP TABLE old_products;")

conn.commit()
conn.close()

print("✅ Table products imesasishwa na picha zinaweza kuwa optional sasa.")
