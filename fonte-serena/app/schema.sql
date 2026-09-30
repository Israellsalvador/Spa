CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    telefone TEXT,
    senha_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    categoria TEXT NOT NULL,
    resumo TEXT,
    descricao TEXT,
    inclui TEXT,
    duracao_min INTEGER,
    preco_centavos INTEGER,
    ativo INTEGER NOT NULL DEFAULT 1,
    destaque INTEGER NOT NULL DEFAULT 0,
    ordem INTEGER NOT NULL DEFAULT 0,
    imagem TEXT
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY,
    codigo TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    experience_id INTEGER NOT NULL REFERENCES experiences(id),
    inicio TEXT NOT NULL,
    fim TEXT NOT NULL,
    status TEXT NOT NULL,
    preco_centavos INTEGER NOT NULL,
    sinal_centavos INTEGER NOT NULL,
    hold_ate TEXT,
    pagamento_informado_em TEXT,
    confirmado_em TEXT,
    cancelado_em TEXT,
    observacoes TEXT,
    remarcacoes INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bookings_inicio ON bookings(inicio);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);

CREATE TABLE IF NOT EXISTS settings (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
