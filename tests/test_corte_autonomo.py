"""
Testes unitários e de integração para corte_autonomo.py (ISSUE-12).

Valida ordenação inviolável de usinagem, otimização TSP por vizinho mais próximo,
classificação topológica automática, exportação DXF em 3 camadas, exportação G-Code
e arquivo de intercâmbio com o CNC-CAM C++.
"""

import json
import math
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from corte_autonomo import (
    CAMADA_DXF_EXTERNO,
    CAMADA_DXF_FUROS,
    CAMADA_DXF_INTERNO,
    PercursoCorte,
    PlanoCorte,
    TipoEntidadeCorte,
    classificar_percursos,
    exportar_conector_cnccam,
    exportar_dxf_estruturado,
    exportar_gcode,
    otimizar_vizinho_mais_proximo,
)
from gerador_gcode import ParametrosUsinagem


def _criar_circulo(cx: float, cy: float, r: float, num_pts: int = 16) -> list:
    pts = []
    for i in range(num_pts):
        ang = 2.0 * math.pi * i / num_pts
        pts.append((round(cx + r * math.cos(ang), 3), round(cy + r * math.sin(ang), 3)))
    pts.append(pts[0])
    return pts


def _criar_retangulo(x: float, y: float, w: float, h: float) -> list:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def test_ordenacao_inviolavel_usinagem():
    """
    Garante a regra física de chão de fábrica inegociável:
      1º: Todos os FUROS
      2º: Todos os CORTES INTERNOS
      3º: Todos os CORTES EXTERNOS
    Nenhum corte externo pode acontecer antes de furos ou internos.
    """
    furo1 = PercursoCorte(tipo=TipoEntidadeCorte.FURO, pontos=_criar_circulo(50, 50, 4))
    furo2 = PercursoCorte(tipo=TipoEntidadeCorte.FURO, pontos=_criar_circulo(80, 80, 5))
    interno1 = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_INTERNO, pontos=_criar_retangulo(30, 30, 20, 20))
    interno2 = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_INTERNO, pontos=_criar_retangulo(60, 60, 15, 15))
    externo1 = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_EXTERNO, pontos=_criar_retangulo(10, 10, 100, 100))
    externo2 = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_EXTERNO, pontos=_criar_retangulo(150, 150, 120, 120))

    # Fornece em ordem invertida e mista
    plano = PlanoCorte(
        percursos=[externo2, interno2, furo2, externo1, interno1, furo1],
        material="MDF",
        espessura=15.0,
    )

    ordenados = plano.ordenar_percursos()
    tipos = [p.tipo for p in ordenados]

    # Verifica os tipos por bloco
    assert tipos[0] == TipoEntidadeCorte.FURO
    assert tipos[1] == TipoEntidadeCorte.FURO
    assert tipos[2] == TipoEntidadeCorte.CORTE_INTERNO
    assert tipos[3] == TipoEntidadeCorte.CORTE_INTERNO
    assert tipos[4] == TipoEntidadeCorte.CORTE_EXTERNO
    assert tipos[5] == TipoEntidadeCorte.CORTE_EXTERNO

    # Validação estrita: índice máximo de furo < índice mínimo de interno < índice mínimo de externo
    idx_max_furo = max(i for i, t in enumerate(tipos) if t == TipoEntidadeCorte.FURO)
    idx_min_interno = min(i for i, t in enumerate(tipos) if t == TipoEntidadeCorte.CORTE_INTERNO)
    idx_max_interno = max(i for i, t in enumerate(tipos) if t == TipoEntidadeCorte.CORTE_INTERNO)
    idx_min_externo = min(i for i, t in enumerate(tipos) if t == TipoEntidadeCorte.CORTE_EXTERNO)

    assert idx_max_furo < idx_min_interno
    assert idx_max_interno < idx_min_externo


def test_otimizacao_tsp_vizinho_mais_proximo():
    """Valida a otimização de caminho rápido G0 entre entidades pelo vizinho mais próximo."""
    p_perto1 = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_EXTERNO, pontos=[(10, 10), (20, 10), (20, 20), (10, 10)])
    p_perto2 = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_EXTERNO, pontos=[(25, 25), (35, 25), (35, 35), (25, 25)])
    p_longe = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_EXTERNO, pontos=[(800, 800), (810, 800), (810, 810), (800, 800)])

    # Ordem desfavorável: perto -> longe -> perto
    desfavoravel = [p_perto1, p_longe, p_perto2]
    otimizado = otimizar_vizinho_mais_proximo(desfavoravel, ponto_inicial=(0, 0))

    # Otimizado deve priorizar perto1 depois perto2 e por último o distante
    assert otimizado[0] is p_perto1
    assert otimizado[1] is p_perto2
    assert otimizado[2] is p_longe

    # Calcula e compara as distâncias de transição em vazio
    def dist_g0(lista, inicio=(0, 0)):
        d = 0.0
        pos = inicio
        for item in lista:
            d += math.hypot(item.ponto_inicio[0] - pos[0], item.ponto_inicio[1] - pos[1])
            pos = item.ponto_fim
        return d

    assert dist_g0(otimizado) < dist_g0(desfavoravel)


def test_classificacao_topologica():
    """Valida a separação de furos (raio <= 8mm), cortes internos (aninhados) e externos (raiz)."""
    furo_pequeno = _criar_circulo(50, 50, r=4.0)   # r = 4 <= 8 -> FURO
    furo_limite = _criar_circulo(80, 80, r=8.0)    # r = 8 <= 8 -> FURO
    ret_externo = _criar_retangulo(0, 0, 200, 200) # Raiz grande -> CORTE_EXTERNO
    ret_interno = _criar_retangulo(20, 20, 50, 50) # Dentro do ret_externo, r = 35 > 8 -> CORTE_INTERNO

    polilinhas = [ret_externo, furo_pequeno, ret_interno, furo_limite]
    percursos = classificar_percursos(polilinhas, raio_max_furo_mm=8.0)

    mapa = {p.id_entidade: p.tipo for p in percursos}
    tipos = [p.tipo for p in percursos]

    assert tipos.count(TipoEntidadeCorte.FURO) == 2
    assert tipos.count(TipoEntidadeCorte.CORTE_INTERNO) == 1
    assert tipos.count(TipoEntidadeCorte.CORTE_EXTERNO) == 1

    # Verifica furos específicos
    furos = [p for p in percursos if p.tipo == TipoEntidadeCorte.FURO]
    raios = [f.raio for f in furos]
    assert any(pytest.approx(r, abs=0.5) == 4.0 for r in raios if r is not None)
    assert any(pytest.approx(r, abs=0.5) == 8.0 for r in raios if r is not None)


def test_exportar_dxf_estruturado(tmp_path):
    """Valida a geração de DXF R12 com as camadas semânticas FUROS, CORTE_INTERNO e CORTE_EXTERNO."""
    furo = PercursoCorte(tipo=TipoEntidadeCorte.FURO, pontos=_criar_circulo(50, 50, 4))
    interno = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_INTERNO, pontos=_criar_retangulo(30, 30, 30, 30))
    externo = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_EXTERNO, pontos=_criar_retangulo(10, 10, 100, 100))

    plano = PlanoCorte(percursos=[externo, interno, furo], espessura=10.0)
    caminho_dxf = tmp_path / "saida_corte.dxf"

    res = exportar_dxf_estruturado(plano, caminho_dxf)
    assert res.exists()

    conteudo = caminho_dxf.read_text(encoding="ascii")
    # Cabeçalho R12 padrão
    assert "AC1009" in conteudo
    # Definição das 3 camadas nas tabelas
    assert CAMADA_DXF_FUROS in conteudo
    assert CAMADA_DXF_INTERNO in conteudo
    assert CAMADA_DXF_EXTERNO in conteudo
    # Entidades vinculadas a cada camada
    assert f"8\n{CAMADA_DXF_FUROS}\n" in conteudo
    assert f"8\n{CAMADA_DXF_INTERNO}\n" in conteudo
    assert f"8\n{CAMADA_DXF_EXTERNO}\n" in conteudo
    assert "POLYLINE" in conteudo
    assert "EOF" in conteudo


def test_exportar_gcode_completo(tmp_path):
    """Valida a exportação direta de G-Code a partir do PlanoCorte."""
    furo = PercursoCorte(tipo=TipoEntidadeCorte.FURO, pontos=_criar_circulo(20, 20, 3))
    externo = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_EXTERNO, pontos=_criar_retangulo(10, 10, 50, 50))

    plano = PlanoCorte(percursos=[externo, furo], espessura=10.0)
    caminho_nc = tmp_path / "corte.tap"

    params = ParametrosUsinagem(profundidade_total_mm=10.0, passo_z_mm=5.0)
    res = exportar_gcode(plano, caminho_nc, parametros=params)
    assert res.exists()

    gcode = caminho_nc.read_text(encoding="ascii")
    assert "G21" in gcode
    assert "M3 S18000" in gcode
    assert "G4 P1.5" in gcode
    # Furo usinado antes do contorno externo
    pos_furo = gcode.find("X23.000") if "X23.000" in gcode else gcode.find("G0 X2")
    pos_externo = gcode.find("X10.000 Y10.000")
    assert pos_furo != -1 and pos_externo != -1
    assert pos_furo < pos_externo
    assert "M30" in gcode


def test_exportar_conector_cnccam(tmp_path):
    """Valida a geração de arquivo de intercâmbio JSON para o CNC-CAM C++."""
    furo = PercursoCorte(tipo=TipoEntidadeCorte.FURO, pontos=_criar_circulo(40, 40, 5), raio=5.0, centro=(40, 40))
    interno = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_INTERNO, pontos=_criar_retangulo(20, 20, 20, 20))
    externo = PercursoCorte(tipo=TipoEntidadeCorte.CORTE_EXTERNO, pontos=_criar_retangulo(0, 0, 100, 100))

    plano = PlanoCorte(
        percursos=[externo, interno, furo],
        material="MDF",
        espessura=15.0,
        largura_chapa=1220.0,
        altura_chapa=2440.0,
        nome_arquivo="teste_lote",
    )

    caminho_conector = tmp_path / "lote.cnccam.json"
    res = exportar_conector_cnccam(plano, caminho_conector)
    assert res.exists()

    dados = json.loads(caminho_conector.read_text(encoding="utf-8"))
    assert dados["versao_conector"] == "1.0"
    assert dados["metadados"]["material"] == "MDF"
    assert dados["metadados"]["espessura_mm"] == 15.0
    assert dados["metadados"]["largura_chapa_mm"] == 1220.0
    assert dados["metadados"]["altura_chapa_mm"] == 2440.0
    assert dados["metadados"]["contagem"]["furos"] == 1
    assert dados["metadados"]["contagem"]["cortes_internos"] == 1
    assert dados["metadados"]["contagem"]["cortes_externos"] == 1

    percursos_json = dados["percursos"]
    assert len(percursos_json) == 3
    # Inviolabilidade preservada no JSON de intercâmbio
    assert percursos_json[0]["tipo"] == "FURO"
    assert percursos_json[0]["camada_dxf"] == "FUROS"
    assert percursos_json[1]["tipo"] == "CORTE_INTERNO"
    assert percursos_json[1]["camada_dxf"] == "CORTE_INTERNO"
    assert percursos_json[2]["tipo"] == "CORTE_EXTERNO"
    assert percursos_json[2]["camada_dxf"] == "CORTE_EXTERNO"
