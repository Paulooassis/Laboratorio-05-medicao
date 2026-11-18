# Script de coleta das evidências de impacto

`coleta_impacto.py` consulta fontes públicas e salva, em CSV e JSON, os números que comprovam que o **Redis** e o **Valkey** são reais, estão em operação e têm alto impacto.

## Como rodar

```bash
py scripts/coleta_impacto.py                  # Windows
python3 scripts/coleta_impacto.py             # Linux/macOS
python3 scripts/coleta_impacto.py --saida outra/pasta
```

O script usa só a biblioteca padrão do Python (3.9+), então não é preciso instalar nada. Para aumentar o limite da API do GitHub, defina a variável `GITHUB_TOKEN` (opcional).

## Saída

São gerados dois arquivos em `data/impacto/`, com a data da coleta no nome:

- `impacto_AAAA-MM-DD.csv`: uma linha por número coletado.
- `impacto_AAAA-MM-DD.json`: os mesmos registros, mais metadados da coleta e a lista de erros (se alguma fonte falhar, as outras continuam).

| Coluna | Conteúdo |
|---|---|
| `data_coleta` | Data e hora da coleta (ISO 8601, com fuso) |
| `software` | `Redis` ou `Valkey` |
| `criterio` | `real`, `em_operacao` ou `alto_impacto` |
| `fonte` | Nome da fonte (Docker Hub, GitHub API, PyPI Stats, npm, Homebrew, endoflife.date, DB-Engines) |
| `metrica` | Nome do número coletado |
| `valor` | O número (ou a versão/data) |
| `unidade` | Unidade ou escala do valor |
| `url` | URL exata consultada (fonte do número) |
| `observacao` | Ressalvas sobre o número |

## Fontes consultadas

| Fonte | O que coleta | Critério |
|---|---|---|
| Docker Hub API | *pulls*, estrelas e última atualização das imagens oficiais | alto impacto / em operação |
| GitHub API | estrelas, forks e último *release* (só como evidência de adoção, sem minerar o repositório) | real / em operação |
| PyPI Stats | downloads mensais dos clientes Python `redis` e `valkey` | alto impacto |
| npm | downloads mensais de `redis`, `ioredis`, `iovalkey` e `@valkey/valkey-glide` | alto impacto |
| Homebrew | versão estável e instalações em 30 e 365 dias | em operação / alto impacto |
| endoflife.date | ciclos de versão mantidos e último *release* | em operação |
| DB-Engines | posição no ranking geral e de *key-value stores* (escala ordinal) | alto impacto |

## Regras de ética

- No máximo **1 requisição por segundo** (pausa mínima de 1,1 s entre chamadas). Se uma fonte responder `429`, o script espera e tenta de novo.
- Apenas endpoints públicos. O `robots.txt` do DB-Engines permite o acesso.
- *User-Agent* genérico, sem dados pessoais dos integrantes. Nenhum dado pessoal é coletado.
