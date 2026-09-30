"""Regras de agenda: dias, horários livres, bloqueio temporário e remarcação."""
from datetime import datetime, timedelta

from .util import FMT, agora, fmt_dt, parse_dt

ATIVOS = ("aguardando_pagamento", "pagamento_informado", "confirmada")


def config_agenda(s):
    def hm(txt, padrao):
        try:
            h, m = txt.split(":")
            return int(h), int(m)
        except (ValueError, AttributeError):
            return padrao

    def inteiro(txt, padrao):
        try:
            return max(0, int(txt))
        except (ValueError, TypeError):
            return padrao

    dias = set()
    for p in (s.get("dias_semana") or "").split(","):
        if p.strip().isdigit():
            dias.add(int(p.strip()))
    bloqueadas = set()
    for linha in (s.get("datas_bloqueadas") or "").replace(",", "\n").splitlines():
        linha = linha.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                bloqueadas.add(datetime.strptime(linha, fmt).date())
                break
            except ValueError:
                continue
    return {
        "dias": dias,
        "inicio": hm(s.get("hora_inicio"), (8, 0)),
        "ultimo": hm(s.get("ultimo_inicio"), (16, 0)),
        "intervalo": max(5, inteiro(s.get("intervalo_min"), 30)),
        "capacidade": max(1, inteiro(s.get("capacidade"), 1)),
        "antecedencia": inteiro(s.get("antecedencia_horas"), 2),
        "janela": max(1, inteiro(s.get("janela_dias"), 30)),
        "bloqueio": max(5, inteiro(s.get("bloqueio_min"), 15)),
        "remarcar": inteiro(s.get("remarcar_horas"), 8),
        "bloqueadas": bloqueadas,
    }


def expirar_bloqueios(db):
    db.execute(
        "UPDATE bookings SET status = 'expirada' "
        "WHERE status = 'aguardando_pagamento' AND hold_ate IS NOT NULL AND hold_ate < ?",
        (fmt_dt(agora()),),
    )


def _ocupados(db, inicio, fim, excluir_id=None):
    agora_txt = fmt_dt(agora())
    rows = db.execute(
        "SELECT id, inicio, fim, status, hold_ate FROM bookings "
        "WHERE status IN ('aguardando_pagamento','pagamento_informado','confirmada') "
        "AND inicio < ? AND fim > ?",
        (fmt_dt(fim), fmt_dt(inicio)),
    ).fetchall()
    out = []
    for r in rows:
        if excluir_id and r["id"] == excluir_id:
            continue
        if r["status"] == "aguardando_pagamento" and r["hold_ate"] and r["hold_ate"] < agora_txt:
            continue
        out.append((parse_dt(r["inicio"]), parse_dt(r["fim"])))
    return out


def horario_livre(db, cfg, inicio, duracao_min, excluir_id=None):
    fim = inicio + timedelta(minutes=duracao_min)
    ocupados = _ocupados(db, inicio, fim, excluir_id)
    # Maior número de atendimentos simultâneos dentro do intervalo pedido
    pontos = sorted({inicio} | {a for a, _ in ocupados if inicio <= a < fim})
    pico = 0
    for p in pontos:
        pico = max(pico, sum(1 for a, b in ocupados if a <= p < b))
    return pico < cfg["capacidade"]


def horarios_do_dia(db, cfg, dia, duracao_min, excluir_id=None):
    if dia.weekday() not in cfg["dias"] or dia in cfg["bloqueadas"]:
        return []
    limite = agora() + timedelta(hours=cfg["antecedencia"])
    h, m = cfg["inicio"]
    atual = datetime(dia.year, dia.month, dia.day, h, m)
    h, m = cfg["ultimo"]
    ultimo = datetime(dia.year, dia.month, dia.day, h, m)
    livres = []
    while atual <= ultimo:
        if atual >= limite and horario_livre(db, cfg, atual, duracao_min, excluir_id):
            livres.append(atual)
        atual += timedelta(minutes=cfg["intervalo"])
    return livres


def dias_disponiveis(db, cfg, duracao_min, excluir_id=None):
    hoje = agora().date()
    dias = []
    for i in range(cfg["janela"] + 1):
        dia = hoje + timedelta(days=i)
        if horarios_do_dia(db, cfg, dia, duracao_min, excluir_id):
            dias.append(dia)
    return dias


def pode_remarcar(booking, cfg):
    if booking["status"] != "confirmada":
        return False
    return parse_dt(booking["inicio"]) - agora() >= timedelta(hours=cfg["remarcar"])


__all__ = [
    "ATIVOS", "FMT", "config_agenda", "expirar_bloqueios", "horario_livre",
    "horarios_do_dia", "dias_disponiveis", "pode_remarcar",
]
