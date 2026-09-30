import os
import secrets
from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from . import admin_required, next_seguro
from .agenda import config_agenda, expirar_bloqueios
from .db import get_db, get_settings, save_settings
from .reservas import pix_configurado
from .util import CATEGORIAS, agora, fmt_dt, slugify

bp = Blueprint("admin", __name__, url_prefix="/admin")

ASSINATURAS = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp",
}


def _salvar_imagem(arquivo):
    """Salva uma imagem enviada (JPG, PNG ou WEBP) e devolve o nome do arquivo."""
    if not arquivo or not arquivo.filename:
        return None
    cabeca = arquivo.stream.read(12)
    arquivo.stream.seek(0)
    ext = None
    for assinatura, e in ASSINATURAS.items():
        if cabeca.startswith(assinatura):
            if e == ".webp" and cabeca[8:12] != b"WEBP":
                continue
            ext = e
    if ext is None:
        flash("Envie a imagem em JPG, PNG ou WEBP.", "erro")
        return None
    nome = secrets.token_hex(10) + ext
    arquivo.save(os.path.join(current_app.config["UPLOAD_DIR"], nome))
    return nome


def _pendencias(s, db):
    p = []
    if not pix_configurado(s):
        p.append(("Cadastrar a chave Pix e o nome do recebedor", url_for("admin.configuracoes")))
    if not s.get("whatsapp"):
        p.append(("Cadastrar o WhatsApp de atendimento", url_for("admin.configuracoes")))
    if not s.get("endereco"):
        p.append(("Cadastrar o endereço", url_for("admin.configuracoes")))
    if not s.get("politicas"):
        p.append(("Publicar as políticas de cancelamento e reembolso", url_for("admin.configuracoes")))
    sem_preco = db.execute("SELECT COUNT(*) FROM experiences WHERE ativo = 1 AND "
                           "(duracao_min IS NULL OR preco_centavos IS NULL)").fetchone()[0]
    if sem_preco:
        p.append((f"Definir duração e preço de {sem_preco} experiência(s)", url_for("admin.experiencias")))
    return p


def _reservas(where, args):
    return get_db().execute(
        "SELECT b.*, e.nome AS exp_nome, u.nome AS cliente, u.email, u.telefone FROM bookings b "
        "JOIN experiences e ON e.id = b.experience_id JOIN users u ON u.id = b.user_id "
        "WHERE " + where + " ORDER BY b.inicio", args).fetchall()


@bp.route("/")
@admin_required
def painel():
    db = get_db()
    expirar_bloqueios(db)
    s = get_settings()
    agora_txt = fmt_dt(agora())
    conferir = _reservas("b.status IN ('pagamento_informado','aguardando_pagamento') AND b.fim >= ?", (agora_txt,))
    proximas = _reservas("b.status = 'confirmada' AND b.fim >= ? AND b.inicio <= ?",
                         (agora_txt, fmt_dt(agora() + timedelta(days=14))))
    return render_template("admin/painel.html", conferir=conferir, proximas=proximas,
                           pendencias=_pendencias(s, db))


@bp.route("/agenda")
@admin_required
def agenda():
    try:
        dia = date.fromisoformat(request.args.get("data", ""))
    except ValueError:
        dia = agora().date()
    rows = _reservas("b.inicio >= ? AND b.inicio < ?",
                     (f"{dia.isoformat()} 00:00", f"{(dia + timedelta(days=1)).isoformat()} 00:00"))
    return render_template("admin/agenda.html", dia=dia, rows=rows,
                           anterior=dia - timedelta(days=1), proximo=dia + timedelta(days=1))


@bp.route("/reserva/<int:bid>/<acao>", methods=["POST"])
@admin_required
def reserva_acao(bid, acao):
    db = get_db()
    b = db.execute("SELECT * FROM bookings WHERE id = ?", (bid,)).fetchone()
    if b is None:
        abort(404)
    agora_txt = fmt_dt(agora())
    if acao == "confirmar" and b["status"] in ("aguardando_pagamento", "pagamento_informado", "expirada"):
        db.execute("UPDATE bookings SET status = 'confirmada', confirmado_em = ?, hold_ate = NULL WHERE id = ?",
                   (agora_txt, bid))
        flash(f"Reserva {b['codigo']} confirmada.", "ok")
    elif acao in ("recusar", "cancelar") and b["status"] in ("aguardando_pagamento", "pagamento_informado", "confirmada"):
        db.execute("UPDATE bookings SET status = 'cancelada', cancelado_em = ? WHERE id = ?", (agora_txt, bid))
        flash(f"Reserva {b['codigo']} cancelada e horário liberado.", "ok")
    return redirect(next_seguro(request.form.get("voltar"), url_for("admin.painel")))


# ---------- experiências ----------

@bp.route("/experiencias")
@admin_required
def experiencias():
    exps = get_db().execute("SELECT * FROM experiences ORDER BY ativo DESC, ordem, nome").fetchall()
    return render_template("admin/experiencias.html", exps=exps)


@bp.route("/experiencias/nova", methods=["GET", "POST"])
@bp.route("/experiencias/<int:eid>", methods=["GET", "POST"])
@admin_required
def experiencia(eid=None):
    db = get_db()
    e = None
    if eid:
        e = db.execute("SELECT * FROM experiences WHERE id = ?", (eid,)).fetchone()
        if e is None:
            abort(404)
    if request.method == "POST":
        f = request.form
        nome = (f.get("nome") or "").strip()
        categoria = f.get("categoria")
        erro = None
        dur = preco = None
        try:
            dur = int(f["duracao_min"]) if f.get("duracao_min", "").strip() else None
            if dur is not None and not 10 <= dur <= 600:
                erro = "A duração deve ficar entre 10 e 600 minutos."
        except ValueError:
            erro = "Duração inválida."
        try:
            p = (f.get("preco") or "").strip().replace("R$", "").replace(" ", "")
            if p:
                p = p.replace(".", "").replace(",", ".") if "," in p else p
                preco = round(float(p) * 100)
                if preco <= 0:
                    erro = "O preço precisa ser maior que zero."
        except ValueError:
            erro = "Preço inválido. Use o formato 180,00."
        if not nome:
            erro = "Informe o nome."
        if categoria not in CATEGORIAS:
            erro = "Escolha uma categoria."
        if erro:
            flash(erro, "erro")
        else:
            imagem = _salvar_imagem(request.files.get("imagem"))
            if f.get("remover_imagem"):
                imagem = ""
            dados = {
                "nome": nome, "categoria": categoria,
                "resumo": (f.get("resumo") or "").strip(),
                "descricao": (f.get("descricao") or "").strip(),
                "inclui": (f.get("inclui") or "").strip(),
                "duracao_min": dur, "preco_centavos": preco,
                "ativo": 1 if f.get("ativo") else 0,
                "destaque": 1 if f.get("destaque") else 0,
                "ordem": int(f.get("ordem") or 0) if (f.get("ordem") or "0").lstrip("-").isdigit() else 0,
            }
            if e is None:
                slug = base = slugify(nome)
                n = 2
                while db.execute("SELECT 1 FROM experiences WHERE slug = ?", (slug,)).fetchone():
                    slug = f"{base}-{n}"
                    n += 1
                dados.update(slug=slug, imagem=imagem or None)
                cur = db.execute("INSERT INTO experiences (nome, slug, categoria, resumo, descricao, inclui, duracao_min, "
                           "preco_centavos, ativo, destaque, ordem, imagem) VALUES (:nome, :slug, :categoria, "
                           ":resumo, :descricao, :inclui, :duracao_min, :preco_centavos, :ativo, :destaque, "
                           ":ordem, :imagem)", dados)
                salvo_id = cur.lastrowid
            else:
                salvo_id = e["id"]
                dados["id"] = e["id"]
                dados["imagem"] = e["imagem"] if imagem is None else (imagem or None)
                db.execute("UPDATE experiences SET nome=:nome, categoria=:categoria, resumo=:resumo, "
                           "descricao=:descricao, inclui=:inclui, duracao_min=:duracao_min, "
                           "preco_centavos=:preco_centavos, ativo=:ativo, destaque=:destaque, ordem=:ordem, "
                           "imagem=:imagem WHERE id=:id", dados)
            if dados["destaque"]:
                db.execute("UPDATE experiences SET destaque = 0 WHERE id != ?", (salvo_id,))
            flash("Experiência salva.", "ok")
            return redirect(url_for("admin.experiencias"))
    return render_template("admin/experiencia_form.html", e=e)


# ---------- configurações ----------

CAMPOS_TEXTO = ["whatsapp", "endereco", "cidade", "referencia", "instagram", "email_contato",
                "email_privacidade", "cnpj", "maps_url", "pix_chave", "pix_nome", "pix_cidade",
                "hora_inicio", "ultimo_inicio", "intervalo_min", "capacidade", "antecedencia_horas",
                "janela_dias", "bloqueio_min", "remarcar_horas", "datas_bloqueadas", "politicas"]


@bp.route("/configuracoes", methods=["GET", "POST"])
@admin_required
def configuracoes():
    if request.method == "POST":
        valores = {c: (request.form.get(c) or "").strip() for c in CAMPOS_TEXTO}
        valores["dias_semana"] = ",".join(sorted(request.form.getlist("dias_semana")))
        for campo in ("hero_imagem", "sobre_imagem"):
            nome = _salvar_imagem(request.files.get(campo))
            if nome:
                valores[campo] = nome
            elif request.form.get("remover_" + campo):
                valores[campo] = ""
        save_settings(valores)
        flash("Configurações salvas.", "ok")
        return redirect(url_for("admin.configuracoes"))
    return render_template("admin/configuracoes.html", cfg=config_agenda(get_settings()))


# ---------- clientes ----------

@bp.route("/clientes")
@admin_required
def clientes():
    rows = get_db().execute(
        "SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id) AS reservas "
        "FROM users u ORDER BY u.criado_em DESC").fetchall()
    return render_template("admin/clientes.html", rows=rows)


@bp.route("/clientes/<int:uid>/senha", methods=["POST"])
@admin_required
def nova_senha(uid):
    senha = secrets.token_urlsafe(6)
    get_db().execute("UPDATE users SET senha_hash = ? WHERE id = ?", (generate_password_hash(senha), uid))
    flash(f"Nova senha temporária: {senha} — envie para a cliente e peça para ela guardar.", "ok")
    return redirect(url_for("admin.clientes"))
