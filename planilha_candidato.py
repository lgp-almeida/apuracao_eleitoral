"""Planilha XLSX de um candidato: votos por local, zona, bairro e seção × eleitorado por ano.

    python planilha_candidato.py --ano 2022 --uf RJ --cargo "deputado estadual" --candidato 13713
    python planilha_candidato.py --ano 2022 --uf RJ --cargo "deputado estadual" --candidato 13713 \
        --comparar-com 2024
    python planilha_candidato.py --ano 2024 --uf RJ --cargo vereador --candidato 12345 \
        --municipio "Rio de Janeiro"

As mudanças de local são medidas entre o cadastro de eleitorado do ANO-BASE e o de 2026.
O ano-base é o ano do resultado (--ano), ou o informado em --comparar-com; para
resultados de 2026 o padrão é 2024. Locais que mudaram ficam destacados (amarelo;
vermelho para desativados/extintos/sem cadastro). A planilha traz sempre o eleitorado de
2024 e de 2026, mais o do ano-base. Cadastros ausentes do cache são baixados da CDN
(ver ingerir_eleitorado.py). A aba "Inconsistencias" lista os problemas de cadastro
entre os dois anos e, para o RJ, em relação à lista de locais do TRE
(cache_tse/consulta_de_locais_de_votacao_*.json), se existir.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import requests

import votos_por_local_votacao as v
from apuracao import eleitorado as el
from apuracao import locais as lc
from apuracao import planilha as pc

logger = logging.getLogger("planilha_candidato")

TRE_JSON_GLOB = "consulta_de_locais_de_votacao_*.json"


@dataclass(frozen=True)
class PlanilhaConfig:
    year: int
    uf: str
    turno: int
    office: str
    candidate: int
    municipality: str | None
    cache_dir: str
    output: str | None
    tre_json: str | None
    compare_with: int | None = None  # ano-base da comparação de locais; None = padrão

    @property
    def base_year(self) -> int:
        """Ano do cadastro comparado com o de 2026."""
        if self.compare_with is not None:
            return self.compare_with
        return self.year if self.year < lc.NEW_YEAR else 2024


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Planilha de votos de um candidato por local/zona/bairro (TSE).")
    p.add_argument("--ano", type=int, required=True, help="ano do resultado (arquivo votacao_secao)")
    p.add_argument("--uf", required=True, type=str.upper)
    p.add_argument("--cargo", required=True, help='ex.: "deputado estadual", "vereador"')
    p.add_argument("--candidato", required=True, type=int, help="número na urna")
    p.add_argument("--turno", type=int, default=1, choices=[1, 2])
    p.add_argument("--municipio", help="restringe a um município (acentos opcionais)")
    p.add_argument("--cache-dir", default="cache_tse")
    p.add_argument("--saida", help="caminho do .xlsx")
    p.add_argument("--comparar-com", type=int, metavar="ANO",
                   help="ano do cadastro de eleitorado comparado com o de 2026 "
                        "(padrão: o ano do resultado; 2024 se o resultado for de 2026)")
    p.add_argument("--tre-json", help="lista de locais do TRE (padrão: a mais recente em --cache-dir)")
    p.add_argument("--sha512", action="store_true", help="validar .sha512 do TSE ao baixar")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _register_or_none(year: int, uf: str, cache: Path, sha: bool) -> pl.DataFrame | None:
    try:
        return el.load_sections(year, uf, cache, sha)
    except (v.TseDataError, requests.RequestException) as exc:
        logger.warning("sem cadastro de eleitorado de %s (%s); bairro virá de outro ano", year, exc)
        return None


def _tre_path(cfg: PlanilhaConfig) -> Path | None:
    if cfg.tre_json:
        return Path(cfg.tre_json)
    if cfg.uf != "RJ":
        return None
    found = sorted(Path(cfg.cache_dir).glob(TRE_JSON_GLOB))
    return found[-1] if found else None


def run(cfg: PlanilhaConfig, sha: bool = False) -> Path:
    cache = Path(cfg.cache_dir)
    votes = v.load_section_votes(cfg.year, cfg.uf, cfg.office, cache, sha)
    muni = v.resolve_municipality(votes, cfg.municipality)
    name = v.candidate_name(votes, cfg.turno, cfg.office, cfg.candidate, muni)
    sections = pc.tally_sections(votes, cfg.turno, cfg.office, cfg.candidate, muni)

    base = cfg.base_year
    if base >= lc.NEW_YEAR:
        raise v.TseDataError(f"--comparar-com deve ser anterior a {lc.NEW_YEAR} (recebido {base}).")
    required = sorted({base, *pc.ALWAYS_ELECTORATE_YEARS})
    registers = {y: el.filter_area(el.load_sections(y, cfg.uf, cache, sha), muni) for y in required}
    if cfg.year not in registers:
        own = _register_or_none(cfg.year, cfg.uf, cache, sha)
        if own is not None:
            registers[cfg.year] = el.filter_area(own, muni)
    regs = pc.Registers(sections=registers, result_year=cfg.year, base_year=base)

    tre_file = _tre_path(cfg)
    tre = lc.load_tre_places(tre_file) if tre_file and tre_file.exists() else None
    if tre_file and tre is None:
        logger.warning("lista do TRE não encontrada: %s", tre_file)

    header = [
        ("Candidato", f"{cfg.candidate} — {name}"),
        ("Cargo", v.normalize_text(cfg.office)),
        ("Eleição", f"{cfg.uf} {cfg.year}, {cfg.turno}º turno"),
        ("Área", f"{sections['NM_MUNICIPIO'][0]} (código TSE {muni})" if muni is not None else f"UF {cfg.uf} inteira"),
        ("Gerado em", datetime.now(timezone.utc).isoformat(timespec="seconds")),
    ]
    report = pc.build_report(sections, regs, cfg.uf, header, tre)

    files = [cache / v.section_votes_spec(cfg.year, cfg.uf, cfg.office).zip_name]
    files += [cache / v.electorate_spec(y, cfg.uf).zip_name for y in sorted(registers)]
    if tre is not None and tre_file is not None:
        files.append(tre_file)
    report.sheets["Proveniencia"] = pc.provenance_sheet({**asdict(cfg), "base_year": base}, files)

    muni_tag = f"_{v.normalize_text(cfg.municipality).replace(' ', '_').lower()}" if cfg.municipality else ""
    out = Path(cfg.output or f"planilha_{cfg.candidate}_{cfg.uf}_{cfg.year}_t{cfg.turno}{muni_tag}.xlsx")
    pc.write_workbook(out, report)

    print(f"\n{cfg.candidate} — {name} | {v.normalize_text(cfg.office)} | {cfg.uf} {cfg.year}, {cfg.turno}º turno")
    shown = ("Comparação de locais", "Votos do candidato", "% sobre válidos", "Locais", "Zonas", "Bairros",
             "Locais do resultado", "Seções do resultado", "Inconsistências apontadas")
    for k, val in report.summary:
        if k in shown[:6] or k.startswith(shown[6:]):
            print(f"  {k:<58}{val:>14,}" if isinstance(val, int) else f"  {k:<58}{val!s:>14}")
    print(f"\nPlanilha: {out}")
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = PlanilhaConfig(year=args.ano, uf=args.uf, turno=args.turno, office=args.cargo,
                         candidate=args.candidato, municipality=args.municipio, cache_dir=args.cache_dir,
                         output=args.saida, tre_json=args.tre_json,
                         compare_with=args.comparar_com)
    try:
        run(cfg, args.sha512)
    except (v.TseDataError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
