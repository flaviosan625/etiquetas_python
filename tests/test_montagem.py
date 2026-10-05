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
    """
    Duas isolacoes, e as duas ja morderam:

    - montagem.PASTA_RAIZ e o OneDrive de verdade: sem isto, teste cria
      pasta la.
    - os conversores do Adobe abrem o ILLUSTRATOR DE VERDADE por COM. Um
      teste com .eps na pasta chamou montar_pasta, que converte antes de
      medir, e o Illustrator subiu invisivel e travou a suite (05/10/2026).
      Zerado aqui: quem quer testar conversao passa o conversor na mao.
    """
    monkeypatch.setattr(montagem, "PASTA_RAIZ", tmp_path / "_onedrive_isolado")
    try:
        import conversao_adobe
    except Exception:       # noqa: BLE001 - sem pywin32 nao ha o que isolar
        return
    monkeypatch.setattr(conversao_adobe, "CONVERSORES_POR_EXTENSAO", {})


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
    """A pasta de montagem da DOCAN R5200 -- o nome e o DA MAQUINA, como na fila."""
    p = tmp_path / "DOCAN R5200"
    p.mkdir()
    return p


# ---------- a pasta diz a maquina, e a maquina diz a largura ----------


def test_a_pasta_diz_qual_maquina_e(pasta):
    """
    Uma pasta por maquina, com o NOME da maquina -- igual a fila (pedido
    dele, 04/10/2026). Nome igual em todo lugar e o que liga arquivo a
    maquina sem tabela de conversao.
    """
    assert montagem.maquina_da_pasta(pasta) == "DOCAN R5200"
    assert montagem.maquina_da_pasta(pasta.parent / "SWJ320A") == "SWJ320A"
    assert montagem.maquina_da_pasta(pasta.parent / "ujv 100 uny cv") == "UJV 100 UNY CV"
    assert montagem.maquina_da_pasta(pasta.parent / "qualquer outra") is None


def test_so_as_duas_maquinas_que_ele_escolheu_tem_pasta(tmp_path):
    """
    "Deixar apenas a DOCAN 5200 e a SWJ 320A, o restante nos fazemos
    manualmente" (04/10/2026). O interruptor e o campo 'montagem' no
    cadastro: maquina nova nao passa a montar sozinha sem alguem decidir.
    """
    criadas = montagem.garantir_pastas(raiz=tmp_path)

    assert sorted(criadas) == ["DOCAN R5200", "SWJ320A"]
    assert all(p.is_dir() for p in criadas.values())
    assert criadas["SWJ320A"].name == "SWJ320A", "o nome da pasta e o da maquina, igual a fila"


def test_a_plana_so_precisa_do_campo_pra_voltar(tmp_path):
    """
    O codigo da mesa continua aqui e testado: a H2525 monta em chapas no
    dia em que ele quiser, e ai e so o campo no cadastro.
    """
    import copy

    import rasterlink_hotfolder as rl_hf

    maquinas = copy.deepcopy(rl_hf.MAQUINAS)
    maquinas["DOCAN H2525"]["montagem"] = True

    criadas = montagem.garantir_pastas(raiz=tmp_path, maquinas=maquinas)

    assert "DOCAN H2525" in criadas


def test_a_margem_e_por_maquina_e_ZERO_em_quem_monta():
    """
    Ele deu uma pra cada (04/10/2026) -- cada maquina agarra o material
    de um jeito. Nas duas que MONTAM ela zerou em 05/10/2026: *"a folga
    de 2 cm de cada lado eu coloco manualmente na maquina na hora da
    impressao... eu me preocupo com a folga"*. Borda desenhada aqui seria
    folga DUAS vezes, e a arte sairia de 4,96 em vez de 5,00.
    """
    assert montagem.margem("DOCAN R5200") == 0.0
    assert montagem.margem("SWJ320A") == 0.0
    assert montagem.margem("DOCAN H2525") == 0.02
    assert montagem.margem("UJV 100 UNY CV") == 0.03


def test_a_largura_do_FECHAMENTO_vem_do_cadastro_e_nao_e_a_da_maquina():
    """
    Sao duas coisas: 'largura_util_m' e o que a maquina imprime e responde
    "cabe?" no vigia; 'largura_montagem_m' e o numero REDONDO com que a
    folha fecha (5,00 e 3,20, pedido dele em 05/10/2026).

    Nenhuma das duas esta escrita aqui: mudam no cadastro da maquina e
    valem na montagem. Foi assim que a correcao de 5,00 pra 5,20 na DOCAN
    (04/10/2026) chegou aqui sem eu mexer nesta linha.
    """
    assert montagem.largura_util("DOCAN R5200") == 5.00
    assert montagem.largura_util("SWJ320A") == 3.20
    import rasterlink_hotfolder as rl_hf

    assert rl_hf.MAQUINAS["DOCAN R5200"]["largura_util_m"] == 5.04, \
        "o que a maquina imprime nao muda porque o fechamento mudou"
    # maquina sem o campo cai na largura dela, como sempre
    assert montagem.largura_util("UJV 100 UNY CV") == 1.27
    assert montagem.mesa("DOCAN H2525") == (2.50, 2.50)


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
    assert "+800 mm fora" in ajuste["motivo"], "o motivo tem que dizer QUANTO sai fora"


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


def test_a_folha_FECHA_na_largura_QUE_USA_sem_branco_em_volta(pasta):
    """
    Regra dele de 05/10/2026: *"depois que montar a arte precisa salvar
    ela sempre centralizada, ou sem margem em branco nas laterais -- eu
    centralizo ela na maquina... temos ate 5,00 m na DOCAN; se a arte
    bater 4,70, pode fechar sem branco em volta"*.

    Folha de 5,00 m nao da pra centralizar: ela ocupa tudo. Fechando no
    que usa, sobra margem pra ele acertar o alinhamento na maquina -- e o
    NOME diz a medida certa, que e de onde o m² e o estoque leem.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_PAINEL.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]

    with pymupdf.open(str(folha)) as doc:
        largura = doc.load_page(0).rect.width / PT_M
    assert round(largura, 2) == 2.00, "sobrariam 3 m de branco na folha de 5,00"

    import dimensoes

    assert dimensoes.extrair_dimensoes(folha.name)["largura_m"] == 2.00


def test_a_folha_NUNCA_passa_da_largura_da_maquina(pasta):
    """
    Aparar e aparar branco, nunca abrir espaco: o teto continua sendo o
    fechamento da maquina (5,00 na DOCAN).
    """
    for i in range(6):
        arte(pasta, f"1UN LONA IMPRESSA 1.50X1.00M_PECA_{i}.pdf", 1.50, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    with pymupdf.open(str(resultado["folhas"][0]["arquivo"])) as doc:
        for n in range(doc.page_count):
            assert doc.load_page(n).rect.width / PT_M <= 5.0001


def test_a_peca_estreita_no_canto_nao_corta_o_proprio_nome(pasta):
    """
    O rotulo comeca na borda esquerda da peca e tem 300 mm: numa peca
    estreita no canto direito e ELE quem manda na largura da folha.
    Aparar por cima dele economizaria 10 cm de branco e deixaria o refile
    sem saber que peca e aquela.
    """
    arte(pasta, "1UN LONA IMPRESSA 0.20X0.20M_VIBRA_TIRA.pdf", 0.20, 0.20)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    with pymupdf.open(str(resultado["folhas"][0]["arquivo"])) as doc:
        largura = doc.load_page(0).rect.width / PT_M

    assert largura == pytest.approx(montagem.ROTULO_LARGURA_M, abs=0.001), \
        "a folha tem que caber o rotulo inteiro, nao so a peca"


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
    assert "mm fora" in motivo and "Confira a arte ou o nome" in motivo


def test_duas_pecas_de_mesma_medida_nao_trocam_de_rotulo(pasta):
    """
    A LATERAL_ESQUERDA e a LATERAL_DIREITA tem 0,90 x 2,40 as duas. Se o
    encaixe perdesse a identidade, o rotulo de uma iria pra outra -- e
    quem corta penduraria a arte errada na parede errada.
    """
    arte(pasta, "1UN LONA IMPRESSA 0.90X2.40M_LATERAL_ESQUERDA.pdf", 0.90, 2.40)
    arte(pasta, "1UN LONA IMPRESSA 0.90X2.40M_LATERAL_DIREITA.pdf", 0.90, 2.40)

    montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    saida = montagem.pasta_de_saida("DOCAN R5200", pasta.parent)
    ficha = json.loads(next(saida.glob("*.json")).read_text(encoding="utf-8"))
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

    for _, x, y, largura, altura, _girada, reservada_l, reservada_a in postas:
        # a arte encosta embaixo do retangulo reservado, entao a faixa do
        # nome e o que sobra em cima -- e sobra igual com a peca girada
        alto_da_arte = y + (reservada_a - altura)
        faixa = (x, alto_da_arte - montagem.RECUO_CORTE_M,
                 x + montagem.ROTULO_LARGURA_M, alto_da_arte)
        for _, ox, oy, olargura, oaltura, _g, _rl, ora in postas:
            oy = oy + (ora - oaltura)
            if (ox, oy) == (x, y):
                continue
            separados = (ox >= faixa[2] - 0.001 or ox + olargura <= faixa[0] + 0.001
                         or oy >= faixa[3] - 0.001 or oy + oaltura <= faixa[1] + 0.001)
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
    assert ficha["folha_m"][0] == 2.05, \
        "duas pecas de 1,00 lado a lado: a folha fecha em 2,05, nao nos 5,00 da bobina"
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
    docan = raiz / "DOCAN R5200"
    swj = raiz / "SWJ320A"
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


# ---------- o que esta desenhado na folha ----------
#
# O insert_textbox do PyMuPDF NAO avisa quando desiste: devolve negativo e
# nao desenha nada. Em 04/10/2026 o numero da peca sumiu assim DUAS vezes,
# e as duas so apareceram ampliando a previa. Estes testes leem o texto do
# PDF pronto -- e a unica conferencia que pega isso.


def _texto_da_folha(caminho):
    with pymupdf.open(str(caminho)) as doc:
        return doc.load_page(0).get_text()


def test_toda_peca_sai_com_NUMERO_e_NOME_na_folha(pasta):
    """
    O material vai ser refilado: depois do corte, o que identifica cada
    pedaco e o numero e o nome que sairam ao lado dele.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL_FUNDO.pdf", 2.00, 1.00)
    arte(pasta, "3UN LONA IMPRESSA 1.60X0.30M_VIBRA_RODAPE.pdf", 1.60, 0.30)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    texto = _texto_da_folha(resultado["folhas"][0]["arquivo"])

    for numero in ("01", "02", "03", "04"):
        assert numero in texto, f"o numero {numero} nao foi desenhado"
    assert "VIBRA_PAINEL_FUNDO" in texto
    assert "VIBRA_RODAPE" in texto


def test_o_rotulo_ENCOLHE_antes_de_cortar(pasta):
    """
    O nome tem que sair EXATO, igual ao do arquivo (regra dele,
    04/10/2026). Entao encolher vem antes de cortar: cortar e ultimo
    recurso, e so quando nem a menor letra couber.
    """
    import pymupdf as mupdf

    doc = mupdf.open()
    pagina = doc.new_page(width=4000, height=1000)
    nome = "07  1UN LONA IMPRESSA_1.97x3.20m_LONA_10_1,67x2,70m_loja_de_incoveniencia_vibra"

    milimetros, escrito = montagem._escrever_rotulo(pagina, 0, 900, 2.00, nome, mupdf)

    assert escrito == nome, "cabendo, o nome sai inteiro -- nada de truncar por preguica"
    assert 0 < milimetros <= 20

    # numa peca estreita demais ele corta, mas o NUMERO nunca e o cortado
    _mm, curto = montagem._escrever_rotulo(pagina, 0, 500, 0.08, nome, mupdf)
    assert curto.startswith("07") and curto.endswith("~")

    with pytest.raises(AssertionError):
        montagem._escrever_rotulo(pagina, 0, 100, 0.002, nome, mupdf)
    doc.close()


def test_o_rotulo_e_o_NOME_DO_ARQUIVO_exato(pasta):
    """
    Antes eu escrevia so o fim do nome, e isso mostrava a SEGUNDA medida
    ao lado de uma peca feita na PRIMEIRA: o rotulo dizia "1,50x0,25m"
    numa peca de 1,80 x 0,55 e parecia que o tamanho estava errado quando
    nao estava (ele viu na folha de 04/10/2026).
    """
    nome = "1UN LONA IMPRESSA_1.80x0.55m_LONA_19.2_1,50x0,25m_vibra.pdf"
    arte(pasta, nome, 1.80, 0.55)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    with pymupdf.open(str(resultado["folhas"][0]["arquivo"])) as doc:
        texto = doc.load_page(0).get_text()
    assert nome[:-4] in texto, "o rotulo tem que ser o nome do arquivo, inteiro"


def test_sem_marcas_de_corte(pasta):
    """
    Ele tirou em 04/10/2026, olhando a folha com elas: a folga de 5 cm
    entre as pecas ja diz onde a lamina passa, e as cruzinhas so sujavam
    a sobra.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    with pymupdf.open(str(resultado["folhas"][0]["arquivo"])) as doc:
        pagina = doc.load_page(0)
        tracos = [d for d in pagina.get_drawings()
                  if d["rect"].width < 5 or d["rect"].height < 5]
    assert not tracos, "sobrou traco de marca de corte na folha"


def test_a_folha_respeita_a_margem_de_2cm(pasta):
    """Borda de 2 cm: nada de arte nem de texto encostando no fio do rolo."""
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))

    with pymupdf.open(str(folha)) as doc:
        pagina = doc.load_page(0)
        limite = montagem.margem("DOCAN R5200") * PT_M
        for peca in ficha["pecas"]:
            assert peca["posicao_m"][0] >= montagem.margem("DOCAN R5200") - 0.001
        for bloco in pagina.get_text("blocks"):
            if not bloco[4].strip():
                continue
            assert bloco[0] >= limite - 0.5, "texto passou da margem esquerda"
            assert bloco[2] <= pagina.rect.width - limite + 0.5, "texto passou da margem direita"


def test_o_nome_fica_ACIMA_da_arte_nunca_em_cima_dela(pasta):
    """
    Canto superior esquerdo, como o RasterLink faz. E fora da peca: o
    rotulo mora na folga de 5 cm, que e por onde a lamina passa.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 2.00, 1.00)
    arte(pasta, "1UN LONA IMPRESSA 1.00X2.00M_VIBRA_LATERAL.pdf", 1.00, 2.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))

    with pymupdf.open(str(folha)) as doc:
        pagina = doc.load_page(0)
        artes = []
        for peca in ficha["pecas"]:
            x, y = peca["posicao_m"]
            largura, altura = peca["medida_m"]
            if peca["girada"]:
                largura, altura = altura, largura
            artes.append(pymupdf.Rect(x * PT_M, y * PT_M,
                                      (x + largura) * PT_M, (y + altura) * PT_M))
        for bloco in pagina.get_text("blocks"):
            if not bloco[4].strip() or "MONTAGEM" in bloco[4]:
                continue
            caixa = pymupdf.Rect(bloco[:4])
            for arte_rect in artes:
                assert (caixa & arte_rect).get_area() <= 1, \
                    f"o rotulo {bloco[4][:30]!r} caiu dentro de uma arte"


def test_a_posicao_do_json_e_onde_a_arte_esta_DE_VERDADE(pasta):
    """
    O JSON e a planta de quem vai procurar a peca 07 numa lona de 9 m. A
    posicao do ENCAIXE nao serve: a arte encosta embaixo da reserva e a
    folha ainda tem cabecalho e margem na frente.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    ficha = json.loads(resultado["folhas"][0]["arquivo"].with_suffix(".json").read_text(
        encoding="utf-8"))

    x, y = ficha["pecas"][0]["posicao_m"]
    assert x == pytest.approx(montagem.margem("DOCAN R5200"), abs=0.001)
    assert y >= montagem.CABECALHO_M + montagem.margem("DOCAN R5200") - 0.001, \
        "a arte nao pode comecar antes do cabecalho"


# ---------- a arte nao pode ser mexida ----------


def test_a_LARGURA_e_a_ancora_e_fecha_sempre_redonda(pasta):
    """
    Regra dele de 05/10/2026: *"sabemos que algumas artes vai dar
    diferenca, entao sempre que redimensionar crie um padrao que deve ser
    pela largura, ou seja, a largura vai bater sempre que redimensionar
    na proporcao"*.

    Entao a peca sai com a largura do NOME, redonda, e o comprimento e o
    que a proporcao da arte der. A escala continua UNIFORME -- "as artes
    nao podem ser mexidas em absolutamente nada" (04/10/2026).
    """
    # o nome pede 2,00 x 1,00; o arquivo tem proporcao 1,99
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 1.990, 1.00)

    pecas, recusadas = montagem.pecas_da_pasta(pasta)
    assert not recusadas
    peca = pecas[0]

    assert peca["largura_m"] == pytest.approx(2.00, abs=1e-9), \
        "a largura e a ancora: ela fecha redonda, sempre"
    assert peca["altura_m"] == pytest.approx(2.00 / 1.99, rel=1e-6), \
        "o comprimento e o que a proporcao da arte der"
    assert peca["largura_m"] / peca["altura_m"] == pytest.approx(1.990 / 1.00, rel=1e-6), \
        "um fator so pros dois lados: arte esticada e arte mexida"


def test_quem_decide_e_quanto_sai_fora_em_MILIMETROS_nao_a_porcentagem():
    """
    A regua e em MILIMETROS, e quem a mudou foi arte REAL dele
    (04/10/2026): oito lonas da LOJINHA tinham TODAS as medidas
    exatamente +0,7 mm acima do nome -- offset constante da exportacao,
    nao erro de proporcao. Em porcentagem a peca mais estreita dava 1,5%
    e era recusada. A regua errada recusava arte boa.
    """
    # a peca de 0,40 x 3,00 com o arquivo em 1:10 mais 0,7 mm: a largura
    # fecha em 0,40 e o comprimento cai 45 mm -- ENTRA
    ajuste = montagem.ajuste_para((0.40, 3.00), (0.0407, 0.3007, 1))
    assert ajuste["acao"] == "escalar"
    assert "-45 mm" in ajuste["motivo"], "o motivo tem que dizer QUANTO o comprimento andou"

    # a MESMA proporcao numa peca dez vezes maior tira quase meio metro
    assert montagem.ajuste_para((4.00, 30.00), (0.407, 3.007, 1))["acao"] == "recusar"

    # mesma proporcao, 1% maior nos dois lados: escala uniforme resolve
    # e o comprimento nem se mexe
    ajuste = montagem.ajuste_para((2.00, 1.00), (2.02, 1.01, 1))
    assert ajuste["acao"] == "escalar"
    assert "comprimento" not in ajuste["motivo"], \
        "sem diferenca nenhuma, nao ha o que avisar"


def test_peca_maior_que_a_bobina_nao_some_calada(pasta):
    """
    O encaixe simplesmente IGNORA o que nao cabe. Sem este aviso a peca
    nao seria produzida e ninguem ficaria sabendo -- o pior resultado
    possivel num sistema de producao.
    """
    arte(pasta, "1UN LONA IMPRESSA 6.00X6.00M_VIBRA_GIGANTE.pdf", 6.00, 6.00)
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_NORMAL.pdf", 2.00, 1.00)
    avisos = []

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x",
                                      logger=lambda n, m: avisos.append(m))

    assert len(resultado["folhas"]) == 1, "a peca normal tinha que montar"
    recusada = [r for r in resultado["recusadas"] if "GIGANTE" in r["arquivo"]]
    assert recusada and "nao cabe" in recusada[0]["motivo"].replace("ã", "a")
    assert any("GIGANTE" in a for a in avisos)


def test_arte_nunca_sai_da_folha(pasta):
    """
    O defeito de 04/10/2026: o teto da largura reservada podia ficar
    ABAIXO da propria peca, e o encaixe "cabia" com uma lona de 7,14 m
    deitada numa bobina de 5,00 -- a arte saia 2,18 m pra fora, calada.
    """
    arte(pasta, "1UN LONA IMPRESSA 7.14X1.10M_VIBRA_LONA_A.pdf", 0.714, 0.110)
    arte(pasta, "1UN LONA IMPRESSA 5.00X0.50M_VIBRA_TESTEIRA.pdf", 5.00, 0.50)
    arte(pasta, "1UN LONA IMPRESSA 3.15X3.77M_VIBRA_PAREDE.pdf", 3.15, 3.77)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]

    with pymupdf.open(str(folha)) as doc:
        pagina = doc.load_page(0)
        for desenho in pagina.get_drawings():
            caixa = desenho["rect"]
            assert caixa.x1 <= pagina.rect.width + 0.5, "desenho passou da largura da folha"
            assert caixa.y1 <= pagina.rect.height + 0.5, "desenho passou do fim da folha"
            assert caixa.x0 >= -0.5 and caixa.y0 >= -0.5


def test_a_meia_folga_continua_mandando_onde_o_rotulo_fica(pasta):
    """
    As marcas de corte sairam, mas a meia-folga continua sendo a regua: o
    rotulo tem que caber nos 2,5 cm que ficam com ESTA peca. Passando
    disso, metade do nome sairia junto com a peca de cima no refile.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))
    _x, y = ficha["pecas"][0]["posicao_m"]

    with pymupdf.open(str(folha)) as doc:
        pagina = doc.load_page(0)
        blocos = [pymupdf.Rect(b[:4]) for b in pagina.get_text("blocks")
                  if b[4].strip() and "MONTAGEM" not in b[4]]
    assert blocos, "cade o rotulo"
    for bloco in blocos:
        assert bloco.y1 <= y * PT_M + 1, "o rotulo invadiu a arte"
        assert bloco.y0 >= (y - montagem.RECUO_CORTE_M) * PT_M - 1,             "o rotulo passou da meia-folga e sairia com a peca de cima"


def test_a_peca_guarda_as_DUAS_medidas_quando_elas_diferem(pasta):
    """
    Numero deduzido nunca se passa por declarado: quando o comprimento
    sai diferente do que o nome diz, a peca carrega os dois valores e o
    JSON ao lado escreve os dois.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 1.992, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    ficha = json.loads(resultado["folhas"][0]["arquivo"].with_suffix(".json").read_text(
        encoding="utf-8"))
    peca = ficha["pecas"][0]

    assert peca["medida_m"][0] == 2.00, "a largura e a do nome"
    assert peca["medida_m"][1] == pytest.approx(2.00 / 1.992, abs=0.0006)
    assert peca["medida_do_nome_m"] == [2.00, 1.00], \
        "o que o nome pedia tem que continuar escrito, senao a prova esconde a diferenca"


def test_nada_e_aparado_a_largura_fecha_e_a_arte_entra_inteira():
    """
    A ancora na largura (05/10/2026) acabou com o recorte: antes a arte
    era cortada no centro pra fechar as duas medidas, e isso comia
    beirada. Agora o fator sai da largura e NADA e descartado.
    """
    for alvo, arquivo in (((1.00, 1.00), (0.98, 1.00)),
                          ((3.77, 3.15), (3.70, 3.15)),
                          ((0.40, 3.00), (0.0407, 0.3007)),
                          ((7.14, 1.10), (0.714, 0.1105))):
        ajuste = montagem.ajuste_para(alvo, (arquivo[0], arquivo[1], 1))
        if ajuste["acao"] not in ("escalar", "girar", "igual"):
            continue
        w, h = arquivo
        if ajuste["girar"]:
            w, h = h, w
        assert w * ajuste["fator"] == pytest.approx(alvo[0], abs=0.0006), \
            f"{alvo}: a largura TEM que fechar redonda, e a ancora"


def test_o_resto_do_sistema_tambem_nao_estica():
    """
    Varredura de 04/10/2026: todo lugar que poe arte numa caixa usa fator
    UNICO. Este teste guarda os dois que calculam a escala na mao -- os
    outros usam keep_proportion do PyMuPDF, que e o padrao.
    """
    import miniaturas

    # miniaturas.encaixar: a OS, o checklist e o relatorio passam por aqui
    largura, altura = miniaturas.encaixar(None, 100, 50)
    assert (largura, altura) == (100, 50), "sem dados nao da pra manter proporcao nenhuma"

    import processamento

    fonte = pathlib.Path(processamento.__file__).read_text(encoding="utf-8")
    assert "escala_fit = min(" in fonte, \
        "a etiqueta calcula a escala na mao: tem que ser min() dos dois lados, nunca um por eixo"


def test_medindo_no_PDF_a_arte_saiu_na_proporcao_do_arquivo(pasta):
    """
    A conferencia que vale e geometrica: medir o que FOI DESENHADO e
    comparar com o arquivo de origem. Uma peca so na folha, pra achar o
    desenho sem ambiguidade.

    A arte entra em 1:10 (0,714 x 0,110) e o nome pede 7,14 x 1,10 --
    proporcao 6,4909 nos dois. Se alguem trocar a conta por um fator
    por eixo, este numero muda.
    """
    arte(pasta, "1UN LONA IMPRESSA 7.14X1.10M_VIBRA_LONA_A.pdf", 0.714, 0.110)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))

    x, y = ficha["pecas"][0]["posicao_m"]
    with pymupdf.open(str(folha)) as doc:
        pagina = doc.load_page(0)
        # get_xobjects devolve a DEFINICAO da pagina de origem junto com a
        # colocacao dela; a que interessa e a que esta na posicao da peca
        caixas = [pymupdf.Rect(item[3]) for item in pagina.get_xobjects()]
        desenhadas = [c for c in caixas
                      if abs(c.x0 / PT_M - x) < 0.06 and abs(c.y0 / PT_M - y) < 0.06]
        assert len(desenhadas) == 1, f"nao achei a arte em x={x:.2f} y={y:.2f}"
        caixa = desenhadas[0]

    proporcao = caixa.width / caixa.height
    if ficha["pecas"][0]["girada"]:
        proporcao = 1 / proporcao
    assert proporcao == pytest.approx(0.714 / 0.110, rel=1e-4), \
        "a arte saiu com proporcao diferente da do arquivo: foi esticada"


# ---------- a maquina PLANA monta em chapas, nao em rolo ----------
#
# Na H2525 os DOIS lados sao teto: nao existe "a bobina anda". O que a
# montagem economiza e NUMERO DE CHAPAS, e chapa e material que sai
# inteiro do estoque.


@pytest.fixture
def mesa(tmp_path):
    p = tmp_path / "DOCAN H2525"
    p.mkdir()
    return p


def test_a_plana_sai_em_paginas_do_tamanho_da_chapa(mesa):
    for i in range(2):
        arte(mesa, f"1UN PS 1.20X1.00M_VIBRA_PLACA_{i}.pdf", 1.20, 1.00)
    arte(mesa, "1UN PS 2.40X2.40M_VIBRA_PAINEL.pdf", 2.40, 2.40)

    resultado = montagem.montar_pasta(mesa, raiz_clientes=mesa.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]

    with pymupdf.open(str(folha)) as doc:
        assert doc.page_count == 2, "o painel de 2,40 nao divide chapa com as placas"
        for n in range(doc.page_count):
            pagina = doc.load_page(n)
            assert round(pagina.rect.width / PT_M, 2) == 2.50
            assert round(pagina.rect.height / PT_M, 2) == 2.50, \
                "a pagina E a chapa: faixa de cabecalho em cima roubaria area dela"


def test_a_plana_conta_chapas_no_nome_e_no_json(mesa):
    arte(mesa, "1UN PS 2.40X2.40M_VIBRA_PAINEL.pdf", 2.40, 2.40)
    arte(mesa, "1UN PS 2.40X2.40M_VIBRA_PAINEL_2.pdf", 2.40, 2.40)

    resultado = montagem.montar_pasta(mesa, raiz_clientes=mesa.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))

    assert "2chapas" in folha.name
    assert ficha["chapas"] == 2
    assert ficha["folha_m"] == [2.5, 2.5]


def test_na_plana_a_peca_maior_que_a_chapa_e_recusada(mesa):
    """2,60 nao cabe nos 2,50 nem girada -- e nao pode sumir calada."""
    arte(mesa, "1UN PS 2.60X1.00M_VIBRA_GRANDE.pdf", 2.60, 1.00)
    arte(mesa, "1UN PS 1.00X1.00M_VIBRA_NORMAL.pdf", 1.00, 1.00)

    resultado = montagem.montar_pasta(mesa, raiz_clientes=mesa.parent / "x")

    assert len(resultado["folhas"]) == 1
    recusada = [r for r in resultado["recusadas"] if "GRANDE" in r["arquivo"]]
    assert recusada and "mesa" in recusada[0]["motivo"]


def test_na_plana_a_arte_tambem_nao_sai_da_chapa(mesa):
    for i in range(4):
        arte(mesa, f"1UN PS 1.20X1.10M_VIBRA_PLACA_{i}.pdf", 1.20, 1.10)

    resultado = montagem.montar_pasta(mesa, raiz_clientes=mesa.parent / "x")

    with pymupdf.open(str(resultado["folhas"][0]["arquivo"])) as doc:
        for n in range(doc.page_count):
            pagina = doc.load_page(n)
            for desenho in pagina.get_drawings():
                caixa = desenho["rect"]
                assert caixa.x0 >= -0.5 and caixa.y0 >= -0.5
                assert caixa.x1 <= pagina.rect.width + 0.5
                assert caixa.y1 <= pagina.rect.height + 0.5


def test_a_margem_da_maquina_vale_no_encaixe(pasta):
    """
    A SWJ pede 5 cm de borda e a DOCAN 2 cm: a mesma peca sobra espaco
    diferente em cada uma. O numero vem do cadastro, nao da montagem.
    """
    pecas = [{"largura_m": 1.00, "altura_m": 1.00, "nome": "x",
              "ajuste": {"girar": False, "acao": "igual"}}]

    postas_docan, _ = montagem.encaixar(pecas, 5.20, montagem.margem("DOCAN R5200"))
    postas_swj, _ = montagem.encaixar(pecas, 3.24, montagem.margem("SWJ320A"))

    assert postas_docan[0][1] == 0.0 and postas_swj[0][1] == 0.0, "o encaixe comeca na origem"
    # a margem entra na hora de desenhar
    assert montagem.posicao_na_folha(postas_docan[0], 0.02)[0] == 0.02
    assert montagem.posicao_na_folha(postas_swj[0], 0.05)[0] == 0.05


def test_a_letra_do_rotulo_nao_cresce_com_a_peca(pasta):
    """
    "Nao quero os nomes grandes" (04/10/2026). Antes o rotulo usava o
    MAIOR tamanho que coubesse, e numa peca larga isso dava 20 mm -- letra
    de 2 cm de altura. Agora o tamanho e o pedido, e so encolhe.
    """
    arte(pasta, "1UN LONA IMPRESSA 4.00X2.00M_VIBRA_PAINEL_GRANDE.pdf", 4.00, 2.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    with pymupdf.open(str(resultado["folhas"][0]["arquivo"])) as doc:
        tamanhos = [span["size"] / PT_M * 1000
                    for bloco in doc.load_page(0).get_text("dict")["blocks"]
                    for linha in bloco.get("lines", [])
                    for span in linha["spans"]
                    if "PAINEL_GRANDE" in span["text"]]
    assert tamanhos, "cade o rotulo"
    assert max(tamanhos) <= montagem.ROTULO_LETRA_MM + 0.1, \
        f"a letra saiu com {max(tamanhos):.1f} mm numa peca larga"


def test_a_largura_da_docan_fecha_5_metros_redondos_de_arte():
    """
    "A maquina DOCAN pode mudar para 504cm de largura; com isso,
    descontando os 2 cm de cada lado de folga, os arquivos finais ficam
    com 500cm de largura" (04/10/2026).
    """
    largura = montagem.largura_util("DOCAN R5200")
    margem = montagem.margem("DOCAN R5200")

    assert round(largura - 2 * margem, 2) == 5.00


# ---------- a peca sai do tamanho EXATO que o nome pede ----------
#
# Ele, 04/10/2026, olhando a primeira folha: *"As medidas tbm nao esta
# precisa conforme a arte"*. Estava certo -- a arte COBRIA a caixa e
# passava dela, com erro de -13 a +14,5 mm. Hoje a arte entra em
# cover+CLIP: enche a caixa sem esticar e o excedente e RECORTADO.


def test_a_peca_ocupa_no_PDF_a_largura_do_nome_ate_o_decimo_de_milimetro(pasta):
    """
    A conferencia que vale e a GEOMETRICA, nunca a varredura de cor: arte
    com faixa branca na propria borda faz o scanner de pixel acusar erro
    que nao existe (foi o que me custou uma rodada em 05/10/2026, lendo
    +9,7 mm que eram o texto preto do rotulo).

    Aqui a arte vem 2% fora de proporcao -- dentro da tolerancia, entao
    ela entra -- e o que tem que fechar redondo no PDF e a LARGURA.
    """
    arte(pasta, "1UN LONA IMPRESSA 1.00X0.50M_VIBRA_PECA.pdf", 1.02, 0.50)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))
    peca = ficha["pecas"][0]

    largura, altura = peca["medida_m"]
    if peca["girada"]:
        largura, altura = altura, largura

    with pymupdf.open(str(folha)) as doc:
        pagina = doc.load_page(0)
        alto = pagina.rect.height
        # get_xobjects devolve a DEFINICAO junto com a colocacao: a que
        # vale e a que esta na posicao da peca. E a caixa vem em
        # coordenada de PDF, de baixo pra cima.
        postas = [pymupdf.Rect(item[3]) for item in pagina.get_xobjects()
                  if item[2] == 0]
        assert len(postas) == 1
        caixa = postas[0]

    assert caixa.width / PT_M == pytest.approx(largura, abs=0.0001), \
        "a peca nao saiu com a largura que o nome pede"
    assert caixa.height / PT_M == pytest.approx(altura, abs=0.0006), \
        "o desenho tem que bater com o comprimento que o JSON declara"
    assert altura == pytest.approx(1.00 * 0.50 / 1.02, abs=0.0006), \
        "o comprimento e o da proporcao da arte, nao o do nome"
    assert (alto - caixa.y1) / PT_M == pytest.approx(peca["posicao_m"][1], abs=0.0006)
    assert caixa.x0 / PT_M == pytest.approx(peca["posicao_m"][0], abs=0.0006)


def test_o_rotulo_mede_300mm_e_nunca_estoura_a_meia_folga():
    """
    Pedido dele de 04/10/2026: *"os nomes precisa ficar todos com 300mm
    de largura"*. A letra nao e escolhida, e CALCULADA pra isso -- entao
    o que se confere e a LARGURA DO TEXTO, nao o corpo da letra.

    E 300 mm e TETO tambem: passar disso quebra a linha no insert_textbox
    e o nome sai cortado. Por isso o tamanho arredonda pra baixo.
    """
    doc = pymupdf.open()
    pagina = doc.new_page(width=5.04 * PT_M, height=1.0 * PT_M)

    nomes = [
        "01  1UN LONA IMPRESSA_0.40x3.00m_LONA_16_0,10x2,70m_loja_de_incoveniencia_vibra_sangria15cm",
        "02  1UN LONA IMPRESSA 2.12X3.20M_VIBRA_LATERAL_ESQUERDA",
    ]
    for i, nome in enumerate(nomes):
        corpo, escrito = montagem._escrever_rotulo(
            pagina, 0.02 * PT_M, (0.3 + i * 0.2) * PT_M, 0.45, nome, pymupdf,
            montagem.RECUO_CORTE_M - 0.001)
        assert escrito == nome, "nome comprido nao pode sair cortado: encolhe a letra"
        largura = pymupdf.get_text_length(escrito, fontname="hebo",
                                          fontsize=corpo / 1000 * PT_M) / PT_M
        assert largura <= montagem.ROTULO_LARGURA_M + 0.0005, \
            f"o rotulo passou de 300 mm ({largura * 1000:.1f} mm): a linha quebra"
        assert largura >= montagem.ROTULO_LARGURA_M - 0.005, \
            f"o rotulo saiu com {largura * 1000:.1f} mm em vez de 300"
        assert corpo / 1000 * 1.8 <= montagem.RECUO_CORTE_M, \
            "letra mais alta que a meia-folga sai junto com a peca de cima no refile"
    doc.close()


def test_nome_curto_para_na_meia_folga_em_vez_de_virar_letra_gigante():
    """
    O limite honesto dos 300 mm: num nome CURTO, a letra que mediria
    300 mm teria 7 cm de altura e invadiria a peca de cima. Entao o teto
    ganha e o rotulo sai mais estreito -- com letra MAIOR, que e o que
    ele pediu de verdade ("a informacao visivel na hora da impressao").
    """
    doc = pymupdf.open()
    pagina = doc.new_page(width=5.04 * PT_M, height=1.0 * PT_M)

    corpo, escrito = montagem._escrever_rotulo(
        pagina, 0.02 * PT_M, 0.5 * PT_M, 0.45, "07  PECA", pymupdf,
        montagem.RECUO_CORTE_M - 0.001)

    assert escrito == "07  PECA"
    assert corpo / 1000 * 1.8 <= montagem.RECUO_CORTE_M
    largura = pymupdf.get_text_length(escrito, fontname="hebo",
                                      fontsize=corpo / 1000 * PT_M) / PT_M
    assert largura < montagem.ROTULO_LARGURA_M, \
        "nome curto a 300 mm daria letra de 7 cm, mais alta que a folga inteira"
    doc.close()


def test_o_nome_da_folha_diz_o_QUE_A_PAGINA_MEDE(pasta):
    """
    O nome do arquivo e o banco de dados do sistema: m2, escolha de
    maquina e baixa de estoque saem dele. Enquanto o comprimento era
    calculado em dois lugares, o nome dizia 6,45 m numa folha de 6,52 --
    7 cm de lona por folha saindo do rolo sem aparecer em lugar nenhum.
    """
    for i in range(3):
        arte(pasta, f"1UN LONA IMPRESSA 2.40X1.60M_VIBRA_PECA_{i}.pdf", 2.40, 1.60)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))

    with pymupdf.open(str(folha)) as doc:
        pagina_m = (doc.load_page(0).rect.width / PT_M,
                    doc.load_page(0).rect.height / PT_M)

    import dimensoes

    medida = dimensoes.extrair_dimensoes(folha.name)
    assert medida is not None, "o nome da folha tem que trazer medida: e por ela que tudo conta"
    assert medida["largura_m"] == pytest.approx(pagina_m[0], abs=0.006)
    assert medida["altura_m"] == pytest.approx(pagina_m[1], abs=0.006), \
        "o nome declara menos material do que a folha gasta"
    assert ficha["folha_m"][1] == pytest.approx(pagina_m[1], abs=0.0006)


def test_a_folha_PRONTA_nao_e_montada_de_novo(pasta):
    """
    Aconteceu na pasta de verdade em 05/10/2026, as 01:45: a folha pronta
    fica na propria pasta da maquina e a passada seguinte a leu como peca
    -- nome com medida e material, como todas as outras. Montou a folha
    de 8 pecas DENTRO de outra, de uma peca so, com 6,68 m e sem o
    cliente no nome. Sozinho isso repetiria pra sempre.
    """
    for i in range(2):
        arte(pasta, f"1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PECA_{i}.pdf", 2.00, 1.00)

    primeira = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = primeira["folhas"][0]["arquivo"]
    assert folha.is_file()
    assert folha.parent == montagem.pasta_de_saida("DOCAN R5200", pasta.parent), \
        "a folha pronta sai da pasta de ENTRADA (pedido dele, 05/10/2026)"

    # a saida em outra pasta ja resolve; o cinto de seguranca e pra quando
    # alguem arrastar a folha pronta de volta pra entrada
    import shutil

    de_volta = pasta / folha.name
    shutil.copy2(folha, de_volta)
    shutil.copy2(folha.with_suffix(".json"), de_volta.with_suffix(".json"))

    pecas, recusadas = montagem.pecas_da_pasta(pasta)
    assert pecas == [] and recusadas == [], \
        "a folha pronta virou peca: a montagem esta se comendo"

    segunda = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    assert segunda["folhas"] == []
    assert de_volta.is_file(), "a folha pronta nao pode ir pros _originais"

    # e sem a ficha ao lado tambem nao: o nome de saida e prova sozinho
    de_volta.with_suffix(".json").unlink()
    assert montagem.pecas_da_pasta(pasta)[0] == []


# ---------- a medida e a da TINTA, nao a da pagina ----------
#
# Ele, 05/10/2026: *"a arte deve bater o tamanho exato na largura que
# pede no nome, a diferenca deve ficar somente na altura... conferi na
# arte, sempre falta medida na largura"*. Estava certo, e eram DUAS
# coisas na pagina das lonas da LOJINHA: 1 pt de branco em volta
# (0,35 mm; 7,1 mm depois do x10 da escala) e um recorte do Illustrator
# 0,6 pt fora de esquadro, que apara mais 2,2 mm de um lado so.


def arte_com_franja(pasta, nome, largura_pt, altura_pt, franja_pt=1.0,
                    recorte=None):
    """
    Arte como o Illustrator exporta: a pagina MAIOR que o desenho, e
    opcionalmente um recorte (`re W n`) deslocado, que e o que de fato
    limita a tinta.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    pagina = doc.new_page(width=largura_pt + 2 * franja_pt,
                          height=altura_pt + 2 * franja_pt)
    pagina.draw_rect(
        pymupdf.Rect(franja_pt, franja_pt, franja_pt + largura_pt,
                     franja_pt + altura_pt),
        color=None, fill=(0.3, 0.6, 0.3))
    if recorte is not None:
        xref = pagina.get_contents()[0]
        corpo = doc.xref_stream(xref)
        x0, y0, x1, y1 = recorte
        antes = f"q {x0} {y0} {x1 - x0} {y1 - y0} re W n\n".encode()
        doc.update_stream(xref, antes + corpo + b"\nQ\n")
    caminho = pasta / nome
    doc.save(str(caminho))
    doc.close()
    return caminho


def test_a_franja_branca_da_exportacao_nao_conta_na_medida(pasta):
    """
    A pagina tem 1 pt de branco de cada lado; a arte, nao. Medindo a
    pagina, a peca entrava encolhida por isso e faltava medida na largura
    -- que foi exatamente o que ele mediu na folha impressa.
    """
    caminho = arte_com_franja(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PECA.pdf",
                              2.00 * PT_M, 1.00 * PT_M, franja_pt=1.0)

    with pymupdf.open(str(caminho)) as doc:
        pagina = doc.load_page(0)
        assert pagina.rect.width / PT_M > 2.0007, "a pagina TEM que ser maior que a arte aqui"
        arte_m = montagem.caixa_da_arte(pagina, pymupdf)

    assert arte_m.width / PT_M == pytest.approx(2.00, abs=1e-6)
    assert arte_m.height / PT_M == pytest.approx(1.00, abs=1e-6)
    assert montagem.medida_do_arquivo(caminho)[0] == pytest.approx(2.00, abs=1e-6)


def test_o_recorte_do_Illustrator_e_quem_limita_a_tinta(pasta):
    """
    O defeito mais fino dos dois: o `re W n` que o Illustrator escreve
    nao coincide com o desenho -- nas lonas dele estava 0,6 pt fora, e
    aparava 2,2 mm do lado direito depois do x10. Quem mede o TRACADO
    acha a medida do nome e manda imprimir uma tira branca pro refile.
    """
    caminho = arte_com_franja(
        pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PECA.pdf",
        2.00 * PT_M, 1.00 * PT_M, franja_pt=1.0,
        # o recorte comeca meio ponto antes e termina meio ponto antes:
        # apara 0,5 pt da direita
        recorte=(0.5, 1.0, 0.5 + 2.00 * PT_M, 1.0 + 1.00 * PT_M))

    with pymupdf.open(str(caminho)) as doc:
        arte_m = montagem.caixa_da_arte(doc.load_page(0), pymupdf)

    esperado = (2.00 * PT_M - 0.5) / PT_M
    assert arte_m.width / PT_M == pytest.approx(esperado, abs=1e-6), \
        "a medida tem que ser a da TINTA: o tracado fica por baixo do recorte"


def test_a_LARGURA_da_tinta_fecha_redonda_na_folha(pasta):
    """
    O teste que prova o pedido inteiro: arte com franja E recorte entra,
    e no PDF pronto a peca mede a largura do nome CRAVADA. A diferenca,
    se houver, fica no comprimento.
    """
    arte_com_franja(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PECA.pdf",
                    2.00 * PT_M, 1.00 * PT_M, franja_pt=1.0,
                    recorte=(0.5, 1.0, 0.5 + 2.00 * PT_M, 1.0 + 1.00 * PT_M))

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))
    peca = ficha["pecas"][0]

    largura, altura = peca["medida_m"]
    if peca["girada"]:
        largura, altura = altura, largura

    with pymupdf.open(str(folha)) as doc:
        pagina = doc.load_page(0)
        postas = [pymupdf.Rect(i[3]) for i in pagina.get_xobjects() if i[2] == 0]
        assert len(postas) == 1
        caixa = postas[0]

    assert caixa.width / PT_M == pytest.approx(largura, abs=0.0006)
    assert peca["medida_m"][0] == 2.00, "a largura do nome tem que fechar redonda"


def test_franja_grande_e_DESIGN_e_nao_e_aparada(pasta):
    """
    O limite da regra, e e o que impede um desastre: arte que e um
    desenho pequeno no meio de uma folha branca tem caixa de tinta
    pequena, e estica-la ate a medida do nome entregaria a peca errada.
    Acima de FRANJA_MAXIMA_FRACAO manda a PAGINA, como antes.
    """
    caminho = arte_com_franja(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_LOGO.pdf",
                              1.00 * PT_M, 0.50 * PT_M,
                              franja_pt=0.50 * PT_M)   # metade e branco

    with pymupdf.open(str(caminho)) as doc:
        pagina = doc.load_page(0)
        arte_m = montagem.caixa_da_arte(pagina, pymupdf)
        assert arte_m == pagina.rect, \
            "franja de meio metro nao e sobra de exportacao, e design"


# ---------- a previa: os dados na tela ANTES de gerar ----------
#
# Ele, 05/10/2026: *"antes de gerar quero que me passe os dados como um
# aviso de como vai ficar depois de montado, mostrando a margem de
# erro"*, e logo depois *"ele vai pegar os arquivos que joguei na pasta,
# calcular e passar os dados na tela"*.


def test_a_previa_nao_escreve_nem_move_NADA(pasta):
    """
    E o que a separa de montar: ela e so olhar. Se ela movesse os
    originais, abrir a tela ja teria montado o pedido.
    """
    original = arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PECA.pdf", 2.00, 1.00)
    antes = sorted(p.name for p in pasta.iterdir())

    previa = montagem.prever_pasta(pasta, raiz_clientes=pasta.parent / "x")

    assert previa["folhas"], "tinha peca pra montar"
    assert original.exists()
    assert sorted(p.name for p in pasta.iterdir()) == antes, \
        "a previa mexeu na pasta: ela so pode OLHAR"


def test_a_previa_e_a_MESMA_conta_que_monta(pasta):
    """
    Previa calculada por fora e previa que mente no dia em que uma das
    duas mudar. Entao as duas saem do mesmo planejar_pasta, e este teste
    compara numero por numero com o PDF que sai depois.
    """
    for i in range(3):
        arte(pasta, f"1UN LONA IMPRESSA 2.40X1.60M_VIBRA_PECA_{i}.pdf", 2.40, 1.60)

    previa = montagem.prever_pasta(pasta, raiz_clientes=pasta.parent / "x")
    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    ficha = json.loads(resultado["folhas"][0]["arquivo"].with_suffix(".json").read_text(
        encoding="utf-8"))

    assert previa["folhas"][0]["pecas"] == len(ficha["pecas"])
    assert previa["folhas"][0]["folha_m"] == pytest.approx(ficha["folha_m"][1], abs=0.0006)
    assert previa["cliente"] == ficha["cliente"]
    for item, gravada in zip(previa["folhas"][0]["itens"], ficha["pecas"]):
        assert item["arquivo"] == gravada["arquivo"]
        assert item["medida_m"][0] == pytest.approx(gravada["medida_m"][0], abs=0.0006)
        assert item["medida_m"][1] == pytest.approx(gravada["medida_m"][1], abs=0.0006)
        assert item["girada"] == gravada["girada"]


def test_a_previa_diz_a_margem_de_erro_de_cada_peca(pasta):
    """
    A coluna da LARGURA e zero por construcao -- ela e a ancora -- e sai
    escrita justamente por isso: e a prova, na tela que ele le antes de
    mandar imprimir, de que a regra esta valendo. Quem muda e o
    comprimento.
    """
    # arte 2% fora de proporcao: entra, e o comprimento anda
    arte(pasta, "1UN LONA IMPRESSA 1.00X0.50M_VIBRA_PECA.pdf", 1.02, 0.50)

    previa = montagem.prever_pasta(pasta, raiz_clientes=pasta.parent / "x")
    item = previa["folhas"][0]["itens"][0]

    assert item["nome_m"] == (1.00, 0.50)
    assert item["erro_largura_mm"] == pytest.approx(0.0, abs=0.001), \
        "a largura e a ancora: a margem de erro dela e zero"
    esperado = (1.00 * 0.50 / 1.02 - 0.50) * 1000
    assert item["diferenca_comprimento_mm"] == pytest.approx(esperado, abs=0.6)
    assert previa["pior_diferenca_mm"] == pytest.approx(abs(esperado), abs=0.6)


def test_a_previa_lista_o_que_vai_ficar_de_fora_com_o_motivo(pasta):
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_DEFORMADA.pdf", 2.00, 1.80)
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_BOA.pdf", 2.00, 1.00)

    previa = montagem.prever_pasta(pasta, raiz_clientes=pasta.parent / "x")

    assert [r["arquivo"] for r in previa["recusadas"]] == \
        ["1UN LONA IMPRESSA 2.00X1.00M_VIBRA_DEFORMADA.pdf"]
    assert "Confira a arte ou o nome" in previa["recusadas"][0]["motivo"]
    assert previa["folhas"][0]["pecas"] == 1, "a boa continua entrando"


def test_o_aviso_sai_ANTES_de_a_folha_existir(pasta, monkeypatch):
    """
    'Antes de gerar' e literal: quando a notificacao e escrita, o PDF
    ainda nao esta na pasta. Se sair depois, o aviso deixa de ser aviso.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PECA.pdf", 2.00, 1.00)
    monkeypatch.setattr(montagem, "PASTA_RAIZ", pasta.parent)
    vistos = []

    def falso_notificar(texto, titulo=None):
        vistos.append((texto, sorted(p.name for p in pasta.glob("*.pdf"))))

    montagem._avisar_o_que_vai_sair(pasta, "DOCAN R5200", None, None,
                                    lambda n, m: None, notificar=falso_notificar)

    assert len(vistos) == 1
    texto, pdfs_na_hora = vistos[0]
    assert "DOCAN R5200" in texto, "o aviso tem que dizer de qual máquina é"
    assert "LONA" in texto and "1 peças" in texto
    assert "2.00" in texto, "e com que medida a folha vai fechar"
    assert not any("MONTAGEM" in nome for nome in pdfs_na_hora), \
        "o aviso saiu depois da folha: deixou de ser aviso"


def test_avisar_que_falha_NUNCA_impede_a_montagem(pasta, caplog):
    """
    Avisar e conforto, montar e o trabalho. E a falha vai pro log: um
    except calado aqui esconderia um alarme que parou de tocar.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PECA.pdf", 2.00, 1.00)
    recado = []

    def notificar_quebrado(texto, titulo=None):
        raise RuntimeError("sem bandeja de notificacao")

    saida = montagem._avisar_o_que_vai_sair(
        pasta, "DOCAN R5200", None, None,
        lambda nivel, msg: recado.append((nivel, msg)),
        notificar=notificar_quebrado)

    assert saida is None
    assert any(nivel == "warn" and "não consegui avisar" in msg for nivel, msg in recado)

    # e a montagem segue inteira
    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    assert len(resultado["folhas"]) == 1


def test_pasta_vazia_nao_avisa_nada(pasta):
    assert montagem._avisar_o_que_vai_sair(
        pasta, "DOCAN R5200", None, None, lambda n, m: None,
        notificar=lambda *a, **k: pytest.fail("não podia avisar")) is None


# ---------- a saida, os 10 m e os formatos ----------
#
# Tres pedidos dele de 05/10/2026: "precisamos de uma pasta de saida
# depois de montado, saida DOCAN, saida SWJ"; "o arquivo montado deve
# conter no maximo 10 metros, se for maior dividir em PDF de 10 em 10
# metros"; "as pastas precisa ler tambem todos os formatos de arquivos
# que ja usamos no sistema, pra depois sair em PDF".


def test_a_folha_pronta_vai_pra_pasta_de_SAIDA(pasta):
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PECA.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    saida = montagem.pasta_de_saida("DOCAN R5200", pasta.parent)

    assert folha.parent == saida
    assert saida.name == "SAIDA DOCAN R5200", "o nome da pasta carrega o da maquina"
    assert folha.with_suffix(".json").is_file(), "a ficha acompanha a folha"
    assert not list(pasta.glob("*.pdf")), "nada de folha pronta na entrada"


def test_garantir_pastas_cria_entrada_E_saida(tmp_path):
    montagem.garantir_pastas(raiz=tmp_path)
    for maquina in montagem.maquinas_que_montam():
        assert (tmp_path / maquina).is_dir()
        assert (tmp_path / ("SAIDA " + maquina)).is_dir()


def test_a_saida_NAO_e_lida_como_entrada(pasta):
    """
    A pasta de saida fica ao LADO da de entrada, nunca dentro: dentro, a
    passada seguinte leria a folha pronta como peca.
    """
    saida = montagem.pasta_de_saida("DOCAN R5200", pasta.parent)
    assert saida.parent == pasta.parent and saida != pasta
    assert montagem.maquina_da_pasta(saida) is None, \
        "a pasta de saida nao pode ser confundida com a da maquina"


def test_montagem_comprida_sai_dividida_de_10_em_10_metros(pasta):
    # 12 pecas de 2,40 x 2,00 numa bobina de 5,00: duas por fileira,
    # 6 fileiras de 2,05 = 12,30 m de encaixe
    for i in range(12):
        arte(pasta, "1UN LONA IMPRESSA 2.40X2.00M_VIBRA_PECA_%d.pdf" % i, 2.40, 2.00)

    previa = montagem.prever_pasta(pasta, raiz_clientes=pasta.parent / "x")
    assert len(previa["folhas"]) > 1, "passou de 10 m e tinha que sair dividida"
    for folha in previa["folhas"]:
        assert folha["folha_m"] <= montagem.MAXIMO_COMPRIMENTO_M + 0.001

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    assert len(resultado["folhas"]) == len(previa["folhas"])
    nomes = [f["arquivo"].name for f in resultado["folhas"]]
    assert all("parte" in nome for nome in nomes), \
        "o nome tem que dizer qual parte e, senao as duas parecem a mesma folha"

    # e NENHUMA peca se perdeu no corte
    montadas = 0
    for f in resultado["folhas"]:
        ficha = json.loads(f["arquivo"].with_suffix(".json").read_text(encoding="utf-8"))
        montadas += len(ficha["pecas"])
        with pymupdf.open(str(f["arquivo"])) as doc:
            assert doc.load_page(0).rect.height / PT_M <= \
                montagem.MAXIMO_COMPRIMENTO_M + 0.001
    assert montadas == 12


def test_a_divisao_nunca_parte_uma_peca(pasta):
    """
    "Jamais deve cortar algum pedaco da imagem" (05/10/2026). O corte e
    entre FILEIRAS: cada peca sai inteira numa folha so.
    """
    for i in range(12):
        arte(pasta, "1UN LONA IMPRESSA 2.40X2.00M_VIBRA_PECA_%d.pdf" % i, 2.40, 2.00)

    pecas, _ = montagem.pecas_da_pasta(pasta)
    postas, _comprimento = montagem.encaixar(pecas, 5.00, 0.0)
    folhas = montagem.dividir_por_fileira(postas, 10.0)

    vistas = [p[0] for folha, _c in folhas for p in folha]
    assert sorted(vistas) == sorted(p[0] for p in postas), \
        "peca sumiu ou foi duplicada na divisao"
    assert len(vistas) == len(set(vistas)), "a mesma peca ficou em duas folhas"
    for folha, comprimento in folhas:
        assert comprimento <= 10.001
        assert min(p[2] for p in folha) == pytest.approx(0.0, abs=1e-9), \
            "cada folha comeca no proprio topo"


def test_peca_mais_alta_que_o_maximo_sai_INTEIRA(pasta):
    """
    Entre quebrar a regra dos 10 m e cortar arte, quem cede e o tamanho.
    Uma lona de 12 m e uma peca so: dividi-la seria corta-la.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X12.00M_VIBRA_GIGANTE.pdf", 2.00, 12.00)

    pecas, recusadas = montagem.pecas_da_pasta(pasta)
    assert not recusadas
    postas, _c = montagem.encaixar(pecas, 5.00, 0.0)
    folhas = montagem.dividir_por_fileira(postas, 10.0)

    assert len(folhas) == 1, "nao da pra dividir uma peca so"
    assert folhas[0][1] > 10.0

    montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    saida = montagem.pasta_de_saida("DOCAN R5200", pasta.parent)
    folha = next(saida.glob("*.pdf"))
    with pymupdf.open(str(folha)) as doc:
        assert doc.load_page(0).rect.height / PT_M > 12.0


def test_a_pasta_le_TODOS_os_formatos_do_sistema():
    """
    A lista nao e propria: e a do sistema (rasterlink_hotfolder), mais o
    .bmp e o .psd que ja aparecem noutras partes. Lista separada vira
    lista que diverge, e ai a pasta ignora calada um arquivo que o resto
    do sistema aceita.
    """
    import rasterlink_hotfolder as rl_hf

    for extensao in rl_hf.EXTENSOES_ACEITAS:
        assert extensao in montagem.EXTENSOES_DE_ARTE, \
            "%s entra no vigia e a montagem ignorava" % extensao
    assert ".psd" in montagem.EXTENSOES_DE_ARTE
    # e cada uma tem um caminho: ou abre, ou vira imagem, ou passa no Adobe
    for extensao in montagem.EXTENSOES_DE_ARTE:
        assert (extensao in montagem.COMO_PDF or extensao in montagem.IMAGENS
                or extensao in montagem.PRECISA_ADOBE)


def test_imagem_entra_na_montagem_e_sai_em_PDF(pasta):
    """PNG/JPG/TIF entram pelo convert_to_pdf, no mesmo caminho do PDF."""
    doc = pymupdf.open()
    pagina = doc.new_page(width=1.00 * PT_M, height=0.50 * PT_M)
    pagina.draw_rect(pagina.rect, color=None, fill=(0.2, 0.4, 0.8))
    pix = pagina.get_pixmap(dpi=72)
    pix.save(str(pasta / "1UN LONA IMPRESSA 1.00X0.50M_VIBRA_FOTO.png"))
    doc.close()

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")

    assert len(resultado["folhas"]) == 1 and not resultado["recusadas"]
    assert resultado["folhas"][0]["arquivo"].suffix == ".pdf"


def test_eps_e_psd_sao_convertidos_ANTES_de_medir(pasta):
    """
    O PyMuPDF nao abre EPS nem PSD: sem a conversao eles seriam recusados
    por "nao consegui abrir pra medir". A conversao e um passo A PARTE
    porque ESCREVE -- e a previa so pode olhar.
    """
    falso = pasta / "1UN LONA IMPRESSA 1.00X0.50M_VIBRA_ARTE.eps"
    falso.write_bytes(b"nao e um eps de verdade")

    assert [a.name for a in montagem.a_converter(pasta)] == [falso.name]

    # a previa NAO converte: ela so olha
    montagem.prever_pasta(pasta, raiz_clientes=pasta.parent / "x")
    assert falso.is_file(), "a previa converteu: ela nao pode escrever nada"

    def falso_conversor(origem, destino):
        doc = pymupdf.open()
        pagina = doc.new_page(width=1.00 * PT_M, height=0.50 * PT_M)
        pagina.draw_rect(pagina.rect, color=None, fill=(0.9, 0.3, 0.1))
        doc.save(destino)
        doc.close()

    gerados = montagem.converter_o_que_precisa(
        pasta, conversores={".eps": falso_conversor})

    assert [p.name for p in gerados] == ["1UN LONA IMPRESSA 1.00X0.50M_VIBRA_ARTE.pdf"]
    assert not falso.exists(), "o original sai da vista, senao converte de novo toda rodada"
    pecas, recusadas = montagem.pecas_da_pasta(pasta)
    assert len(pecas) == 1 and not recusadas


def test_conversao_que_falha_nao_derruba_a_montagem(pasta):
    """Programa fechado nao pode impedir o resto da pasta de montar."""
    (pasta / "1UN LONA IMPRESSA 1.00X0.50M_VIBRA_QUEBRADA.eps").write_bytes(b"x")
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_BOA.pdf", 2.00, 1.00)
    avisos = []

    def conversor_quebrado(origem, destino):
        raise RuntimeError("Illustrator nao esta instalado")

    montagem.converter_o_que_precisa(pasta, logger=lambda n, m: avisos.append((n, m)),
                                     conversores={".eps": conversor_quebrado})
    assert any(nivel == "warn" for nivel, _m in avisos)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    assert len(resultado["folhas"]) == 1, "a arte boa tinha que montar do mesmo jeito"
