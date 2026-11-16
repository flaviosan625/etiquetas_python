"""
motor_pdf/geometria.py — Transformações afins 2D, cálculo de BoundingBox e curvas de Bézier.

Implementa:
  - Matriz2D: matriz afim 3x3 no padrão PDF (a b c d e f cm).
  - BoundingBox: acumulador de limites retangulares com interseção de clipping.
  - Calculador exato de extremos de curvas de Bézier cúbicas via derivadas analíticas.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from .leitor import Caixa


class Matriz2D:
    """
    Matriz de transformação afim 2D no formato padrão PDF:
      [ a  b  0 ]
      [ c  d  0 ]
      [ e  f  1 ]
    """
    __slots__ = ("a", "b", "c", "d", "e", "f")

    def __init__(self, a: float = 1.0, b: float = 0.0, c: float = 0.0, d: float = 1.0, e: float = 0.0, f: float = 0.0):
        self.a = float(a)
        self.b = float(b)
        self.c = float(c)
        self.d = float(d)
        self.e = float(e)
        self.f = float(f)

    @classmethod
    def identidade(cls) -> "Matriz2D":
        return cls(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def multiplicar(self, outra: "Matriz2D") -> "Matriz2D":
        """Multiplica self por outra matriz (self x outra)."""
        return Matriz2D(
            self.a * outra.a + self.b * outra.c,
            self.a * outra.b + self.b * outra.d,
            self.c * outra.a + self.d * outra.c,
            self.c * outra.b + self.d * outra.d,
            self.e * outra.a + self.f * outra.c + outra.e,
            self.e * outra.b + self.f * outra.d + outra.f,
        )

    def transformar_ponto(self, x: float, y: float) -> Tuple[float, float]:
        """Aplica a transformação afim em um ponto (x, y)."""
        return (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )

    def __repr__(self):
        return f"Matriz2D({self.a:.4f}, {self.b:.4f}, {self.c:.4f}, {self.d:.4f}, {self.e:.4f}, {self.f:.4f})"


class BoundingBox:
    """Acumulador retangular de limites geométricos [x0, y0, x1, y1]."""
    __slots__ = ("x0", "y0", "x1", "y1", "vazio")

    def __init__(self, x0: Optional[float] = None, y0: Optional[float] = None, x1: Optional[float] = None, y1: Optional[float] = None):
        if x0 is not None and y0 is not None and x1 is not None and y1 is not None:
            self.x0 = float(min(x0, x1))
            self.y0 = float(min(y0, y1))
            self.x1 = float(max(x0, x1))
            self.y1 = float(max(y0, y1))
            self.vazio = False
        else:
            self.x0 = float("inf")
            self.y0 = float("inf")
            self.x1 = float("-inf")
            self.y1 = float("-inf")
            self.vazio = True

    def adicionar_ponto(self, x: float, y: float):
        if x < self.x0: self.x0 = x
        if y < self.y0: self.y0 = y
        if x > self.x1: self.x1 = x
        if y > self.y1: self.y1 = y
        self.vazio = False

    def adicionar_retangulo(self, x0: float, y0: float, x1: float, y1: float):
        self.adicionar_ponto(min(x0, x1), min(y0, y1))
        self.adicionar_ponto(max(x0, x1), max(y0, y1))

    def adicionar_outro(self, outro: "BoundingBox"):
        if not outro.vazio:
            self.adicionar_ponto(outro.x0, outro.y0)
            self.adicionar_ponto(outro.x1, outro.y1)

    def intersecao(self, outro: "BoundingBox") -> "BoundingBox":
        """Calcula a interseção entre dois retângulos (usado para máscaras de recorte / clipping)."""
        if self.vazio or outro.vazio:
            return BoundingBox()
        nx0 = max(self.x0, outro.x0)
        ny0 = max(self.y0, outro.y0)
        nx1 = min(self.x1, outro.x1)
        ny1 = min(self.y1, outro.y1)
        if nx0 <= nx1 and ny0 <= ny1:
            return BoundingBox(nx0, ny0, nx1, ny1)
        return BoundingBox()

    def para_caixa(self) -> Caixa:
        if self.vazio:
            return Caixa(0, 0, 0, 0)
        return Caixa(self.x0, self.y0, self.x1, self.y1)

    def __repr__(self):
        if self.vazio:
            return "BoundingBox(VAZIO)"
        return f"BoundingBox({self.x0:.2f}, {self.y0:.2f}, {self.x1:.2f}, {self.y1:.2f})"


def extremos_bezier_1d(p0: float, p1: float, p2: float, p3: float) -> List[float]:
    """
    Encontra os valores de t em [0, 1] onde a derivada da curva de Bézier cúbica é zero.
    B'(t) = 3(1-t)^2(p1 - p0) + 6(1-t)t(p2 - p1) + 3t^2(p3 - p2) = A*t^2 + B*t + C
    """
    a = 3.0 * (-p0 + 3.0 * p1 - 3.0 * p2 + p3)
    b = 6.0 * (p0 - 2.0 * p1 + p2)
    c = 3.0 * (p1 - p0)

    ts = [0.0, 1.0]

    # Derivada linear (A ~ 0)
    if abs(a) < 1e-9:
        if abs(b) > 1e-9:
            t = -c / b
            if 0.0 < t < 1.0:
                ts.append(t)
        return ts

    # Derivada quadrática
    delta = b * b - 4.0 * a * c
    if delta >= 0.0:
        sqrt_delta = math.sqrt(delta)
        t1 = (-b + sqrt_delta) / (2.0 * a)
        t2 = (-b - sqrt_delta) / (2.0 * a)
        if 0.0 < t1 < 1.0:
            ts.append(t1)
        if 0.0 < t2 < 1.0:
            ts.append(t2)

    return ts


def ponto_bezier(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Calcula o valor B(t) de uma curva de Bézier cúbica unidimensional."""
    u = 1.0 - t
    return (u * u * u * p0) + (3.0 * u * u * t * p1) + (3.0 * u * t * t * p2) + (t * t * t * p3)


def adicionar_bezier_ao_bbox(
    bbox: BoundingBox,
    x0: float, y0: float,
    x1: float, y1: float,
    x2: float, y2: float,
    x3: float, y3: float,
):
    """Calcula os limites exatos de um segmento de curva de Bézier cúbica e adiciona ao BoundingBox."""
    ts_x = extremos_bezier_1d(x0, x1, x2, x3)
    ts_y = extremos_bezier_1d(y0, y1, y2, y3)

    for t in ts_x:
        bbox.adicionar_ponto(ponto_bezier(x0, x1, x2, x3, t), ponto_bezier(y0, y1, y2, y3, t))
    for t in ts_y:
        bbox.adicionar_ponto(ponto_bezier(x0, x1, x2, x3, t), ponto_bezier(y0, y1, y2, y3, t))
