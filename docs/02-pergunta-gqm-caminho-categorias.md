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

## 2.3 Caminho do estudo

**Caminho principal: Rodar o software no ambiente do grupo.** Os dois servidores são executados a partir das **mesmas imagens oficiais usadas em produção**, na mesma máquina, com a mesma configuração e a mesma carga. Só a variável "software" muda entre os tratamentos.

**Caminho complementar: Avaliar a qualidade do produto (ISO/IEC 25010).** As métricas escolhidas operacionalizam a característica *eficiência de desempenho* da norma (subcaracterísticas *comportamento no tempo* e *utilização de recursos*).

**Por que este caminho e não os outros:**

| Alternativa | Por que não foi o principal |
|---|---|
| Medir o serviço de fora | Não existe um "serviço Redis público" para observar. Além disso, teste de carga em sistema de terceiros é proibido pelo enunciado. |
| Analisar dados de operação | Não há dados públicos comparáveis de desempenho Redis × Valkey em produção. Os *benchmarks* publicados vêm dos próprios fornecedores, o que gera conflito de interesse. |
| Estudar com pessoas / survey | A pergunta é sobre o comportamento do software, não sobre a percepção de usuários. |
| **Rodar no ambiente do grupo** | **Permite controlar as variáveis, repetir as medições muitas vezes e aplicar carga sem afetar ninguém**, o que é o que um teste de hipótese sobre desempenho exige. |

Os números de impacto (M6–M8) vêm de fontes públicas e são coletados por script (tarefa 4), servindo para traduzir o resultado para o mundo real (seção 5 do enunciado).

## 2.4 Classificação nas 7 categorias de pesquisa (v1)

| Categoria | Classificação | Justificativa |
|---|---|---|
| **Natureza** | Aplicada | O objetivo é gerar conhecimento para uma decisão prática (manter Redis ou migrar para Valkey), não desenvolver teoria nova. |
| **Objetivos** | Explicativa | O estudo busca estabelecer se a troca do software (causa) **provoca** diferença no desempenho (efeito), indo além de descrever os números. |
| **Abordagem** | Quantitativa | Todas as métricas são numéricas (ops/s, ms, MiB, %) e a análise usa estatística descritiva e testes de hipótese. |
| **Procedimentos** | Experimental (experimento controlado), com apoio documental | O grupo manipula a variável independente (software) e controla as demais (máquina, versão, configuração, carga). Os dados de impacto vêm de pesquisa documental em fontes públicas. |
| **Tempo** | Transversal | As medições são feitas em uma janela curta, com as versões vigentes em novembro de 2026. Não se acompanha a evolução das versões ao longo do tempo. |
| **Controle** | Laboratório (*in vitro*) | O ambiente é totalmente controlado pelo grupo: contêineres isolados, CPUs fixadas, carga sintética. Isso aumenta a validade interna e reduz a externa (não é tráfego real de produção). |
| **Nível de evidência** | Alto para causalidade no contexto testado, limitado para generalização | Um experimento controlado com repetições e aleatorização é o desenho mais forte para inferir causa. A evidência vale para *esta* máquina, *estas* versões e *esta* carga, e não substitui medição em produção. |

> Versão 1 (Sprint 1). A classificação será revisada na Sprint 3, depois da coleta completa.

## 2.5 Checklist de entrega

- [x] Pergunta de pesquisa escrita (2.1)
- [x] GQM completo: objetivo no template de Basili, perguntas e métricas (2.2)
- [x] Caminho do estudo escolhido e justificado (2.3)
- [x] 7 categorias classificadas, cada uma com justificativa, v1 (2.4)
