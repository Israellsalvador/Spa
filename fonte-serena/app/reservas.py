import secrets
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from . import current_user, login_required
from .agenda import (config_agenda, dias_disponiveis, expirar_bloqueios, horario_livre,
                     horarios_do_dia, pode_remarcar)
from .db import get_db, get_settings, transaction
from .pix import copia_e_cola, qr_svg
from .util import agora, experiencia_reservavel, fmt_dt, parse_dt, sinal_de

bp = Blueprint("reservas", __name__)


def pix_configurado(s):
    return bool((s.get("pix_chave") or "").strip() and (s.get("pix_nome") or "").strip())


def _parse_dia(txt):
    try:
        return date.fromisoformat(txt)
    except (TypeError, ValueError):
        return None


def _minha_reserva(codigo):
    b = get_db().execute(
        "SELECT b.*, e.nome AS exp_nome, e.slug AS exp_slug, e.duracao_min AS exp_duracao "
        "FROM bookings b JOIN experiences e ON e.id = b.experience_id WHERE b.codigo = ?",
        (codigo,),
    ).fetchone()
    u = current_user()
    if b is None or (b["user_id"] != u["id"] and not u["is_admin"]):
        abort(404)
    return b


@bp.route("/agendar")
def agendar():
    s = get_settings()
    exps = get_db().execute(
        "SELECT * FROM experiences WHERE ativo = 1 ORDER BY destaque DESC, ordem, nome").fetchall()
    reservaveis = [e for e in exps if experiencia_reservavel(e)]
    a_confirmar = [e for e in exps if not experiencia_reservavel(e)]
    if request.args.get("exp"):
        return redirect(url_for("reservas.horario", slug=request.args["exp"]))
    return render_template("agendar.html", reservaveis=reservaveis if pix_configurado(s) else [],
                           a_confirmar=a_confirmar, pix_ok=pix_configurado(s))


@bp.route("/agendar/<slug>")
def horario(slug):
    s = get_settings()
    db = get_db()
    e = db.execute("SELECT * FROM experiences WHERE slug = ? AND ativo = 1", (slug,)).fetchone()
    if e is None:
        abort(404)
    if not experiencia_reservavel(e) or not pix_configurado(s):
        return redirect(url_for("reservas.agendar"))
    expirar_bloqueios(db)
    cfg = config_agenda(s)
    dias = dias_disponiveis(db, cfg, e["duracao_min"])
    dia = _parse_dia(request.args.get("data"))
    if dia not in dias:
        dia = dias[0] if dias else None
    horarios = horarios_do_dia(db, cfg, dia, e["duracao_min"]) if dia else []
    hora = request.args.get("hora")
    escolhido = next((h for h in horarios if h.strftime("%H:%M") == hora), None)
    return render_template("horario.html", e=e, dias=dias, dia=dia, horarios=horarios,
                           escolhido=escolhido, cfg=cfg, sinal=sinal_de(e["preco_centavos"]))


@bp.route("/agendar/<slug>/reservar", methods=["POST"])
@login_required
def reservar(slug):
    s = get_settings()
    db = get_db()
    e = db.execute("SELECT * FROM experiences WHERE slug = ? AND ativo = 1", (slug,)).fetchone()
    if e is None or not experiencia_reservavel(e) or not pix_configurado(s):
        abort(404)
    cfg = config_agenda(s)
    try:
        inicio = datetime.strptime(f"{request.form['data']} {request.form['hora']}", "%Y-%m-%d %H:%M")
    except (KeyError, ValueError):
        abort(400)

    validos = horarios_do_dia(db, cfg, inicio.date(), e["duracao_min"])
    if inicio not in validos:
        flash("Esse horário acabou de ser reservado. Escolha outro, por favor.", "erro")
        return redirect(url_for("reservas.horario", slug=slug, data=inicio.date().isoformat()))

    codigo = "FS" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    agora_ = agora()
    with transaction(db):
        if not horario_livre(db, cfg, inicio, e["duracao_min"]):
            db_ok = False
        else:
            db_ok = True
            db.execute(
                "INSERT INTO bookings (codigo, user_id, experience_id, inicio, fim, status, preco_centavos, "
                "sinal_centavos, hold_ate, observacoes, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (codigo, current_user()["id"], e["id"], fmt_dt(inicio),
                 fmt_dt(inicio + timedelta(minutes=e["duracao_min"])), "aguardando_pagamento",
                 e["preco_centavos"], sinal_de(e["preco_centavos"]),
                 fmt_dt(agora_ + timedelta(minutes=cfg["bloqueio"])),
                 session.get("quiz_resumo") or None, fmt_dt(agora_)),
            )
    if not db_ok:
        flash("Esse horário acabou de ser reservado. Escolha outro, por favor.", "erro")
        return redirect(url_for("reservas.horario", slug=slug, data=inicio.date().isoformat()))
    return redirect(url_for("reservas.pagamento", codigo=codigo))


@bp.route("/reserva/<codigo>")
@login_required
def pagamento(codigo):
    db = get_db()
    expirar_bloqueios(db)
    b = _minha_reserva(codigo)
    s = get_settings()
    payload = qr = None
    if b["status"] == "aguardando_pagamento" and pix_configurado(s):
        payload = copia_e_cola(s["pix_chave"], s["pix_nome"], s["pix_cidade"], b["sinal_centavos"], b["codigo"])
        qr = qr_svg(payload)
    cfg = config_agenda(s)
    return render_template("reserva.html", b=b, payload=payload, qr=qr,
                           pode_remarcar=pode_remarcar(b, cfg), cfg=cfg)


@bp.route("/reserva/<codigo>/paguei", methods=["POST"])
@login_required
def paguei(codigo):
    db = get_db()
    expirar_bloqueios(db)
    b = _minha_reserva(codigo)
    if b["status"] == "aguardando_pagamento":
        db.execute("UPDATE bookings SET status = 'pagamento_informado', pagamento_informado_em = ? "
                   "WHERE id = ?", (fmt_dt(agora()), b["id"]))
        flash("Recebemos seu aviso. Assim que o Pix for conferido, sua reserva é confirmada.", "ok")
    elif b["status"] == "expirada":
        flash("O tempo para pagar este sinal acabou. Se você já pagou, fale com a gente pelo WhatsApp.", "erro")
    return redirect(url_for("reservas.pagamento", codigo=codigo))


@bp.route("/reserva/<codigo>/cancelar", methods=["POST"])
@login_required
def cancelar(codigo):
    db = get_db()
    b = _minha_reserva(codigo)
    if b["status"] == "aguardando_pagamento":
        db.execute("UPDATE bookings SET status = 'cancelada', cancelado_em = ? WHERE id = ?",
                   (fmt_dt(agora()), b["id"]))
        flash("Reserva cancelada. O horário foi liberado.", "ok")
    else:
        flash("Para cancelar uma reserva com sinal pago, fale com a gente pelo WhatsApp.", "info")
    return redirect(url_for("conta.meus_agendamentos"))


@bp.route("/reserva/<codigo>/remarcar", methods=["GET", "POST"])
@login_required
def remarcar(codigo):
    s = get_settings()
    db = get_db()
    expirar_bloqueios(db)
    b = _minha_reserva(codigo)
    cfg = config_agenda(s)
    if not pode_remarcar(b, cfg):
        flash(f"Remarcações pelo site podem ser feitas até {cfg['remarcar']} horas antes. "
              "Fale com a gente pelo WhatsApp.", "info")
        return redirect(url_for("conta.meus_agendamentos"))
    dur = int((parse_dt(b["fim"]) - parse_dt(b["inicio"])).total_seconds() // 60)

    if request.method == "POST":
        try:
            inicio = datetime.strptime(f"{request.form['data']} {request.form['hora']}", "%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            abort(400)
        ok = False
        if inicio in horarios_do_dia(db, cfg, inicio.date(), dur, excluir_id=b["id"]):
            with transaction(db):
                if horario_livre(db, cfg, inicio, dur, excluir_id=b["id"]):
                    db.execute("UPDATE bookings SET inicio = ?, fim = ?, remarcacoes = remarcacoes + 1 "
                               "WHERE id = ?", (fmt_dt(inicio), fmt_dt(inicio + timedelta(minutes=dur)), b["id"]))
                    ok = True
        if ok:
            flash("Pronto! Sua reserva foi remarcada.", "ok")
            return redirect(url_for("conta.meus_agendamentos"))
        flash("Esse horário não está mais disponível. Escolha outro.", "erro")

    dias = dias_disponiveis(db, cfg, dur, excluir_id=b["id"])
    dia = _parse_dia(request.args.get("data"))
    if dia not in dias:
        dia = dias[0] if dias else None
    horarios = horarios_do_dia(db, cfg, dia, dur, excluir_id=b["id"]) if dia else []
    hora = request.args.get("hora")
    escolhido = next((h for h in horarios if h.strftime("%H:%M") == hora), None)
    return render_template("remarcar.html", b=b, dias=dias, dia=dia, horarios=horarios, escolhido=escolhido)
