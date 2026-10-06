"""O mesmo partido em eleições diferentes (rodada 41): número e sigla NÃO bastam para ligar anos.

O número de urna é reaproveitado por partidos sem relação (14 = PTB até 2022, MISSÃO em 2026; 25 = DEM até
2018, PRD em 2026; 44 = PRP até 2018, UNIÃO desde 2022) e o mesmo partido troca de número (Podemos: 19 em 2022,
20 em 2026, depois de incorporar o PSC) e de sigla (PMN → MOBILIZA). Por isso a ligação entre anos é pela
ENTIDADE: a sigla de cada ano (do cadastro de candidatos daquele ano), seguida pelos eventos de `EVENTOS`:

  renomeação     a mesma entidade com outra sigla (ou outro número);
  fusão/incorporação
                 os antecessores somam no ano antigo (PRD 2026 × PTB + PATRIOTA 2022; PODE 2026 × PODE + PSC).

Um partido novo que reaproveita um número (MISSÃO) não tem antecessor. Siglas são comparadas por `compact`
("PC do B" = "PCDOB"). `conferir` acusa par número/sigla de um ano que a tabela não explica — partido novo,
fusão ou renomeação que ainda não está em `EVENTOS`.

Sem I/O: o mapa número → sigla de cada ano vem de quem chama (`bairros.ComparacaoBairros.siglas`, tabelas do
coletor/importador).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from apuracao.eleitorado import compact


@dataclass(frozen=True)
class Evento:
    """A partir da eleição de `vale_desde`, as siglas `origens` passam a ser a sigla `destino`."""

    vale_desde: int
    origens: tuple[str, ...]
    destino: str
    tipo: str        # "renomeação" | "fusão" | "incorporação"
    fonte: str = ""


# Ano = primeira eleição GERAL (2014, 2018, 2022, 2026) em que a sigla nova aparece no cadastro do TSE;
# conferido contra os consulta_cand de 2014/2018/2022/2026 (test_partidos.py, com o cache real).
EVENTOS: tuple[Evento, ...] = (
    Evento(2018, ("PMDB",), "MDB", "renomeação", "PMDB volta a se chamar MDB (2017)"),
    Evento(2018, ("PSDC",), "DC", "renomeação", "PSDC → Democracia Cristã (2017)"),
    Evento(2018, ("PTN",), "PODE", "renomeação", "PTN → Podemos (2017)"),
    Evento(2018, ("PT do B",), "AVANTE", "renomeação", "PT do B → Avante (2017)"),
    Evento(2018, ("SD",), "SOLIDARIEDADE", "renomeação", "sigla SD → SOLIDARIEDADE no cadastro do TSE"),
    Evento(2022, ("PRB",), "REPUBLICANOS", "renomeação", "PRB → Republicanos (2019)"),
    Evento(2022, ("PR",), "PL", "renomeação", "PR volta a se chamar PL (2019)"),
    Evento(2022, ("PPS",), "CIDADANIA", "renomeação", "PPS → Cidadania (2019)"),
    Evento(2022, ("PTC",), "AGIR", "renomeação", "PTC → Agir (2022)"),
    Evento(2022, ("PHS",), "PODE", "incorporação", "PHS incorporado ao Podemos (2019)"),
    Evento(2022, ("PRP",), "PATRIOTA", "incorporação", "PRP incorporado ao Patriota (2019)"),
    Evento(2022, ("PPL",), "PC do B", "incorporação", "PPL incorporado ao PCdoB (2019)"),
    Evento(2022, ("DEM", "PSL"), "UNIÃO", "fusão", "DEM + PSL → União Brasil (2022)"),
    Evento(2026, ("PTB", "PATRIOTA"), "PRD", "fusão", "PTB + Patriota → PRD (2023)"),
    Evento(2026, ("PSC",), "PODE", "incorporação", "PSC incorporado ao Podemos (2023), que passa a usar o 20"),
    Evento(2026, ("PROS",), "SOLIDARIEDADE", "incorporação", "PROS incorporado ao Solidariedade (2023)"),
    Evento(2026, ("PMN",), "MOBILIZA", "renomeação", "PMN → Mobiliza"),
    Evento(2026, ("PMB",), "DEMOCRATA", "renomeação", "PMB → Democrata"),
)
# partidos sem antecessor: (primeira eleição geral, sigla)
NOVOS: tuple[tuple[int, str], ...] = ((2018, "NOVO"), (2018, "PMB"), (2022, "UP"), (2026, "MISSÃO"))


def chave(sigla: str | None) -> str:
    """Sigla comparável entre fontes e anos: só letras e dígitos, sem acento ("PC do B" = "PCDOB")."""
    return compact(sigla)


def descendente(sigla: str, ano_a: int, ano_b: int) -> str:
    """A sigla (chave) que o partido `sigla` do ano `ano_a` tem no ano `ano_b` (≥ `ano_a`)."""
    atual = chave(sigla)
    for e in sorted(EVENTOS, key=lambda x: x.vale_desde):
        if ano_a < e.vale_desde <= ano_b and atual in {chave(o) for o in e.origens}:
            atual = chave(e.destino)
    return atual


def correspondencia(mapa_antigo: Mapping[int, str], mapa_novo: Mapping[int, str], ano_antigo: int,
                    ano_novo: int) -> dict[int, list[int]]:
    """nº no ano novo → nºs no ano antigo que formam o MESMO partido (antecessores; vazio = partido novo).
    `mapa_*`: nº → sigla do cadastro de cada ano. Mesmo ano: cada nº corresponde a ele mesmo."""
    if ano_antigo > ano_novo:
        raise ValueError("ano_antigo depois de ano_novo")
    por_chave: dict[str, list[int]] = {}
    for nr, sigla in mapa_antigo.items():
        por_chave.setdefault(descendente(sigla, ano_antigo, ano_novo), []).append(nr)
    return {nr: sorted(por_chave.get(chave(sigla), [])) for nr, sigla in mapa_novo.items()}


def sem_sucessor(mapa_antigo: Mapping[int, str], mapa_novo: Mapping[int, str], ano_antigo: int,
                 ano_novo: int) -> list[int]:
    """nºs do ano antigo cujo partido não existe no ano novo (no `mapa_novo` dado)."""
    novos = {chave(s) for s in mapa_novo.values()}
    return sorted(nr for nr, s in mapa_antigo.items() if descendente(s, ano_antigo, ano_novo) not in novos)


def rotulo(siglas_antigas: Iterable[str], ano_antigo: int) -> str:
    """"PTB + PATRIOTA em 2022", "sem antecessor em 2022"."""
    s = list(dict.fromkeys(siglas_antigas))
    return f"{' + '.join(s)} em {ano_antigo}" if s else f"sem antecessor em {ano_antigo}"


def conferir(mapas: Mapping[int, Mapping[int, str]]) -> list[str]:
    """Para anos consecutivos dos `mapas` (ano → nº → sigla): sigla do ano antigo sem sucessor no novo e sigla do
    ano novo sem antecessor nem registro em `NOVOS`. Lista vazia = `EVENTOS` explica todas as mudanças."""
    avisos = []
    anos = sorted(mapas)
    novos = {(a, chave(s)) for a, s in NOVOS}
    for a, b in zip(anos, anos[1:]):
        chaves_b = {chave(s) for s in mapas[b].values()}
        alcancadas = set()
        for nr, s in sorted(mapas[a].items()):
            d = descendente(s, a, b)
            alcancadas.add(d)
            if d not in chaves_b:
                avisos.append(f"{a}→{b}: {s} ({nr}) não tem sucessor em {b} (falta um evento em EVENTOS?)")
        for nr, s in sorted(mapas[b].items()):
            if chave(s) not in alcancadas and not any((ano, chave(s)) in novos for ano in range(a + 1, b + 1)):
                avisos.append(f"{a}→{b}: {s} ({nr}) aparece em {b} sem antecessor em {a} (partido novo? "
                              "registre em NOVOS ou EVENTOS)")
    return avisos


def normalizar_federacao(texto: str | None) -> str | None:
    """"13-PT/65-PC do B/43-PV" (cadastro de 2026) → "PT/PC do B/PV" (o formato de 2022 e do tempo real)."""
    if texto is None:
        return None
    import re
    return "/".join(re.sub(r"^\s*\d+\s*-\s*", "", p).strip() for p in texto.split("/"))
