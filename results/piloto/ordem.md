# Diagnóstico de deriva temporal: coleta `piloto`

Desvio % = (valor − mediana do tratamento) / mediana do tratamento. Gráfico: [ordem_desvios.png](ordem_desvios.png).

## Tendência ao longo da coleta (Spearman: ordem × desvio)

| Métrica | Grupo | n | ρ | p |
|---|---|---|---|---|
| M1 Vazão | Todos | 40 | -0,08 | 0,6374 |
| M1 Vazão | Redis | 20 | 0,33 | 0,1536 |
| M1 Vazão | Valkey | 20 | -0,58 | 0,0077 |
| M2 Latência p50 | Todos | 40 | 0,01 | 0,9508 |
| M2 Latência p50 | Redis | 20 | -0,35 | 0,1257 |
| M2 Latência p50 | Valkey | 20 | 0,49 | 0,0294 |
| M3 Latência p99 | Todos | 40 | 0,12 | 0,4562 |
| M3 Latência p99 | Redis | 20 | -0,29 | 0,2152 |
| M3 Latência p99 | Valkey | 20 | 0,53 | 0,0160 |
| M4 Memória | Todos | 40 | -0,28 | 0,0774 |
| M4 Memória | Redis | 20 | -0,10 | 0,6621 |
| M4 Memória | Valkey | 20 | -0,46 | 0,0430 |
| M5 CPU | Todos | 40 | 0,32 | 0,0445 |
| M5 CPU | Redis | 20 | 0,26 | 0,2675 |
| M5 CPU | Valkey | 20 | 0,33 | 0,1496 |

## Episódios (vazão ≥ 10% abaixo da mediana do tratamento)

**Episódio 1:** ordem 17–19 (17:28–17:29 UTC), 3 execução(ões), software: Redis.

| Execução | Vazão | Lat. p50 | Lat. p99 | Memória | CPU |
|---|---|---|---|---|---|
| `0017-redis-get-p16-t1` | -23,0% | 27,5% | 53,7% | -0,2% | -0,5% |
| `0018-redis-get-p1-t1` | -15,1% | 17,1% | 17,5% | -0,1% | -0,2% |
| `0019-redis-set-p1-t1` | -16,3% | 16,9% | 13,3% | 0,6% | -0,2% |

## Sensibilidade: diferença Valkey × Redis sem as execuções sinalizadas

Diferença = (mediana Valkey − mediana Redis) / mediana Redis. Variação em pontos percentuais (p.p.).

| Métrica | Comando | Pipeline | Excluídas | Dif. todas (%) | Dif. sem sinalizadas (%) | Variação (p.p.) |
|---|---|---|---|---|---|---|
| M1 Vazão | GET | 1 | 1 | -0,7 | -1,9 | -1,2 |
| M1 Vazão | GET | 16 | 1 | -4,0 | -5,3 | -1,3 |
| M1 Vazão | SET | 1 | 1 | -3,5 | -4,1 | -0,6 |
| M1 Vazão | SET | 16 | 0 | -1,1 | -1,1 | 0,0 |
| M2 Latência p50 | GET | 1 | 1 | 2,1 | 3,2 | 1,1 |
| M2 Latência p50 | GET | 16 | 1 | 3,6 | 5,1 | 1,5 |
| M2 Latência p50 | SET | 1 | 1 | 3,7 | 4,0 | 0,3 |
| M2 Latência p50 | SET | 16 | 0 | 4,9 | 4,9 | 0,0 |
| M3 Latência p99 | GET | 1 | 1 | 1,3 | 2,3 | 0,9 |
| M3 Latência p99 | GET | 16 | 1 | 6,0 | 8,0 | 2,0 |
| M3 Latência p99 | SET | 1 | 1 | 0,9 | 3,9 | 3,0 |
| M3 Latência p99 | SET | 16 | 0 | -7,8 | -7,8 | 0,0 |
| M4 Memória | GET | 1 | 1 | -20,2 | -20,3 | -0,0 |
| M4 Memória | GET | 16 | 1 | -20,0 | -20,0 | -0,0 |
| M4 Memória | SET | 1 | 1 | -19,9 | -19,9 | 0,0 |
| M4 Memória | SET | 16 | 0 | -20,3 | -20,3 | 0,0 |
| M5 CPU | GET | 1 | 1 | 0,0 | -0,0 | -0,0 |
| M5 CPU | GET | 16 | 1 | -0,1 | -0,1 | -0,0 |
| M5 CPU | SET | 1 | 1 | -0,2 | -0,2 | -0,0 |
| M5 CPU | SET | 16 | 0 | 0,0 | 0,0 | 0,0 |
