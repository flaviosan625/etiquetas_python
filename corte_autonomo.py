"""
corte_autonomo.py — Módulo de corte autônomo e classificação geométrica para CNC.

Elimina 100% a dependência do Vectric Aspire, implementando:
  1. Classificação topológica inteligente (FUROS, CORTE_INTERNO, CORTE_EXTERNO).
  2. Ordenação inviolável de usinagem com otimização TSP (Vizinho Mais Próximo):
       - 1º: Todos os FUROS (peça presa com segurança)
       - 2º: Todos os CORTES INTERNOS (recortes de letras, furos grandes e sanca)
       - 3º: Todos os CORTES EXTERNOS (contorno final quando a peça se desprende)
  3. Exportação de G-Code ISO via gerador_gcode.py.
  4. Exportação de DXF R12 estruturado nas camadas FUROS, CORTE_INTERNO, CORTE_EXTERNO.
  5. Exportação de arquivo conector/intercâmbio para o CNC-CAM C++.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from enum import Enum
import json
import math
import pathlib
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from gerador_gcode import GeradorGCodeISO, ParametrosUsinagem


class TipoEntidadeCorte(str, Enum):
    """Classificação funcional e de precedência física da entidade de corte."""

    FURO = "FURO"
    CORTE_INTERNO = "CORTE_INTERNO"
    CORTE_EXTERNO = "CORTE_EXTERNO"


CAMADA_DXF_FUROS = "FUROS"
CAMADA_DXF_INTERNO = "CORTE_INTERNO"
CAMADA_DXF_EXTERNO = "CORTE_EXTERNO"

MAPA_TIPO_CAMADA = {
    TipoEntidadeCorte.FURO: CAMADA_DXF_FUROS,
    TipoEntidadeCorte.CORTE_INTERNO: CAMADA_DXF_INTERNO,
    TipoEntidadeCorte.CORTE_EXTERNO: CAMADA_DXF_EXTERNO,
}


@dataclasses.dataclass
class PercursoCorte:
    """Representa um percurso vetorial fechado ou aberto para corte CNC."""

    tipo: TipoEntidadeCorte
    pontos: List[Tuple[float, float]]
    fechado: bool = True
    raio: Optional[float] = None
    centro: Optional[Tuple[float, float]] = None
    id_entidade: Optional[str] = None
    profundidade_customizada: Optional[float] = None

    def __post_init__(self):
        if not self.pontos and self.centro and self.raio:
            # Gera círculo discretizado se fornecido apenas centro e raio
            cx, cy = self.centro
            r = self.raio
            pts = []
            num_pts = 36
            for i in range(num_pts):
                ang = 2.0 * math.pi * i / num_pts
                pts.append((round(cx + r * math.cos(ang), 4), round(cy + r * math.sin(ang), 4)))
            pts.append(pts[0])
            self.pontos = pts
            self.fechado = True

    @property
    def caixa(self) -> Tuple[float, float, float, float]:
        """Caixa delimitadora (min_x, min_y, max_x, max_y)."""
        if not self.pontos:
            if self.centro and self.raio:
                cx, cy = self.centro
                return (cx - self.raio, cy - self.raio, cx + self.raio, cy + self.raio)
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in self.pontos]
        ys = [p[1] for p in self.pontos]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def largura(self) -> float:
        x0, _, x1, _ = self.caixa
        return max(0.0, x1 - x0)

    @property
    def altura(self) -> float:
        _, y0, _, y1 = self.caixa
        return max(0.0, y1 - y0)

    @property
    def ponto_inicio(self) -> Tuple[float, float]:
        return self.pontos[0] if self.pontos else (0.0, 0.0)

    @property
    def ponto_fim(self) -> Tuple[float, float]:
        return self.pontos[-1] if self.pontos else (0.0, 0.0)

    @property
    def comprimento_total(self) -> float:
        """Comprimento do perímetro ou percurso em milímetros."""
        if len(self.pontos) < 2:
            return 0.0
        total = 0.0
        for i in range(len(self.pontos) - 1):
            p1, p2 = self.pontos[i], self.pontos[i + 1]
            total += math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        return round(total, 3)

    def obter_centro(self) -> Tuple[float, float]:
        if self.centro:
            return self.centro
        x0, y0, x1, y1 = self.caixa
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def ponto_em_poligono(ponto: Tuple[float, float], poligono: Sequence[Tuple[float, float]]) -> bool:
    """
    Algoritmo de traçado de raio (Ray Casting). Determina se ponto está dentro do polígono.
    """
    x, y = ponto
    dentro = False
    n = len(poligono)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if (yi > y) != (yj > y):
            corte = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < corte:
                dentro = not dentro
        j = i
    return dentro


def otimizar_vizinho_mais_proximo(
    percursos: Sequence[PercursoCorte],
    ponto_inicial: Tuple[float, float] = (0.0, 0.0),
) -> List[PercursoCorte]:
    """
    Ordena percursos usando o algoritmo guloso de vizinho mais próximo (TSP Greedy),
    minimizando os deslocamentos em vazio (G0) da fresa.
    """
    if not percursos:
        return []
    restantes = list(percursos)
    ordenados: List[PercursoCorte] = []
    atual = ponto_inicial

    while restantes:
        melhor_dist = float("inf")
        melhor_idx = 0
        for i, p in enumerate(restantes):
            pt = p.ponto_inicio
            dist = math.hypot(pt[0] - atual[0], pt[1] - atual[1])
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_idx = i
        escolhido = restantes.pop(melhor_idx)
        ordenados.append(escolhido)
        atual = escolhido.ponto_fim

    return ordenados


def classificar_percursos(
    polilinhas: Sequence[Sequence[Tuple[float, float]]],
    raio_max_furo_mm: float = 8.0,
) -> List[PercursoCorte]:
    """
    Classifica topologicamente um conjunto de polilinhas em:
      - FURO: círculos/polígonos com raio equivalente <= raio_max_furo_mm (<= 8mm).
      - CORTE_INTERNO: polígonos aninhados dentro de outros polígonos.
      - CORTE_EXTERNO: polígonos raiz (não contidos em nenhum outro polígono).
    """
    itens: List[Dict[str, Any]] = []

    for idx, poli in enumerate(polilinhas):
        if not poli:
            continue
        pts = list(poli)
        # Fecha se os extremos forem coincidentes ou quase coincidentes
        fechado = len(pts) >= 3
        if fechado and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
            pts.append(pts[0])

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        w, h = x1 - x0, y1 - y0
        raio_estimado = max(w, h) / 2.0
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0

        # Verifica critério de furo: raio estimado <= 8.0 mm
        e_furo = fechado and (raio_estimado <= raio_max_furo_mm + 1e-4)

        itens.append({
            "idx": idx,
            "pontos": pts,
            "fechado": fechado,
            "caixa": (x0, y0, x1, y1),
            "raio": raio_estimado,
            "centro": (cx, cy),
            "e_furo": e_furo,
        })

    # Classificação topológica de polígonos não-furo (aninhamento)
    resultado: List[PercursoCorte] = []
    nao_furos = [it for it in itens if not it["e_furo"]]

    for it in itens:
        if it["e_furo"]:
            tipo = TipoEntidadeCorte.FURO
            raio = it["raio"]
            centro = it["centro"]
        else:
            # Conta por quantos polígonos não-furo este polígono é envolvido
            x0, y0, x1, y1 = it["caixa"]
            pt_teste = it["pontos"][0]
            nivel = 0

            for outro in nao_furos:
                if outro["idx"] == it["idx"]:
                    continue
                ox0, oy0, ox1, oy1 = outro["caixa"]
                if ox0 <= x0 and oy0 <= y0 and ox1 >= x1 and oy1 >= y1:
                    if ponto_em_poligono(pt_teste, outro["pontos"]):
                        nivel += 1

            # Nível > 0 indica que está dentro de outra peça -> CORTE_INTERNO
            # Nível == 0 indica polígono raiz -> CORTE_EXTERNO
            tipo = TipoEntidadeCorte.CORTE_INTERNO if nivel > 0 else TipoEntidadeCorte.CORTE_EXTERNO
            raio = None
            centro = it["centro"]

        percurso = PercursoCorte(
            tipo=tipo,
            pontos=it["pontos"],
            fechado=it["fechado"],
            raio=raio,
            centro=centro,
            id_entidade=f"{tipo.value}_{it['idx'] + 1:03d}",
        )
        resultado.append(percurso)

    return resultado


@dataclasses.dataclass
class PlanoCorte:
    """
    Plano consolidado de usinagem CNC para chapas e lotes de produção.
    Garante a ordenação inviolável: FUROS -> CORTE_INTERNO -> CORTE_EXTERNO.
    """

    percursos: List[PercursoCorte] = dataclasses.field(default_factory=list)
    largura_chapa: float = 1220.0
    altura_chapa: float = 2440.0
    material: str = "MDF"
    espessura: float = 10.0
    nome_arquivo: str = ""

    def ordenar_percursos(
        self,
        ponto_inicial: Tuple[float, float] = (0.0, 0.0),
    ) -> List[PercursoCorte]:
        """
        Executa a ordenação inviolável de usinagem com otimização TSP:
          1º: Todos os FUROS (peça presa com segurança na chapa)
          2º: Todos os CORTES INTERNOS (recortes de letras, furos grandes e sanca)
          3º: Todos os CORTES EXTERNOS (quando a peça se desprende)
        """
        furos = [p for p in self.percursos if p.tipo == TipoEntidadeCorte.FURO]
        internos = [p for p in self.percursos if p.tipo == TipoEntidadeCorte.CORTE_INTERNO]
        externos = [p for p in self.percursos if p.tipo == TipoEntidadeCorte.CORTE_EXTERNO]

        # 1º Estágio: FUROS com Nearest Neighbor
        furos_ord = otimizar_vizinho_mais_proximo(furos, ponto_inicial)
        pos_atual = furos_ord[-1].ponto_fim if furos_ord else ponto_inicial

        # 2º Estágio: CORTES INTERNOS com Nearest Neighbor a partir da última posição
        internos_ord = otimizar_vizinho_mais_proximo(internos, pos_atual)
        pos_atual = internos_ord[-1].ponto_fim if internos_ord else pos_atual

        # 3º Estágio: CORTES EXTERNOS com Nearest Neighbor
        externos_ord = otimizar_vizinho_mais_proximo(externos, pos_atual)

        ordenados = furos_ord + internos_ord + externos_ord
        self.percursos = ordenados
        return ordenados

    @property
    def percursos_ordenados(self) -> List[PercursoCorte]:
        """Retorna uma cópia da lista ordenada com a hierarquia inviolável."""
        return self.ordenar_percursos()

    def contagem_por_tipo(self) -> Dict[TipoEntidadeCorte, int]:
        """Retorna contagem de entidades por tipo."""
        res = {
            TipoEntidadeCorte.FURO: 0,
            TipoEntidadeCorte.CORTE_INTERNO: 0,
            TipoEntidadeCorte.CORTE_EXTERNO: 0,
        }
        for p in self.percursos:
            res[p.tipo] = res.get(p.tipo, 0) + 1
        return res

    def resumo(self) -> Dict[str, Any]:
        """Resumo executivo do plano de corte."""
        contagens = self.contagem_por_tipo()
        comp_total = sum(p.comprimento_total for p in self.percursos)
        return {
            "nome_arquivo": self.nome_arquivo,
            "material": self.material,
            "espessura_mm": self.espessura,
            "largura_chapa_mm": self.largura_chapa,
            "altura_chapa_mm": self.altura_chapa,
            "total_percursos": len(self.percursos),
            "furos": contagens[TipoEntidadeCorte.FURO],
            "cortes_internos": contagens[TipoEntidadeCorte.CORTE_INTERNO],
            "cortes_externos": contagens[TipoEntidadeCorte.CORTE_EXTERNO],
            "comprimento_total_corte_mm": round(comp_total, 2),
        }


def _par(codigo: int, valor: Any) -> str:
    return f"{codigo}\n{valor}\n"


def exportar_dxf_estruturado(
    plano: PlanoCorte,
    caminho_saida: Union[str, pathlib.Path],
) -> pathlib.Path:
    """
    Exporta o plano de corte em formato DXF R12 ASCII com 3 camadas semânticas estritas:
      - FUROS
      - CORTE_INTERNO
      - CORTE_EXTERNO
    Compatível com CNC-CAM C++, Aspire, Zünd, Kongsberg e AutoCAD.
    """
    caminho = pathlib.Path(caminho_saida)
    percursos_ordenados = plano.ordenar_percursos()

    # Camadas declaradas na ordem canônica
    camadas = [
        (CAMADA_DXF_FUROS, 1),       # 1 = Vermelho
        (CAMADA_DXF_INTERNO, 2),     # 2 = Amarelo
        (CAMADA_DXF_EXTERNO, 3),     # 3 = Verde
    ]

    partes = [
        _par(0, "SECTION"), _par(2, "HEADER"),
        _par(9, "$ACADVER"), _par(1, "AC1009"),
        _par(9, "$INSUNITS"), _par(70, 4),          # 4 = milímetros
        _par(9, "$MEASUREMENT"), _par(70, 1),      # 1 = métrico
        _par(0, "ENDSEC"),
        _par(0, "SECTION"), _par(2, "TABLES"),
        _par(0, "TABLE"), _par(2, "LAYER"), _par(70, len(camadas)),
    ]

    for nome_camada, cor_acad in camadas:
        partes += [
            _par(0, "LAYER"), _par(2, nome_camada),
            _par(70, 0),
            _par(62, cor_acad),
            _par(6, "CONTINUOUS"),
        ]

    partes += [
        _par(0, "ENDTAB"), _par(0, "ENDSEC"),
        _par(0, "SECTION"), _par(2, "BLOCKS"),
        _par(0, "ENDSEC"),
        _par(0, "SECTION"), _par(2, "ENTITIES"),
    ]

    for p in percursos_ordenados:
        camada = MAPA_TIPO_CAMADA.get(p.tipo, CAMADA_DXF_EXTERNO)
        pts = p.pontos
        fechado = p.fechado and len(pts) >= 3

        partes += [
            _par(0, "POLYLINE"), _par(8, camada),
            _par(66, 1),
            _par(70, 1 if fechado else 0),
        ]
        # Se for fechado e o último vértice for repetido, omite na emissão
        vertices = pts[:-1] if (fechado and len(pts) > 3 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-4) else pts
        for x, y in vertices:
            partes += [
                _par(0, "VERTEX"), _par(8, camada),
                _par(10, f"{x:.4f}"), _par(20, f"{y:.4f}"), _par(30, "0.0"),
            ]
        partes += [_par(0, "SEQEND"), _par(8, camada)]

    partes += [_par(0, "ENDSEC"), _par(0, "EOF")]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("".join(partes), encoding="ascii")
    return caminho


def exportar_gcode(
    plano: PlanoCorte,
    caminho_saida: Union[str, pathlib.Path],
    parametros: Optional[ParametrosUsinagem] = None,
) -> pathlib.Path:
    """
    Gera e exporta o arquivo de usinagem G-Code ISO 6983 a partir do PlanoCorte.
    """
    caminho = pathlib.Path(caminho_saida)
    p = parametros or ParametrosUsinagem(profundidade_total_mm=plano.espessura)
    gerador = GeradorGCodeISO(p)

    # Garante ordenação inviolável
    percursos_ordenados = plano.ordenar_percursos()
    conteudo_gcode = gerador.gerar_gcode(percursos_ordenados, p)

    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo_gcode, encoding="ascii")
    return caminho


def exportar_conector_cnccam(
    plano: PlanoCorte,
    caminho_saida: Union[str, pathlib.Path],
) -> pathlib.Path:
    """
    Exporta metadados de lote e geometria estruturada no formato conector para o CNC-CAM C++.
    Permite importação direta de ferramentas, camadas, hierarquia de furos e cortes sem Aspire.
    """
    caminho = pathlib.Path(caminho_saida)
    percursos_ordenados = plano.ordenar_percursos()
    resumo = plano.resumo()

    dados_conector = {
        "versao_conector": "1.0",
        "aplicacao": "CNC-CAM Autonomo / etiquetas_python",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "metadados": {
            "nome_arquivo": plano.nome_arquivo,
            "material": plano.material,
            "espessura_mm": plano.espessura,
            "largura_chapa_mm": plano.largura_chapa,
            "altura_chapa_mm": plano.altura_chapa,
            "total_percursos": len(percursos_ordenados),
            "contagem": {
                "furos": resumo["furos"],
                "cortes_internos": resumo["cortes_internos"],
                "cortes_externos": resumo["cortes_externos"],
            },
            "comprimento_total_corte_mm": resumo["comprimento_total_corte_mm"],
        },
        "percursos": [
            {
                "ordem": idx,
                "id": p.id_entidade or f"PERC_{idx + 1:03d}",
                "tipo": p.tipo.value,
                "camada_dxf": MAPA_TIPO_CAMADA.get(p.tipo, CAMADA_DXF_EXTERNO),
                "fechado": p.fechado,
                "raio_mm": p.raio,
                "centro": p.obter_centro(),
                "caixa_delimitadora": {
                    "min_x": round(p.caixa[0], 4),
                    "min_y": round(p.caixa[1], 4),
                    "max_x": round(p.caixa[2], 4),
                    "max_y": round(p.caixa[3], 4),
                },
                "comprimento_mm": p.comprimento_total,
                "num_pontos": len(p.pontos),
                "pontos": [[round(pt[0], 4), round(pt[1], 4)] for pt in p.pontos],
            }
            for idx, p in enumerate(percursos_ordenados)
        ],
    }

    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados_conector, indent=2, ensure_ascii=False), encoding="utf-8")
    return caminho


def extrair_plano_de_pdf(
    caminho_pdf: Union[str, pathlib.Path],
    espessura: float = 10.0,
    material: str = "MDF",
    raio_max_furo_mm: float = 8.0,
) -> PlanoCorte:
    """
    Extrai contornos vetoriais de PDF (via corte_dxf) e gera um PlanoCorte classificado.
    """
    caminho = pathlib.Path(caminho_pdf)
    import corte_dxf

    polilinhas, _ = corte_dxf.extrair_contornos(caminho)
    percursos = classificar_percursos(polilinhas, raio_max_furo_mm=raio_max_furo_mm)
    plano = PlanoCorte(
        percursos=percursos,
        material=material,
        espessura=espessura,
        nome_arquivo=caminho.name,
    )
    plano.ordenar_percursos()
    return plano
