"""
Máquina PLANA (mesa) contra máquina de ROLO (bobina).

A DOCAN H2525 é plana: imprime em chapa rígida, e a mesa é finita nos
DOIS sentidos. A regra de girar que vale pro rolo não vale aqui, e
confundir as duas produz peça errada — daí estes testes existirem antes
mesmo de a máquina estar cadastrada.

Nada aqui toca pasta nenhuma: LimiteDaMaquina é cálculo puro.
"""
import pytest

import envio_impressao
import rasterlink_hotfolder as rl_hf

# Uma plana de 2,50 × 2,50 m e um rolo de 3,20 m, só pra comparar.
MESA = rl_hf.LimiteDaMaquina(mesa_util_m=(2.50, 2.50))
ROLO = rl_hf.LimiteDaMaquina(largura_util_m=3.20)


def dim(largura_m, altura_m):
    return {"largura_m": largura_m, "altura_m": altura_m}


# ------------------------------------------------------- o que cabe

def test_na_mesa_os_dois_lados_sao_teto():
    """
    O caso que separa mesa de rolo: 2,00 × 4,00 m. Num rolo de 3,20 isso
    passa deitado e imprime — a bobina anda 2,00 m. Numa mesa de 2,50 os
    4,00 m não têm pra onde ir.
    """
    assert ROLO.cabe(2.00, 4.00) is True
    assert MESA.cabe(2.00, 4.00) is False


def test_cabe_na_mesa_quando_entra_nos_dois_lados():
    assert MESA.cabe(2.40, 2.40) is True
    assert MESA.cabe(1.00, 2.50) is True


def test_a_folga_de_um_milimetro_vale_na_mesa_tambem():
    """
    Chapa fechada exatamente na medida vira 2.5000000038 depois da
    conversão de pontos pra metros — recusar isso seria recusar por um
    décimo de milímetro que não existe no material.
    """
    assert MESA.cabe(2.5000000038, 2.5000000038) is True


def test_mesa_retangular_distingue_os_dois_eixos():
    mesa = rl_hf.LimiteDaMaquina(mesa_util_m=(2.50, 1.30))
    assert mesa.cabe_em_pe(2.40, 1.20) is True
    assert mesa.cabe_em_pe(1.20, 2.40) is False, "2,40 nao entra no eixo de 1,30"
    assert mesa.cabe_deitado(1.20, 2.40) is True, "girada ela entra"


# ------------------------------------------------------- quando gira

def test_na_mesa_o_que_ja_cabe_nunca_gira():
    """
    Não existe bobina pra economizar numa plana: girar uma arte que já
    cabe não ganha material nenhum e ainda briga com quem posicionou a
    chapa na mesa.
    """
    assert MESA.decidir_giro(1.00, 2.40) is None


def test_no_rolo_o_que_ja_cabe_gira_por_economia():
    """A mesma arte, num rolo, deita pra gastar menos bobina."""
    giro = ROLO.decidir_giro(1.00, 2.40)
    assert giro["motivo"] == "economia"
    assert giro["economia_m"] == pytest.approx(1.40)


def test_na_mesa_gira_so_pra_encaixar():
    mesa = rl_hf.LimiteDaMaquina(mesa_util_m=(2.50, 1.30))
    giro = mesa.decidir_giro(1.20, 2.40)
    assert giro["motivo"] == "nao_cabe", "girou porque em pe nao entrava"


def test_o_que_nao_cabe_nem_girado_nao_gira():
    assert MESA.decidir_giro(3.00, 3.00) is None


# ------------------------------------------------ texto pra quem lê

def test_a_descricao_diz_mesa_e_nao_largura():
    assert MESA.descricao() == "mesa de 2,50 × 2,50 m"
    assert ROLO.descricao() == "3,20 m úteis"


def test_o_motivo_da_recusa_mede_os_dois_lados_na_plana():
    assert "nem girada" in MESA.porque_nao_cabe()
    assert "largura útil" in ROLO.porque_nao_cabe()


# ------------------------------------------------ leitura da config

def test_mesa_ganha_de_largura_quando_as_duas_aparecem():
    """
    Uma plana com largura solta na configuração seria lida como rolo e
    deixaria passar arte comprida demais pra mesa.
    """
    limite = rl_hf.limite_da_maquina({"mesa_util_m": (2.5, 2.5), "largura_util_m": 2.5})
    assert limite.plana is True
    assert limite.cabe(2.00, 4.00) is False


def test_maquina_sem_medida_nao_recusa_nem_gira_nada():
    assert rl_hf.limite_da_maquina({"hot_folder": r"C:\x"}) is None
    assert rl_hf.limite_da_maquina(r"C:\x") is None


def test_as_maquinas_de_rolo_continuam_sendo_de_rolo():
    """As três de bobina — nenhuma virou mesa por acidente."""
    for nome in ("UJV 100 UNY CV", "SWJ320A", "DOCAN R5200"):
        assert rl_hf.limite_de(nome).plana is False


# --------------------------------------------- a DOCAN H2525 cadastrada

def test_h2525_esta_cadastrada_como_plana_de_2_50():
    limite = rl_hf.limite_de("DOCAN H2525")
    assert limite.plana is True
    assert limite.mesa_util_m == (2.50, 2.50)


def test_h2525_e_atendida_pelo_vigia_deste_pc():
    """
    Ela roda no SAi desta máquina, ao lado da R5200 — se cair no posto do
    RIP, ninguém entrega nada e o arquivo fica encalhado na fila.
    """
    assert "DOCAN H2525" in rl_hf.maquinas_do_posto(rl_hf.POSTO_SAI)


def test_as_duas_docan_nao_dividem_a_mesma_hot_folder():
    """
    O SAi criou a pasta da H2525 como 'Docan_1', não com o nome do setup.
    Cadastro copiado da R5200 mandaria a chapa pra impressora de rolo —
    e o vigia diria "enviado", porque a pasta existe.
    """
    r5200 = rl_hf.MAQUINAS["DOCAN R5200"]["hot_folder"]
    h2525 = rl_hf.MAQUINAS["DOCAN H2525"]["hot_folder"]
    assert r5200 != h2525


def test_arte_de_rolo_nao_passa_na_mesa_da_h2525():
    """
    O caso que a plana precisa recusar: lona de 2,00 × 4,00 m, que a SWJ
    imprime sem pensar, não tem pra onde ir numa mesa de 2,50.
    """
    assert rl_hf.limite_de("DOCAN H2525").cabe(2.00, 4.00) is False
    assert rl_hf.limite_de("SWJ320A").cabe(2.00, 4.00) is True


# ------------------------------------ a tela usa a mesma regra do vigia

def test_a_tela_preve_o_giro_da_plana_pela_mesma_regra():
    maquinas = {"H": {"hot_folder": r"C:\x", "mesa_util_m": (2.50, 1.30)}}

    assert envio_impressao.prever_giro(dim(1.20, 2.40), "H", maquinas)["motivo"] == "nao_cabe"
    assert envio_impressao.prever_giro(dim(1.00, 1.20), "H", maquinas) is None
    assert envio_impressao.cabe_na_maquina(dim(2.00, 4.00), "H", maquinas) is False
    assert envio_impressao.cabe_na_maquina(dim(1.00, 1.20), "H", maquinas) is True


# ------------------------------ a pasta da fila nasce sozinha

def test_a_fila_de_maquina_nova_nasce_na_passada(tmp_path):
    """
    Ate 23/09/2026 a pasta so nascia no primeiro envio, e maquina
    recem-cadastrada nao aparecia na fila - ele foi procurar a da H2525
    pra largar arquivo e nao existia. Pasta que nao existe tambem nao da
    pra usar na mao, que e como um arquivo urgente entra.
    """
    hot = tmp_path / "hot"
    hot.mkdir()
    maquinas = {"MAQUINA NOVA": {"hot_folder": str(hot), "mesa_util_m": (2.5, 2.5)}}
    fila = tmp_path / "fila"
    fila.mkdir()

    rl_hf.vigiar_fila_uma_vez(pasta_fila=fila, maquinas=maquinas, logger=lambda *a: None,
                              pasta_relatorios=tmp_path / "rel")

    assert (fila / "MAQUINA NOVA" / "Enviados").is_dir()


def test_pasta_que_ja_existe_nao_e_mexida(tmp_path):
    fila = tmp_path / "fila"
    (fila / "X" / "Enviados").mkdir(parents=True)
    (fila / "X" / "ja_estava.pdf").write_bytes(b"x")

    nascidas = rl_hf.garantir_pastas_da_fila(fila, {"X": {}})

    assert nascidas == []
    assert (fila / "X" / "ja_estava.pdf").exists()


def test_falha_ao_criar_pasta_nao_derruba_a_passada(tmp_path, monkeypatch):
    """Entregar o que ja esta na fila e o trabalho de verdade; a pasta e conforto."""
    avisos = []
    monkeypatch.setattr(rl_hf.pathlib.Path, "mkdir",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("OneDrive pendurado")))

    nascidas = rl_hf.garantir_pastas_da_fila(tmp_path / "fila", {"X": {}},
                                             logger=lambda n, m: avisos.append(m))

    assert nascidas == []
    assert any("não consegui criar" in m.lower() for m in avisos)


def test_a_h2525_tem_pasta_na_fila_de_verdade():
    """Contra a fila REAL, so leitura: se sumir, o arquivo dela nao tem pra onde ir."""
    import pytest

    fila = rl_hf.PASTA_FILA_ONEDRIVE
    if not fila.is_dir():
        pytest.skip("fila do OneDrive não está nesta máquina")
    assert (fila / "DOCAN H2525").is_dir()


# ------------------------------ DOCAN: o sistema so entrega (24/09/2026)

def _pdf(caminho, largura_m, altura_m):
    import pymupdf

    pt = 72 / 0.0254
    doc = pymupdf.open()
    doc.new_page(width=largura_m * pt, height=altura_m * pt)
    doc.save(str(caminho))
    doc.close()


def test_maquina_que_nao_gira_nunca_gira():
    """Nem por economia, nem pra encaixar: quem acerta isso e quem opera o RIP."""
    rolo = rl_hf.LimiteDaMaquina(largura_util_m=3.20, gira=False)
    mesa = rl_hf.LimiteDaMaquina(mesa_util_m=(2.50, 1.30), gira=False)
    assert rolo.decidir_giro(1.00, 2.40) is None
    assert mesa.decidir_giro(1.20, 2.40) is None
    assert mesa.cabe(2.00, 4.00) is False, "a medida continua valendo pro aviso"


def test_as_duas_docan_so_entregam_e_as_mimaki_continuam_girando():
    assert rl_hf.limite_de("DOCAN R5200").gira is False
    assert rl_hf.limite_de("DOCAN H2525").gira is False
    assert rl_hf.limite_de("UJV 100 UNY CV").gira is True
    assert rl_hf.limite_de("SWJ320A").gira is True


def test_a_tela_nao_promete_giro_na_docan():
    assert envio_impressao.prever_giro(dim(1.00, 2.40), "DOCAN R5200") is None
    assert envio_impressao.prever_giro(dim(1.00, 2.40), "SWJ320A")["motivo"] == "economia"


def test_a_docan_recebe_a_arte_byte_a_byte(tmp_path):
    """
    O caso real: lona em 1:10 (pagina 0,32 x 0,70 de uma peca de 7 x 3,20) foi
    girada pela medida da pagina. Agora o arquivo chega ao RIP como saiu da fila,
    e a medida da pagina ainda vai pro registro de producao.
    """
    origem = tmp_path / "LONA.pdf"
    _pdf(origem, 0.32, 0.70)
    destino = tmp_path / "hot" / "LONA.pdf"
    destino.parent.mkdir()
    limite = rl_hf.limite_da_maquina(rl_hf.MAQUINAS["DOCAN R5200"])

    girou, pagina = rl_hf._montar_para_hot_folder(origem, destino, limite, lambda *a: None)

    assert girou is False
    assert destino.read_bytes() == origem.read_bytes()
    assert pagina is not None and round(pagina[0], 2) == 0.32


def test_na_mimaki_a_mesma_arte_ainda_gira(tmp_path):
    origem = tmp_path / "LONA.pdf"
    _pdf(origem, 0.32, 0.70)
    destino = tmp_path / "hot" / "LONA.pdf"
    destino.parent.mkdir()
    limite = rl_hf.limite_da_maquina(rl_hf.MAQUINAS["SWJ320A"])

    girou, _ = rl_hf._montar_para_hot_folder(origem, destino, limite, lambda *a: None)

    assert girou is True
