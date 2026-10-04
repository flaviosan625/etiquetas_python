"""
Montagem de artes numa folha so, pra aproveitar a largura do rolo.

A REGRA QUE INVERTE AQUI: no recebimento vale a medida da ARTE; na
montagem vale a medida do NOME. Nao e contradicao -- o arquivo ja foi
recebido, conferido e nomeado, entao o nome e a medida combinada, e arte
fora dela esta errada. Foi o que ele pediu em 04/10/2026: "fazer a
leitura pelo nome, ver o tamanho do arquivo e redimensionar para a medida
que pede no nome".

O limite dessa regra, que e o que mais importa travar: escalar so quando
a PROPORCAO bate. Quando nao bate, nao existe escala que conserte, e
distorcer entregaria peca deformada que so se descobre impressa.
"""
import json
import pathlib
import sys

import pymupdf
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import montagem

PT_M = montagem.PT_M


@pytest.fixture(autouse=True)
def _isolar(tmp_path, monkeypatch):
    """montagem.PASTA_RAIZ e o OneDrive de verdade: sem isto, teste cria pasta la."""
    monkeypatch.setattr(montagem, "PASTA_RAIZ", tmp_path / "_onedrive_isolado")


def arte(pasta, nome, largura_m, altura_m, cor=(0.3, 0.5, 0.8), paginas=1):
    pasta.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for _ in range(paginas):
        pagina = doc.new_page(width=largura_m * PT_M, height=altura_m * PT_M)
        pagina.draw_rect(pagina.rect, color=None, fill=cor)
    caminho = pasta / nome
    doc.save(str(caminho))
    doc.close()
    return caminho


@pytest.fixture
def pasta(tmp_path):
    p = tmp_path / "MONTAGEM ARTES DOCAN 5200"
    p.mkdir()
    return p


# ---------- a pasta diz a maquina, e a maquina diz a largura ----------


def test_a_pasta_diz_qual_maquina_e(pasta):
    assert montagem.maquina_da_pasta(pasta) == "DOCAN R5200"
    assert montagem.maquina_da_pasta(pasta.parent / "MONTAGEM ARTES SWJ 3200") == "SWJ320A"
    assert montagem.maquina_da_pasta(pasta.parent / "qualquer outra") is None


def test_a_largura_vem_do_cadastro_da_maquina():
    """5,00 e 3,20 nao estao escritos na montagem: mudam no cadastro e valem aqui."""
    assert montagem.largura_util("DOCAN R5200") == 5.00
    assert montagem.largura_util("SWJ320A") == 3.20


# ---------- o nome manda no tamanho ----------


def test_medida_vem_da_PRIMEIRA_do_nome():
    """Com duas medidas vale a primeira, que desde 02/10/2026 e a COM sangria."""
    assert montagem.medida_do_nome("1UN LONA 7.44X1.40M_LONA_C_final_7,14x1,10m") == (7.44, 1.40)


def test_arte_na_medida_certa_nao_mexe():
    assert montagem.ajuste_para((3.15, 3.77), (3.15, 3.77, 1))["acao"] == "igual"


def test_arte_deitada_so_gira():
    ajuste = montagem.ajuste_para((2.30, 1.15), (1.15, 2.30, 1))
    assert ajuste["acao"] == "girar" and ajuste["girar"] is True


def test_arte_em_escala_1_para_10_e_multiplicada():
    """A agencia desenha a lona grande em 1:10 porque o Illustrator nao passa de 5,77 m."""
    ajuste = montagem.ajuste_para((7.14, 1.10), (0.714, 0.110, 1))
    assert ajuste["acao"] == "escalar"
    assert ajuste["fator"] == 10.0


def test_arte_exportada_fora_de_medida_e_arrumada():
    """3% maior: e o caso que ele descreveu -- 'arte fora de medida vai ser arrumada'."""
    ajuste = montagem.ajuste_para((1.15, 0.90), (1.185, 0.927, 1))
    assert ajuste["acao"] == "escalar"
    assert 0.96 < ajuste["fator"] < 0.98


def test_proporcao_que_nao_bate_e_RECUSADA_nunca_distorcida():
    """
    Nao existe escala que transforme 2,00x1,80 em 2,00x1,00: ou a arte
    esta errada, ou o nome esta. Distorcer calado entregaria peca
    deformada, e isso so se descobre impressa.
    """
    ajuste = montagem.ajuste_para((2.00, 1.00), (2.00, 1.80, 1))
    assert ajuste["acao"] == "recusar"
    assert "proporção não bate" in ajuste["motivo"]


def test_meio_centimetro_de_diferenca_e_a_mesma_medida():
    """Abaixo de 5 mm e arredondamento de quem exportou, nao erro."""
    assert montagem.ajuste_para((3.15, 3.77), (3.153, 3.772, 1))["acao"] == "igual"


# ---------- ler a pasta ----------


def test_quantidade_do_nome_vira_varias_pecas(pasta):
    arte(pasta, "3UN LONA IMPRESSA 1.60X0.30M_RODAPE.pdf", 1.60, 0.30)
    pecas, recusadas = montagem.pecas_da_pasta(pasta)
    assert len(pecas) == 3 and not recusadas


def test_pdf_de_varias_paginas_vira_uma_peca_por_pagina(pasta):
    """A maquina imprime so a primeira pagina -- um quadrado escondido na 2 ja custou material."""
    arte(pasta, "1UN LONA IMPRESSA 1.00X1.00M_TOTEM.pdf", 1.00, 1.00, paginas=3)
    pecas, _ = montagem.pecas_da_pasta(pasta)
    assert [p["pagina"] for p in pecas] == [0, 1, 2]


def test_nome_sem_medida_fica_de_fora(pasta):
    arte(pasta, "arquivo_qualquer.pdf", 1.0, 1.0)
    pecas, recusadas = montagem.pecas_da_pasta(pasta)
    assert not pecas
    assert "o nome não traz medida" in recusadas[0]["motivo"]


def test_material_que_o_config_nao_conhece_fica_de_fora(pasta):
    """O material escolhe a bobina: sem ele nao da pra saber o que vai na maquina."""
    arte(pasta, "1UN XABLAU 1.00X1.00M_PECA.pdf", 1.00, 1.00)
    pecas, recusadas = montagem.pecas_da_pasta(pasta)
    assert not pecas and "não reconheci o material" in recusadas[0]["motivo"]


# ---------- montar ----------


def test_cada_material_vira_UMA_folha(pasta):
    """Lona e adesivo nao dividem bobina, e o m2 deste projeto nunca mistura material."""
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_PAINEL.pdf", 2.00, 1.00)
    arte(pasta, "1UN ADESIVO 1.26X2.02M_VITRINE.pdf", 1.26, 2.02)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "sem_clientes")

    assert sorted(f["categoria"] for f in resultado["folhas"]) == ["ADESIVO", "LONA"]
    assert all(f["arquivo"].is_file() for f in resultado["folhas"])


def test_a_folha_sai_na_largura_da_maquina(pasta):
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_PAINEL.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    with pymupdf.open(str(resultado["folhas"][0]["arquivo"])) as doc:
        assert round(doc.load_page(0).rect.width / PT_M, 2) == 5.00


def test_os_originais_saem_da_pasta_depois_de_montados(pasta):
    """Se ficassem, a passada seguinte montaria tudo de novo."""
    original = arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_PAINEL.pdf", 2.00, 1.00)

    montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    assert not original.exists()
    guardados = list((pasta / montagem.NOME_SUBPASTA_ORIGINAIS).rglob("*.pdf"))
    assert [g.name for g in guardados] == [original.name]


def test_recusada_vai_pro_conferir_COM_O_MOTIVO_escrito(pasta):
    """Peca que some sem explicacao e peca que nao vai ser produzida."""
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_DEFORMADA.pdf", 2.00, 1.80)

    montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    conferir = pasta / montagem.NOME_SUBPASTA_PROBLEMAS
    assert (conferir / "1UN LONA IMPRESSA 2.00X1.00M_DEFORMADA.pdf").is_file()
    motivo = (conferir / "1UN LONA IMPRESSA 2.00X1.00M_DEFORMADA.pdf.motivo.txt").read_text(
        encoding="utf-8")
    assert "proporção não bate" in motivo


def test_duas_pecas_de_mesma_medida_nao_trocam_de_rotulo(pasta):
    """
    A LATERAL_ESQUERDA e a LATERAL_DIREITA tem 0,90 x 2,40 as duas. Se o
    encaixe perdesse a identidade, o rotulo de uma iria pra outra -- e
    quem corta penduraria a arte errada na parede errada.
    """
    arte(pasta, "1UN LONA IMPRESSA 0.90X2.40M_LATERAL_ESQUERDA.pdf", 0.90, 2.40)
    arte(pasta, "1UN LONA IMPRESSA 0.90X2.40M_LATERAL_DIREITA.pdf", 0.90, 2.40)

    montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    ficha = json.loads(next(pasta.glob("*.json")).read_text(encoding="utf-8"))
    nomes = {p["arquivo"] for p in ficha["pecas"]}
    assert len(nomes) == 2, "cada arte tem que aparecer uma vez, com o nome dela"


def test_a_canaleta_nao_invade_a_peca_de_baixo(pasta):
    """
    Os 5 cm de dados sao espaco RESERVADO no encaixe, nao sobra. No
    primeiro desenho (04/10/2026) o rotulo caiu dentro da peca seguinte.
    """
    for i in range(4):
        arte(pasta, f"1UN LONA IMPRESSA 2.40X1.00M_PECA_{i}.pdf", 2.40, 1.00)

    pecas, _ = montagem.pecas_da_pasta(pasta)
    postas, _ = montagem.encaixar(pecas, 5.00)

    for _, x, y, largura, altura, _girada in postas:
        faixa = (x, y + altura + montagem.FOLGA_M,
                 x + largura, y + altura + montagem.FOLGA_M + montagem.CANALETA_M)
        for _, ox, oy, olargura, oaltura, _g in postas:
            if (ox, oy) == (x, y):
                continue
            separados = (ox >= faixa[2] or ox + olargura <= faixa[0]
                         or oy >= faixa[3] or oy + oaltura <= faixa[1])
            assert separados, f"a canaleta de ({x},{y}) cai dentro da peça de ({ox},{oy})"


def test_o_json_ao_lado_guarda_as_pecas(pasta):
    """
    Sem ele a montagem APAGARIA a comprovacao: pro registro de producao a
    folha e UM arquivo entregue, e as pecas sumiriam do relatorio do
    cliente.
    """
    arte(pasta, "2UN LONA IMPRESSA 1.00X1.00M_PECA.pdf", 1.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    ficha = json.loads(resultado["folhas"][0]["arquivo"].with_suffix(".json").read_text(
        encoding="utf-8"))
    assert len(ficha["pecas"]) == 2
    assert ficha["area_pecas_m2"] == 2.0
    assert ficha["folha_m"][0] == 5.0
    assert ficha["pecas"][0]["posicao_m"] and ficha["pecas"][0]["medida_m"] == [1.0, 1.0]


def test_a_escala_aplicada_fica_escrita_no_registro(pasta):
    """Numero deduzido nunca se passa por declarado: a arte foi mexida, entao esta escrito."""
    arte(pasta, "1UN LONA IMPRESSA 7.14X1.10M_LONA_A.pdf", 0.714, 0.110)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    ficha = json.loads(resultado["folhas"][0]["arquivo"].with_suffix(".json").read_text(
        encoding="utf-8"))
    assert ficha["pecas"][0]["ajuste"] == "escalar"
    assert ficha["pecas"][0]["fator"] == 10.0


def test_pasta_vazia_nao_gera_folha(pasta):
    assert montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")["folhas"] == []


# ---------- o nome de saida ----------


def test_o_nome_de_saida_leva_o_cliente_e_a_especificacao():
    """
    Ele pediu o cliente no nome. E a especificacao na frente porque o nome
    do arquivo e o banco de dados: a folha montada e UMA peca de material.
    """
    nome = montagem.nome_da_folha("VIBRA", "LONA", 5.00, 9.86, 13)
    assert nome.startswith("1UN LONA 5.00X9.86M")
    assert "VIBRA" in nome and "13pecas" in nome and nome.endswith(".pdf")


def test_sem_cliente_reconhecido_o_nome_nao_inventa():
    nome = montagem.nome_da_folha("", "LONA", 5.00, 2.00, 1)
    assert nome.startswith("1UN LONA 5.00X2.00M_MONTAGEM")


def test_o_cliente_sai_do_nome_dos_arquivos(pasta, tmp_path):
    """A arte da producao leva '<especificacao>_<CLIENTE>_<descricao>'."""
    raiz = tmp_path / "clientes"
    (raiz / "VIBRA").mkdir(parents=True)
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=raiz)

    assert resultado["folhas"][0]["cliente"] == "VIBRA"
    assert "VIBRA" in resultado["folhas"][0]["arquivo"].name


# ---------- o rotulo ----------


def test_o_rotulo_corta_a_especificacao_nunca_a_descricao():
    """
    Cortar o nome pelo fim deixava '1UN DECORFLEX 4.30X0.80M_~' e jogava
    fora o 'SPFW26_PASSARELA_PISO', que e o que diz qual peca e.
    """
    descricao, especificacao = montagem.descricao_e_especificacao(
        "1UN DECORFLEX 4.30X0.80M_SPFW26_PASSARELA_PISO.pdf")
    assert descricao == "SPFW26_PASSARELA_PISO"
    assert especificacao == "1UN DECORFLEX"


def test_nome_sem_medida_vira_descricao_inteira():
    descricao, especificacao = montagem.descricao_e_especificacao("PAINEL_DO_FUNDO.pdf")
    assert descricao == "PAINEL_DO_FUNDO" and especificacao == ""


# ---------- a pasta se resolvendo sozinha ----------


def test_pasta_ainda_recebendo_arquivo_NAO_monta(pasta):
    """
    Ele larga dez arquivos seguidos e pelo OneDrive eles chegam um a um.
    Montar no primeiro faria uma folha de UMA peca e jogaria as outras
    nove numa segunda folha.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_PECA.pdf", 2.00, 1.00)

    assert montagem.pasta_parada(pasta) is False


def test_pasta_parada_ha_tempo_monta(pasta):
    import os
    import time

    caminho = arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_PECA.pdf", 2.00, 1.00)
    antigo = time.time() - 60 * 10
    os.utime(caminho, (antigo, antigo))

    assert montagem.pasta_parada(pasta) is True


def test_pasta_vazia_nao_esta_parada_esta_vazia(pasta):
    """Sem nada pra montar nao e 'parada': e 'nao tem o que fazer'."""
    assert montagem.pasta_parada(pasta) is False


def test_uma_pasta_com_problema_nao_impede_a_outra(tmp_path, monkeypatch):
    """Arte problematica numa maquina nao pode deixar a outra sem montar."""
    import os
    import time

    raiz = tmp_path / "_onedrive"
    docan = raiz / "MONTAGEM ARTES DOCAN 5200"
    swj = raiz / "MONTAGEM ARTES SWJ 3200"
    for p, nome in ((docan, "1UN LONA IMPRESSA 2.00X1.00M_A.pdf"),
                    (swj, "1UN LONA IMPRESSA 1.00X1.00M_B.pdf")):
        caminho = arte(p, nome, 2.00 if p is docan else 1.00, 1.00)
        antigo = time.time() - 600
        os.utime(caminho, (antigo, antigo))

    original = montagem.montar_pasta

    def explode(pasta_, *a, **k):
        if "DOCAN" in str(pasta_):
            raise RuntimeError("arte quebrada")
        return original(pasta_, *a, **k)

    monkeypatch.setattr(montagem, "montar_pasta", explode)
    avisos = []

    feitas = montagem.conferir(raiz=raiz, logger=lambda n, m: avisos.append(m))

    assert len(feitas) == 1, "a SWJ tinha que montar mesmo com a DOCAN quebrando"
    assert any("arte quebrada" in a for a in avisos), "e o motivo tem que ficar no log"
