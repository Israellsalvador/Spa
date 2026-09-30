import re

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import current_user, login_required, next_seguro
from .agenda import config_agenda, expirar_bloqueios, pode_remarcar
from .db import get_db, get_settings
from .util import agora, fmt_dt

bp = Blueprint("conta", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _logar(user):
    session.clear()
    session.permanent = True
    session["uid"] = user["id"]


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    nxt = next_seguro(request.values.get("next"), url_for("conta.meus_agendamentos"))
    if current_user():
        return redirect(nxt)
    aba = request.values.get("aba", "entrar")
    form = {}
    if request.method == "POST":
        db = get_db()
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        form = {"email": email}
        if aba == "cadastro":
            nome = (request.form.get("nome") or "").strip()
            telefone = (request.form.get("telefone") or "").strip()
            form.update(nome=nome, telefone=telefone)
            erro = None
            if len(nome) < 2:
                erro = "Informe seu nome."
            elif not EMAIL_RE.match(email):
                erro = "Informe um e-mail válido."
            elif len(senha) < 8:
                erro = "A senha precisa ter pelo menos 8 caracteres."
            elif db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                erro = "Já existe uma conta com este e-mail. Entre com sua senha."
            if erro:
                flash(erro, "erro")
            else:
                cur = db.execute(
                    "INSERT INTO users (nome, email, telefone, senha_hash, criado_em) VALUES (?, ?, ?, ?, ?)",
                    (nome, email, telefone, generate_password_hash(senha), fmt_dt(agora())),
                )
                user = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
                _logar(user)
                flash(f"Conta criada. Boas-vindas, {nome.split()[0]}!", "ok")
                return redirect(nxt)
        else:
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and check_password_hash(user["senha_hash"], senha):
                _logar(user)
                if user["is_admin"] and nxt == url_for("conta.meus_agendamentos"):
                    nxt = url_for("admin.painel")
                return redirect(nxt)
            flash("E-mail ou senha incorretos.", "erro")
    return render_template("entrar.html", aba=aba, nxt=nxt, form=form)


@bp.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("public.home"))


@bp.route("/esqueci-senha")
def esqueci():
    return render_template("esqueci.html")


@bp.route("/meus-agendamentos")
@login_required
def meus_agendamentos():
    db = get_db()
    expirar_bloqueios(db)
    aba = request.args.get("aba", "proximos")
    rows = db.execute(
        "SELECT b.*, e.nome AS exp_nome, e.slug AS exp_slug FROM bookings b "
        "JOIN experiences e ON e.id = b.experience_id WHERE b.user_id = ? ORDER BY b.inicio",
        (current_user()["id"],),
    ).fetchall()
    agora_txt = fmt_dt(agora())
    ativos = ("aguardando_pagamento", "pagamento_informado", "confirmada")
    proximos = [r for r in rows if r["status"] in ativos and r["fim"] >= agora_txt]
    anteriores = [r for r in rows if r not in proximos][::-1]
    cfg = config_agenda(get_settings())
    return render_template("meus_agendamentos.html", aba=aba, proximos=proximos, anteriores=anteriores,
                           pode_remarcar=lambda b: pode_remarcar(b, cfg), cfg=cfg)
