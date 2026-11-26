# 6. Coleta completa, validação e análise (Lab05S02)

Este documento cobre as tarefas 12 (coleta completa), 13 (validação), 14a (descritiva e gráficos) e 14c (interação com o *pipeline*). Os testes de hipótese de H-1 a H-5 (14b) e as ameaças à validade (15) estão em outras tarefas.

> **Situação em 26/11/2026:** os scripts e o procedimento estão prontos e testados (pytest e uma rodada de ponta a ponta sobre os dados do piloto). **A coleta completa ainda não foi executada.** Ela exige ~6 h com a máquina do estudo parada (seção 6.1), o que não coube no prazo da sprint. As seções de resultados (6.6) serão preenchidas depois da coleta, com os mesmos comandos.

## 6.1 Tarefa 12: procedimento da coleta completa

A coleta segue o protocolo do [docs/05](05-revisao-piloto-tamanho-amostra.md): mini-piloto como portão, n = 50 por tratamento, 12 tratamentos (8 de carga saturada + 4 de carga fixa a 50.000 ops/s), ordem em blocos completos aleatorizados.

### Antes de começar (máquina do estudo)

```bash
sudo cpupower frequency-set -g performance   # o coletor recusa outro governador
powerprofilesctl set performance
# notebook na tomada, navegador e outros apps fechados, sem usar a máquina até o fim
```

O coletor confere a tomada e o governador antes de começar e para se algo estiver fora do protocolo. O resultado da checagem fica em `data/raw/<coleta>/metadados.json` (`verificacao_ambiente`).

### Passo 1: mini-piloto, o portão (~26 min)

```bash
python3 scripts/coleta_experimento.py --coleta minipiloto --repeticoes 3
python3 scripts/validacao_dados.py   --coleta minipiloto
python3 scripts/diagnostico_ordem.py --coleta minipiloto   # results/minipiloto/ordem.md -> "Critério de aceite"
python3 scripts/simulacao_poder.py   --coleta minipiloto   # results/minipiloto/poder.md -> "Decisão"
```

Só siga para o passo 2 se **os dois** saírem **APROVADO**. Se algum sair REPROVADO, ache a fonte do ruído (processo em segundo plano, temperatura, governador), corrija e repita o mini-piloto. **Não** aumente o n para compensar (docs/05, seção 5.3).

### Passo 2: coleta completa (~5 h 35 min, 612 execuções)

```bash
python3 scripts/coleta_experimento.py --coleta completa --repeticoes 50
```

Uma falha numa execução não para a coleta: ela vai para o log e para o CSV com `status=erro`, e a execução é repetida (até 3 tentativas). Se a coleta for interrompida (Ctrl+C, queda de energia), os contêineres são removidos e o CSV mantém as linhas já gravadas. Nesse caso, apague `data/processed/completa_execucoes.csv` e `data/raw/completa/` e recomece. O coletor não retoma uma coleta pela metade, porque isso quebraria os blocos aleatorizados.

### Passo 3: validação, análise e diagnóstico (alguns minutos)

```bash
python3 scripts/validacao_dados.py   --coleta completa
python3 scripts/diagnostico_ordem.py --coleta completa   # critério de aceite da deriva
python3 scripts/analise.py           --coleta completa   # descritiva, gráficos e testes H-1 a H-5
python3 scripts/interacao.py         --coleta completa   # H-6
python3 scripts/simulacao_poder.py   --coleta completa   # poder alcançado com o CV real
```

### O que é versionado

| Arquivo | Conteúdo |
|---|---|
| `data/raw/completa/` | JSON bruto do memtier e `_meta.json` de cada execução, `metadados.json` (semente, plano, ambiente, *digests*) e `coleta.log` |
| `data/processed/completa_execucoes.csv` | Uma linha por execução, inclusive as inválidas e as de aquecimento |
| `data/processed/completa_validado.csv` | Mesmas linhas, mais `valido`, `motivo_descarte` e `outliers` |
| `results/completa/` | Tabelas e gráficos das seções 6.2 a 6.5 |

Os dados do mini-piloto também são versionados (`minipiloto`), mas não entram na análise final.

## 6.2 Tarefa 13: validação

`validacao_dados.py` aplica as regras V1 a V10 ([scripts/README.md](../scripts/README.md#validacao_dadospy-validação-dos-dados)). O que mudou nesta tarefa:

- **Registros inválidos documentados um a um.** O `validacao.md` passou a ter a seção "Execuções descartadas por problema", com o `run_id` e o motivo de cada execução descartada (aquecimento à parte). O mesmo vai para o `validacao.json` (`descartados_detalhe`). Antes só havia a contagem por motivo.
- **Outliers:** continuam só sinalizados (coluna `outliers` e tabela no `validacao.md`), sem remoção automática.
- **Execuções repetidas:** quando uma execução é inválida, o coletor a repete. A tentativa inválida fica no CSV, descartada pela V1, e a válida entra com o mesmo tratamento e a mesma repetição.

## 6.3 Tarefa 14a: estatística descritiva e gráficos

`analise.py` gera, por tratamento (software × comando × *pipeline* × carga) e métrica: n, média, mediana, desvio-padrão, CV, mínimo, máximo, Q1, Q3, IQR e IC 95% da mediana por *bootstrap* (`descritiva.md` / `.csv`).

Gráficos em `results/<coleta>/`:

| Gráfico | O que mostra |
|---|---|
| `boxplot_<métrica>.png` | Distribuição de M1–M5 por software em cada condição, com os pontos de cada execução |
| `ecdf_lat_p50_ms.png`, `ecdf_lat_p99_ms.png` | **Novo nesta tarefa.** ECDF das latências por execução, uma curva por software, em cada condição. Previsto no plano de análise (docs/03, seção 3.5) e ainda não gerado. Mostra se um software é mais lento em toda a distribuição ou só em algumas execuções |
| `interacao_vazao.png` | Vazão mediana por *pipeline*, uma linha por software (visual de H-6) |

## 6.4 Tarefa 14c: interação software × *pipeline* (H-6)

**Pergunta (Q4):** a diferença entre Valkey e Redis muda quando os comandos são enviados em *pipeline*?

**H-6** (docs/03): a diferença Valkey − Redis na vazão (M1) **não depende** do *pipeline* (H0) × depende (H1). M2 e M3 passam pela mesma análise, mas como análise exploratória, porque Q4 pede M1–M3 estratificadas e só M1 tem hipótese formal.

Novo script: `scripts/interacao.py`. Só usa as execuções de carga saturada: na carga fixa o *pipeline* é sempre 1, então não há o que cruzar.

| Passo | Como |
|---|---|
| Teste | ANOVA fatorial 2×2 (software × *pipeline*) tipo III, por comando. Se os resíduos não forem normais (Shapiro-Wilk, α = 0,05), usa a **ART ANOVA** (*Aligned Rank Transform*, Wobbrock et al., 2011), como no plano |
| Tamanho do efeito | η² parcial do termo de interação (0,01 pequeno, 0,06 médio, 0,14 grande) |
| Relevância prática | Diferença % das medianas (Valkey − Redis) em cada *pipeline*, com IC 95% por *bootstrap*, e a **diferença das diferenças** (p=16 − p=1, em pontos percentuais), com IC 95% |
| Comparações múltiplas | Holm dentro de cada métrica (2 testes: GET e SET). A família de H-6 é separada da família de 18 testes de H-1 a H-5 |
| Conclusão | Combina o teste com o IC. Uma interação só é dita **irrelevante na prática** se o IC da diferença das diferenças ficar **inteiro** dentro de ±5 p.p., o limiar de relevância do plano. Se não rejeitar H0 e o IC passar de ±5 p.p., o resultado é **inconclusivo**, e não "sem interação" |

Saídas: `interacao.md` / `.csv` e `interacao_<métrica>.png` (diferença Valkey − Redis por *pipeline*, com IC 95% e a faixa de ±5%).

**Por que a diferença das diferenças, e não só o p-valor.** Com n = 50 por célula, uma interação de 1 a 2 p.p. pode sair significativa sem importar para quem opera o serviço. Na direção contrária, um p alto com IC largo não prova que a interação não existe. O IC em pontos percentuais responde direto à pergunta de quem usa o software: "o ganho (ou a perda) de trocar para o Valkey muda se eu usar *pipeline*?".

**Teste de funcionamento sobre o piloto (n = 5 por célula, não é resultado do estudo).** Nenhuma interação em M1 (GET: p Holm = 0,31; SET: p Holm = 0,13), mas todos os ICs da diferença das diferenças passam de ±5 p.p. (por exemplo, GET: −3,2 p.p. [−22,2; 26,4]). Com n = 5, o resultado é inconclusivo, como esperado. Os arquivos de `results/piloto/` não foram regerados (docs/05: eles ficam na versão da S01).

**Testes automatizados** (`tests/test_interacao.py`): a ANOVA isola cada efeito e bate com a fórmula clássica no desenho balanceado; a ART detecta interação em dados assimétricos e não inventa interação num modelo aditivo; e há testes para o Holm, para a regra de conclusão e para a exclusão da carga fixa.

## 6.5 Ligação com as outras tarefas

| Tarefa | O que ela usa daqui |
|---|---|
| 14b Testes de hipótese (H-1 a H-5) | `analise.py` → `testes.md` (já existente) e os dados validados da seção 6.2 |
| 15 Ameaças à validade | Critério de deriva (`ordem.md`), *outliers* sinalizados, H-6 inconclusiva se o IC passar de ±5 p.p., e a limitação da ART com valores extremos (o alinhamento usa médias) |
| 16 Impacto | Diferenças % com IC (descritiva, testes e interação) |

## 6.6 Resultados da coleta completa

*A preencher depois da coleta (seção 6.1, passos 1 a 3):*

- [ ] Mini-piloto: critério de deriva e decisão de poder (APROVADO/REPROVADO)
- [ ] Coleta completa: data, duração, execuções válidas e descartadas por motivo (`results/completa/validacao.md`)
- [ ] Critério de aceite da deriva (`results/completa/ordem.md`)
- [ ] Descritiva por tratamento e gráficos principais (`descritiva.md`, `boxplot_*.png`, `ecdf_*.png`)
- [ ] H-6: decisão por comando e diferença das diferenças com IC (`interacao.md`, `interacao_ops_s.png`)
