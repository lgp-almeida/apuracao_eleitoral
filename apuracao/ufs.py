"""As 27 UFs e a pasta de dados de cada uma.

Convenção (rodada 39): cada UF tem a sua pasta `dados_2026/<base>_<UF>` (`oficial_SP`, `oficial_t2_SP`,
`historico_2022_t1_SP`…), para que duas UFs não se misturem. As pastas anteriores, sem sufixo, são do RJ
(o `status.json` delas diz `"uf": "RJ"`) e continuam valendo para o RJ: nada precisa ser movido.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

UFS: dict[str, str] = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
    "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins",
}
UF_LEGADA = "RJ"  # dona das pastas sem sufixo, de antes da rodada 39


def lista(ufs: str | Iterable[str]) -> list[str]:
    """"todas" (ou ["todas"]) → as 27 UFs em ordem; senão, as pedidas, em maiúsculas e sem repetição.
    UF desconhecida é erro (ValueError), não é ignorada."""
    pedidas = [ufs] if isinstance(ufs, str) else list(ufs)
    if [u.lower() for u in pedidas] == ["todas"]:
        return list(UFS)
    saida = list(dict.fromkeys(u.strip().upper() for u in pedidas if u.strip()))
    desconhecidas = [u for u in saida if u not in UFS]
    if desconhecidas:
        raise ValueError(f"UF desconhecida: {', '.join(desconhecidas)} (use as siglas, ex.: SP MG, ou 'todas')")
    return saida


def uf_da_pasta(pasta: Path) -> str | None:
    """A UF que o `status.json` da pasta registra (coletor e importador gravam `uf`)."""
    try:
        return (json.loads((pasta / "status.json").read_text()).get("uf") or "").upper() or None
    except (OSError, ValueError):
        return None


def dir_uf(base: Path, uf: str) -> Path:
    """Pasta de dados da UF: `<base>_<UF>`; para a UF legada (RJ), a pasta antiga `<base>` se ela já existir
    e for do RJ. Para as demais, nunca devolve `<base>` (seria misturar com os dados do RJ)."""
    uf = uf.upper()
    nova = base.with_name(f"{base.name}_{uf}")
    if nova.exists() or uf != UF_LEGADA:
        return nova
    if base.exists() and uf_da_pasta(base) in (UF_LEGADA, None):
        return base
    return nova


def tem_dados(pasta: Path) -> bool:
    return (pasta / "ultimo" / "totais.parquet").exists()
