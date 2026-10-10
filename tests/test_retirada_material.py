"""Retirada, OS e etiquetas precisam identificar as mesmas peças e quantidades."""
import copy
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf
import pytest

from config import CONFIG_PADRAO
from processamento import processar_etiquetas
from relatorios import gerar_os
from retirada_material import caminho_pdf


def _item(nome, quantidade, categoria="LONA", **extras):
    return dict(arquivo=f"{quantidade} UN {categoria} 3.00x2.00M {nome}.pdf",
                quantidade=quantidade, categoria=categoria,
                dimensao=dict(largura_m=3, altura_m=2, area_m2=6), **extras)


def _gerar(pasta, itens, quando="09/10/2026 10:00:00", **extras):
    ordem = list(dict.fromkeys(i["categoria"] for i in itens))
    dados = {cat: dict(contem_arquivos=True, area_total_m2=sum(
        i["dimensao"]["area_m2"] * i["quantidade"] for i in itens if i["categoria"] == cat))
        for cat in ordem}
    return gerar_os(str(pasta), "CLIENTE TESTE", "Gerente", "Produtor",
                    itens, dados, ordem, quando, **extras)


def _partes(caminho):
    with pymupdf.open(caminho) as doc:
        os = "".join(p.get_text() for p in doc)
    assert "COMPROVANTE DE RETIRADA" not in os
    arquivo_retirada = caminho_pdf(pathlib.Path(caminho).parent, "CLIENTE TESTE")
    retirada = ""
    if arquivo_retirada.exists():
        with pymupdf.open(arquivo_retirada) as doc:
            retirada = "".join(p.get_text() for p in doc)
    return os, retirada


def _quantidades(texto):
    return re.findall(r"\b(\d+) UN\b", texto)


def test_mesmas_quantidades_ordem_e_medidas_sem_duplicar_material_composto(tmp_path):
    itens = [_item("PAINEL", 2), _item("PLACAS", 6, "PS", categoria_extra="ADESIVO"),
             _item("TESTEIRA", 1, "PVC")]
    os, retirada = _partes(_gerar(tmp_path, itens))
    assert _quantidades(os) == _quantidades(retirada) == ["2", "6", "1"]
    assert "3 itens no total" in os and "9 unidades" in os
    assert "Nesta folha: 9 unidades" in retirada and "Total da OS: 9 unidades" in retirada
    assert "PS + ADESIVO" in retirada
    assert "3,00 x 2,00 m" in retirada
    assert all(text in retirada for text in ["OS - CLIENTE TESTE.pdf", "09/10/2026 10:00:00",
                                             "MOTORISTA", "PLACA", "DESTINO", "assinatura"])


def test_atualizar_os_substitui_a_retirada_sem_deixar_quantidade_antiga(tmp_path):
    caminho = _gerar(tmp_path, [_item("PAINEL", 2), _item("REMOVIDA", 3)])
    _gerar(tmp_path, [_item("PAINEL", 7)], quando="09/10/2026 11:00:00")
    os, retirada = _partes(caminho)
    assert _quantidades(os) == _quantidades(retirada) == ["7"]
    assert "REMOVIDA" not in os + retirada
    assert "10:00:00" not in retirada and "11:00:00" in retirada
    assert retirada.count("COMPROVANTE DE RETIRADA") == 1


def test_muitas_pecas_paginam_sem_perdas_com_assinatura_apenas_na_ultima(tmp_path):
    itens = [_item(f"PECA{i:02d}", i + 1) for i in range(23)]
    caminho = _gerar(tmp_path, itens)
    os, retirada = _partes(caminho)
    assert _quantidades(os) == _quantidades(retirada) == [str(i+1) for i in range(23)]
    assert all(retirada.count(f"PECA{i:02d}") == 1 for i in range(23))
    with pymupdf.open(caminho_pdf(tmp_path, "CLIENTE TESTE")) as doc:
        folhas = [p.get_text() for p in doc if "COMPROVANTE DE RETIRADA" in p.get_text()]
    assert 1 < len(folhas) <= 2
    for n, texto in enumerate(folhas, 1):
        assert f"Página {n} de {len(folhas)}" in texto
        assert "Total da OS: 276 unidades" in texto
        if n == len(folhas):
            assert "Motorista: assinatura" in texto and "Responsável pela liberação" in texto
            assert "Declaro que retirei" in texto and "todas as páginas deste documento" in texto
        else:
            assert "assinatura" not in texto and "Declaro que retirei" not in texto
            assert "Ressalvas / avarias" not in texto


@pytest.mark.parametrize("quantidade", [1, 10, 14, 23, 40])
def test_paginacao_com_miniaturas_nao_perde_pecas_nem_cria_folha_so_para_assinar(tmp_path, quantidade):
    imagem = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 60), False)
    imagem.clear_with(170)
    itens = [_item(f"PECA{i:02d}", i+1, thumbnail_bytes=imagem.tobytes("png")) for i in range(quantidade)]
    os, retirada = _partes(_gerar(tmp_path, itens))
    assert _quantidades(os) == _quantidades(retirada) == [str(i+1) for i in range(quantidade)]
    assert retirada.count("Declaro que retirei") == retirada.count("Motorista: assinatura") == 1
    assert retirada.count("MOTORISTA / TRANSPORTADORA") == 1
    with pymupdf.open(caminho_pdf(tmp_path, "CLIENTE TESTE")) as doc:
        for pagina in doc:
            assert "PECA" in pagina.get_text(), "Não deve haver uma folha só com a declaração"
        assert "Declaro que retirei" in doc[-1].get_text()
        assert len(doc) <= max(1, (quantidade + 10) // 11)


def test_nome_longo_pode_reduzir_itens_por_folha_sem_encolher_a_fonte(tmp_path):
    itens = [_item(f"PECA{i:02d} " + "Descrição detalhada da peça " * 20, i+1) for i in range(7)]
    os, retirada = _partes(_gerar(tmp_path, itens))
    assert _quantidades(os) == _quantidades(retirada) == [str(i+1) for i in range(7)]
    assert retirada.count("COMPROVANTE DE RETIRADA") > 1


def test_os_vazia_nao_declara_uma_retirada(tmp_path):
    _, retirada = _partes(_gerar(tmp_path, []))
    assert "Nenhum material listado na OS" in retirada
    assert "Declaro que retirei" not in retirada


def test_copia_de_custos_nao_recebe_documento_de_logistica(tmp_path):
    custos = dict(por_material={}, completo=True, total=0, faltando_preco=[])
    _, retirada = _partes(_gerar(tmp_path, [_item("PAINEL", 2)],
                                custos=custos, nome_arquivo="CUSTOS - CLIENTE TESTE.pdf"))
    assert retirada == ""


def test_etiquetas_os_e_retirada_acompanham_duas_rodadas(tmp_path):
    config = copy.deepcopy(CONFIG_PADRAO)
    pasta_pedido = None
    for rodada, nome in enumerate(["2UN LONA 3,00X2,00M_PAINEL.pdf",
                                  "6UN PVC BRANCO 0,60X0,40M_PLACAS.pdf"], 1):
        entrada = tmp_path / f"entrada{rodada}"
        entrada.mkdir()
        with pymupdf.open() as doc:
            doc.new_page(width=200, height=200)
            doc.save(str(entrada / nome))
        resultado = processar_etiquetas(str(entrada), "CLIENTE TESTE", "Gerente", "Produtor", config,
                                        pasta_saida_base=str(tmp_path / "saida"),
                                        pasta_saida_existente=pasta_pedido)
        assert resultado is not None
        pasta_pedido = resultado["pasta_saida"]
        assert pathlib.Path(resultado["retirada"]).is_file()
        assert resultado["retirada"] != resultado["os"] != resultado["unificado"]
        os, retirada = _partes(resultado["os"])
        assert _quantidades(os) == _quantidades(retirada) == (["2"] if rodada == 1 else ["2", "6"])
        with pymupdf.open(resultado["unificado"]) as doc:
            etiquetas = "".join(p.get_text() for p in doc)
        assert "2 UN LONA" in etiquetas
        if rodada == 2:
            assert "6 UN PVC" in etiquetas
            assert "Total da OS: 8 unidades" in retirada and "8 unidades" in os


def test_miniatura_da_os_aparece_na_retirada_sem_distorcer(tmp_path):
    imagem = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 40), False)
    imagem.clear_with(170)
    bruto = imagem.tobytes("png")
    caminho = _gerar(tmp_path, [_item("PAINEL", 2, thumbnail_bytes=bruto)])
    with pymupdf.open(caminho) as os, pymupdf.open(caminho_pdf(tmp_path, "CLIENTE TESTE")) as retirada:
        imagens_os = [pymupdf.Pixmap(os, img[0]).samples for p in os for img in p.get_images()]
        imagens_retirada = [pymupdf.Pixmap(retirada, img[0]).samples for p in retirada for img in p.get_images()]
        assert imagem.samples in imagens_os and imagem.samples in imagens_retirada
        assert "Sem miniatura" not in retirada[0].get_text()
        ocorrencias = retirada[0].get_image_info()
        arte = next(i for i in ocorrencias if i["width"] == 120 and i["height"] == 40)
        rect = pymupdf.Rect(arte["bbox"])
        assert rect.width / rect.height == pytest.approx(3, abs=0.01)


def test_miniatura_quebrada_mantem_material_e_quantidade(tmp_path):
    os, retirada = _partes(_gerar(tmp_path, [_item("PAINEL", 2, thumbnail_bytes=b"corrompida")]))
    assert "Sem" in retirada and "miniatura" in retirada
    assert _quantidades(os) == _quantidades(retirada) == ["2"]


def test_falha_ao_trocar_retirada_preserva_os_e_retirada_anteriores(tmp_path, monkeypatch):
    import retirada_material as modulo
    caminho = pathlib.Path(_gerar(tmp_path, [_item("PAINEL", 2)]))
    retirada = caminho_pdf(tmp_path, "CLIENTE TESTE")
    original_os, original_retirada = caminho.read_bytes(), retirada.read_bytes()
    substituir = modulo.os.replace

    def arquivo_aberto(origem, destino):
        if pathlib.Path(destino) == retirada:
            raise PermissionError("Retirada aberta no leitor de PDF")
        return substituir(origem, destino)

    monkeypatch.setattr(modulo.os, "replace", arquivo_aberto)
    with pytest.raises(PermissionError):
        _gerar(tmp_path, [_item("PAINEL", 7)])
    assert caminho.read_bytes() == original_os
    assert retirada.read_bytes() == original_retirada
    assert not list(tmp_path.glob(".os_retirada_*"))
