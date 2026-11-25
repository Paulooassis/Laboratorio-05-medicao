# 5. Revisão do piloto e tamanho da amostra (Lab05S02)

Este documento fecha os ajustes A1, A3 e A4 do piloto ([docs/04, seção 4.6](04-coleta-piloto.md#46-problemas-encontrados-e-ajustes-no-plano)) antes da coleta completa. São três decisões:

| # | Problema do piloto | Decisão |
|---|---|---|
| D1 | Deriva temporal (P1) | Protocolo de ambiente **conferido pelo script**, ordem em **blocos completos aleatorizados** e **critério de aceite** automático para a deriva |
| D2 | Efeito teto da CPU (P3) | Nova condição de **carga fixa** (50.000 ops/s, abaixo da saturação). H-5 passa a ser testada só nela |
| D3 | Poder insuficiente (P4) | **n = 50 execuções por tratamento**, com o mini-piloto como portão de entrada |

Os números abaixo saem dos dados do piloto (`data/processed/piloto_validado.csv`) e dos scripts deste repositório. Os arquivos em `results/piloto/` ficam como estavam na S01 (versão dos scripts daquela sprint).

## 5.1 D1: deriva temporal

### Quanto do ruído do piloto vem da deriva

As 3 execuções do episódio de 17:28–17:29 UTC (ordem 17–19, [docs/04, seção 4.5](04-coleta-piloto.md#45-diagnóstico-de-deriva-temporal-resultspilotoordemmd)) explicam a maior parte da variabilidade de vazão e latência p50. Maior CV entre Redis e Valkey em cada condição:

| Métrica | Condição | CV com todas (%) | CV sem as 3 execuções (%) | CV robusto (1,4826·MAD/mediana, %) |
|---|---|---|---|---|
| M1 Vazão | GET p=1 | 8,3 | 4,1 | 5,9 |
| | GET p=16 | 11,5 | 5,1 | 6,2 |
| | SET p=1 | 8,0 | 3,6 | 4,0 |
| | SET p=16 | 4,9 | 4,9 | 3,2 |
| M2 Latência p50 | GET p=1 | 8,1 | 1,9 | 3,2 |
| | GET p=16 | 12,5 | 5,2 | 6,4 |
| | SET p=1 | 7,5 | 1,8 | 1,6 |
| | SET p=16 | 3,7 | 3,7 | 3,0 |
| M3 Latência p99 | GET p=1 | 10,8 | 8,4 | 2,7 |
| | GET p=16 | 23,4 | 10,3 | 14,4 |
| | SET p=1 | 9,2 | 8,2 | 9,1 |
| | SET p=16 | 16,3 | 16,3 | 11,6 |

Sem a deriva, o CV de M1 e M2 cai de 8–12% para **2–5%**. Então o caminho é tirar a deriva do ambiente, e não compensar o ruído só com mais execuções. A cauda (M3) continua com 8–16%, porque é ruidosa por natureza.

### O que foi decidido

1. **Protocolo de ambiente, agora conferido.** Coleta na tomada, governador `performance`, aplicativos fechados e máquina sem uso. O `coleta_experimento.py` lê `/sys` antes de começar e **não roda** se a máquina estiver na bateria ou com outro governador. Foi assim que o piloto rodou (`powersave`, na bateria). A opção `--ignorar-ambiente` existe para testes e fica registrada em `metadados.json` (`verificacao_ambiente`).
2. **Ordem em blocos completos aleatorizados** (`--ordem blocos`, o novo padrão). O bloco *r* tem a repetição *r* de cada um dos 12 tratamentos, em ordem sorteada, e os blocos rodam em sequência (~6,5 min cada). Uma deriva lenta (bateria, temperatura) fica distribuída igualmente entre os tratamentos, e não só "em média", como no sorteio livre. No piloto, o sorteio livre pôs as três execuções afetadas no Redis e deixou as três últimas do Valkey no fim da coleta. O piloto continua reproduzível com `--ordem sorteio --taxa-fixa 0`. Um teste (`tests/test_coleta_plano.py`) confere que o plano gerado é igual ao de `data/raw/piloto/metadados.json`.
3. **Critério de aceite da deriva**, calculado pelo `diagnostico_ordem.py` (seção "Critério de aceite" do `ordem.md`). A coleta é **APROVADA** se:
   - nenhuma execução tiver vazão 10% ou mais abaixo da mediana do seu tratamento; e
   - nenhuma tendência de M1–M3 ao longo da coleta, **com todas as execuções juntas**, tiver |ρ| > 0,3 **e** p < 0,05.

   Isso **revisa** o critério proposto no docs/04 ("nenhuma tendência com |ρ| > 0,3"). Com cerca de 20 execuções por software, |ρ| = 0,3 aparece por acaso: o limiar de significância para n = 20 é |ρ| ≈ 0,44, e são 9 correlações. Numa simulação (2.000 coletas do tamanho do mini-piloto, 36 execuções), o critério antigo reprova **79%** das coletas **sem deriva nenhuma**. O novo reprova 13% e ainda detecta 97% das coletas com deriva moderada. A tendência por software continua na tabela, mas só como informação.
4. **Nada é removido da análise principal.** A sensibilidade (diferença com e sem as execuções sinalizadas) continua no `ordem.md` e entra nas ameaças à validade.

Rodado sobre o piloto, o critério dá **REPROVADO** (3 execuções sinalizadas na ordem 17–19), como esperado.

## 5.2 D2: efeito teto da CPU

Com 200 conexões e sem limite de taxa, os dois servidores ficam em ~101% de um núcleo (CV 0,2%). M5 mostra que o servidor está no limite, mas não quanto ele gasta por trabalho feito. As duas saídas pensadas no piloto:

| Opção | Avaliação |
|---|---|
| Métrica derivada "CPU por 100 mil ops" (`cpu_medio_pct / ops_s × 10⁵`) | **Rejeitada.** Com a CPU constante no teto, ela é só 1/vazão multiplicada por uma constante. No piloto, a correlação com 1/M1 é **0,9994 a 0,9999** nas 4 condições. Repetiria H-1 com outro nome e não mediria eficiência de CPU (validade de construto). |
| Condição de **carga fixa** abaixo da saturação | **Adotada.** Com a mesma vazão imposta aos dois servidores, a CPU vira diretamente "quanto cada um gasta para fazer o mesmo trabalho". |

### Como fica o desenho

- **4 tratamentos novos:** 2 softwares × 2 comandos (`GET`, `SET`), *pipeline* 1, com `memtier_benchmark --rate-limiting=250` (por conexão) × 200 conexões = **50.000 ops/s no total**. São ~43% da vazão saturada com *pipeline* 1 no piloto (114–118 mil ops/s), então os dois servidores dão conta da taxa com folga. Opção `--taxa-fixa` no coletor (0 tira a condição).
- **H-5 (CPU) é testada só na carga fixa** (2 testes: `GET` e `SET`). Na carga saturada, M5 fica na estatística descritiva, como checagem de que o servidor saturou.
- **Família do Holm:** M1–M4 × 4 condições saturadas + M5 × 2 de carga fixa = **18 testes** (eram 20). O `analise.py` monta essa família sozinho quando a coleta tem carga fixa. Sem ela (piloto), mantém os 20 testes de antes.
- **Nova regra de validação V10:** uma execução de carga fixa com vazão fora de ±5% da taxa é descartada. Se o servidor não atingiu a taxa, a CPU deixa de ser comparável.
- Na carga fixa, M1 é a própria taxa (imposta), então não é uma resposta e não é testada. M2–M4 ficam na descritiva.

**Teste de fumaça (só funcional, não é dado do estudo).** Uma rodada curta (1 repetição, 6 s) num Mac com Docker (Colima, 2 CPUs) confirmou o encadeamento completo (coleta → validação → análise → diagnóstico). Nas 4 execuções de carga fixa, a vazão ficou entre **49.985 e 49.999 ops/s**, e a CPU do servidor entre **33% e 38%**, longe do teto (81–84% nas execuções saturadas daquela máquina). Os dados foram descartados: a máquina do estudo é outra.

## 5.3 D3: tamanho da amostra

### Poder em função do CV

Simulação do Mann-Whitney U (`simulacao_poder.py`, tabela "Cenários"), efeito de 5% na mediana, α = 0,05 / 18 = 0,0028 (pior caso do Holm), 2.000 réplicas:

| CV (%) | n=20 | n=30 | n=40 | **n=50** | n=60 | n=80 | n=100 |
|---|---|---|---|---|---|---|---|
| 3 | 0,95 | 1,00 | 1,00 | **1,00** | 1,00 | 1,00 | 1,00 |
| 4 | 0,67 | 0,93 | 0,98 | **1,00** | 1,00 | 1,00 | 1,00 |
| 5 | 0,39 | 0,69 | 0,87 | **0,95** | 0,97 | 1,00 | 1,00 |
| 6 | 0,22 | 0,47 | 0,68 | **0,81** | 0,89 | 0,97 | 1,00 |
| 8 | 0,10 | 0,20 | 0,33 | **0,46** | 0,60 | 0,77 | 0,88 |
| 10 | 0,05 | 0,12 | 0,17 | **0,25** | 0,33 | 0,48 | 0,63 |

### Decisão: n = 50 por tratamento

- **Por que 50.** Sem a deriva, o pior CV de M1 e M2 no piloto é **5,2%** (robusto: 6,4%). Com n = 50, o poder é 0,95 a CV de 5% e ainda passa de 0,8 até **CV de 6%**. Com n = 30, só haveria poder ≥ 0,8 até CV de 4%, sem margem para o que o piloto mostrou.
- **Por que não mais.** O custo cresce linearmente. São 12 tratamentos × (50 + 1 de aquecimento) = **612 execuções**, que levam cerca de **5 h 35 min** a 32,8 s por execução (o ritmo do piloto). Com n = 80 seriam ~9 h, o que obriga a dividir a coleta em vários dias e traz um efeito de dia. Se o CV real passar de 6%, o problema é o ambiente (D1), e mais execuções não resolvem.
- **Hipóteses-alvo do poder:** H-1 (M1) e H-2 (M2) nas 4 condições saturadas, H-4 (M4) e H-5 (M5 na carga fixa). M4 e M5 têm CV < 0,5% e passam com folga.
- **H-3 (latência p99) é testada, mas não é alvo de poder.** A cauda tem CV de 8 a 16% mesmo sem a deriva, e o n para detectar 5% passaria de 100 por tratamento. Se H-3 não for rejeitada, isso **não** é evidência de igualdade. Essa limitação vai para as ameaças à validade (tarefa 15), com o poder alcançado informado no `poder.md`.
- **Família menor do Holm (18 testes).** Já reflete D2. Restringir ainda mais a família (por exemplo, só H-1 a H-3) não foi preciso.

### Portão: mini-piloto

O n = 50 vale se o mini-piloto confirmar que o ambiente ficou limpo. Ele roda **na máquina do estudo**, na tomada e em `performance`:

```bash
python3 scripts/coleta_experimento.py --coleta minipiloto --repeticoes 3   # 48 execuções, ~26 min
python3 scripts/validacao_dados.py   --coleta minipiloto
python3 scripts/diagnostico_ordem.py --coleta minipiloto   # results/minipiloto/ordem.md -> "Critério de aceite"
python3 scripts/simulacao_poder.py   --coleta minipiloto   # results/minipiloto/poder.md -> "Decisão"
```

| Resultado do mini-piloto | Ação |
|---|---|
| `ordem.md` **APROVADO** e `poder.md` **APROVADO** (n = 50 dá poder ≥ 0,8 nas hipóteses-alvo) | Rodar a coleta completa: `python3 scripts/coleta_experimento.py --coleta completa --repeticoes 50` |
| Algum dos dois **REPROVADO** | Achar a fonte do ruído (processos em segundo plano, temperatura, governador), corrigir e repetir o mini-piloto. **Não** aumentar o n para compensar |

Com 3 execuções por tratamento, o CV do mini-piloto é uma estimativa grosseira. O portão serve para pegar um ambiente claramente ruim (CV de 8% ou mais, como no piloto), não para afinar o n. Os dados do mini-piloto não entram na análise final.

## 5.4 O que mudou nos scripts

| Script | Mudança |
|---|---|
| `coleta_experimento.py` | Carga fixa (`--taxa-fixa`, padrão 50.000), ordem em blocos (`--ordem`, padrão `blocos`), checagem de ambiente (`--ignorar-ambiente`), colunas `bloco` e `taxa` no CSV |
| `validacao_dados.py` | Tratamento passa a incluir a `taxa`. Nova regra V10 (carga fixa fora de ±5% da taxa) |
| `analise.py` | Condição = comando × *pipeline* × carga. Família de 18 testes, com H-5 só na carga fixa |
| `diagnostico_ordem.py` | Seção "Critério de aceite" (APROVADO/REPROVADO), opção `--rho-max` |
| `simulacao_poder.py` | n planejado = 50 (`--n-planejado`), α para 18 testes, grade de n até 100, tabela de cenários por CV (`poder_cenarios.csv`) e decisão sobre as hipóteses-alvo |

Coletas sem a coluna `taxa`, como o piloto, são lidas como carga saturada. Por isso todos os scripts continuam rodando sobre os dados da S01.
