# Validacao dos dados: coleta `piloto`

| Item | Quantidade |
|---|---|
| Registros no CSV | 48 |
| Execucoes de aquecimento (descartadas por desenho) | 8 |
| Execucoes validas | 40 |
| Execucoes descartadas por problema | 0 |
| Outliers sinalizados (nao removidos) | 15 |

## Motivos de descarte

- V2 aquecimento: 8

## Execucoes validas por tratamento (esperado: 5)

| Software | Comando | Pipeline | Validas |
|---|---|---|---|
| Redis | GET | 1 | 5 |
| Redis | GET | 16 | 5 |
| Redis | SET | 1 | 5 |
| Redis | SET | 16 | 5 |
| Valkey | GET | 1 | 5 |
| Valkey | GET | 16 | 5 |
| Valkey | SET | 1 | 5 |
| Valkey | SET | 16 | 5 |

## Outliers sinalizados

| Execucao | Metricas |
|---|---|
| `0012-valkey-get-p16-t1` | mem_rss_mib |
| `0013-redis-get-p1-t1` | ops_s lat_p99_ms |
| `0015-valkey-set-p16-t1` | lat_p99_ms mem_rss_mib |
| `0017-redis-get-p16-t1` | ops_s lat_p50_ms lat_p99_ms mem_rss_mib cpu_medio_pct |
| `0018-redis-get-p1-t1` | ops_s lat_p50_ms lat_p99_ms cpu_medio_pct |
| `0019-redis-set-p1-t1` | ops_s lat_p50_ms |
| `0022-valkey-get-p1-t1` | lat_p99_ms |
| `0024-redis-get-p16-t1` | mem_rss_mib |
| `0025-valkey-get-p1-t1` | mem_rss_mib |
| `0029-redis-get-p1-t1` | cpu_medio_pct |
| `0032-valkey-get-p1-t1` | lat_p99_ms |
| `0035-redis-get-p16-t1` | cpu_medio_pct |
| `0041-redis-set-p16-t1` | lat_p99_ms |
| `0044-redis-set-p16-t1` | cpu_medio_pct |
| `0048-valkey-set-p16-t1` | lat_p50_ms |
