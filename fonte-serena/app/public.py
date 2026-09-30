from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from .db import get_db
from .quiz import PERGUNTAS, POR_CHAVE, recomendar, resumo_preferencias
from .util import CATEGORIAS, experiencia_reservavel

bp = Blueprint("public", __name__)


def _experiencias(categoria=None):
    sql = "SELECT * FROM experiences WHERE ativo = 1"
    args = []
    if categoria:
        sql += " AND categoria = ?"
        args.append(categoria)
    sql += " ORDER BY destaque DESC, ordem, nome"
    rows = get_db().execute(sql, args).fetchall()
    # quem já pode ser reservado online aparece antes do que ainda está "sob consulta"
    return sorted(rows, key=lambda e: 0 if experiencia_reservavel(e) or e["destaque"] else 1)


@bp.app_template_global()
def reservavel(exp):
    return experiencia_reservavel(exp)


@bp.route("/")
def home():
    exps = _experiencias()
    destaque = next((e for e in exps if e["destaque"]), exps[0] if exps else None)
    outras = [e for e in exps if destaque is None or e["id"] != destaque["id"]]
    return render_template("home.html", destaque=destaque, outras=outras,
                           sentimentos=POR_CHAVE["sentimento"]["opcoes"])


@bp.route("/experiencias")
def experiencias():
    cat = request.args.get("categoria")
    if cat not in CATEGORIAS:
        cat = None
    so_online = request.args.get("online") == "1"
    exps = _experiencias(cat)
    if so_online:
        exps = [e for e in exps if experiencia_reservavel(e)]
    return render_template("experiencias.html", exps=exps, cat=cat, so_online=so_online)


@bp.route("/experiencias/<slug>")
def experiencia(slug):
    e = get_db().execute("SELECT * FROM experiences WHERE slug = ? AND ativo = 1", (slug,)).fetchone()
    if e is None:
        abort(404)
    return render_template("experiencia.html", e=e)


@bp.route("/descubra", methods=["GET", "POST"])
def descubra():
    respostas = session.get("quiz", {})
    if request.method == "GET" and request.args.get("recomecar"):
        session.pop("quiz", None)
        return redirect(url_for("public.descubra"))

    # Atalho da home: /descubra?sentimento=tensao
    pre = request.args.get("sentimento")
    if pre and any(v == pre for v, _, _ in POR_CHAVE["sentimento"]["opcoes"]):
        respostas = {"sentimento": [pre]}
        session["quiz"] = respostas

    try:
        passo = int(request.values.get("passo", 1))
    except ValueError:
        passo = 1
    passo = min(max(passo, 1), len(PERGUNTAS))
    pergunta = PERGUNTAS[passo - 1]

    if request.method == "POST":
        acao = request.form.get("acao", "continuar")
        validos = {v for v, _, _ in pergunta["opcoes"]}
        escolhidas = [v for v in request.form.getlist("r") if v in validos][: pergunta["multipla"]]
        if acao == "pular":
            escolhidas = []
        if acao != "voltar":
            respostas = dict(respostas)
            respostas[pergunta["chave"]] = escolhidas
            session["quiz"] = respostas
        if acao == "voltar":
            return redirect(url_for("public.descubra", passo=max(1, passo - 1)))
        if passo >= len(PERGUNTAS):
            return redirect(url_for("public.resultado"))
        return redirect(url_for("public.descubra", passo=passo + 1))

    return render_template("descubra.html", passo=passo, pergunta=pergunta, perguntas=PERGUNTAS,
                           marcadas=respostas.get(pergunta["chave"], []))


@bp.route("/descubra/resultado")
def resultado():
    respostas = session.get("quiz", {})
    exps = _experiencias()
    sugestoes, categoria = recomendar(respostas, exps)
    session["quiz_resumo"] = resumo_preferencias(respostas)
    return render_template("resultado.html", sugestoes=sugestoes, categoria=categoria,
                           resumo=session["quiz_resumo"])


@bp.route("/contato")
def contato():
    return render_template("contato.html")


@bp.route("/politicas")
def politicas():
    return render_template("politicas.html")
