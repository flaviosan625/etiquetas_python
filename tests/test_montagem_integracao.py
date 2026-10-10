"""Conferência do lote real em entradas sintéticas, sem impressoras ou OneDrive."""
import copy
import json
import pathlib
import time

import pymupdf
import pytest

import config
import montagem
from seguranca_montagem import PublicacaoMontagem


@pytest.fixture
def entrada(tmp_path, monkeypatch):
    import caminhos
    import conversao_adobe

    monkeypatch.setattr(montagem, "PASTA_RAIZ", tmp_path / "montagem")
    monkeypatch.setattr(caminhos, "ONEDRIVE_UNY", tmp_path / "onedrive")
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", tmp_path / "clientes")
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    config.salvar_config(copy.deepcopy(config.CONFIG_PADRAO))
    monkeypatch.setattr(conversao_adobe, "CONVERSORES_POR_EXTENSAO", {})
    pasta = montagem.pasta_da_maquina("DOCAN R5200")
    pasta.mkdir(parents=True)
    return pasta


def _arte(pasta, nome, largura=1.0, altura=0.5):
    arquivo = pasta / nome
    with pymupdf.open() as doc:
        pagina = doc.new_page(width=largura * montagem.PT_M, height=altura * montagem.PT_M)
        pagina.draw_rect(pagina.rect, color=None, fill=(0.3, 0.5, 0.7))
        doc.save(arquivo)
    return arquivo


def test_cabecalho_e_nome_completos_na_folha_estreita(entrada):
    nome = "1UN LONA 0.30X0.50M_LOGO_CLIENTE.pdf"
    _arte(entrada, nome, 0.30, 0.50)
    resultado = montagem.montar_pasta(entrada, folga_m=0.01)
    with pymupdf.open(resultado["folhas"][0]["arquivo"]) as doc:
        pagina = doc[0]
        texto = pagina.get_text()
        assert "MONTAGEM" in texto
        assert "REDIMENSIONAR" in texto
        assert pathlib.Path(nome).stem in texto
        for bloco in pagina.get_text("blocks"):
            if "MONTAGEM" in bloco[4]:
                assert bloco[3] / montagem.PT_M <= montagem.CABECALHO_M


def test_falha_no_segundo_material_nao_publica_nem_arquiva_o_primeiro(entrada, monkeypatch):
    originais = [_arte(entrada, "1UN LONA 1.00X0.50M_A.pdf"),
                 _arte(entrada, "1UN ADESIVO 1.00X0.50M_B.pdf")]
    salvar = PublicacaoMontagem.salvar
    chamadas = 0

    def salvar_com_falha(self, doc, destino, ficha):
        nonlocal chamadas
        chamadas += 1
        if chamadas == 2:
            raise OSError("disco indisponível no segundo material")
        return salvar(self, doc, destino, ficha)

    monkeypatch.setattr(PublicacaoMontagem, "salvar", salvar_com_falha)
    with pytest.raises(OSError, match="segundo material"):
        montagem.montar_pasta(entrada)
    assert all(arquivo.exists() for arquivo in originais)
    assert not (entrada / montagem.NOME_SUBPASTA_ORIGINAIS).exists()
    saida = montagem.pasta_de_saida("DOCAN R5200", entrada.parent)
    assert not list(saida.iterdir())


def test_arte_alterada_durante_desenho_exige_nova_previa(entrada, monkeypatch):
    original = _arte(entrada, "1UN LONA 1.00X0.50M_A.pdf")
    previa = montagem.prever_pasta(entrada)
    colocar = montagem.colocar_arte

    def alterar_depois_de_desenhar(*args, **kwargs):
        colocar(*args, **kwargs)
        original.write_bytes(original.read_bytes() + b"\n% alteracao simulada\n")

    monkeypatch.setattr(montagem, "colocar_arte", alterar_depois_de_desenhar)
    with pytest.raises(ValueError, match="mudaram desde a prévia"):
        montagem.montar_pasta(entrada, versoes_esperadas=previa["versoes"])
    assert original.exists()
    saida = montagem.pasta_de_saida("DOCAN R5200", entrada.parent)
    assert not list(saida.iterdir())


def test_duas_montagens_no_mesmo_minuto_nao_sobrescrevem_pdf(entrada):
    _arte(entrada, "1UN LONA 1.00X0.50M_A.pdf")
    primeira = montagem.montar_pasta(entrada, guardar_originais=False)
    arquivo_primeiro = primeira["folhas"][0]["arquivo"]
    conteudo_primeiro = arquivo_primeiro.read_bytes()
    segunda = montagem.montar_pasta(entrada, guardar_originais=False)
    arquivo_segundo = segunda["folhas"][0]["arquivo"]
    assert arquivo_segundo != arquivo_primeiro
    assert arquivo_primeiro.read_bytes() == conteudo_primeiro
    assert arquivo_segundo.with_suffix(".json").is_file()


def test_pagina_vazia_e_sinalizada_antes_da_montagem(entrada):
    arquivo = entrada / "1UN LONA 1.00X0.50M_VAZIA.pdf"
    with pymupdf.open() as doc:
        doc.new_page(width=montagem.PT_M, height=0.5 * montagem.PT_M)
        doc.save(arquivo)
    previa = montagem.prever_pasta(entrada)
    assert not previa["folhas"]
    assert "sem conteúdo" in previa["recusadas"][0]["motivo"]


def test_conversao_manual_respeita_trava_da_montagem(entrada):
    from seguranca_montagem import MontagemOcupada, trava_montagem

    with trava_montagem(entrada):
        with pytest.raises(MontagemOcupada):
            montagem.converter_o_que_precisa(entrada)


def test_original_aberto_nao_faz_repetir_pdf_na_proxima_passada(entrada, monkeypatch):
    original = _arte(entrada, "1UN LONA 1.00X0.50M_A.pdf")
    mover = montagem._mover_para

    def aberto(arquivo, destino):
        raise PermissionError("original aberto no editor")

    monkeypatch.setattr(montagem, "_mover_para", aberto)
    primeira = montagem.montar_pasta(entrada)
    assert len(primeira["folhas"]) == 1
    assert original.exists()
    assert "arquivamento pendente" in primeira["avisos"][0]
    previa = montagem.prever_pasta(entrada)
    assert not previa["folhas"]
    assert "não será montado novamente" in previa["recusadas"][0]["motivo"]
    segunda = montagem.montar_pasta(entrada)
    assert not segunda["folhas"]
    saida = montagem.pasta_de_saida("DOCAN R5200", entrada.parent)
    assert len(list(saida.glob("*.pdf"))) == 1
    monkeypatch.setattr(montagem, "_mover_para", mover)
    terceira = montagem.montar_pasta(entrada)
    assert not terceira["folhas"]
    assert not original.exists()
    assert not list((entrada / "_lotes_montagem").glob("*.json"))


def test_falha_publicando_ficha_limpa_registro_e_preserva_originais(entrada, monkeypatch):
    originais = [_arte(entrada, "1UN LONA 1.00X0.50M_A.pdf"),
                 _arte(entrada, "1UN ADESIVO 1.00X0.50M_B.pdf")]
    renomear = pathlib.Path.rename

    def falhar_segunda_ficha(arquivo, destino):
        if arquivo.name == "0001.json":
            raise OSError("falha de publicação simulada")
        return renomear(arquivo, destino)

    monkeypatch.setattr(pathlib.Path, "rename", falhar_segunda_ficha)
    with pytest.raises(OSError, match="publicação simulada"):
        montagem.montar_pasta(entrada)
    assert all(arquivo.exists() for arquivo in originais)
    assert not list((entrada / "_lotes_montagem").glob("*.json"))
    saida = montagem.pasta_de_saida("DOCAN R5200", entrada.parent)
    assert not list(saida.iterdir())


def test_tela_e_backend_montam_apenas_selecao_conferida(entrada, monkeypatch):
    import gui_montagem as gm

    escolhido = _arte(entrada, "1UN LONA 1.00X0.50M_A.pdf")
    pendente = _arte(entrada, "1UN LONA 1.00X0.50M_B.pdf")
    erros = []
    monkeypatch.setattr(gm.messagebox, "showerror", lambda *args, **kwargs: erros.append(args))
    raiz = gm.tk.Tk()
    raiz.withdraw()
    aba = gm._AbaMaquina(raiz, "DOCAN R5200")

    def esperar():
        limite = time.monotonic() + 10
        while aba._ocupada and time.monotonic() < limite:
            raiz.update()
            time.sleep(0.01)
        assert not aba._ocupada
        assert not erros

    try:
        esperar()
        aba._alternar_arquivo(pendente.name)
        aba.var_folga.set("2,5")
        aba.calcular()
        esperar()
        assert aba._previa["folga_m"] == 0.025
        assert set(aba._previa["versoes"]) == {escolhido.name}
        aba._montar_agora()
        esperar()
        assert len(aba._feitas) == 1
        ficha = json.loads(aba._feitas[0].with_suffix(".json").read_text(encoding="utf-8"))
        assert ficha["folga_m"] == 0.025
        assert {p["arquivo"] for p in ficha["pecas"]} == {escolhido.name}
        assert pendente.exists()
        assert not escolhido.exists()
    finally:
        aba.fechar()
        raiz.destroy()
