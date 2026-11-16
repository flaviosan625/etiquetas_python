"""
Suíte de Testes para o módulo parser_regras.py (ISSUE-08).

Testa:
- Conversão de templates declarativos para regex com Named Groups.
- Perfis de fábrica: comunicacao_visual_classico, erp_os, padrao_flexivel.
- Adição de novos perfis por template e por regex pura.
- Prioridade e fallback para PENDENTE_TRIAGEM sem exceções.
- Persistência e exportação/importação via config JSON.
- Integração e retrocompatibilidade com dimensoes.py.
"""
import copy
import json
import pathlib
import pytest

from config import CONFIG_PADRAO
import dimensoes
from parser_regras import (
    ParserRegrasNomes,
    PerfilRegra,
    ResultadoParse,
    converter_template_para_regex,
)


def test_converter_template_tokens_declarativos():
    """Valida conversão de todos os 9 tokens declarativos."""
    template = "{QTD}UN_{MATERIAL}_{ESPESSURA}_{CLIENTE}_OS{OS}_{LARG}x{ALT}{UNIDADE}_{DESCRICAO}"
    regex = converter_template_para_regex(template)

    assert "(?P<qtd>\\d+)" in regex
    assert "(?P<material>.+?)" in regex
    assert "(?P<espessura>" in regex
    assert "(?P<cliente>.+?)" in regex
    assert "(?P<os>[A-Za-z0-9_-]+?)" in regex
    assert "(?P<larg>" in regex
    assert "(?P<alt>" in regex
    assert "(?P<unidade>" in regex
    assert "(?P<descricao>.+?)" in regex


def test_converter_template_case_insensitive_e_opcionais():
    """Valida que tokens em minúsculas e blocos opcionais funcionam."""
    template = "{qtd}un_{material}_{larg}x{alt}{unidade}[_{descricao}]"
    regex = converter_template_para_regex(template)

    assert "(?P<qtd>\\d+)" in regex
    assert "(?P<larg>" in regex
    assert "(?P<alt>" in regex


def test_perfil_comunicacao_visual_classico_nomes_reais():
    """Testa nomes reais clássicos de comunicação visual."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    # 1. Com descrição e marcação de reposição
    res1 = parser.parsear("1UN LONA 2,00X1,00M_c - REPOSICAO.pdf", CONFIG_PADRAO)
    assert res1.sucesso is True
    assert res1.status == "PRONTO"
    assert res1.perfil_usado == "comunicacao_visual_classico"
    assert res1.qtd == 1
    assert pytest.approx(res1.largura_m) == 2.0
    assert pytest.approx(res1.altura_m) == 1.0
    assert res1.unidade_original == "M"
    assert res1.categoria == "LONA"
    assert res1.descricao == "c - REPOSICAO"

    # 2. Com underscore e descrição
    res2 = parser.parsear("1UN_LONA_2,00X1,00M_BANNER.pdf", CONFIG_PADRAO)
    assert res2.sucesso is True
    assert res2.status == "PRONTO"
    assert res2.perfil_usado == "comunicacao_visual_classico"
    assert res2.qtd == 1
    assert pytest.approx(res2.largura_m) == 2.0
    assert pytest.approx(res2.altura_m) == 1.0
    assert res2.descricao == "BANNER"

    # 3. Sem descrição ao final
    res3 = parser.parsear("1UN LONA 2,00X1,00M.pdf", CONFIG_PADRAO)
    assert res3.sucesso is True
    assert res3.status == "PRONTO"
    assert res3.perfil_usado == "comunicacao_visual_classico"
    assert res3.descricao is None
    assert pytest.approx(res3.largura_m) == 2.0
    assert pytest.approx(res3.altura_m) == 1.0

    # 4. Com adesivo e medidas decimais com ponto
    res4 = parser.parsear("2UN ADESIVO 1.50x2.00M_FACHADA.pdf", CONFIG_PADRAO)
    assert res4.sucesso is True
    assert res4.qtd == 2
    assert res4.categoria == "ADESIVO"
    assert pytest.approx(res4.largura_m) == 1.5
    assert pytest.approx(res4.altura_m) == 2.0


def test_perfil_erp_os():
    """Testa nomes no padrão ERP: OS{OS}_{CLIENTE}_{MATERIAL}_{LARG}x{ALT}{UNIDADE}."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    # 1. Caso direto do requisito: OS1234_CLIENTE_MATERIAL_2x1M
    res1 = parser.parsear("OS1234_CLIENTE_MATERIAL_2x1M", CONFIG_PADRAO)
    assert res1.sucesso is True
    assert res1.status == "PRONTO"
    assert res1.perfil_usado == "erp_os"
    assert res1.os == "1234"
    assert res1.cliente == "CLIENTE"
    assert res1.material == "MATERIAL"
    assert pytest.approx(res1.largura_m) == 2.0
    assert pytest.approx(res1.altura_m) == 1.0
    assert res1.unidade_original == "M"

    # 2. Com extensão .pdf
    res2 = parser.parsear("OS1234_CLIENTE_MATERIAL_2x1M.pdf", CONFIG_PADRAO)
    assert res2.sucesso is True
    assert res2.perfil_usado == "erp_os"
    assert res2.os == "1234"
    assert res2.cliente == "CLIENTE"
    assert res2.material == "MATERIAL"
    assert pytest.approx(res2.largura_m) == 2.0
    assert pytest.approx(res2.altura_m) == 1.0

    # 3. Nome de cliente com espaços (ex: PADARIA DO ZE)
    res3 = parser.parsear("OS999_PADARIA DO ZE_LONA_3x1.5M.pdf", CONFIG_PADRAO)
    assert res3.sucesso is True
    assert res3.perfil_usado == "erp_os"
    assert res3.os == "999"
    assert res3.cliente == "PADARIA DO ZE"
    assert res3.material == "LONA"
    assert res3.categoria == "LONA"
    assert pytest.approx(res3.largura_m) == 3.0
    assert pytest.approx(res3.altura_m) == 1.5

    # 4. Medidas em centímetros
    res4 = parser.parsear("OS456_FARMACIA_ADESIVO_50x50CM.pdf", CONFIG_PADRAO)
    assert res4.sucesso is True
    assert res4.os == "456"
    assert res4.cliente == "FARMACIA"
    assert res4.material == "ADESIVO"
    assert res4.categoria == "ADESIVO"
    assert pytest.approx(res4.largura_m) == 0.5
    assert pytest.approx(res4.altura_m) == 0.5
    assert res4.unidade_original == "CM"


def test_perfil_padrao_flexivel_fallback():
    """Testa fallback para padrão flexível com arquivos legados e variados."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    # 1. Medida solta sem UN e sem OS
    res1 = parser.parsear("banner_58x60.pdf", CONFIG_PADRAO)
    assert res1.sucesso is True
    assert res1.status == "PRONTO"
    assert res1.perfil_usado == "padrao_flexivel"
    assert pytest.approx(res1.largura_m) == 0.58
    assert pytest.approx(res1.altura_m) == 0.60
    assert res1.unidade_original == "CM"

    # 2. Medida em metros com vírgula
    res2 = parser.parsear("placa_1,5x2M.pdf", CONFIG_PADRAO)
    assert res2.sucesso is True
    assert res2.perfil_usado == "padrao_flexivel"
    assert pytest.approx(res2.largura_m) == 1.5
    assert pytest.approx(res2.altura_m) == 2.0
    assert res2.unidade_original == "M"

    # 3. Arte de agência externa: quantidade por extenso no final
    res3 = parser.parsear("AF_Banner 50x250_Lona_8 Unidades.tif", CONFIG_PADRAO)
    assert res3.sucesso is True
    assert res3.qtd == 8
    assert res3.categoria == "LONA"
    assert pytest.approx(res3.largura_m) == 0.50
    assert pytest.approx(res3.altura_m) == 2.50
    assert res3.perfil_usado == "padrao_flexivel"

    # 4. Chapa de PVC com variante (sem prefixo UN, cai no flexivel)
    res4 = parser.parsear("PVC 10MM RECORTE_PRETO 100x50CM.pdf", CONFIG_PADRAO)
    assert res4.sucesso is True
    assert res4.categoria == "PVC"
    assert res4.variante == {"espessura": "10MM", "cor": "PRETO"}
    assert pytest.approx(res4.largura_m) == 1.0
    assert pytest.approx(res4.altura_m) == 0.5
    assert res4.perfil_usado == "padrao_flexivel"


def test_status_pendente_triagem_quando_sem_medida():
    """Testa que arquivos sem medidas vão para triagem sem disparar exceção."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    arquivos_sem_medida = [
        "arte_final_cliente.pdf",
        "logo_vetorizado.eps",
        "",
        "   ",
        "1UN LONA SEM_MEDIDA.pdf",
        "1UN LONA 0x0CM.pdf",
    ]

    for nome in arquivos_sem_medida:
        res = parser.parsear(nome, CONFIG_PADRAO)
        assert res.sucesso is False
        assert res.status == "PENDENTE_TRIAGEM"
        assert res.largura_m is None
        assert res.altura_m is None
        assert res.perfil_usado is None


def test_adicionar_novo_perfil_por_template():
    """Testa adição de perfil customizado via template declarativo."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    parser.adicionar_perfil_template(
        nome="ecommerce_shopee",
        template="{CLIENTE}_{MATERIAL}_{LARG}x{ALT}{UNIDADE}",
        prioridade=15,
        descricao="Arquivos vindos da integração Shopee",
    )

    res = parser.parsear("SHOPEE_ADESIVO_30x30CM.pdf", CONFIG_PADRAO)
    assert res.sucesso is True
    assert res.status == "PRONTO"
    assert res.perfil_usado == "ecommerce_shopee"
    assert res.cliente == "SHOPEE"
    assert res.material == "ADESIVO"
    assert res.categoria == "ADESIVO"
    assert pytest.approx(res.largura_m) == 0.3
    assert pytest.approx(res.altura_m) == 0.3
    assert res.unidade_original == "CM"


def test_adicionar_novo_perfil_por_regex_pura():
    """Testa adição de perfil customizado via Regex pura."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    parser.adicionar_perfil_regex(
        nome="legado_erp_cod",
        regex=r"^COD-(?P<os>\d+)_(?P<larg>\d+)X(?P<alt>\d+)(?P<unidade>MM|CM|M)?",
        prioridade=5,
        descricao="Sistema legado com prefixo COD-",
    )

    res = parser.parsear("COD-7788_1000X2000MM.pdf", CONFIG_PADRAO)
    assert res.sucesso is True
    assert res.status == "PRONTO"
    assert res.perfil_usado == "legado_erp_cod"
    assert res.os == "7788"
    assert pytest.approx(res.largura_m) == 1.0
    assert pytest.approx(res.altura_m) == 2.0
    assert res.unidade_original == "MM"


def test_prioridade_entre_perfis():
    """Valida que o perfil com menor número de prioridade é avaliado primeiro."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    # Ambos casam com o padrão OS\d+_CLIENTE_...
    parser.adicionar_perfil_template(
        nome="perfil_prioritario",
        template="OS{OS}_{CLIENTE}_{MATERIAL}_{LARG}x{ALT}{UNIDADE}",
        prioridade=5,
    )
    # erp_os tem prioridade 20

    res = parser.parsear("OS100_LOJA_LONA_1x1M.pdf", CONFIG_PADRAO)
    assert res.perfil_usado == "perfil_prioritario"


def test_persistencia_regras_config_json(tmp_path):
    """Testa exportação, serialização em JSON e importação de regras."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)
    parser.adicionar_perfil_template(
        nome="novo_perfil_teste",
        template="{CLIENTE}_{LARG}x{ALT}{UNIDADE}",
        prioridade=25,
    )

    regras_exportadas = parser.exportar_regras()
    assert any(r["nome"] == "novo_perfil_teste" for r in regras_exportadas)

    # Simular salvamento e carregamento via JSON
    arquivo_json = tmp_path / "config_teste.json"
    dados_config = copy.deepcopy(CONFIG_PADRAO)
    dados_config["perfis_nomenclatura"] = regras_exportadas

    with open(arquivo_json, "w", encoding="utf-8") as f:
        json.dump(dados_config, f, indent=2)

    with open(arquivo_json, "r", encoding="utf-8") as f:
        dados_recarregados = json.load(f)

    parser_novo = ParserRegrasNomes(config=dados_recarregados)
    perfil = parser_novo.obter_perfil("novo_perfil_teste")
    assert perfil is not None
    assert perfil.prioridade == 25
    assert perfil.template == "{CLIENTE}_{LARG}x{ALT}{UNIDADE}"

    # Testar parse com o perfil recarregado
    res = parser_novo.parsear("MERCADO_50x50CM.pdf", dados_recarregados)
    assert res.sucesso is True
    assert res.perfil_usado == "novo_perfil_teste"
    assert res.cliente == "MERCADO"


def test_integracao_dimensoes_parsear_nome_arquivo():
    """Testa a função integrada dimensoes.parsear_nome_arquivo()."""
    # 1. Arquivo ERP
    res1 = dimensoes.parsear_nome_arquivo("OS1234_CLIENTE_MATERIAL_2x1M")
    assert isinstance(res1, ResultadoParse)
    assert res1.sucesso is True
    assert res1.status == "PRONTO"
    assert res1.perfil_usado == "erp_os"
    assert res1.os == "1234"

    # 2. Arquivo clássico
    res2 = dimensoes.parsear_nome_arquivo("1UN LONA 2,00X1,00M_c - REPOSICAO.pdf")
    assert res2.sucesso is True
    assert res2.perfil_usado == "comunicacao_visual_classico"

    # 3. Arquivo sem medidas
    res3 = dimensoes.parsear_nome_arquivo("arte_sem_medida.pdf")
    assert res3.sucesso is False
    assert res3.status == "PENDENTE_TRIAGEM"


def test_resolucao_sinonimo_e_variante_no_parse():
    """Verifica resolução de sinônimos (ex: VINIL -> ADESIVO) e variantes."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    # VINIL é sinônimo de ADESIVO
    res = parser.parsear("1UN_VINIL_100x200CM.pdf", CONFIG_PADRAO)
    assert res.sucesso is True
    assert res.material == "VINIL"
    assert res.categoria == "ADESIVO"
    assert pytest.approx(res.largura_m) == 1.0
    assert pytest.approx(res.altura_m) == 2.0


def test_resultado_parse_helpers():
    """Testa métodos auxiliares de ResultadoParse."""
    res = ResultadoParse(
        sucesso=True,
        qtd=3,
        largura_m=1.2,
        altura_m=2.0,
        unidade_original="M",
        material="LONA",
        categoria="LONA",
        cliente="ACME",
        os="100",
        perfil_usado="erp_os",
        status="PRONTO",
    )

    assert pytest.approx(res.area_m2) == 2.4
    d = res.to_dict()
    assert d["cliente"] == "ACME"
    assert d["area_m2"] == 2.4

    dim_d = res.as_dimensao_dict()
    assert dim_d is not None
    assert dim_d["largura_m"] == 1.2
    assert dim_d["altura_m"] == 2.0
    assert dim_d["origem"] == "nome"


def test_remover_e_desativar_perfil():
    """Testa desativação e remoção de perfis."""
    parser = ParserRegrasNomes(config=CONFIG_PADRAO)

    p_erp = parser.obter_perfil("erp_os")
    assert p_erp is not None
    p_erp.ativo = False

    # Com erp_os desativado, arquivo tipo OS1234_CLIENTE_MATERIAL_2x1M cai no padrao_flexivel
    res = parser.parsear("OS1234_CLIENTE_MATERIAL_2x1M", CONFIG_PADRAO)
    assert res.sucesso is True
    assert res.perfil_usado == "padrao_flexivel"

    # Remover o perfil
    assert parser.remover_perfil("erp_os") is True
    assert parser.obter_perfil("erp_os") is None
