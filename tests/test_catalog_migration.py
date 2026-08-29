import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_alembic_migrates_then_drops_legacy_products_columns(tmp_path: Path):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, brand VARCHAR(120), category VARCHAR(100) NOT NULL, description TEXT, price_clp INTEGER NOT NULL, rating NUMERIC, created_at DATETIME);
        INSERT INTO products (id, name, brand, category, price_clp) VALUES (1, 'Producto heredado', 'Marca', 'Notebooks', 100000);
    """)
    connection.commit()
    connection.close()

    environment = {**os.environ, "DATABASE_URL": f"sqlite:///{database}"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=Path(__file__).parents[1], env=environment, check=True, capture_output=True, text=True)

    connection = sqlite3.connect(database)
    columns = [row[0] for row in connection.execute("PRAGMA table_info(products)").fetchall()]
    assert "category" not in columns, "legacy category column should be dropped"
    assert "price_clp" not in columns, "legacy price_clp column should be dropped"
    assert connection.execute("SELECT category_id FROM products WHERE id = 1").fetchone() == (1,)
    assert connection.execute("SELECT price FROM store_offers").fetchone()[0] == 100000
    assert connection.execute("SELECT price FROM price_history").fetchone()[0] == 100000
    connection.close()
