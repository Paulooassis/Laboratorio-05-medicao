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
