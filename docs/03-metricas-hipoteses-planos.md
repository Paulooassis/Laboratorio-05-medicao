# 3. Métricas, hipóteses, plano de coleta e plano de análise

## 3.1 Variáveis do experimento

| Tipo | Variável | Níveis / valores |
|---|---|---|
| Independente (fator principal) | Software | Redis 8.10.3 · Valkey 9.1.3 |
| Independente (fator de bloco) | Comando | `GET` (leitura) · `SET` (escrita) |
| Independente (fator de bloco) | *Pipeline* | 1 (sem *pipeline*) · 16 |
| Fixas (controladas) | Tamanho do valor, nº de clientes, nº de chaves, duração, configuração do servidor, máquina | 256 bytes · 4 *threads* × 50 conexões · 100.000 chaves · 30 s · padrão da imagem oficial · mesma máquina |
| Dependentes | M1–M5 | ver 3.2 |

## 3.2 Métricas

| ID | Métrica | Entidade | Tipo de entidade | Atributo | Interno / externo | Medida | Escala | Unidade | Como é obtida |
|---|---|---|---|---|---|---|---|---|---|
| M1 | Vazão | Servidor em execução | Produto | Comportamento no tempo (capacidade) | Externo | Direta | Razão | ops/s | Saída JSON do `memtier_benchmark` (`Totals.Ops/sec`) |
| M2 | Latência p50 | Servidor em execução | Produto | Comportamento no tempo (tempo de resposta típico) | Externo | Derivada (percentil da distribuição das latências) | Razão | ms | `memtier_benchmark` (`Percentile Latencies.p50.00`) |
| M3 | Latência p99 | Servidor em execução | Produto | Comportamento no tempo (cauda) | Externo | Derivada (percentil) | Razão | ms | `memtier_benchmark` (`p99.00`) |
| M4 | Memória residente | Processo do servidor | Recurso | Utilização de memória | Externo | Direta | Razão | MiB | `INFO memory` → `used_memory_rss` ao final da execução |
| M5 | Uso médio de CPU | Contêiner do servidor | Recurso | Utilização de CPU | Externo | Derivada (média das amostras de 1 s) | Razão | % de 1 núcleo | `docker stats --no-stream` a cada 1 s durante a carga |
| M6 | *Pulls* da imagem oficial | Software (distribuição) | Produto | Adoção | Externo | Direta | Razão (contagem) | *pulls* | API do Docker Hub |
| M7 | Downloads mensais dos clientes | Ecossistema de clientes | Produto | Adoção | Externo | Direta | Razão (contagem) | downloads/mês | APIs do PyPI Stats e do npm |
| M8 | Posição no DB-Engines | Software | Produto | Popularidade | Externo | Direta (publicada pela fonte) | **Ordinal** | posição | Página do sistema no DB-Engines |
| — | Software (tratamento) | — | — | — | — | — | **Nominal** | — | Definido pelo grupo |

**Estatísticas permitidas por escala:**

- **Razão (M1–M7):** todas, incluindo média, desvio padrão, coeficiente de variação e razões ("X% mais rápido").
- **Ordinal (M8):** apenas mediana, moda, percentis e comparações de ordem. Média e razão não fazem sentido.
- **Nominal (software, comando):** apenas contagens e moda. Servem para agrupar.
