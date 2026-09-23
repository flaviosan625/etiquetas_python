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


# ---------------------------------------------------------------------
# Medida vinda do ARQUIVO quando o nome nao da conta
#
# Motivo (2026-09-10): o relatorio de 08/09 mostrou a UJV com "medida
# nao lida" em dois arquivos e "0,00 m2" num terceiro — material que
# rodou de verdade aparecendo como producao nenhuma. Regra do usuario:
# "se nao conseguir medida precisa acessar o arquivo e buscar medida da
# arte".
# ---------------------------------------------------------------------

def _arte_em_enviados(pasta_fila, maquina, nome, largura_m, altura_m,
                      margem_m=0.0, paginas=1):
    """
    Grava um PDF em 'Enviados' com a ARTE do tamanho pedido, dentro de
    uma pagina 'margem_m' maior de cada lado — pra provar que o que
    vale e a arte, nao a folha do gabarito.
    """
    pt_por_m = 72 / 0.0254
    destino = pasta_fila / maquina / "Enviados"
    destino.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for _ in range(paginas):
        pagina = doc.new_page(width=(largura_m + 2 * margem_m) * pt_por_m,
                              height=(altura_m + 2 * margem_m) * pt_por_m)
        pagina.draw_rect(
            pymupdf.Rect(margem_m * pt_por_m, margem_m * pt_por_m,
                         (margem_m + largura_m) * pt_por_m,
                         (margem_m + altura_m) * pt_por_m),
            color=None, fill=(0, 0, 0))
    caminho = destino / nome
    doc.save(str(caminho))
    doc.close()
    return caminho


def _uma_linha(tmp_path, registro, pasta_fila):
    por_maquina = rp.interpretar([{**registro, "_quando": datetime.datetime(2026, 9, 8, 12, 0)}],
                                 maquinas=MAQUINAS_TESTE, pasta_fila=pasta_fila)
    return list(por_maquina.values())[0][0]


def test_nome_sem_medida_vai_medir_a_arte_dentro_do_arquivo(tmp_path):
    fila = tmp_path / "fila"
    _arte_em_enviados(fila, "UJV 100 UNY CV", "arquivos emendas_01_montado.pdf",
                      largura_m=1.20, altura_m=1.41, margem_m=0.05)

    linha = _uma_linha(tmp_path, _envio("2026-09-08T18:46:55", "UJV 100 UNY CV",
                                        "arquivos emendas_01_montado.pdf"), fila)

    assert linha["origem_medida"] == "arte"
    assert round(linha["dimensao"]["largura_m"], 2) == 1.20, "tem que medir a ARTE, nao a folha"
    assert round(linha["dimensao"]["altura_m"], 2) == 1.41
    assert round(linha["area_m2"], 2) == round(1.20 * 1.41, 2)


def test_medida_impossivel_no_nome_e_trocada_pela_arte_medida(tmp_path):
    """'0.77X0.15CM' seria 7,7mm x 1,5mm — nenhuma maquina daqui faz isso."""
    fila = tmp_path / "fila"
    nome = "Adesivo_pantone + GABARITO 0.77X0.15CM_logo tv_.pdf"
    _arte_em_enviados(fila, "UJV 100 UNY CV", nome, largura_m=1.22, altura_m=0.59)

    linha = _uma_linha(tmp_path, _envio("2026-09-08T12:37:05", "UJV 100 UNY CV", nome), fila)

    assert linha["origem_medida"] == "arte"
    assert round(linha["area_m2"], 2) == round(1.22 * 0.59, 2), "0,00 m2 nao pode sair no relatorio"


def test_nome_que_escreveu_metro_e_digitou_cm_e_lido_em_metros(tmp_path):
    """A lona 5,65x1,80 M com 'cm' no fim do nome (09/09/2026)."""
    fila = tmp_path / "fila"
    nome = "1 UN LONA IMPRESSA COM ILHOS  5,65X1,80cm.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=5.65, altura_m=1.80)

    linha = _uma_linha(tmp_path, _envio("2026-09-09T17:15:34", "SWJ320A", nome), fila)

    assert linha["origem_medida"] == "nome_em_metros"
    assert round(linha["area_m2"], 2) == round(5.65 * 1.80, 2)


def test_centimetro_de_verdade_continua_sendo_centimetro(tmp_path):
    """
    '60X20cm' e 60 por 20 centimetros mesmo, e a arte no arquivo e uma
    folha encaixada de 1x1m. Sem a prova dos 100x, nao se mexe na
    medida do nome — senao um adesivo de 0,12 m2 viraria 12 m2.
    """
    fila = tmp_path / "fila"
    nome = "6 UN ADESIVO VINIL DE RECORTE IMPRESSO 60X20cm.pdf"
    _arte_em_enviados(fila, "UJV 100 UNY CV", nome, largura_m=0.95, altura_m=0.96)

    linha = _uma_linha(tmp_path, _envio("2026-09-09T19:18:00", "UJV 100 UNY CV", nome), fila)

    assert linha["origem_medida"] == "nome"
    assert round(linha["area_m2"], 2) == round(0.60 * 0.20 * 6, 2)


def test_sem_o_arquivo_usa_a_medida_da_folha_anotada_no_envio(tmp_path):
    """Relatorio refeito depois dos 15 dias: o arquivo ja nao existe."""
    registro = _envio("2026-09-08T18:46:55", "UJV 100 UNY CV", "sumiu_dos_15_dias.pdf")
    registro["pagina_m"] = [1.20, 1.45]
    registro["paginas"] = 2

    linha = _uma_linha(tmp_path, registro, tmp_path / "fila_vazia")

    assert linha["origem_medida"] == "folha"
    assert round(linha["area_m2"], 2) == round(1.20 * 1.45 * 2, 2), "2 paginas gastam 2x o material"


def test_material_sem_nome_ganha_subtotal_proprio_em_vez_de_sumir(tmp_path):
    fila = tmp_path / "fila"
    _arte_em_enviados(fila, "UJV 100 UNY CV", "arquivos emendas_01_montado.pdf",
                      largura_m=1.20, altura_m=1.41)

    linha = _uma_linha(tmp_path, _envio("2026-09-08T18:46:55", "UJV 100 UNY CV",
                                        "arquivos emendas_01_montado.pdf"), fila)
    subtotais = rp.subtotais_por_material([linha])

    assert rp.MATERIAL_SEM_NOME in subtotais, "m2 real nao pode sumir do rodape por falta de material"
    assert not linha["categoria"]


# --- nome que perdeu a virgula ("320M" por 3,20 m) -------------------
# 18 e 22/09/2026: 8 arquivos assim entraram na recuperacao do registro.
# Lidos ao pe da letra, uma lona de 26,5 m2 virava 2.649 m2 no relatorio.

def test_nome_sem_virgula_e_corrigido_com_a_arte(tmp_path):
    fila = tmp_path / "fila"
    nome = "1UN LONA IMPRESSA 8.28X320M_MLXP26_CRED_PREMIUM.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=8.28, altura_m=3.20)

    linha = _uma_linha(tmp_path, _envio("2026-09-18T10:00:00", "SWJ320A", nome), fila)

    assert linha["origem_medida"] == "nome_sem_virgula"
    assert round(linha["area_m2"], 2) == round(8.28 * 3.20, 2)


def test_so_o_lado_errado_e_corrigido(tmp_path):
    """Em '8.28X320M' o 8,28 ja estava certo: cada lado e conferido sozinho."""
    fila = tmp_path / "fila"
    nome = "1UN LONA IMPRESSA 8.28X320M_x.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=8.28, altura_m=3.20)

    linha = _uma_linha(tmp_path, _envio("2026-09-18T10:00:00", "SWJ320A", nome), fila)

    assert round(linha["dimensao"]["largura_m"], 2) == 8.28
    assert round(linha["dimensao"]["altura_m"], 2) == 3.20


def test_arte_girada_em_relacao_ao_nome_tambem_serve_de_prova(tmp_path):
    fila = tmp_path / "fila"
    nome = "1UN LONA IMPRESSA 8.28X320M_y.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=3.20, altura_m=8.28)

    linha = _uma_linha(tmp_path, _envio("2026-09-18T10:00:00", "SWJ320A", nome), fila)

    assert linha["origem_medida"] == "nome_sem_virgula"
    assert round(linha["area_m2"], 2) == round(8.28 * 3.20, 2)


def test_quantidade_continua_multiplicando_depois_da_correcao(tmp_path):
    """A medida foi corrigida, mas continua sendo medida do NOME: 3 pecas sao 3."""
    fila = tmp_path / "fila"
    nome = "3UN LONA IMPRESSA 0.80X320M_MLXP26_AREA_PREMIUM_L03.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=0.80, altura_m=3.20)

    linha = _uma_linha(tmp_path, _envio("2026-09-18T10:00:00", "SWJ320A", nome), fila)

    assert linha["quantidade"] == 3
    assert round(linha["area_m2"], 2) == round(0.80 * 3.20 * 3, 2)


def test_sem_prova_no_arquivo_o_nome_fica_como_esta(tmp_path):
    """Onde a virgula 'devia' estar nao se adivinha: sem os 100x, nao mexe."""
    fila = tmp_path / "fila"
    nome = "1UN LONA IMPRESSA 120X3.08M_z.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=4.00, altura_m=3.00)

    linha = _uma_linha(tmp_path, _envio("2026-09-22T10:00:00", "SWJ320A", nome), fila)

    assert linha["origem_medida"] != "nome_sem_virgula"
    assert round(linha["area_m2"], 2) == round(120 * 3.08, 2)


def test_folha_anotada_no_envio_serve_quando_o_arquivo_ja_sumiu(tmp_path):
    """Passados os 15 dias de guarda nao ha arquivo pra abrir — sobra a folha."""
    fila = tmp_path / "fila"
    nome = "1UN LONA IMPRESSA 1.30X320M_sem_arquivo.pdf"
    registro = {**_envio("2026-09-18T10:00:00", "SWJ320A", nome),
                "pagina_m": [1.30, 3.20], "paginas": 1}

    linha = _uma_linha(tmp_path, registro, fila)

    assert linha["origem_medida"] == "nome_sem_virgula"
    assert round(linha["area_m2"], 2) == round(1.30 * 3.20, 2)


def test_peca_longa_de_verdade_nao_e_mexida(tmp_path):
    """28 m e comprimento de lona normal aqui: abaixo do limite, nem confere."""
    fila = tmp_path / "fila"
    nome = "1UN LONA IMPRESSA 28.27X3.20M_MLXP26_CRED_GERAL_L04.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=28.27, altura_m=3.20)

    linha = _uma_linha(tmp_path, _envio("2026-09-11T10:00:00", "SWJ320A", nome), fila)

    assert round(linha["area_m2"], 2) == round(28.27 * 3.20, 2)
    assert linha["origem_medida"] != "nome_sem_virgula"


def test_linha_recuperada_sai_assinalada_no_relatorio(tmp_path):
    """Entrega provada pelo arquivo, horario e giro deduzidos: tem que dizer."""
    registro = {**_envio("2026-09-18T10:30:00", "SWJ320A", "sumiu.pdf"),
                "recuperado": "hora = data do arquivo em Enviados; giro previsto."}

    linha = _uma_linha(tmp_path, registro, tmp_path / "fila")

    assert linha["recuperado"]


def test_linha_normal_nao_tem_marca_de_recuperada(tmp_path):
    linha = _uma_linha(tmp_path, _envio("2026-09-18T10:30:00", "SWJ320A", "normal.pdf"),
                       tmp_path / "fila")

    assert linha["recuperado"] is None


# --- previa da arte em cada linha (pedido de 23/09/2026) -------------

def test_relatorio_leva_a_arte_de_cada_linha(tmp_path):
    """Somos uma grafica: o documento mostra a arte, nao so o nome dela."""
    fila = tmp_path / "fila"
    nome = "1UN LONA IMPRESSA 2.00X1.00M_peca.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=2.00, altura_m=1.00)
    _escrever_registro(tmp_path, [_envio("2026-09-18T10:00:00", "SWJ320A", nome)])

    caminho = rp.gerar_pdf(datetime.date(2026, 9, 18), pasta_relatorios=tmp_path,
                           maquinas=MAQUINAS_TESTE, pasta_fila=fila)

    doc = pymupdf.open(str(caminho))
    try:
        assert doc.load_page(0).get_images(), "a pagina tem que ter a previa da arte"
    finally:
        doc.close()


def test_a_previa_fica_guardada_pra_quando_o_arquivo_sumir(tmp_path):
    """
    O arquivo so fica 15 dias em Enviados e o relatorio e refeito a
    qualquer momento — sem guardar, o relatorio velho voltaria sem arte.
    """
    fila = tmp_path / "fila"
    nome = "1UN LONA IMPRESSA 2.00X1.00M_peca.pdf"
    _arte_em_enviados(fila, "SWJ320A", nome, largura_m=2.00, altura_m=1.00)
    _escrever_registro(tmp_path, [_envio("2026-09-18T10:00:00", "SWJ320A", nome)])
    dia = datetime.date(2026, 9, 18)

    primeira = rp.previa_da_arte("SWJ320A", nome, dia, tmp_path, fila)
    (fila / "SWJ320A" / "Enviados" / nome).unlink()
    depois = rp.previa_da_arte("SWJ320A", nome, dia, tmp_path, fila)

    assert primeira and depois == primeira


def test_linha_sem_arte_nao_impede_o_relatorio(tmp_path):
    """Arte ja apagada, EPS ou arquivo quebrado: sai o quadrado cinza."""
    _escrever_registro(tmp_path, [_envio("2026-09-18T10:00:00", "SWJ320A", "sumido.pdf")])

    caminho = rp.gerar_pdf(datetime.date(2026, 9, 18), pasta_relatorios=tmp_path,
                           maquinas=MAQUINAS_TESTE, pasta_fila=tmp_path / "vazia")

    assert caminho and caminho.is_file()


def test_a_letra_do_relatorio_nao_encolhe_pra_caber(tmp_path):
    """
    insert_htmlbox encolhe a letra calado quando nao cabe. Com a previa
    as linhas ficaram mais altas: se a conta de altura errar, o relatorio
    sai ilegivel sem ninguem perceber.
    """
    fila = tmp_path / "fila"
    linhas = []
    for i in range(40):
        nome = f"1UN LONA IMPRESSA 2.00X1.00M_peca_{i:02d}.pdf"
        _arte_em_enviados(fila, "SWJ320A", nome, largura_m=2.00, altura_m=1.00)
        linhas.append(_envio(f"2026-09-18T10:{i:02d}:00", "SWJ320A", nome))
    _escrever_registro(tmp_path, linhas)

    registros = rp.ler_registros_do_dia(datetime.date(2026, 9, 18), pasta_relatorios=tmp_path)
    por_maquina = rp.interpretar(registros, maquinas=MAQUINAS_TESTE, pasta_fila=fila)
    for nome_maquina, itens in por_maquina.items():
        for item in itens:
            item["previa"] = rp.previa_da_arte(nome_maquina, item["arquivo"],
                                               datetime.date(2026, 9, 18), tmp_path, fila)
    folha = rp._Folha(datetime.date(2026, 9, 18))
    for item in list(por_maquina.values())[0]:
        folha.bloco(52, f'<div>{item["arquivo"]}</div>')
    folha.salvar(tmp_path / "x.pdf")

    assert folha.menor_escala == 1.0
