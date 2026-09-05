import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest
import pymupdf

import relatorio_producao as rp


@pytest.fixture(autouse=True)
def _isolar_pasta_relatorios(tmp_path, monkeypatch):
    """
    Rede de segurança: rp.PASTA_RELATORIOS é o OneDrive real, e um teste
    que esqueça de passar 'pasta_relatorios' escreveria (ou leria) em
    produção. Ver a mesma proteção em test_rasterlink_hotfolder.py.
    """
    monkeypatch.setattr(rp, "PASTA_RELATORIOS", tmp_path / "_relatorios_isolados")


MAQUINAS_TESTE = {
    "UJV 100 UNY CV": {"hot_folder": r"C:\nao_usado", "largura_util_m": 1.48},
    "SWJ320A": {"hot_folder": r"C:\nao_usado", "largura_util_m": 3.20},
}


def _escrever_registro(pasta, linhas, ano_mes="2026-09"):
    destino = pasta / rp.NOME_SUBPASTA_REGISTRO
    destino.mkdir(parents=True, exist_ok=True)
    with open(destino / f"{ano_mes}.jsonl", "w", encoding="utf-8") as f:
        for linha in linhas:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return pasta


def _envio(quando, maquina, arquivo, bytes_=1000, girado=False):
    return {"quando": quando, "maquina": maquina, "arquivo": arquivo, "bytes": bytes_, "girado": girado}


def test_ler_registros_do_dia_pega_so_o_dia_pedido(tmp_path):
    _escrever_registro(tmp_path, [
        _envio("2026-09-02T14:27:00", "SWJ320A", "a.pdf"),
        _envio("2026-09-03T14:04:00", "SWJ320A", "b.pdf"),
        _envio("2026-09-03T23:41:00", "SWJ320A", "c.pdf"),
    ])

    registros = rp.ler_registros_do_dia(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path)

    assert [r["arquivo"] for r in registros] == ["b.pdf", "c.pdf"]


def test_ler_registros_ordena_por_horario_mesmo_gravado_fora_de_ordem(tmp_path):
    _escrever_registro(tmp_path, [
        _envio("2026-09-03T23:41:00", "SWJ320A", "tarde.pdf"),
        _envio("2026-09-03T08:10:00", "SWJ320A", "cedo.pdf"),
    ])

    registros = rp.ler_registros_do_dia(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path)

    assert [r["arquivo"] for r in registros] == ["cedo.pdf", "tarde.pdf"]


def test_ler_registros_pula_linha_corrompida_sem_derrubar_o_resto(tmp_path):
    destino = tmp_path / rp.NOME_SUBPASTA_REGISTRO
    destino.mkdir(parents=True)
    with open(destino / "2026-09.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(_envio("2026-09-03T10:00:00", "SWJ320A", "boa.pdf")) + "\n")
        f.write('{"quando": "2026-09-03T11:00:00", "maquina": "SWJ\n')  # escrita cortada no meio
        f.write(json.dumps(_envio("2026-09-03T12:00:00", "SWJ320A", "outra_boa.pdf")) + "\n")

    registros = rp.ler_registros_do_dia(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path)

    assert [r["arquivo"] for r in registros] == ["boa.pdf", "outra_boa.pdf"]


def test_ler_registros_sem_arquivo_nenhum_devolve_vazio(tmp_path):
    assert rp.ler_registros_do_dia(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path) == []


def test_interpretar_le_quantidade_material_e_m2_do_nome(tmp_path):
    registros = [
        {"quando": "2026-09-03T14:04:00", "maquina": "SWJ320A", "bytes": 100, "girado": False,
         "arquivo": "1UN LONA IMPRESSA 3.16X8.48M_testeiras.pdf", "_quando": datetime.datetime(2026, 9, 3, 14, 4)},
    ]

    por_maquina = rp.interpretar(registros, maquinas=MAQUINAS_TESTE)

    linha = por_maquina["SWJ320A"][0]
    assert linha["quantidade"] == 1
    assert linha["categoria"] == "LONA"
    assert round(linha["area_m2"], 2) == 26.80


def test_interpretar_multiplica_area_pela_quantidade(tmp_path):
    registros = [
        {"quando": "2026-09-03T23:41:00", "maquina": "SWJ320A", "bytes": 100, "girado": False,
         "arquivo": "AF_Colunas_220x300+sangria_lona_2 Unidades.tif", "_quando": datetime.datetime(2026, 9, 3, 23, 41)},
    ]

    linha = rp.interpretar(registros, maquinas=MAQUINAS_TESTE)["SWJ320A"][0]

    assert linha["quantidade"] == 2
    assert round(linha["area_m2"], 2) == 13.20, "2,20x3,00m vezes 2 unidades"


def test_interpretar_marca_arquivo_repetido_mas_mantem_a_area(tmp_path):
    """
    Regra do usuário (2026-09-05): repetiu por refação (material
    danificou na instalação) ou porque o cliente salvou a arte corrigida
    por cima do mesmo nome. Nos dois casos consumiu material de verdade
    — então CONTA, só precisa ficar sinalizado.
    """
    nome = "1UN LONA IMPRESSA 3.16X8.48M_testeiras.pdf"
    registros = [
        {"quando": "x", "maquina": "SWJ320A", "arquivo": nome, "bytes": 1, "girado": False,
         "_quando": datetime.datetime(2026, 9, 3, 14, 4)},
        {"quando": "x", "maquina": "SWJ320A", "arquivo": nome, "bytes": 1, "girado": False,
         "_quando": datetime.datetime(2026, 9, 3, 14, 4)},
    ]

    linhas = rp.interpretar(registros, maquinas=MAQUINAS_TESTE)["SWJ320A"]

    assert linhas[0]["repeticao"] == 1
    assert linhas[1]["repeticao"] == 2
    assert linhas[1]["area_m2"] == linhas[0]["area_m2"], "repetição nunca zera a área"
    assert round(sum(l["area_m2"] for l in linhas), 2) == 53.59


def test_interpretar_sinaliza_arquivo_que_nao_cabe_na_maquina(tmp_path):
    """Caso real de 03/09: guarda-corpo de 10,00x2,20m foi pra UJV 100, que tem 1,48m úteis."""
    registros = [
        {"quando": "x", "maquina": "UJV 100 UNY CV", "bytes": 1, "girado": False,
         "arquivo": "AF_guardacorpo_1000x220+sangria_lona_2 Unidades.tif",
         "_quando": datetime.datetime(2026, 9, 3, 23, 51)},
    ]

    linha = rp.interpretar(registros, maquinas=MAQUINAS_TESTE)["UJV 100 UNY CV"][0]

    assert linha["nao_cabe"] is True


def test_interpretar_nao_sinaliza_o_que_cabe(tmp_path):
    registros = [
        {"quando": "x", "maquina": "SWJ320A", "bytes": 1, "girado": False,
         "arquivo": "1UN LONA 3.16X8.48M teste.pdf", "_quando": datetime.datetime(2026, 9, 3, 14, 4)},
    ]

    linha = rp.interpretar(registros, maquinas=MAQUINAS_TESTE)["SWJ320A"][0]

    assert linha["nao_cabe"] is False, "3,16m cabe nos 3,20m uteis da SWJ320A"


def test_subtotais_nunca_juntam_materiais_diferentes():
    linhas = [
        {"categoria": "LONA", "area_m2": 10.0},
        {"categoria": "LONA", "area_m2": 5.0},
        {"categoria": "ADESIVO", "area_m2": 3.0},
    ]

    totais = rp.subtotais_por_material(linhas)

    assert totais == {"LONA": 15.0, "ADESIVO": 3.0}
    assert "TOTAL" not in totais, "nunca existe um total somando materiais diferentes"


def test_subtotais_ignoram_item_sem_medida_lida():
    linhas = [{"categoria": "LONA", "area_m2": 10.0}, {"categoria": "LONA", "area_m2": None}]
    assert rp.subtotais_por_material(linhas) == {"LONA": 10.0}


def test_gerar_pdf_sem_nada_no_dia_nao_emite_documento_em_branco(tmp_path):
    _escrever_registro(tmp_path, [_envio("2026-09-02T10:00:00", "SWJ320A", "a.pdf")])

    assert rp.gerar_pdf(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path, maquinas=MAQUINAS_TESTE) is None


def test_gerar_pdf_do_dia_real_sai_com_o_conteudo_esperado(tmp_path):
    _escrever_registro(tmp_path, [
        _envio("2026-09-03T14:04:12", "SWJ320A", "1UN LONA IMPRESSA 3.16X8.48M_testeiras.pdf", 97562126),
        _envio("2026-09-03T14:04:12", "SWJ320A", "1UN LONA IMPRESSA 3.16X8.48M_testeiras.pdf", 97562126),
        _envio("2026-09-03T23:41:20", "SWJ320A", "AF_Colunas_220x300+sangria_lona_2 Unidades.tif", 1024713764),
        _envio("2026-09-03T23:51:44", "UJV 100 UNY CV", "AF_guardacorpo_1000x220+sangria_lona_2 Unidades.tif", 1830000000),
    ])

    caminho = rp.gerar_pdf(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path, maquinas=MAQUINAS_TESTE)

    assert caminho.name == "2026-09-03.pdf"
    assert caminho.parent.name == "2026", "PDFs agrupados por ano"

    doc = pymupdf.open(str(caminho))
    texto = "\n".join(pagina.get_text() for pagina in doc)
    doc.close()

    assert "Relatório Diário de Produção" in texto
    assert "03/09/2026" in texto
    assert "SWJ320A" in texto and "UJV 100 UNY CV" in texto
    assert "2ª entrada" in texto, "a repetição precisa aparecer sinalizada"
    assert "Não cabe nesta máquina" in texto, "o arquivo grande demais precisa aparecer sinalizado"
    assert "66,80" in texto, "subtotal soma os valores arredondados: 26,80 + 26,80 + 13,20"
    assert "44,00" in texto, "subtotal da UJV 100"


def test_gerar_pdf_fica_leve(tmp_path):
    """
    O usuário aceitou guardar o ano inteiro na pasta com a condição de o
    documento ser leve. insert_htmlbox embute uma fonte por chamada — sem
    o save(garbage=4) isso passa de 1MB fácil.
    """
    _escrever_registro(tmp_path, [
        _envio(f"2026-09-03T{h:02d}:{m:02d}:00", "SWJ320A", f"1UN LONA 2.00X3.00M item {h}-{m}.pdf")
        for h in range(9, 19) for m in (0, 20, 40)
    ])

    caminho = rp.gerar_pdf(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path, maquinas=MAQUINAS_TESTE)

    tamanho_kb = caminho.stat().st_size / 1024
    assert tamanho_kb < 300, f"30 envios geraram {tamanho_kb:.0f}KB — fonte duplicando?"


def test_gerar_pendentes_cobre_os_dias_recentes_com_envio(tmp_path):
    _escrever_registro(tmp_path, [
        _envio("2026-09-03T10:00:00", "SWJ320A", "1UN LONA 2.00X3.00M a.pdf"),
        _envio("2026-09-05T10:00:00", "SWJ320A", "1UN LONA 2.00X3.00M b.pdf"),
    ])

    gerados = rp.gerar_pendentes(
        dias_para_tras=3, hoje=datetime.date(2026, 9, 5),
        pasta_relatorios=tmp_path, maquinas=MAQUINAS_TESTE,
    )

    assert sorted(c.name for c in gerados) == ["2026-09-03.pdf", "2026-09-05.pdf"]


def test_gerar_pendentes_recupera_dia_perdido_com_pc_desligado(tmp_path):
    """Se ninguém rodou ontem, a rodada de hoje precisa emitir o de ontem também."""
    _escrever_registro(tmp_path, [_envio("2026-09-04T10:00:00", "SWJ320A", "1UN LONA 2.00X3.00M a.pdf")])

    gerados = rp.gerar_pendentes(
        dias_para_tras=3, hoje=datetime.date(2026, 9, 5),
        pasta_relatorios=tmp_path, maquinas=MAQUINAS_TESTE,
    )

    assert [c.name for c in gerados] == ["2026-09-04.pdf"]


def test_gerar_pendentes_sem_envio_nenhum_nao_cria_nada(tmp_path):
    gerados = rp.gerar_pendentes(
        hoje=datetime.date(2026, 9, 5), pasta_relatorios=tmp_path, maquinas=MAQUINAS_TESTE,
    )

    assert gerados == []
    assert not (tmp_path / "2026").exists()


def test_regerar_o_mesmo_dia_inclui_envio_que_chegou_depois(tmp_path):
    """
    Regerar precisa ser seguro: o registro só cresce por acréscimo, então
    o documento novo tem tudo do antigo mais o que faltava.
    """
    _escrever_registro(tmp_path, [_envio("2026-09-03T10:00:00", "SWJ320A", "1UN LONA 2.00X3.00M a.pdf")])
    primeiro = rp.gerar_pdf(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path, maquinas=MAQUINAS_TESTE)
    doc = pymupdf.open(str(primeiro))
    texto_antes = "\n".join(p.get_text() for p in doc)
    doc.close()
    assert "b.pdf" not in texto_antes

    with open(tmp_path / rp.NOME_SUBPASTA_REGISTRO / "2026-09.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(_envio("2026-09-03T18:00:00", "SWJ320A", "1UN LONA 2.00X3.00M b.pdf")) + "\n")

    segundo = rp.gerar_pdf(datetime.date(2026, 9, 3), pasta_relatorios=tmp_path, maquinas=MAQUINAS_TESTE)
    doc = pymupdf.open(str(segundo))
    texto_depois = "\n".join(p.get_text() for p in doc)
    doc.close()

    assert segundo == primeiro, "regera no mesmo arquivo, nao cria um segundo"
    assert "a.pdf" in texto_depois and "b.pdf" in texto_depois


def test_tamanho_legivel_nunca_mostra_zero_para_arquivo_pequeno():
    """'0 MB' num documento de comprovacao parece dado faltando."""
    assert rp._tamanho_legivel(1120) == "1 KB"
    assert rp._tamanho_legivel(500) == "500 B"
    assert rp._tamanho_legivel(97562126) == "93 MB"
    assert rp._tamanho_legivel(1830042484) == "1,7 GB"
    assert rp._tamanho_legivel(None) == "—"


def test_dias_com_registro_lista_os_dias_do_mes(tmp_path):
    _escrever_registro(tmp_path, [
        _envio("2026-09-02T10:00:00", "SWJ320A", "a.pdf"),
        _envio("2026-09-03T10:00:00", "SWJ320A", "b.pdf"),
        _envio("2026-09-03T11:00:00", "SWJ320A", "c.pdf"),
    ])

    dias = rp.dias_com_registro(datetime.date(2026, 9, 1), pasta_relatorios=tmp_path)

    assert dias == [datetime.date(2026, 9, 2), datetime.date(2026, 9, 3)]
