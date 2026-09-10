"""
Crea planta.db con catálogos de ejemplo.

En producción las órdenes vienen de SQL Server, alimentadas por el pipeline
que integra el ERP, y los eventos y operarios de maestras mantenidas por
calidad. Aquí se generan localmente para que la aplicación se pueda ejecutar
sin depender de nada externo.

Uso:
    python datos_demo.py
"""

import random
import sqlite3
from pathlib import Path

RUTA_DB = Path("planta.db")
SEMILLA = 7

CLIENTES = ["ALFA", "BETA", "GAMMA", "DELTA", "OMEGA"]
PRODUCTOS = ["CAJA PLEGADIZA", "ESTUCHE", "MICROCORRUGADO", "DISPLAY", "BANDEJA"]

EVENTOS = [
    ("10", "TIRAJE"),
    ("11", "TIRAJE PRUEBA"),
    ("20", "GRADUACION"),
    ("21", "CAMBIO DE REFERENCIA"),
    ("30", "PARO MANTENIMIENTO"),
    ("31", "PARO FALTA MATERIAL"),
    ("32", "PARO CALIDAD"),
    ("40", "LIMPIEZA"),
    ("50", "REUNION"),
]

OPERARIOS = [
    ("1001", "CARLOS RAMIREZ"),
    ("1002", "MARIA GONZALEZ"),
    ("1003", "JORGE MARTINEZ"),
    ("1004", "ANA TORRES"),
    ("1005", "LUIS HERRERA"),
    ("1006", "SANDRA VELEZ"),
]


def main() -> None:
    if RUTA_DB.exists():
        RUTA_DB.unlink()

    rnd = random.Random(SEMILLA)
    con = sqlite3.connect(RUTA_DB)
    try:
        con.executescript(
            """
            CREATE TABLE ordenes (
                op             TEXT PRIMARY KEY,
                cod_referencia TEXT,
                referencia     TEXT,
                activa         INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE eventos (
                codigo TEXT PRIMARY KEY,
                nombre TEXT NOT NULL
            );
            CREATE TABLE operarios (
                id     TEXT PRIMARY KEY,
                nombre TEXT NOT NULL
            );
            CREATE TABLE registros (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha            TEXT NOT NULL,
                hora             TEXT NOT NULL,
                maquina          TEXT NOT NULL,
                op               TEXT NOT NULL,
                cod_referencia   TEXT,
                referencia       TEXT,
                cod_evento       TEXT,
                evento           TEXT,
                cantidad         INTEGER NOT NULL,
                lectura_contador INTEGER,
                operario_id      TEXT,
                operario         TEXT,
                observaciones    TEXT
            );
            CREATE INDEX idx_reg_busqueda ON registros(op, maquina, fecha);
            """
        )

        ordenes = []
        for i in range(1, 41):
            cliente = rnd.choice(CLIENTES)
            ordenes.append(
                (
                    f"OP-{2600 + i}",
                    f"{cliente[:3]}-{rnd.randint(100, 999)}",
                    f"{rnd.choice(PRODUCTOS)} {cliente}",
                    1 if rnd.random() > 0.15 else 0,
                )
            )

        con.executemany("INSERT INTO ordenes VALUES (?,?,?,?)", ordenes)
        con.executemany("INSERT INTO eventos VALUES (?,?)", EVENTOS)
        con.executemany("INSERT INTO operarios VALUES (?,?)", OPERARIOS)
        con.commit()

        activas = sum(1 for o in ordenes if o[3])
        print(f"Ordenes:   {len(ordenes)} ({activas} activas)")
        print(f"Eventos:   {len(EVENTOS)}")
        print(f"Operarios: {len(OPERARIOS)}")
        print(f"\nBase creada en {RUTA_DB.resolve()}")
        print("Ahora ejecuta: python app.py")
    finally:
        con.close()


if __name__ == "__main__":
    main()
