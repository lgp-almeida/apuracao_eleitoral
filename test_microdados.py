"""Vigia dos microdados de 2026: publicação, arquivo só com cabeçalho, atualização pelo TSE — offline."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from apuracao import microdados as md

URL = md.ARQUIVOS[0].url(2026, "RJ")  # votacao_secao_2026_RJ.zip
URL_MZ = next(a for a in md.ARQUIVOS if a.chave == "detalhe_munzona").url(2026, "RJ")
LM1, LM2 = "Mon, 12 Oct 2026 10:00:00 GMT", "Tue, 13 Oct 2026 09:00:00 GMT"


def _zip(membro: str, linhas: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(membro, "\n".join(['"A";"B"'] + linhas).encode("latin-1"))
        z.writestr("leiame.pdf", b"%PDF")
    return buf.getvalue()


class Resp:
    def __init__(self, status: int, corpo: bytes = b"", lm: str | None = None) -> None:
        self.status_code, self.corpo = status, corpo
        self.headers = {"Content-Length": str(len(corpo)), **({"Last-Modified": lm} if lm else {})}

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, chunk_size: int = 0):
        yield self.corpo


class CDN:
    """url → (bytes, Last-Modified); o resto é 404. Conta HEAD e GET."""

    def __init__(self) -> None:
        self.arquivos: dict[str, tuple[bytes, str]] = {}
        self.heads, self.gets = 0, 0

    def head(self, url, **kw):
        self.heads += 1
        return Resp(200, *self.arquivos[url]) if url in self.arquivos else Resp(404)

    def get(self, url, **kw):
        self.gets += 1
        return Resp(200, *self.arquivos[url]) if url in self.arquivos else Resp(404)


def test_nada_publicado_so_faz_um_head_por_arquivo(tmp_path: Path) -> None:
    cdn = CDN()
    estados = md.preparar(tmp_path, 2026, "RJ", cdn)
    assert {e.situacao for e in estados} == {"não publicado"} and cdn.heads == len(md.ARQUIVOS) and cdn.gets == 0
    assert json.loads((tmp_path / "microdados_2026.json").read_text())["arquivos"][0]["situacao"] == "não publicado"


def test_so_cabecalho_nao_conta_como_publicado_e_atualizacao_baixa_de_novo(tmp_path: Path) -> None:
    cdn = CDN()
    cdn.arquivos[URL_MZ] = (_zip("detalhe_votacao_munzona_2026_RJ.csv", []), LM1)  # como em 30/09/2026
    chegaram: list[set[str]] = []
    e = {x.chave: x for x in md.preparar(tmp_path, 2026, "RJ", cdn, ao_chegar=chegaram.append)}
    assert e["detalhe_munzona"].tem_dados is False and e["detalhe_munzona"].acao == "baixado" and chegaram == []
    # 2ª verificação, nada mudou no TSE: nada é baixado
    gets = cdn.gets
    e = {x.chave: x for x in md.preparar(tmp_path, 2026, "RJ", cdn, ao_chegar=chegaram.append)}
    assert cdn.gets == gets and e["detalhe_munzona"].situacao.startswith("só cabeçalho") and chegaram == []
    # o TSE publica os votos no MESMO endereço (Last-Modified mais novo): baixa de novo e avisa
    cdn.arquivos[URL_MZ] = (_zip("detalhe_votacao_munzona_2026_RJ.csv", ['"1";"2"']), LM2)
    e = {x.chave: x for x in md.preparar(tmp_path, 2026, "RJ", cdn, ao_chegar=chegaram.append)}
    assert e["detalhe_munzona"].tem_dados and chegaram == [{"detalhe_munzona"}]
    prov = json.loads((tmp_path / "detalhe_votacao_munzona_2026.proveniencia.json").read_text())
    assert prov["last_modified"] == LM2


def test_atualizacao_apaga_os_parquet_derivados(tmp_path: Path) -> None:
    cdn = CDN()
    cdn.arquivos[URL] = (_zip("votacao_secao_2026_RJ.csv", ['"1";"2"']), LM1)
    md.preparar(tmp_path, 2026, "RJ", cdn)
    derivado = tmp_path / "votacao_secao_2026_RJ__RJ.parquet"
    derivado.write_bytes(b"velho")                       # convertido da 1ª versão
    cdn.arquivos[URL] = (_zip("votacao_secao_2026_RJ.csv", ['"1";"3"']), LM2)  # retotalização
    chegaram: list[set[str]] = []
    md.preparar(tmp_path, 2026, "RJ", cdn, ao_chegar=chegaram.append)
    assert not derivado.exists() and chegaram == [{"votos_uf"}]
    assert zipfile.ZipFile(tmp_path / "votacao_secao_2026_RJ.zip").read("votacao_secao_2026_RJ.csv").endswith(b'"3"')


def test_limpar_zip_so_com_cabecalho(tmp_path: Path) -> None:
    (tmp_path / "votacao_partido_munzona_2026.zip").write_bytes(_zip("votacao_partido_munzona_2026_RJ.csv", []))
    (tmp_path / "votacao_partido_munzona_2026.proveniencia.json").write_text("{}")
    (tmp_path / "votacao_secao_2026_RJ.zip").write_bytes(_zip("votacao_secao_2026_RJ.csv", ['"1";"2"']))
    assert md.limpar_cache_vazio(tmp_path, 2026, "RJ") == ["votacao_partido_munzona_2026.zip"]
    assert not (tmp_path / "votacao_partido_munzona_2026.proveniencia.json").exists()
    assert (tmp_path / "votacao_secao_2026_RJ.zip").exists()


def test_membro_certo_do_zip(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:  # SP com dados, RJ vazio: o que vale é o da UF
        z.writestr("x_SP.csv", b'"A"\n"1"')
        z.writestr("x_RJ.csv", b'"A"\n')
    (tmp_path / "x.zip").write_bytes(buf.getvalue())
    assert md.tem_dados(tmp_path / "x.zip", "_RJ.csv") is False and md.tem_dados(tmp_path / "x.zip", "_SP.csv")


def test_converte_o_que_chegou(tse_cache: Path) -> None:
    feitos = md.converter(tse_cache, 2024, "RJ", {"votos_uf", "perfil"})
    assert feitos == ["votos por seção da UF", "perfil do eleitorado"]
    assert (tse_cache / "votacao_secao_2024_RJ__RJ.parquet").exists()
    assert md.converter(tse_cache, 2024, "RJ", {"detalhe_munzona"}) == []  # lido direto do ZIP, sem Parquet


def test_cli_vigia_encerra_quando_os_votos_chegam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import preparar_2026 as cli
    cdn = CDN()
    chamadas: list[tuple] = []
    monkeypatch.setattr(md, "converter", lambda c, a, u, chaves: chamadas.append(("converter", frozenset(chaves))) or [])
    monkeypatch.setattr(cli, "transferencia", lambda a: chamadas.append(("transferencia",)))
    from apuracao import ibge
    monkeypatch.setattr(ibge, "preparar", lambda c, uf: chamadas.append(("ibge",)) or [])
    dormiu: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", lambda s: (dormiu.append(s), publicar(cdn)))
    args = ["--vigiar", "--intervalo", "10", "--cache-dir", str(tmp_path), "--saidas", str(tmp_path / "s")]
    assert cli.main(args, sessao=cdn) == 0
    assert dormiu == [600]  # 1ª verificação sem nada; espera (nunca menos de 10 min) e na 2ª chegou tudo
    assert chamadas[0] == ("converter", frozenset({"votos_uf", "votos_br", "detalhe_secao"}))
    assert chamadas.index(("ibge",)) < chamadas.index(("transferencia",))  # malhas/Censo antes das análises


def publicar(cdn: CDN) -> None:
    for chave, membro in (("votos_uf", "x_RJ.csv"), ("votos_br", "x.csv"), ("detalhe_secao", "x_BRASIL.csv")):
        a = next(x for x in md.ARQUIVOS if x.chave == chave)
        cdn.arquivos[a.url(2026, "RJ")] = (_zip(membro, ['"1";"2"']), LM1)
