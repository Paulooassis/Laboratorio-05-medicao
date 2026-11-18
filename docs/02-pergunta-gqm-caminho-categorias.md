# 2. Pergunta de pesquisa, GQM, caminho do estudo e 7 categorias

## 2.1 Pergunta de pesquisa

> **PP:** Para quem usa um servidor chave-valor como cache, **trocar o Redis pelo Valkey** (versões estáveis atuais, configuração padrão, mesma máquina e mesma carga) **muda a vazão, a latência e o consumo de recursos do serviço**?

Subperguntas:

- **PP1:** Há diferença de **vazão** (operações por segundo) entre Redis e Valkey em cargas de leitura (`GET`) e de escrita (`SET`)?
- **PP2:** Há diferença de **latência** típica (p50) e de cauda (p99)?
- **PP3:** Há diferença no **uso de memória e de CPU** do servidor sob a mesma carga?
- **PP4:** A diferença, se existir, **se mantém quando muda o modo de envio** (sem *pipeline* × com *pipeline*)?

## 2.2 GQM (Goal–Question–Metric)

### Objetivo (template de Basili)

| Elemento | Preenchimento |
|---|---|
| **Analisar** | os servidores Redis 8.10 e Valkey 9.1 (imagens oficiais) |
| **com o propósito de** | comparar / avaliar |
| **com respeito à** | eficiência de desempenho (ISO/IEC 25010: comportamento no tempo e utilização de recursos) |
| **do ponto de vista de** | equipes de engenharia e operação que decidem qual servidor usar como cache |
| **no contexto de** | execução em contêineres Docker, na máquina do grupo, com cargas sintéticas típicas de cache (`GET`/`SET`, valores de 256 bytes) |

### Perguntas e métricas

| Pergunta | Métricas |
|---|---|
| **Q1.** O Valkey processa mais ou menos operações por segundo que o Redis? | **M1** Vazão (ops/s) |
| **Q2.** O Valkey responde mais rápido ou mais devagar que o Redis, no caso típico e no pior caso? | **M2** Latência p50 (ms) · **M3** Latência p99 (ms) |
| **Q3.** O Valkey consome mais ou menos recursos que o Redis para atender a mesma carga? | **M4** Memória residente do servidor (MiB) · **M5** Uso médio de CPU do contêiner (%) |
| **Q4.** O resultado muda com o modo de envio dos comandos? | M1–M3 estratificadas por *pipeline* (1 e 16) |
| **Q5.** Quantos usuários e empresas são afetados pela escolha entre os dois? | **M6** *Pulls* no Docker Hub · **M7** Downloads mensais dos clientes (PyPI/npm) · **M8** Posição no DB-Engines |

```
                 Objetivo: comparar eficiência de desempenho Redis × Valkey
        ┌───────────────┬───────────────┬───────────────┬───────────────┐
        Q1 vazão        Q2 latência     Q3 recursos     Q4 pipeline     Q5 impacto
        │               │               │               │               │
        M1              M2, M3          M4, M5          M1–M3 por       M6, M7, M8
                                                        estrato
```

A definição completa de cada métrica (entidade, atributo, tipo de medida e escala) está no documento da tarefa 3.

### Cuidado com Goodhart e McNamara

- **Lei de Goodhart / Campbell:** os dois projetos publicam *benchmarks* próprios e têm incentivo para otimizar exatamente o que o `redis-benchmark` mede. Por isso o estudo usa uma ferramenta de carga **neutra e igual para os dois** (`memtier_benchmark`) e reporta latência de cauda (p99), não só a média.
- **Falácia de McNamara:** vazão e latência não capturam tudo o que pesa na escolha (licença, suporte, ecossistema). O estudo **não** conclui "qual é melhor"; conclui apenas sobre a eficiência de desempenho medida.
