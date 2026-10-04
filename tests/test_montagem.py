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


def test_a_margem_e_por_maquina():
    """Ele deu uma pra cada (04/10/2026): cada maquina agarra o material de um jeito."""
    assert montagem.margem("DOCAN R5200") == 0.02
    assert montagem.margem("DOCAN H2525") == 0.02
    assert montagem.margem("UJV 100 UNY CV") == 0.03
    assert montagem.margem("SWJ320A") == 0.05


def test_a_largura_vem_do_cadastro_da_maquina():
    """
    As larguras nao estao escritas na montagem: mudam no cadastro da
    maquina e valem aqui. Foi assim que a correcao de 5,00 pra 5,20 na
    DOCAN (04/10/2026) chegou na montagem sem eu mexer nela.
    """
    assert montagem.largura_util("DOCAN R5200") == 5.20
    assert montagem.largura_util("SWJ320A") == 3.24
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
    assert "400 mm por lado" in ajuste["motivo"], "o motivo tem que dizer QUANTO sobraria"


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
        assert round(doc.load_page(0).rect.width / PT_M, 2) == 5.20


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
    assert "mm por lado" in motivo and "Confira a arte ou o nome" in motivo


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
    assert ficha["folha_m"][0] == 5.2
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


def test_o_rotulo_encolhe_ate_caber_e_nunca_some(pasta):
    """Se nem encolhendo e cortando couber, e pra ESTOURAR -- rotulo que some e peca perdida."""
    import pymupdf as mupdf

    doc = mupdf.open()
    pagina = doc.new_page(width=1000, height=500)
    apertada = mupdf.Rect(0, 0, 300, 40)

    milimetros, escrito = montagem._escrever_rotulo(
        pagina, apertada, "07  VIBRA_UM_NOME_BEM_COMPRIDO_DE_PECA")
    assert 0 < milimetros <= 20
    assert escrito.startswith("07"), "o numero nunca pode ser o pedaco cortado"

    with pytest.raises(AssertionError):
        montagem._escrever_rotulo(pagina, mupdf.Rect(0, 0, 4, 4), "07  QUALQUER")
    doc.close()


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


def test_escala_e_sempre_UNIFORME_nunca_estica(pasta):
    """
    "As artes nao podem ser mexidas em absolutamente nada" (04/10/2026).
    A caixa que a arte cobre mantem a proporcao do arquivo: um fator so
    pros dois lados.
    """
    import pymupdf as mupdf

    caixa = mupdf.Rect(0, 0, 200, 100)          # proporcao 2,00
    onde = montagem._caixa_que_a_arte_cobre(caixa, 199, 100, mupdf)   # arte 1,99

    assert onde.width / onde.height == pytest.approx(199 / 100, rel=1e-6)
    assert onde.width >= caixa.width - 0.001 and onde.height >= caixa.height - 0.001, \
        "a arte tem que COBRIR a caixa: por dentro deixaria tira branca na peca"


def test_quem_decide_e_quanto_sobra_em_MILIMETROS_nao_a_porcentagem():
    """
    A regua mudou em 04/10/2026, e quem a mudou foi arte REAL dele: oito
    lonas da LOJINHA tinham TODAS as medidas exatamente +0,7 mm acima do
    nome -- offset constante da exportacao, nao erro de proporcao. Em
    porcentagem, a peca mais estreita dava 1,5% e era recusada; em
    milimetros, a sobra era de 3 mm por lado, dentro dos 25 mm de folga.
    A regua errada recusava arte boa.
    """
    # a peca de 0,40 x 3,00 com o arquivo em 1:10 mais 0,7 mm: 1,5% de
    # desvio, 3 mm aparados -- ENTRA
    ajuste = montagem.ajuste_para((0.40, 3.00), (0.0407, 0.3007, 1))
    assert ajuste["acao"] == "escalar"
    assert "3 mm aparados" in ajuste["motivo"]

    # o MESMO 1,5% numa peca dez vezes maior ja nao cabe na folga
    assert montagem.ajuste_para((4.00, 30.00), (0.407, 3.007, 1))["acao"] == "recusar"

    # mesma proporcao, 1% maior nos dois lados: escala uniforme resolve
    assert montagem.ajuste_para((2.00, 1.00), (2.02, 1.01, 1))["acao"] == "escalar"


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


def test_as_marcas_de_corte_ficam_no_MEIO_da_folga(pasta):
    """
    Pedido dele (04/10/2026). Nos cantos da arte obrigariam a cortar
    rente; no meio da folga cada peca fica com 2,5 cm de branco de cada
    lado depois do refile.
    """
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 2.00, 1.00)

    resultado = montagem.montar_pasta(pasta, raiz_clientes=pasta.parent / "x")
    folha = resultado["folhas"][0]["arquivo"]
    ficha = json.loads(folha.with_suffix(".json").read_text(encoding="utf-8"))
    x, y = ficha["pecas"][0]["posicao_m"]
    largura, altura = ficha["pecas"][0]["medida_m"]
    if ficha["pecas"][0]["girada"]:
        largura, altura = altura, largura

    with pymupdf.open(str(folha)) as doc:
        pagina = doc.load_page(0)
        linhas = [d["rect"] for d in pagina.get_drawings() if d["rect"].height < 5]
        # a marca de cima fica 2,5 cm ACIMA da arte
        alvo = (y - montagem.RECUO_CORTE_M) * PT_M
        assert any(abs(r.y0 - alvo) < 2 for r in linhas), \
            "nenhuma marca horizontal a 2,5 cm acima da arte"


# ---------- a arte nunca e esticada, em lugar nenhum ----------
#
# Regra dele de 04/10/2026: "quando for modificar arte para o tamanho que
# esta no nome do arquivo precisa ser proporcional, nao pode ser esticado
# apenas por um lado". A conferencia que vale e geometrica: medir o que
# saiu no PDF e comparar a proporcao com a do arquivo de origem.


def test_a_proporcao_desenhada_e_a_do_ARQUIVO_nao_a_da_caixa(pasta):
    """
    O defeito que isto pega: passar a medida do NOME pra conta de cobrir
    a torna um no-op (ela devolve a propria caixa), e a arte com
    proporcao um tiquinho diferente entra encaixada POR DENTRO, deixando
    tira branca na peca.
    """
    # o nome pede 2,00 x 1,00 (proporcao 2,000); o arquivo tem 1,992 x 1,00
    arte(pasta, "1UN LONA IMPRESSA 2.00X1.00M_VIBRA_PAINEL.pdf", 1.992, 1.00)

    pecas, recusadas = montagem.pecas_da_pasta(pasta)
    assert not recusadas and pecas[0]["ajuste"]["acao"] == "escalar"

    import pymupdf as mupdf

    caixa = mupdf.Rect(0, 0, 2.00 * PT_M, 1.00 * PT_M)
    arquivo_l, arquivo_a = pecas[0]["arquivo_m"]
    onde = montagem._caixa_que_a_arte_cobre(caixa, arquivo_l, arquivo_a, mupdf)

    assert onde.width / onde.height == pytest.approx(arquivo_l / arquivo_a, rel=1e-6), \
        "a proporcao desenhada tem que ser a do ARQUIVO"
    assert onde != caixa, "se devolveu a propria caixa, a conta virou no-op de novo"
    assert onde.width >= caixa.width - 0.01 and onde.height >= caixa.height - 0.01, \
        "a arte tem que COBRIR a caixa: por dentro deixaria tira branca na peca"


def test_nada_que_passa_apara_mais_que_a_folga_de_corte():
    """
    Cobrir faz a arte passar das marcas, e esse "passar" nao pode invadir
    a peca vizinha. Agora e a propria REGRA que garante: o limite de
    aceitacao E a folga de corte, entao o que entra nunca a estoura.
    """
    assert montagem.SOBRA_MAXIMA_M == montagem.RECUO_CORTE_M, \
        "o limite de aceitacao e a folga de corte: sao a mesma coisa, de proposito"

    for alvo, arquivo in (((1.00, 1.00), (0.98, 1.00)),
                          ((3.77, 3.15), (3.70, 3.15)),
                          ((7.14, 1.10), (0.714, 0.1105))):
        ajuste = montagem.ajuste_para(alvo, (arquivo[0], arquivo[1], 1))
        if ajuste["acao"] != "escalar":
            continue
        fator = ajuste["fator"]
        sobra = max(arquivo[0] * fator - alvo[0], arquivo[1] * fator - alvo[1]) / 2
        assert sobra <= montagem.RECUO_CORTE_M + 0.0005, \
            f"{alvo}: sobra {sobra * 1000:.1f} mm por lado"


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
