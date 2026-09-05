import datetime
import json

import pymupdf
import pytest

import documento_enviados as doc
from documento_enviados import (
    caminho_dados, caminho_pdf, carregar, gerar_pdf, miniatura, pasta_documento, regravar_pdf, registrar,
)

ORDEM = ["LONA", "ADESIVO", "PS", "ACRILICO", "PVC", "MDF"]


def _registro(arquivo="1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf", quando="2026-09-05T14:22:03",
              categoria="LONA", quantidade=1, area=2.00, maquina="SWJ320A", girou=False,
              producao="PRODUCAO 03_09"):
    return {
        "quando": quando, "arquivo": arquivo, "maquina": maquina, "producao": producao,
        "pasta_trabalho": "LONAS", "categoria": categoria, "quantidade": quantidade,
        "dimensao": {"largura_m": 1.00, "altura_m": 2.00, "area_m2": 2.00},
        "area_total_m2": area, "girou_previsto": girou, "bytes": 4096,
    }


def _cliente(tmp_path, nome="FESTA ALEMA"):
    pasta = tmp_path / "EVENTOS" / nome
    pasta.mkdir(parents=True)
    return pasta


def _texto_do_pdf(caminho):
    documento = pymupdf.open(str(caminho))
    texto = "\n".join(pagina.get_text() for pagina in documento)
    documento.close()
    return texto


# ---------------------------------------------------------------- pasta e dados

def test_pasta_so_nasce_no_primeiro_envio(tmp_path):
    """Sem isso, toda pasta de cliente ganharia uma 'Enviados' vazia — e pasta demais foi a objeção."""
    cliente = _cliente(tmp_path)

    assert carregar(cliente) == {"cliente": "FESTA ALEMA", "envios": []}
    assert not pasta_documento(cliente).exists()


def test_registrar_cria_a_pasta_e_guarda_o_envio(tmp_path):
    cliente = _cliente(tmp_path)

    registrar(cliente, [_registro()])

    assert caminho_dados(cliente).exists()
    assert len(carregar(cliente)["envios"]) == 1


def test_reenvio_do_mesmo_arquivo_vira_linha_nova(tmp_path):
    """Regra do usuário: reenvio soma, não substitui — material foi gasto de novo."""
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro(quando="2026-09-04T09:12:00")])
    registrar(cliente, [_registro(quando="2026-09-05T16:40:00")])

    envios = carregar(cliente)["envios"]

    assert len(envios) == 2
    assert [e["quando"] for e in envios] == ["2026-09-04T09:12:00", "2026-09-05T16:40:00"]


def test_reenvio_reaproveita_a_miniatura_do_primeiro_envio(tmp_path):
    """O original pode ter virado placeholder de 1,83 GB — não dá pra reabrir a cada envio."""
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()], miniaturas={"1UN LONA IMPRESSA_faixa_1,00x2,00M.pdf": b"jpegfalso"})
    registrar(cliente, [_registro(quando="2026-09-06T10:00:00")])

    envios = carregar(cliente)["envios"]

    assert envios[0]["miniatura_b64"] == envios[1]["miniatura_b64"]
    assert envios[1]["miniatura_b64"] is not None


def test_json_corrompido_nao_derruba_nem_some_em_silencio(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()])
    caminho_dados(cliente).write_text("{ isso nao e json", encoding="utf-8")

    assert carregar(cliente)["envios"] == []
    assert caminho_dados(cliente).with_suffix(".json.bak").exists()


def test_gravacao_e_atomica(tmp_path):
    """Queda de energia no meio da gravação não pode deixar o histórico truncado."""
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()])

    assert not list(pasta_documento(cliente).glob("*.tmp"))
    json.loads(caminho_dados(cliente).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- PDF

def test_sem_envio_nenhum_nao_gera_pdf(tmp_path):
    assert gerar_pdf(_cliente(tmp_path), ORDEM) is None


def test_pdf_mostra_cliente_material_medida_e_hora(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()])

    caminho = gerar_pdf(cliente, ORDEM, agora=datetime.datetime(2026, 9, 5, 16, 40))
    texto = _texto_do_pdf(caminho)

    assert "FESTA ALEMA" in texto
    assert "ENVIADOS PARA IMPRESSÃO" in texto
    assert "LONA" in texto
    assert "2,00 m²" in texto
    assert "05/09 14:22" in texto
    assert "SWJ320A" in texto
    assert "PRODUCAO 03_09" in texto


def test_pdf_fica_no_nome_do_cliente_dentro_de_enviados(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()])

    caminho = gerar_pdf(cliente, ORDEM)

    assert caminho == caminho_pdf(cliente)
    assert caminho.name == "ENVIADOS - FESTA ALEMA.pdf"
    assert caminho.parent.name == "Enviados"


def test_pdf_marca_o_segundo_envio_e_nao_o_primeiro(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro(quando="2026-09-04T09:12:00")])
    registrar(cliente, [_registro(quando="2026-09-05T16:40:00")])

    texto = _texto_do_pdf(gerar_pdf(cliente, ORDEM))

    assert "2º ENVIO" in texto
    assert "3º ENVIO" not in texto


def test_pdf_marca_o_giro(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro(girou=True)])

    assert "GIROU 90°" in _texto_do_pdf(gerar_pdf(cliente, ORDEM))


def test_subtotal_por_material_nunca_e_combinado(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [
        _registro(categoria="LONA", area=18.00, arquivo="lona_a.pdf"),
        _registro(categoria="ADESIVO", area=2.52, arquivo="adesivo_a.pdf", maquina="UJV 100 UNY CV"),
    ])

    texto = _texto_do_pdf(gerar_pdf(cliente, ORDEM))

    assert "18,00 m²" in texto
    assert "2,52 m²" in texto
    assert "20,52" not in texto  # o total combinado NUNCA aparece


def test_subtotal_soma_reenvio_porque_material_foi_gasto_de_novo(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro(area=2.52, quando="2026-09-04T09:12:00")])
    registrar(cliente, [_registro(area=2.52, quando="2026-09-05T16:40:00")])

    texto = _texto_do_pdf(gerar_pdf(cliente, ORDEM))

    assert "5,04 m²" in texto
    assert "2 envios" in texto


def test_subtotal_mostra_o_periodo_dos_envios(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro(quando="2026-09-04T09:12:00")])
    registrar(cliente, [_registro(quando="2026-09-05T16:40:00")])

    texto = _texto_do_pdf(gerar_pdf(cliente, ORDEM))

    assert "04/09 09:12 a 05/09 16:40" in texto


def test_pdf_e_sempre_refeito_do_zero(tmp_path):
    """PDF apagado por engano volta igualzinho no envio seguinte — o JSON é a fonte de verdade."""
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()])
    gerar_pdf(cliente, ORDEM)
    caminho_pdf(cliente).unlink()

    registrar(cliente, [_registro(quando="2026-09-06T10:00:00")])
    documento = pymupdf.open(str(gerar_pdf(cliente, ORDEM)))
    total_paginas = len(documento)
    documento.close()

    assert total_paginas == 1
    assert len(carregar(cliente)["envios"]) == 2


def test_muitos_envios_pagina_e_numeram_certo(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [
        _registro(arquivo=f"1UN LONA IMPRESSA_peca_{i:02d}_1,00x2,00M.pdf") for i in range(30)
    ])

    caminho = gerar_pdf(cliente, ORDEM)
    documento = pymupdf.open(str(caminho))
    total = len(documento)
    texto_primeira = documento[0].get_text()
    documento.close()

    assert total > 1
    assert f"1 / {total}" in texto_primeira


def test_documento_nao_engorda_demais(tmp_path):
    """
    Fica salvo o ano todo e cresce a cada envio, então o custo POR LINHA
    é o que importa. Duas armadilhas já pegas aqui (2026-09-05): cada
    insert_htmlbox embute ~91 KB de fonte, e salvar sem deflate deixa o
    logo descomprimido. Com as duas, 30 linhas davam 3,5 MB; sem elas,
    dão ~53 KB. O limite abaixo pega qualquer uma das duas voltando.
    """
    cliente = _cliente(tmp_path)
    registrar(cliente, [
        _registro(arquivo=f"1UN LONA IMPRESSA_peca_{i:02d}_1,00x2,00M.pdf") for i in range(30)
    ])

    assert gerar_pdf(cliente, ORDEM).stat().st_size < 100 * 1024


def test_documento_nao_embute_fonte(tmp_path):
    """
    O documento desenha só com as fontes base do PDF. Se alguém voltar a
    usar insert_htmlbox aqui, cada chamada embute um subconjunto próprio
    e o arquivo explode — este teste é o alarme.
    """
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()])

    documento = pymupdf.open(str(gerar_pdf(cliente, ORDEM)))
    embutidas = [f for pagina in documento for f in pagina.get_fonts(full=True) if f[1] != "n/a"]
    documento.close()

    assert embutidas == []


def test_categoria_desconhecida_nao_derruba_o_documento(tmp_path):
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro(categoria=None)])

    assert "SEM MATERIAL" in _texto_do_pdf(gerar_pdf(cliente, ORDEM))


def test_registro_sem_medida_aparece_sem_inventar_area(tmp_path):
    cliente = _cliente(tmp_path)
    sem_medida = _registro(arquivo="1UN PVC 10MM RECORTE_Castelo_PVC Adesivado.pdf")
    sem_medida["dimensao"] = None
    sem_medida["area_total_m2"] = None
    registrar(cliente, [sem_medida])

    assert "Medida não informada" in _texto_do_pdf(gerar_pdf(cliente, ORDEM))


# ---------------------------------------------------------------- miniatura

def test_miniatura_de_pdf_de_verdade(tmp_path):
    arte = tmp_path / "arte.pdf"
    documento = pymupdf.open()
    documento.new_page(width=2000, height=1000)
    documento.save(str(arte))
    documento.close()

    bytes_thumb = miniatura(arte)

    assert bytes_thumb and bytes_thumb[:2] == b"\xff\xd8"  # JPEG


def test_miniatura_de_arquivo_que_nao_abre_devolve_none(tmp_path):
    quebrado = tmp_path / "arte.eps"
    quebrado.write_bytes(b"isso nao e um eps de verdade")

    assert miniatura(quebrado) is None


def test_miniatura_desenhada_no_pdf(tmp_path):
    cliente = _cliente(tmp_path)
    arte = tmp_path / "arte.pdf"
    documento = pymupdf.open()
    documento.new_page(width=600, height=400)
    documento.save(str(arte))
    documento.close()

    registrar(cliente, [_registro(arquivo="arte.pdf")], miniaturas={"arte.pdf": miniatura(arte)})
    gerado = pymupdf.open(str(gerar_pdf(cliente, ORDEM)))
    imagens = gerado[0].get_images()
    gerado.close()

    assert len(imagens) >= 1


# ---------------------------------------------------------------- documento aberto

def test_pdf_travado_nao_derruba_o_envio(tmp_path, monkeypatch):
    """
    O caso real: usuário com o documento aberto no leitor de PDF na
    hora do envio. Os arquivos já foram pra fila e já estão no JSON —
    só o desenho fica velho.
    """
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()])

    def trava(*args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr(doc, "gerar_pdf", trava)
    caminho, erro = regravar_pdf(cliente, ORDEM)

    assert caminho is None
    assert "Permission denied" in erro
    assert len(carregar(cliente)["envios"]) == 1


def test_material_sem_medida_nao_vira_zero_no_subtotal(tmp_path):
    """
    Num documento de comprovação, '0,00 m²' afirma que nada foi gasto —
    diferente de 'não sei a medida'. O subtotal precisa dizer a verdade.
    """
    cliente = _cliente(tmp_path)
    sem_medida = _registro(categoria="PVC", arquivo="1UN PVC 10MM RECORTE_Castelo_PVC Adesivado.pdf")
    sem_medida["dimensao"] = None
    sem_medida["area_total_m2"] = None
    registrar(cliente, [sem_medida])

    texto = _texto_do_pdf(gerar_pdf(cliente, ORDEM))

    assert "0,00 m²" not in texto
    assert "sem medida" in texto


def test_subtotal_avisa_quantos_ficaram_sem_medida(tmp_path):
    cliente = _cliente(tmp_path)
    sem_medida = _registro(categoria="LONA", arquivo="lona_sem_medida.pdf")
    sem_medida["dimensao"] = None
    sem_medida["area_total_m2"] = None
    registrar(cliente, [_registro(categoria="LONA", area=18.00, arquivo="lona_com_medida.pdf"), sem_medida])

    texto = _texto_do_pdf(gerar_pdf(cliente, ORDEM))

    assert "18,00 m²" in texto
    assert "1 sem medida no nome" in texto


def test_extensao_nao_sobra_na_descricao(tmp_path):
    """A limpeza da OS só conhece '.pdf' — aqui .tif e .jpg são a maioria."""
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro(arquivo="AF_Colunas Arena Principal_220x5500+sangria_lona.tif")])

    texto = _texto_do_pdf(gerar_pdf(cliente, ORDEM))

    assert "tif" not in texto.lower()


def test_cabecalho_nao_vaza_codigo_de_html(tmp_path):
    """O documento é desenhado com fontes base, não com HTML — entidade solta apareceria crua."""
    cliente = _cliente(tmp_path)
    registrar(cliente, [_registro()])

    texto = _texto_do_pdf(gerar_pdf(cliente, ORDEM))

    assert "&nbsp;" not in texto
    assert "&middot;" not in texto
