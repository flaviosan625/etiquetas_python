"""
Recebimento SEM caderno (receber_artes, segunda metade): do que foi
baixado pra pasta de espera até ARTES — medir, separar página, descrever,
nomear, arquivar.

As regras que os testes travam são do usuário, 2026-09-21:
  - a medida vem sempre da arte ("tamanho da arte sempre mais confiável");
  - sem especificação: 1 unidade e material A DEFINIR, sem perguntar;
  - arquivo de apoio (.ai de trabalho, prévia) fica junto, com o nome do
    cliente.

Nenhum teste toca pasta real nem o Illustrator: a remoção de marca é um
dublê que conta quantas vezes foi chamada.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pymupdf
import pytest

import caminhos
import clientes
import marcas_de_corte
import origem_artes as oa
import receber_artes as ra

PT = 72 / 0.0254   # pontos por metro


@pytest.fixture(autouse=True)
def nada_real(tmp_path, monkeypatch):
    onedrive = tmp_path / "UNYCOMUNICACAO"
    monkeypatch.setattr(caminhos, "ONEDRIVE_UNY", onedrive)
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", onedrive / "Recebimento de Artes")
    monkeypatch.setattr(caminhos, "EVENTOS", onedrive / "EVENTOS")
    monkeypatch.setattr(caminhos, "ETIQUETAS_GERADAS", tmp_path / "etiquetas_geradas")
    monkeypatch.setattr(caminhos, "PASTA_RECEBENDO", tmp_path / "recebendo")
    (onedrive / "Recebimento de Artes").mkdir(parents=True)

    def illustrator_proibido(*a, **k):
        raise AssertionError("teste tentou abrir o Illustrator de verdade")
    monkeypatch.setattr(marcas_de_corte, "remover_marcas_com_limite", illustrator_proibido)


def _pdf(caminho, paginas=((4.30, 2.80),), sangria_m=0.0, marca_m=0.0, texto="ARTE"):
    """
    PDF com as caixas de um arquivo de arte-finalista. 'paginas' em metros
    (a arte); a página ganha sangria e, se pedir, a moldura da marca de corte.
    """
    doc = pymupdf.open()
    for largura, altura in paginas:
        folga = (sangria_m + marca_m) * PT
        w, h = largura * PT + 2 * folga, altura * PT + 2 * folga
        pg = doc.new_page(width=w, height=h)
        pg.insert_text((folga + 10, folga + 30), texto, fontsize=20)
        m = marca_m * PT
        s = (sangria_m + marca_m) * PT
        # sem margem, a caixa É a página: declarar daria erro de arredondamento
        if m:
            pg.set_bleedbox(pymupdf.Rect(m, m, w - m, h - m))
        if s:
            pg.set_trimbox(pymupdf.Rect(s, s, w - s, h - s))
    caminho = pathlib.Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(caminho))
    doc.close()
    return caminho


def _arq(nome, grupo=""):
    return oa.Arquivo(id=(grupo + "/" + nome) if grupo else nome, nome=nome, grupo=grupo)


def _baixado(tmp_path, arquivo, criar=None):
    local = tmp_path / "espera" / (arquivo.grupo or "_") / arquivo.nome
    if criar:
        criar(local)
    else:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b"conteudo de " + arquivo.nome.encode())
    return (arquivo, local, "teste|origem|" + arquivo.id)


# ============================================================ descrever

def test_descricao_do_arquivo_do_mandarin_tira_af_medida_e_cliente():
    assert ra.limpar_descricao("AF_MANDARIN_SESSIONS_BACKDROP_400X250CM",
                               remover=("Mandarin Sessions",)) == "BACKDROP"


def test_descricao_tira_o_artboard_da_previa_exportada():
    d = ra.limpar_descricao("AF_MLXP26_LANDMARK_PAINEL_FRONTAL_FUNDO_9,5x4,5mArtboard 1")
    assert "ARTBOARD" not in d and "9,5" not in d and "PAINEL FRONTAL FUNDO" in d


def test_pasta_de_uma_peca_so_da_o_nome_da_peca():
    """O Mercado Livre: cada pasta é uma peça, com o PDF, o .ai e o PNG dela."""
    grupo = "LANDMARK / PAINEL FRONTAL FUNDO"
    irmaos = [_arq("AF_ML_PAINEL_9,5x4,5m.pdf", grupo), _arq("AF_ML_PAINEL_9,5x4,5m.ai", grupo),
              _arq("AF_ML_PAINEL_9,5x4,5mArtboard 1.png", grupo)]
    assert ra.descricao_sugerida(irmaos[0], irmaos) == "PAINEL FRONTAL FUNDO"


def test_pasta_com_varias_pecas_usa_o_nome_de_cada_arquivo():
    """O ZIP do Mandarin: AFs_CENOGRAFIA/ com 4 artes diferentes."""
    grupo = "AFs_CENOGRAFIA"
    irmaos = [_arq("AF_MANDARIN_SESSIONS_%s.pdf" % n, grupo) for n in ("TOTEM", "PAINEL", "SAIA_PALCO")]
    assert ra.descricao_sugerida(irmaos[2], irmaos, cliente="Mandarin Sessions") == "SAIA PALCO"


# ======================================================== especificação

def test_sem_especificacao_e_1_unidade_e_a_definir():
    qtd, material, de_onde, _ = ra.especificacao_do_nome(_arq("AF_MANDARIN_SESSIONS_TOTEM.pdf"))
    assert (qtd, material) == (1, "A DEFINIR")
    assert "sem especificação" in de_onde["quantidade"] and "sem especificação" in de_onde["material"]


def test_o_que_o_nome_especifica_vale():
    qtd, material, de_onde, _ = ra.especificacao_do_nome(_arq("10UN LONA IMPRESSA FAIXA 3X1M.pdf"))
    assert (qtd, material) == (10, "LONA")
    assert de_onde["material"] == "nome do arquivo"


def test_material_pode_vir_do_nome_da_pasta():
    _, material, de_onde, _ = ra.especificacao_do_nome(_arq("FAIXA 01.pdf", "LONAS"))
    assert material == "LONA" and de_onde["material"] == "nome da pasta"


def test_dois_materiais_no_nome_nao_se_escolhe_no_chute():
    _, material, _, avisos = ra.especificacao_do_nome(_arq("ADESIVO SOBRE PS.pdf"))
    assert material == "A DEFINIR" and any("mais de um material" in a for a in avisos)


# =============================================================== propor

def test_medida_vem_da_arte_mesmo_com_o_nome_dizendo_outra(tmp_path):
    """BACKDROP_400X250CM media 4,30x2,80 na arte: vale a arte, e avisa."""
    a = _arq("AF_MANDARIN_SESSIONS_BACKDROP_400X250CM.pdf", "AFs")
    b = _baixado(tmp_path, a, lambda p: _pdf(p, [(4.30, 2.80)], sangria_m=0.003))

    peca, = ra.propor([b], cliente="Mandarin Sessions")

    assert peca.arte_m == pytest.approx((4.30, 2.80), abs=0.001)
    assert peca.sangria_m == pytest.approx((4.306, 2.806), abs=0.001)
    assert peca.de_onde["medida"] == "da arte"
    assert any("vale a arte" in av for av in peca.avisos)


def test_pdf_com_paginas_de_tamanhos_diferentes_vira_uma_peca_por_pagina(tmp_path):
    """O TOTEM do Mandarin: 0,80x1,90 + um quadrado de 0,50x0,50 no mesmo PDF."""
    a = _arq("AF_MANDARIN_SESSIONS_TOTEM.pdf", "AFs")
    b = _baixado(tmp_path, a, lambda p: _pdf(p, [(0.80, 1.90), (0.50, 0.50)]))

    pecas = ra.propor([b], cliente="Mandarin Sessions")

    assert [p.pagina for p in pecas] == [1, 2]
    assert pecas[0].arte_m == pytest.approx((0.80, 1.90), abs=0.001)
    assert pecas[1].arte_m == pytest.approx((0.50, 0.50), abs=0.001)
    assert pecas[1].descricao == "TOTEM - PAGINA 2"


def test_paginas_do_mesmo_tamanho_ficam_juntas_e_da_pra_separar(tmp_path):
    a = _arq("BANNER FRENTE E VERSO.pdf")
    b = _baixado(tmp_path, a, lambda p: _pdf(p, [(0.80, 1.90), (0.80, 1.90)]))

    peca, = ra.propor([b])

    assert peca.paginas == 2 and peca.pagina is None
    assert any("frente e verso" in av for av in peca.avisos)
    assert [p.pagina for p in ra.separar_paginas(peca)] == [1, 2]


def test_marca_de_corte_e_detectada_na_proposta(tmp_path):
    a = _arq("PAINEL.pdf")
    b = _baixado(tmp_path, a, lambda p: _pdf(p, [(2.0, 1.0)], sangria_m=0.03, marca_m=0.02))
    assert ra.propor([b])[0].marca == "tem"


def test_ai_ao_lado_do_pdf_e_trabalho_e_fica_com_o_nome_do_cliente(tmp_path):
    pdf, ai = _arq("X_9,5x4,5m.pdf", "P"), _arq("X_9,5x4,5m.ai", "P")
    bp = _baixado(tmp_path, pdf, lambda p: _pdf(p, [(9.5, 4.5)]))
    ba = _baixado(tmp_path, ai)

    pecas = ra.propor([bp, ba], todos=[pdf, ai])

    assert [p.papel for p in pecas] == ["arte", "trabalho"]
    assert ra.nome_final(pecas[1]) == "X_9,5x4,5m.ai"


def test_imagem_e_medida_pela_resolucao_gravada(tmp_path):
    from PIL import Image
    a = _arq("BACKDROP.tif")

    def criar(p):
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1000, 500), "orange").save(p, dpi=(100, 100))   # 0,254 x 0,127 m

    peca, = ra.propor([_baixado(tmp_path, a, criar)])

    assert peca.arte_m == pytest.approx((0.254, 0.127), abs=0.001)
    # a imagem é examinada já na proposta: lisa, sem marca nas margens
    assert peca.marca == "nao tem"


def test_imagem_sem_resolucao_cai_na_medida_do_nome(tmp_path):
    from PIL import Image
    a = _arq("BACKDROP 400X250CM.png")

    def criar(p):
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (100, 50), "orange").save(p)   # PNG sem DPI

    peca, = ra.propor([_baixado(tmp_path, a, criar)])

    assert peca.arte_m == pytest.approx((4.0, 2.5))
    assert "nome do arquivo" in peca.de_onde["medida"]


def test_eps_e_medido_pelo_cabecalho(tmp_path):
    a = _arq("LOGO.eps")

    def criar(p):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 283 142\n"
                     "%%HiResBoundingBox: 0 0 283.465 141.732\n", encoding="latin-1")

    peca, = ra.propor([_baixado(tmp_path, a, criar)])

    assert peca.arte_m == pytest.approx((0.10, 0.05), abs=0.001)


# =============================================================== nomear

def _peca(nome="BACKDROP.pdf", arte=(4.30, 2.80), sangria=(4.30, 2.80), **kw):
    a = _arq(nome)
    base = dict(arquivo=a, local=pathlib.Path("x") / nome, chave="t|o|" + nome, papel="arte",
                descricao="BACKDROP", arte_m=arte, sangria_m=sangria)
    base.update(kw)
    return ra.Peca(**base)


def test_nome_sem_especificacao():
    assert ra.nome_final(_peca()) == "1UN A DEFINIR 4,30X2,80M_BACKDROP.pdf"


def test_nome_com_area_na_frente_como_no_mercado_livre():
    p = _peca(descricao="PAINEL FRONTAL FUNDO", material="LONA", arte=(9.5, 4.5), sangria=(9.8, 4.8))
    assert ra.nome_final(p, area="LANDMARK") == \
        "1UN LONA 9,50X4,50M_LANDMARK - PAINEL FRONTAL FUNDO_sangria 9,80X4,80M.pdf"


def test_area_nao_se_repete_quando_a_descricao_ja_comeca_com_ela():
    p = _peca(descricao="LANDMARK - PAINEL")
    assert ra.nome_final(p, area="Landmark").count("LANDMARK") == 1


def test_area_com_acento_sai_sem_acento_como_as_outras():
    assert "_AREA PREMIUM - BACKDROP" in ra.nome_final(_peca(), area="Área Premium")


def test_pagina_separada_sai_em_pdf():
    p = _peca(nome="TOTEM.pdf", pagina=2, descricao="TOTEM - PAGINA 2", arte=(0.5, 0.5), sangria=(0.5, 0.5))
    assert ra.nome_final(p).endswith("_TOTEM - PAGINA 2.pdf")


def test_arquivos_de_apoio_com_o_mesmo_nome_nao_se_atropelam():
    a1 = ra.Peca(arquivo=_arq("mockup.jpg", "PAINEL VERSO"), local=pathlib.Path("a"), chave="x", papel="previa")
    a2 = ra.Peca(arquivo=_arq("mockup.jpg", "PAINEL FRENTE"), local=pathlib.Path("b"), chave="y", papel="previa")
    nomes = ra.nomes_do_lote([a1, a2])
    assert sorted(nomes.values()) == ["mockup (PAINEL FRENTE).jpg", "mockup (PAINEL VERSO).jpg"]


def test_duas_artes_com_o_mesmo_nome_sao_barradas():
    """As páginas 152 e 153 do ML: mesmo texto na ficha, artes diferentes."""
    assert ra.repetidos([_peca(nome="a.pdf"), _peca(nome="b.pdf")])


# ============================================================= arquivar

def _cliente(nome="Mandarin Sessions"):
    return clientes.criar(nome)


def test_arquivar_poe_a_arte_com_o_nome_e_o_apoio_com_o_do_cliente(tmp_path):
    pdf, ai = _arq("X_9,5x4,5m.pdf", "P"), _arq("X_9,5x4,5m.ai", "P")
    bp = _baixado(tmp_path, pdf, lambda p: _pdf(p, [(9.5, 4.5)]))
    ba = _baixado(tmp_path, ai)
    pecas = ra.propor([bp, ba], todos=[pdf, ai])
    cliente = _cliente()
    destino = cliente.pasta / "ARTES" / "LANDMARK"

    resumo = ra.arquivar(pecas, cliente, destino, area="LANDMARK", remover_marcas=False)

    assert sorted(p.name for p in destino.iterdir()) == [
        "1UN A DEFINIR 9,50X4,50M_LANDMARK - P.pdf", "X_9,5x4,5m.ai"]
    assert len(resumo.arquivadas) == 2 and not resumo.falharam
    assert bp[1].is_file(), "o baixado na espera não é consumido"


def test_arquivar_registra_de_onde_veio_e_o_que_falta(tmp_path):
    a = _arq("AF_MANDARIN_SESSIONS_BACKDROP_400X250CM.pdf", "AFs")
    pecas = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(4.30, 2.80)]))], cliente="Mandarin Sessions")
    cliente = _cliente()

    ra.arquivar(pecas, cliente, cliente.pasta / "ARTES", remover_marcas=False)

    registro = json.loads((cliente.pasta / "_baixados.json").read_text(encoding="utf-8"))
    entrada = registro["teste|origem|AFs/AF_MANDARIN_SESSIONS_BACKDROP_400X250CM.pdf"]
    assert entrada["arquivo"] == "1UN A DEFINIR 4,30X2,80M_BACKDROP.pdf"
    assert entrada["falta_confirmar"] == ["material"], "1UN é regra; A DEFINIR é pendência"
    assert entrada["medida_no_nome_m"] == [4.0, 2.5]
    assert not pathlib.Path(entrada["pasta"]).is_absolute(), "gravado relativo ao OneDrive"


def test_arquivar_separa_as_paginas_e_cada_uma_tem_o_seu_tamanho(tmp_path):
    a = _arq("AF_MANDARIN_SESSIONS_TOTEM.pdf", "AFs")
    pecas = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(0.80, 1.90), (0.50, 0.50)]))],
                      cliente="Mandarin Sessions")
    cliente = _cliente()

    resumo = ra.arquivar(pecas, cliente, cliente.pasta / "ARTES", remover_marcas=False)

    for peca, caminho in resumo.arquivadas:
        d = marcas_de_corte.medidas(caminho)
        corte = d.get("TrimBox_pt") or d["MediaBox_pt"]   # sem caixa declarada, a arte é a página
        assert d["paginas"] == 1
        assert (corte[0] / PT, corte[1] / PT) == pytest.approx(peca.arte_m, abs=0.001)


def test_pasta_de_nome_generico_com_uma_arte_so_nao_vira_descricao(tmp_path):
    """
    Baixar só o BACKDROP de dentro de 'AFs/' não pode chamar a peça de 'AFs'
    — nem devolver o nome do cliente junto.
    """
    a = _arq("AF_MANDARIN_SESSIONS_BACKDROP_400X250CM.pdf", "AFs")
    peca, = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(4.30, 2.80)]))], cliente="Mandarin Sessions")
    assert peca.descricao == "BACKDROP"


def test_nunca_sobrescreve_arquivo_diferente(tmp_path):
    a = _arq("BACKDROP.pdf")
    pecas = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(4.30, 2.80)]))])
    cliente = _cliente()
    destino = cliente.pasta / "ARTES"
    destino.mkdir(exist_ok=True)
    velho = destino / ra.nome_final(pecas[0])
    velho.write_bytes(b"outra arte")

    resumo = ra.arquivar(pecas, cliente, destino, remover_marcas=False)

    assert velho.read_bytes() == b"outra arte"
    assert resumo.falharam and "já existe" in resumo.falharam[0][1]


def test_mesmo_arquivo_de_novo_e_ja_estava(tmp_path):
    a = _arq("BACKDROP.pdf")
    pecas = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(4.30, 2.80)]))])
    cliente = _cliente()
    ra.arquivar(pecas, cliente, cliente.pasta / "ARTES", remover_marcas=False)

    resumo = ra.arquivar(pecas, cliente, cliente.pasta / "ARTES", remover_marcas=False)

    assert resumo.ja_estavam and not resumo.falharam


def test_nomes_repetidos_param_o_arquivamento_antes_de_gravar(tmp_path):
    cliente = _cliente()
    with pytest.raises(ra.ErroRecebimento, match="iguais"):
        ra.arquivar([_peca(nome="a.pdf"), _peca(nome="b.pdf")], cliente, cliente.pasta / "ARTES")
    assert not any((cliente.pasta / "ARTES").iterdir())


def test_a_mesma_arte_em_tres_pecas_passa_uma_vez_so_pelo_illustrator(tmp_path, monkeypatch):
    """O PAINEL FUNDO LATERAIS do LANDMARK: uma arte, três peças."""
    chamadas = []

    def fingido(caminho, timeout_s=None, logger=None):
        chamadas.append(caminho)
        return True, "ok"
    monkeypatch.setattr(marcas_de_corte, "remover_marcas_com_limite", fingido)

    a = _arq("LATERAIS.pdf")
    base, = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(0.5, 4.5)], sangria_m=0.03, marca_m=0.02))])
    esquerdo = ra.duplicar(base, [base])
    esquerdo.descricao = "LATERAIS ESQUERDO"
    direito = ra.duplicar(base, [base, esquerdo])
    direito.descricao = "LATERAIS DIREITO"
    cliente = _cliente()

    resumo = ra.arquivar([base, esquerdo, direito], cliente, cliente.pasta / "ARTES")

    assert len(chamadas) == 1
    assert len(resumo.arquivadas) == 3
    registro = json.loads((cliente.pasta / "_baixados.json").read_text(encoding="utf-8"))
    assert sum(1 for k in registro if k.startswith("teste|origem|LATERAIS.pdf")) == 3


def test_marca_que_nao_saiu_nao_entra_pela_metade(tmp_path, monkeypatch):
    monkeypatch.setattr(marcas_de_corte, "remover_marcas_com_limite",
                        lambda c, timeout_s=None, logger=None: (False, "o Illustrator travou"))
    a = _arq("PAINEL.pdf")
    pecas = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(2.0, 1.0)], sangria_m=0.03, marca_m=0.02))])
    cliente = _cliente()

    resumo = ra.arquivar(pecas, cliente, cliente.pasta / "ARTES")

    assert resumo.falharam and "NÃO entrou" in resumo.falharam[0][1]
    assert not list((cliente.pasta / "ARTES").glob("*.pdf"))


def test_o_original_de_origem_descartavel_e_guardado(tmp_path):
    class OrigemFingida:
        tipo, rotulo = "wetransfer", "WeTransfer · MANDARIN SESSIONS - 23.09"

        def guardar_original(self, pasta):
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / "AFs_CENOGRAFIA.zip").write_bytes(b"zip")
            return [pasta / "AFs_CENOGRAFIA.zip"]

    a = _arq("BACKDROP.pdf")
    pecas = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(4.30, 2.80)]))])
    cliente = _cliente()

    resumo = ra.arquivar(pecas, cliente, cliente.pasta / "ARTES", origem=OrigemFingida(),
                         remover_marcas=False)

    assert resumo.originais and resumo.originais[0].is_relative_to(cliente.pasta / "_sistema" / "recebidos")


def test_preparo_nao_suja_a_pasta_de_artes(tmp_path):
    """O Illustrator trabalha na espera local, nunca dentro de ARTES (OneDrive)."""
    a = _arq("TOTEM.pdf")
    pecas = ra.propor([_baixado(tmp_path, a, lambda p: _pdf(p, [(0.8, 1.9), (0.5, 0.5)]))])
    cliente = _cliente()
    destino = cliente.pasta / "ARTES"

    ra.arquivar(pecas, cliente, destino, remover_marcas=False)

    assert all(p.suffix == ".pdf" and not p.name.startswith("~") for p in destino.iterdir())


def test_foi_recebido_acha_pagina_e_copia():
    recebidos = {"wetransfer|T|X/TOTEM.pdf|pagina 2": {}, "drive|R|abc|copia 2": {}}
    assert ra.foi_recebido("wetransfer|T|X/TOTEM.pdf", recebidos)
    assert ra.foi_recebido("drive|R|abc", recebidos)
    assert not ra.foi_recebido("drive|R|ab", recebidos)
