"""
Marca de corte em IMAGEM (marcas_de_corte, parte de imagem): achar a
linha de corte só por pixel, propor o corte, e cortar só com conferência.

As imagens são desenhadas aqui com a geometria de um arquivo de
arte-finalista: arte, sangria, e as marcas de corte fora da sangria,
alinhadas com a linha de corte. E com a TARJA de informação na margem de
cima — foi ela que derrubou a primeira versão da detecção (19 falsos
positivos), e só o cruzamento de margens opostas limpa.

O Photoshop nunca é chamado: cortar e reduzir recebem dublês.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest
from PIL import Image, ImageDraw

import caminhos
import marcas_de_corte as mc


@pytest.fixture(autouse=True)
def sem_photoshop(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PASTA_RECEBENDO", tmp_path / "recebendo")

    def proibido(*a, **k):
        raise AssertionError("teste tentou abrir o Photoshop de verdade")
    monkeypatch.setattr(mc, "_cortar_pelo_photoshop", proibido)
    monkeypatch.setattr(mc, "_reduzir_pelo_photoshop", proibido)


def desenhar(arte=(2400, 1500), sangria=45, recuo=8, comprimento=70, margem=40, tarja=True,
             marcas="todas", cor=(230, 90, 30)):
    """
    Imagem com marca de corte. Devolve (imagem, corte, bloco) em pixel.
    'marcas': 'todas', 'nenhuma' ou 'so_esquerda'.
    """
    fora = sangria + recuo + comprimento + margem
    largura, altura = arte[0] + 2 * fora, arte[1] + 2 * fora
    img = Image.new("RGB", (largura, altura), "white")
    d = ImageDraw.Draw(img)
    t0x, t0y = fora, fora
    t1x, t1y = fora + arte[0], fora + arte[1]
    b = (t0x - sangria, t0y - sangria, t1x + sangria, t1y + sangria)
    d.rectangle([b[0], b[1], b[2] - 1, b[3] - 1], fill=cor)

    def linha(x0, y0, x1, y1):
        d.line([(x0, y0), (x1, y1)], fill="black", width=2)

    if marcas != "nenhuma":
        for ty in (t0y, t1y):
            linha(b[0] - recuo - comprimento, ty, b[0] - recuo, ty)          # esquerda
            if marcas == "todas":
                linha(b[2] + recuo, ty, b[2] + recuo + comprimento, ty)      # direita
        if marcas == "todas":
            for tx in (t0x, t1x):
                linha(tx, b[1] - recuo - comprimento, tx, b[1] - recuo)      # cima
                linha(tx, b[3] + recuo, tx, b[3] + recuo + comprimento)      # baixo
    if tarja:
        # "letras" da tarja do Illustrator, só na margem de cima
        for i in range(18):
            x = b[0] + 120 + i * 21
            d.rectangle([x, b[1] - recuo - 25, x + 10, b[1] - recuo - 12], fill="black")
    return img, (t0x, t0y, t1x, t1y), b


def _salvar(img, caminho, dpi=100, **kw):
    img.save(caminho, dpi=(dpi, dpi), **kw)
    return caminho


# ============================================================ detecção

def test_acha_a_linha_de_corte_mesmo_com_a_tarja_de_informacao():
    img, corte, _ = desenhar()

    achado, _ = mc.detectar_corte_em_imagem(img.convert("L"))

    assert achado is not None
    for obtido, esperado in zip(achado["corte"], corte):
        assert abs(obtido - esperado) <= 1.5
    assert achado["desacordo_px"] <= 1


def test_o_bloco_da_arte_e_a_sangria():
    img, _, bloco = desenhar()
    achado, _ = mc.detectar_corte_em_imagem(img.convert("L"))
    for obtido, esperado in zip(achado["bloco"], bloco):
        assert abs(obtido - esperado) <= 1


def test_imagem_sem_marca_nao_inventa_corte():
    img, _, _ = desenhar(marcas="nenhuma", tarja=False)
    achado, _ = mc.detectar_corte_em_imagem(img.convert("L"))
    assert achado is None


def test_marca_de_um_lado_so_nao_e_confiavel():
    """Sem o par do lado oposto, não tem como saber se é marca ou desenho."""
    img, _, _ = desenhar(marcas="so_esquerda")
    achado, _ = mc.detectar_corte_em_imagem(img.convert("L"))
    assert achado is None


# ============================================================ proposta

def test_proposta_mede_a_arte_entre_as_marcas(tmp_path):
    """
    Pelo DPI a imagem inteira mediria mais — com moldura. A arte do nome é
    entre as marcas: 2400 x 1500 px a 100 dpi = 0,6096 x 0,381 m.
    """
    img, _, _ = desenhar()
    caminho = _salvar(img, tmp_path / "arte.tif")

    proposta = mc.propor_corte_imagem(caminho)
    arte, fica = mc.medidas_da_proposta(proposta)

    assert proposta["ok"]
    assert arte == pytest.approx((0.6096, 0.381), abs=0.001)
    assert fica == pytest.approx(((2400 + 90) * 0.000254, (1500 + 90) * 0.000254), abs=0.001)


def test_proposta_mantem_a_sangria_como_no_pdf(tmp_path):
    img, corte, bloco = desenhar(sangria=45)
    proposta = mc.propor_corte_imagem(_salvar(img, tmp_path / "a.png"))

    assert abs(proposta["sangria_px"] - 45) <= 1.5
    ret = mc.retangulo_do_corte(proposta)
    for obtido, esperado in zip(ret, bloco):
        assert abs(obtido - esperado) <= 2


def test_jpg_aberto_ja_reduzido_nao_desloca_o_corte(tmp_path, monkeypatch):
    """
    O JPEG grande abre em modo rascunho, já reduzido. A escala tem que ser
    medida no fim, senão o corte cai deslocado no arquivo de verdade.
    """
    monkeypatch.setattr(mc, "LARGURA_DETECCAO", 1500)
    img, corte, _ = desenhar(arte=(4000, 2400), sangria=60, comprimento=120, recuo=12)
    caminho = _salvar(img.convert("RGB"), tmp_path / "grande.jpg", quality=95)

    proposta = mc.propor_corte_imagem(caminho)

    assert proposta["corte_px"] is not None
    for obtido, esperado in zip(proposta["corte_px"], corte):
        assert abs(obtido - esperado) <= 6, (proposta["corte_px"], corte)


def test_imagem_grande_demais_passa_pelo_photoshop_reduzir(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "LIMITE_DETECCAO_PIXELS", 1000)
    reduzidas = []

    def reduzir(origem, destino, largura):
        with Image.open(origem) as im:
            im.resize((largura, round(im.height * largura / im.width)), Image.Resampling.BOX).save(destino)
        reduzidas.append(origem)

    img, corte, _ = desenhar()
    proposta = mc.propor_corte_imagem(_salvar(img, tmp_path / "enorme.tif"), reduzir=reduzir,
                                      pasta_temporaria=tmp_path)

    assert reduzidas, "o Photoshop (dublê) foi chamado"
    for obtido, esperado in zip(proposta["corte_px"], corte):
        assert abs(obtido - esperado) <= 3


def test_retangulo_nao_passa_da_imagem():
    proposta = {"corte_px": (10, 10, 90, 90), "sangria_px": 50, "largura_px": 100, "altura_px": 100}
    assert mc.retangulo_do_corte(proposta) == (0, 0, 100, 100)


# ================================================================ corte

def _cortador_pil(origem, destino, ret):
    with Image.open(origem) as im:
        dpi = im.info.get("dpi")
        im.crop(ret).save(destino, dpi=dpi) if dpi else im.crop(ret).save(destino)


def test_corte_aprovado_troca_o_arquivo_depois_de_conferir(tmp_path):
    img, _, bloco = desenhar()
    caminho = _salvar(img, tmp_path / "a.tif")

    ok, msg = mc.cortar_imagem(caminho, bloco, cortador=_cortador_pil)

    assert ok, msg
    with Image.open(caminho) as im:
        assert im.size == (bloco[2] - bloco[0], bloco[3] - bloco[1])
        assert round(im.info["dpi"][0]) == 100


def test_corte_com_tamanho_errado_nao_troca(tmp_path):
    img, _, bloco = desenhar()
    caminho = _salvar(img, tmp_path / "a.tif")
    antes = caminho.read_bytes()

    def errado(origem, destino, ret):
        _cortador_pil(origem, destino, (ret[0], ret[1], ret[2] - 50, ret[3]))

    ok, msg = mc.cortar_imagem(caminho, bloco, cortador=errado)

    assert not ok and "NÃO troquei" in msg
    assert caminho.read_bytes() == antes


def test_corte_que_perde_a_resolucao_nao_troca(tmp_path):
    img, _, bloco = desenhar()
    caminho = _salvar(img, tmp_path / "a.tif")

    def sem_dpi(origem, destino, ret):
        with Image.open(origem) as im:
            im.crop(ret).save(destino, dpi=(72, 72))

    ok, msg = mc.cortar_imagem(caminho, bloco, cortador=sem_dpi)
    assert not ok and "resolução" in msg


def test_corte_que_muda_a_arte_nao_troca(tmp_path):
    img, _, bloco = desenhar()
    caminho = _salvar(img, tmp_path / "a.tif")

    def estragou(origem, destino, ret):
        with Image.open(origem) as im:
            Image.new("RGB", (ret[2] - ret[0], ret[3] - ret[1]), "blue").save(destino, dpi=im.info["dpi"])

    ok, msg = mc.cortar_imagem(caminho, bloco, cortador=estragou)
    assert not ok and "mudou" in msg


def test_photoshop_que_falha_nao_deixa_lixo(tmp_path):
    img, _, bloco = desenhar()
    caminho = _salvar(img, tmp_path / "a.tif")

    def falha(origem, destino, ret):
        raise RuntimeError("o Photoshop não respondeu")

    ok, msg = mc.cortar_imagem(caminho, bloco, cortador=falha)
    assert not ok and "não respondeu" in msg
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.tif"]


# ========================================== junto com o recebimento

def test_recebimento_mede_a_imagem_pelas_marcas_e_exige_aprovacao(tmp_path, monkeypatch):
    import origem_artes as oa
    import receber_artes as ra
    import clientes

    onedrive = tmp_path / "UNYCOMUNICACAO"
    monkeypatch.setattr(caminhos, "ONEDRIVE_UNY", onedrive)
    monkeypatch.setattr(caminhos, "RECEBIMENTO_DE_ARTES", onedrive / "Recebimento de Artes")
    (onedrive / "Recebimento de Artes").mkdir(parents=True)

    img, _, bloco = desenhar()
    (tmp_path / "espera").mkdir()
    local = _salvar(img, tmp_path / "espera" / "BACKDROP.tif")
    arquivo = oa.Arquivo(id="BACKDROP.tif", nome="BACKDROP.tif")
    peca, = ra.propor([(arquivo, local, "teste|o|BACKDROP.tif")])

    assert peca.marca == "tem"
    assert peca.arte_m == pytest.approx((0.6096, 0.381), abs=0.001), "a arte é entre as marcas"

    cliente = clientes.criar("Teste")
    resumo = ra.arquivar([peca], cliente, cliente.pasta / "ARTES")
    assert resumo.falharam and "não foi aprovado" in resumo.falharam[0][1]

    # ele aprova; o corte de verdade roda, só que com o Pillow no lugar do Photoshop
    monkeypatch.setattr(mc, "cortar_imagem",
                        lambda c, r, logger=None: _CORTAR_IMAGEM(c, r, cortador=_cortador_pil))
    peca.corte_px = mc.retangulo_do_corte(peca.proposta_corte)
    resumo = ra.arquivar([peca], cliente, cliente.pasta / "ARTES")

    assert not resumo.falharam, resumo.falharam
    _, gravado = resumo.arquivadas[0]
    with Image.open(gravado) as im:
        assert abs(im.width - (bloco[2] - bloco[0])) <= 2
    with Image.open(local) as original:
        assert original.size == img.size, "o baixado na espera não é tocado"


# a função de verdade, guardada antes de qualquer teste trocar ela
_CORTAR_IMAGEM = mc.cortar_imagem
