# Testes Redis × Valkey: coleta `piloto`

Diferença = (mediana Valkey − mediana Redis) / mediana Redis. Efeito positivo: Valkey maior.

| Métrica | Comando | Pipeline | Med. Redis | Med. Valkey | Dif. (%) | Teste | p | p Holm | Efeito | Magnitude |
|---|---|---|---|---|---|---|---|---|---|---|
| M1 Vazão | GET | 1 | 118.114,13 | 117.248,25 | -0,7 | t de Welch | 0,9117 | 1,0000 | g de Hedges = -0,07 | desprezível |
| M1 Vazão | GET | 16 | 687.237,70 | 659.925,01 | -4,0 | t de Welch | 0,7119 | 1,0000 | g de Hedges = -0,22 | pequeno |
| M1 Vazão | SET | 1 | 118.478,93 | 114.364,94 | -3,5 | t de Welch | 0,8518 | 1,0000 | g de Hedges = -0,11 | desprezível |
| M1 Vazão | SET | 16 | 668.095,28 | 660.813,40 | -1,1 | t de Welch | 0,0730 | 1,0000 | g de Hedges = -1,18 | grande |
| M2 Latência p50 | GET | 1 | 1,50 | 1,53 | 2,1 | Mann-Whitney U | 0,1719 | 1,0000 | delta de Cliff = 0,56 | grande |
| M2 Latência p50 | GET | 16 | 4,42 | 4,58 | 3,6 | Mann-Whitney U | 0,4206 | 1,0000 | delta de Cliff = 0,36 | médio |
| M2 Latência p50 | SET | 1 | 1,51 | 1,57 | 3,7 | Mann-Whitney U | 0,1508 | 1,0000 | delta de Cliff = 0,60 | grande |
| M2 Latência p50 | SET | 16 | 4,54 | 4,77 | 4,9 | t de Welch | 0,0100 | 0,1603 | g de Hedges = 1,93 | grande |
| M3 Latência p99 | GET | 1 | 3,57 | 3,62 | 1,3 | t de Welch | 0,8776 | 1,0000 | g de Hedges = 0,09 | desprezível |
| M3 Latência p99 | GET | 16 | 8,57 | 9,09 | 6,0 | t de Welch | 0,8331 | 1,0000 | g de Hedges = -0,13 | desprezível |
| M3 Latência p99 | SET | 1 | 3,62 | 3,65 | 0,9 | t de Welch | 0,7421 | 1,0000 | g de Hedges = -0,19 | desprezível |
| M3 Latência p99 | SET | 16 | 9,79 | 9,02 | -7,8 | t de Welch | 0,9344 | 1,0000 | g de Hedges = -0,05 | desprezível |
| M4 Memória residente | GET | 1 | 60,41 | 48,19 | -20,2 | t de Welch | 0,0000 | 0,0000 | g de Hedges = -125,90 | grande |
| M4 Memória residente | GET | 16 | 61,25 | 49,00 | -20,0 | t de Welch | 0,0000 | 0,0000 | g de Hedges = -141,36 | grande |
| M4 Memória residente | SET | 1 | 60,30 | 48,27 | -19,9 | t de Welch | 0,0000 | 0,0000 | g de Hedges = -73,16 | grande |
| M4 Memória residente | SET | 16 | 60,47 | 48,20 | -20,3 | t de Welch | 0,0000 | 0,0000 | g de Hedges = -130,94 | grande |
| M5 CPU média | GET | 1 | 101,16 | 101,16 | 0,0 | t de Welch | 0,7027 | 1,0000 | g de Hedges = -0,23 | pequeno |
| M5 CPU média | GET | 16 | 101,15 | 101,05 | -0,1 | t de Welch | 0,8275 | 1,0000 | g de Hedges = -0,13 | desprezível |
| M5 CPU média | SET | 1 | 101,30 | 101,11 | -0,2 | t de Welch | 0,1148 | 1,0000 | g de Hedges = -1,04 | grande |
| M5 CPU média | SET | 16 | 100,95 | 100,98 | 0,0 | t de Welch | 0,7614 | 1,0000 | g de Hedges = 0,18 | desprezível |
