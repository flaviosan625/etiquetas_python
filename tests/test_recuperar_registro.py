"""
Testes da recuperação de linhas perdidas do registro.

Tudo isolado no tmp_path: o módulo, deixado por conta própria, lê a fila
de verdade no OneDrive e ESCREVE no registro permanente de produção.
"""
import datetime
import json
import os
import pathlib

import pymupdf
import pytest

import rasterlink_hotfolder as vigia
import recuperar_registro as rr

MAQUINAS_TESTE = {
    "UJV 100 UNY CV": {"hot_folder": r"C:\nao_usado", "largura_util_m": 1.48},
    "SWJ320A": {"hot_folder": r"C:\nao_usado", "largura_util_m": 3.20},
}


@pytest.fixture(autouse=True)
def _isolar(tmp_path, monkeypatch):
    """Mesma rede de segurança do test_rasterlink_hotfolder."""
    monkeypatch.setattr(vigia, "PASTA_RELATORIOS", tmp_path / "_relatorios_isolados")
    monkeypatch.setattr(vigia, "PASTA_FILA_ONEDRIVE", tmp_path / "_fila_isolada")
    monkeypatch.setattr(vigia, "CAMINHO_REGISTRO_PENDENTE", tmp_path / "registro_pendente.jsonl")
    monkeypatch.setattr(vigia, "CAMINHO_LOG", tmp_path / "hotfolder.log")


def _enviado(pasta_fila, maquina, nome, quando, largura_m=1.0, altura_m=2.0, paginas=1):
    """Um arquivo guardado em Enviados — a prova de que a entrega aconteceu."""
    pt_por_m = 72 / 0.0254
    destino = pasta_fila / maquina / vigia.NOME_SUBPASTA_ENVIADOS
    destino.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for _ in range(paginas):
        doc.new_page(width=largura_m * pt_por_m, height=altura_m * pt_por_m)
    caminho = destino / nome
    doc.save(str(caminho))
    doc.close()
    marca = quando.timestamp()
    os.utime(caminho, (marca, marca))
    return caminho


def _registro(pasta_relatorios, linhas, ano_mes="2026-09"):
    pasta = pasta_relatorios / vigia.NOME_SUBPASTA_REGISTRO
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / f"{ano_mes}.jsonl", "w", encoding="utf-8") as f:
        for linha in linhas:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def _linhas_gravadas(pasta_relatorios, ano_mes="2026-09"):
    caminho = pasta_relatorios / vigia.NOME_SUBPASTA_REGISTRO / f"{ano_mes}.jsonl"
    if not caminho.is_file():
        return []
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_acha_o_que_esta_em_enviados_e_nao_esta_no_registro(tmp_path):
    fila, rel = tmp_path / "fila", tmp_path / "rel"
    _enviado(fila, "SWJ320A", "tem_linha.pdf", datetime.datetime(2026, 9, 18, 9, 0))
    _enviado(fila, "SWJ320A", "sumiu.pdf", datetime.datetime(2026, 9, 18, 10, 30))
    _registro(rel, [{"quando": "2026-09-18T09:00:00", "maquina": "SWJ320A",
                     "arquivo": "tem_linha.pdf", "bytes": 10, "girado": False}])

    faltando = rr.entregas_sem_registro(fila, rel, MAQUINAS_TESTE)

    assert [e["caminho"].name for e in faltando] == ["sumiu.pdf"]
    assert faltando[0]["quando"] == datetime.datetime(2026, 9, 18, 10, 30)


def test_mesmo_nome_entregue_duas_vezes_precisa_de_duas_linhas(tmp_path):
    """Refação consome material igual — a segunda entrega não é duplicata."""
    fila, rel = tmp_path / "fila", tmp_path / "rel"
    _enviado(fila, "SWJ320A", "refeito.pdf", datetime.datetime(2026, 9, 18, 9, 0))
    _enviado(fila, "SWJ320A", "refeito_1789.pdf", datetime.datetime(2026, 9, 18, 15, 0))
    _registro(rel, [{"quando": "2026-09-18T09:00:00", "maquina": "SWJ320A",
                     "arquivo": "refeito.pdf", "bytes": 10, "girado": False}])

    faltando = rr.entregas_sem_registro(fila, rel, MAQUINAS_TESTE)

    assert [e["caminho"].name for e in faltando] == ["refeito_1789.pdf"]


def test_mesmo_nome_em_maquinas_diferentes_nao_se_confunde(tmp_path):
    fila, rel = tmp_path / "fila", tmp_path / "rel"
    _enviado(fila, "SWJ320A", "igual.pdf", datetime.datetime(2026, 9, 18, 9, 0))
    _enviado(fila, "UJV 100 UNY CV", "igual.pdf", datetime.datetime(2026, 9, 18, 9, 5))
    _registro(rel, [{"quando": "2026-09-18T09:00:00", "maquina": "SWJ320A",
                     "arquivo": "igual.pdf", "bytes": 10, "girado": False}])

    faltando = rr.entregas_sem_registro(fila, rel, MAQUINAS_TESTE)

    assert [(e["maquina"], e["caminho"].name) for e in faltando] == [("UJV 100 UNY CV", "igual.pdf")]


def test_ensaio_nao_escreve_nada(tmp_path):
    fila, rel = tmp_path / "fila", tmp_path / "rel"
    _enviado(fila, "SWJ320A", "sumiu.pdf", datetime.datetime(2026, 9, 18, 10, 30))

    resultado = rr.recuperar(fila, rel, MAQUINAS_TESTE, aplicar=False)

    assert resultado["encontradas"] == 1
    assert resultado["gravadas"] == 0
    assert _linhas_gravadas(rel) == []


def test_gravar_devolve_a_linha_marcada_como_recuperada(tmp_path):
    fila, rel = tmp_path / "fila", tmp_path / "rel"
    _enviado(fila, "SWJ320A", "sumiu.pdf", datetime.datetime(2026, 9, 18, 10, 30),
             largura_m=3.20, altura_m=8.28)

    resultado = rr.recuperar(fila, rel, MAQUINAS_TESTE, aplicar=True)

    assert resultado["gravadas"] == 1
    linha, = _linhas_gravadas(rel)
    assert linha["arquivo"] == "sumiu.pdf"
    assert linha["quando"] == "2026-09-18T10:30:00"
    # número deduzido não pode se passar por declarado
    assert "Enviados" in linha["recuperado"]
    assert [round(v, 2) for v in linha["pagina_m"]] == [3.20, 8.28]
    assert linha["paginas"] == 1


def test_rodar_duas_vezes_nao_duplica(tmp_path):
    fila, rel = tmp_path / "fila", tmp_path / "rel"
    _enviado(fila, "SWJ320A", "sumiu.pdf", datetime.datetime(2026, 9, 18, 10, 30))

    rr.recuperar(fila, rel, MAQUINAS_TESTE, aplicar=True)
    segunda = rr.recuperar(fila, rel, MAQUINAS_TESTE, aplicar=True)

    assert segunda["encontradas"] == 0
    assert len(_linhas_gravadas(rel)) == 1


def test_registro_completo_nao_tem_nada_a_recuperar(tmp_path):
    fila, rel = tmp_path / "fila", tmp_path / "rel"
    _enviado(fila, "SWJ320A", "a.pdf", datetime.datetime(2026, 9, 18, 9, 0))
    _registro(rel, [{"quando": "2026-09-18T09:00:00", "maquina": "SWJ320A",
                     "arquivo": "a.pdf", "bytes": 10, "girado": False}])

    assert rr.recuperar(fila, rel, MAQUINAS_TESTE)["encontradas"] == 0


def test_giro_e_previsto_pela_medida_da_folha(tmp_path):
    """Arte mais alta que larga e que cabe deitada: a máquina teria girado."""
    fila, rel = tmp_path / "fila", tmp_path / "rel"
    _enviado(fila, "SWJ320A", "em_pe.pdf", datetime.datetime(2026, 9, 18, 10, 0),
             largura_m=1.00, altura_m=3.00)

    resultado = rr.recuperar(fila, rel, MAQUINAS_TESTE, aplicar=True)

    assert resultado["linhas"][0]["girado"] is True
    assert _linhas_gravadas(rel)[0]["girado"] is True
