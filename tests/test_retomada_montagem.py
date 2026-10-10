"""Lotes publicados não voltam a montar quando o original está aberto."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import retomada_montagem as retomada

LOTE = "2026-10-08_14-30-00_abcdef12"


@pytest.fixture
def lote(tmp_path):
    entrada = tmp_path / "DOCAN R5200"
    entrada.mkdir()
    saida = tmp_path / "SAIDA DOCAN R5200"
    saida.mkdir()
    original = entrada / "1UN LONA 1.00X1.00M_CLIENTE.pdf"
    original.write_bytes(b"original de teste")
    info = original.stat()
    versoes = {original.name: {"tamanho": info.st_size, "mtime_ns": info.st_mtime_ns}}
    pdf = saida / "1UN LONA 1.00X1.13M_MONTAGEM.pdf"
    registro = retomada.criar_registro(entrada, versoes, [pdf], LOTE)
    return entrada, original, versoes, pdf, registro


def _publicar(pdf, versoes, lote_id=LOTE):
    pdf.write_bytes(b"%PDF-1.7\nsaida de teste\n")
    pdf.with_suffix(".json").write_text(
        json.dumps({"lote_id": lote_id, "originais": versoes}), encoding="utf-8")


def _mover(arquivo, destino):
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / arquivo.name
    arquivo.rename(alvo)
    return alvo


def test_falha_de_arquivamento_persiste_e_impede_repetir_lote(lote):
    entrada, original, versoes, pdf, registro = lote
    _publicar(pdf, versoes)
    antes_pdf = pdf.read_bytes()
    def aberto(*args):
        raise PermissionError("arquivo aberto no Illustrator")
    avisos = retomada.retomar_arquivamento(entrada, aberto)
    assert len(avisos) == 1 and "arquivamento pendente" in avisos[0]
    assert registro.exists() and original.exists()
    assert retomada.originais_confirmados(entrada) == versoes
    assert pdf.read_bytes() == antes_pdf


def test_segunda_tentativa_arquiva_original_e_limpa_registro(lote):
    entrada, original, versoes, pdf, registro = lote
    _publicar(pdf, versoes)
    def aberto(*args):
        raise PermissionError("ocupado")
    retomada.retomar_arquivamento(entrada, aberto)
    assert retomada.retomar_arquivamento(entrada, _mover) == []
    assert not original.exists() and not registro.exists()
    assert (entrada / "_originais" / LOTE / original.name).read_bytes() == b"original de teste"
    assert retomada.originais_confirmados(entrada) == {}
    assert pdf.exists()


def test_previa_de_confirmacao_nao_escreve_nem_move(lote):
    entrada, original, versoes, pdf, registro = lote
    _publicar(pdf, versoes)
    antes = {p: (p.read_bytes(), p.stat().st_mtime_ns)
             for p in entrada.parent.rglob("*") if p.is_file()}
    assert retomada.originais_confirmados(entrada) == versoes
    depois = {p: (p.read_bytes(), p.stat().st_mtime_ns)
              for p in entrada.parent.rglob("*") if p.is_file()}
    assert antes == depois and original.exists() and registro.exists()


def test_original_alterado_nao_e_ignorado_nem_arquivado(lote):
    entrada, original, versoes, pdf, registro = lote
    _publicar(pdf, versoes)
    original.write_bytes(b"nova arte com o mesmo nome, nunca impressa")
    assert retomada.originais_confirmados(entrada) == {}
    chamadas = []
    assert retomada.retomar_arquivamento(entrada, lambda *args: chamadas.append(args)) == []
    assert not chamadas and original.exists() and not registro.exists()
    assert original.read_bytes().startswith(b"nova arte")


@pytest.mark.parametrize("ausente", ["pdf", "ficha"])
def test_publicacao_parcial_exige_revisao_e_nao_move_original(lote, ausente):
    entrada, original, versoes, pdf, registro = lote
    _publicar(pdf, versoes)
    (pdf if ausente == "pdf" else pdf.with_suffix(".json")).unlink()
    with pytest.raises(ValueError, match="Publicação incompleta"):
        retomada.originais_confirmados(entrada)
    with pytest.raises(ValueError, match="Publicação incompleta"):
        retomada.retomar_arquivamento(entrada, _mover)
    assert original.exists() and registro.exists()


def test_lote_sem_qualquer_saida_pode_ser_remontado(lote):
    entrada, original, _versoes, _pdf, registro = lote
    assert retomada.originais_confirmados(entrada) == {}
    assert registro.exists()
    assert retomada.retomar_arquivamento(entrada, _mover) == []
    assert original.exists() and not registro.exists()


def test_arquivo_com_varias_saidas_so_confirma_o_conjunto_completo(lote):
    entrada, original, versoes, pdf, registro = lote
    registro.unlink()
    segundo = pdf.with_name("segunda_pagina.pdf")
    registro = retomada.criar_registro(entrada, versoes, [pdf, segundo], LOTE)
    _publicar(pdf, versoes)
    with pytest.raises(ValueError, match="Publicação incompleta"):
        retomada.originais_confirmados(entrada)
    assert original.exists() and registro.exists()
    _publicar(segundo, versoes)
    assert retomada.originais_confirmados(entrada) == versoes


@pytest.mark.parametrize("campo", ["lote_id", "originais"])
def test_ficha_de_outro_lote_ou_versao_nao_confirma(lote, campo):
    entrada, original, versoes, pdf, _registro = lote
    _publicar(pdf, versoes)
    ficha = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    if campo == "lote_id":
        ficha[campo] = "outro_lote"
    else:
        ficha[campo][original.name]["tamanho"] += 1
    pdf.with_suffix(".json").write_text(json.dumps(ficha), encoding="utf-8")
    with pytest.raises(ValueError, match="Publicação incompleta"):
        retomada.originais_confirmados(entrada)


def test_original_ja_ausente_limpa_sem_alterar_saidas(lote):
    entrada, original, versoes, pdf, registro = lote
    _publicar(pdf, versoes)
    _mover(original, entrada / "_originais" / LOTE)
    assert retomada.retomar_arquivamento(entrada, _mover) == []
    assert not registro.exists() and pdf.exists()


def test_mover_que_nao_move_mantem_registro(lote):
    entrada, original, versoes, pdf, registro = lote
    _publicar(pdf, versoes)
    avisos = retomada.retomar_arquivamento(entrada, lambda *args: None)
    assert avisos and "ainda está na entrada" in avisos[0]
    assert registro.exists() and original.exists()


@pytest.mark.parametrize("alvo", ["registro", "ficha"])
def test_json_corrompido_pede_revisao_sem_presumir_concluido(lote, alvo):
    entrada, original, versoes, pdf, registro = lote
    _publicar(pdf, versoes)
    (registro if alvo == "registro" else pdf.with_suffix(".json")).write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Confira o registro"):
        retomada.originais_confirmados(entrada)
    assert original.exists()


def test_nao_cria_registro_com_saida_fora_da_maquina(lote):
    entrada, _original, versoes, _pdf, _registro = lote
    externo = entrada.parent / "outra_saida" / "folha.pdf"
    with pytest.raises(ValueError, match="fora da saída"):
        retomada.criar_registro(entrada, versoes, [externo], "novo_lote")
    assert not (entrada / retomada.PASTA_REGISTROS / "novo_lote.json").exists()


def test_nao_cria_registro_com_origem_fora_da_entrada(lote):
    entrada, _original, versoes, pdf, _registro = lote
    versao = next(iter(versoes.values()))
    with pytest.raises(ValueError, match="fora da pasta"):
        retomada.criar_registro(entrada, {"../externo.pdf": versao}, [pdf], "novo_lote")


def test_registro_adulterado_nao_le_saida_externa(lote):
    entrada, original, _versoes, _pdf, registro = lote
    dados = json.loads(registro.read_text(encoding="utf-8"))
    dados["saidas"] = [str(entrada.parent / "externo.pdf")]
    registro.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(ValueError, match="fora da saída"):
        retomada.originais_confirmados(entrada)
    assert original.exists()


def test_falha_na_publicacao_atomica_nao_deixa_registro_parcial(lote, monkeypatch):
    entrada, _original, versoes, pdf, _registro = lote
    def falhar(*args):
        raise OSError("falha no disco")
    monkeypatch.setattr(retomada.os, "replace", falhar)
    with pytest.raises(ValueError, match="não consegui guardar"):
        retomada.criar_registro(entrada, versoes, [pdf], "novo_lote")
    registros = entrada / retomada.PASTA_REGISTROS
    assert not (registros / "novo_lote.json").exists()
    assert list(registros.glob("*.tmp")) == []


def test_falha_ao_listar_registros_nao_presume_entrada_livre(lote, monkeypatch):
    entrada, original, versoes, pdf, _registro = lote
    _publicar(pdf, versoes)
    iterdir_original = pathlib.Path.iterdir
    def listar(caminho):
        if caminho == entrada / retomada.PASTA_REGISTROS:
            raise PermissionError("pasta indisponível")
        return iterdir_original(caminho)
    monkeypatch.setattr(pathlib.Path, "iterdir", listar)
    with pytest.raises(ValueError, match="não consegui listar"):
        retomada.originais_confirmados(entrada)
    assert original.exists()
