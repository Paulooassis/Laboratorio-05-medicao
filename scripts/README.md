# Scripts

| Script | O que faz | Dependências |
|---|---|---|
| [`coleta_impacto.py`](#coleta_impactopy-evidências-de-impacto) | Coleta os números públicos de impacto (Docker Hub, PyPI, npm etc.) | biblioteca padrão |
| [`coleta_experimento.py`](#coleta_experimentopy-execuções-do-experimento) | Roda as execuções do experimento Redis × Valkey | biblioteca padrão + Docker |
| [`validacao_dados.py`](#validacao_dadospy-validação-dos-dados) | Valida os dados coletados (nulos, duplicados, fora do esperado) | `requirements.txt` |
| [`analise.py`](#analisepy-análise) | Estatística descritiva, gráficos e testes de hipótese | `requirements.txt` |
| [`simulacao_poder.py`](#simulacao_poderpy-poder-e-erro-tipo-i) | Simula erro tipo I e poder com a variância do piloto | `requirements.txt` |
| [`diagnostico_ordem.py`](#diagnostico_ordempy-deriva-temporal) | Verifica se o desempenho mudou ao longo da coleta (deriva, episódios de interferência) e aplica o critério de aceite | `requirements.txt` |

Fluxo completo (Linux/macOS; no Windows troque `python3` por `py`):

```bash
pip install -r requirements.txt
python3 scripts/coleta_experimento.py --coleta piloto --repeticoes 5 --ordem sorteio --taxa-fixa 0   # ~26 min
python3 scripts/validacao_dados.py   --coleta piloto
python3 scripts/analise.py           --coleta piloto
python3 scripts/simulacao_poder.py   --coleta piloto
python3 scripts/diagnostico_ordem.py --coleta piloto
```

As regras de validação e as funções estatísticas têm testes em [`tests/`](../tests/): `pip install -r requirements-dev.txt` e `python3 -m pytest`.

---

## `coleta_impacto.py`: evidências de impacto

Consulta fontes públicas e salva, em CSV e JSON, os números que comprovam que o **Redis** e o **Valkey** são reais, estão em operação e têm alto impacto.

```bash
python3 scripts/coleta_impacto.py             # salva em data/impacto/
python3 scripts/coleta_impacto.py --saida outra/pasta
```

Usa só a biblioteca padrão do Python (3.9+). Para aumentar o limite da API do GitHub, defina a variável `GITHUB_TOKEN` (opcional).

### Saída

São gerados dois arquivos em `data/impacto/`, com a data da coleta no nome:

- `impacto_AAAA-MM-DD.csv`: uma linha por número coletado.
- `impacto_AAAA-MM-DD.json`: os mesmos registros, mais metadados da coleta e a lista de erros (se alguma fonte falhar, as outras continuam).

| Coluna | Conteúdo |
|---|---|
| `data_coleta` | Data e hora da coleta (ISO 8601, com fuso) |
| `software` | `Redis` ou `Valkey` |
| `criterio` | `real`, `em_operacao` ou `alto_impacto` |
| `fonte` | Nome da fonte (Docker Hub, GitHub API, PyPI Stats, npm, Homebrew, endoflife.date, DB-Engines) |
| `metrica` | Nome do número coletado |
| `valor` | O número (ou a versão/data) |
| `unidade` | Unidade ou escala do valor |
| `url` | URL exata consultada (fonte do número) |
| `observacao` | Ressalvas sobre o número |

### Fontes consultadas

| Fonte | O que coleta | Critério |
|---|---|---|
| Docker Hub API | *pulls*, estrelas e última atualização das imagens oficiais | alto impacto / em operação |
| GitHub API | estrelas, forks e último *release* (só como evidência de adoção, sem minerar o repositório) | real / em operação |
| PyPI Stats | downloads mensais dos clientes Python `redis` e `valkey` | alto impacto |
| npm | downloads mensais de `redis`, `ioredis`, `iovalkey` e `@valkey/valkey-glide` | alto impacto |
| Homebrew | versão estável e instalações em 30 e 365 dias | em operação / alto impacto |
| endoflife.date | ciclos de versão mantidos e último *release* | em operação |
| DB-Engines | posição no ranking geral e de *key-value stores* (escala ordinal) | alto impacto |

### Regras de ética

- No máximo **1 requisição por segundo** (pausa mínima de 1,1 s entre chamadas). Se uma fonte responder `429`, o script espera e tenta de novo.
- Apenas endpoints públicos. O `robots.txt` do DB-Engines permite o acesso.
- *User-Agent* genérico, sem dados pessoais dos integrantes. Nenhum dado pessoal é coletado.

---

## `coleta_experimento.py`: execuções do experimento

Orquestra o desenho descrito em [`docs/03`](../docs/03-metricas-hipoteses-planos.md): fatorial 2 (software) × 2 (comando) × 2 (*pipeline*) em carga saturada, mais 2 (software) × 2 (comando) em **carga fixa** (*pipeline* 1, `--taxa-fixa` ops/s), num total de 12 tratamentos ([`docs/05`](../docs/05-revisao-piloto-tamanho-amostra.md)). Cada execução é uma unidade experimental independente:

1. sobe um **contêiner novo** do servidor (`redis:8.10.3` ou `valkey/valkey:9.1.3`), com CPUs fixadas;
2. popula 100.000 chaves de 256 bytes;
3. roda a carga com o `memtier_benchmark` (4 *threads* × 50 conexões, 30 s; na carga fixa, com `--rate-limiting`), amostrando a CPU do servidor com `docker stats`;
4. lê `INFO memory` e `INFO server` (confere a versão);
5. remove o contêiner.

```bash
python3 scripts/coleta_experimento.py --coleta minipiloto --repeticoes 3    # 48 execuções, ~26 min
python3 scripts/coleta_experimento.py --coleta completa   --repeticoes 50   # 612 execuções, ~5 h 35 min
python3 scripts/coleta_experimento.py --coleta x --repeticoes 50 --dry-run  # só mostra a ordem sorteada
python3 scripts/coleta_experimento.py --coleta piloto --repeticoes 5 --ordem sorteio --taxa-fixa 0  # refaz o plano do piloto
```

**Antes de começar** (antes de baixar imagens), o script confere em `/sys` (Linux) se a máquina está na tomada e com o governador de CPU `performance`. Se não estiver, ele para. Só contam como tomada as fontes do tipo `Mains`, porque a bateria de um mouse sem fio não vale. Se não conseguir ler alguma das duas informações, avisa qual.

| Opção | Padrão | Significado |
|---|---|---|
| `--coleta` | `piloto` | Nome da coleta (pasta em `data/raw/` e prefixo do CSV) |
| `--repeticoes` | 5 | Execuções medidas por tratamento |
| `--duracao` | 30 | Segundos de carga por execução |
| `--semente` | 20261119 | Semente do sorteio da ordem (fica registrada nos metadados) |
| `--cpus-servidor` / `--cpus-cliente` | `0,4` / `1-3,5-7` | `--cpuset-cpus` de cada contêiner. Ajuste à topologia da sua máquina (`lscpu -e`) |
| `--sem-aquecimento` | — | Não roda a execução de aquecimento (descartada) de cada tratamento |
| `--ordem` | `blocos` | `blocos`: o bloco *r* tem a repetição *r* de cada tratamento, em ordem sorteada. `sorteio`: todas as execuções sorteadas de uma vez (piloto) |
| `--taxa-fixa` | 50000 | ops/s no total da carga fixa (múltiplo de 200, porque o limite do memtier é por conexão). `0` tira essa condição |
| `--ignorar-ambiente` | — | Coleta mesmo fora da tomada ou do governador `performance` (fica em `metadados.json`, `verificacao_ambiente`) |
| `--tentativas` | 3 | Quantas vezes repetir uma execução inválida |

### Saída

| Arquivo | Conteúdo |
|---|---|
| `data/raw/<coleta>/metadados.json` | Semente, plano sorteado, parâmetros, CPU, RAM, SO, governador de CPU, perfil de energia, se está na tomada, versão do Docker e do memtier, *digests* das imagens, commit do Git |
| `data/raw/<coleta>/<run_id>.json` | Saída bruta do `memtier_benchmark` |
| `data/raw/<coleta>/<run_id>_meta.json` | Amostras de CPU (todas e as da janela usada), `INFO memory` e `INFO server` |
| `data/raw/<coleta>/coleta.log` | Log da coleta, com os erros |
| `data/processed/<coleta>_execucoes.csv` | Uma linha por execução (colunas abaixo) |

Colunas principais do CSV: `run_id`, `ordem`, `bloco`, `tentativa`, `aquecimento`, `software`, `versao`, `versao_reportada`, `comando`, `pipeline`, `taxa` (ops/s da carga fixa; 0 = saturada), `repeticao`, `inicio`, `fim` (timestamps UTC), `ops_s` (M1), `lat_p50_ms` (M2), `lat_p99_ms` (M3), `lat_media_ms`, `lat_p999_ms`, `mem_rss_mib` (M4), `mem_usada_mib`, `cpu_medio_pct` (M5), `cpu_amostras`, `erros_conexao`, `misses_s`, `status` (`ok`/`erro`) e `erro`.

**CPU (M5).** O `docker stats` é lido em modo contínuo. Ficam só as leituras com pelo menos 0,75 s de distância (ele repete cada leitura) e dentro da janela da carga informada pelo memtier (`Start time` e `Finish time`), descartando os 2 s iniciais (conexões abrindo).

**Erros.** Uma falha (contêiner que não sobe, erro de conexão, vazão zero, versão diferente da esperada) não para a coleta: é registrada no log e no CSV com `status=erro`, e a execução é repetida.

**Ética.** Toda a carga é gerada e recebida dentro da máquina do grupo, numa rede Docker local. Nenhum sistema de terceiros é acessado e não há dados pessoais (chaves e valores são sintéticos).

---

## `validacao_dados.py`: validação dos dados

```bash
python3 scripts/validacao_dados.py --coleta piloto
```

Uma execução é **descartada** se violar qualquer regra:

| Regra | Descarta quando |
|---|---|
| V1 | `status` diferente de `ok` |
| V2 | é execução de aquecimento |
| V3 | alguma métrica M1–M5 é nula |
| V4 | `run_id` duplicado |
| V5 | tratamento + repetição duplicado entre as válidas |
| V6 | valor fora do esperado: vazão ≤ 0, latência ≤ 0, p50 > p99 > p99,9 fora de ordem, erro de conexão, memória ≤ 0, CPU fora de [0, 100 × nº de CPUs do servidor] |
| V7 | versão reportada pelo servidor ≠ versão do tratamento |
| V8 | `GET` com *misses* (base mal populada) |
| V9 | menos amostras de CPU que metade da janela |
| V10 | carga fixa com vazão fora de ±5% da taxa (a carga não foi a planejada) |

O tratamento inclui a carga (`taxa`). Coletas sem essa coluna (piloto) são lidas como carga saturada. *Outliers* (fora de Q1 − 1,5·IQR / Q3 + 1,5·IQR dentro do tratamento) **não são removidos**, só sinalizados na coluna `outliers`.

Saída: `data/processed/<coleta>_validado.csv` (todas as linhas + `valido`, `motivo_descarte`, `outliers`) e o resumo em `results/<coleta>/validacao.md` e `.json` (total, válidas, descartadas, motivos, válidas por tratamento).

---

## `analise.py`: análise

```bash
python3 scripts/analise.py --coleta piloto
```

Lê só as execuções válidas e gera em `results/<coleta>/`:

- `descritiva.csv` / `.md`: n, média, mediana, DP, CV, mín, máx, Q1, Q3, IQR e IC 95% da mediana (*bootstrap*, 10.000 reamostragens) por tratamento e métrica;
- `testes.csv` / `.md`: Shapiro-Wilk em cada grupo → t de Welch ou Mann-Whitney U, g de Hedges ou δ de Cliff, diferença % das medianas e p ajustado por Holm-Bonferroni. Com carga fixa, a família tem 18 testes: M1–M4 nas 4 condições saturadas e M5 só na carga fixa. Sem ela (piloto), são 20 testes (M1–M5 × 4);
- `boxplot_<métrica>.png`: *boxplot* com os pontos, por condição;
- `interacao_vazao.png`: gráfico de interação software × *pipeline* (H-6).

---

## `simulacao_poder.py`: poder e erro tipo I

```bash
python3 scripts/simulacao_poder.py --coleta minipiloto [--replicas 2000] [--efeito 0.05] [--n-planejado 50]
```

Reaproveita o Lab04: simula o Mann-Whitney com dados log-normais que têm o CV observado na coleta (o maior entre Redis e Valkey). Mede o erro tipo I (efeito 0, n planejado) e o poder para detectar 5% de diferença com n de 5 a 100, em α = 0,05 e em α = 0,05/m, o pior caso do Holm. A família é a mesma do `analise.py`: m = 18 com carga fixa e m = 20 sem ela (piloto). Só entram as combinações que a análise testa. A tabela de **cenários** dá o poder numa grade de CVs, sem depender da coleta. A seção **Decisão** diz se o n planejado dá poder ≥ 0,8 nas hipóteses-alvo (H-1, H-2, H-4 e H-5; H-3 fica fora, ver [`docs/05`](../docs/05-revisao-piloto-tamanho-amostra.md#53-d3-tamanho-da-amostra)). Gera `erro_tipo1.csv`, `poder.csv`, `poder_cenarios.csv`, `poder.md` e `poder.png` em `results/<coleta>/`.

---

## `diagnostico_ordem.py`: deriva temporal

```bash
python3 scripts/diagnostico_ordem.py --coleta piloto [--limiar 10] [--rho-max 0.3]
```

A ordem das execuções é sorteada para que uma interferência passageira (frequência da CPU, processo em segundo plano) não favoreça um tratamento. Este script confere se essa interferência existiu e se ela muda as conclusões:

1. **Desvio** de cada execução válida em relação à mediana do seu tratamento, em %, para M1–M5 (as 8 condições ficam na mesma escala);
2. **Tendência:** correlação de Spearman entre a ordem de execução e o desvio, em todas as execuções e por software;
3. **Episódios:** execuções com vazão pelo menos `--limiar`% (padrão 10%) abaixo da mediana do tratamento; vizinhas na sequência formam um episódio;
4. **Sensibilidade:** diferença % das medianas (Valkey × Redis) por condição, com todas as execuções e sem as sinalizadas;
5. **Critério de aceite** (mini-piloto e coleta completa): **APROVADO** se nenhuma execução for sinalizada e nenhuma tendência de M1–M3, com todas as execuções juntas, tiver |ρ| > `--rho-max` e p < 0,05. A tendência por software é só informativa. Na carga fixa, a vazão é imposta, então essas execuções ficam fora da tendência e dos episódios de M1 ([`docs/05`](../docs/05-revisao-piloto-tamanho-amostra.md#51-d1-deriva-temporal)).

Nada é removido da análise principal. Gera em `results/<coleta>/`: `ordem_desvios.csv` (desvios e coluna `sinalizada`), `ordem.md` (critério de aceite, tendência, episódios e sensibilidade) e `ordem_desvios.png` (desvio × ordem, por métrica).
