"""
ETL do painel logístico.

1. Lê todos os relatórios novos em entrada/ (pedidos_*.csv)
2. Valida cada linha (datas, números, chaves) e separa as inválidas em logs/rejeitados.csv
3. Faz upsert por pedido_id em dados/fato_pedidos.csv (status mais recente vence)
4. Calcula campos de negócio: lead time, atraso, no prazo, OTIF, status logístico
5. Move os arquivos processados para entrada/processados/
6. Gera dados/resumo_kpis.json (últimos 30 dias) com um alerta se o OTD ficar abaixo da meta

Código de saída: 0 = OK, 2 = OK mas com alerta de KPI (útil para o Power Automate decidir se manda e-mail).
"""
import csv
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENTRADA = BASE / "entrada"
PROCESSADOS = ENTRADA / "processados"
DADOS = BASE / "dados"
LOGS = BASE / "logs"
FATO = DADOS / "fato_pedidos.csv"
RESUMO = DADOS / "resumo_kpis.json"

META_OTD = 0.85  # 85% dos pedidos entregues no prazo
JANELA_DIAS = 30

ORDEM_STATUS = {"AGUARDANDO_EXPEDICAO": 0, "EM_TRANSITO": 1, "ENTREGUE": 2}

COLUNAS_FATO = [
    "pedido_id", "data_pedido", "data_prometida", "data_expedicao", "data_entrega", "status_sistema",
    "status_logistico", "cd_id", "transportadora_id", "cliente_id", "produto_id", "quantidade",
    "quantidade_entregue", "valor_mercadoria", "peso_kg", "custo_frete", "prazo_prometido_dias",
    "tempo_expedicao_dias", "lead_time_dias", "atraso_dias", "no_prazo", "otif", "atualizado_em",
]


def log(msg):
    LOGS.mkdir(exist_ok=True)
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(linha)
    with open(LOGS / "processamento.log", "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def ler_csv(caminho):
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def num(v):
    return float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(v)


def data_ou_none(v):
    return date.fromisoformat(v) if v else None


def carregar_chaves():
    chaves = {}
    for nome, col in (("dim_centros.csv", "cd_id"), ("dim_transportadoras.csv", "transportadora_id"),
                      ("dim_clientes.csv", "cliente_id"), ("dim_produtos.csv", "produto_id")):
        chaves[col] = {l[col] for l in ler_csv(DADOS / nome)}
    return chaves


def validar(l, chaves):
    erros = []
    try:
        dp = date.fromisoformat(l["data_pedido"])
        dpr = date.fromisoformat(l["data_prometida"])
        dexp = data_ou_none(l["data_expedicao"])
        dent = data_ou_none(l["data_entrega"])
        if dpr < dp:
            erros.append("data_prometida antes do pedido")
        if dexp and dexp < dp:
            erros.append("expedição antes do pedido")
        if dent and (not dexp or dent < dexp):
            erros.append("entrega sem expedição ou antes dela")
    except ValueError as e:
        erros.append(f"data inválida ({e})")
    for col in ("quantidade", "valor_mercadoria", "peso_kg", "custo_frete"):
        try:
            if num(l[col]) < 0:
                erros.append(f"{col} negativo")
        except ValueError:
            erros.append(f"{col} não numérico")
    for col, validas in chaves.items():
        if l[col] not in validas:
            erros.append(f"{col} desconhecido: {l[col]}")
    if l["status_sistema"] not in ORDEM_STATUS:
        erros.append(f"status desconhecido: {l['status_sistema']}")
    return erros


def enriquecer(l, hoje):
    dp = date.fromisoformat(l["data_pedido"])
    dpr = date.fromisoformat(l["data_prometida"])
    dexp = data_ou_none(l["data_expedicao"])
    dent = data_ou_none(l["data_entrega"])
    l["prazo_prometido_dias"] = (dpr - dp).days
    l["tempo_expedicao_dias"] = (dexp - dp).days if dexp else ""
    if dent:
        l["lead_time_dias"] = (dent - dp).days
        l["atraso_dias"] = max(0, (dent - dpr).days)
        l["no_prazo"] = 1 if dent <= dpr else 0
        completo = int(l["quantidade_entregue"] or 0) >= int(l["quantidade"])
        l["otif"] = 1 if (l["no_prazo"] == 1 and completo) else 0
        l["status_logistico"] = "Entregue no prazo" if l["no_prazo"] else "Entregue com atraso"
    else:
        atrasado = hoje > dpr
        l["lead_time_dias"] = ""
        l["atraso_dias"] = (hoje - dpr).days if atrasado else 0
        l["no_prazo"] = ""
        l["otif"] = ""
        base = "Em trânsito" if dexp else "Aguardando expedição"
        l["status_logistico"] = f"{base} - atrasado" if atrasado else base
    return l


def kpis(linhas, hoje):
    inicio = hoje - timedelta(days=JANELA_DIAS)
    entregues = [l for l in linhas if l["data_entrega"] and date.fromisoformat(l["data_entrega"]) > inicio]
    abertos = [l for l in linhas if not l["data_entrega"]]
    atrasados_abertos = [l for l in abertos if "atrasado" in l["status_logistico"]]
    n = len(entregues)
    otd = sum(int(l["no_prazo"]) for l in entregues) / n if n else 0
    otif = sum(int(l["otif"]) for l in entregues) / n if n else 0
    lead = sum(int(l["lead_time_dias"]) for l in entregues) / n if n else 0
    frete = sum(num(l["custo_frete"]) for l in entregues)
    valor = sum(num(l["valor_mercadoria"]) for l in entregues)

    # pior transportadora no período (mín. 20 entregas)
    por_tr = {}
    for l in entregues:
        t = por_tr.setdefault(l["transportadora_id"], [0, 0])
        t[0] += 1
        t[1] += int(l["no_prazo"])
    ranking = sorted(((v[1] / v[0], k, v[0]) for k, v in por_tr.items() if v[0] >= 20))
    pior = {"transportadora_id": ranking[0][1], "otd": round(ranking[0][0], 4)} if ranking else None

    alerta = n > 0 and otd < META_OTD
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "periodo": f"{inicio + timedelta(days=1)} a {hoje}",
        "entregas_no_periodo": n,
        "otd": round(otd, 4),
        "otif": round(otif, 4),
        "meta_otd": META_OTD,
        "lead_time_medio_dias": round(lead, 2),
        "frete_sobre_valor": round(frete / valor, 4) if valor else 0,
        "pedidos_em_aberto": len(abertos),
        "pedidos_em_aberto_atrasados": len(atrasados_abertos),
        "pior_transportadora": pior,
        "alerta": alerta,
        "mensagem": (f"ALERTA: OTD dos últimos {JANELA_DIAS} dias em {otd:.1%}, abaixo da meta de {META_OTD:.0%}."
                     if alerta else f"OTD dos últimos {JANELA_DIAS} dias em {otd:.1%} (meta {META_OTD:.0%})."),
    }


def main():
    arquivos = sorted(ENTRADA.glob("pedidos_*.csv"), key=lambda p: (0 if "historico" in p.name else 1, p.name))
    base = {l["pedido_id"]: l for l in ler_csv(FATO)} if FATO.exists() else {}
    if not arquivos:
        log("Nenhum arquivo novo em entrada/.")
    chaves = carregar_chaves()
    hoje = date.today()
    rejeitados = []
    for arq in arquivos:
        novos = atualizados = ignorados = 0
        for l in ler_csv(arq):
            erros = validar(l, chaves)
            if erros:
                rejeitados.append({**l, "arquivo": arq.name, "erros": " | ".join(erros)})
                continue
            atual = base.get(l["pedido_id"])
            if atual and ORDEM_STATUS[atual["status_sistema"]] > ORDEM_STATUS[l["status_sistema"]]:
                ignorados += 1  # nunca regredir status (arquivo antigo processado depois)
                continue
            novos += atual is None
            atualizados += atual is not None
            l["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
            base[l["pedido_id"]] = l
        PROCESSADOS.mkdir(parents=True, exist_ok=True)
        shutil.move(str(arq), PROCESSADOS / arq.name)
        log(f"{arq.name}: {novos} novos, {atualizados} atualizados, {ignorados} ignorados")

    # recalcula campos de todos (status "atrasado" muda com o passar dos dias)
    linhas = [enriquecer(dict(l), hoje) for l in sorted(base.values(), key=lambda x: x["pedido_id"])]
    DADOS.mkdir(exist_ok=True)
    tmp = FATO.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_FATO, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    tmp.replace(FATO)  # troca atômica: o Power BI nunca lê um arquivo pela metade

    if rejeitados:
        LOGS.mkdir(exist_ok=True)
        caminho = LOGS / "rejeitados.csv"
        novo = not caminho.exists()
        with open(caminho, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rejeitados[0].keys()), delimiter=";")
            if novo:
                w.writeheader()
            w.writerows(rejeitados)
        log(f"{len(rejeitados)} linhas rejeitadas (ver logs/rejeitados.csv)")

    resumo = kpis(linhas, hoje)
    RESUMO.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Base com {len(linhas)} pedidos. {resumo['mensagem']}")
    return 2 if resumo["alerta"] else 0


if __name__ == "__main__":
    sys.exit(main())
