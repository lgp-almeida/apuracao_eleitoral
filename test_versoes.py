"""Acervo de versões dos arquivos do TSE no cache (`apuracao/versoes.py`) e `ingerir_eleitorado.py --atualizar`
— offline."""

from __future__ import annotations

import io
import json
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

import ingerir_eleitorado
import votos_por_local_votacao as v
from apuracao import versoes as vs

SPEC = v.electorate_spec(2026, "RJ")
LM1, LM2 = "Tue, 06 Oct 2026 09:34:36 GMT", "Thu, 15 Oct 2026 17:37:58 GMT"
GER1, GER2 = "06/10/2026 06:29:12", "15/10/2026 14:33:26"


def _conteudo(geracao: str, valor: str) -> bytes:
    data, hora = geracao.split()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("eleitorado_local_votacao_2026_RJ.csv",
                   f'"DT_GERACAO";"HH_GERACAO";"A"\r\n"{data}";"{hora}";"{valor}"\r\n'.encode("latin-1"))
        z.writestr("leiame.pdf", b"%PDF")
    return buf.getvalue()


V1, V2 = _conteudo(GER1, "um"), _conteudo(GER2, "dois")


def _no_cache(cache: Path, corpo: bytes, lm: str | None = LM1, sha: str | None = None) -> Path:
    """O ZIP no cache com a proveniência que o `download` grava."""
    cache.mkdir(parents=True, exist_ok=True)
    zp = cache / SPEC.zip_name
    zp.write_bytes(corpo)
    prov = {"url": SPEC.url, "downloaded_at": "2026-10-06T23:26:01+00:00", "last_modified": lm,
            "bytes": len(corpo), "sha512": sha or vs.sha512_de(zp)}
    zp.with_suffix(".proveniencia.json").write_text(json.dumps(prov))
    return zp


class Resp:
    def __init__(self, status: int, corpo: bytes = b"", lm: str | None = None) -> None:
        self.status_code, self.corpo = status, corpo
        self.headers = {"Content-Length": str(len(corpo)), **({"Last-Modified": lm} if lm else {})}

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size: int = 0):
        yield self.corpo


class CDN:
    """Um arquivo (bytes, Last-Modified) na URL do cadastro; o resto é 404. Conta os GET."""

    def __init__(self, corpo: bytes | None, lm: str = LM2) -> None:
        self.corpo, self.lm, self.gets = corpo, lm, 0

    def head(self, url, **kw):
        return Resp(200, self.corpo, self.lm) if self.corpo is not None and url == SPEC.url else Resp(404)

    def get(self, url, **kw):
        self.gets += 1
        return Resp(200, self.corpo, self.lm) if self.corpo is not None and url.startswith(SPEC.url) else Resp(404)


def test_carimbo_pela_geracao_do_tse_senao_pelo_last_modified_em_utc() -> None:
    assert vs.carimbo(GER2, LM2) == "2026-10-15T143326"
    assert vs.carimbo(None, LM2) == "2026-10-15T173758Z"
    assert vs.carimbo(None, None, datetime(2026, 9, 29, 23, 56, 38, tzinfo=timezone.utc)) == "2026-09-29T235638Z"
    with pytest.raises(ValueError, match="nomear a versão"):
        vs.carimbo(None, None)


def test_guardar_e_idempotente_e_a_copia_fica_so_leitura(tmp_path: Path) -> None:
    zp = _no_cache(tmp_path, V1)
    x = vs.guardar(zp, tmp_path)
    assert x.pasta == tmp_path / "versoes" / "eleitorado_local_votacao_2026" / "2026-10-06T062912"
    assert x.zip.read_bytes() == V1 and x.sha512 == vs.sha512_de(zp) and x.geracao_tse == GER1
    assert x.last_modified == LM1 and x.url == SPEC.url and x.baixado_em.startswith("2026-10-06")
    assert not x.zip.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    # a proveniência vai junto, igual: a pasta da versão tem o layout do cache
    assert (x.pasta / "eleitorado_local_votacao_2026.proveniencia.json").read_text() == \
        json.dumps(json.loads(zp.with_suffix(".proveniencia.json").read_text()), indent=2, ensure_ascii=False)
    assert vs.guardar(zp, tmp_path) == x and len(vs.listar(tmp_path, SPEC.zip_name)) == 1


def test_a_versao_guardada_sobrevive_a_troca_do_zip_no_cache(tmp_path: Path) -> None:
    zp = _no_cache(tmp_path, V1)
    x = vs.guardar(zp, tmp_path)
    novo = tmp_path / "novo.zip"
    novo.write_bytes(V2)
    novo.replace(zp)  # como o download troca o ZIP: rename, nunca escrita no lugar
    assert zp.read_bytes() == V2 and x.zip.read_bytes() == V1 and vs.sha512_de(x.zip) == x.sha512


def test_zip_que_nao_confere_com_a_proveniencia_e_recusado(tmp_path: Path) -> None:
    zp = _no_cache(tmp_path, V1, sha="0" * 128)
    with pytest.raises(vs.VersaoDivergente, match="SHA-512"):
        vs.guardar(zp, tmp_path)
    assert vs.listar(tmp_path, SPEC.zip_name) == []


def test_mesma_geracao_com_conteudo_diferente_fica_ao_lado(tmp_path: Path) -> None:
    a = vs.guardar(_no_cache(tmp_path / "a", V1), tmp_path)
    b = vs.guardar(_no_cache(tmp_path / "b", _conteudo(GER1, "outro")), tmp_path)
    assert a.carimbo == "2026-10-06T062912" and b.carimbo == f"2026-10-06T062912_{b.sha512[:8]}"
    assert [x.carimbo for x in vs.listar(tmp_path, SPEC.zip_name)] == [a.carimbo, b.carimbo]


def test_escolher_por_carimbo_ou_prefixo_unico(tmp_path: Path) -> None:
    vs.guardar(_no_cache(tmp_path / "a", V1), tmp_path)
    vs.guardar(_no_cache(tmp_path / "b", V2), tmp_path)
    assert vs.escolher(tmp_path, SPEC.zip_name, "2026-10-06").geracao_tse == GER1
    assert vs.escolher(tmp_path, SPEC.zip_name, "2026-10-15T143326").geracao_tse == GER2
    with pytest.raises(v.TseDataError, match="mais de uma"):
        vs.escolher(tmp_path, SPEC.zip_name, "2026-10")
    with pytest.raises(v.TseDataError, match="guardadas: 2026-10-06T062912, 2026-10-15T143326"):
        vs.escolher(tmp_path, SPEC.zip_name, "2026-09")


def test_atualizar_guarda_a_anterior_baixa_a_nova_e_apaga_os_derivados(tmp_path: Path) -> None:
    zp = _no_cache(tmp_path, V1)
    derivados = [tmp_path / f"eleitorado_local_votacao_2026__{uf}.parquet" for uf in ("RJ", "SP")]
    for d in derivados:
        d.write_bytes(b"parquet velho")
    outro = tmp_path / "eleitorado_local_votacao_2024__RJ.parquet"
    outro.write_bytes(b"de outro ano")
    cdn = CDN(V2)
    a = vs.atualizar(SPEC, tmp_path, cdn)
    assert a.situacao == "atualizado" and a.anterior.carimbo == "2026-10-06T062912"
    assert a.atual.carimbo == "2026-10-15T143326" and a.atual.last_modified == LM2
    assert zp.read_bytes() == V2
    assert json.loads(zp.with_suffix(".proveniencia.json").read_text())["last_modified"] == LM2
    assert a.anterior.zip.read_bytes() == V1 and a.atual.zip.read_bytes() == V2
    assert not any(d.exists() for d in derivados) and outro.exists()
    assert sorted(a.derivados_apagados) == sorted(d.name for d in derivados)
    # nada mudou no TSE: só o HEAD
    gets = cdn.gets
    b = vs.atualizar(SPEC, tmp_path, cdn)
    assert b.situacao == "em dia" and b.atual == a.atual and cdn.gets == gets


def test_republicado_sem_mudanca_mantem_os_derivados(tmp_path: Path) -> None:
    _no_cache(tmp_path, V1)
    derivado = tmp_path / "eleitorado_local_votacao_2026__RJ.parquet"
    derivado.write_bytes(b"ainda vale")
    a = vs.atualizar(SPEC, tmp_path, CDN(V1, LM2))
    assert a.situacao == "republicado sem mudança" and derivado.exists()
    assert len(vs.listar(tmp_path, SPEC.zip_name)) == 1


def test_sem_last_modified_mais_novo_so_baixa_com_forcar(tmp_path: Path) -> None:
    _no_cache(tmp_path, V1, lm=LM2)
    cdn = CDN(V2, LM1)
    assert vs.atualizar(SPEC, tmp_path, cdn).situacao == "em dia" and cdn.gets == 0
    assert vs.atualizar(SPEC, tmp_path, cdn, forcar=True).situacao == "atualizado"


def test_sem_zip_no_cache_baixa_e_guarda(tmp_path: Path) -> None:
    a = vs.atualizar(SPEC, tmp_path, CDN(V2))
    assert a.situacao == "baixado" and a.anterior is None and (tmp_path / SPEC.zip_name).read_bytes() == V2
    assert [x.carimbo for x in vs.listar(tmp_path, SPEC.zip_name)] == ["2026-10-15T143326"]


def test_head_com_erro_nao_toca_no_cache(tmp_path: Path) -> None:
    zp = _no_cache(tmp_path, V1)
    with pytest.raises(v.TseDataError, match="HTTP 404"):
        vs.atualizar(SPEC, tmp_path, CDN(None))
    assert zp.read_bytes() == V1


def test_cli_atualiza_e_lista_as_versoes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    _no_cache(tmp_path, V1)
    cdn = CDN(V2)
    monkeypatch.setattr(requests, "head", cdn.head)
    monkeypatch.setattr(requests, "get", cdn.get)
    assert ingerir_eleitorado.main(["--ano", "2026", "--atualizar", "--cache-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Cadastro de eleitorado 2026: atualizado" in out and "anterior: 2026-10-06T062912" in out
    assert ingerir_eleitorado.main(["--ano", "2026", "--versoes", "--cache-dir", str(tmp_path)]) == 0
    linhas = [x for x in capsys.readouterr().out.splitlines() if x.startswith("  2026")]
    assert len(linhas) == 2 and "← no cache" not in linhas[0] and linhas[1].endswith("← no cache")


def test_cli_sem_uf_e_sem_atualizar_e_erro_de_uso(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        ingerir_eleitorado.main(["--ano", "2026", "--cache-dir", str(tmp_path)])
