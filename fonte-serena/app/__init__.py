import os
import secrets
from datetime import timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, abort, flash, g, redirect, request, send_from_directory, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from . import db as dbmod
from .util import (CATEGORIAS, STATUS, agora, data_longa, duracao, fmt_dt, instagram_link,
                   parse_dt, reais, whatsapp_link)


# ---------- fotos padrão (app/static/img/fotos) ----------

FOTOS_CATEGORIA = {"headspa": ["head-spa.jpg"], "dayspa": ["hidromassagem.jpg", "jardim.jpg"],
                   "massagens": ["sala.jpg", "roupoes.jpg"]}
FOTOS_SITE = {"hero_imagem": "head-spa.jpg", "sobre_imagem": "jardim.jpg", "entrar": "roupoes.jpg"}
FOTOS_POSICAO = {"head-spa.jpg": "50% 42%", "hidromassagem.jpg": "50% 40%", "roupoes.jpg": "50% 35%",
                 "jardim.jpg": "50% 55%", "sala.jpg": "50% 78%"}


# ---------- autenticação ----------

def current_user():
    if "user" not in g:
        g.user = None
        uid = session.get("uid")
        if uid:
            g.user = dbmod.get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            if g.user is None:
                session.pop("uid", None)
    return g.user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            flash("Entre na sua conta para continuar.", "info")
            return redirect(url_for("conta.entrar", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        u = current_user()
        if u is None:
            return redirect(url_for("conta.entrar", next=request.full_path.rstrip("?")))
        if not u["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def next_seguro(url, padrao="/"):
    if not url:
        return padrao
    p = urlparse(url)
    if p.scheme or p.netloc or not url.startswith("/") or url.startswith("//"):
        return padrao
    return url


# ---------- app ----------

def create_app():
    app = Flask(__name__)
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
    os.makedirs(os.path.join(data_dir, "uploads"), exist_ok=True)

    secret = os.environ.get("SECRET_KEY")
    if not secret:
        # Gera e guarda uma chave persistente no volume de dados
        chave_path = os.path.join(data_dir, ".secret_key")
        if os.path.exists(chave_path):
            secret = open(chave_path).read().strip()
        else:
            secret = secrets.token_hex(32)
            with open(chave_path, "w") as f:
                f.write(secret)

    app.config.update(
        SECRET_KEY=secret,
        DATA_DIR=data_dir,
        UPLOAD_DIR=os.path.join(data_dir, "uploads"),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )

    if os.environ.get("BEHIND_PROXY", "1") == "1":
        # Atrás do Nginx: respeita X-Forwarded-Proto/Host (links e cookies corretos em HTTPS)
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.teardown_appcontext(dbmod.close_db)
    dbmod.init_db(app)
    _criar_admin(app)

    from .public import bp as public_bp
    from .conta import bp as conta_bp
    from .reservas import bp as reservas_bp
    from .admin import bp as admin_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(conta_bp)
    app.register_blueprint(reservas_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def csrf_protect():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        if request.method == "POST":
            token = request.form.get("csrf") or request.headers.get("X-CSRF")
            if not token or not secrets.compare_digest(token, session["csrf"]):
                abort(400)

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    @app.route("/media/<path:nome>")
    def media(nome):
        resp = send_from_directory(app.config["UPLOAD_DIR"], nome, max_age=60 * 60 * 24 * 30)
        return resp

    @app.context_processor
    def contexto():
        s = dbmod.get_settings()
        return {
            "S": s,
            "user": current_user(),
            "csrf_token": session.get("csrf", ""),
            "CATEGORIAS": CATEGORIAS,
            "STATUS": STATUS,
            "wa_link": whatsapp_link(s.get("whatsapp"), "Olá! Vim pelo site da Fonte Serena."),
            "ig_link": instagram_link(s.get("instagram")),
        }

    def horario_texto():
        s = dbmod.get_settings()
        dias = sorted({int(d) for d in (s.get("dias_semana") or "").split(",") if d.strip().isdigit()})
        nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        if not dias:
            txt = "Atendimento com hora marcada"
            return txt
        if dias == list(range(dias[0], dias[-1] + 1)) and len(dias) > 1:
            d = f"{nomes[dias[0]].capitalize()} a {nomes[dias[-1]]}"
        else:
            d = ", ".join(nomes[i] for i in dias).capitalize()
        return f"{d}, das {_h(s.get('hora_inicio'))} às {_h(s.get('ultimo_inicio'))}"

    def horario_linhas():
        s = dbmod.get_settings()
        dias = {int(d) for d in (s.get("dias_semana") or "").split(",") if d.strip().isdigit()}
        uteis = [i for i in range(5) if i in dias]
        faixa = f"{_h(s.get('hora_inicio'))} às {_h(s.get('ultimo_inicio'))}"
        linhas = []
        if uteis == list(range(5)):
            linhas.append(("Segunda a sexta", faixa))
        else:
            nomes = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]
            for i in range(5):
                linhas.append((nomes[i], faixa if i in dias else "Fechado"))
        linhas.append(("Sábado", faixa if 5 in dias else "Fechado"))
        linhas.append(("Domingo", faixa if 6 in dias else "Fechado"))
        return linhas

    def mapa_link():
        s = dbmod.get_settings()
        if s.get("maps_url"):
            return s["maps_url"]
        if s.get("endereco"):
            from urllib.parse import quote
            return "https://www.google.com/maps/search/?api=1&query=" + quote(f"{s['endereco']}, {s.get('cidade', '')}")
        return ""

    def _media(nome):
        return url_for("media", nome=nome) if nome else ""

    def _static_foto(nome):
        return url_for("static", filename="img/fotos/" + nome) if nome else ""

    def foto_exp(e):
        """Foto da experiência: a enviada pelo painel ou a padrão da categoria."""
        opcoes = FOTOS_CATEGORIA.get(e["categoria"]) or [None]
        # alterna entre as fotos da categoria para não repetir a mesma imagem lado a lado
        return _media(e["imagem"]) or _static_foto(opcoes[(e["id"] - 1) % len(opcoes)])

    def foto_site(chave):
        """Foto do site: a enviada em Configurações ou a padrão do projeto."""
        return _media(dbmod.get_settings().get(chave)) or _static_foto(FOTOS_SITE.get(chave))

    def foto_pos(url):
        for nome, pos in FOTOS_POSICAO.items():
            if url.endswith(nome):
                return pos
        return "50% 50%"

    app.jinja_env.globals.update(foto_exp=foto_exp, foto_site=foto_site, foto_pos=foto_pos)
    app.jinja_env.globals.update(hora_fmt=_h, horario_texto=horario_texto, horario_linhas=horario_linhas, mapa_link=mapa_link)
    app.jinja_env.filters["wa"] = lambda n: whatsapp_link(n)
    app.jinja_env.filters["reais"] = reais
    app.jinja_env.filters["duracao"] = duracao
    app.jinja_env.filters["data_longa"] = lambda s: data_longa(parse_dt(s) if isinstance(s, str) else s)
    app.jinja_env.filters["hora"] = lambda s: (parse_dt(s) if isinstance(s, str) else s).strftime("%H:%M")
    app.jinja_env.filters["dt"] = parse_dt
    app.jinja_env.globals["agora"] = agora
    app.jinja_env.globals["fmt_dt"] = fmt_dt

    from flask import render_template

    @app.errorhandler(404)
    def nao_encontrado(_e):
        return render_template("erro.html", titulo="Página não encontrada",
                               texto="O endereço que você abriu não existe ou mudou de lugar."), 404

    @app.errorhandler(403)
    def proibido(_e):
        return render_template("erro.html", titulo="Acesso restrito",
                               texto="Esta área é só para a administração do espaço."), 403

    @app.errorhandler(400)
    def invalido(_e):
        return render_template("erro.html", titulo="Sessão expirada",
                               texto="Recarregue a página e tente de novo."), 400

    @app.errorhandler(413)
    def grande(_e):
        return render_template("erro.html", titulo="Arquivo muito grande",
                               texto="Envie imagens de até 8 MB."), 413

    return app


def _h(txt):
    try:
        h, m = (txt or "").split(":")
        return f"{int(h)}h" if m == "00" else f"{int(h)}h{m}"
    except ValueError:
        return txt or ""


def _criar_admin(app):
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    senha = os.environ.get("ADMIN_PASSWORD") or ""
    if not email or not senha:
        return
    with app.app_context():
        db = dbmod.get_db()
        u = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if u is None:
            db.execute(
                "INSERT INTO users (nome, email, senha_hash, is_admin, criado_em) VALUES (?, ?, ?, 1, ?)",
                ("Administração", email, generate_password_hash(senha), fmt_dt(agora())),
            )
        else:
            db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (u["id"],))
        dbmod.close_db()
