"""
Canvas WYSIWYG Interativo com PySide6 / QGraphicsView para Montagem de Bobina/Chapa.

Recursos:
- Renderização visual aperfeiçoada de rolo de mídia industrial contínuo com sombra suave.
- Zonas de presilha e linhas tracejadas de margem de segurança lateral e topo da máquina.
- Réguas de medição dinâmica métrica em cm/m ajustadas ao zoom com marcações legíveis a cada 10cm, 50cm, 1m.
- Guia reticular do cursor do mouse em tempo real sobre as réguas métricas.
- PecaGraficaItem com movimentação livre, rotação 90 graus (tecla R / menu) e
  detecção de colisão em tempo real (destaque azul elétrico para seleção e vermelho vivo para colisão).
- Substrato das peças com efeito realista de elevação e chanfro 3D.
- Miniatura de arte renderizada perfeitamente nítida (Anti-aliasing + SmoothPixmapTransform).
- Tarja de informações inferior ultra-legível com nome, material, dimensões e rotação.
- Cálculo contínuo de métricas de aproveitamento e comprimento linear.
"""

from typing import Optional, List, Dict, Any, Union
import math
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QObject, QEvent
from PySide6.QtWidgets import (
    QWidget,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsObject,
    QMenu,
    QToolTip,
)
from PySide6.QtGui import (
    QPainter,
    QPen,
    QBrush,
    QColor,
    QFont,
    QWheelEvent,
    QMouseEvent,
    QKeyEvent,
    QPixmap,
    QAction,
    QPolygonF,
    QPainterPath,
    QLinearGradient,
)

from ui.tema import CoresTema


class PecaGraficaItem(QGraphicsObject):
    """
    Representação visual e interativa de uma peça a ser montada na bobina/chapa.
    """

    posicao_alterada = Signal(object, QPointF)
    colisao_alterada = Signal(object, bool)
    rotacao_alterada = Signal(object, float)

    def __init__(
        self,
        nome: str,
        largura_mm: float,
        altura_mm: float,
        id_peca: Optional[str] = None,
        miniatura: Optional[QPixmap] = None,
        caminho_arquivo: Optional[Union[str, Path]] = None,
        material: str = "VINIL",
        quantidade: int = 1,
        metadados: Optional[Dict[str, Any]] = None,
        parent: Optional[QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.id_peca = id_peca or str(uuid.uuid4())[:8]
        self.nome = nome
        self.largura_mm = float(largura_mm)
        self.altura_mm = float(altura_mm)
        self.miniatura = miniatura
        self.caminho_arquivo = str(caminho_arquivo) if caminho_arquivo else None
        self.material = str(material).upper()
        self.quantidade = int(quantidade)
        self.metadados = metadados or {}

        self.rotacao = 0.0  # 0, 90, 180, 270 graus
        self.tem_colisao = False
        self.fora_dos_limites = False

        # Se não forneceu miniatura mas forneceu o caminho do arquivo, carrega agora
        if (self.miniatura is None or self.miniatura.isNull()) and self.caminho_arquivo:
            self._carregar_miniatura_arquivo()

        # Configurar flags de interação
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
            | QGraphicsItem.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)
        self.setTransformOriginPoint(self.largura_mm / 2.0, self.altura_mm / 2.0)
        self.setToolTip(f"{self.nome}\n{self.material} • {self.largura_mm:.1f} × {self.altura_mm:.1f} mm")

    def _carregar_miniatura_arquivo(self) -> None:
        """Gera ou carrega miniatura real do arquivo (PDF ou imagem) sem travar."""
        if not self.caminho_arquivo:
            return
        p = Path(self.caminho_arquivo)
        if not p.is_file():
            return
        try:
            import miniaturas
            dados = miniaturas.obter(p, lado=500)
            if dados:
                pix = QPixmap()
                if pix.loadFromData(dados) and not pix.isNull():
                    self.miniatura = pix
                    return
        except Exception:
            pass
        # Fallback direto caso seja imagem comum
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"):
            try:
                pix = QPixmap(str(p))
                if not pix.isNull():
                    self.miniatura = pix
            except Exception:
                pass

    def boundingRect(self) -> QRectF:
        """Retorna o retângulo delimitador da peça em mm."""
        return QRectF(0.0, 0.0, self.largura_mm, self.altura_mm)

    def girar_90_graus(self) -> None:
        """Gira a peça 90 graus no sentido horário."""
        self.rotacao = (self.rotacao + 90.0) % 360.0
        self.setRotation(self.rotacao)
        self.rotacao_alterada.emit(self, self.rotacao)
        self.atualizar_colisao()
        self.update()

    def set_estado_colisao(self, tem_colisao: bool, fora_dos_limites: bool) -> None:
        """Atualiza os indicadores de colisão e dispara sinal caso tenha mudado."""
        mudou = (self.tem_colisao != tem_colisao) or (self.fora_dos_limites != fora_dos_limites)
        self.tem_colisao = tem_colisao
        self.fora_dos_limites = fora_dos_limites
        if mudou:
            self.colisao_alterada.emit(self, self.tem_colisao or self.fora_dos_limites)
            self.update()

    def atualizar_colisao(self) -> None:
        """Verifica colisões contra outras peças e contra os limites úteis da cena."""
        cena = self.scene()
        if not cena:
            return

        # 1. Colisão com outras peças
        outros_itens = self.collidingItems(Qt.IntersectsItemShape)
        colisao_com_pecas = any(isinstance(it, PecaGraficaItem) and it != self for it in outros_itens)

        # 2. Ultrapassagem dos limites úteis da bobina
        fora = False
        view = self._obter_view()
        if view and hasattr(view, "obter_limites_uteis"):
            limites = view.obter_limites_uteis()
            rect_cena = self.sceneBoundingRect()
            # Deve estar estritamente dentro da área útil
            tolerancia = 0.05
            if (
                rect_cena.left() < limites.left() - tolerancia
                or rect_cena.right() > limites.right() + tolerancia
                or rect_cena.top() < limites.top() - tolerancia
            ):
                fora = True

        self.set_estado_colisao(colisao_com_pecas, fora)

    def _obter_view(self) -> Optional["CanvasMontagem"]:
        """Obtém a instância da view CanvasMontagem associada."""
        cena = self.scene()
        if cena and cena.views():
            v = cena.views()[0]
            if isinstance(v, CanvasMontagem):
                return v
        return None

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        """Interrompe ou monitora mudanças de posição."""
        ret = super().itemChange(change, value)
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.posicao_alterada.emit(self, self.pos())
            view = self._obter_view()
            if view and not getattr(view, "_atualizando_colisoes", False):
                view.ao_mover_peca(self)
        return ret

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Atalho de teclado para rotação rápida ('R')."""
        if event.key() == Qt.Key_R:
            self.girar_90_graus()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Menu de contexto via botão direito."""
        menu = QMenu()
        acao_girar = menu.addAction("Girar 90° (Tecla R)")
        acao_girar.triggered.connect(self.girar_90_graus)

        acao_remover = menu.addAction("Remover da Bobina")
        view = self._obter_view()
        if view:
            acao_remover.triggered.connect(lambda: view.remover_peca(self))

        menu.exec(event.screenPos())

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """
        Desenha a peça gráfica com substrato elevado, miniatura nítida,
        tarja de informações ultra-legível e realce interativo de colisão/seleção.
        """
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = self.boundingRect()
        tem_problema = self.tem_colisao or self.fora_dos_limites

        # ---------------------------------------------------------------------
        # 1. Substrato Físico com Efeito Sutil de Sombra e Elevação 3D
        # ---------------------------------------------------------------------
        path_peca = QPainterPath()
        path_peca.addRoundedRect(rect, 4.0, 4.0)

        # Gradiente suave de substrato vinil acetinado
        grad_substrato = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad_substrato.setColorAt(0.0, QColor("#ffffff"))
        grad_substrato.setColorAt(1.0, QColor("#f8fafc"))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad_substrato))
        painter.drawPath(path_peca)

        # Chanfro / Chanfradura sutil de elevação física do vinil (espessura do material)
        # Borda superior e esquerda com reflexo de luz
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.0))
        painter.drawLine(QPointF(rect.left() + 4.0, rect.top() + 1.0), QPointF(rect.right() - 4.0, rect.top() + 1.0))
        painter.drawLine(QPointF(rect.left() + 1.0, rect.top() + 4.0), QPointF(rect.left() + 1.0, rect.bottom() - 4.0))

        # Borda inferior e direita com sombra sutil de relevo
        painter.setPen(QPen(QColor(148, 163, 184, 150), 1.2))
        painter.drawLine(QPointF(rect.left() + 4.0, rect.bottom() - 1.0), QPointF(rect.right() - 4.0, rect.bottom() - 1.0))
        painter.drawLine(QPointF(rect.right() - 1.0, rect.top() + 4.0), QPointF(rect.right() - 1.0, rect.bottom() - 4.0))

        # ---------------------------------------------------------------------
        # 2. Miniatura de Arte Renderizada Perfeitamente Nítida
        # ---------------------------------------------------------------------
        if (self.miniatura is None or self.miniatura.isNull()) and self.caminho_arquivo:
            self._carregar_miniatura_arquivo()

        altura_tarja = min(24.0, max(14.0, rect.height() * 0.20))
        margem_interna = 2.5
        rect_arte = QRectF(
            rect.x() + margem_interna,
            rect.y() + margem_interna,
            rect.width() - (2.0 * margem_interna),
            rect.height() - altura_tarja - margem_interna - 1.5,
        )

        if self.miniatura and not self.miniatura.isNull():
            if rect_arte.width() > 4 and rect_arte.height() > 4:
                pix_w = self.miniatura.width()
                pix_h = self.miniatura.height()
                if pix_w > 0 and pix_h > 0:
                    escala = min(rect_arte.width() / pix_w, rect_arte.height() / pix_h)
                    w_alvo = pix_w * escala
                    h_alvo = pix_h * escala
                    x_alvo = rect_arte.x() + (rect_arte.width() - w_alvo) / 2.0
                    y_alvo = rect_arte.y() + (rect_arte.height() - h_alvo) / 2.0
                    target_rect = QRectF(x_alvo, y_alvo, w_alvo, h_alvo)

                    # Fundo branco e projeção nítida em resolução total da tela
                    painter.fillRect(target_rect, QColor("#ffffff"))
                    painter.drawPixmap(target_rect, self.miniatura, QRectF(self.miniatura.rect()))

                    # Filete sutil de acabamento ao redor da arte
                    painter.setPen(QPen(QColor("#cbd5e1"), 0.6))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(target_rect)
        elif rect_arte.width() > 20 and rect_arte.height() > 15:
            # Placeholder CAD vetorial limpo
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#f1f5f9")))
            painter.drawRoundedRect(rect_arte, 2.0, 2.0)

            # Grid sutil de blueprint
            painter.setPen(QPen(QColor("#e2e8f0"), 0.8, Qt.DotLine))
            centro_x = rect_arte.center().x()
            centro_y = rect_arte.center().y()
            painter.drawLine(QPointF(rect_arte.left(), centro_y), QPointF(rect_arte.right(), centro_y))
            painter.drawLine(QPointF(centro_x, rect_arte.top()), QPointF(centro_x, rect_arte.bottom()))

            # Informação textual central
            painter.setPen(QColor("#64748b"))
            tam_fonte_ph = max(6, int(min(rect_arte.width(), rect_arte.height()) * 0.12))
            painter.setFont(QFont("Segoe UI", min(tam_fonte_ph, 11), QFont.Bold))
            painter.drawText(
                rect_arte,
                Qt.AlignCenter,
                f"{self.material}\n{self.largura_mm:.0f} × {self.altura_mm:.0f} mm",
            )

        # ---------------------------------------------------------------------
        # 3. Tarja Inferior Ultra-Legível com Nome, Material e Dimensões
        # ---------------------------------------------------------------------
        rect_tarja = QRectF(rect.x(), rect.bottom() - altura_tarja, rect.width(), altura_tarja)
        path_tarja_rect = QPainterPath()
        path_tarja_rect.addRect(rect_tarja)
        # Interseção garante que a tarja herde com perfeição os cantos arredondados inferiores
        path_tarja = path_peca.intersected(path_tarja_rect)

        if tem_problema:
            grad_tarja = QLinearGradient(rect_tarja.topLeft(), rect_tarja.bottomLeft())
            grad_tarja.setColorAt(0.0, QColor("#991b1b"))
            grad_tarja.setColorAt(1.0, QColor("#7f1d1d"))
            cor_borda_tarja = QColor("#ef4444")
            cor_texto_tarja = QColor("#ffffff")
        elif self.isSelected():
            grad_tarja = QLinearGradient(rect_tarja.topLeft(), rect_tarja.bottomLeft())
            grad_tarja.setColorAt(0.0, QColor("#0c2340"))
            grad_tarja.setColorAt(1.0, QColor("#0f172a"))
            cor_borda_tarja = QColor("#0ea5e9")
            cor_texto_tarja = QColor("#38bdf8")
        else:
            grad_tarja = QLinearGradient(rect_tarja.topLeft(), rect_tarja.bottomLeft())
            grad_tarja.setColorAt(0.0, QColor("#1e293b"))
            grad_tarja.setColorAt(1.0, QColor("#0f172a"))
            cor_borda_tarja = QColor("#334155")
            cor_texto_tarja = QColor("#f8fafc")

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad_tarja))
        painter.drawPath(path_tarja)

        # Linha divisória superior da tarja
        painter.setPen(QPen(cor_borda_tarja, 1.0))
        painter.drawLine(rect_tarja.topLeft(), rect_tarja.topRight())

        # Formatação de texto da tarja
        texto_dim = f"{self.largura_mm:.0f}×{self.altura_mm:.0f}mm"
        if self.rotacao > 0:
            texto_dim += f" (↻{self.rotacao:.0f}°)"

        texto_exibicao = f"{self.nome} | {self.material} | {texto_dim}"

        tam_fonte_tarja = max(6, int(altura_tarja * 0.44))
        fonte_tarja = QFont("Segoe UI", min(tam_fonte_tarja, 10), QFont.Bold)
        painter.setFont(fonte_tarja)
        painter.setPen(cor_texto_tarja)
        margem_texto = 4.0
        rect_texto = rect_tarja.adjusted(margem_texto, 0, -margem_texto, 0)
        texto_formatado = painter.fontMetrics().elidedText(texto_exibicao, Qt.ElideRight, int(rect_texto.width()))
        painter.drawText(rect_texto, Qt.AlignVCenter | Qt.AlignLeft, texto_formatado)

        # ---------------------------------------------------------------------
        # 4. Borda de Destaque Interativa / Seleção / Alerta de Colisão
        # ---------------------------------------------------------------------
        if tem_problema:
            # Vermelho Vivo de Perigo / Alerta de Colisão
            cor_borda = QColor(CoresTema.PERIGO)
            painter.setPen(QPen(cor_borda, 2.8, Qt.SolidLine))
            cor_overlay = QColor(239, 68, 68, 45)
            painter.setBrush(QBrush(cor_overlay))
            painter.drawPath(path_peca)

            # Alerta visual em banner central de alta visibilidade
            if rect_arte.width() > 60 and rect_arte.height() > 22:
                aviso = "COLISÃO DETECTADA!" if self.tem_colisao else "FORA DA ÁREA ÚTIL!"
                w_banner = min(rect_arte.width() - 8.0, 220.0)
                h_banner = min(rect_arte.height() - 8.0, 26.0)
                rect_banner = QRectF(
                    rect_arte.center().x() - (w_banner / 2.0),
                    rect_arte.center().y() - (h_banner / 2.0),
                    w_banner,
                    h_banner,
                )
                painter.setPen(QPen(QColor("#fca5a5"), 1.2))
                painter.setBrush(QBrush(QColor("#7f1d1d")))
                painter.drawRoundedRect(rect_banner, 4.0, 4.0)

                painter.setPen(QColor("#ffffff"))
                tam_aviso = max(7, int(h_banner * 0.44))
                fonte_aviso = QFont("Segoe UI", min(tam_aviso, 11), QFont.Black)
                painter.setFont(fonte_aviso)
                painter.drawText(rect_banner, Qt.AlignCenter, f"⚠ {aviso}")

        elif self.isSelected():
            # Azul Brilhante Elétrico de Seleção Interativa
            cor_borda = QColor(CoresTema.ACENTO_PRIMARIO)
            painter.setPen(QPen(cor_borda, 2.5, Qt.SolidLine))
            cor_overlay = QColor(14, 165, 233, 35)
            painter.setBrush(QBrush(cor_overlay))
            painter.drawPath(path_peca)

            # Alças de Seleção CAD/CAM nos 4 cantos
            tam_alca = min(6.0, min(rect.width(), rect.height()) * 0.12)
            meia_alca = tam_alca / 2.0
            pontos_alcas = [
                QPointF(rect.left(), rect.top()),
                QPointF(rect.right(), rect.top()),
                QPointF(rect.left(), rect.bottom()),
                QPointF(rect.right(), rect.bottom()),
            ]
            painter.setPen(QPen(QColor("#0ea5e9"), 1.5))
            painter.setBrush(QBrush(QColor("#ffffff")))
            for pt in pontos_alcas:
                painter.drawRect(QRectF(pt.x() - meia_alca, pt.y() - meia_alca, tam_alca, tam_alca))

        else:
            # Estado Normal: Contorno de Faca/Corte CNC em Azul Técnico
            cor_borda = QColor("#0284c7")
            painter.setPen(QPen(cor_borda, 1.2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path_peca)

            # Marcas de Corte L nos 4 cantos (Estilo Gráfica / Plotter CNC)
            tam_corte = min(6.0, min(rect.width(), rect.height()) * 0.10)
            if tam_corte >= 3.0:
                painter.setPen(QPen(QColor("#0284c7"), 1.2, Qt.SolidLine))
                # Canto Superior Esquerdo
                painter.drawLine(QPointF(rect.left(), rect.top()), QPointF(rect.left() + tam_corte, rect.top()))
                painter.drawLine(QPointF(rect.left(), rect.top()), QPointF(rect.left(), rect.top() + tam_corte))
                # Canto Superior Direito
                painter.drawLine(QPointF(rect.right(), rect.top()), QPointF(rect.right() - tam_corte, rect.top()))
                painter.drawLine(QPointF(rect.right(), rect.top()), QPointF(rect.right(), rect.top() + tam_corte))
                # Canto Inferior Esquerdo
                painter.drawLine(QPointF(rect.left(), rect.bottom()), QPointF(rect.left() + tam_corte, rect.bottom()))
                painter.drawLine(QPointF(rect.left(), rect.bottom()), QPointF(rect.left(), rect.bottom() - tam_corte))
                # Canto Inferior Direito
                painter.drawLine(QPointF(rect.right(), rect.bottom()), QPointF(rect.right() - tam_corte, rect.bottom()))
                painter.drawLine(QPointF(rect.right(), rect.bottom()), QPointF(rect.right(), rect.bottom() - tam_corte))


class CanvasMontagem(QGraphicsView):
    """
    Viewport WYSIWYG de alta precisão para montagem de peças sobre bobinas/chapas.
    """

    estatisticas_alteradas = Signal(dict)
    peca_selecionada = Signal(object)
    pecas_modificadas = Signal()

    def __init__(
        self,
        largura_bobina_mm: float = 1600.0,
        comprimento_inicial_mm: float = 2000.0,
        margem_lateral_mm: float = 15.0,
        margem_topo_mm: float = 15.0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._cena = QGraphicsScene(self)
        self.setScene(self._cena)

        self.largura_mm = float(largura_bobina_mm)
        self.comprimento_mm = float(comprimento_inicial_mm)
        self.margem_lateral_mm = float(margem_lateral_mm)
        self.margem_topo_mm = float(margem_topo_mm)
        self.espacamento_mm = 10.0  # Padrão: 10 mm (1.0 cm) entre peças

        self._pecas: List[PecaGraficaItem] = []
        self._espaco_pressionado = False
        self._arrastando_pan = False
        self._pos_mouse_anterior = QPointF()
        self._pos_mouse_view: Optional[QPointF] = None
        self._atualizando_colisoes = False

        self._configurar_view()
        self._atualizar_geometria_bobina()

    def _configurar_view(self) -> None:
        """Configura os parâmetros visuais e otimizações de desenho."""
        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
            | QPainter.TextAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setBackgroundBrush(QBrush(QColor(CoresTema.CANVAS_FUNDO)))
        self.setMouseTracking(True)

    def definir_espacamento(self, espacamento_mm: float) -> None:
        """Configura a distância/espaçamento em milímetros entre as artes na montagem."""
        self.espacamento_mm = max(0.0, float(espacamento_mm))

    def definir_bobina(
        self,
        largura_mm: float,
        comprimento_mm: Optional[float] = None,
        margem_lateral_mm: Optional[float] = None,
        margem_topo_mm: Optional[float] = None,
    ) -> None:
        """Redefine os parâmetros da bobina/chapa e atualiza a cena."""
        self.largura_mm = float(largura_mm)
        if comprimento_mm is not None:
            self.comprimento_mm = float(comprimento_mm)
        if margem_lateral_mm is not None:
            self.margem_lateral_mm = float(margem_lateral_mm)
        if margem_topo_mm is not None:
            self.margem_topo_mm = float(margem_topo_mm)

        self._atualizar_geometria_bobina()
        self.verificar_todas_colisoes()
        self.emitir_estatisticas()

    def obter_limites_uteis(self) -> QRectF:
        """Retorna o retângulo delimitador da área útil de corte/impressão."""
        largura_util = max(0.0, self.largura_mm - (2.0 * self.margem_lateral_mm))
        comprimento_util = max(0.0, self.comprimento_mm - self.margem_topo_mm)
        return QRectF(
            self.margem_lateral_mm,
            self.margem_topo_mm,
            largura_util,
            comprimento_util,
        )

    def _atualizar_geometria_bobina(self) -> None:
        """Recalcula a área total da cena considerando a bobina e folga ao redor."""
        # Recalcular comprimento dinâmico para acomodar peças existentes
        max_y = self.comprimento_mm
        for peca in self._pecas:
            br = peca.sceneBoundingRect()
            if br.bottom() + 100.0 > max_y:
                max_y = br.bottom() + 100.0
        self.comprimento_mm = max_y

        margem_folga = 150.0  # Folga de visualização ao redor da bobina
        rect_total = QRectF(
            -margem_folga,
            -margem_folga,
            self.largura_mm + (2.0 * margem_folga),
            self.comprimento_mm + (2.0 * margem_folga),
        )
        self.scene().setSceneRect(rect_total)
        self.scene().update()

    def adicionar_peca(
        self,
        nome: str,
        largura_mm: float,
        altura_mm: float,
        id_peca: Optional[str] = None,
        miniatura: Optional[QPixmap] = None,
        caminho_arquivo: Optional[Union[str, Path]] = None,
        material: str = "VINIL",
        quantidade: int = 1,
        pos_x: Optional[float] = None,
        pos_y: Optional[float] = None,
        metadados: Optional[Dict[str, Any]] = None,
    ) -> PecaGraficaItem:
        """Adiciona uma nova peça gráfica ao canvas."""
        peca = PecaGraficaItem(
            nome=nome,
            largura_mm=largura_mm,
            altura_mm=altura_mm,
            id_peca=id_peca,
            miniatura=miniatura,
            caminho_arquivo=caminho_arquivo,
            material=material,
            quantidade=quantidade,
            metadados=metadados,
        )

        # Posicionamento inteligente padrão caso não fornecido
        if pos_x is None or pos_y is None:
            pos_x, pos_y = self._calcular_proxima_posicao_livre(largura_mm, altura_mm)

        peca.setPos(pos_x, pos_y)
        self.scene().addItem(peca)
        self._pecas.append(peca)

        self._atualizar_geometria_bobina()
        self.verificar_todas_colisoes()
        self.emitir_estatisticas()
        self.pecas_modificadas.emit()
        return peca

    def remover_peca(self, peca: PecaGraficaItem) -> None:
        """Remove uma peça do canvas."""
        if peca in self._pecas:
            self._pecas.remove(peca)
            if peca.scene():
                peca.scene().removeItem(peca)
            self._atualizar_geometria_bobina()
            self.verificar_todas_colisoes()
            self.emitir_estatisticas()
            self.pecas_modificadas.emit()

    def limpar_pecas(self) -> None:
        """Remove todas as peças do canvas."""
        for peca in list(self._pecas):
            if peca.scene():
                peca.scene().removeItem(peca)
        self._pecas.clear()
        self._atualizar_geometria_bobina()
        self.emitir_estatisticas()
        self.pecas_modificadas.emit()

    def obter_pecas(self) -> List[PecaGraficaItem]:
        """Retorna a lista de todas as peças presentes no canvas."""
        return list(self._pecas)

    def _calcular_proxima_posicao_livre(self, largura: float, altura: float) -> tuple:
        """Determina uma posição inicial para nova peça dentro da área útil."""
        limites = self.obter_limites_uteis()
        margem = getattr(self, "espacamento_mm", 10.0)
        x = limites.left() + margem
        y = limites.top() + margem

        for p in self._pecas:
            br = p.sceneBoundingRect()
            if br.bottom() + margem > y:
                y = br.bottom() + margem

        return x, y

    def ao_mover_peca(self, peca_movida: PecaGraficaItem) -> None:
        """Handler executado continuamente enquanto uma peça é arrastada."""
        self.verificar_todas_colisoes()
        self._atualizar_geometria_bobina()
        self.emitir_estatisticas()

    def verificar_todas_colisoes(self) -> None:
        """Atualiza o estado de colisão de todas as peças da bobina."""
        self._atualizando_colisoes = True
        try:
            for p in self._pecas:
                p.atualizar_colisao()
        finally:
            self._atualizando_colisoes = False

    def calcular_estatisticas(self) -> Dict[str, Any]:
        """Calcula métricas de aproveitamento de material e metragem linear."""
        largura_m = self.largura_mm / 1000.0

        # Comprimento ocupado real pelas peças
        if not self._pecas:
            comprimento_usado_mm = 0.0
        else:
            comprimento_usado_mm = max(
                (p.sceneBoundingRect().bottom() for p in self._pecas),
                default=0.0,
            )

        comprimento_m = max(comprimento_usado_mm / 1000.0, 0.01) if self._pecas else 0.0
        area_total_m2 = largura_m * (comprimento_m if comprimento_m > 0 else (self.comprimento_mm / 1000.0))

        area_pecas_m2 = sum(
            (p.largura_mm * p.altura_mm) / 1_000_000.0 for p in self._pecas
        )

        aproveitamento_pct = (
            (area_pecas_m2 / area_total_m2 * 100.0) if area_total_m2 > 0 else 0.0
        )
        aproveitamento_pct = min(100.0, aproveitamento_pct)

        colidindo = sum(1 for p in self._pecas if (p.tem_colisao or p.fora_dos_limites))

        return {
            "largura_mm": self.largura_mm,
            "largura_m": largura_m,
            "comprimento_mm": comprimento_usado_mm,
            "comprimento_m": comprimento_m,
            "area_total_m2": area_total_m2,
            "area_pecas_m2": area_pecas_m2,
            "aproveitamento_pct": aproveitamento_pct,
            "total_pecas": len(self._pecas),
            "pecas_colidindo": colidindo,
        }

    def emitir_estatisticas(self) -> None:
        """Dispara sinal com as estatísticas atualizadas."""
        stats = self.calcular_estatisticas()
        self.estatisticas_alteradas.emit(stats)

    # -------------------------------------------------------------------------
    # Controle de Câmera, Zoom Centrado e Pan Fluido
    # -------------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom centrado na posição exata do cursor do mouse (fator 1.15)."""
        fator = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        pos_cena_antes = self.mapToScene(event.position().toPoint())

        self.scale(fator, fator)

        pos_cena_depois = self.mapToScene(event.position().toPoint())
        delta = pos_cena_depois - pos_cena_antes
        self.translate(delta.x(), delta.y())
        event.accept()

    def zoom_in(self) -> None:
        """Aumenta o zoom programaticamente no centro da view."""
        self.scale(1.15, 1.15)

    def zoom_out(self) -> None:
        """Diminui o zoom programaticamente no centro da view."""
        self.scale(1.0 / 1.15, 1.0 / 1.15)

    def reset_zoom(self) -> None:
        """Restaura a escala padrão 1:1."""
        self.resetTransform()

    def fit_in_view(self) -> None:
        """Ajusta a visão para enquadrar perfeitamente a bobina."""
        rect_bobina = QRectF(0, 0, self.largura_mm, self.comprimento_mm)
        self.fitInView(rect_bobina, Qt.KeepAspectRatio)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Detecta pressionamento da barra de espaço para modo Pan."""
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._espaco_pressionado = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        """Restaura cursor ao soltar a barra de espaço."""
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._espaco_pressionado = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Inicia pan ao clicar com botão do meio ou com espaço pressionado."""
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and self._espaco_pressionado):
            self._arrastando_pan = True
            self._pos_mouse_anterior = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Arrasta a câmera durante o pan fluido e atualiza guias reticulares das réguas."""
        if self._arrastando_pan:
            delta = event.position() - self._pos_mouse_anterior
            self._pos_mouse_anterior = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return

        self._pos_mouse_view = event.position()
        self.viewport().update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finaliza operação de pan."""
        if self._arrastando_pan and (event.button() == Qt.MiddleButton or event.button() == Qt.LeftButton):
            self._arrastando_pan = False
            self.setCursor(Qt.OpenHandCursor if self._espaco_pressionado else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Limpa guias reticulares do cursor ao sair da viewport."""
        self._pos_mouse_view = None
        self.viewport().update()
        super().leaveEvent(event)

    # -------------------------------------------------------------------------
    # Renderização da Bobina, Margens e Réguas Métricas Dinâmicas
    # -------------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Desenha a representação da mídia física e margens de corte com acabamento industrial."""
        super().drawBackground(painter, rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        # 1. Grade Técnica de Fundo da Máquina (Chão de Fábrica / Base CNC)
        pen_grade_menor = QPen(QColor("#181b25"), 0.8, Qt.DotLine)
        pen_grade_maior = QPen(QColor("#252b3b"), 1.2, Qt.SolidLine)

        x_inicio = math.floor(rect.left() / 100.0) * 100.0
        x_fim = math.ceil(rect.right() / 100.0) * 100.0
        curr_x = x_inicio
        while curr_x <= x_fim:
            is_metro = abs(curr_x % 1000.0) < 0.01
            painter.setPen(pen_grade_maior if is_metro else pen_grade_menor)
            painter.drawLine(QPointF(curr_x, rect.top()), QPointF(curr_x, rect.bottom()))
            curr_x += 100.0

        y_inicio = math.floor(rect.top() / 100.0) * 100.0
        y_fim = math.ceil(rect.bottom() / 100.0) * 100.0
        curr_y = y_inicio
        while curr_y <= y_fim:
            is_metro = abs(curr_y % 1000.0) < 0.01
            painter.setPen(pen_grade_maior if is_metro else pen_grade_menor)
            painter.drawLine(QPointF(rect.left(), curr_y), QPointF(rect.right(), curr_y))
            curr_y += 100.0

        # 2. Sombra Suave de Elevação do Rolo de Mídia sobre o Chão
        rect_midia = QRectF(0.0, 0.0, self.largura_mm, self.comprimento_mm)
        for d_off, alpha in [(10.0, 15), (7.0, 25), (4.0, 45), (2.0, 75)]:
            s_rect = QRectF(rect_midia.x() + d_off, rect_midia.y() + d_off, rect_midia.width(), rect_midia.height())
            painter.fillRect(s_rect, QColor(0, 0, 0, alpha))

        # 3. Bobina Branca Contínua (Substrato Vinil / Lona)
        grad_midia = QLinearGradient(rect_midia.topLeft(), rect_midia.bottomLeft())
        grad_midia.setColorAt(0.0, QColor("#ffffff"))
        grad_midia.setColorAt(1.0, QColor("#f8fafc"))
        painter.setBrush(QBrush(grad_midia))
        painter.setPen(QPen(QColor(CoresTema.MIDIA_BORDA), 1.5))
        painter.drawRect(rect_midia)

        # 4. Cabeçote / Eixo de Alimentação no Topo (Origem Y = 0)
        rect_alimentacao = QRectF(0.0, -18.0, self.largura_mm, 18.0)
        grad_eixo = QLinearGradient(rect_alimentacao.topLeft(), rect_alimentacao.bottomLeft())
        grad_eixo.setColorAt(0.0, QColor("#1e2433"))
        grad_eixo.setColorAt(1.0, QColor("#0f131c"))
        painter.fillRect(rect_alimentacao, QBrush(grad_eixo))
        painter.setPen(QPen(QColor("#334155"), 1.0))
        painter.drawRect(rect_alimentacao)

        painter.setPen(QColor("#94a3b8"))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(
            rect_alimentacao,
            Qt.AlignCenter,
            "▲ ENTRADA / ALIMENTAÇÃO DA BOBINA (EIXO 0,0) ▲",
        )

        # 5. Zonas de Presilha / Margem de Segurança Lateral e Topo
        rect_util = self.obter_limites_uteis()
        cor_presilha = QColor(239, 68, 68, 18)

        # Faixa Esquerda
        rect_presilha_esq = QRectF(0.0, 0.0, self.margem_lateral_mm, self.comprimento_mm)
        painter.fillRect(rect_presilha_esq, cor_presilha)

        # Faixa Direita
        rect_presilha_dir = QRectF(self.largura_mm - self.margem_lateral_mm, 0.0, self.margem_lateral_mm, self.comprimento_mm)
        painter.fillRect(rect_presilha_dir, cor_presilha)

        # Faixa Topo
        rect_presilha_topo = QRectF(self.margem_lateral_mm, 0.0, rect_util.width(), self.margem_topo_mm)
        painter.fillRect(rect_presilha_topo, cor_presilha)

        # 6. Linhas Tracejadas de Margem de Segurança da Máquina
        pen_margem = QPen(QColor(CoresTema.MARGEM_CORTE), 1.8, Qt.DashLine)
        painter.setPen(pen_margem)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect_util)

        # Rótulos técnicos nas presilhas se houver espaço
        painter.setPen(QColor("#ef4444"))
        fonte_margem = QFont("Segoe UI", 7, QFont.DemiBold)
        painter.setFont(fonte_margem)
        if self.margem_lateral_mm >= 10.0 and self.comprimento_mm >= 80.0:
            painter.save()
            painter.translate(self.margem_lateral_mm / 2.0, 50.0)
            painter.rotate(-90)
            painter.drawText(QRectF(-150, -6, 300, 12), Qt.AlignCenter, f"PRESILHA {self.margem_lateral_mm:.0f}mm")
            painter.restore()

            painter.save()
            painter.translate(self.largura_mm - (self.margem_lateral_mm / 2.0), 50.0)
            painter.rotate(-90)
            painter.drawText(QRectF(-150, -6, 300, 12), Qt.AlignCenter, f"PRESILHA {self.margem_lateral_mm:.0f}mm")
            painter.restore()

        # 7. Rótulo Informativo Superior da Mídia e Área Útil
        rect_badge = QRectF(0.0, -52.0, min(self.largura_mm, 600.0), 28.0)
        painter.setPen(QPen(QColor(CoresTema.ACENTO_PRIMARIO), 1.2))
        painter.setBrush(QBrush(QColor("#161a24")))
        painter.drawRoundedRect(rect_badge, 4.0, 4.0)

        painter.setPen(QColor(CoresTema.TEXTO_PRINCIPAL))
        fonte_info = QFont("Segoe UI", 8, QFont.Bold)
        painter.setFont(fonte_info)
        texto_midia = (
            f"  LARGURA: {self.largura_mm:.0f} mm ({self.largura_mm/1000.0:.2f}m)  |  "
            f"ÁREA ÚTIL: {rect_util.width():.0f} mm  |  "
            f"MARGENS: {self.margem_lateral_mm:.0f} mm"
        )
        painter.drawText(rect_badge, Qt.AlignVCenter | Qt.AlignLeft, texto_midia)

        # 8. Fim da Bobina / Extensão Contínua
        pen_corte = QPen(QColor("#64748b"), 1.2, Qt.DashDotLine)
        painter.setPen(pen_corte)
        y_fim_bobina = self.comprimento_mm
        painter.drawLine(QPointF(0.0, y_fim_bobina), QPointF(self.largura_mm, y_fim_bobina))

        painter.setPen(QColor("#64748b"))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(
            QRectF(0.0, y_fim_bobina + 2.0, self.largura_mm, 18.0),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"--- FIM DO COMPRIMENTO ÚTIL ATUAL ({y_fim_bobina:.0f} mm / {y_fim_bobina/1000.0:.2f} m) ---",
        )

        painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Desenha as réguas dinâmicas horizontal e vertical com marcações métricas (10cm, 50cm, 1m)."""
        super().drawForeground(painter, rect)
        painter.save()
        painter.resetTransform()  # Desenhar em coordenadas fixas de tela na viewport

        largura_view = self.viewport().width()
        altura_view = self.viewport().height()
        espessura_regua = 28

        cor_bg_regua = QColor("#12141c")
        cor_borda_regua = QColor(CoresTema.BORDA)
        fonte_regua_peq = QFont("Segoe UI", 7)
        fonte_regua_med = QFont("Segoe UI", 7, QFont.DemiBold)
        fonte_regua_destaque = QFont("Segoe UI", 8, QFont.Bold)

        # 1. Régua Horizontal (Topo)
        rect_regua_h = QRectF(espessura_regua, 0, largura_view - espessura_regua, espessura_regua)
        painter.fillRect(rect_regua_h, cor_bg_regua)
        painter.setPen(QPen(cor_borda_regua, 1.2))
        painter.drawLine(espessura_regua, espessura_regua, largura_view, espessura_regua)

        # 2. Régua Vertical (Lateral Esquerda)
        rect_regua_v = QRectF(0, espessura_regua, espessura_regua, altura_view - espessura_regua)
        painter.fillRect(rect_regua_v, cor_bg_regua)
        painter.setPen(QPen(cor_borda_regua, 1.2))
        painter.drawLine(espessura_regua, espessura_regua, espessura_regua, altura_view)

        # 3. Canto Superior Esquerdo (Indicador de Unidade)
        rect_canto = QRectF(0, 0, espessura_regua, espessura_regua)
        painter.fillRect(rect_canto, QColor("#1a1e2b"))
        painter.setPen(QPen(cor_borda_regua, 1.2))
        painter.drawRect(rect_canto)
        painter.setPen(QColor(CoresTema.ACENTO_PRIMARIO))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(rect_canto, Qt.AlignCenter, "mm")

        # 4. Cálculo de Escala (pixels por milímetro)
        pt1 = self.mapToScene(espessura_regua, 0)
        pt2 = self.mapToScene(espessura_regua + 100, 0)
        pixels_por_mm = 100.0 / max(0.0001, abs(pt2.x() - pt1.x()))

        # Determinar passo base dinâmico (métrica: 10mm, 50mm, 100mm, 200mm, 500mm, 1000mm)
        passos = [10.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0]
        passo_mm = 100.0
        for p in passos:
            if p * pixels_por_mm >= 36:
                passo_mm = p
                break

        # Graduações da Régua Horizontal
        x_min_cena = self.mapToScene(espessura_regua, 0).x()
        x_max_cena = self.mapToScene(largura_view, 0).x()
        primeiro_passo = math.floor(x_min_cena / passo_mm) * passo_mm

        curr_x = primeiro_passo
        while curr_x <= x_max_cena:
            view_pt = self.mapFromScene(curr_x, 0)
            vx = view_pt.x()
            if vx >= espessura_regua:
                is_metro = abs(curr_x % 1000.0) < 0.01
                is_50cm = (abs(curr_x % 500.0) < 0.01) and not is_metro
                is_10cm = (abs(curr_x % 100.0) < 0.01) and not (is_metro or is_50cm)

                if is_metro:
                    altura_traco = 18.0
                    painter.setPen(QPen(QColor(CoresTema.ACENTO_PRIMARIO), 1.6))
                    txt = f"{curr_x/1000.0:.1f}m"
                    painter.setFont(fonte_regua_destaque)
                    cor_txt = QColor("#ffffff")
                elif is_50cm:
                    altura_traco = 12.0
                    painter.setPen(QPen(QColor("#94a3b8"), 1.2))
                    txt = f"{curr_x/10.0:.0f}cm"
                    painter.setFont(fonte_regua_med)
                    cor_txt = QColor("#cbd5e1")
                elif is_10cm:
                    altura_traco = 8.0
                    painter.setPen(QPen(QColor("#64748b"), 1.0))
                    txt = f"{curr_x/10.0:.0f}cm"
                    painter.setFont(fonte_regua_peq)
                    cor_txt = QColor("#94a3b8")
                else:
                    altura_traco = 5.0
                    painter.setPen(QPen(QColor("#475569"), 0.8))
                    txt = ""
                    cor_txt = None

                painter.drawLine(vx, espessura_regua - altura_traco, vx, espessura_regua)

                if txt and (vx + 45 <= largura_view):
                    painter.setPen(cor_txt)
                    painter.drawText(
                        QRectF(vx + 3, 2, 50, espessura_regua - 5),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        txt,
                    )
            curr_x += passo_mm

        # Graduações da Régua Vertical
        y_min_cena = self.mapToScene(0, espessura_regua).y()
        y_max_cena = self.mapToScene(0, altura_view).y()
        primeiro_passo_y = math.floor(y_min_cena / passo_mm) * passo_mm

        curr_y = primeiro_passo_y
        while curr_y <= y_max_cena:
            view_pt = self.mapFromScene(0, curr_y)
            vy = view_pt.y()
            if vy >= espessura_regua:
                is_metro = abs(curr_y % 1000.0) < 0.01
                is_50cm = (abs(curr_y % 500.0) < 0.01) and not is_metro
                is_10cm = (abs(curr_y % 100.0) < 0.01) and not (is_metro or is_50cm)

                if is_metro:
                    comp_traco = 18.0
                    painter.setPen(QPen(QColor(CoresTema.ACENTO_PRIMARIO), 1.6))
                    txt_y = f"{curr_y/1000.0:.1f}m"
                    painter.setFont(fonte_regua_destaque)
                    cor_txt = QColor("#ffffff")
                elif is_50cm:
                    comp_traco = 12.0
                    painter.setPen(QPen(QColor("#94a3b8"), 1.2))
                    txt_y = f"{curr_y/10.0:.0f}cm"
                    painter.setFont(fonte_regua_med)
                    cor_txt = QColor("#cbd5e1")
                elif is_10cm:
                    comp_traco = 8.0
                    painter.setPen(QPen(QColor("#64748b"), 1.0))
                    txt_y = f"{curr_y/10.0:.0f}cm"
                    painter.setFont(fonte_regua_peq)
                    cor_txt = QColor("#94a3b8")
                else:
                    comp_traco = 5.0
                    painter.setPen(QPen(QColor("#475569"), 0.8))
                    txt_y = ""
                    cor_txt = None

                painter.drawLine(espessura_regua - comp_traco, vy, espessura_regua, vy)

                if txt_y and (vy + 12 <= altura_view):
                    painter.setPen(cor_txt)
                    painter.save()
                    painter.translate(3, vy - 3)
                    painter.drawText(0, 0, txt_y)
                    painter.restore()

            curr_y += passo_mm

        # 5. Marcadores de Margens de Segurança nas Réguas
        # Margem Esquerda na Régua Superior
        vx_margem_esq = self.mapFromScene(self.margem_lateral_mm, 0).x()
        if vx_margem_esq >= espessura_regua:
            painter.setPen(QPen(QColor(CoresTema.MARGEM_CORTE), 1.5, Qt.DashLine))
            painter.drawLine(vx_margem_esq, 0, vx_margem_esq, espessura_regua)

        # Margem Direita na Régua Superior
        vx_margem_dir = self.mapFromScene(self.largura_mm - self.margem_lateral_mm, 0).x()
        if vx_margem_dir >= espessura_regua and vx_margem_dir <= largura_view:
            painter.setPen(QPen(QColor(CoresTema.MARGEM_CORTE), 1.5, Qt.DashLine))
            painter.drawLine(vx_margem_dir, 0, vx_margem_dir, espessura_regua)

        # Margem Topo na Régua Vertical
        vy_margem_topo = self.mapFromScene(0, self.margem_topo_mm).y()
        if vy_margem_topo >= espessura_regua and vy_margem_topo <= altura_view:
            painter.setPen(QPen(QColor(CoresTema.MARGEM_CORTE), 1.5, Qt.DashLine))
            painter.drawLine(0, vy_margem_topo, espessura_regua, vy_margem_topo)

        # 6. Guia Reticular de Posição do Mouse nas Réguas
        pos_mouse = getattr(self, "_pos_mouse_view", None)
        if pos_mouse and not self._arrastando_pan:
            mx = pos_mouse.x()
            my = pos_mouse.y()
            if mx >= espessura_regua and my >= espessura_regua:
                pen_guia = QPen(QColor(CoresTema.ACENTO_PRIMARIO), 1.0)
                painter.setPen(pen_guia)
                # Marcador na régua superior
                painter.drawLine(mx, 0, mx, espessura_regua)
                # Marcador na régua esquerda
                painter.drawLine(0, my, espessura_regua, my)

        painter.restore()
