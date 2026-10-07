"""Dados do IBGE: versão no nome, verificação, atualização com volta atrás, malha da API — offline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import requests

import votos_por_local_votacao as v
from apuracao import ibge
from conftest import download_sem_rede

LM1, LM2 = "Mon, 12 Oct 2026 10:00:00 GMT", "Tue, 13 Oct 2026 09:00:00 GMT"
BASICO = ibge.POR_CHAVE["bairros_basico"]
MALHA_B = ibge.POR_CHAVE["malha_bairros"]
MUN = ibge.POR_CHAVE["malha_municipios"]
DIR = BASICO.diretorio
DERIV_CENSO = "ibge_censo2022/censo_bairros_RJ.parquet"
DERIV_MALHA = "malhas/bairros_RJ.geojson"


class Resp:
    def __init__(self, status: int, corpo: bytes = b"", lm: str | None = None) -> None:
        self.status_code, self.content = status, corpo
        self.text = corpo.decode("utf-8", "replace")
        self.headers = {"Content-Length": str(len(corpo)), **({"Last-Modified": lm} if lm else {})}

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size: int = 0):
        yield self.content


class IBGE:
    """url → (bytes, Last-Modified); diretórios ("…/") viram índice HTML dos arquivos dentro dele."""

    def __init__(self) -> None:
        self.arquivos: dict[str, tuple[bytes, str | None]] = {}
        self.pedidos: list[tuple[str, str]] = []
        self.fora_do_ar = False

    def _resp(self, url: str) -> Resp:
        if self.fora_do_ar:
            raise requests.ConnectionError("fora do ar")
        if url.endswith("/"):
            nomes = [u.rsplit("/", 1)[1] for u in self.arquivos if u.rsplit("/", 1)[0] + "/" == url]
            html = "".join(f'<a href="{n}">{n[:20]}..&gt;</a>\n' for n in sorted(nomes))
            return Resp(200, f'<a href="../">Parent</a>\n{html}'.encode())
        return Resp(200, *self.arquivos[url]) if url in self.arquivos else Resp(404)

    def head(self, url, **kw):
        self.pedidos.append(("HEAD", url))
        return self._resp(url)

    def get(self, url, **kw):
        self.pedidos.append(("GET", url))
        return self._resp(url)

    def publicar(self, fonte: ibge.Fonte, versao: str, corpo: bytes, lm: str | None = LM1) -> str:
        nome = fonte.nome("RJ", versao)
        self.arquivos[fonte.url("RJ", nome)] = (corpo, lm)
        return nome


class SemRede:
    def head(self, *a, **k): raise AssertionError("não devia ir à rede")
    get = head


@pytest.fixture()
def fontes(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Três fontes (FTP com versão, geoftp sem versão, API) e geradores falsos dos derivados, que
    gravam o nome do arquivo de origem — ou falham se o conteúdo for b"ruim"."""
    monkeypatch.setattr(ibge, "FONTES", [MUN, MALHA_B, BASICO])
    monkeypatch.setattr(ibge, "POR_CHAVE", {f.chave: f for f in (MUN, MALHA_B, BASICO)})
    gerados: dict[str, list[str]] = {MALHA_B.derivados[0]: [], BASICO.derivados[0]: []}

    def gerador(modelo: str, chave: str):
        def gerar(uf: str, cache: Path) -> None:
            alvo = cache / modelo.format(uf=uf)
            if alvo.exists():
                return
            origem = ibge.local(ibge.POR_CHAVE[chave], cache, uf)
            if origem.read_bytes() == b"ruim":
                raise ValueError("arquivo do IBGE ilegível")
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(origem.name)
            gerados[modelo].append(origem.name)
        return gerar

    monkeypatch.setattr(ibge, "_geradores", lambda: {MALHA_B.derivados[0]: gerador(MALHA_B.derivados[0], "malha_bairros"),
                                                     BASICO.derivados[0]: gerador(BASICO.derivados[0], "bairros_basico")})
    return gerados


def _no_cache(cache: Path, fonte: ibge.Fonte, nome: str, corpo: bytes = b"zip", lm: str | None = LM1) -> Path:
    p = cache / fonte.pasta / nome
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(corpo)
    p.with_suffix(".proveniencia.json").write_text(json.dumps({"last_modified": lm, "sha512": "x"}))
    return p


# --------------------------------------------------------------------------
# Versão no nome
# --------------------------------------------------------------------------
def test_modelo_do_nome_e_versao() -> None:
    assert BASICO.nome("RJ") == "Agregados_por_bairros_basico_BR_20260520.zip"
    assert BASICO.nome("RJ", "") == "Agregados_por_bairros_basico_BR.zip"
    renda = ibge.POR_CHAVE["bairros_renda"]
    assert ibge._versao(renda, "RJ", "Agregados_por_bairros_renda_responsavel_BR_20260508_csv.zip") == "20260508"
    assert ibge._versao(renda, "RJ", "Agregados_por_bairros_renda_responsavel_BR_20260508_xlsx.zip") is None
    assert MALHA_B.nome("rj") == "RJ_bairros_CD2022.zip" and ibge._versao(MALHA_B, "RJ", "SP_bairros_CD2022.zip") is None


def test_resolver_escolhe_a_versao_datada_mais_nova() -> None:
    srv = IBGE()
    for ver in ("", "20260520", "20270101"):
        srv.publicar(BASICO, ver, b"zip")
    srv.arquivos[f"{DIR}/Agregados_por_bairros_basico_BR_20280101.xlsx"] = (b"", None)  # outro formato: ignora
    srv.arquivos[f"{DIR}/Agregados_por_setores_basico_BR_20290101.zip"] = (b"", None)   # outro nível: ignora
    assert ibge.resolver(BASICO, "RJ", srv) == "Agregados_por_bairros_basico_BR_20270101.zip"


def test_resolver_sem_arquivo_que_siga_o_modelo_avisa() -> None:
    srv = IBGE()
    srv.arquivos[f"{DIR}/outro.zip"] = (b"", None)
    with pytest.raises(v.TseDataError, match="mudou o nome"):
        ibge.resolver(BASICO, "RJ", srv)


# --------------------------------------------------------------------------
# caminho: o que os módulos de domínio chamam
# --------------------------------------------------------------------------
def test_caminho_usa_o_cache_sem_rede_e_a_versao_mais_nova(tmp_path: Path) -> None:
    _no_cache(tmp_path, BASICO, "Agregados_por_bairros_basico_BR.zip")
    novo = _no_cache(tmp_path, BASICO, "Agregados_por_bairros_basico_BR_20260520.zip")
    (tmp_path / BASICO.pasta / (novo.name + ibge.ANTERIOR)).write_bytes(b"")  # guardado: nunca é escolhido
    assert ibge.caminho("bairros_basico", tmp_path, "RJ", SemRede()) == novo


def test_caminho_descobre_a_versao_e_baixa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    srv = IBGE()
    nome = srv.publicar(BASICO, "20270101", b"zip")
    pedidos: list[str] = []

    def baixar(spec: v.DatasetSpec, pasta: Path, verify_sha512: bool = False) -> Path:
        pedidos.append(spec.url)
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / spec.zip_name).write_bytes(b"zip")
        return pasta / spec.zip_name

    monkeypatch.setattr(v, "download", baixar)
    assert ibge.caminho("bairros_basico", tmp_path, "RJ", srv).name == nome
    assert pedidos == [f"{DIR}/{nome}"]


def test_caminho_sem_indice_tenta_a_versao_conhecida(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    download_sem_rede(monkeypatch)
    with pytest.raises(v.TseDataError, match="Agregados_por_bairros_basico_BR_20260520.zip"):
        ibge.caminho("bairros_basico", tmp_path, "RJ")


def test_malha_de_bairros_404_mantem_a_mensagem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from apuracao import bairros as br
    download_sem_rede(monkeypatch)
    with pytest.raises(v.TseDataError, match="o IBGE não publica malha de bairros para RJ"):
        br.malha("RJ", tmp_path)


def test_preparar_uf_sem_malha_de_bairros_nao_e_falha(tmp_path: Path, fontes,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """DF e TO: o IBGE não publica malha de bairros (404). O lote marcava "erro" toda vez (07/10/2026);
    não é falha, e o derivado da malha não é tentado. O resto da UF segue normal."""
    download_sem_rede(monkeypatch)
    _no_cache(tmp_path, MUN, MUN.nome("RJ"))
    _no_cache(tmp_path, BASICO, BASICO.nome("RJ"))
    assert ibge.preparar(tmp_path, "RJ", IBGE()) == []
    assert fontes[MALHA_B.derivados[0]] == [] and fontes[BASICO.derivados[0]] == [BASICO.nome("RJ")]

    def sem_conexao(*a, **k):  # outra falha da malha continua sendo falha
        raise requests.ConnectionError("fora do ar")
    monkeypatch.setattr(v, "download", sem_conexao)
    assert [f.split(":")[0] for f in ibge.preparar(tmp_path, "RJ", IBGE())] == ["malha_bairros", DERIV_MALHA]


def test_caminho_da_api_grava_com_proveniencia(tmp_path: Path) -> None:
    srv = IBGE()
    corpo = b'{"type": "FeatureCollection", "features": []}'
    srv.arquivos[MUN.url("RJ")] = (corpo, None)
    p = ibge.caminho("malha_municipios", tmp_path, "RJ", srv)
    assert p == tmp_path / "malhas" / "municipios_RJ.geojson" and p.read_bytes() == corpo
    assert json.loads(p.with_suffix(".proveniencia.json").read_text())["sha512"] == hashlib.sha512(corpo).hexdigest()
    srv.arquivos[MUN.url("RJ")] = (b"<html>erro</html>", None)  # página de erro não entra no cache
    p.unlink()
    with pytest.raises(ValueError):
        ibge.caminho("malha_municipios", tmp_path, "RJ", srv)
    assert not p.exists()


# --------------------------------------------------------------------------
# verificar
# --------------------------------------------------------------------------
def test_verificar_compara_versao_data_e_cache(tmp_path: Path, fontes) -> None:
    srv = IBGE()
    srv.publicar(BASICO, "20270101", b"zip")
    srv.publicar(MALHA_B, "", b"zip", LM2)
    _no_cache(tmp_path, BASICO, BASICO.nome("RJ"))
    _no_cache(tmp_path, MALHA_B, MALHA_B.nome("RJ"), lm=LM1)
    e = {x.chave: x for x in ibge.verificar(tmp_path, "RJ", srv)}
    assert (e["bairros_basico"].acao, e["bairros_basico"].arquivo) == (
        "baixar versão nova", "Agregados_por_bairros_basico_BR_20270101.zip")
    assert e["malha_bairros"].acao == "baixar de novo"
    assert e["malha_municipios"].acao == "baixar"
    assert not any(m == "GET" and u.endswith(".zip") for m, u in srv.pedidos)  # verificar nunca baixa

    _no_cache(tmp_path, MALHA_B, MALHA_B.nome("RJ"), lm=LM2)
    e = {x.chave: x for x in ibge.verificar(tmp_path, "RJ", srv)}
    assert (e["malha_bairros"].situacao, e["malha_bairros"].acao) == ("em dia", "")


def test_verificar_com_ibge_fora_do_ar(tmp_path: Path, fontes) -> None:
    srv = IBGE()
    srv.fora_do_ar = True
    e = {x.chave: x for x in ibge.verificar(tmp_path, "RJ", srv)}
    assert e["bairros_basico"].acao == e["malha_bairros"].acao == "tentar de novo"


# --------------------------------------------------------------------------
# atualizar
# --------------------------------------------------------------------------
def test_atualizar_baixa_versao_nova_refaz_derivado_e_apaga_a_antiga(tmp_path: Path, fontes) -> None:
    srv = IBGE()
    srv.arquivos[MUN.url("RJ")] = (b"{}", None)
    srv.publicar(MALHA_B, "", b"zip", LM1)
    novo = srv.publicar(BASICO, "20270101", b"zip novo")
    antigo = _no_cache(tmp_path, BASICO, BASICO.nome("RJ"))
    (tmp_path / DERIV_CENSO).write_text(antigo.name)
    e = {x.chave: x for x in ibge.atualizar(tmp_path, "RJ", srv)}
    assert e["bairros_basico"].acao == "baixado"
    assert (tmp_path / DERIV_CENSO).read_text() == novo
    assert not antigo.exists() and not antigo.with_suffix(".proveniencia.json").exists()
    assert json.loads((tmp_path / ibge.ESTADO).read_text())["fontes"][2]["acao"] == "baixado"
    # 2ª vez: nada muda, nada é baixado
    srv.pedidos.clear()
    e = {x.chave: x for x in ibge.atualizar(tmp_path, "RJ", srv)}
    assert {x.acao for x in e.values()} == {""}
    assert not any(m == "GET" and u.endswith(".zip") for m, u in srv.pedidos)


def test_versao_nova_que_nao_converte_volta_a_anterior(tmp_path: Path, fontes) -> None:
    srv = IBGE()
    srv.arquivos[MUN.url("RJ")] = (b"{}", None)
    srv.publicar(MALHA_B, "", b"zip", LM1)
    srv.publicar(BASICO, "20270101", b"ruim")
    antigo = _no_cache(tmp_path, BASICO, BASICO.nome("RJ"))
    (tmp_path / DERIV_CENSO).write_text(antigo.name)
    e = {x.chave: x for x in ibge.atualizar(tmp_path, "RJ", srv)}
    assert e["bairros_basico"].acao == "tentar de novo" and "não convertida" in e["bairros_basico"].situacao
    assert ibge.local(BASICO, tmp_path, "RJ") == antigo
    assert (tmp_path / DERIV_CENSO).read_text() == antigo.name
    assert not list((tmp_path / BASICO.pasta).glob(f"*{ibge.ANTERIOR}"))


def test_republicado_no_mesmo_nome_que_nao_converte_volta_o_conteudo(tmp_path: Path, fontes) -> None:
    srv = IBGE()
    srv.arquivos[MUN.url("RJ")] = (b"{}", None)
    srv.publicar(BASICO, "20260520", b"zip", LM1)
    srv.publicar(MALHA_B, "", b"ruim", LM2)
    antigo = _no_cache(tmp_path, MALHA_B, MALHA_B.nome("RJ"), b"bom", LM1)
    _no_cache(tmp_path, BASICO, BASICO.nome("RJ"), lm=LM1)
    (tmp_path / DERIV_MALHA).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / DERIV_MALHA).write_text("derivado antigo")
    e = {x.chave: x for x in ibge.atualizar(tmp_path, "RJ", srv)}
    assert e["malha_bairros"].acao == "tentar de novo"
    assert antigo.read_bytes() == b"bom"
    assert json.loads(antigo.with_suffix(".proveniencia.json").read_text())["last_modified"] == LM1
    assert (tmp_path / DERIV_MALHA).read_text() == "derivado antigo"


def test_falha_no_download_restaura_o_guardado(tmp_path: Path, fontes) -> None:
    srv = IBGE()
    srv.arquivos[MUN.url("RJ")] = (b"{}", None)
    srv.publicar(BASICO, "20260520", b"zip", LM1)
    srv.publicar(MALHA_B, "", b"novo", LM2)
    antigo = _no_cache(tmp_path, MALHA_B, MALHA_B.nome("RJ"), b"bom", LM1)

    def baixar_falha(url: str, destino: Path, sessao) -> Path:
        raise requests.ConnectionError("caiu no meio")

    e = {x.chave: x for x in ibge.atualizar(tmp_path, "RJ", srv, baixar=baixar_falha)}
    assert e["malha_bairros"].acao == "tentar de novo" and antigo.read_bytes() == b"bom"


def test_api_so_e_conferida_quando_pedida_e_so_troca_se_mudou(tmp_path: Path, fontes) -> None:
    srv = IBGE()
    srv.publicar(BASICO, "20260520", b"zip")
    srv.publicar(MALHA_B, "", b"zip")
    srv.arquivos[MUN.url("RJ")] = (b'{"v": 1}', None)
    ibge.atualizar(tmp_path, "RJ", srv)
    malha = tmp_path / "malhas" / "municipios_RJ.geojson"
    assert malha.read_bytes() == b'{"v": 1}'
    srv.arquivos[MUN.url("RJ")] = (b'{"v": 2}', None)
    srv.pedidos.clear()
    e = {x.chave: x for x in ibge.atualizar(tmp_path, "RJ", srv)}
    assert e["malha_municipios"].situacao.startswith("em dia") and ("GET", MUN.url("RJ")) not in srv.pedidos
    e = {x.chave: x for x in ibge.atualizar(tmp_path, "RJ", srv, forcar_api=True)}
    assert e["malha_municipios"].acao == "atualizado" and malha.read_bytes() == b'{"v": 2}'
    e = {x.chave: x for x in ibge.atualizar(tmp_path, "RJ", srv, forcar_api=True)}
    assert e["malha_municipios"].situacao == "conferida: igual"


# --------------------------------------------------------------------------
# CLI e prontidão
# --------------------------------------------------------------------------
def test_cli_e_prontidao(tmp_path: Path, fontes, capsys: pytest.CaptureFixture[str]) -> None:
    import preparar_ibge as cli
    import verificar_prontidao as vp
    assert vp._ibge(tmp_path)[0][0] == "AVISO"  # nunca verificado
    srv = IBGE()
    srv.arquivos[MUN.url("RJ")] = (b"{}", None)
    srv.publicar(BASICO, "20260520", b"zip")
    srv.publicar(MALHA_B, "", b"zip")
    assert cli.main(["--cache-dir", str(tmp_path), "--so-verificar"], sessao=srv) == 0
    assert not (tmp_path / DERIV_CENSO).exists()
    assert "bairros_basico" in vp._ibge(tmp_path)[0][2]  # pendente
    assert cli.main(["--cache-dir", str(tmp_path)], sessao=srv) == 0
    assert "reinicie os sites" in capsys.readouterr().out
    assert (tmp_path / DERIV_CENSO).exists() and (tmp_path / DERIV_MALHA).exists()
    assert vp._ibge(tmp_path)[0][0] == "OK"
    srv.fora_do_ar = True
    assert cli.main(["--cache-dir", str(tmp_path)], sessao=srv) == 1
