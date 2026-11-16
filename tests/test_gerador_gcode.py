"""
Testes unitários para gerador_gcode.py (ISSUE-12).

Valida conformidade rigorosa com o padrão ISO 6983, cálculo de passadas em Z,
sistema de pontes de fixação (tabs) e estimador cinemático de tempo de usinagem.
"""

import math
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from gerador_gcode import GeradorGCodeISO, ParametrosUsinagem


def test_parametros_padrao_conforme_especificacao():
    """Valida que os valores padrão de ParametrosUsinagem cumprem a ISSUE-12."""
    p = ParametrosUsinagem()
    assert p.diametro_fresa_mm == 6.0
    assert p.profundidade_total_mm == 10.0
    assert p.passo_z_mm == 3.5
    assert p.avanco_corte_mm_min == 3000.0
    assert p.avanco_mergulho_mm_min == 800.0
    assert p.safe_z_mm == 5.0
    assert p.spindle_rpm == 18000
    assert p.usar_pontes is False
    assert p.largura_ponte_mm == 5.0
    assert p.espessura_ponte_mm == 1.5


def test_calculo_passadas_z_uniforme_e_fracionada():
    """Valida a divisão uniforme e fracionada da profundidade total por passo_z_mm."""
    gerador = GeradorGCodeISO()

    # Caso padrão: prof 10.0 mm, passo 3.5 mm -> 3 passadas
    # Uniforme: 10.0 / 3 = 3.3333 mm por passada
    passadas_uni = gerador.calcular_passadas_z(profundidade=10.0, passo_z=3.5, uniforme=True)
    assert len(passadas_uni) == 3
    assert passadas_uni[0] == pytest.approx(-3.3333, abs=1e-3)
    assert passadas_uni[1] == pytest.approx(-6.6667, abs=1e-3)
    assert passadas_uni[2] == -10.0

    # Fracionada: -3.5, -7.0, -10.0
    passadas_frac = gerador.calcular_passadas_z(profundidade=10.0, passo_z=3.5, uniforme=False)
    assert len(passadas_frac) == 3
    assert passadas_frac[0] == -3.5
    assert passadas_frac[1] == -7.0
    assert passadas_frac[2] == -10.0

    # Chapa fina que sai em 1 passada
    passadas_1 = gerador.calcular_passadas_z(profundidade=3.0, passo_z=3.5, uniforme=True)
    assert len(passadas_1) == 1
    assert passadas_1[0] == -3.0

    # Profundidade zero
    assert gerador.calcular_passadas_z(profundidade=0.0) == []


def test_cabecalho_e_rodape_iso():
    """Valida cabeçalho ISO (G21, G90, G17, M3, G4 P1.5) e rodapé (G0 Z, M5, G0 X0 Y0, M30, %)."""
    p = ParametrosUsinagem(spindle_rpm=18000, safe_z_mm=5.0, espera_spindle_s=1.5)
    gerador = GeradorGCodeISO(p)

    cabecalho = gerador.emitir_cabecalho(p)
    texto_cab = "\n".join(cabecalho)
    assert "%" in cabecalho[0]
    assert "G21" in texto_cab
    assert "G90" in texto_cab
    assert "G17" in texto_cab
    assert "M3 S18000" in texto_cab
    assert "G4 P1.5" in texto_cab
    assert "G0 Z5.000" in texto_cab

    rodape = gerador.emitir_rodape(p)
    texto_rod = "\n".join(rodape)
    assert "G0 Z5.000" in texto_rod
    assert "M5" in texto_rod
    assert "G0 X0.000 Y0.000" in texto_rod
    assert "M30" in texto_rod
    assert "%" in rodape[-1]


def test_geracao_movimentos_e_mergulho():
    """Valida movimentos G0 rápido, mergulho G1 Z com F{plunge} e corte G1 com F{feed}."""
    p = ParametrosUsinagem(
        profundidade_total_mm=6.0,
        passo_z_mm=3.0,
        avanco_corte_mm_min=2400.0,
        avanco_mergulho_mm_min=600.0,
        safe_z_mm=5.0,
    )
    gerador = GeradorGCodeISO(p)

    # Retângulo 50x50 mm
    quadrado = [(10.0, 10.0), (60.0, 10.0), (60.0, 60.0), (10.0, 60.0), (10.0, 10.0)]
    gcode = gerador.gerar_gcode([quadrado], parametros=p)

    assert "G0 X10.000 Y10.000" in gcode
    # Mergulho da passada 1 (Z=-3.0) com avanço F600.0
    assert "G1 Z-3.000 F600.0" in gcode
    # Corte perimétrico com avanço F2400.0
    assert "G1 X60.000 Y10.000 F2400.0" in gcode
    # Mergulho da passada 2 (Z=-6.0)
    assert "G1 Z-6.000 F600.0" in gcode
    # Retração para Z seguro
    assert "G0 Z5.000" in gcode


def test_pontes_de_fixacao():
    """Valida a elevação da fresa na cota z_ponte ao ativar usar_pontes=True."""
    p = ParametrosUsinagem(
        profundidade_total_mm=10.0,
        passo_z_mm=5.0,
        espessura_ponte_mm=2.0,  # Ponte eleva até -10.0 + 2.0 = -8.0 mm
        usar_pontes=True,
        largura_ponte_mm=5.0,
        pontes_por_contorno=4,
    )
    gerador = GeradorGCodeISO(p)

    # Contorno de 100x100 mm (perímetro 400 mm)
    contorno = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0)]
    gcode = gerador.gerar_gcode([contorno], parametros=p)

    # Cota da ponte esperada: -8.000 mm
    assert "G1 Z-8.000" in gcode
    # Retorno ao fundo de corte: -10.000 mm
    assert "G1 Z-10.000" in gcode


def test_estimador_tempo_usinagem():
    """Valida o método de estimativa de tempo cinemático de usinagem."""
    p = ParametrosUsinagem(
        profundidade_total_mm=5.0,
        passo_z_mm=5.0,
        avanco_corte_mm_min=3000.0,    # 50 mm/s
        avanco_mergulho_mm_min=600.0,  # 10 mm/s
        avanco_rapido_mm_min=6000.0,   # 100 mm/s
        espera_spindle_s=1.5,
    )
    gerador = GeradorGCodeISO(p)

    # Contorno de 100x100 mm: perímetro = 400 mm
    # Tempo corte: 400 mm / (3000 mm/min) = 0.1333 min = 8.0 s
    # Mergulho Z 5mm safe -> -5mm prof = 10mm -> 10 / 600 * 60 = 1.0 s
    # Dwell: 1.5 s
    # Total esperado em torno de 10.5s a 13s dependendo do G0 inicial
    quadrado = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0)]
    gcode = gerador.gerar_gcode([quadrado], parametros=p)

    tempo_segundos = gerador.estimar_tempo(gcode, p)
    assert tempo_segundos > 8.0
    assert tempo_segundos < 30.0

    detalhes = gerador.estimar_tempo_detalhado(gcode, p)
    assert detalhes["tempo_total_s"] == tempo_segundos
    assert detalhes["tempo_dwell_s"] == 1.5
    assert "m" in detalhes["tempo_formatado"] and "s" in detalhes["tempo_formatado"]
