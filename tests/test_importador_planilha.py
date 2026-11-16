"""
Testes unitários para importador_planilha.py (ISSUE-09).
"""

import io
import pathlib
import pytest
import openpyxl

import importador_planilha as imp


def test_detectar_encoding_utf8_e_bom(tmp_path):
    p_utf8 = tmp_path / "utf8.csv"
    p_utf8.write_text("arquivo,qtd,material\narte1.pdf,2,LONA\n", encoding="utf-8")
    assert imp.detectar_encoding(p_utf8) == "utf-8"

    p_bom = tmp_path / "utf8_bom.csv"
    p_bom.write_bytes(b"\xef\xbb\xbfarquivo,qtd,material\narte1.pdf,2,LONA\n")
    assert imp.detectar_encoding(p_bom) == "utf-8-sig"


def test_detectar_encoding_latin1(tmp_path):
    p_latin1 = tmp_path / "latin1.csv"
    # Caractere acentuado exclusivo latin-1
    p_latin1.write_bytes("arquivo;descrição;produção\narte.pdf;adesivo;balcão\n".encode("latin-1"))
    enc = imp.detectar_encoding(p_latin1)
    assert enc in ("latin-1", "cp1252")


def test_detectar_delimitador():
    csv_virgula = "arquivo,quantidade,largura,altura\narte1.pdf,1,100,50\n"
    assert imp.detectar_delimitador(csv_virgula) == ","

    csv_ponto_virgula = "arquivo;quantidade;largura;altura\narte1.pdf;1;100;50\n"
    assert imp.detectar_delimitador(csv_ponto_virgula) == ";"

    csv_tab = "arquivo\tquantidade\tlargura\taltura\narte1.pdf\t1\t100\t50\n"
    assert imp.detectar_delimitador(csv_tab) == "\t"

    csv_pipe = "arquivo|quantidade|largura|altura\narte1.pdf|1|100|50\n"
    assert imp.detectar_delimitador(csv_pipe) == "|"


def test_normalizar_cabecalho():
    assert imp.normalizar_cabecalho("Nome do Arquivo")[0] == "arquivo"
    assert imp.normalizar_cabecalho("ARQUIVO_PDF")[0] == "arquivo"
    assert imp.normalizar_cabecalho("Qtd.")[0] == "quantidade"
    assert imp.normalizar_cabecalho("QUANTIDADE DE CÓPIAS")[0] == "quantidade"
    assert imp.normalizar_cabecalho("Substrato")[0] == "material"
    assert imp.normalizar_cabecalho("Tipo de Material")[0] == "material"
    assert imp.normalizar_cabecalho("Cliente / Empresa")[0] == "cliente"
    assert imp.normalizar_cabecalho("Ordem de Serviço")[0] == "os"
    assert imp.normalizar_cabecalho("Nº Pedido")[0] == "os"
    assert imp.normalizar_cabecalho("Observações")[0] == "descricao"
    assert imp.normalizar_cabecalho("Escala")[0] == "escala"


def test_normalizar_cabecalho_com_unidade():
    campo, unid = imp.normalizar_cabecalho("Largura (cm)")
    assert campo == "largura"
    assert unid == "CM"

    campo, unid = imp.normalizar_cabecalho("Altura [mm]")
    assert campo == "altura"
    assert unid == "MM"

    campo, unid = imp.normalizar_cabecalho("Largura em metros")
    assert campo == "largura"
    assert unid == "M"


def test_converter_valor_numerico():
    val, unid = imp.converter_valor_numerico("120,5")
    assert val == pytest.approx(120.5)
    assert unid is None

    val, unid = imp.converter_valor_numerico("1.250,50")
    assert val == pytest.approx(1250.50)

    val, unid = imp.converter_valor_numerico("120 cm")
    assert val == pytest.approx(120.0)
    assert unid == "CM"

    val, unid = imp.converter_valor_numerico("2.5 m")
    assert val == pytest.approx(2.5)
    assert unid == "M"

    assert imp.converter_valor_numerico(None) == (None, None)
    assert imp.converter_valor_numerico("") == (None, None)
    assert imp.converter_valor_numerico("invalido") == (None, None)


def test_ler_csv_virgula_e_ponto_virgula(tmp_path):
    # CSV com vírgula
    p1 = tmp_path / "planilha1.csv"
    p1.write_text(
        "Arquivo,Qtd,Material,Largura,Altura,Unidade,Cliente,OS\n"
        "banner_promo.pdf,5,LONA,2.00,1.00,M,ACME,1001\n"
        "adesivo_vitrine.pdf,2,ADESIVO,80,120,CM,LOJA XPTO,1002\n",
        encoding="utf-8",
    )
    dados1 = imp.ler_csv(p1)
    assert len(dados1) == 2
    assert dados1[0]["arquivo"] == "banner_promo.pdf"
    assert dados1[0]["quantidade"] == 5
    assert dados1[0]["material"] == "LONA"
    assert dados1[0]["largura_m"] == pytest.approx(2.00)
    assert dados1[0]["altura_m"] == pytest.approx(1.00)
    assert dados1[0]["cliente"] == "ACME"
    assert dados1[0]["os"] == "1001"

    assert dados1[1]["arquivo"] == "adesivo_vitrine.pdf"
    assert dados1[1]["quantidade"] == 2
    assert dados1[1]["unidade"] == "CM"
    assert dados1[1]["largura_m"] == pytest.approx(0.80)
    assert dados1[1]["altura_m"] == pytest.approx(1.20)

    # CSV com ponto e vírgula e formato brasileiro
    p2 = tmp_path / "planilha2.csv"
    p2.write_text(
        "Arquivo;Quantidade;Material;Largura (cm);Altura (cm);Cliente;OS\n"
        "totem.pdf;1;PS;150;200;SHOPPING;555\n",
        encoding="utf-8",
    )
    dados2 = imp.ler_csv(p2)
    assert len(dados2) == 1
    assert dados2[0]["arquivo"] == "totem.pdf"
    assert dados2[0]["largura_m"] == pytest.approx(1.50)
    assert dados2[0]["altura_m"] == pytest.approx(2.00)
    assert dados2[0]["material"] == "PS"


def test_ler_xlsx(tmp_path):
    p_xlsx = tmp_path / "corte.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Corte"
    ws.append(["Nome do Arquivo", "Quantidade", "Material", "Largura (m)", "Altura (m)", "Cliente", "Pedido"])
    ws.append(["painel_fachada.pdf", 3, "LONA 440G", 3.0, 1.5, "Padaria Central", "987"])
    ws.append(["placa_sinal.pdf", 10, "PS 2MM", 0.4, 0.2, "Estacionamento", "988"])
    wb.save(str(p_xlsx))

    dados = imp.ler_xlsx(p_xlsx)
    assert len(dados) == 2
    assert dados[0]["arquivo"] == "painel_fachada.pdf"
    assert dados[0]["quantidade"] == 3
    assert dados[0]["material"] == "LONA 440G"
    assert dados[0]["largura_m"] == pytest.approx(3.0)
    assert dados[0]["altura_m"] == pytest.approx(1.5)
    assert dados[0]["cliente"] == "Padaria Central"
    assert dados[0]["os"] == "987"

    assert dados[1]["arquivo"] == "placa_sinal.pdf"
    assert dados[1]["quantidade"] == 10
    assert dados[1]["material"] == "PS 2MM"
    assert dados[1]["largura_m"] == pytest.approx(0.4)
    assert dados[1]["altura_m"] == pytest.approx(0.2)


def test_ler_planilha_unificada(tmp_path):
    p_csv = tmp_path / "teste.csv"
    p_csv.write_text("arquivo,qtd,material\narte.pdf,1,LONA\n", encoding="utf-8")
    assert len(imp.ler_planilha(p_csv)) == 1

    with pytest.raises(FileNotFoundError):
        imp.ler_planilha(tmp_path / "arquivo_fantasma.xlsx")


def test_cruzar_arquivos_com_planilha():
    linhas_planilha = [
        {
            "arquivo": "banner_promocao.pdf",
            "quantidade": 2,
            "material": "LONA",
            "largura_m": 2.0,
            "altura_m": 1.0,
            "cliente": "MERCADO",
            "os": "101",
        },
        {
            "arquivo": "adesivo_vitrine",  # sem extensão
            "quantidade": 4,
            "material": "ADESIVO",
            "largura_m": 0.5,
            "altura_m": 0.5,
            "cliente": "FARMACIA",
            "os": "102",
        },
        {
            "arquivo": "totem_entrada",
            "quantidade": 1,
            "material": "PS",
            "largura_m": 1.0,
            "altura_m": 1.8,
            "cliente": "EVENTO",
            "os": "103",
        },
    ]

    arquivos = [
        pathlib.Path("banner_promocao.pdf"),                  # Match exato
        pathlib.Path("adesivo_vitrine.pdf"),                  # Match sem extensão
        pathlib.Path("01_totem_entrada_final.pdf"),           # Match substring
        pathlib.Path("arte_avulsa_sem_cadastro.pdf"),         # Não encontrado
    ]

    resultados = imp.cruzar_arquivos_com_planilha(arquivos, linhas_planilha)
    assert len(resultados) == 4

    # 1. Exato
    assert resultados[0].tipo_match == "exato"
    assert resultados[0].confianca == 1.0
    assert resultados[0].linha_planilha["cliente"] == "MERCADO"

    # 2. Sem extensão
    assert resultados[1].tipo_match == "sem_extensao"
    assert resultados[1].confianca == 0.9
    assert resultados[1].linha_planilha["cliente"] == "FARMACIA"

    # 3. Substring
    assert resultados[2].tipo_match == "substring"
    assert resultados[2].confianca == 0.7
    assert resultados[2].linha_planilha["cliente"] == "EVENTO"

    # 4. Não encontrado
    assert resultados[3].tipo_match == "nao_encontrado"
    assert resultados[3].confianca == 0.0
    assert resultados[3].linha_planilha is None
