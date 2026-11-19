# LAB05: Redis × Valkey em operação

**Experimento em software real: trocar o Redis pelo Valkey muda o desempenho de um cache?**

Laboratório de Experimentação de Software · Engenharia de Software · PUC Minas · 6º período · Prof. Danilo Maia

| | |
|---|---|
| Repositório | https://github.com/Paulooassis/Laboratorio-05-medicao |
| GitHub Projects (Kanban) | https://github.com/users/Paulooassis/projects/6 |
| Sprint atual | **Lab05S01: proposta + coleta piloto** |

---

## Proposta (Lab05S01)

### 1. Software: Redis × Valkey

O **Redis** é o servidor chave-valor em memória mais usado do mundo, aplicado como cache, armazenamento de sessão, fila e *rate limiting*. O **Valkey** é o *fork* do Redis 7.2.4 mantido pela Linux Foundation desde março de 2024, criado depois da mudança de licença do Redis. Os dois falam o mesmo protocolo e usam os mesmos clientes. Por isso, quem opera Redis em produção hoje tem uma decisão real a tomar: ficar no Redis ou migrar para o Valkey.

| Critério | Evidência principal (17/11/2026) | Redis | Valkey |
|---|---|---|---|
| Real | Site oficial e imagem oficial no Docker Hub | redis.io · `redis` | valkey.io · `valkey/valkey` |
| Em operação | Versão estável e data do último *release* | 8.10.3 (26/10/2026) | 9.1.3 (26/10/2026) |
| Alto impacto | *Pulls* da imagem oficial no Docker Hub | **11,7 bilhões** | **410,9 milhões** |
| Alto impacto | Posição no DB-Engines (*key-value stores*) | **1º** | 12º |
| Alto impacto | Downloads/mês do cliente Python (PyPI) | 242,1 milhões | 6,4 milhões |

Todas as evidências, com fonte e data: [docs/01-software-e-criterios.md](docs/01-software-e-criterios.md). Os números são coletados por script ([data/impacto/](data/impacto/)).

**O objeto de pesquisa não é um repositório do GitHub.** O que se mede é o servidor em execução, nas mesmas imagens oficiais que as empresas usam em produção. Nenhum commit, issue, PR ou código-fonte é analisado.

### 2. Pergunta de pesquisa

> **PP:** Para quem usa um servidor chave-valor como cache, **trocar o Redis pelo Valkey** (versões estáveis atuais, configuração padrão, mesma máquina e mesma carga) **muda a vazão, a latência e o consumo de recursos do serviço**?

Subperguntas: vazão (PP1), latência p50 e p99 (PP2), memória e CPU (PP3) e se a diferença se mantém com e sem *pipeline* (PP4).

### 3. Caminho escolhido

- **Principal: rodar o software no ambiente do grupo.** Os dois servidores rodam nas imagens oficiais, na mesma máquina, com a mesma configuração e a mesma carga. Só o software muda.
- **Complementar: avaliar a qualidade do produto (ISO/IEC 25010).** As métricas operacionalizam a *eficiência de desempenho* (comportamento no tempo e utilização de recursos).

Por que não os outros caminhos: [docs/02, seção 2.3](docs/02-pergunta-gqm-caminho-categorias.md#23-caminho-do-estudo).

### 4. GQM

**Objetivo (Basili):** analisar **Redis 8.10 e Valkey 9.1** com o propósito de **comparar** com respeito à **eficiência de desempenho** do ponto de vista de **equipes que decidem qual servidor usar como cache** no contexto de **contêineres Docker na máquina do grupo, com cargas sintéticas de cache**.

| Pergunta | Métricas |
|---|---|
| Q1 Vazão | M1 ops/s |
| Q2 Latência | M2 p50 (ms) · M3 p99 (ms) |
| Q3 Recursos | M4 memória residente (MiB) · M5 CPU média (%) |
| Q4 Efeito do *pipeline* | M1–M3 por estrato |
| Q5 Alcance (impacto) | M6 *pulls* · M7 downloads dos clientes · M8 posição no DB-Engines |

GQM completo, Goodhart/McNamara e escalas: [docs/02](docs/02-pergunta-gqm-caminho-categorias.md) e [docs/03](docs/03-metricas-hipoteses-planos.md).

### 5. As 7 categorias de pesquisa (v1)

| Categoria | Classificação | Justificativa resumida |
|---|---|---|
| Natureza | Aplicada | Apoia uma decisão prática (manter ou migrar) |
| Objetivos | Explicativa | Busca a relação de causa entre o software e o desempenho |
| Abordagem | Quantitativa | Métricas numéricas, estatística descritiva e testes de hipótese |
| Procedimentos | Experimental (controlado) + documental | O grupo manipula o software e controla o resto; impacto vem de fontes públicas |
| Tempo | Transversal | Uma janela curta, com as versões de novembro de 2026 |
| Controle | Laboratório (*in vitro*) | Ambiente totalmente controlado: alta validade interna, externa limitada |
| Nível de evidência | Alto para causa no contexto testado | Experimento com repetição e aleatorização, mas não substitui medição em produção |

Justificativas completas: [docs/02, seção 2.4](docs/02-pergunta-gqm-caminho-categorias.md#24-classificação-nas-7-categorias-de-pesquisa-v1). Serão revisadas na S03.

### 6. Hipóteses, plano de coleta e plano de análise

- **Hipóteses bilaterais** H-1 a H-5 (Redis = Valkey em M1–M5) e H-6 (interação software × *pipeline*), α = 0,05 com Holm-Bonferroni.
- **Desenho:** fatorial 2 (software) × 2 (comando `GET`/`SET`) × 2 (*pipeline* 1/16) = 8 tratamentos, **30 execuções por tratamento** em ordem sorteada, contêiner novo a cada execução.
- **Análise:** descritiva por tratamento, Shapiro-Wilk → t de Welch ou Mann-Whitney U, δ de Cliff ou g de Hedges, ANOVA/ART para a interação, diferença % das medianas com IC 95% por *bootstrap*. Diferença < 5% é tratada como irrelevante na prática.

Detalhes: [docs/03-metricas-hipoteses-planos.md](docs/03-metricas-hipoteses-planos.md).

### 7. Coleta piloto

Rodada em 19/11/2026: 8 tratamentos × 5 repetições = **40 execuções válidas** (mais 8 de aquecimento), em ordem sorteada, com 0 descartes por erro. Relatório completo: [docs/04-coleta-piloto.md](docs/04-coleta-piloto.md).

| Achado | Detalhe |
|---|---|
| Memória (M4) | O Valkey usou **~20% menos memória residente** (≈ 48 MiB contra ≈ 60 MiB do Redis) em todas as condições, sem sobreposição entre os grupos |
| Vazão e latência (M1–M3) | Diferenças de 0 a 5%, dentro do ruído do piloto (CV de 8 a 23%) |
| CPU (M5) | Os dois servidores ficam saturados (~101%), então a métrica não discrimina (efeito teto) |
| Poder (simulação) | Erro tipo I calibrado (≈ 0,05). Com a variância do piloto, n = 30 **não basta** para detectar 5% em vazão e latência |
| Deriva temporal | 3 execuções seguidas (todas Redis) com vazão 15–23% abaixo da mediana; sem elas, a vantagem do Redis em vazão e latência p50 cresce até 1,5 p.p. A memória não muda |

**Ajustes para a S02:** coletar na tomada com governador `performance` (o piloto rodou na bateria, em `powersave`), refazer a simulação de poder com um mini-piloto (sem deriva no `diagnostico_ordem.py`) e redefinir o n; tratar o efeito teto da CPU com uma condição de carga fixa ou a métrica "CPU por 100 mil ops".

Dados: [data/raw/piloto/](data/raw/piloto/) e [data/processed/](data/processed/) · Tabelas e gráficos: [results/piloto/](results/piloto/)

### 8. O que foi reaproveitado dos laboratórios anteriores

| Lab | Reaproveitado | Onde |
|---|---|---|
| Lab01 | Coleta automatizada via API pública e Kanban no GitHub Projects | `scripts/coleta_impacto.py`, [Projects](https://github.com/users/Paulooassis/projects/6) |
| Lab02 | Desenho com tratamentos, controle das demais variáveis e aleatorização | Desenho fatorial em [docs/03](docs/03-metricas-hipoteses-planos.md) |
| Lab04 | Escolha do teste pela normalidade, simulação de erro tipo I e de poder | `scripts/analise.py`, `scripts/simulacao_poder.py` |

**Novo neste lab:** ambiente com Docker, orquestração de *benchmark* com fixação de CPUs e validação automática dos dados.

---

## Como reproduzir

**Requisitos:** Docker (testado com 29.1) e Python 3.10+.

```bash
pip install -r requirements.txt

# Ambiente para exploração manual (os dois servidores nas versões do estudo)
docker compose up -d                       # ou docker-compose up -d
docker compose run --rm memtier -s valkey --test-time=10 --hide-histogram
docker compose down

# Estudo (cada script grava em data/ ou results/)
python3 scripts/coleta_impacto.py                                   # evidências de impacto
python3 scripts/coleta_experimento.py --coleta piloto --repeticoes 5 # execuções (~32 min)
python3 scripts/validacao_dados.py   --coleta piloto                 # validação
python3 scripts/analise.py           --coleta piloto                 # descritiva, gráficos, testes
python3 scripts/simulacao_poder.py   --coleta piloto                 # poder e erro tipo I
python3 scripts/diagnostico_ordem.py --coleta piloto                 # deriva ao longo da coleta
```

No Windows, troque `python3` por `py`. Ajuste `--cpus-servidor` e `--cpus-cliente` à topologia da sua máquina (`lscpu -e` no Linux). Detalhes de cada script, opções e saídas: [scripts/README.md](scripts/README.md).

## Estrutura do repositório

```
docs/                     proposta: software, pergunta, GQM, categorias, planos, piloto
scripts/                  coleta, validação, análise e simulação (ver scripts/README.md)
data/impacto/             evidências públicas de impacto (CSV/JSON com fonte e data)
data/raw/<coleta>/        saída bruta do memtier, amostras de CPU, metadados e log
data/processed/           uma linha por execução (_execucoes.csv) e versão validada (_validado.csv)
results/<coleta>/         tabelas e gráficos da validação, da análise e da simulação de poder
docker-compose.yml        ambiente com Redis, Valkey e memtier nas versões do estudo
requirements.txt          bibliotecas Python com versões fixadas
```

## Ética

- Nenhum teste de carga em sistema de terceiros: toda a carga é gerada e recebida na máquina do grupo.
- Consultas a fontes públicas com no máximo 1 requisição por segundo, respeitando termos de uso e `robots.txt`.
- Nenhum dado pessoal coletado. O estudo não envolve participantes.
