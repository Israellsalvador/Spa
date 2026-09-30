"""Teste de ponta a ponta: cadastro, reserva, Pix, confirmação, remarcação e conflitos."""
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMP = tempfile.mkdtemp()
os.environ.update(DATA_DIR=TMP, ADMIN_EMAIL="admin@teste.com", ADMIN_PASSWORD="admin12345")

from app import create_app  # noqa: E402
from app.pix import _crc16, copia_e_cola  # noqa: E402

app = create_app()


def csrf(client, url="/"):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf" value="([0-9a-f]+)"', html).group(1)


def login(client, email, senha):
    t = csrf(client, "/entrar")
    return client.post("/entrar", data={"csrf": t, "email": email, "senha": senha, "aba": "entrar"})


def ok(cond, msg):
    print(("OK   " if cond else "FALHA") + " " + msg)
    if not cond:
        raise SystemExit(1)


def main():
    admin = app.test_client()
    ana = app.test_client()
    bia = app.test_client()

    # Sem Pix/preço: agendar mostra estado vazio
    ok("Vamos combinar o seu horário" in ana.get("/agendar").get_data(as_text=True), "agendar vazio sem Pix/preço")

    # Admin configura
    r = login(admin, "admin@teste.com", "admin12345")
    ok(r.status_code == 302 and r.headers["Location"].endswith("/admin/"), "admin entra no painel")
    ok("Cadastrar a chave Pix" in admin.get("/admin/").get_data(as_text=True), "painel lista pendências")
    t = csrf(admin, "/admin/configuracoes")
    dados = {"csrf": t, "pix_chave": "+55 (34) 99999-0000", "pix_nome": "Fonte Serena Ltda", "pix_cidade": "Patos de Minas",
             "whatsapp": "(34) 99999-0000", "endereco": "Rua Teste, 100 - Centro", "cidade": "Patos de Minas/MG",
             "hora_inicio": "08:00", "ultimo_inicio": "16:00", "intervalo_min": "30", "capacidade": "1",
             "antecedencia_horas": "2", "janela_dias": "30", "bloqueio_min": "15", "remarcar_horas": "8",
             "dias_semana": ["0", "1", "2", "3", "4"], "politicas": "Texto de teste."}
    ok(admin.post("/admin/configuracoes", data=dados).status_code == 302, "salva configurações")
    t = csrf(admin, "/admin/experiencias/1")
    r = admin.post("/admin/experiencias/1", data={"csrf": t, "nome": "Pacote completo", "categoria": "dayspa",
                                                 "resumo": "Tudo junto.", "inclui": "Head Spa\nSauna",
                                                 "duracao_min": "180", "preco": "1.234,50", "ativo": "1", "destaque": "1", "ordem": "1"})
    ok(r.status_code == 302, "salva preço e duração")

    # Página de experiências mostra preço formatado
    ok("R$ 1.234,50" in ana.get("/experiencias").get_data(as_text=True), "preço em R$ formatado")

    # Cliente cria conta
    t = csrf(ana, "/entrar?aba=cadastro")
    r = ana.post("/entrar", data={"csrf": t, "aba": "cadastro", "nome": "Ana Souza", "telefone": "34988887777",
                                  "email": "ana@teste.com", "senha": "senha1234", "next": "/agendar"})
    ok(r.status_code == 302 and r.headers["Location"] == "/agendar", "cadastro redireciona para /agendar")

    # Escolhe dia e horário
    html = ana.get("/agendar/pacote-completo").get_data(as_text=True)
    horas = re.findall(r'href="/agendar/pacote-completo\?data=([\d-]+)&amp;hora=(\d\d:\d\d)', html)
    ok(len(horas) > 0, f"horários disponíveis ({len(horas)})")
    data, hora = horas[0]
    t = csrf(ana, f"/agendar/pacote-completo?data={data}&hora={hora}")
    r = ana.post("/agendar/pacote-completo/reservar", data={"csrf": t, "data": data, "hora": hora})
    ok(r.status_code == 302 and "/reserva/FS" in r.headers["Location"], "reserva criada")
    url_reserva = r.headers["Location"]
    codigo = url_reserva.rsplit("/", 1)[1]

    html = ana.get(url_reserva).get_data(as_text=True)
    ok("R$ 617,25" in html, "sinal de 50% arredondado para cima")
    payload = re.search(r'id="pix-codigo" type="text" readonly value="([^"]+)"', html).group(1)
    ok(payload.startswith("000201") and _crc16(payload[:-4]) == payload[-4:], "Pix Copia e Cola com CRC válido")
    ok("+5534999990000" in payload and "5406617.25" in payload and codigo in payload, "Pix com chave, valor e txid")
    ok("<svg" in html, "QR Code renderizado")

    # Outra cliente não vê a reserva e não consegue o mesmo horário (capacidade 1)
    t = csrf(bia, "/entrar?aba=cadastro")
    bia.post("/entrar", data={"csrf": t, "aba": "cadastro", "nome": "Bia", "email": "bia@teste.com", "senha": "senha1234"})
    ok(bia.get(url_reserva).status_code == 404, "outra cliente não acessa a reserva")
    html_b = bia.get(f"/agendar/pacote-completo?data={data}").get_data(as_text=True)
    ok(f"hora={hora}" not in html_b, "horário bloqueado para outras clientes durante o pagamento")
    t = csrf(bia, "/agendar")
    r = bia.post("/agendar/pacote-completo/reservar", data={"csrf": t, "data": data, "hora": hora})
    ok("/reserva/" not in r.headers.get("Location", ""), "reserva duplicada recusada")

    # Cliente avisa que pagou; admin confirma
    t = csrf(ana, url_reserva)
    ana.post(f"/reserva/{codigo}/paguei", data={"csrf": t})
    ok("Estamos conferindo seu Pix" in ana.get(url_reserva).get_data(as_text=True), "status: Pix em conferência")
    painel = admin.get("/admin/").get_data(as_text=True)
    ok(codigo in painel, "reserva aparece no painel para conferir")
    bid = re.search(r'/admin/reserva/(\d+)/confirmar', painel).group(1)
    t = csrf(admin, "/admin/")
    admin.post(f"/admin/reserva/{bid}/confirmar", data={"csrf": t, "voltar": "/admin/"})
    html = ana.get("/meus-agendamentos").get_data(as_text=True)
    ok("Confirmada" in html, "cliente vê reserva confirmada")

    # Remarcação (se faltar mais de 8h)
    r = ana.get(f"/reserva/{codigo}/remarcar")
    if r.status_code == 200:
        html = r.get_data(as_text=True)
        novas = re.findall(rf'href="/reserva/{codigo}/remarcar\?data=([\d-]+)&amp;hora=(\d\d:\d\d)', html)
        nd, nh = novas[-1]
        t = csrf(ana, f"/reserva/{codigo}/remarcar?data={nd}&hora={nh}")
        r = ana.post(f"/reserva/{codigo}/remarcar", data={"csrf": t, "data": nd, "hora": nh})
        ok(r.status_code == 302 and r.headers["Location"].endswith("/meus-agendamentos"), f"remarcada para {nd} {nh}")
        # horário antigo liberado para outra cliente
        html_b = bia.get(f"/agendar/pacote-completo?data={data}").get_data(as_text=True)
        ok(f"hora={hora}" in html_b, "horário antigo liberado")
    else:
        print("---- remarcação pulada (menos de 8h)")

    # Segurança básica
    ok(ana.get("/admin/").status_code == 403, "cliente não acessa o admin")
    ok(ana.post("/sair").status_code == 400, "POST sem CSRF recusado")
    r = login(app.test_client(), "ana@teste.com", "errada")
    ok("E-mail ou senha incorretos" in r.get_data(as_text=True), "senha errada recusada")
    ok(copia_e_cola("a@b.com", "Nome", "Cidade", 1000, "X")[-4:] == _crc16(copia_e_cola("a@b.com", "Nome", "Cidade", 1000, "X")[:-4]), "CRC Pix")

    # Todas as páginas renderizam
    for u in ["/", "/experiencias", "/experiencias?categoria=kids", "/experiencias?online=1", "/descubra",
              "/descubra?sentimento=tensao", "/descubra/resultado", "/contato", "/politicas", "/agendar"]:
        ok(ana.get(u).status_code == 200, "GET " + u)
    for u in ["/admin/", "/admin/agenda", "/admin/experiencias", "/admin/experiencias/nova", "/admin/configuracoes", "/admin/clientes"]:
        ok(admin.get(u).status_code == 200, "GET " + u)
    print("\nTudo certo.")


try:
    main()
finally:
    shutil.rmtree(TMP, ignore_errors=True)
