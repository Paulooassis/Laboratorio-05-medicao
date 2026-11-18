"""Coleta automatizada das evidencias de impacto do Redis e do Valkey.

Consulta fontes publicas (Docker Hub, GitHub API, PyPI Stats, npm, Homebrew,
endoflife.date e DB-Engines) e salva os numeros em CSV e JSON, com a data da
coleta e a fonte (URL) de cada numero.

Regras de etica seguidas:
- no maximo 1 requisicao por segundo (pausa entre chamadas);
- apenas endpoints publicos, sem autenticacao obrigatoria e sem dados pessoais;
- User-Agent generico identificando a ferramenta, sem dados dos integrantes.

Uso:
    py scripts/coleta_impacto.py                 # salva em data/impacto/
    py scripts/coleta_impacto.py --saida outra/pasta

Opcional: defina GITHUB_TOKEN para aumentar o limite da API do GitHub.
Usa apenas a biblioteca padrao do Python (3.9+).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

USER_AGENT = "lab05-impacto-coleta/1.0 (pesquisa academica)"
INTERVALO_MIN_S = 1.1  # garante < 1 requisicao por segundo
TIMEOUT_S = 30
TENTATIVAS = 4  # tentativas por URL quando a fonte responde 429

_ultima_req = 0.0


@dataclass
class Registro:
    data_coleta: str
    software: str
    criterio: str  # real | em_operacao | alto_impacto
    fonte: str
    metrica: str
    valor: object
    unidade: str
    url: str
    observacao: str = ""


@dataclass
class Coleta:
    data_coleta: str
    registros: list[Registro] = field(default_factory=list)
    erros: list[dict] = field(default_factory=list)

    def add(self, **kw) -> None:
        self.registros.append(Registro(data_coleta=self.data_coleta, **kw))

    def erro(self, fonte: str, url: str, exc: Exception) -> None:
        self.erros.append({"fonte": fonte, "url": url, "erro": repr(exc)})
        print(f"  [erro] {fonte}: {exc}", file=sys.stderr)


def _get(url: str, aceita_json: bool = True) -> object:
    """GET respeitando o intervalo minimo entre requisicoes."""
    global _ultima_req
    espera = INTERVALO_MIN_S - (time.monotonic() - _ultima_req)
    if espera > 0:
        time.sleep(espera)

    headers = {"User-Agent": USER_AGENT}
    if aceita_json:
        headers["Accept"] = "application/json"
    if "api.github.com" in url and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"

    req = urllib.request.Request(url, headers=headers)
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                corpo = resp.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            # 429 = limite da fonte: espera e tenta de novo (backoff crescente)
            if e.code != 429 or tentativa == TENTATIVAS:
                raise
            pausa = max(int(e.headers.get("Retry-After") or 0), 10 * tentativa)
            print(f"  429 em {url}; nova tentativa em {pausa}s", file=sys.stderr)
            time.sleep(pausa)
        finally:
            _ultima_req = time.monotonic()
    print(f"  GET {url}")
    return json.loads(corpo) if aceita_json else corpo


# --------------------------------------------------------------------------- #
# Fontes
# --------------------------------------------------------------------------- #

def docker_hub(c: Coleta, software: str, repo: str) -> None:
    url = f"https://hub.docker.com/v2/repositories/{repo}/"
    try:
        d = _get(url)
    except Exception as e:  # noqa: BLE001
        return c.erro("Docker Hub", url, e)
    obs = f"imagem {repo}"
    c.add(software=software, criterio="alto_impacto", fonte="Docker Hub",
          metrica="pulls_total", valor=d.get("pull_count"), unidade="pulls",
          url=url, observacao=obs)
    c.add(software=software, criterio="alto_impacto", fonte="Docker Hub",
          metrica="estrelas_docker_hub", valor=d.get("star_count"),
          unidade="estrelas", url=url, observacao=obs)
    c.add(software=software, criterio="em_operacao", fonte="Docker Hub",
          metrica="imagem_ultima_atualizacao", valor=d.get("last_updated"),
          unidade="data ISO 8601", url=url, observacao=obs)


def github(c: Coleta, software: str, repo: str) -> None:
    url = f"https://api.github.com/repos/{repo}"
    try:
        d = _get(url)
        c.add(software=software, criterio="real", fonte="GitHub API",
              metrica="estrelas_github", valor=d.get("stargazers_count"),
              unidade="estrelas", url=url,
              observacao="apenas evidencia de adocao; o repositorio nao e objeto de pesquisa")
        c.add(software=software, criterio="real", fonte="GitHub API",
              metrica="forks_github", valor=d.get("forks_count"),
              unidade="forks", url=url)
    except Exception as e:  # noqa: BLE001
        c.erro("GitHub API", url, e)

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        d = _get(url)
        c.add(software=software, criterio="em_operacao", fonte="GitHub API",
              metrica="ultimo_release_versao", valor=d.get("tag_name"),
              unidade="versao", url=url)
        c.add(software=software, criterio="em_operacao", fonte="GitHub API",
              metrica="ultimo_release_data", valor=d.get("published_at"),
              unidade="data ISO 8601", url=url)
    except Exception as e:  # noqa: BLE001
        c.erro("GitHub API (release)", url, e)


def pypi(c: Coleta, software: str, pacote: str) -> None:
    url = f"https://pypistats.org/api/packages/{pacote}/recent"
    try:
        d = _get(url)["data"]
    except Exception as e:  # noqa: BLE001
        return c.erro("PyPI Stats", url, e)
    c.add(software=software, criterio="alto_impacto", fonte="PyPI Stats",
          metrica="downloads_cliente_python_ultimo_mes", valor=d.get("last_month"),
          unidade="downloads/mes", url=url,
          observacao=f"cliente oficial em Python: pacote '{pacote}'")


def npm(c: Coleta, software: str, pacote: str) -> None:
    url = f"https://api.npmjs.org/downloads/point/last-month/{pacote}"
    try:
        d = _get(url)
    except Exception as e:  # noqa: BLE001
        return c.erro("npm", url, e)
    c.add(software=software, criterio="alto_impacto", fonte="npm",
          metrica=f"downloads_npm_ultimo_mes[{pacote}]", valor=d.get("downloads"),
          unidade="downloads/mes", url=url,
          observacao=f"cliente Node.js '{pacote}', periodo {d.get('start')} a {d.get('end')}")


def homebrew(c: Coleta, software: str, formula: str) -> None:
    url = f"https://formulae.brew.sh/api/formula/{formula}.json"
    try:
        d = _get(url)
    except Exception as e:  # noqa: BLE001
        return c.erro("Homebrew", url, e)
    c.add(software=software, criterio="em_operacao", fonte="Homebrew",
          metrica="versao_estavel_homebrew", valor=d.get("versions", {}).get("stable"),
          unidade="versao", url=url)
    inst = d.get("analytics", {}).get("install", {})
    for periodo in ("30d", "365d"):
        valor = inst.get(periodo, {}).get(formula)
        c.add(software=software, criterio="alto_impacto", fonte="Homebrew",
              metrica=f"instalacoes_homebrew_{periodo}", valor=valor,
              unidade="instalacoes", url=url,
              observacao="apenas macOS/Linux via Homebrew (subestima o total)")


def endoflife(c: Coleta, software: str, produto: str) -> None:
    url = f"https://endoflife.date/api/{produto}.json"
    try:
        ciclos = _get(url)
    except Exception as e:  # noqa: BLE001
        return c.erro("endoflife.date", url, e)
    hoje = c.data_coleta[:10]

    def suportado(ciclo: dict) -> bool:
        eol = ciclo.get("eol")
        if isinstance(eol, bool):
            return not eol
        return eol is None or str(eol) > hoje

    mantidas = [x["cycle"] for x in ciclos if suportado(x)]
    c.add(software=software, criterio="em_operacao", fonte="endoflife.date",
          metrica="versoes_mantidas", valor=";".join(mantidas),
          unidade="ciclos de versao", url=url,
          observacao="ciclos sem data de fim de suporte vencida na data da coleta")
    if ciclos:
        c.add(software=software, criterio="em_operacao", fonte="endoflife.date",
              metrica="versao_mais_recente", valor=ciclos[0].get("latest"),
              unidade="versao", url=url)
        c.add(software=software, criterio="em_operacao", fonte="endoflife.date",
              metrica="versao_mais_recente_data", valor=ciclos[0].get("latestReleaseDate"),
              unidade="data", url=url)


_RE_RANK = re.compile(
    r"#(\d+)<th class=dbi_mini>&nbsp;&nbsp;<a href=\"[^\"]+\">([^<]+)</a>")


def db_engines(c: Coleta, software: str, sistema: str) -> None:
    url = f"https://db-engines.com/en/system/{sistema}"
    try:
        html = _get(url, aceita_json=False)
    except Exception as e:  # noqa: BLE001
        return c.erro("DB-Engines", url, e)
    achados = _RE_RANK.findall(html)
    if not achados:
        return c.erro("DB-Engines", url, ValueError("ranking nao encontrado no HTML"))
    for posicao, categoria in achados:
        c.add(software=software, criterio="alto_impacto", fonte="DB-Engines",
              metrica=f"posicao_ranking[{categoria.strip()}]", valor=int(posicao),
              unidade="posicao (ordinal)", url=url,
              observacao="ranking de popularidade, atualizado mensalmente")


# --------------------------------------------------------------------------- #
# Configuracao do estudo
# --------------------------------------------------------------------------- #

FONTES = {
    "Redis": [
        (docker_hub, "library/redis"),
        (github, "redis/redis"),
        (pypi, "redis"),
        (npm, "redis"),
        (npm, "ioredis"),
        (homebrew, "redis"),
        (endoflife, "redis"),
        (db_engines, "Redis"),
    ],
    "Valkey": [
        (docker_hub, "valkey/valkey"),
        (github, "valkey-io/valkey"),
        (pypi, "valkey"),
        (npm, "iovalkey"),
        (npm, "@valkey/valkey-glide"),
        (homebrew, "valkey"),
        (endoflife, "valkey"),
        (db_engines, "Valkey"),
    ],
}


def salvar(c: Coleta, pasta: Path) -> tuple[Path, Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    dia = c.data_coleta[:10]
    arq_csv = pasta / f"impacto_{dia}.csv"
    arq_json = pasta / f"impacto_{dia}.json"

    campos = list(Registro.__dataclass_fields__)
    with arq_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for r in c.registros:
            w.writerow(asdict(r))

    with arq_json.open("w", encoding="utf-8") as f:
        json.dump({
            "data_coleta": c.data_coleta,
            "user_agent": USER_AGENT,
            "intervalo_minimo_entre_requisicoes_s": INTERVALO_MIN_S,
            "total_registros": len(c.registros),
            "registros": [asdict(r) for r in c.registros],
            "erros": c.erros,
        }, f, ensure_ascii=False, indent=2)
    return arq_csv, arq_json


def main() -> int:
    raiz = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--saida", type=Path, default=raiz / "data" / "impacto",
                   help="pasta de saida (padrao: data/impacto)")
    args = p.parse_args()

    c = Coleta(data_coleta=datetime.now().astimezone().isoformat(timespec="seconds"))
    print(f"Coleta iniciada em {c.data_coleta}")
    for software, fontes in FONTES.items():
        print(f"\n[{software}]")
        for funcao, alvo in fontes:
            funcao(c, software, alvo)

    arq_csv, arq_json = salvar(c, args.saida)
    print(f"\n{len(c.registros)} registros salvos em:\n  {arq_csv}\n  {arq_json}")
    if c.erros:
        print(f"{len(c.erros)} fonte(s) com erro (ver campo 'erros' no JSON).")
    return 0 if c.registros else 1


if __name__ == "__main__":
    sys.exit(main())
