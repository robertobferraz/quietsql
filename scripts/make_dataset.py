import argparse
from pathlib import Path

import duckdb

CITIES = [
    ("Recife", "PE"),
    ("Olinda", "PE"),
    ("Caruaru", "PE"),
    ("São Paulo", "SP"),
    ("Campinas", "SP"),
    ("Rio de Janeiro", "RJ"),
    ("Niterói", "RJ"),
    ("Belo Horizonte", "MG"),
    ("Curitiba", "PR"),
    ("Porto Alegre", "RS"),
    ("Salvador", "BA"),
    ("Fortaleza", "CE"),
]
CATEGORIES = ["beverages", "snacks", "cleaning", "hygiene", "bakery", "dairy"]
PRODUCTS = 200
SOLD_PRODUCTS = 180


def build(rows: int, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    con = duckdb.connect(str(out))
    con.execute("CREATE TABLE cities(idx INTEGER, city VARCHAR, state VARCHAR)")
    con.executemany(
        "INSERT INTO cities VALUES (?, ?, ?)", [(i, c, s) for i, (c, s) in enumerate(CITIES)]
    )
    con.execute("CREATE TABLE categories(idx INTEGER, name VARCHAR)")
    con.executemany("INSERT INTO categories VALUES (?, ?)", list(enumerate(CATEGORIES)))
    customers = max(100, rows // 50)
    con.execute(
        f"""
        CREATE TABLE customers AS
        SELECT i AS id,
               printf('Customer %06d', i) AS name,
               c.city, c.state,
               printf('customer%06d@example.com', i) AS email,
               DATE '2024-01-01' + (hash(i) % 700)::INTEGER AS created_at
        FROM range({customers}) t(i)
        JOIN cities c ON c.idx = (hash(i * 7) % {len(CITIES)})::INTEGER
        """
    )
    con.execute(
        f"""
        CREATE TABLE products AS
        SELECT i AS id,
               printf('Product %03d', i) AS name,
               cat.name AS category,
               round(1 + (hash(i * 3) % 20000) / 100.0, 2) AS unit_price
        FROM range({PRODUCTS}) t(i)
        JOIN categories cat ON cat.idx = (hash(i * 11) % {len(CATEGORIES)})::INTEGER
        """
    )
    con.execute(
        f"""
        CREATE TABLE sales AS
        WITH raw AS (
            SELECT i AS id,
                   (hash(i * 13) % {customers})::INTEGER AS customer_id,
                   (hash(i * 17) % {SOLD_PRODUCTS})::INTEGER AS product_id,
                   DATE '2026-01-01' + (hash(i * 19) % 270)::INTEGER AS sold_at,
                   1 + (hash(i * 23) % 5)::INTEGER AS quantity,
                   CASE (hash(i * 29) % 10)
                       WHEN 0 THEN 'cancelled'
                       WHEN 1 THEN 'open'
                       ELSE 'paid'
                   END AS status
            FROM range({rows}) t(i)
        )
        SELECT r.id,
               r.customer_id,
               r.product_id,
               r.sold_at,
               r.quantity,
               round(r.quantity * p.unit_price, 2) AS amount,
               r.status
        FROM raw r
        JOIN products p ON p.id = r.product_id
        """
    )
    con.execute("DROP TABLE cities; DROP TABLE categories")
    con.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--out", type=Path, default=Path("data/demo.duckdb"))
    args = parser.parse_args()
    build(args.rows, args.out)
    print(f"wrote {args.out} with {args.rows} sales rows")


if __name__ == "__main__":
    main()
