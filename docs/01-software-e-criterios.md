# 1. Software escolhido e comprovação dos três critérios

## 1.1 Software

**Redis × Valkey**: servidores de estrutura de dados em memória (chave-valor), usados principalmente como **cache**, armazenamento de sessão, fila e *rate limiting*.

| | Redis | Valkey |
|---|---|---|
| Site oficial | https://redis.io | https://valkey.io |
| Mantenedor | Redis Ltd. | Linux Foundation (comunidade) |
| Origem | Projeto original (2009) | *Fork* do Redis 7.2.4, criado em março de 2024 após a mudança de licença do Redis |
| Licença atual | RSALv2 / SSPLv1 / AGPLv3 (a partir do 8.0) | BSD-3-Clause |
| Imagem oficial | `redis` (Docker Official Image) | `valkey/valkey` |

**Por que estudar os dois juntos.** Desde 2024, quem opera Redis em produção tem uma decisão real a tomar: continuar no Redis ou migrar para o Valkey, que é compatível com o mesmo protocolo (RESP) e com os mesmos clientes. Provedores de nuvem já oferecem o Valkey como serviço gerenciado (ex.: AWS ElastiCache for Valkey, https://aws.amazon.com/elasticache/what-is-valkey/). A pergunta que importa para quem usa é se essa troca altera o desempenho do serviço.

## 1.2 Evidências dos três critérios

Todos os números abaixo foram consultados em **17/11/2026** nas fontes indicadas. A coleta foi automatizada pelo script `scripts/coleta_impacto.py` (tarefa 4), que grava os mesmos números, com a URL e a data, em `data/impacto/`.

### Critério 1: Real

| Evidência | Redis | Valkey | Fonte |
|---|---|---|---|
| Site oficial e documentação | redis.io | valkey.io | https://redis.io · https://valkey.io |
| Imagem oficial no Docker Hub | `redis` | `valkey/valkey` | https://hub.docker.com/_/redis · https://hub.docker.com/r/valkey/valkey |
| Estrelas no GitHub (só como sinal de adoção) | 77.687 | 27.735 | https://api.github.com/repos/redis/redis · https://api.github.com/repos/valkey-io/valkey |
| Fórmula oficial no Homebrew | `redis` | `valkey` | https://formulae.brew.sh/formula/redis · https://formulae.brew.sh/formula/valkey |

### Critério 2: Em operação

| Evidência | Redis | Valkey | Fonte |
|---|---|---|---|
| Versão estável mais recente | 8.10.3 | 9.1.3 | https://endoflife.date/redis · https://endoflife.date/valkey |
| Data do último release | 26/10/2026 | 26/10/2026 | GitHub Releases API (`/releases/latest`) |
| Ciclos de versão ainda mantidos | 8.10, 8.8, 8.6, 8.4, 8.2, 8.0, 7.4, 7.2, 6.2 | 9.1, 9.0, 8.1, 8.0, 7.2 | https://endoflife.date/api/redis.json · https://endoflife.date/api/valkey.json |
| Última atualização da imagem oficial | 16/11/2026 | 17/11/2026 | Docker Hub API |
| Oferta como serviço gerenciado em nuvem | Sim (Redis Cloud, Azure, AWS) | Sim (AWS ElastiCache for Valkey) | https://aws.amazon.com/elasticache/what-is-valkey/ |

### Critério 3: Alto impacto

| Evidência | Redis | Valkey | Fonte |
|---|---|---|---|
| *Pulls* da imagem oficial no Docker Hub | **11,70 bilhões** | **410,9 milhões** | https://hub.docker.com/v2/repositories/library/redis/ · https://hub.docker.com/v2/repositories/valkey/valkey/ |
| Posição no DB-Engines (geral) | **8º** | 87º | https://db-engines.com/en/system/Redis · https://db-engines.com/en/system/Valkey |
| Posição no DB-Engines (*key-value stores*) | **1º** | 12º | idem |
| Downloads do cliente Python no último mês (PyPI) | 242,1 milhões (`redis`) | ver `data/impacto/` (`valkey`) | https://pypistats.org/api/packages/redis/recent |
| Downloads de clientes Node.js no último mês (npm) | 81,2 mi (`redis`) + 165,9 mi (`ioredis`) | 3,8 mi (`iovalkey`) + 2,7 mi (`@valkey/valkey-glide`) | https://api.npmjs.org/downloads/point/last-month/ |
| Instalações via Homebrew nos últimos 365 dias | 346.085 | 13.839 | https://formulae.brew.sh/api/formula/redis.json · https://formulae.brew.sh/api/formula/valkey.json |

**Leitura.** O Redis é o banco chave-valor mais popular do mundo (1º no DB-Engines na categoria) e sua imagem oficial passa de 11 bilhões de *pulls*. O Valkey é mais novo (2024), mas já soma mais de 400 milhões de *pulls* e é oferecido por grandes provedores de nuvem. Como os dois falam o mesmo protocolo, **qualquer diferença de desempenho entre eles afeta diretamente a base instalada do Redis que está avaliando a migração**.

> Observação sobre escalas: *pulls* e downloads são contagens (escala de razão); a posição no DB-Engines é **ordinal** e só permite comparações de ordem (não faz sentido dizer que o Redis é "10 vezes mais popular" por estar em 8º contra 87º).
