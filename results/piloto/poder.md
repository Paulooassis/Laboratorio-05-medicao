# Simulação de poder e erro tipo I: coleta `piloto`

Mann-Whitney U bilateral, dados log-normais com o maior CV observado entre Redis e Valkey, 2000 réplicas por cenário, efeito = 5% na mediana.

## Erro tipo I (H0 verdadeira, n = 30, α = 0,05)

Taxa de rejeição: mínima 0.037, média 0.046, máxima 0.054 (esperado ≈ 0,05).

## Poder para detectar 5% de diferença

| Métrica | Comando | Pipeline | CV piloto (%) | Poder n=30 (α=0,05) | Poder n=30 (α=0,0025) | Menor n com poder ≥ 0,8 (α=0,0025) |
|---|---|---|---|---|---|---|
| M1 Vazão | GET | 1 | 8.33 | 0.61 | 0.17 | > 50 |
| M2 Latência p50 | GET | 1 | 8.14 | 0.60 | 0.18 | > 50 |
| M3 Latência p99 | GET | 1 | 10.83 | 0.37 | 0.07 | > 50 |
| M4 Memória | GET | 1 | 0.16 | 1.00 | 1.00 | 10.0 |
| M5 CPU | GET | 1 | 0.23 | 1.00 | 1.00 | 10.0 |
| M1 Vazão | GET | 16 | 11.54 | 0.34 | 0.07 | > 50 |
| M2 Latência p50 | GET | 16 | 12.46 | 0.30 | 0.06 | > 50 |
| M3 Latência p99 | GET | 16 | 23.38 | 0.12 | 0.01 | > 50 |
| M4 Memória | GET | 16 | 0.15 | 1.00 | 1.00 | 10.0 |
| M5 CPU | GET | 16 | 0.28 | 1.00 | 1.00 | 10.0 |
| M1 Vazão | SET | 1 | 8.02 | 0.61 | 0.20 | > 50 |
| M2 Latência p50 | SET | 1 | 7.52 | 0.68 | 0.24 | > 50 |
| M3 Latência p99 | SET | 1 | 9.22 | 0.51 | 0.11 | > 50 |
| M4 Memória | SET | 1 | 0.33 | 1.00 | 1.00 | 10.0 |
| M5 CPU | SET | 1 | 0.21 | 1.00 | 1.00 | 10.0 |
| M1 Vazão | SET | 16 | 4.95 | 0.95 | 0.68 | 40.0 |
| M2 Latência p50 | SET | 16 | 3.73 | 1.00 | 0.96 | 30.0 |
| M3 Latência p99 | SET | 16 | 16.26 | 0.20 | 0.02 | > 50 |
| M4 Memória | SET | 16 | 0.18 | 1.00 | 1.00 | 10.0 |
| M5 CPU | SET | 16 | 0.28 | 1.00 | 1.00 | 10.0 |

## Decisão

11 de 20 combinações métrica × condição ficam com poder < 0,8 em n = 30 (α corrigido):
- M1 Vazão, GET p=1 (CV 8.3%): poder 0.17
- M2 Latência p50, GET p=1 (CV 8.1%): poder 0.18
- M3 Latência p99, GET p=1 (CV 10.8%): poder 0.07
- M1 Vazão, GET p=16 (CV 11.5%): poder 0.07
- M2 Latência p50, GET p=16 (CV 12.5%): poder 0.06
- M3 Latência p99, GET p=16 (CV 23.4%): poder 0.01
- M1 Vazão, SET p=1 (CV 8.0%): poder 0.20
- M2 Latência p50, SET p=1 (CV 7.5%): poder 0.24
- M3 Latência p99, SET p=1 (CV 9.2%): poder 0.11
- M1 Vazão, SET p=16 (CV 4.9%): poder 0.68
- M3 Latência p99, SET p=16 (CV 16.3%): poder 0.02
