"""Questionário "Descubra seu momento": 6 perguntas opcionais e recomendação."""

PERGUNTAS = [
    {
        "chave": "sentimento",
        "rotulo": "Sentimento",
        "titulo": "Como você está se sentindo hoje?",
        "ajuda": "Escolha até 2 opções.",
        "multipla": 2,
        "opcoes": [
            ("mente", "Com a mente acelerada", {"headspa": 3, "dayspa": 1}),
            ("cansada", "Cansada", {"dayspa": 2, "headspa": 1, "massagens": 1}),
            ("tensao", "Com tensão no corpo", {"massagens": 3, "dayspa": 1}),
            ("momento", "Precisando de um momento só meu", {"dayspa": 2, "headspa": 1}),
            ("fios", "Quero cuidar do couro cabeludo e dos fios", {"headspa": 4}),
            ("completa", "Quero uma experiência completa", {"dayspa": 4}),
            ("crianca", "Estou escolhendo para uma criança", {"kids": 10}),
        ],
    },
    {
        "chave": "foco",
        "rotulo": "Foco",
        "titulo": "Onde você quer sentir o cuidado?",
        "ajuda": "Escolha uma opção.",
        "multipla": 1,
        "opcoes": [
            ("cabeca", "Na cabeça e no couro cabeludo", {"headspa": 3}),
            ("corpo", "No corpo", {"massagens": 3}),
            ("tudo", "Um pouco de tudo", {"dayspa": 3}),
            ("tanto", "Tanto faz, quero relaxar", {}),
        ],
    },
    {
        "chave": "tempo",
        "rotulo": "Tempo",
        "titulo": "Quanto tempo você tem?",
        "ajuda": "Usamos isso para sugerir experiências que cabem no seu dia.",
        "multipla": 1,
        "opcoes": [
            ("curto", "Até 1 hora", {"_max_min": 60}),
            ("medio", "Até 2 horas", {"_max_min": 120}),
            ("longo", "Uma manhã ou tarde inteira", {"dayspa": 2}),
        ],
    },
    {
        "chave": "massagem",
        "rotulo": "Massagem",
        "titulo": "Como você prefere o toque?",
        "ajuda": "Vale para a massagem no couro cabeludo e no corpo.",
        "multipla": 1,
        "opcoes": [
            ("leve", "Leve e bem suave", {}),
            ("media", "Pressão média", {"massagens": 1}),
            ("firme", "Mais firme", {"massagens": 2}),
            ("sem", "Prefiro sem massagem no corpo", {"headspa": 2, "massagens": -4}),
        ],
    },
    {
        "chave": "aromas",
        "rotulo": "Aromas",
        "titulo": "Que tipo de aroma combina com você?",
        "ajuda": "Anotamos sua preferência para o atendimento.",
        "multipla": 1,
        "opcoes": [
            ("florais", "Suaves e florais", {}),
            ("citricos", "Frescos e cítricos", {}),
            ("amadeirados", "Amadeirados", {}),
            ("sem", "Prefiro sem aroma", {}),
        ],
    },
    {
        "chave": "investimento",
        "rotulo": "Investimento",
        "titulo": "Quanto você quer investir neste momento?",
        "ajuda": "Sem certo ou errado — isso só ajusta a ordem das sugestões.",
        "multipla": 1,
        "opcoes": [
            ("simples", "Algo mais simples", {"_preco": "baixo"}),
            ("intermediario", "Intermediário", {"_preco": "medio"}),
            ("completo", "A experiência completa", {"_preco": "alto", "dayspa": 1}),
            ("nao", "Prefiro não dizer", {}),
        ],
    },
]

POR_CHAVE = {p["chave"]: p for p in PERGUNTAS}


def rotulo_opcao(pergunta_chave, valor):
    for v, rotulo, _ in POR_CHAVE[pergunta_chave]["opcoes"]:
        if v == valor:
            return rotulo
    return ""


def resumo_preferencias(respostas):
    partes = []
    for p in PERGUNTAS:
        vals = respostas.get(p["chave"]) or []
        rot = [rotulo_opcao(p["chave"], v) for v in vals if rotulo_opcao(p["chave"], v)]
        if rot:
            partes.append(f"{p['rotulo']}: {', '.join(rot)}")
    return " · ".join(partes)


def recomendar(respostas, experiencias):
    pontos = {"headspa": 0, "massagens": 0, "dayspa": 0, "kids": 0}
    max_min = None
    faixa = None
    for p in PERGUNTAS:
        for valor in respostas.get(p["chave"]) or []:
            for v, _, efeitos in p["opcoes"]:
                if v != valor:
                    continue
                for k, n in efeitos.items():
                    if k == "_max_min":
                        max_min = n
                    elif k == "_preco":
                        faixa = n
                    else:
                        pontos[k] += n

    crianca = "crianca" in (respostas.get("sentimento") or [])
    ativos = [e for e in experiencias if e["ativo"]]
    if crianca:
        ativos = [e for e in ativos if e["categoria"] == "kids"] or ativos

    precos = sorted(e["preco_centavos"] for e in ativos if e["preco_centavos"])

    def nota(e):
        n = pontos.get(e["categoria"], 0) * 10
        if e["duracao_min"] and e["preco_centavos"]:
            n += 5  # reservável agora
        if max_min and e["duracao_min"]:
            n += 6 if e["duracao_min"] <= max_min else -8
        if faixa and precos and e["preco_centavos"]:
            posicao = precos.index(e["preco_centavos"]) / max(1, len(precos) - 1)
            alvo = {"baixo": 0.0, "medio": 0.5, "alto": 1.0}[faixa]
            n += 6 - int(abs(posicao - alvo) * 10)
        if e["destaque"]:
            n += 1
        return n

    ordenadas = sorted(ativos, key=nota, reverse=True)
    categoria_top = max(pontos, key=pontos.get) if any(pontos.values()) else None
    return ordenadas[:3], categoria_top
