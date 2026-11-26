# 3. Métricas, hipóteses, plano de coleta e plano de análise

## 3.1 Variáveis do experimento

| Tipo | Variável | Níveis / valores |
|---|---|---|
| Independente (fator principal) | Software | Redis 8.10.3 · Valkey 9.1.3 |
| Independente (fator de bloco) | Comando | `GET` (leitura) · `SET` (escrita) |
| Independente (fator de bloco) | *Pipeline* | 1 (sem *pipeline*) · 16 |
| Independente (fator de bloco) | Carga | saturada (sem limite de taxa) · fixa (50.000 ops/s, só com *pipeline* 1; ver [docs/05, D2](05-revisao-piloto-tamanho-amostra.md#52-d2-efeito-teto-da-cpu)) |
| Fixas (controladas) | Tamanho do valor, nº de clientes, nº de chaves, duração, configuração do servidor, máquina | 256 bytes · 4 *threads* × 50 conexões · 100.000 chaves · 30 s · padrão da imagem oficial · mesma máquina |
| Dependentes | M1–M5 | ver 3.2 |

## 3.2 Métricas

| ID | Métrica | Entidade | Tipo de entidade | Atributo | Interno / externo | Medida | Escala | Unidade | Como é obtida |
|---|---|---|---|---|---|---|---|---|---|
| M1 | Vazão | Servidor em execução | Produto | Comportamento no tempo (capacidade) | Externo | Direta | Razão | ops/s | Saída JSON do `memtier_benchmark` (`Totals.Ops/sec`) |
| M2 | Latência p50 | Servidor em execução | Produto | Comportamento no tempo (tempo de resposta típico) | Externo | Derivada (percentil da distribuição das latências) | Razão | ms | `memtier_benchmark` (`Percentile Latencies.p50.00`) |
| M3 | Latência p99 | Servidor em execução | Produto | Comportamento no tempo (cauda) | Externo | Derivada (percentil) | Razão | ms | `memtier_benchmark` (`p99.00`) |
| M4 | Memória residente | Processo do servidor | Recurso | Utilização de memória | Externo | Direta | Razão | MiB | `INFO memory` → `used_memory_rss` ao final da execução |
| M5 | Uso médio de CPU | Contêiner do servidor | Recurso | Utilização de CPU | Externo | Derivada (média das amostras de 1 s) | Razão | % de 1 núcleo | `docker stats` em modo contínuo (~1 leitura/s) durante a carga. Comparada entre os softwares só na **carga fixa**: na saturada, os dois ficam no teto (~100%) |
| M6 | *Pulls* da imagem oficial | Software (distribuição) | Produto | Adoção | Externo | Direta | Razão (contagem) | *pulls* | API do Docker Hub |
| M7 | Downloads mensais dos clientes | Ecossistema de clientes | Produto | Adoção | Externo | Direta | Razão (contagem) | downloads/mês | APIs do PyPI Stats e do npm |
| M8 | Posição no DB-Engines | Software | Produto | Popularidade | Externo | Direta (publicada pela fonte) | **Ordinal** | posição | Página do sistema no DB-Engines |
| — | Software (tratamento) | — | — | — | — | — | **Nominal** | — | Definido pelo grupo |

**Estatísticas permitidas por escala:**

- **Razão (M1–M7):** todas, incluindo média, desvio padrão, coeficiente de variação e razões ("X% mais rápido").
- **Ordinal (M8):** apenas mediana, moda, percentis e comparações de ordem. Média e razão não fazem sentido.
- **Nominal (software, comando):** apenas contagens e moda. Servem para agrupar.

## 3.3 Hipóteses

As hipóteses são **bilaterais**, porque não há razão teórica forte para apostar em um sentido. Os dois servidores compartilham a base de código até a versão 7.2.4 e evoluíram de forma independente depois disso. H-1 a H-4 são testadas **em cada uma das 4 condições de carga saturada** (comando × *pipeline*). H-5 é testada **nas 2 condições de carga fixa** (`GET` e `SET`), onde a CPU não fica no teto ([docs/05, D2](05-revisao-piloto-tamanho-amostra.md#52-d2-efeito-teto-da-cpu)). O nível de significância é **α = 0,05**, com correção de Holm-Bonferroni para as comparações múltiplas.

| ID | Pergunta | H0 (hipótese nula) | H1 (hipótese alternativa) |
|---|---|---|---|
| H-1 | Q1 | A distribuição da vazão (M1) do Valkey é **igual** à do Redis. | A distribuição da vazão do Valkey é **diferente** da do Redis. |
| H-2 | Q2 | A latência p50 (M2) do Valkey é **igual** à do Redis. | A latência p50 do Valkey é **diferente** da do Redis. |
| H-3 | Q2 | A latência p99 (M3) do Valkey é **igual** à do Redis. | A latência p99 do Valkey é **diferente** da do Redis. |
| H-4 | Q3 | O uso de memória (M4) do Valkey é **igual** ao do Redis. | O uso de memória do Valkey é **diferente** do do Redis. |
| H-5 | Q3 | Com a mesma carga fixa, o uso de CPU (M5) do Valkey é **igual** ao do Redis. | Com a mesma carga fixa, o uso de CPU do Valkey é **diferente** do do Redis. |
| H-6 | Q4 | A diferença Valkey − Redis em M1 **não depende** do *pipeline* (sem interação). | A diferença Valkey − Redis em M1 **depende** do *pipeline* (há interação). |

Em notação, para H-1 a H-5, sendo θ a mediana (ou a média, se o teste paramétrico for aplicável):

- H0: θ_Valkey = θ_Redis
- H1: θ_Valkey ≠ θ_Redis

As métricas de impacto (M6–M8) **não** têm hipóteses. São usadas de forma descritiva, para estimar o alcance do resultado.

## 3.4 Plano de coleta

### Ferramentas

| Ferramenta | Uso | Versão |
|---|---|---|
| Docker / Docker Compose | Isolar servidor e cliente em contêineres | registrar `docker version` na coleta |
| `redis:8.10.3` | Servidor Redis (imagem oficial) | *digest* registrado no arquivo de metadados |
| `valkey/valkey:9.1.3` | Servidor Valkey (imagem oficial) | *digest* registrado no arquivo de metadados |
| `redislabs/memtier_benchmark:2.6.1` | Gerador de carga, **o mesmo para os dois servidores** | 2.6.1 (*digest* registrado no arquivo de metadados) |
| `docker stats` + `INFO memory` | Uso de CPU e memória | — |
| Python 3 (`scripts/`) | Orquestrar as execuções, sortear a ordem, validar e analisar | 3.10+ (bibliotecas fixadas em `requirements.txt`) |

### Desenho e amostra

- **Desenho:** fatorial completo 2 (software) × 2 (comando) × 2 (*pipeline*) = **8 tratamentos em carga saturada**, mais 2 (software) × 2 (comando) = **4 tratamentos em carga fixa** (*pipeline* 1, 50.000 ops/s). Total: **12 tratamentos**.
- **Repetições:** **50 execuções independentes por tratamento** ([docs/05, D3](05-revisao-piloto-tamanho-amostra.md#53-d3-tamanho-da-amostra)), totalizando **600 execuções medidas** de 30 s cada (≈ 5 h 35 min com reinícios e aquecimento). Era 30 na proposta. O piloto mostrou que esse n não basta.
- **Unidade experimental:** uma execução completa (contêiner novo → carga → coleta das métricas → contêiner removido).
- **Aleatorização em blocos:** a coleta roda em 50 **blocos completos**. Cada bloco tem uma execução de cada tratamento, em ordem sorteada com semente fixa (registrada). Assim, efeitos de temperatura, *throttling* ou processos de fundo se distribuem igualmente entre os tratamentos ([docs/05, D1](05-revisao-piloto-tamanho-amostra.md#51-d1-deriva-temporal)).
- **Aquecimento:** 1 execução de aquecimento por tratamento, descartada (as 12 rodam antes das medidas, em ordem sorteada).
- **Mini-piloto (portão):** antes da coleta completa, 3 repetições por tratamento na máquina do estudo. A coleta completa só roda se o critério de deriva e o de poder derem APROVADO (docs/05, seção 5.3).

### Procedimento de cada execução

1. Subir o contêiner do servidor com CPUs fixadas (`--cpuset-cpus=0,4`, um núcleo físico) e configuração padrão.
2. Popular 100.000 chaves com valores de 256 bytes (necessário para o `GET`).
3. Rodar a carga no contêiner do cliente, em outros núcleos físicos (`--cpuset-cpus=1-3,5-7`). As CPUs foram ajustadas após o piloto (ver [docs/04](04-coleta-piloto.md)):
   ```
   memtier_benchmark -s <servidor> -p 6379 -t 4 -c 50 --test-time=30 \
     --data-size=256 --key-maximum=100000 --key-pattern=R:R \
     --ratio=<1:0 para SET | 0:1 para GET> --pipeline=<1|16> \
     [--rate-limiting=250   # só na carga fixa: 250 req/s × 200 conexões = 50.000 ops/s] \
     --hide-histogram --json-out-file=<arquivo>.json
   ```
4. Durante a carga, amostrar `docker stats` a cada 1 s (M5). Ao final, ler `INFO memory` (M4).
5. Salvar o JSON bruto em `data/raw/` e uma linha consolidada em `data/processed/execucoes.csv`.
6. Remover os contêineres antes da próxima execução.

### Controle do ambiente

- Mesma máquina para todas as execuções, ligada na tomada, com governador de CPU `performance` e aplicativos fechados. O coletor confere a tomada e o governador antes de começar e não roda se estiverem fora do protocolo.
- Registrar no arquivo de metadados: CPU, RAM, sistema operacional, versão do Docker/WSL2, *digests* das imagens e semente.

### Coleta piloto (Sprint 1)

- **5 execuções por tratamento (40 no total).** Servem para validar o roteiro, estimar a variância de cada métrica e conferir com simulação de poder (reaproveitando o Lab04) se n = 30 basta para detectar diferenças de 5% na vazão.

### Evidências de impacto

- Coletadas pelo script `scripts/coleta_impacto.py` (tarefa 4), uma vez no início e outra no fim do estudo.

### Scripts que implementam este plano

`scripts/coleta_experimento.py` (execuções), `scripts/validacao_dados.py` (regras de validação), `scripts/analise.py` (plano de análise) e `scripts/simulacao_poder.py` (poder e erro tipo I). Como rodar: [`scripts/README.md`](../scripts/README.md).

### Regras de ética

- **Nenhum teste de carga em sistema de terceiros.** Toda a carga é gerada e recebida **dentro da máquina do grupo**.
- Consultas a serviços públicos (Docker Hub, PyPI, npm, DB-Engines etc.) feitas **por script com no máximo 1 requisição por segundo**, em endpoints públicos, respeitando os termos de uso e o `robots.txt`.
- **Nenhum dado pessoal** é coletado. Os dados do experimento são sintéticos (chaves e valores gerados).
- O estudo não envolve participantes humanos.

### Validação e versionamento dos dados

- Execução **inválida** (e repetida) se: o `memtier_benchmark` reportar erros de conexão, a vazão for 0 ou o contêiner reiniciar durante a carga.
- Na carga fixa, execução **descartada** se a vazão ficar fora de ±5% da taxa planejada (regra V10). Se o servidor não atingiu a carga, a CPU não é comparável.
- *Outliers* **não** são removidos automaticamente. São sinalizados (fora de Q1 − 1,5·IQR / Q3 + 1,5·IQR) e discutidos.
- Dados brutos e processados versionados no repositório (`data/raw/`, `data/processed/`), junto com os metadados de cada coleta.

## 3.5 Plano de análise

### Estatística descritiva (por tratamento)

- n, média, **mediana**, desvio padrão, coeficiente de variação, mínimo, máximo, Q1, Q3 e IQR.
- Intervalo de confiança de 95% da mediana por *bootstrap* (10.000 reamostragens).
- Gráficos: *boxplot* por software em cada condição (M1–M5), ECDF das latências e gráfico de interação software × *pipeline* para H-6.
- M6–M8 (impacto): apenas tabela descritiva. M8 é ordinal, então reporta-se só a posição, sem médias.

### Escolha do teste de hipótese (H-1 a H-5)

As amostras são **independentes** (cada execução usa um contêiner novo) e há **dois grupos** (Redis × Valkey) em cada condição:

```
Shapiro-Wilk em cada grupo (α = 0,05) + inspeção do Q-Q plot
├── os dois grupos normais   → teste t de Welch (não assume variâncias iguais)
└── algum grupo não normal   → Mann-Whitney U (bilateral)
```

Como métricas de desempenho costumam ser assimétricas e ter cauda longa, **o teste esperado é o Mann-Whitney U**. O t de Welch só entra se a normalidade for confirmada.

### Interação (H-6)

- ANOVA fatorial 2 × 2 (software × *pipeline*) para cada comando, se os resíduos forem normais.
- Caso contrário, **ANOVA com *Aligned Rank Transform* (ART)**, a alternativa não paramétrica que permite testar a interação.

### Tamanho do efeito

| Teste usado | Tamanho do efeito | Interpretação |
|---|---|---|
| Mann-Whitney U | **δ de Cliff** | \|δ\| < 0,147 desprezível · < 0,33 pequeno · < 0,474 médio · ≥ 0,474 grande (Romano et al., 2006) |
| t de Welch | **g de Hedges** | < 0,2 desprezível · < 0,5 pequeno · < 0,8 médio · ≥ 0,8 grande (Cohen) |
| ANOVA / ART | η² parcial | 0,01 pequeno · 0,06 médio · 0,14 grande |

Além do tamanho do efeito padronizado, reporta-se a **diferença percentual entre as medianas** com IC de 95% (*bootstrap*), porque é o número que faz sentido para quem opera o serviço ("o Valkey teve X% mais vazão").

### Comparações múltiplas e relevância prática

- São 4 hipóteses (H-1 a H-4) × 4 condições saturadas + H-5 × 2 condições de carga fixa = **18 testes**. O p-valor é ajustado por **Holm-Bonferroni**.
- **Relevância prática:** uma diferença menor que **5%** na mediana é tratada como irrelevante na prática, mesmo que seja estatisticamente significativa. A leitura usa o IC 95% da diferença: **relevante** se o IC inteiro estiver além de ±5%, **irrelevante** se estiver inteiro dentro de ±5% e **inconclusivo** se cruzar o limiar. Assim, uma não rejeição só vira "sem diferença relevante" quando o IC permite, o que importa para H-3 (p99), que não é alvo de poder.

### Poder e erro tipo I (reaproveitado do Lab04)

- Com a variância estimada no piloto, simula-se (≥ 1.000 réplicas) o erro tipo I e o poder do Mann-Whitney para efeito de 5%. Com o piloto, n = 30 não bastava, e o n passou para **50** (docs/05, D3). O mini-piloto confirma esse n. H-3 (p99) é testada, mas não é alvo de poder (a cauda é ruidosa demais para detectar 5% com um n viável).

### Ferramentas

- Python: `pandas`, `scipy.stats` (Shapiro, Levene, Welch, Mann-Whitney), `numpy` (*bootstrap*), `matplotlib`/`seaborn`. O *dashboard* do Lab04 é reaproveitado para a visualização.

## 3.6 Checklist de entrega

- [x] Métricas com entidade, atributo, tipo de medida e escala (3.2)
- [x] Hipóteses H0 e H1 escritas (3.3)
- [x] Plano de coleta com ferramentas, frequência, amostra e regras de ética (3.4)
- [x] Plano de análise com a estatística descritiva, o teste escolhido e o tamanho do efeito (3.5)
