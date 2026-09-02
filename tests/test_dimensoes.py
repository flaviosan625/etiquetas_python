import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf

from dimensoes import (
    contem_palavra, extrair_dimensoes, calcular_desperdicio_item, extrair_quantidade,
    identificar_categoria, identificar_categoria_extra, identificar_variante, formatar_variante,
    calcular_desperdicio_chapa_grande, medir_conteudo_pagina, dimensao_da_arte, nome_sem_prefixo_reconhecido,
)


def test_identificar_categoria_por_nome_direto():
    materiais = {"LONA": {}, "ADESIVO": {}, "PVC": {}}
    categoria, candidatas = identificar_categoria("1UN LONA 1,00X1,00.PDF", materiais)
    assert categoria == "LONA"
    assert candidatas == ["LONA"]


def test_identificar_categoria_por_sinonimo():
    materiais = {"LONA": {}, "ADESIVO": {}}
    categoria, _ = identificar_categoria("1UN VINIL 1,00X1,00.PDF", materiais, {"VINIL": "ADESIVO"})
    assert categoria == "ADESIVO"


def test_identificar_categoria_ignora_sinonimo_sem_categoria_valida():
    # sinônimo aponta pra uma categoria que não existe no cadastro atual
    materiais = {"LONA": {}}
    categoria, candidatas = identificar_categoria("1UN VINIL 1,00X1,00.PDF", materiais, {"VINIL": "ADESIVO"})
    assert categoria is None
    assert candidatas == []


def test_identificar_categoria_mais_especifica_vence_ambiguidade():
    # "PS_01" bate tanto com "PS" quanto com um hipotético "PS_01" mais
    # específico — o nome mais longo deve vencer
    materiais = {"PS": {}, "PS ESPECIAL": {}}
    categoria, candidatas = identificar_categoria("BANNER PS ESPECIAL 1X1.PDF", materiais)
    assert categoria == "PS ESPECIAL"
    assert set(candidatas) == {"PS", "PS ESPECIAL"}


def test_identificar_categoria_nenhuma_bate():
    materiais = {"LONA": {}, "ADESIVO": {}}
    categoria, candidatas = identificar_categoria("1UN TECIDO IMPRESSO 1,00X1,00.PDF", materiais)
    assert categoria is None
    assert candidatas == []


def test_contem_palavra_evita_falso_positivo_em_substring():
    assert contem_palavra("BANNER_XPS_60X40.PDF", "PS") is False


def test_identificar_categoria_extra_ps_adesivado():
    materiais = {"PS": {}, "ADESIVO": {}, "ACRILICO": {}}
    materiais_compostos = {"ADESIVADO": "ADESIVO"}
    categoria_extra = identificar_categoria_extra("1UN PS ADESIVADO 1,00X1,00.PDF", materiais, materiais_compostos)
    assert categoria_extra == "ADESIVO"


def test_identificar_categoria_extra_acrilico_adesivado():
    materiais = {"PS": {}, "ADESIVO": {}, "ACRILICO": {}}
    materiais_compostos = {"ADESIVADO": "ADESIVO"}
    categoria_extra = identificar_categoria_extra(
        "1UN ACRILICO ADESIVADO 1,00X1,00.PDF", materiais, materiais_compostos
    )
    assert categoria_extra == "ADESIVO"


def test_identificar_categoria_extra_nao_confunde_impresso_com_adesivado():
    # "IMPRESSO" é um processo diferente (impressão direta, sem adesivo
    # colado em cima) — nunca deve contar categoria extra nenhuma
    materiais = {"PS": {}, "ADESIVO": {}}
    materiais_compostos = {"ADESIVADO": "ADESIVO"}
    categoria_extra = identificar_categoria_extra("1UN PS 10MM IMPRESSO 1,00X1,00.PDF", materiais, materiais_compostos)
    assert categoria_extra is None


def test_identificar_categoria_extra_sem_material_composto_configurado():
    materiais = {"PS": {}}
    categoria_extra = identificar_categoria_extra("1UN PS ADESIVADO 1,00X1,00.PDF", materiais, {})
    assert categoria_extra is None
    assert contem_palavra("PLACA_PS_60X40.PDF", "PS") is True


def test_contem_palavra_aceita_numero_colado_depois():
    # nome real: "VINIL150" (Vinil, 150cm de largura), sem separador
    assert contem_palavra("1UN VINIL150 DE LARGURA IMPRESSO.PDF", "VINIL") is True


def test_contem_palavra_ainda_rejeita_letra_colada_depois():
    # "VINILICO" não devia contar como "VINIL"
    assert contem_palavra("BANNER VINILICO ESPECIAL.PDF", "VINIL") is False


def test_extrair_dimensoes_assume_cm_quando_sem_unidade():
    d = extrair_dimensoes("banner_58x60.pdf", {})
    assert d is not None
    assert d["unidade_usada"] == "CM"
    assert round(d["area_m2"], 4) == round(0.58 * 0.60, 4)


def test_extrair_dimensoes_aceita_virgula_decimal():
    d = extrair_dimensoes("placa_1,5x2M.pdf", {})
    assert d["unidade_usada"] == "M"
    assert round(d["largura_m"], 2) == 1.5


def test_extrair_dimensoes_corrige_typo_configuravel():
    d = extrair_dimensoes("banner_58x60XM.pdf", {"XM": "CM"})
    assert d["unidade_usada"] == "CM"
    assert d["unidade_corrigida"] is True


def test_extrair_dimensoes_novo_typo_configurado_funciona():
    # simula um erro de digitação novo, cadastrado só no config,
    # sem precisar mexer no código
    d = extrair_dimensoes("placa_40x50NM.pdf", {"NM": "MM"})
    assert d["unidade_usada"] == "MM"
    assert d["unidade_corrigida"] is True


def test_extrair_dimensoes_sem_medida_no_nome():
    assert extrair_dimensoes("arte_final_cliente.pdf", {}) is None


def test_extrair_dimensoes_usa_primeira_ocorrencia():
    # a primeira medida é sempre a medida real do cliente; uma segunda
    # medida no nome (acrescentada depois pela produção) é ignorada
    d = extrair_dimensoes("pedido_123x456cm_58x60cm.pdf", {})
    assert round(d["largura_m"], 2) == 1.23


def test_extrair_quantidade_reconhece_prefixo_un():
    assert extrair_quantidade("1UN ADESIVO IMPRESSA 2.30X2.30M.pdf") == (1, True)
    assert extrair_quantidade("12UN LONA banner.pdf") == (12, True)
    assert extrair_quantidade("3 UN mdf recorte.pdf") == (3, True)


def test_extrair_quantidade_assume_1_quando_ausente():
    assert extrair_quantidade("banner_58x60.pdf") == (1, False)


def test_extrair_quantidade_reconhece_unidades_por_extenso_no_fim_do_nome():
    # arte vinda de fora (agência/cliente) não segue a convenção "NUN"
    # no início — traz "N Unidade(s)" por extenso no FIM do nome.
    # Achado real (2026-08-31): arquivos TIF da FESTA ALEMA perdiam a
    # quantidade real, virando sempre 1.
    assert extrair_quantidade("AF_Banner 50x250_Lona_8 Unidades.tif") == (8, True)
    assert extrair_quantidade("AF_Colunas_220x300+sangria_lona_18 Unidades.tif") == (18, True)
    assert extrair_quantidade("AF_saia_palco_900x100+sangria_LONA_1 Unidade.tif") == (1, True)
    assert extrair_quantidade("AF_mapa_entrada_300x250+sangria_lona_1Unidade.tif") == (1, True)  # sem espaço


def test_extrair_quantidade_prefixo_nun_tem_prioridade_sobre_extenso():
    # quando os dois padrões aparecem (improvável, mas não pode dar
    # resultado ambíguo), o prefixo "NUN" — convenção interna da
    # fábrica — sempre vence.
    assert extrair_quantidade("2UN LONA banner_5 Unidades.pdf") == (2, True)


def test_extrair_quantidade_ignora_separador_entre_numero_e_un():
    # nome vem de digitação manual — separador entre a quantidade e
    # "UN" varia sem padrão (2026-08-29, pedido do usuário: pontuação
    # não pode influenciar a leitura do arquivo)
    assert extrair_quantidade("1_UN_LONA_2,00X1,00M.pdf") == (1, True)
    assert extrair_quantidade("1-UN-LONA-2,00X1,00M.pdf") == (1, True)
    assert extrair_quantidade("1.UN.LONA.2,00X1,00M.pdf") == (1, True)
    assert extrair_quantidade("1UN_LONA_2,00X1,00M.pdf") == (1, True)  # "UN" colado no número, mas seguido de "_"
    assert extrair_quantidade("4UN-PVC-recorte.pdf") == (4, True)


def test_extrair_dimensoes_ignora_separador_ao_redor_do_x():
    d1 = extrair_dimensoes("1UN LONA 2,10_X_2,10M.pdf", {})
    assert round(d1["area_m2"], 2) == 4.41
    d2 = extrair_dimensoes("1UN LONA 2,10-X-2,10M.pdf", {})
    assert round(d2["area_m2"], 2) == 4.41
    d3 = extrair_dimensoes("1UN LONA 2,10.X.2,10M.pdf", {})
    assert round(d3["area_m2"], 2) == 4.41


_VARIANTES_PVC = [
    {"espessura": "10MM", "cor": "BRANCO"},
    {"espessura": "10MM", "cor": "PRETO"},
    {"espessura": "20MM", "cor": "BRANCO"},
    {"espessura": "20MM", "cor": "PRETO"},
]


def test_identificar_variante_encontra_espessura_e_cor():
    v = identificar_variante("1UN PVC 10MM RECORTE_PRETO_Credenciamento.pdf", _VARIANTES_PVC)
    assert v == {"espessura": "10MM", "cor": "PRETO"}


def test_identificar_variante_nao_bate_sem_as_duas_palavras():
    # só a espessura, sem a cor — não deve "adivinhar"
    assert identificar_variante("1UN PVC 10MM RECORTE.pdf", _VARIANTES_PVC) is None


def test_identificar_variante_sem_lista_retorna_none():
    assert identificar_variante("1UN MDF 9MM RECORTE.pdf", []) is None


_VARIANTES_MDF = [
    {"espessura": "6MM"}, {"espessura": "9MM"}, {"espessura": "15MM"}, {"espessura": "18MM"},
    {"espessura": "6MM", "cor": "VERDE", "rotulo": "MDF HIDRO"},
    {"espessura": "9MM", "cor": "VERDE", "rotulo": "MDF HIDRO"},
]


def test_identificar_variante_so_espessura_sem_cor_no_arquivo():
    # MDF cru: nunca tem cor no nome, a variante não exige cor
    v = identificar_variante("1UN MDF 9MM RECORTE_Tiktok Criadores.pdf", _VARIANTES_MDF)
    assert v == {"espessura": "9MM"}


def test_identificar_variante_especifica_tem_prioridade_sobre_generica():
    # com "verde" no nome, tem que cair na variante hidro, não na crua de mesma espessura
    v = identificar_variante("1UN MDF_VERDE_9MM_RECORTE.pdf", _VARIANTES_MDF)
    assert v == {"espessura": "9MM", "cor": "VERDE", "rotulo": "MDF HIDRO"}


def test_formatar_variante_com_cor():
    assert formatar_variante({"espessura": "10MM", "cor": "PRETO"}) == "10MM · PRETO"


def test_formatar_variante_com_rotulo_prioriza_rotulo():
    assert formatar_variante({"espessura": "9MM", "cor": "VERDE", "rotulo": "MDF HIDRO"}) == "9MM · MDF HIDRO"


def test_formatar_variante_so_espessura():
    assert formatar_variante({"espessura": "9MM"}) == "9MM"


def test_formatar_variante_none():
    assert formatar_variante(None) == ""


def test_calcular_desperdicio_chapa_grande_escolhe_orientacao_com_menos_chapas():
    # peça real (BASE_RAMPA do pedido CIF): 5.00 x 3.60m numa chapa de MDF 1.85 x 2.70m
    # sem girar: 3 colunas x 2 linhas = 6 chapas; girada: 2x2 = 4 chapas
    dimensao = {"largura_m": 5.00, "altura_m": 3.60}
    r = calcular_desperdicio_chapa_grande(dimensao, 1.85, 2.70)
    assert r["total_chapas"] == 4
    assert r["girada"] is True
    assert round(r["desperdicio_m2"], 2) == round(4 * 1.85 * 2.70 - 5.00 * 3.60, 2)


def test_calcular_desperdicio_chapa_grande_sem_diferenca_de_orientacao():
    dimensao = {"largura_m": 5.00, "altura_m": 4.99}
    r = calcular_desperdicio_chapa_grande(dimensao, 1.85, 2.70)
    assert r["total_chapas"] == 6


def test_calcular_desperdicio_peca_cabe_no_rolo():
    dimensao = {"largura_m": 0.5, "altura_m": 2.0}
    r = calcular_desperdicio_item(dimensao, 1.0)
    assert r is not None
    assert round(r["desperdicio_m2"], 2) == round((1.0 - 0.5) * 2.0, 2)


def test_calcular_desperdicio_peca_nao_cabe_no_rolo():
    # mesmo o lado menor da peça (1.5m) é maior que a largura do rolo (1.0m)
    dimensao = {"largura_m": 2.0, "altura_m": 1.5}
    r = calcular_desperdicio_item(dimensao, 1.0)
    assert r is None


def _pagina_com_desenho(largura_pagina, altura_pagina, retangulo):
    doc = pymupdf.open()
    pagina = doc.new_page(width=largura_pagina, height=altura_pagina)
    pagina.draw_rect(retangulo, color=(0, 0, 0), fill=(0, 0, 0))
    return doc, pagina


def test_medir_conteudo_pagina_ignora_margem_em_volta_do_desenho():
    # arquivo com "gabarito"/máscara: a página é maior que a peça real —
    # medir_conteudo_pagina deve achar só o desenho, não a página inteira
    doc, pagina = _pagina_com_desenho(400, 400, pymupdf.Rect(50, 50, 150, 150))
    caixa = medir_conteudo_pagina(pagina)
    assert round(caixa.width) == 100
    assert round(caixa.height) == 100
    doc.close()


def test_medir_conteudo_pagina_nao_extrapola_a_pagina():
    # desenho com coordenadas fora da página (linha-guia/marca de corte
    # sobrando fora da área visível) não pode inflar o resultado — o
    # conteúdo real nunca é considerado maior que a própria página
    doc = pymupdf.open()
    pagina = doc.new_page(width=200, height=200)
    pagina.draw_line(pymupdf.Point(-1000, -1000), pymupdf.Point(5000, 5000))
    caixa = medir_conteudo_pagina(pagina)
    assert caixa.width <= 200
    assert caixa.height <= 200
    doc.close()


def test_medir_conteudo_pagina_vazia_retorna_vazio():
    doc = pymupdf.open()
    pagina = doc.new_page(width=200, height=200)
    caixa = medir_conteudo_pagina(pagina)
    assert caixa.is_empty
    doc.close()


def test_dimensao_da_arte_sem_conteudo_retorna_none():
    doc = pymupdf.open()
    pagina = doc.new_page(width=200, height=200)
    assert dimensao_da_arte(pagina) is None
    doc.close()


def test_dimensao_da_arte_usa_tamanho_do_desenho_sem_escala():
    # sem referência confiável pra comparar, não inventa escala — usa
    # o tamanho do desenho como veio, mesmo se parecer "pequeno demais"
    doc, pagina = _pagina_com_desenho(2000, 2000, pymupdf.Rect(0, 0, 1500, 200))
    dimensao = dimensao_da_arte(pagina)
    largura_esperada_m = 1500 / 72 * 0.0254
    assert round(dimensao["largura_m"], 3) == round(largura_esperada_m, 3)
    assert dimensao["origem"] == "arte"
    doc.close()


def test_nome_sem_prefixo_reconhecido_tira_quantidade_e_medida():
    nome = nome_sem_prefixo_reconhecido("1UN PS 10MM IMPRESSO + GABARITO 1.20X0.22 UCB_120xproporcao.pdf")
    assert nome == "PS 10MM IMPRESSO + GABARITO UCB_120xproporcao.pdf"


def test_nome_sem_prefixo_reconhecido_preserva_marca_de_reposicao():
    nome = nome_sem_prefixo_reconhecido("1UN LONA 2,00X1,00M_c - REPOSICAO.pdf")
    assert "REPOSICAO" in nome


def test_nome_sem_prefixo_reconhecido_sem_medida_so_tira_quantidade():
    nome = nome_sem_prefixo_reconhecido("2UN LOGO EM PS RECORTE APLICADO EM ACRILICO CRISTAL.pdf")
    assert nome == "LOGO EM PS RECORTE APLICADO EM ACRILICO CRISTAL.pdf"
