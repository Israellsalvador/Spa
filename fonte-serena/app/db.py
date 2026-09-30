import os
import sqlite3
from contextlib import contextmanager

from flask import current_app, g

DEFAULT_SETTINGS = {
    # Contato
    "nome_negocio": "Fonte Serena",
    "whatsapp": "",
    "endereco": "",
    "cidade": "Patos de Minas/MG",
    "referencia": "",
    "instagram": "",
    "email_contato": "",
    "email_privacidade": "",
    "cnpj": "",
    "maps_url": "",
    # Pix
    "pix_chave": "",
    "pix_nome": "",
    "pix_cidade": "PATOS DE MINAS",
    # Agenda
    "dias_semana": "0,1,2,3,4",
    "hora_inicio": "08:00",
    "ultimo_inicio": "16:00",
    "intervalo_min": "30",
    "capacidade": "1",
    "antecedencia_horas": "2",
    "janela_dias": "30",
    "bloqueio_min": "15",
    "remarcar_horas": "8",
    "datas_bloqueadas": "",
    # Textos e imagens
    "politicas": "",
    "hero_imagem": "",
    "sobre_imagem": "",
}

SEED_EXPERIENCES = [
    {
        "nome": "Pacote completo",
        "slug": "pacote-completo",
        "categoria": "dayspa",
        "resumo": "Head Spa, escalda-pés, sauna e hidromassagem, combinados em sequência.",
        "descricao": "Uma manhã inteira de pausa, com tudo o que a casa oferece.",
        "inclui": "Head Spa\nEscalda-pés\nSauna\nHidromassagem",
        "destaque": 1,
        "ordem": 1,
    },
    {
        "nome": "Head Spa",
        "slug": "head-spa",
        "categoria": "headspa",
        "resumo": "Cuidado para o couro cabeludo e a cabeça, com água morna e aromas.",
        "descricao": "",
        "inclui": "",
        "destaque": 0,
        "ordem": 2,
    },
]


def get_db():
    if "db" not in g:
        path = os.path.join(current_app.config["DATA_DIR"], "fonte-serena.db")
        conn = sqlite3.connect(path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 15000")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction(db):
    """Transação exclusiva de escrita (evita reservas duplicadas no mesmo horário)."""
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def init_db(app):
    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql") as f:
            db.executescript(f.read().decode("utf-8"))
        for chave, valor in DEFAULT_SETTINGS.items():
            db.execute("INSERT OR IGNORE INTO settings (chave, valor) VALUES (?, ?)", (chave, valor))
        if db.execute("SELECT COUNT(*) FROM experiences").fetchone()[0] == 0:
            for e in SEED_EXPERIENCES:
                db.execute(
                    "INSERT INTO experiences (nome, slug, categoria, resumo, descricao, inclui, destaque, ordem) "
                    "VALUES (:nome, :slug, :categoria, :resumo, :descricao, :inclui, :destaque, :ordem)",
                    e,
                )
        close_db()


def get_settings():
    if "settings" not in g:
        rows = get_db().execute("SELECT chave, valor FROM settings").fetchall()
        s = dict(DEFAULT_SETTINGS)
        s.update({r["chave"]: (r["valor"] or "") for r in rows})
        g.settings = s
    return g.settings


def save_settings(values):
    db = get_db()
    with transaction(db):
        for chave, valor in values.items():
            db.execute(
                "INSERT INTO settings (chave, valor) VALUES (?, ?) "
                "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (chave, valor),
            )
    g.pop("settings", None)
