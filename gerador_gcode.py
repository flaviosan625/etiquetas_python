"""
gerador_gcode.py — Gerador autônomo de G-Code padrão ISO 6983 para usinagem CNC.

Elimina a dependência de softwares proprietários (Vectric Aspire, ArtCAM) para
geração de percursos de fresamento 2.5D, garantindo compatibilidade universal
com comandos CNC industriais e com o CNC-CAM C++.

Padrões adotados:
  - ISO 6983 / DIN 66025 (G-Code padrão industrial)
  - Unidades em milímetros (G21)
  - Coordenadas absolutas (G90)
  - Seleção de plano de interpolação XY (G17)
  - Spindle horário (M3) com estabilização por temporização (G4)
  - Desligamento de spindle (M5) e finalização de programa (M30, %)
"""

from __future__ import annotations

import dataclasses
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


@dataclasses.dataclass
class ParametrosUsinagem:
    """Parâmetros operacionais e tecnológicos para usinagem CNC."""

    diametro_fresa_mm: float = 6.0
    profundidade_total_mm: float = 10.0
    passo_z_mm: float = 3.5
    avanco_corte_mm_min: float = 3000.0
    avanco_mergulho_mm_min: float = 800.0
    safe_z_mm: float = 5.0
    spindle_rpm: int = 18000
    usar_pontes: bool = False
    largura_ponte_mm: float = 5.0
    espessura_ponte_mm: float = 1.5

    # Parâmetros complementares com valores padrão seguros
    avanco_rapido_mm_min: float = 6000.0
    espera_spindle_s: float = 1.5
    divisao_uniforme: bool = True
    pontes_por_contorno: int = 4


class GeradorGCodeISO:
    """
    Emissor de código G padrão ISO 6983 para centros de usinagem e roteadores CNC.
    """

    def __init__(self, parametros: Optional[ParametrosUsinagem] = None):
        self.parametros = parametros or ParametrosUsinagem()

    def calcular_passadas_z(
        self,
        profundidade: Optional[float] = None,
        passo_z: Optional[float] = None,
        uniforme: Optional[bool] = None,
    ) -> List[float]:
        """
        Calcula as cotas negativas de profundidade em Z para cada passada.

        Se uniforme=True (padrão): divide a profundidade total pelo número
        inteiro de passadas necessárias para que todas tenham profundidade idêntica.
        Se uniforme=False: desce de passo_z em passo_z até atingir a profundidade.
        """
        prof = abs(self.parametros.profundidade_total_mm if profundidade is None else profundidade)
        passo = abs(self.parametros.passo_z_mm if passo_z is None else passo_z)
        e_uniforme = self.parametros.divisao_uniforme if uniforme is None else uniforme

        if prof <= 0.0 or passo <= 0.0:
            return [-round(prof, 4)] if prof > 0.0 else []

        num_passadas = max(1, math.ceil(prof / passo))

        if e_uniforme:
            cota_por_passada = prof / num_passadas
            passadas = [-round((i + 1) * cota_por_passada, 4) for i in range(num_passadas)]
            # Garante que a última seja exatamente a profundidade total
            passadas[-1] = -round(prof, 4)
            return passadas
        else:
            passadas = []
            atual = 0.0
            while atual + 1e-6 < prof:
                atual = min(prof, atual + passo)
                passadas.append(-round(atual, 4))
            return passadas

    def emitir_cabecalho(self, params: Optional[ParametrosUsinagem] = None) -> List[str]:
        """
        Gera o cabeçalho padrão ISO 6983.
        G21: Unidades métricas em milímetros
        G90: Coordenadas absolutas
        G17: Seleção do plano de interpolação XY
        M3 S{rpm}: Liga spindle no sentido horário com a rotação definida
        G4 P{espera}: Dwell para estabilização da rotação do spindle
        G0 Z{safe_z}: Posiciona eixo Z em cota segura acima do material
        """
        p = params or self.parametros
        linhas = [
            "%",
            "( CNC-CAM AUTONOMO - PADRAO ISO 6983 )",
            "G21",
            "G90",
            "G17",
            f"M3 S{int(p.spindle_rpm)}",
            f"G4 P{p.espera_spindle_s:.1f}",
            f"G0 Z{p.safe_z_mm:.3f}",
        ]
        return linhas

    def emitir_rodape(self, params: Optional[ParametrosUsinagem] = None) -> List[str]:
        """
        Gera o rodapé de segurança e finalização de programa CNC.
        G0 Z{safe_z}: Retrai eixo Z para cota segura
        M5: Desliga spindle
        G0 X0 Y0: Retorna os eixos à origem da máquina/peça
        M30: Fim de programa e rebobinamento
        %: Caractere de finalização de fita/programa ISO
        """
        p = params or self.parametros
        linhas = [
            f"G0 Z{p.safe_z_mm:.3f}",
            "M5",
            "G0 X0.000 Y0.000",
            "M30",
            "%",
        ]
        return linhas

    def _preparar_pontes_contorno(
        self,
        pontos: Sequence[Tuple[float, float]],
        largura_ponte: float,
        num_pontes: int,
    ) -> List[Tuple[float, float, bool]]:
        """
        Interpola a polilinha inserindo nós nas bordas de cada ponte (tab).
        Retorna lista de (x, y, esta_na_ponte).
        """
        if len(pontos) < 2:
            return [(p[0], p[1], False) for p in pontos]

        # Comprimento de cada segmento
        segs = []
        comp_acum = [0.0]
        total_len = 0.0
        for i in range(len(pontos) - 1):
            p1, p2 = pontos[i], pontos[i + 1]
            d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            segs.append(d)
            total_len += d
            comp_acum.append(total_len)

        if total_len <= largura_ponte * 2.0 or num_pontes <= 0:
            return [(p[0], p[1], False) for p in pontos]

        # Intervalos de pontes [s_ini, s_fim] ao longo do percurso
        num_pontes = min(num_pontes, max(1, int(total_len / (largura_ponte * 2.5))))
        intervalos_pontes: List[Tuple[float, float]] = []
        for k in range(num_pontes):
            centro = (k + 0.5) * (total_len / num_pontes)
            s_ini = max(0.01, centro - largura_ponte / 2.0)
            s_fim = min(total_len - 0.01, centro + largura_ponte / 2.0)
            if s_fim > s_ini:
                intervalos_pontes.append((s_ini, s_fim))

        # Função auxiliar para obter ponto em distância acumulada 's'
        def ponto_em(s: float) -> Tuple[float, float]:
            if s <= 0.0:
                return pontos[0]
            if s >= total_len:
                return pontos[-1]
            for idx, comp in enumerate(segs):
                if s <= comp_acum[idx + 1]:
                    t = (s - comp_acum[idx]) / max(comp, 1e-9)
                    x = pontos[idx][0] + t * (pontos[idx + 1][0] - pontos[idx][0])
                    y = pontos[idx][1] + t * (pontos[idx + 1][1] - pontos[idx][1])
                    return (x, y)
            return pontos[-1]

        def esta_em_ponte(s: float) -> bool:
            return any(s_ini <= s <= s_fim for s_ini, s_fim in intervalos_pontes)

        # Mescla pontos originais e pontos de início/fim de pontes
        eventos: List[Tuple[float, str]] = []
        for s_ini, s_fim in intervalos_pontes:
            eventos.append((s_ini, "ini_ponte"))
            eventos.append((s_fim, "fim_ponte"))
        for s in comp_acum:
            eventos.append((s, "vertice"))

        eventos.sort(key=lambda ev: ev[0])

        resultado: List[Tuple[float, float, bool]] = []
        ultimo_s = -1.0
        for s, tipo in eventos:
            if abs(s - ultimo_s) < 1e-4:
                continue
            ultimo_s = s
            pt = ponto_em(s)
            na_ponte = esta_em_ponte(s)
            resultado.append((pt[0], pt[1], na_ponte))

        return resultado

    def gerar_percurso_contorno(
        self,
        pontos: Sequence[Tuple[float, float]],
        fechado: bool = True,
        usar_pontes: Optional[bool] = None,
        parametros: Optional[ParametrosUsinagem] = None,
    ) -> List[str]:
        """
        Gera movimentos de G-Code para um contorno específico:
          1. Deslocamento rápido G0 até ponto de início com Z seguro.
          2. Itera por todas as passadas em Z calculadas.
          3. Em cada passada: mergulho G1 Z... F{plunge}, percurso perimétrico G1 X... Y... F{feed}.
          4. Se pontes ativadas e na passada final/fundo: eleva a Z da ponte ao passar pelas abas.
          5. Ao terminar, retrai o eixo Z para safe_z.
        """
        p = parametros or self.parametros
        if not pontos:
            return []

        pts = list(pontos)
        if fechado and (abs(pts[0][0] - pts[-1][0]) > 1e-4 or abs(pts[0][1] - pts[-1][1]) > 1e-4):
            pts.append(pts[0])

        pontes_habilitadas = p.usar_pontes if usar_pontes is None else usar_pontes
        z_passadas = self.calcular_passadas_z(p.profundidade_total_mm, p.passo_z_mm, p.divisao_uniforme)
        if not z_passadas:
            return []

        # Cota de Z da ponte: espessura_ponte acima do fundo
        z_fundo = -abs(p.profundidade_total_mm)
        z_ponte = z_fundo + abs(p.espessura_ponte_mm)

        pts_com_pontes = None
        if pontes_habilitadas:
            pts_com_pontes = self._preparar_pontes_contorno(
                pts, p.largura_ponte_mm, p.pontes_por_contorno
            )

        linhas: List[str] = []
        x0, y0 = pts[0]

        # 1. Posicionamento rápido inicial em Z seguro
        linhas.append(f"G0 X{x0:.3f} Y{y0:.3f}")

        # 2. Iteração de passadas em Z
        for indice_passada, z_corte in enumerate(z_passadas):
            e_passada_ponte = pontes_habilitadas and (z_corte < z_ponte or indice_passada == len(z_passadas) - 1)

            # Mergulho inicial da passada
            linhas.append(f"G1 Z{z_corte:.3f} F{p.avanco_mergulho_mm_min:.1f}")

            if e_passada_ponte and pts_com_pontes:
                # Percurso com elevação em pontes
                z_atual = z_corte
                for px, py, na_ponte in pts_com_pontes[1:]:
                    alvo_z = z_ponte if na_ponte else z_corte
                    if abs(alvo_z - z_atual) > 1e-4:
                        # Mudança de nível de Z (subida da ponte ou descida)
                        linhas.append(f"G1 Z{alvo_z:.3f} F{p.avanco_mergulho_mm_min:.1f}")
                        z_atual = alvo_z
                    linhas.append(f"G1 X{px:.3f} Y{py:.3f} F{p.avanco_corte_mm_min:.1f}")
                # Garante retorno ao Z de corte antes de fechar passada
                if abs(z_atual - z_corte) > 1e-4:
                    linhas.append(f"G1 Z{z_corte:.3f} F{p.avanco_mergulho_mm_min:.1f}")
            else:
                # Percurso normal sem pontes
                for px, py in pts[1:]:
                    linhas.append(f"G1 X{px:.3f} Y{py:.3f} F{p.avanco_corte_mm_min:.1f}")

        # Retração de segurança ao final do contorno
        linhas.append(f"G0 Z{p.safe_z_mm:.3f}")
        return linhas

    def gerar_gcode(
        self,
        percursos: Sequence[Any],
        parametros: Optional[ParametrosUsinagem] = None,
    ) -> str:
        """
        Gera o programa G-Code completo para uma coleção de percursos.
        Suporta objetos PercursoCorte ou tuplas/listas de pontos.
        """
        p = parametros or self.parametros
        linhas = self.emitir_cabecalho(p)

        for percurso in percursos:
            # Extrai pontos e propriedades de PercursoCorte ou coleção de coordenadas
            if hasattr(percurso, "pontos"):
                pontos = percurso.pontos
                fechado = getattr(percurso, "fechado", True)
                tipo = getattr(percurso, "tipo", None)
                # Pontes são prioritárias em contorno externo para evitar desprendimento
                aplicar_pontes = p.usar_pontes
                if tipo and str(tipo) not in ("CORTE_EXTERNO", "TipoEntidadeCorte.CORTE_EXTERNO"):
                    # Em furos e internos, pontes são desnecessárias por padrão
                    aplicar_pontes = False
            else:
                pontos = percurso
                fechado = True
                aplicar_pontes = p.usar_pontes

            linhas_contorno = self.gerar_percurso_contorno(
                pontos=pontos,
                fechado=fechado,
                usar_pontes=aplicar_pontes,
                parametros=p,
            )
            linhas.extend(linhas_contorno)

        linhas.extend(self.emitir_rodape(p))
        return "\n".join(linhas) + "\n"

    def estimar_tempo(
        self,
        gcode_ou_linhas: Union[str, Sequence[str]],
        parametros: Optional[ParametrosUsinagem] = None,
    ) -> float:
        """
        Estima o tempo total de usinagem em segundos simulando a cinemática do percurso.
        """
        detalhes = self.estimar_tempo_detalhado(gcode_ou_linhas, parametros)
        return detalhes["tempo_total_s"]

    def estimar_tempo_detalhado(
        self,
        gcode_ou_linhas: Union[str, Sequence[str]],
        parametros: Optional[ParametrosUsinagem] = None,
    ) -> Dict[str, Any]:
        """
        Analisa o G-Code e retorna métricas detalhadas de tempo e distância.
        """
        p = parametros or self.parametros
        if isinstance(gcode_ou_linhas, str):
            linhas = gcode_ou_linhas.splitlines()
        else:
            linhas = list(gcode_ou_linhas)

        cur_x, cur_y, cur_z = 0.0, 0.0, p.safe_z_mm
        feed_corte = p.avanco_corte_mm_min
        feed_rapido = p.avanco_rapido_mm_min
        feed_mergulho = p.avanco_mergulho_mm_min
        cur_feed = feed_corte

        dist_rapida = 0.0
        dist_corte_xy = 0.0
        dist_mergulho_z = 0.0
        tempo_dwell_s = 0.0

        tempo_rapido_s = 0.0
        tempo_corte_s = 0.0
        tempo_mergulho_s = 0.0

        padrao_g = re.compile(r"([GMTXYZFSP])([-+]?[0-9]*\.?[0-9]+)", re.IGNORECASE)

        for linha in linhas:
            linha_limpa = linha.split("(")[0].split(";")[0].strip()
            if not linha_limpa or linha_limpa.startswith("%"):
                continue

            matches = padrao_g.findall(linha_limpa)
            if not matches:
                continue

            tokens = {letra.upper(): float(val) for letra, val in matches}

            if "F" in tokens:
                cur_feed = max(1.0, tokens["F"])

            # Dwell G4
            if tokens.get("G") == 4:
                tempo_dwell_s += tokens.get("P", 0.0)
                continue

            modo_g = tokens.get("G")
            if modo_g is None:
                # Mantém modo modal se houver coordenadas
                if any(k in tokens for k in ("X", "Y", "Z")):
                    modo_g = 1
                else:
                    continue

            novo_x = tokens.get("X", cur_x)
            novo_y = tokens.get("Y", cur_y)
            novo_z = tokens.get("Z", cur_z)

            dx = novo_x - cur_x
            dy = novo_y - cur_y
            dz = novo_z - cur_z
            dist_xy = math.hypot(dx, dy)
            dist_3d = math.sqrt(dx * dx + dy * dy + dz * dz)

            if dist_3d > 1e-6:
                if modo_g == 0:
                    dist_rapida += dist_3d
                    tempo_rapido_s += (dist_3d / feed_rapido) * 60.0
                elif modo_g == 1:
                    if dist_xy < 1e-5 and abs(dz) > 1e-5:
                        # Movimento vertical puro
                        dist_mergulho_z += abs(dz)
                        tempo_mergulho_s += (abs(dz) / cur_feed) * 60.0
                    else:
                        dist_corte_xy += dist_3d
                        tempo_corte_s += (dist_3d / cur_feed) * 60.0

            cur_x, cur_y, cur_z = novo_x, novo_y, novo_z

        tempo_total = tempo_rapido_s + tempo_corte_s + tempo_mergulho_s + tempo_dwell_s
        minutos = int(tempo_total // 60)
        segundos = int(tempo_total % 60)

        return {
            "tempo_total_s": round(tempo_total, 2),
            "tempo_corte_s": round(tempo_corte_s, 2),
            "tempo_rapido_s": round(tempo_rapido_s, 2),
            "tempo_mergulho_s": round(tempo_mergulho_s, 2),
            "tempo_dwell_s": round(tempo_dwell_s, 2),
            "dist_corte_xy_mm": round(dist_corte_xy, 2),
            "dist_rapida_mm": round(dist_rapida, 2),
            "dist_mergulho_z_mm": round(dist_mergulho_z, 2),
            "tempo_formatado": f"{minutos:02d}m {segundos:02d}s",
        }
