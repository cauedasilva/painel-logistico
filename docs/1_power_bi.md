# Montando o dashboard no Power BI

Tempo estimado: 1h30 a 2h na primeira vez.

## 1. Gerar os dados

Na pasta do projeto, dê dois cliques em `rotina_diaria.bat`. Na primeira vez ele cria cerca de 18 mil pedidos (maio/2025 até ontem) na pasta `dados/`:

| Arquivo | O que é |
|---|---|
| `fato_pedidos.csv` | um pedido por linha, com datas, status, valores e KPIs já calculados |
| `dim_centros.csv` | 4 centros de distribuição (SC, PR, SP) |
| `dim_transportadoras.csv` | 5 transportadoras |
| `dim_clientes.csv` | 180 clientes industriais em 16 estados |
| `dim_produtos.csv` | 48 produtos em 8 categorias |

## 2. Importar no Power BI (Power Query)

1. **Página Inicial → Transformar dados → Gerenciar parâmetros → Novo parâmetro**
   - Nome: `PastaDados`, tipo Texto
   - Valor: `C:\Users\caued\Dev\Projetos\painel-logistico\dados\` (com a barra no final)
2. **Nova fonte → Consulta nula**, renomeie para `fato_pedidos`, abra o **Editor avançado** e cole:

```m
let
    Fonte = Csv.Document(File.Contents(PastaDados & "fato_pedidos.csv"),
        [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    VaziosParaNulo = Table.TransformColumns(Cabecalhos, {}, each if _ = "" then null else _),
    Tipos = Table.TransformColumnTypes(VaziosParaNulo, {
        {"data_pedido", type date}, {"data_prometida", type date},
        {"data_expedicao", type date}, {"data_entrega", type date},
        {"quantidade", Int64.Type}, {"quantidade_entregue", Int64.Type},
        {"valor_mercadoria", type number}, {"peso_kg", type number}, {"custo_frete", type number},
        {"prazo_prometido_dias", Int64.Type}, {"tempo_expedicao_dias", Int64.Type},
        {"lead_time_dias", Int64.Type}, {"atraso_dias", Int64.Type},
        {"no_prazo", Int64.Type}, {"otif", Int64.Type}, {"atualizado_em", type datetime}
    }, "pt-BR")
in
    Tipos
```

3. Para cada dimensão, crie outra consulta nula com o mesmo começo, trocando o nome do arquivo (ex.: `dim_transportadoras.csv`). Nas dimensões, ajuste os tipos pelo próprio Power Query: **Transformar → Tipo de dados → Usando localidade → Português (Brasil)** nas colunas numéricas.
4. **Fechar e aplicar.**

> Para o currículo: cada passo acima aparece no painel **Etapas aplicadas**. Isso é Power Query de verdade (parâmetro, tratamento de nulos, tipagem com localidade).

## 3. Modelo (estrela)

**Modelagem → Nova tabela**, crie o calendário:

```dax
dCalendario =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2025, 5, 1 ), TODAY () + 30 ),
    "Ano", YEAR ( [Date] ),
    "Mês", FORMAT ( [Date], "mmm/yy" ),
    "AnoMes", YEAR ( [Date] ) * 100 + MONTH ( [Date] ),
    "Dia da semana", FORMAT ( [Date], "ddd" )
)
```

Selecione a coluna `Mês` → **Classificar por coluna → AnoMes**.

Na **Exibição de modelo**, ligue (1 → muitos):

| De | Para |
|---|---|
| `dCalendario[Date]` | `fato_pedidos[data_pedido]` |
| `dim_centros[cd_id]` | `fato_pedidos[cd_id]` |
| `dim_transportadoras[transportadora_id]` | `fato_pedidos[transportadora_id]` |
| `dim_clientes[cliente_id]` | `fato_pedidos[cliente_id]` |
| `dim_produtos[produto_id]` | `fato_pedidos[produto_id]` |

## 4. Medidas DAX

Crie uma tabela vazia `_Medidas` (Inserir dados → OK) e adicione:

```dax
Pedidos = COUNTROWS ( fato_pedidos )

Entregues = CALCULATE ( [Pedidos], NOT ISBLANK ( fato_pedidos[data_entrega] ) )

Entregues no prazo = CALCULATE ( [Pedidos], fato_pedidos[no_prazo] = 1 )

OTD % = DIVIDE ( [Entregues no prazo], [Entregues] )

OTIF % = DIVIDE ( CALCULATE ( [Pedidos], fato_pedidos[otif] = 1 ), [Entregues] )

Meta OTD = 0.85

OTD vs Meta (p.p.) = ( [OTD %] - [Meta OTD] ) * 100

OTD mês anterior = CALCULATE ( [OTD %], DATEADD ( dCalendario[Date], -1, MONTH ) )

Lead time médio (dias) = AVERAGE ( fato_pedidos[lead_time_dias] )

Tempo médio de expedição (dias) = AVERAGE ( fato_pedidos[tempo_expedicao_dias] )

Atraso médio dos atrasados (dias) =
CALCULATE ( AVERAGE ( fato_pedidos[atraso_dias] ), fato_pedidos[no_prazo] = 0 )

Faturamento = SUM ( fato_pedidos[valor_mercadoria] )

Frete total = SUM ( fato_pedidos[custo_frete] )

Frete % do faturamento = DIVIDE ( [Frete total], [Faturamento] )

Frete por kg = DIVIDE ( [Frete total], SUM ( fato_pedidos[peso_kg] ) )

Em aberto = CALCULATE ( [Pedidos], ISBLANK ( fato_pedidos[data_entrega] ) )

Em aberto atrasados =
CALCULATE ( [Pedidos], ISBLANK ( fato_pedidos[data_entrega] ), fato_pedidos[atraso_dias] > 0 )

Cor OTD = IF ( [OTD %] >= [Meta OTD], "#2E7D32", "#C62828" )

Última atualização = "Atualizado em " & FORMAT ( MAX ( fato_pedidos[atualizado_em] ), "dd/mm/yyyy hh:mm" )
```

Formate `OTD %`, `OTIF %`, `Meta OTD` e `Frete % do faturamento` como **Porcentagem** (1 casa decimal).

## 5. Páginas sugeridas

**Página 1 – Visão geral**
- Cartões: OTD %, OTIF %, Lead time médio, Frete % do faturamento, Em aberto atrasados
- Gráfico de linhas: OTD % por Mês, com linha constante em 85% (painel **Análise → Linha constante**)
- Mapa preenchido: OTD % por `dim_clientes[uf]`
- Barras: OTD % por transportadora, cor pela medida `Cor OTD` (Formatar → Barras → Cores → fx)
- Segmentações: Mês, Centro, Categoria
- Caixa de texto com a medida `Última atualização`

**Página 2 – Transportadoras**
- Matriz: transportadora × Mês com OTD % e formatação condicional
- Dispersão: eixo X = Frete por kg, eixo Y = OTD %, detalhes = transportadora (mostra quem é barato x confiável)

**Página 3 – Centros de distribuição**
- Colunas: Tempo médio de expedição por Mês, legenda = centro
- Matriz: centro × categoria com OTD %

**Página 4 – Pedidos em aberto**
- Tabela filtrada por `status_logistico` contendo "atrasado": pedido, cliente, UF, transportadora, data prometida, atraso_dias (barras de dados)

## 6. O que os dados escondem (para você "descobrir" e contar no LinkedIn)

Os dados foram gerados com problemas propositais, como numa operação real:

- **Crise de uma transportadora**: a Expresso Atlântico (TR02) cai de ~85% para ~60% de OTD em **março e abril de 2026** e depois se recupera.
- **Gargalo de expedição**: o CD Pomerode (CD01) atrasa a expedição em **outubro e novembro** (pico de demanda). Isso derruba o OTD do mês, e é o que dispara o alerta agora.
- **Barato sai caro**: a TransBrasil Fracionados (TR04) tem o menor frete por kg e o pior OTD.
- **Norte e Nordeste** têm lead time bem maior e usam mais frete aéreo.

Encontrar isso no dashboard e escrever "o que eu recomendaria" é o que transforma o projeto de exercício em case.
