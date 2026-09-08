"""
O caminho inteiro, do jeito que a tela faz: listar -> conferir ->
enviar -> registrar -> gerar o documento. Os testes por módulo cobrem
cada peça; estes cobrem a costura entre elas, que é onde erro de
integração aparece.
"""
import pymupdf
import pytest

import documento_enviados as doc
import envio_impressao as env
import rasterlink_hotfolder as rl_hf
from config import carregar_config
from documento_enviados import carregar, caminho_pdf, gerar_pdf, miniatura, registrar
from envio_impressao import (
    MAQUINA_ADESIVO, MAQUINA_LONA, conferir, enviar, listar, nome_da_producao, raiz_do_cliente,
)


@pytest.fixture(autouse=True)
def _isolar_pastas_reais(tmp_path, monkeypatch):
    """Mesma trava dos outros testes de envio — nada pode encostar na fila nem no registro reais."""
    monkeypatch.setattr(env, "PASTA_FILA_ONEDRIVE", tmp_path / "_fila_isolada")
    monkeypatch.setattr(rl_hf, "PASTA_FILA_ONEDRIVE", tmp_path / "_fila_isolada")
    monkeypatch.setattr(rl_hf, "PASTA_RELATORIOS", tmp_path / "_relatorios_isolados")


CONFIG = carregar_config()
ORDEM = list(CONFIG["materiais"])
MAQUINAS_TESTE = {
    MAQUINA_LONA: {"hot_folder": r"C:\nao_usado", "largura_util_m": 3.20},
    MAQUINA_ADESIVO: {"hot_folder": r"C:\nao_usado", "largura_util_m": 1.48},
}


def _pdf(caminho, largura_pt=600, altura_pt=400):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    documento = pymupdf.open()
    pagina = documento.new_page(width=largura_pt, height=altura_pt)
    pagina.draw_rect(pymupdf.Rect(10, 10, largura_pt - 10, altura_pt - 10), fill=(0.2, 0.4, 0.8))
    documento.save(str(caminho))
    documento.close()
    return caminho


def _producao(tmp_path):
    pasta = tmp_path / "EVENTOS" / "FESTA ALEMA" / "PRODUCAO 03_09"
    for sub in ("LONAS", "ADESIVOS", "CORTES", "COMPOSTOS"):
        (pasta / sub / "Prontos").mkdir(parents=True)
    return pasta


def _rodar_envio(pasta, fila, itens=None):
    """Faz o que a tela faz depois de confirmar a conferência."""
    raiz = raiz_do_cliente(pasta)
    if itens is None:
        itens = listar(pasta, CONFIG, carregar(raiz)["envios"], maquinas=MAQUINAS_TESTE)
    resultado = enviar(itens, pasta, pasta_fila=fila, maquinas=MAQUINAS_TESTE)
    miniaturas = {i["arquivo"]: miniatura(i["caminho"]) for i in itens}
    if resultado["enviados"]:
        registrar(raiz, resultado["enviados"], miniaturas)
        gerar_pdf(raiz, ORDEM)
    return resultado, raiz


def test_ciclo_completo_de_um_envio(tmp_path):
    pasta = _producao(tmp_path)
    _pdf(pasta / "LONAS" / "8UN LONA IMPRESSA ACABAMENTO BANNER_Banner 50x250_.pdf")
    _pdf(pasta / "ADESIVOS" / "2UN VINIL IMPRESSO FOSCO 0.70X1.80M_totem_Adesivo.pdf")
    fila = tmp_path / "fila"

    resultado, raiz = _rodar_envio(pasta, fila)

    # 1. as cópias chegaram na fila da máquina certa
    assert (fila / MAQUINA_LONA / "8UN LONA IMPRESSA ACABAMENTO BANNER_Banner 50x250_.pdf").exists()
    assert (fila / MAQUINA_ADESIVO / "2UN VINIL IMPRESSO FOSCO 0.70X1.80M_totem_Adesivo.pdf").exists()

    # 2. os originais continuam exatamente onde estavam
    assert (pasta / "LONAS" / "8UN LONA IMPRESSA ACABAMENTO BANNER_Banner 50x250_.pdf").exists()
    assert (pasta / "ADESIVOS" / "2UN VINIL IMPRESSO FOSCO 0.70X1.80M_totem_Adesivo.pdf").exists()

    # 3. nenhuma pasta nova apareceu na produção
    assert sorted(p.name for p in pasta.iterdir() if p.is_dir()) == [
        "ADESIVOS", "COMPOSTOS", "CORTES", "LONAS",
    ]

    # 4. o documento nasceu na raiz do cliente, com miniatura
    documento = caminho_pdf(raiz)
    assert documento.exists()
    assert documento.parent.parent == raiz.resolve() or documento.parent.parent == raiz
    aberto = pymupdf.open(str(documento))
    texto = aberto[0].get_text()
    tem_imagem = bool(aberto[0].get_images())
    aberto.close()

    assert len(resultado["enviados"]) == 2
    assert "FESTA ALEMA" in texto
    assert "10,00 m²" in texto      # 8 un x 0,50 x 2,50
    assert "2,52 m²" in texto       # 2 un x 0,70 x 1,80
    assert "PRODUCAO 03_09" in texto
    assert tem_imagem


def test_segundo_envio_soma_no_documento_sem_apagar_o_primeiro(tmp_path):
    pasta = _producao(tmp_path)
    arte = _pdf(pasta / "LONAS" / "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf")
    fila = tmp_path / "fila"

    _rodar_envio(pasta, fila)
    # a fila já tem o arquivo: a conferência travaria o reenvio, então
    # simula o RIP tendo puxado (que é o que acontece na vida real)
    (fila / MAQUINA_LONA / arte.name).unlink()
    _, raiz = _rodar_envio(pasta, fila)

    envios = carregar(raiz)["envios"]
    aberto = pymupdf.open(str(caminho_pdf(raiz)))
    texto = aberto[0].get_text()
    aberto.close()

    assert len(envios) == 2
    assert "2º ENVIO" in texto
    assert "4,00 m²" in texto  # 2,00 + 2,00: material foi gasto duas vezes


def test_reenvio_e_travado_enquanto_o_rip_nao_puxou(tmp_path):
    """A cópia anterior ainda na fila é o caso que pode mandar peça pela metade."""
    pasta = _producao(tmp_path)
    _pdf(pasta / "LONAS" / "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf")
    fila = tmp_path / "fila"
    _rodar_envio(pasta, fila)

    raiz = raiz_do_cliente(pasta)
    itens = listar(pasta, CONFIG, carregar(raiz)["envios"], maquinas=MAQUINAS_TESTE)
    conferencia = conferir(itens, pasta_fila=fila, maquinas=MAQUINAS_TESTE)

    assert len(conferencia["bloqueados"]) == 1
    assert "na fila" in conferencia["bloqueados"][0][1]


def test_envios_de_producoes_diferentes_caem_no_mesmo_documento(tmp_path):
    """Um documento por CLIENTE — cada linha diz de qual produção saiu."""
    pasta_a = _producao(tmp_path)
    pasta_b = tmp_path / "EVENTOS" / "FESTA ALEMA" / "PRODUCAO 02_09"
    (pasta_b / "LONAS").mkdir(parents=True)
    _pdf(pasta_a / "LONAS" / "1UN LONA IMPRESSA_castelo_1,00x2,00M.pdf")
    _pdf(pasta_b / "LONAS" / "1UN LONA IMPRESSA_totem_1,00x2,00M.pdf")
    fila = tmp_path / "fila"

    _rodar_envio(pasta_a, fila)
    _, raiz = _rodar_envio(pasta_b, fila)

    aberto = pymupdf.open(str(caminho_pdf(raiz)))
    texto = aberto[0].get_text()
    aberto.close()

    assert len(carregar(raiz)["envios"]) == 2
    assert "PRODUCAO 03_09" in texto
    assert "PRODUCAO 02_09" in texto
    assert len(list((raiz / "Enviados").glob("*.pdf"))) == 1


def test_apontar_uma_subpasta_de_trabalho_nao_perde_o_nome_da_producao(tmp_path):
    """Escolhendo 'PRODUCAO 03_09\\LONAS', a coluna não pode virar 'LONAS'."""
    pasta = _producao(tmp_path)
    _pdf(pasta / "LONAS" / "1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf")

    assert nome_da_producao(pasta / "LONAS") == "PRODUCAO 03_09"

    resultado, _ = _rodar_envio(pasta / "LONAS", tmp_path / "fila")

    assert resultado["enviados"][0]["producao"] == "PRODUCAO 03_09"


def test_falha_no_meio_do_lote_nao_registra_o_que_nao_foi(tmp_path, monkeypatch):
    """Documento de comprovação não pode ter linha de arquivo que não chegou na fila."""
    pasta = _producao(tmp_path)
    _pdf(pasta / "LONAS" / "1UN LONA IMPRESSA_boa_1,00x2,00M.pdf")
    _pdf(pasta / "LONAS" / "1UN LONA IMPRESSA_ruim_1,00x2,00M.pdf")
    original = env.enviar_para_fila

    def falha_na_ruim(caminho, maquina, pasta_fila=None, maquinas=None):
        if "ruim" in str(caminho):
            raise OSError("rede caiu")
        return original(caminho, maquina, pasta_fila=pasta_fila, maquinas=maquinas)

    monkeypatch.setattr(env, "enviar_para_fila", falha_na_ruim)
    resultado, raiz = _rodar_envio(pasta, tmp_path / "fila")

    arquivos_no_documento = [e["arquivo"] for e in carregar(raiz)["envios"]]

    assert len(resultado["enviados"]) == 1
    assert len(resultado["falhas"]) == 1
    assert arquivos_no_documento == ["1UN LONA IMPRESSA_boa_1,00x2,00M.pdf"]


def test_documento_sobrevive_a_apagar_o_pdf(tmp_path):
    """O JSON é a fonte de verdade — PDF apagado por engano volta inteiro no envio seguinte."""
    pasta = _producao(tmp_path)
    _pdf(pasta / "LONAS" / "1UN LONA IMPRESSA_castelo_1,00x2,00M.pdf")
    fila = tmp_path / "fila"
    _, raiz = _rodar_envio(pasta, fila)
    caminho_pdf(raiz).unlink()

    _pdf(pasta / "LONAS" / "1UN LONA IMPRESSA_totem_1,00x2,00M.pdf")
    _rodar_envio(pasta, fila)

    aberto = pymupdf.open(str(caminho_pdf(raiz)))
    texto = aberto[0].get_text()
    aberto.close()

    assert "castelo" in texto
    assert "totem" in texto
