import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from relatorios import gerar_os


def _dados_categorias(categorias_com_area):
    return {
        cat: {"contem_arquivos": True, "area_total_m2": area, "total_etiquetas": 1}
        for cat, area in categorias_com_area.items()
    }


def test_itens_no_total_ignora_item_sem_categoria_reconhecida(tmp_path):
    """
    Item vindo de uma pasta legado (categoria=None — ver estado_pedido.
    carregar_estado) não aparece na lista da OS, porque nenhuma
    categoria bate com ele. A contagem final precisa refletir só o que
    de fato foi listado, não incluir esses itens invisíveis.
    """
    itens = [
        {"arquivo": "1UN LONA 1,00X1,00.PDF", "categoria": "LONA", "quantidade": 1,
         "dimensao": {"area_m2": 1.0, "largura_m": 1.0, "altura_m": 1.0}, "thumbnail_bytes": None, "variante": None},
        # itens "legado": sem categoria reconhecida, não deveriam ser contados
        {"arquivo": "ARQUIVO_ANTIGO_1.pdf", "categoria": None, "quantidade": 1,
         "dimensao": None, "thumbnail_bytes": None, "variante": None},
        {"arquivo": "ARQUIVO_ANTIGO_2.pdf", "categoria": None, "quantidade": 1,
         "dimensao": None, "thumbnail_bytes": None, "variante": None},
    ]
    dados_categorias = _dados_categorias({"LONA": 1.0})

    caminho = gerar_os(
        str(tmp_path), "CLIENTE TESTE", "Gerente", "Produtor",
        itens, dados_categorias, ["LONA"], "26/08/2026 10:00:00",
    )

    import pymupdf
    doc = pymupdf.open(caminho)
    texto = doc[0].get_text()
    doc.close()

    assert "1 item" in texto  # subtotal da categoria LONA
    assert "1 item no total" in texto, "deveria contar só o item visível, não os 2 itens legado sem categoria"
    assert "3 itens no total" not in texto


def test_subtotal_mostra_tempo_estimado_quando_configurado(tmp_path):
    itens = [
        {"arquivo": "1UN LONA 4,00X4,00.PDF", "categoria": "LONA", "quantidade": 1,
         "dimensao": {"area_m2": 16.0, "largura_m": 4.0, "altura_m": 4.0}, "thumbnail_bytes": None, "variante": None},
    ]
    dados_categorias = _dados_categorias({"LONA": 16.0})

    caminho = gerar_os(
        str(tmp_path), "CLIENTE TESTE", "Gerente", "Produtor",
        itens, dados_categorias, ["LONA"], "26/08/2026 10:00:00",
        materiais_config={"LONA": {"minutos_por_m2": 2.0}},
    )

    import pymupdf
    doc = pymupdf.open(caminho)
    texto = doc[0].get_text()
    doc.close()

    assert "32min" in texto


def test_descricao_item_nao_repete_material_medida_cliente_ja_padronizados(tmp_path):
    """
    Regressão achada numa varredura (2026-08-29): com o nome de arquivo
    já padronizado (ver processamento._nome_padronizado — "{QTD} UN
    {MATERIAL} {MEDIDA} {CLIENTE} {resto}"), a descrição do item na OS
    repetia tudo isso de novo ("LONA 2.10x2.10M UCB_CWB IMPRESSA Photo
    Opp"), mesmo já aparecendo na etiqueta colorida, na linha de área
    logo abaixo, e no cabeçalho da página. Só o "resto" deve aparecer.
    """
    itens = [
        {"arquivo": "1 UN LONA 2.10x2.10M UCB_CWB IMPRESSA Photo Opp.pdf", "categoria": "LONA", "quantidade": 1,
         "dimensao": {"area_m2": 4.41, "largura_m": 2.1, "altura_m": 2.1}, "thumbnail_bytes": None, "variante": None},
    ]
    dados_categorias = _dados_categorias({"LONA": 4.41})

    caminho = gerar_os(
        str(tmp_path), "UCB_CWB", "Gerente", "Produtor",
        itens, dados_categorias, ["LONA"], "29/08/2026 10:00:00",
    )

    import pymupdf
    doc = pymupdf.open(caminho)
    texto = doc[0].get_text()
    doc.close()

    assert "IMPRESSA Photo Opp" in texto
    # "LONA" e "UCB_CWB" continuam aparecendo (etiqueta/cabeçalho), mas
    # não colados na linha de descrição do item
    assert "LONA 2.10x2.10M UCB_CWB" not in texto


def test_categoria_so_com_consumo_extra_nao_vira_cabecalho_vazio(tmp_path):
    """
    Regressão real (achada nessa mesma varredura): material composto
    (ex: "PS ADESIVADO" também consome ADESIVO — ver
    dimensoes.identificar_categoria_extra) marca 'contem_arquivos' pra
    ADESIVO mesmo sem nenhum item com 'categoria' == "ADESIVO". Isso
    fazia o corpo da OS desenhar um cabeçalho "ADESIVO" vazio, sem
    nenhum item embaixo — só a linha de subtotal do fim deveria mostrar
    ADESIVO, nunca uma seção vazia no corpo.
    """
    itens = [
        {"arquivo": "1 UN PS 1.00x2.00M CLIENTE ADESIVADO.pdf", "categoria": "PS", "categoria_extra": "ADESIVO",
         "quantidade": 1, "dimensao": {"area_m2": 2.0, "largura_m": 1.0, "altura_m": 2.0},
         "thumbnail_bytes": None, "variante": None},
    ]
    dados_categorias = {
        "PS": {"contem_arquivos": True, "area_total_m2": 2.0, "total_etiquetas": 1},
        "ADESIVO": {"contem_arquivos": True, "area_total_m2": 2.0, "total_etiquetas": 0},
    }

    caminho = gerar_os(
        str(tmp_path), "CLIENTE", "Gerente", "Produtor",
        itens, dados_categorias, ["PS", "ADESIVO"], "29/08/2026 10:00:00",
    )

    import pymupdf
    doc = pymupdf.open(caminho)
    texto = doc[0].get_text()
    doc.close()

    corpo, _, resumo = texto.partition("Subtotal por material")
    assert "ADESIVO" not in corpo, "ADESIVO não pode virar cabeçalho de seção vazio no corpo da OS"
    assert "ADESIVO" in resumo, "ADESIVO precisa continuar aparecendo no subtotal do fim"


def test_subtotal_sem_tempo_quando_categoria_nao_configurada(tmp_path):
    itens = [
        {"arquivo": "1UN MDF 1,00X1,00.PDF", "categoria": "MDF", "quantidade": 1,
         "dimensao": {"area_m2": 1.0, "largura_m": 1.0, "altura_m": 1.0}, "thumbnail_bytes": None, "variante": None},
    ]
    dados_categorias = _dados_categorias({"MDF": 1.0})

    caminho = gerar_os(
        str(tmp_path), "CLIENTE TESTE", "Gerente", "Produtor",
        itens, dados_categorias, ["MDF"], "26/08/2026 10:00:00",
        materiais_config={"LONA": {"minutos_por_m2": 2.0}},  # MDF de propósito não configurado
    )

    import pymupdf
    doc = pymupdf.open(caminho)
    texto = doc[0].get_text()
    doc.close()

    assert "min" not in texto
    assert "≈" not in texto
