import sqlite3
from werkzeug.security import generate_password_hash

# database
conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# username na password mpya
new_username = "ben"   # unaweza kubadilisha kuwa BEN
new_password = "2050"    # unaweza kubadilisha kwa unavyotaka

# tengeneza hashed password
hashed_password = generate_password_hash(new_password)

# update admin mwenye id=1
cursor.execute("UPDATE admin SET username=?, password=? WHERE id=1", (new_username, hashed_password))

conn.commit()
conn.close()

print("✅ Admin credentials updated successfully!")
