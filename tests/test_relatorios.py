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
    assert "1 itens no total" in texto, "deveria contar só o item visível, não os 2 itens legado sem categoria"
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
