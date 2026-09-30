"""Utilidades: fuso horário, formatação em pt-BR, categorias e links."""
import re
import unicodedata
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
FMT = "%Y-%m-%d %H:%M"

CATEGORIAS = {
    "headspa": "Head Spa",
    "massagens": "Massagens",
    "dayspa": "Day Spa",
    "kids": "Kids",
}

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
DIAS_CURTO = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

STATUS = {
    "aguardando_pagamento": ("Aguardando Pix", "ambar"),
    "pagamento_informado": ("Pix em conferência", "ambar"),
    "confirmada": ("Confirmada", "verde"),
    "cancelada": ("Cancelada", "cinza"),
    "expirada": ("Expirada", "cinza"),
}


def agora():
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def parse_dt(s):
    return datetime.strptime(s, FMT)


def fmt_dt(dt):
    return dt.strftime(FMT)


def reais(centavos):
    if centavos is None:
        return ""
    inteiro, cent = divmod(int(centavos), 100)
    return "R$ " + f"{inteiro:,}".replace(",", ".") + f",{cent:02d}"


def duracao(minutos):
    if not minutos:
        return ""
    h, m = divmod(int(minutos), 60)
    if h and m:
        return f"{h}h{m:02d}"
    if h:
        return f"{h}h"
    return f"{m} min"


def data_longa(dt):
    return f"{DIAS[dt.weekday()]}, {dt.day} de {MESES[dt.month - 1]}"


def slugify(texto):
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-") or "experiencia"


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def whatsapp_link(numero, mensagem=""):
    d = so_digitos(numero)
    if not d:
        return ""
    if not d.startswith("55"):
        d = "55" + d
    url = f"https://wa.me/{d}"
    if mensagem:
        url += "?text=" + quote(mensagem)
    return url


def instagram_link(handle):
    h = (handle or "").strip()
    if not h:
        return ""
    if h.startswith("http"):
        return h
    return "https://instagram.com/" + h.lstrip("@")


def experiencia_reservavel(exp):
    return bool(exp["ativo"] and exp["duracao_min"] and exp["preco_centavos"])


def sinal_de(preco_centavos):
    return (int(preco_centavos) + 1) // 2  # metade, arredondando para cima
