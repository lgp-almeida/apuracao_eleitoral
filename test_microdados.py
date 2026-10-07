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
LM3 = "Wed, 14 Oct 2026 08:00:00 GMT"


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


def test_cdn_com_copia_velha_no_get(tmp_path: Path) -> None:
    """07/10/2026: o HEAD anunciava a versão nova e o GET entregava a velha. Pede de novo furando o cache;
    se ainda vier velha, recusa (sem trocar o ZIP nem apagar derivados) e tenta na próxima verificação."""
    cdn = CDN()
    cdn.arquivos[URL] = (_zip("votacao_secao_2026_RJ.csv", ['"1";"2"']), LM1)
    md.preparar(tmp_path, 2026, "RJ", cdn)
    derivado = tmp_path / "votacao_secao_2026_RJ__RJ.parquet"
    derivado.write_bytes(b"da 1a versao")
    velho, novo = cdn.arquivos[URL], (_zip("votacao_secao_2026_RJ.csv", ['"1";"3"']), LM2)
    pedidos: list[str] = []

    def nos_desencontrados(url, **kw):  # o nó do GET ainda tem a cópia velha; com parâmetro, a origem
        pedidos.append(url)
        return Resp(200, *(novo if "?" in url else velho))
    cdn.head = lambda url, **kw: Resp(200, *novo) if url == URL else Resp(404)
    cdn.get = nos_desencontrados
    e = {x.chave: x for x in md.preparar(tmp_path, 2026, "RJ", cdn)}
    assert e["votos_uf"].acao == "baixado" and pedidos[0] == URL and pedidos[1].startswith(URL + "?")
    prov = json.loads((tmp_path / "votacao_secao_2026_RJ.proveniencia.json").read_text())
    assert prov["last_modified"] == LM2 and prov["url"] == URL and not derivado.exists()

    derivado.write_bytes(b"da 2a versao")
    novo = (_zip("votacao_secao_2026_RJ.csv", ['"1";"4"']), LM3)
    velho = cdn.arquivos[URL] = (velho[0], LM2)
    cdn.get = lambda url, **kw: Resp(200, *velho)  # todo nó ainda velho
    e = {x.chave: x for x in md.preparar(tmp_path, 2026, "RJ", cdn)}
    assert e["votos_uf"].acao == "tentar de novo" and "versão de" in e["votos_uf"].situacao
    assert derivado.exists()
    assert json.loads((tmp_path / "votacao_secao_2026_RJ.proveniencia.json").read_text())["last_modified"] == LM2


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


MEMBRO = {"votos_uf": "x_RJ.csv", "votos_br": "x.csv", "detalhe_secao": "x_BRASIL.csv", "candidatos": "x_RJ.csv",
          "candidato_munzona": "x_RJ.csv", "detalhe_munzona": "x_RJ.csv", "partido_munzona": "x_RJ.csv",
          "perfil": "x_RJ.csv"}
PROVISORIO = ("votos_uf", "votos_br", "detalhe_secao", "candidatos", "candidato_munzona")
OFICIAL = ("detalhe_munzona", "partido_munzona")


def publicar(cdn: CDN, chaves: tuple[str, ...], lm: str = LM1) -> None:
    for chave in chaves:
        a = next(x for x in md.ARQUIVOS if x.chave == chave)
        cdn.arquivos[a.url(2026, "RJ")] = (_zip(MEMBRO[chave], ['"1";"2"']), lm)


@pytest.fixture()
def cli_falso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """preparar_2026 sem converter nem importar de verdade: registra as chamadas; a importação grava só o
    status.json (é por ele que se sabe o que já foi importado)."""
    import preparar_2026 as cli
    from apuracao import ibge
    from apuracao.ufs import dir_uf

    chamadas: list[tuple] = []
    monkeypatch.setattr(md, "converter", lambda c, a, u, chaves: chamadas.append(("converter", frozenset(chaves))) or [])
    monkeypatch.setattr(cli, "transferencia", lambda a: chamadas.append(("transferencia",)))
    monkeypatch.setattr(ibge, "preparar", lambda c, uf: chamadas.append(("ibge",)) or [])

    def importar(a, totais_de, turno, memo=None):
        chamadas.append(("importar", totais_de))
        destino = dir_uf(a.raiz / f"historico_{a.ano}_t{turno}", a.uf)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "status.json").write_text(json.dumps({"ano": a.ano, "totais_de": totais_de}))
        return True
    monkeypatch.setattr(cli, "importar", importar)
    monkeypatch.setattr(md, "turnos", lambda *a: {1})  # os ZIPs falsos não têm NR_TURNO: só o 1º turno
    args = ["--cache-dir", str(tmp_path / "cache"), "--raiz", str(tmp_path / "dados"), "--saidas", str(tmp_path / "s")]
    return cli, chamadas, args


def test_cli_vigia_importa_provisorio_e_so_encerra_com_os_totais_oficiais(cli_falso, monkeypatch) -> None:
    cli, chamadas, args = cli_falso
    cdn = CDN()
    fases = iter([PROVISORIO, OFICIAL])
    dormiu: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", lambda s: (dormiu.append(s), publicar(cdn, next(fases))))
    assert cli.main(["--vigiar", "--intervalo", "10", *args], sessao=cdn) == 0
    # nada → (10 min) votos + detalhe por seção + destinação: provisório → (10 min) totais oficiais: fim
    assert dormiu == [600, 600]
    assert [c for c in chamadas if c[0] == "importar"] == [("importar", "secoes"), ("importar", "munzona")]
    assert chamadas[0] == ("converter", frozenset(PROVISORIO))
    assert chamadas.index(("ibge",)) < chamadas.index(("transferencia",))  # malhas/Censo antes das análises


def test_execucao_nova_importa_quando_so_falta_o_detalhe_munzona(cli_falso) -> None:
    """O defeito da rodada 40: uma execução NOVA (memória vazia) em que só o detalhe munzona chega."""
    cli, chamadas, args = cli_falso
    cdn = CDN()
    publicar(cdn, PROVISORIO + ("partido_munzona",))
    assert cli.main(args, sessao=cdn) == 0
    assert [c for c in chamadas if c[0] == "importar"] == [("importar", "secoes")]
    chamadas.clear()
    publicar(cdn, ("detalhe_munzona",))
    assert cli.main(args, sessao=cdn) == 0       # outro processo: o resto vem do cache, não da memória
    assert chamadas == [("converter", frozenset({"detalhe_munzona"})), ("importar", "munzona")]
    chamadas.clear()
    assert cli.main(args, sessao=cdn) == 0       # nada mudou: nada a importar
    assert chamadas == []


def test_dados_no_cache_sem_importacao_sao_importados(cli_falso, tmp_path: Path) -> None:
    """Arquivos baixados por uma execução que não importou (versão antiga, queda): a próxima importa."""
    cli, chamadas, args = cli_falso
    cdn = CDN()
    publicar(cdn, PROVISORIO + OFICIAL)
    md.preparar(tmp_path / "cache", 2026, "RJ", cdn)  # baixa sem reagir
    assert cli.main(args, sessao=cdn) == 0
    assert chamadas == [("importar", "munzona")]


def test_fonte_dos_totais() -> None:
    assert md.fonte_dos_totais(set()) is None
    assert md.fonte_dos_totais(set(PROVISORIO)) == "secoes"
    assert md.fonte_dos_totais(set(PROVISORIO) - {"candidato_munzona"}) is None  # sem a destinação, não dá
    assert md.fonte_dos_totais({"votos_uf", "votos_br", "candidatos", "detalhe_munzona"}) == "munzona"
    assert md.FINAL >= {"detalhe_munzona", "partido_munzona"}


def test_falha_num_download_nao_perde_os_outros(cli_falso, tmp_path: Path) -> None:
    """Conexão caindo no meio (06/10/2026, "Connection reset by peer"): o que já chegou é preparado e o
    arquivo que falhou é pedido de novo na próxima vez."""
    import requests
    cli, chamadas, args = cli_falso
    cdn = CDN()
    publicar(cdn, PROVISORIO)
    url_dest = next(a for a in md.ARQUIVOS if a.chave == "candidato_munzona").url(2026, "RJ")
    get_original = cdn.get

    def get(url, **kw):
        if url == url_dest:
            raise requests.ConnectionError("Connection reset by peer")
        return get_original(url, **kw)
    cdn.get = get
    estados = md.preparar(tmp_path / "cache", 2026, "RJ", cdn, ao_chegar=cli.ao_chegar(
        __import__("argparse").Namespace(ano=2026, uf="RJ", cache_dir=tmp_path / "cache", raiz=tmp_path / "dados",
                                         saidas=tmp_path / "s")))
    assert [e.chave for e in md.com_erro(estados)] == ["candidato_munzona"]
    assert chamadas[0] == ("converter", frozenset(set(PROVISORIO) - {"candidato_munzona"}))  # o resto foi preparado
    assert not any(c[0] == "importar" for c in chamadas)  # sem a destinação, ainda não dá para importar
    cdn.get = get_original
    chamadas.clear()
    assert cli.main(args, sessao=cdn) == 0
    assert chamadas == [("converter", frozenset({"candidato_munzona"})), ("importar", "secoes")]


def test_so_verificar_nao_baixa_nem_importa(cli_falso, capsys) -> None:
    cli, chamadas, args = cli_falso
    cdn = CDN()
    publicar(cdn, PROVISORIO)
    assert cli.main(["--so-verificar", *args], sessao=cdn) == 0
    saida = capsys.readouterr().out
    # só consulta: um HEAD por arquivo + a lista de Boletins de Urna no CKAN (sem baixar nada)
    assert cdn.gets == 1 and cdn.heads == len(md.ARQUIVOS) and chamadas == []
    assert "detalhe_votacao_munzona_2026.zip" in saida and "1º turno — importado: nada" in saida
    assert "rode sem --so-verificar" in saida
    with pytest.raises(SystemExit):
        cli.main(["--so-verificar", "--vigiar", *args], sessao=cdn)


# --------------------------------------------------------------------------
# Download que continua de onde parou (rodada 58)
# --------------------------------------------------------------------------
class RespRange:
    def __init__(self, status: int, corpo: bytes, headers: dict[str, str], cai_apos: int | None) -> None:
        self.status_code, self.corpo, self.headers, self.cai_apos = status, corpo, headers, cai_apos

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, chunk_size: int = 0):
        import requests
        if self.cai_apos is None:
            yield self.corpo
            return
        yield self.corpo[:self.cai_apos]
        raise requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead")


class CDNRange:
    """Um arquivo servido com Range/If-Range (206) como a CDN do TSE; `quedas`: bytes entregues antes de a
    conexão cair, um por pedido (None = não cai)."""

    def __init__(self, corpo: bytes, lm: str = LM1, aceita_range: bool = True) -> None:
        self.corpo, self.lm, self.aceita_range = corpo, lm, aceita_range
        self.quedas: list[int | None] = []
        self.pedidos: list[dict[str, str]] = []

    def get(self, url, headers=None, **kw):
        headers = headers or {}
        self.pedidos.append(dict(headers))
        cai = self.quedas.pop(0) if self.quedas else None
        rng, if_range = headers.get("Range"), headers.get("If-Range")
        if rng and self.aceita_range and if_range == self.lm:
            ini = int(rng.removeprefix("bytes=").rstrip("-"))
            return RespRange(206, self.corpo[ini:], {"Last-Modified": self.lm,
                             "Content-Range": f"bytes {ini}-{len(self.corpo) - 1}/{len(self.corpo)}"}, cai)
        return RespRange(200, self.corpo, {"Last-Modified": self.lm}, cai)


def test_download_que_cai_continua_de_onde_parou(tmp_path: Path) -> None:
    import hashlib
    corpo = bytes(range(256)) * 400  # ~100 KB
    cdn = CDNRange(corpo)
    cdn.quedas = [30_000, 50_000]    # cai duas vezes; a 3ª vai até o fim
    zp = md.baixar("u", tmp_path / "x.zip", cdn, esperado=LM1)
    assert zp.read_bytes() == corpo
    assert [p.get("Range") for p in cdn.pedidos] == [None, "bytes=30000-", "bytes=80000-"]
    assert all(p.get("If-Range") == LM1 for p in cdn.pedidos[1:])
    prov = json.loads((tmp_path / "x.proveniencia.json").read_text())
    assert prov["sha512"] == hashlib.sha512(corpo).hexdigest() and prov["bytes"] == len(corpo)
    assert not list(tmp_path.glob("*.parcial*"))


def test_parcial_fica_para_a_proxima_verificacao(tmp_path: Path) -> None:
    import requests
    corpo = b"z" * 100_000
    cdn = CDNRange(corpo)
    cdn.quedas = [10_000] * md.RETOMADAS            # todas as tentativas desta verificação caem
    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        md.baixar("u", tmp_path / "x.zip", cdn, esperado=LM1)
    assert not (tmp_path / "x.zip").exists() and (tmp_path / "x.zip.parcial").stat().st_size == 50_000
    cdn.pedidos.clear()
    assert md.baixar("u", tmp_path / "x.zip", cdn, esperado=LM1).read_bytes() == corpo  # outra execução
    assert cdn.pedidos[0]["Range"] == "bytes=50000-"


def test_parcial_de_outra_versao_recomeca(tmp_path: Path) -> None:
    corpo = b"novo" * 10_000
    (tmp_path / "x.zip.parcial").write_bytes(b"velho" * 1000)
    (tmp_path / "x.zip.parcial.json").write_text(json.dumps({"url": "u", "last_modified": LM1}))
    cdn = CDNRange(corpo, lm=LM2)
    assert md.baixar("u", tmp_path / "x.zip", cdn, esperado=LM2).read_bytes() == corpo
    assert cdn.pedidos[0].get("Range") is None       # descartado antes de pedir
    # servidor que ignora Range (200): recomeça do zero sem misturar os bytes
    (tmp_path / "y.zip.parcial").write_bytes(b"n" * 7)
    (tmp_path / "y.zip.parcial.json").write_text(json.dumps({"url": "u", "last_modified": LM2}))
    sem_range = CDNRange(corpo, lm=LM2, aceita_range=False)
    assert md.baixar("u", tmp_path / "y.zip", sem_range, esperado=LM2).read_bytes() == corpo
    assert sem_range.pedidos[0]["Range"] == "bytes=7-"
