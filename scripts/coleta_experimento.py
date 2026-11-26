"""Orquestra as execucoes do experimento Redis x Valkey.

Desenho fatorial 2 (software) x 2 (comando) x 2 (pipeline) = 8 tratamentos em
carga saturada, mais 2 (software) x 2 (comando) em carga fixa (pipeline 1,
--taxa-fixa ops/s no total, abaixo da saturacao), em que a CPU (M5) e comparavel
(docs/05-revisao-piloto-tamanho-amostra.md). Cada execucao e uma unidade
experimental independente:

    conteiner novo do servidor -> popula as chaves -> carga com memtier_benchmark
    (amostrando CPU com docker stats a cada ~1 s) -> INFO memory -> remove conteiner

A ordem e sorteada com semente fixa em blocos completos (--ordem blocos, padrao):
cada bloco tem uma execucao de cada tratamento, em ordem sorteada, para que uma
deriva da maquina ao longo da coleta se distribua igualmente entre os
tratamentos. O piloto usou o sorteio livre (--ordem sorteio --taxa-fixa 0).

Antes de coletar, o script confere se a maquina esta na tomada e com o
governador de CPU em `performance` (Linux) e para se nao estiver
(--ignorar-ambiente pula a checagem, e isso fica nos metadados).

Cada execucao gera:
- data/raw/<coleta>/<run_id>.json        saida bruta do memtier_benchmark
- data/raw/<coleta>/<run_id>_meta.json   amostras de CPU, INFO memory e versao
- uma linha em data/processed/<coleta>_execucoes.csv

Erros nao param a coleta: sao registrados em data/raw/<coleta>/coleta.log e na
coluna `status` do CSV, e a execucao e repetida (ate --tentativas vezes).

Etica: toda a carga e gerada e recebida dentro da maquina do grupo
(rede Docker local). Nenhum sistema de terceiros e acessado.

Uso:
    python3 scripts/coleta_experimento.py --coleta piloto --repeticoes 5
    python3 scripts/coleta_experimento.py --coleta minipiloto --repeticoes 3
    python3 scripts/coleta_experimento.py --coleta completa --repeticoes 50
    python3 scripts/coleta_experimento.py --coleta teste --repeticoes 1 --duracao 5 --dry-run

Requer Docker. Usa apenas a biblioteca padrao do Python (3.9+).
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import logging
import os
import platform
import random
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

SOFTWARES = {
    "redis": {"nome": "Redis", "imagem": "redis:8.10.3", "versao": "8.10.3", "cli": "redis-cli"},
    "valkey": {"nome": "Valkey", "imagem": "valkey/valkey:9.1.3", "versao": "9.1.3", "cli": "valkey-cli"},
}
IMAGEM_MEMTIER = "redislabs/memtier_benchmark:2.6.1"
COMANDOS = {"GET": "0:1", "SET": "1:0"}  # --ratio=<sets>:<gets>
PIPELINES = [1, 16]

# Parametros fixos (controlados), conforme docs/03-metricas-hipoteses-planos.md
THREADS = 4
CONEXOES = 50
TAMANHO_VALOR = 256
CHAVES = 100_000
REDE = "lab05-net"
TAXA_FIXA = 50_000  # ops/s no total na carga fixa: ~43% da vazao saturada com pipeline 1 no piloto

COLUNAS = [
    "run_id", "coleta", "ordem", "bloco", "tentativa", "aquecimento", "software", "versao",
    "versao_reportada", "comando", "pipeline", "taxa", "repeticao", "inicio", "fim",
    "ops_s", "lat_media_ms", "lat_p50_ms", "lat_p99_ms", "lat_p999_ms",
    "erros_conexao", "misses_s", "mem_rss_mib", "mem_usada_mib",
    "cpu_medio_pct", "cpu_amostras", "status", "erro",
]

log = logging.getLogger("coleta")
_conteineres_ativos: set[str] = set()


def docker(*args: str, timeout: float = 120, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=timeout, check=check)


def usuario_docker() -> list[str]:
    """Roda o memtier com o UID do usuario para o JSON nao ficar com dono root."""
    if hasattr(os, "getuid"):
        return ["--user", f"{os.getuid()}:{os.getgid()}"]
    return []


def remover(nome: str) -> None:
    docker("rm", "-f", nome, check=False, timeout=60)
    _conteineres_ativos.discard(nome)


def garantir_rede() -> None:
    if docker("network", "inspect", REDE, check=False).returncode != 0:
        docker("network", "create", REDE)


def esperar_servidor(nome: str, cli: str, limite_s: float = 20) -> None:
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        r = docker("exec", nome, cli, "PING", check=False, timeout=10)
        if r.stdout.strip() == "PONG":
            return
        time.sleep(0.3)
    raise RuntimeError(f"servidor {nome} nao respondeu PING em {limite_s}s")


def memtier(args: list[str], cpus: str, saida: Path, timeout: float) -> subprocess.CompletedProcess:
    cmd = ["run", "--rm", "--network", REDE, "--cpuset-cpus", cpus, *usuario_docker(),
           "-v", f"{saida.resolve()}:/out", IMAGEM_MEMTIER, *args]
    return docker(*cmd, timeout=timeout)


class AmostradorCPU(threading.Thread):
    """Le `docker stats` em modo streaming (~1 amostra por segundo)."""

    _num = re.compile(r"([\d.]+)%")

    def __init__(self, conteiner: str) -> None:
        super().__init__(daemon=True)
        self.conteiner = conteiner
        self.amostras: list[tuple[float, float]] = []
        self._proc: subprocess.Popen | None = None

    def run(self) -> None:
        self._proc = subprocess.Popen(
            ["docker", "stats", "--format", "{{.CPUPerc}}", self.conteiner],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        assert self._proc.stdout is not None
        for linha in self._proc.stdout:
            m = self._num.search(linha)
            if m:
                self.amostras.append((time.time(), float(m.group(1))))

    def parar(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


DESCARTE_INICIAL_S = 2.0  # conexoes abrindo + docker stats reporta o intervalo anterior


def janela_cpu(amostras: list[tuple[float, float]], inicio: float, fim: float) -> list[float]:
    """Amostras de CPU do regime estacionario da carga.

    O `docker stats` atualiza a tela a cada ~0,5 s e repete a mesma leitura, entao so
    se mantem leituras com pelo menos 0,75 s de distancia. Ficam as amostras entre
    `inicio + DESCARTE_INICIAL_S` e `fim` (horarios reportados pelo memtier).
    """
    dedup: list[tuple[float, float]] = []
    for t, v in amostras:
        if not dedup or t - dedup[-1][0] >= 0.75:
            dedup.append((t, v))
    return [v for t, v in dedup if inicio + DESCARTE_INICIAL_S <= t <= fim]


def info(nome: str, cli: str, secao: str) -> dict[str, str]:
    r = docker("exec", nome, cli, "INFO", secao, timeout=15)
    campos = {}
    for linha in r.stdout.splitlines():
        if ":" in linha and not linha.startswith("#"):
            k, v = linha.strip().split(":", 1)
            campos[k] = v
    return campos


def executar(exec_: dict, args: argparse.Namespace, dir_raw: Path) -> dict:
    sw = SOFTWARES[exec_["software"]]
    run_id = exec_["run_id"]
    nome = f"lab05-srv-{run_id}"
    linha = {k: "" for k in COLUNAS}
    linha.update({k: exec_[k] for k in ("run_id", "coleta", "ordem", "bloco", "tentativa", "aquecimento",
                                         "comando", "pipeline", "taxa", "repeticao")})
    linha.update(software=sw["nome"], versao=sw["versao"],
                 inicio=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    amostrador = None
    try:
        remover(nome)
        _conteineres_ativos.add(nome)
        docker("run", "-d", "--name", nome, "--network", REDE,
               "--cpuset-cpus", args.cpus_servidor, sw["imagem"])
        esperar_servidor(nome, sw["cli"])

        # 1) popula todas as chaves (necessario para o GET; feito em todos os tratamentos)
        memtier(["-s", nome, "-p", "6379", "-t", "1", "-c", "1", "--ratio=1:0",
                 "--key-pattern=P:P", f"--key-maximum={CHAVES}", "--requests=allkeys",
                 f"--data-size={TAMANHO_VALOR}", "--pipeline=64", "--hide-histogram"],
                args.cpus_cliente, dir_raw, timeout=120)

        # 2) carga medida, com amostragem de CPU em paralelo
        #    (carga fixa: --rate-limiting e por conexao, entao divide a taxa total)
        limite = [f"--rate-limiting={exec_['taxa'] // (THREADS * CONEXOES)}"] if exec_["taxa"] else []
        amostrador = AmostradorCPU(nome)
        amostrador.start()
        t0 = time.time()
        memtier(["-s", nome, "-p", "6379", "-t", str(THREADS), "-c", str(CONEXOES),
                 f"--test-time={args.duracao}", f"--data-size={TAMANHO_VALOR}",
                 f"--key-maximum={CHAVES}", "--key-pattern=R:R",
                 f"--ratio={COMANDOS[exec_['comando']]}", f"--pipeline={exec_['pipeline']}", *limite,
                 "--hide-histogram", f"--json-out-file=/out/{run_id}.json"],
                args.cpus_cliente, dir_raw, timeout=args.duracao + 90)
        t1 = time.time()
        amostrador.parar()

        # 3) memoria e versao do servidor ao final da carga
        mem = info(nome, sw["cli"], "memory")
        srv = info(nome, sw["cli"], "server")
        versao_rep = srv.get("valkey_version") or srv.get("redis_version", "")

        dados = json.loads((dir_raw / f"{run_id}.json").read_text())
        tot = dados["ALL STATS"]["Totals"]
        runtime = dados["ALL STATS"].get("Runtime", {})
        ini_carga = runtime.get("Start time", t0 * 1000) / 1000
        fim_carga = runtime.get("Finish time", t1 * 1000) / 1000
        janela = janela_cpu(amostrador.amostras, ini_carga, fim_carga)
        cpu = sum(janela) / len(janela) if janela else None
        pct = tot.get("Percentile Latencies", {})
        linha.update(
            versao_reportada=versao_rep,
            ops_s=tot["Ops/sec"],
            lat_media_ms=tot.get("Average Latency", tot.get("Latency")),
            lat_p50_ms=pct.get("p50.00"),
            lat_p99_ms=pct.get("p99.00"),
            lat_p999_ms=pct.get("p99.90"),
            erros_conexao=tot.get("Connection Errors", 0),
            misses_s=tot.get("Misses/sec", 0),
            mem_rss_mib=round(int(mem["used_memory_rss"]) / 2**20, 3),
            mem_usada_mib=round(int(mem["used_memory"]) / 2**20, 3),
            cpu_medio_pct=round(cpu, 3) if cpu is not None else "",
            cpu_amostras=len(janela),
        )
        (dir_raw / f"{run_id}_meta.json").write_text(json.dumps({
            "run_id": run_id, "execucao": exec_, "imagem": sw["imagem"],
            "inicio_carga": ini_carga, "fim_carga": fim_carga, "cpu_janela": janela,
            "cpu_amostras": amostrador.amostras, "info_memory": mem,
            "info_server": {k: srv.get(k) for k in ("redis_version", "valkey_version", "server_name",
                                                    "io_threads_active", "arch_bits", "os")},
        }, indent=2))

        problemas = []
        if not tot["Ops/sec"]:
            problemas.append("vazao zero")
        if tot.get("Connection Errors", 0):
            problemas.append(f"{tot['Connection Errors']} erros de conexao")
        if versao_rep != sw["versao"]:
            problemas.append(f"versao reportada {versao_rep} != {sw['versao']}")
        if not janela:
            problemas.append("sem amostras de CPU")
        linha["status"] = "erro" if problemas else "ok"
        linha["erro"] = "; ".join(problemas)
    except Exception as e:  # noqa: BLE001 - nenhuma falha pode parar a coleta
        detalhe = getattr(e, "stderr", "") or ""
        linha["status"] = "erro"
        linha["erro"] = f"{type(e).__name__}: {e} {detalhe}".strip().replace("\n", " ")[:500]
    finally:
        if amostrador:
            amostrador.parar()
        remover(nome)
        linha["fim"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return linha


def tratamentos(taxa_fixa: int) -> list[dict]:
    """Carga saturada (taxa 0 = sem limite) nos 8 tratamentos e, se taxa_fixa > 0,
    carga fixa com pipeline 1 para os 2 softwares x 2 comandos."""
    saturada = [dict(software=s, comando=c, pipeline=p, taxa=0)
                for s, c, p in itertools.product(SOFTWARES, COMANDOS, PIPELINES)]
    fixa = [dict(software=s, comando=c, pipeline=1, taxa=taxa_fixa)
            for s, c in itertools.product(SOFTWARES, COMANDOS)] if taxa_fixa else []
    return saturada + fixa


def montar_plano(args: argparse.Namespace) -> list[dict]:
    """Aquecimentos (bloco 0) e depois as execucoes medidas.

    - ordem "blocos": o bloco r tem a repeticao r de cada tratamento, em ordem sorteada.
    - ordem "sorteio": todas as execucoes medidas sorteadas de uma vez (como no piloto).
    """
    rng = random.Random(args.semente)
    trats = tratamentos(args.taxa_fixa)
    aquec = [dict(t, repeticao=0, bloco=0, aquecimento=True) for t in trats] if args.aquecimento else []
    rng.shuffle(aquec)
    if args.ordem == "blocos":
        medidas = []
        for r in range(1, args.repeticoes + 1):
            bloco = [dict(t, repeticao=r, bloco=r, aquecimento=False) for t in trats]
            rng.shuffle(bloco)
            medidas += bloco
    else:
        medidas = [dict(t, repeticao=r, bloco="", aquecimento=False)
                   for t in trats for r in range(1, args.repeticoes + 1)]
        rng.shuffle(medidas)
    plano = aquec + medidas
    for i, e in enumerate(plano, 1):
        e["ordem"] = i
        e["coleta"] = args.coleta
    return plano


def ler(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def ler_arquivo(caminho: str | Path) -> str:
    try:
        return Path(caminho).read_text().strip()
    except OSError:
        return ""


def energia(sys_dir: Path = Path("/sys")) -> dict:
    """Governador de CPU, perfil de energia e fontes de energia da rede eletrica (Linux).

    So contam as fontes do tipo "Mains" (carregador): baterias de mouse, teclado ou
    nobreak USB tambem tem `online` e fariam um notebook na bateria parecer na tomada.
    """
    return {
        "governador_cpu": ler_arquivo(sys_dir / "devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "perfil_energia": ler_arquivo(sys_dir / "firmware/acpi/platform_profile"),
        "na_tomada": {p.parent.name: ler_arquivo(p) == "1"
                      for p in (sys_dir / "class/power_supply").glob("*/online")
                      if ler_arquivo(p.parent / "type") == "Mains"},
    }


def metadados(args: argparse.Namespace, plano: list[dict]) -> dict:
    cpu_modelo = ""
    for linha in ler_arquivo("/proc/cpuinfo").splitlines():
        if linha.startswith("model name"):
            cpu_modelo = linha.split(":", 1)[1].strip()
            break
    ram = ""
    for linha in ler_arquivo("/proc/meminfo").splitlines():
        if linha.startswith("MemTotal"):
            ram = f"{int(linha.split()[1]) / 2**20:.1f} GiB"
    imagens = {}
    for img in [s["imagem"] for s in SOFTWARES.values()] + [IMAGEM_MEMTIER]:
        imagens[img] = ler(["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", img])
    return {
        "coleta": args.coleta,
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "semente": args.semente,
        "parametros": {
            "repeticoes": args.repeticoes, "duracao_s": args.duracao, "aquecimento": args.aquecimento,
            "threads": THREADS, "conexoes_por_thread": CONEXOES, "tamanho_valor_bytes": TAMANHO_VALOR,
            "chaves": CHAVES, "pipelines": PIPELINES, "comandos": COMANDOS,
            "taxa_fixa_ops_s": args.taxa_fixa, "ordem": args.ordem,
            "cpus_servidor": args.cpus_servidor, "cpus_cliente": args.cpus_cliente,
        },
        "ambiente": {
            "so": platform.platform(), "python": platform.python_version(),
            "cpu": cpu_modelo, "cpus_logicas": os.cpu_count(), "ram": ram,
            **energia(),
            "docker": ler(["docker", "version", "--format", "{{.Server.Version}}"]),
            "memtier": ler(["docker", "run", "--rm", IMAGEM_MEMTIER, "--version"]).splitlines()[:1],
            "git_commit": ler(["git", "-C", str(RAIZ), "rev-parse", "HEAD"]),
        },
        "imagens": imagens,
        "plano": [{k: e[k] for k in ("ordem", "bloco", "software", "comando", "pipeline", "taxa",
                                     "repeticao", "aquecimento")}
                  for e in plano],
    }


def problemas_ambiente(amb: dict) -> list[str]:
    """O que impede a coleta (ajuste A1 do piloto): fora da tomada ou CPU fora de `performance`.

    So da para conferir no Linux (arquivos em /sys). Onde a informacao nao existe,
    nada e acusado aqui: o aviso de "nao verificado" fica no main.
    """
    problemas = []
    if amb.get("governador_cpu") and amb["governador_cpu"] != "performance":
        problemas.append(f"governador de CPU '{amb['governador_cpu']}' (esperado: performance)")
    tomada = amb.get("na_tomada") or {}
    if tomada and not any(tomada.values()):
        problemas.append("maquina fora da tomada (na bateria)")
    return problemas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default="piloto", help="nome da coleta (pasta em data/raw)")
    ap.add_argument("--repeticoes", type=int, default=5, help="execucoes por tratamento")
    ap.add_argument("--duracao", type=int, default=30, help="segundos de carga por execucao")
    ap.add_argument("--semente", type=int, default=20261119, help="semente do sorteio da ordem")
    ap.add_argument("--cpus-servidor", default="0,4", help="--cpuset-cpus do servidor")
    ap.add_argument("--cpus-cliente", default="1-3,5-7", help="--cpuset-cpus do memtier")
    ap.add_argument("--sem-aquecimento", dest="aquecimento", action="store_false",
                    help="nao roda a execucao de aquecimento de cada tratamento")
    ap.add_argument("--tentativas", type=int, default=3, help="tentativas por execucao invalida")
    ap.add_argument("--ordem", choices=["blocos", "sorteio"], default="blocos",
                    help="blocos completos sorteados (padrao) ou sorteio livre (piloto)")
    ap.add_argument("--taxa-fixa", type=int, default=TAXA_FIXA,
                    help=f"ops/s no total da condicao de carga fixa (0 = sem essa condicao). "
                         f"Multiplo de {THREADS * CONEXOES} (o limite e por conexao)")
    ap.add_argument("--ignorar-ambiente", action="store_true",
                    help="coleta mesmo fora da tomada ou sem o governador performance")
    ap.add_argument("--dry-run", action="store_true", help="so mostra o plano sorteado")
    args = ap.parse_args()
    if args.taxa_fixa < 0 or args.taxa_fixa % (THREADS * CONEXOES):
        ap.error(f"--taxa-fixa deve ser 0 ou multiplo de {THREADS * CONEXOES}")

    plano = montar_plano(args)
    if args.dry_run:
        for e in plano:
            carga = f"{e['taxa']} ops/s" if e["taxa"] else "saturada"
            print(f"{e['ordem']:4d}  bloco={e['bloco']!s:<3s} {e['software']:7s} {e['comando']} "
                  f"p={e['pipeline']:<3d} {carga:<12s} rep={e['repeticao']:<3d}"
                  f"{' (aquecimento)' if e['aquecimento'] else ''}")
        return 0

    dir_raw = RAIZ / "data" / "raw" / args.coleta
    dir_raw.mkdir(parents=True, exist_ok=True)
    csv_saida = RAIZ / "data" / "processed" / f"{args.coleta}_execucoes.csv"
    csv_saida.parent.mkdir(parents=True, exist_ok=True)
    if csv_saida.exists():
        print(f"ERRO: {csv_saida} ja existe. Use outro --coleta ou apague o arquivo.", file=sys.stderr)
        return 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(dir_raw / "coleta.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])

    def encerrar(*_):
        for nome in list(_conteineres_ativos):
            remover(nome)
        log.warning("coleta interrompida pelo usuario")
        sys.exit(130)

    signal.signal(signal.SIGINT, encerrar)

    # Ambiente (A1 do piloto) antes de rede, imagens e metadados: so le /sys, e rapido
    amb = energia()
    problemas = problemas_ambiente(amb)
    if not amb["governador_cpu"]:
        log.warning("nao foi possivel ler o governador de CPU (so no Linux com cpufreq): confira a mao")
    if not amb["na_tomada"]:
        log.warning("nao foi possivel conferir se a maquina esta na tomada (so no Linux): confira a mao")
    if problemas and not args.ignorar_ambiente:
        log.error("ambiente fora do protocolo: %s. Corrija (docs/05, D1) ou use --ignorar-ambiente.",
                  "; ".join(problemas))
        return 1

    garantir_rede()
    for img in [s["imagem"] for s in SOFTWARES.values()] + [IMAGEM_MEMTIER]:
        if docker("image", "inspect", img, check=False).returncode != 0:
            log.info("baixando %s", img)
            docker("pull", img, timeout=900)
    meta = metadados(args, plano)
    meta["verificacao_ambiente"] = {"problemas": problemas, "ignorado": bool(problemas)}
    (dir_raw / "metadados.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    total = len(plano)
    inicio = time.monotonic()
    with csv_saida.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        for e in plano:
            carga = "-fixa" if e["taxa"] else ""
            for tentativa in range(1, args.tentativas + 1):
                e = {**e, "tentativa": tentativa,
                     "run_id": f"{e['ordem']:04d}-{e['software']}-{e['comando'].lower()}-p{e['pipeline']}"
                               f"{carga}-t{tentativa}"}
                linha = executar(e, args, dir_raw)
                w.writerow(linha)
                f.flush()
                decorrido = (time.monotonic() - inicio) / 60
                if linha["status"] == "ok":
                    log.info("[%d/%d] %s ok  ops/s=%.0f p50=%s p99=%s cpu=%s%% rss=%sMiB  (%.1f min)",
                             e["ordem"], total, e["run_id"], float(linha["ops_s"]), linha["lat_p50_ms"],
                             linha["lat_p99_ms"], linha["cpu_medio_pct"], linha["mem_rss_mib"], decorrido)
                    break
                log.error("[%d/%d] %s ERRO: %s", e["ordem"], total, e["run_id"], linha["erro"])
            else:
                log.error("execucao %d descartada apos %d tentativas", e["ordem"], args.tentativas)
    log.info("coleta concluida: %s", csv_saida.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
