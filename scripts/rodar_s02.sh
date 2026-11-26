#!/usr/bin/env bash
# Roda a S02 de ponta a ponta na maquina do estudo (docs/05, secao 5.3):
#
#   1. mini-piloto (3 repeticoes por tratamento, ~26 min)
#   2. portoes: criterio de deriva (ordem.md) e de poder (poder.md) precisam dar APROVADO
#   3. coleta completa (50 repeticoes por tratamento, ~5 h 35 min)
#   4. validacao, analise, diagnostico de deriva e simulacao de poder da coleta completa
#
# Se um portao reprovar, o script para antes da coleta completa: corrija o
# ambiente e rode de novo (o mini-piloto anterior e renomeado com a data).
#
# Uso (na raiz do repositorio, na tomada e com o governador performance):
#     bash scripts/rodar_s02.sh                  # tudo
#     bash scripts/rodar_s02.sh --so-minipiloto  # para depois dos portoes
#     bash scripts/rodar_s02.sh --so-analise     # so o passo 4 (coleta completa ja feita)
#
# Os argumentos extras vao para o coleta_experimento.py (por exemplo,
# --cpus-servidor 0,4 --cpus-cliente 1-3,5-7 em outra topologia).

set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
ETAPA="tudo"
EXTRAS=()
for a in "$@"; do
  case "$a" in
    --so-minipiloto) ETAPA="minipiloto" ;;
    --so-analise) ETAPA="analise" ;;
    *) EXTRAS+=("$a") ;;
  esac
done

passo() { printf '\n=== %s (%s) ===\n' "$1" "$(date '+%H:%M')"; }

analisar() {
  local coleta="$1"
  "$PY" scripts/validacao_dados.py --coleta "$coleta"
  "$PY" scripts/diagnostico_ordem.py --coleta "$coleta" > /dev/null
  "$PY" scripts/simulacao_poder.py --coleta "$coleta" > /dev/null
}

aprovado() {  # aprovado <arquivo> <texto que indica aprovacao>
  grep -qF "$2" "$1"
}

if [[ "$ETAPA" != "analise" ]]; then
  if [[ -e data/processed/minipiloto_execucoes.csv ]]; then
    sufixo="$(date '+%Y%m%d-%H%M')"
    echo "Mini-piloto anterior guardado como minipiloto-$sufixo"
    mv data/processed/minipiloto_execucoes.csv "data/processed/minipiloto-${sufixo}_execucoes.csv"
    rm -f data/processed/minipiloto_validado.csv
    [[ -d data/raw/minipiloto ]] && mv data/raw/minipiloto "data/raw/minipiloto-$sufixo"
    [[ -d results/minipiloto ]] && mv results/minipiloto "results/minipiloto-$sufixo"
  fi

  passo "1/4 mini-piloto"
  "$PY" scripts/coleta_experimento.py --coleta minipiloto --repeticoes 3 ${EXTRAS[@]+"${EXTRAS[@]}"}
  analisar minipiloto

  passo "2/4 portoes"
  ok=1
  if aprovado results/minipiloto/ordem.md "**Resultado: APROVADO**"; then
    echo "deriva (results/minipiloto/ordem.md): APROVADO"
  else
    echo "deriva (results/minipiloto/ordem.md): REPROVADO"; sed -n '/^## Critério de aceite/,/^## Tendência/p' results/minipiloto/ordem.md; ok=0
  fi
  if aprovado results/minipiloto/poder.md "**APROVADO:**"; then
    echo "poder  (results/minipiloto/poder.md): APROVADO"
  else
    echo "poder  (results/minipiloto/poder.md): REPROVADO"; sed -n '/^## Decisão/,$p' results/minipiloto/poder.md; ok=0
  fi
  if [[ "$ok" != 1 ]]; then
    echo; echo "Portao reprovado: corrija o ambiente (docs/05, D1) e rode de novo. A coleta completa NAO foi iniciada."
    exit 1
  fi
  [[ "$ETAPA" == "minipiloto" ]] && { echo "Portoes aprovados. Rode sem --so-minipiloto para a coleta completa."; exit 0; }

  passo "3/4 coleta completa (~5 h 35 min)"
  "$PY" scripts/coleta_experimento.py --coleta completa --repeticoes 50 ${EXTRAS[@]+"${EXTRAS[@]}"}
fi

passo "4/4 analise da coleta completa"
analisar completa
"$PY" scripts/analise.py --coleta completa > /dev/null
grep -F "Resultado:" results/completa/ordem.md || true

cat <<'FIM'

Pronto. Para versionar (tarefa 13), numa branch nova:
    git add data/raw/minipiloto data/processed/minipiloto_* results/minipiloto \
            data/raw/completa data/processed/completa_* results/completa
    git commit -m "data: adiciona mini-piloto e coleta completa da S02"
FIM
