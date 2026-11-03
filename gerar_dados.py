"""
Gerador de dados fictícios de logística (simula o "sistema da empresa").

Uso:
    python gerar_dados.py --historico            # gera dimensões + histórico até ontem
    python gerar_dados.py --dia                  # gera o relatório do dia de hoje
    python gerar_dados.py --dia 2026-11-03       # gera o relatório de um dia específico

Tudo é determinístico: o mesmo dia sempre gera os mesmos pedidos, então rodar
o histórico e depois os dias seguintes produz uma base consistente.
O relatório diário traz os pedidos novos do dia e as atualizações de status
(expedições e entregas) que aconteceram naquele dia, como um export real de ERP.
"""
import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENTRADA = BASE / "entrada"
DADOS = BASE / "dados"

INICIO_HISTORICO = date(2025, 5, 1)
SEED = 2026

# --------------------------------------------------------------------------
# Dimensões (empresa fictícia "MoveTech Componentes Industriais")
# --------------------------------------------------------------------------
CENTROS = [
    # id, nome, cidade, uf, capacidade_pedidos_dia
    ("CD01", "CD Pomerode", "Pomerode", "SC", 22),
    ("CD02", "CD Joinville", "Joinville", "SC", 14),
    ("CD03", "CD Curitiba", "Curitiba", "PR", 10),
    ("CD04", "CD Campinas", "Campinas", "SP", 16),
]

TRANSPORTADORAS = [
    # id, nome, modal, confiabilidade (prob. no prazo), custo_relativo
    ("TR01", "Rota Sul Cargas", "Rodoviário", 0.94, 1.00),
    ("TR02", "Expresso Atlântico", "Rodoviário", 0.88, 0.85),
    ("TR03", "Veloz Log", "Rodoviário expresso", 0.96, 1.35),
    ("TR04", "TransBrasil Fracionados", "Rodoviário fracionado", 0.82, 0.75),
    ("TR05", "AeroCarga Express", "Aéreo", 0.97, 2.40),
]

CATEGORIAS = {
    # categoria: (peso_kg_min, peso_kg_max, valor_unit_min, valor_unit_max)
    "Cilindros hidráulicos": (8, 60, 900, 6500),
    "Válvulas direcionais": (1, 8, 350, 2800),
    "Bombas hidráulicas": (6, 45, 1800, 14000),
    "Motores hidráulicos": (5, 40, 2200, 16000),
    "Atuadores lineares": (2, 25, 1200, 9000),
    "Componentes pneumáticos": (0.3, 4, 60, 900),
    "Unidades de potência": (40, 250, 9000, 48000),
    "Sensores e controladores": (0.2, 2, 250, 3500),
}

SINGULAR = {
    "Cilindros hidráulicos": "Cilindro hidráulico", "Válvulas direcionais": "Válvula direcional",
    "Bombas hidráulicas": "Bomba hidráulica", "Motores hidráulicos": "Motor hidráulico",
    "Atuadores lineares": "Atuador linear", "Componentes pneumáticos": "Componente pneumático",
    "Unidades de potência": "Unidade de potência", "Sensores e controladores": "Sensor/controlador",
}

UFS = [
    # uf, regiao, peso (demanda), prazo_base_dias a partir de SC
    ("SC", "Sul", 18, 2), ("PR", "Sul", 12, 2), ("RS", "Sul", 11, 3),
    ("SP", "Sudeste", 22, 3), ("MG", "Sudeste", 9, 4), ("RJ", "Sudeste", 6, 4),
    ("ES", "Sudeste", 2, 5), ("GO", "Centro-Oeste", 4, 5), ("MT", "Centro-Oeste", 3, 6),
    ("MS", "Centro-Oeste", 2, 5), ("DF", "Centro-Oeste", 1, 5), ("BA", "Nordeste", 3, 7),
    ("PE", "Nordeste", 2, 8), ("CE", "Nordeste", 1, 9), ("AM", "Norte", 1, 11),
    ("PA", "Norte", 1, 10),
]
CIDADES = {
    "SC": ["Blumenau", "Joinville", "Jaraguá do Sul", "Itajaí", "Chapecó"],
    "PR": ["Curitiba", "Ponta Grossa", "Londrina", "Maringá"],
    "RS": ["Caxias do Sul", "Porto Alegre", "Novo Hamburgo"],
    "SP": ["São Paulo", "Campinas", "Sorocaba", "São José dos Campos", "Ribeirão Preto"],
    "MG": ["Belo Horizonte", "Contagem", "Uberlândia"],
    "RJ": ["Rio de Janeiro", "Resende"], "ES": ["Serra"], "GO": ["Anápolis", "Goiânia"],
    "MT": ["Rondonópolis", "Cuiabá"], "MS": ["Campo Grande"], "DF": ["Brasília"],
    "BA": ["Camaçari", "Salvador"], "PE": ["Recife", "Suape"], "CE": ["Fortaleza"],
    "AM": ["Manaus"], "PA": ["Belém", "Parauapebas"],
}
SEGMENTOS = ["Máquinas agrícolas", "Construção", "Mineração", "Automotivo",
             "Papel e celulose", "Alimentos e bebidas", "Siderurgia", "Plásticos"]
PREFIXOS = ["Metal", "Agro", "Hidro", "Tec", "Forte", "Nova", "Sul", "Prime",
            "Indu", "Mega", "Força", "Ação", "Alfa", "Delta", "Ômega", "Vale"]
SUFIXOS = ["mec", "plast", "maq", "fer", "tech", "sul", "flex", "pack", "minas", "agro"]
TIPOS = ["Indústria", "Máquinas", "Equipamentos", "Metalúrgica", "Agroindustrial"]


def _f(v):
    return float(str(v).replace(",", "."))


def _peso_dias_semana(d: date) -> float:
    return {0: 1.15, 1: 1.1, 2: 1.05, 3: 1.0, 4: 0.9, 5: 0.25, 6: 0.05}[d.weekday()]


def _sazonalidade(d: date) -> float:
    # pico de safra/obra no 2º semestre, queda no fim de ano
    return {1: 0.8, 2: 0.9, 3: 1.0, 4: 1.0, 5: 1.05, 6: 1.05, 7: 1.0, 8: 1.1,
            9: 1.15, 10: 1.2, 11: 1.1, 12: 0.75}[d.month]


def gerar_dimensoes():
    rnd = random.Random(SEED)
    produtos = []
    for i, (cat, (pmin, pmax, vmin, vmax)) in enumerate(CATEGORIAS.items(), start=1):
        for j in range(1, 7):
            peso = round(rnd.uniform(pmin, pmax), 1)
            valor = round(rnd.uniform(vmin, vmax), -1)
            codigo = f"P{i:02d}{j:02d}"
            nome = f"{SINGULAR[cat]} {rnd.choice('ABCDEFGHKMRSTX')}{rnd.randint(10, 99)}"
            produtos.append((codigo, nome, cat, peso, valor))

    clientes = []
    nomes_usados = set()
    pesos_uf = [u[2] for u in UFS]
    for n in range(1, 181):
        uf, regiao, _, _ = rnd.choices(UFS, weights=pesos_uf)[0]
        while True:
            nome = f"{rnd.choice(PREFIXOS)}{rnd.choice(SUFIXOS)} {rnd.choice(TIPOS)}"
            if nome not in nomes_usados:
                nomes_usados.add(nome)
                break
        clientes.append((f"C{n:03d}", nome, rnd.choice(SEGMENTOS), rnd.choice(CIDADES[uf]), uf, regiao))

    DADOS.mkdir(exist_ok=True)
    _escrever(DADOS / "dim_centros.csv", ["cd_id", "centro", "cidade", "uf", "capacidade_dia"], CENTROS)
    _escrever(DADOS / "dim_transportadoras.csv",
              ["transportadora_id", "transportadora", "modal", "meta_no_prazo", "custo_relativo"],
              TRANSPORTADORAS)
    _escrever(DADOS / "dim_produtos.csv", ["produto_id", "produto", "categoria", "peso_kg", "valor_unitario"], produtos)
    _escrever(DADOS / "dim_clientes.csv", ["cliente_id", "cliente", "segmento", "cidade", "uf", "regiao"], clientes)
    return produtos, clientes


def _carregar_dimensoes():
    def ler(nome):
        with open(DADOS / nome, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f, delimiter=";"))
    if not (DADOS / "dim_produtos.csv").exists():
        gerar_dimensoes()
    return ler("dim_produtos.csv"), ler("dim_clientes.csv")


def _ciclo_de_vida(d: date, n: int, produtos, clientes):
    """Gera o pedido completo (incluindo o futuro). O relatório só mostra o que já aconteceu."""
    pid = f"PED-{d:%Y%m%d}-{n:03d}"
    r = random.Random(f"{SEED}-{pid}")
    cli = r.choice(clientes)
    prod = r.choice(produtos)
    uf = cli["uf"]
    info_uf = next(u for u in UFS if u[0] == uf)
    prazo_base = info_uf[3]

    # CD: preferência por proximidade
    if uf in ("SP", "MG", "RJ", "GO", "DF", "MT", "MS", "ES"):
        cd = r.choices(CENTROS, weights=[25, 5, 10, 60])[0]
    elif uf == "PR":
        cd = r.choices(CENTROS, weights=[30, 15, 55, 0])[0]
    else:
        cd = r.choices(CENTROS, weights=[55, 30, 10, 5])[0]

    # transportadora: aéreo só para Norte/Nordeste ou urgências
    pesos_tr = [30, 25, 15, 25, 0]
    if info_uf[1] in ("Norte", "Nordeste"):
        pesos_tr = [20, 20, 10, 25, 25]
    tr = r.choices(TRANSPORTADORAS, weights=pesos_tr)[0]

    qtd = max(1, int(r.paretovariate(1.6)))
    if _f(prod["valor_unitario"]) > 9000:
        qtd = min(qtd, 3)
    valor = round(qtd * _f(prod["valor_unitario"]) * r.uniform(0.92, 1.05), 2)
    peso = round(qtd * _f(prod["peso_kg"]), 1)

    prazo = prazo_base
    if tr[2] == "Aéreo":
        prazo = 2
    elif tr[2] == "Rodoviário expresso":
        prazo = max(1, prazo_base - 1)
    prazo += 1  # +1 dia de separação/expedição
    frete = round((35 + peso * 0.9 * (1 + prazo_base / 4)) * tr[4] * r.uniform(0.9, 1.15), 2)

    # expedição: 0-2 dias, mais lenta quando o CD está sobrecarregado (out/nov)
    atraso_exp = r.choices([0, 1, 2, 3], weights=[64, 30, 5, 1])[0]
    if d.month in (10, 11) and cd[0] == "CD01":
        atraso_exp += r.choices([0, 1], weights=[60, 40])[0]
    data_exp = d + timedelta(days=atraso_exp)

    # transporte: confiabilidade da transportadora (+ "crise" da TR02 em mar-abr/2026)
    conf = tr[3]
    if tr[0] == "TR02" and date(2026, 3, 1) <= d <= date(2026, 4, 30):
        conf -= 0.25
    if d.month == 12:
        conf -= 0.05
    transito = prazo - 1
    if r.random() > conf:
        transito += r.choices([1, 2, 3, 5, 8], weights=[40, 28, 17, 10, 5])[0]
    elif r.random() < 0.3:
        transito = max(1, transito - 1)
    data_entrega = data_exp + timedelta(days=transito)

    qtd_entregue = qtd
    if qtd > 1 and r.random() < 0.04:
        qtd_entregue = qtd - r.randint(1, max(1, qtd // 3))

    return {
        "pedido_id": pid, "data_pedido": d, "data_prometida": d + timedelta(days=prazo),
        "data_expedicao": data_exp, "data_entrega": data_entrega,
        "cd_id": cd[0], "transportadora_id": tr[0], "cliente_id": cli["cliente_id"],
        "produto_id": prod["produto_id"], "quantidade": qtd, "quantidade_entregue": qtd_entregue,
        "valor_mercadoria": valor, "peso_kg": peso, "custo_frete": frete,
    }


def pedidos_do_dia(d: date, produtos, clientes):
    r = random.Random(f"{SEED}-qtd-{d}")
    media = 38 * _peso_dias_semana(d) * _sazonalidade(d)
    tendencia = 1 + (d - INICIO_HISTORICO).days / 365 * 0.12  # crescimento de ~12% a.a.
    n = max(0, int(r.gauss(media * tendencia, 4)))
    return [_ciclo_de_vida(d, i, produtos, clientes) for i in range(1, n + 1)]


def _foto(p, ate: date):
    """Como o pedido aparece no sistema na data 'ate'."""
    linha = {k: p[k] for k in ("pedido_id", "data_pedido", "data_prometida", "cd_id", "transportadora_id",
                               "cliente_id", "produto_id", "quantidade", "valor_mercadoria", "peso_kg", "custo_frete")}
    if p["data_entrega"] <= ate:
        linha.update(data_expedicao=p["data_expedicao"], data_entrega=p["data_entrega"],
                     quantidade_entregue=p["quantidade_entregue"], status_sistema="ENTREGUE")
    elif p["data_expedicao"] <= ate:
        linha.update(data_expedicao=p["data_expedicao"], data_entrega="", quantidade_entregue="",
                     status_sistema="EM_TRANSITO")
    else:
        linha.update(data_expedicao="", data_entrega="", quantidade_entregue="", status_sistema="AGUARDANDO_EXPEDICAO")
    return linha


COLUNAS = ["pedido_id", "data_pedido", "data_prometida", "data_expedicao", "data_entrega", "status_sistema",
           "cd_id", "transportadora_id", "cliente_id", "produto_id", "quantidade", "quantidade_entregue",
           "valor_mercadoria", "peso_kg", "custo_frete"]


def _escrever(caminho: Path, cabecalho, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cabecalho)
        for l in linhas:
            if isinstance(l, dict):
                w.writerow([_fmt(l.get(c, "")) for c in cabecalho])
            else:
                w.writerow([_fmt(v) for v in l])


def _fmt(v):
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return f"{v:.2f}".replace(".", ",")  # padrão brasileiro, como um export de ERP
    return v


def gerar_historico(ate: date):
    produtos, clientes = _carregar_dimensoes()
    linhas = []
    d = INICIO_HISTORICO
    while d <= ate:
        linhas += [_foto(p, ate) for p in pedidos_do_dia(d, produtos, clientes)]
        d += timedelta(days=1)
    destino = ENTRADA / f"pedidos_historico_ate_{ate:%Y-%m-%d}.csv"
    _escrever(destino, COLUNAS, linhas)
    return destino, len(linhas)


def gerar_dia(d: date):
    produtos, clientes = _carregar_dimensoes()
    linhas = [_foto(p, d) for p in pedidos_do_dia(d, produtos, clientes)]
    # atualizações de pedidos antigos que mudaram de status hoje
    for k in range(1, 60):
        for p in pedidos_do_dia(d - timedelta(days=k), produtos, clientes):
            if p["data_expedicao"] == d or p["data_entrega"] == d:
                linhas.append(_foto(p, d))
    destino = ENTRADA / f"pedidos_{d:%Y-%m-%d}.csv"
    _escrever(destino, COLUNAS, linhas)
    return destino, len(linhas)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Gera dados fictícios de logística")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--historico", action="store_true", help="gera dimensões + histórico até ontem")
    g.add_argument("--dia", nargs="?", const=str(date.today()), help="gera o relatório de um dia (AAAA-MM-DD)")
    a = ap.parse_args()

    if a.dia:
        caminho, n = gerar_dia(date.fromisoformat(a.dia))
    else:
        gerar_dimensoes()
        caminho, n = gerar_historico(date.today() - timedelta(days=1))
    print(f"{n} linhas -> {caminho}")
