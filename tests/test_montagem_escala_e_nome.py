import pathlib
import pytest
import pymupdf

import montagem
from config import carregar_config


PT_M = 72 / 0.0254


def _pdf_simples(pasta, nome, largura_m, altura_m):
    """Cria um PDF de teste com retângulo de conteúdo vetorial medido em PT_M."""
    p = pathlib.Path(pasta) / nome
    doc = pymupdf.open()
    pagina = doc.new_page(width=largura_m * PT_M, height=altura_m * PT_M)
    pagina.draw_rect(pagina.rect, color=(0, 0, 0), fill=(0.2, 0.4, 0.8))
    doc.save(str(p))
    doc.close()
    return p


def test_arquivo_sem_medida_no_nome_e_recusado_com_aviso_obrigatorio(tmp_path):
    """
    Se o usuário jogar na pasta direto para montar sem tamanho no nome do arquivo:
    NÃO ACEITAR e sinalizar que o tamanho do arquivo é obrigatório para
    redimensionamento 1:10 e validação.
    """
    _pdf_simples(tmp_path, "LONA_CLIENTE_SEM_MEDIDA.pdf", 3.00, 1.00)
    pecas, recusadas = montagem.pecas_da_pasta(tmp_path)

    assert len(pecas) == 0
    assert len(recusadas) == 1
    motivo = recusadas[0]["motivo"]
    assert "Tamanho no nome do arquivo é obrigatório para validação e redimensionamento 1:10" in motivo
    assert "o nome não traz medida" in motivo


def test_arquivo_em_escala_1_para_10_e_detectado_e_redimensionado(tmp_path):
    """
    Arquivo com arte em escala 1:10 (ex: 0,60 x 0,30 m no PDF para nome 6,00 x 3,00 m):
    Deve ser identificado como 1:10, redimensionado para 6x3m e avisado na prévia.
    """
    _pdf_simples(tmp_path, "1UN LONA 6.00X3.00M_CLIENTE_FACHADA.pdf", 0.60, 0.30)
    pecas, recusadas = montagem.pecas_da_pasta(tmp_path)

    assert not recusadas
    assert len(pecas) == 1
    peca = pecas[0]
    assert peca["ajuste"]["escala_1_10"] is True
    assert peca["ajuste"]["fator"] == 10.0
    assert pytest.approx(peca["largura_m"], abs=0.01) == 6.00
    assert pytest.approx(peca["altura_m"], abs=0.01) == 3.00


def test_divergencia_acima_de_1cm_sinaliza_tolerancia_excedida(tmp_path):
    """
    Tolerância de 1 cm (10 mm):
    Se a arte física divergir do nome em mais de 1 cm (ex: nome pede 1,00 m e arte tem 0,97 m -> 30 mm de diferença),
    o sistema deve conferir e avisar expressamente que a tolerância de 1 cm foi excedida.
    """
    # 2.00 x 1.00m no nome, mas PDF tem 2.00 x 0.97m (diferença de 30 mm = 3 cm > 1 cm)
    _pdf_simples(tmp_path, "1UN LONA 2.00X1.00M_PAINEL.pdf", 2.00, 0.97)
    pecas, recusadas = montagem.pecas_da_pasta(tmp_path)

    assert not recusadas
    assert len(pecas) == 1
    peca = pecas[0]
    assert peca["ajuste"]["fora_tolerancia_1cm"] is True
    assert "tolerância de 1 cm" in peca["ajuste"]["motivo"].lower()

    # Na prévia, deve gerar aviso de tolerância de 1 cm excedida
    previa = montagem.prever_pasta(tmp_path, nome_maquina="DOCAN R5200")
    todos_avisos = []
    for folha in previa["folhas"]:
        for item in folha.get("itens", []):
            todos_avisos.extend(item.get("avisos", []))
    todos_avisos.extend(previa.get("avisos", []))

    assert any("tolerância de 1 cm excedida" in a.lower() for a in todos_avisos), \
        f"Aviso de tolerância de 1 cm não encontrado nos avisos: {todos_avisos}"

    # E no resumo da prévia também
    resumo = montagem.resumo_da_previa(previa)
    assert "tolerância de 1 cm excedida" in resumo.lower()


def test_diferenca_dentro_de_1cm_nao_dispara_alerta_de_tolerancia(tmp_path):
    """
    Diferença dentro da tolerância de 1 cm (ex: 5 mm = 0.005 m) é aceita
    sem disparar aviso de tolerância de 1 cm excedida.
    """
    # 2.00 x 1.00m no nome, PDF com 2.00 x 0.995m (diferença de 5 mm <= 10 mm)
    _pdf_simples(tmp_path, "1UN LONA 2.00X1.00M_PAINEL.pdf", 2.00, 0.995)
    pecas, recusadas = montagem.pecas_da_pasta(tmp_path)

    assert not recusadas
    assert len(pecas) == 1
    peca = pecas[0]
    assert peca["ajuste"]["fora_tolerancia_1cm"] is False

    previa = montagem.prever_pasta(tmp_path, nome_maquina="DOCAN R5200")
    assert not any("tolerância de 1 cm excedida" in a.lower() for a in previa.get("avisos", []))


def test_materiais_xps_e_tecido_sao_reconhecidos_e_separados(tmp_path):
    """
    XPS e TECIDO são categorias distintas de materiais.
    XPS é chapa própria (não é mais PVC).
    TECIDO é rolo para wind banner.
    """
    config = carregar_config()
    assert "XPS" in config["materiais"]
    assert config["materiais"]["XPS"]["tipo"] == "chapa"
    assert "TECIDO" in config["materiais"]
    assert config["materiais"]["TECIDO"]["tipo"] == "rolo"
    assert "XPS" not in config.get("sinonimos_categoria", {})

    _pdf_simples(tmp_path, "1UN XPS 1.20X0.80M_LETRAS_CAIXA.pdf", 1.20, 0.80)
    _pdf_simples(tmp_path, "1UN TECIDO 0.70X2.20M_WINDBANNER.pdf", 0.70, 2.20)

    pecas, recusadas = montagem.pecas_da_pasta(tmp_path, config=config)
    assert not recusadas
    assert len(pecas) == 2

    materiais_achados = {p["categoria"] for p in pecas}
    assert materiais_achados == {"XPS", "TECIDO"}
