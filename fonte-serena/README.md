# Fonte Serena — site com agendamento

Site do Head Spa com reserva online, sinal de 50% via Pix e painel da administração.
Flask + SQLite, roda em um container Docker.

## O que tem

**Para a cliente**
- Início, Experiências (com filtros), página de cada experiência, Contato e Políticas
- **Descubra seu momento**: questionário de 6 perguntas opcionais que sugere experiências
- **Agendar**: escolhe a experiência → dia e horário livres → paga o sinal por **Pix Copia e Cola ou QR Code**
- O horário fica bloqueado por 15 min enquanto ela paga (configurável). Se não pagar, é liberado sozinho
- **Meus agendamentos**: status de cada reserva, pagar sinal, **remarcar até 8h antes** (configurável)
- Conta com e-mail e senha. Ver preços e fazer o questionário não exige cadastro

**Para a dona (/admin)**
- **Painel**: lista de Pix para conferir, com os botões "Pix recebido" / "Não recebido", e os próximos atendimentos
- **Agenda** do dia
- **Experiências**: nome, categoria, descrição, o que inclui, duração, preço, foto, destaque
- **Configurações**: chave Pix, WhatsApp, endereço, Instagram, dias e horários, datas bloqueadas (feriados), políticas e fotos do site
- **Clientes**: lista, com geração de senha temporária para quem esqueceu a senha
- Lista automática do que falta configurar antes de abrir as reservas

Enquanto faltar a chave Pix, ou duração e preço de uma experiência, o site não quebra. A experiência aparece como "Valores a confirmar", com botão de WhatsApp.

## Subir no servidor

```bash
cp .env.example .env
nano .env            # SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
docker compose up -d --build
docker compose logs -f
```

O app escuta em `127.0.0.1:8000`. Para testar direto sem Nginx, troque a porta no
`docker-compose.yml` para `"8000:8000"` e use `COOKIE_SECURE=0` no `.env`.

## Primeiro acesso (checklist)

1. Abra `/entrar` e entre com o `ADMIN_EMAIL` / `ADMIN_PASSWORD` do `.env`.
2. **Configurações** → preencha a chave Pix, o nome do recebedor (como aparece no banco), o WhatsApp, o endereço e o Instagram.
3. **Configurações** → confira dias e horários. O padrão é seg–sex, das 8h às 16h (último início), com 1 atendimento por vez.
4. **Configurações** → publique as **políticas de cancelamento e reembolso** antes de cobrar.
5. **Experiências** → cadastre duração e preço de cada uma e suba as fotos. Já vêm criadas "Pacote completo" e "Head Spa", sem preço.
6. **Configurações** → suba a foto principal e a foto do espaço.
7. Faça uma reserva de teste com outra conta e confirme pelo painel.

## Fotos

O projeto já vem com 5 fotos do espaço em `app/static/img/fotos/`:

| Arquivo | Onde aparece |
|---|---|
| `head-spa.jpg` | Topo da página inicial e cartões de Head Spa |
| `hidromassagem.jpg` | Pacote completo e cartões de Day Spa |
| `sala.jpg` | Galeria "O espaço" e cartões de Massagens |
| `jardim.jpg` | Galeria "O espaço" e seção Visite (quando não há endereço) |
| `roupoes.jpg` | Galeria "O espaço" e página Entrar |

Uma foto enviada pelo painel substitui a padrão: em **Configurações** para topo e espaço, e em cada **Experiência** para os cartões.

## Fontes

Newsreader (títulos) e Figtree (textos) ficam em `app/static/fonts/`, dentro do próprio site. Não dependem do Google Fonts, o que também evita repassar dados de acesso a terceiros (LGPD). As duas têm licença SIL Open Font License, com o texto na mesma pasta.

## Nginx (HTTPS)

```nginx
server {
    server_name fonteserena.com.br www.fonteserena.com.br;
    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
    listen 80;
}
```

Depois: `certbot --nginx -d fonteserena.com.br -d www.fonteserena.com.br`.

## Como o Pix funciona

- O site gera um **BR Code estático com valor** (padrão do Banco Central) para a chave cadastrada. Não precisa de conta em gateway nem de API do banco.
- O **código da reserva** (ex.: `FSK7M2QX9A`) vai no identificador da transação. É por ele que a dona acha o Pix no extrato.
- A confirmação é **manual**. A cliente toca em "Já paguei", a reserva vai para "Pix para conferir" e a dona marca "Pix recebido" depois de ver o dinheiro na conta.
- Enquanto a reserva está "em conferência", o horário continua bloqueado para as outras clientes.

## Backup

Tudo fica no volume `dados`: banco `fonte-serena.db`, fotos em `uploads/` e a chave de sessão.

```bash
# backup
docker run --rm -v fonte-serena_dados:/data -v "$PWD":/bkp alpine tar czf /bkp/fonte-serena-$(date +%F).tgz -C /data .
# restaurar
docker compose down
docker run --rm -v fonte-serena_dados:/data -v "$PWD":/bkp alpine sh -c "rm -rf /data/* && tar xzf /bkp/ARQUIVO.tgz -C /data"
docker compose up -d
```

Para automatizar, coloque o comando de backup num cron diário.

## Atualizar

```bash
docker compose up -d --build
```

O banco é migrado sozinho na subida. As tabelas são criadas se não existirem, e os dados não são apagados.

## Rodar sem Docker (desenvolvimento)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export ADMIN_EMAIL=admin@teste.com ADMIN_PASSWORD=admin12345 COOKIE_SECURE=0
flask --app wsgi run --debug     # http://127.0.0.1:5000  (dados em ./data)
python tests/test_fluxo.py       # teste de ponta a ponta
```

## Estrutura

```
app/
  __init__.py     app, sessão, CSRF, cabeçalhos de segurança, admin inicial
  db.py           SQLite, configurações padrão e experiências iniciais
  schema.sql      tabelas
  agenda.py       horários livres, bloqueio de 15 min, capacidade, remarcação
  pix.py          Pix Copia e Cola (BR Code + CRC16) e QR Code em SVG
  quiz.py         perguntas do "Descubra seu momento" e recomendação
  public.py       páginas públicas e questionário
  conta.py        entrar, criar conta, sair, meus agendamentos
  reservas.py     agendar, pagamento, "já paguei", cancelar, remarcar
  admin.py        painel, agenda, experiências, configurações, clientes
  templates/      páginas (Jinja)
  static/         CSS, JS, favicon
tests/test_fluxo.py
```

## Segurança

- Senhas com hash (Werkzeug/PBKDF2) e sessão assinada com cookie HttpOnly, SameSite=Lax e Secure (em HTTPS)
- CSRF em todos os formulários
- Cada cliente só vê as próprias reservas. O `/admin` exige conta de administração
- Reserva criada em transação exclusiva do SQLite, o que evita duas clientes no mesmo horário
- Upload aceita só JPG, PNG ou WEBP (conferidos pelo conteúdo do arquivo), até 8 MB
