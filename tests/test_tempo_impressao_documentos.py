"""Cálculos expostos nos PDFs e fichas, com produção inteiramente isolada."""
import copy
import datetime
import json

import pymupdf
import pytest

import config
import documento_enviados
import montagem
import relatorio_producao
import relatorios
import tempo_impressao as tempo


def ler_pdf(caminho):
    with pymupdf.open(caminho) as pdf:
        texto = "\n".join(p.get_text() for p in pdf)
        for pagina in pdf:
            for bloco in pagina.get_text("blocks"):
                assert bloco[0] >= -0.5 and bloco[1] >= -0.5
                assert bloco[2] <= pagina.rect.width + .5
                assert bloco[3] <= pagina.rect.height + .5
        return texto


def registro(maquina="DOCAN R5200", area=100, passadas=None):
    linha = {"quando": "2026-10-09T08:00:00", "arquivo": "2UN LONA 5.00X10.00M.pdf",
             "maquina": maquina, "producao": "PRODUCAO EXEMPLO", "categoria": "LONA",
             "quantidade": 2, "area_total_m2": area,
             "dimensao": {"largura_m": 5.0, "altura_m": 10.0}, "girou_previsto": False}
    if passadas is not None:
        linha["estimativa_impressao"] = tempo.estimar(maquina, area, passadas)
    return linha


def test_enviados_mostra_planejamento_e_soma_reenvios_sem_misturar_maquinas(tmp_path):
    cliente = tmp_path / "CLIENTE EXEMPLO"
    documento_enviados.registrar(cliente, [registro(passadas=4), registro(passadas=4),
                                          registro("SWJ320A")])
    texto = ler_pdf(documento_enviados.gerar_pdf(cliente))
    assert "Est. DOCAN 4 passadas (planejamento): 59min16s" in texto
    assert "Est. DOCAN: 1h58min32s" in texto
    assert "300,00 m²" in texto
    assert "09/10 08:00" in texto
    assert "SWJ320A" in texto


def test_enviados_antigos_docan_exibem_referencia_e_sem_medida_nao_inventa(tmp_path):
    cliente = tmp_path / "CLIENTE EXEMPLO"
    documento_enviados.registrar(cliente, [registro(), registro(area=None)])
    texto = ler_pdf(documento_enviados.gerar_pdf(cliente))
    assert texto.count("Est. DOCAN 8 passadas (referência)") == 1
    assert "Medida não informada" in texto


def test_enviados_docan_multipagina_preserva_todas_as_linhas_e_rodape(tmp_path):
    cliente = tmp_path / "CLIENTE EXEMPLO"
    documento_enviados.registrar(cliente, [registro(passadas=6) for _ in range(30)])
    texto = ler_pdf(documento_enviados.gerar_pdf(cliente))
    assert texto.count("Est. DOCAN 6 passadas (planejamento)") == 30
    assert "SUBTOTAL POR MATERIAL" in texto
    assert "Referência de 8 passadas" in " ".join(texto.split())


def test_montagem_ficha_e_previa_usam_area_completa_sem_alterar_arte(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    entrada = tmp_path / tempo.MAQUINA_DOCAN
    entrada.mkdir()
    original = entrada / "2UN LONA 1.00X0.50M_CLIENTE.pdf"
    with pymupdf.open() as pdf:
        pagina = pdf.new_page(width=montagem.PT_M, height=montagem.PT_M / 2)
        pagina.draw_rect(pagina.rect, color=None, fill=(.2,.5,.7))
        pdf.save(original)
    cfg = copy.deepcopy(config.CONFIG_PADRAO)
    previa = montagem.prever_pasta(entrada, config=cfg, raiz_clientes=tmp_path / "clientes",
                                   folga_m=.025, passadas_docan=6)
    resultado = montagem.montar_pasta(entrada, config=cfg, raiz_clientes=tmp_path / "clientes",
                                     folga_m=.025, passadas_docan=6, guardar_originais=False)
    ficha = json.loads(resultado["folhas"][0]["arquivo"].with_suffix(".json").read_text(encoding="utf-8"))
    estimativa = ficha["estimativa_impressao"]
    assert estimativa["passadas"] == 6
    assert estimativa["area_m2"] > ficha["area_pecas_m2"]
    assert estimativa["segundos"] == pytest.approx(previa["folhas"][0]["estimativa_impressao"]["segundos"])
    assert len(ficha["pecas"]) == 2
    assert original.exists()


def test_os_decorflex_referencia_e_taxa_manual_preservada(tmp_path):
    itens = [{"arquivo": "1UN DECORFLEX 5.00X10.00M.pdf", "categoria": "DECORFLEX", "quantidade": 1,
              "dimensao": {"largura_m":5, "altura_m":10, "area_m2":50},
              "thumbnail_bytes": None, "variante": None}]
    dados = {"DECORFLEX": {"contem_arquivos": True, "area_total_m2":50, "total_etiquetas":1}}
    args = (str(tmp_path), "CLIENTE EXEMPLO", "Gerente", "Produtor", itens, dados,
            ["DECORFLEX"], "09/10/2026 08:00")
    texto = ler_pdf(relatorios.gerar_os(*args))
    assert "Est. DOCAN 8 passadas (referência): 59min16s" in texto
    texto_manual = ler_pdf(relatorios.gerar_os(*args, materiais_config={"DECORFLEX":{"minutos_por_m2":2}}))
    assert "1h 40min" in texto_manual
    assert "Est. DOCAN" not in texto_manual


def test_relatorio_diario_estimativa_separada_de_tempo_real(tmp_path, monkeypatch):
    monkeypatch.setattr(relatorio_producao, "PASTA_RELATORIOS", tmp_path / "relatorios")
    pasta_registro = tmp_path / "relatorios" / relatorio_producao.NOME_SUBPASTA_REGISTRO
    pasta_registro.mkdir(parents=True)
    linha = registro()
    linha.pop("dimensao")
    (pasta_registro / "2026-10.jsonl").write_text(json.dumps(linha) + "\n", encoding="utf-8")
    caminho = relatorio_producao.gerar_pdf(datetime.date(2026,10,9), pasta_relatorios=tmp_path / "relatorios",
                                          pasta_fila=tmp_path / "fila", config=copy.deepcopy(config.CONFIG_PADRAO))
    texto = ler_pdf(caminho)
    assert "Est. DOCAN 8 passadas (referência): 1h58min32s" in texto
    assert "Est. DOCAN por material" in texto
