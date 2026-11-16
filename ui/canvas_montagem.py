"""
Canvas WYSIWYG Interativo com PySide6 / QGraphicsView para Montagem de Bobina/Chapa.

Recursos:
- Zoom centrado na posição do cursor do mouse (fator 1.15).
- Pan fluido via clique e arraste com botão do meio ou barra de espaço.
- Réguas de medição dinâmica métrica em cm/m ajustadas ao zoom.
- Representação gráfica da mídia física e margens de corte de segurança.
- PecaGraficaItem com movimentação livre, rotação 90 graus (tecla R / menu) e
  detecção de colisão em tempo real (destaque vermelho/verde).
- Cálculo contínuo de métricas de aproveitamento e comprimento linear.
"""

from typing import Optional, List, Dict, Any
import math
import uuid

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
        metadados: Optional[Dict[str, Any]] = None,
        parent: Optional[QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.id_peca = id_peca or str(uuid.uuid4())[:8]
        self.nome = nome
        self.largura_mm = float(largura_mm)
        self.altura_mm = float(altura_mm)
        self.miniatura = miniatura
        self.metadados = metadados or {}
        
        self.rotacao = 0.0  # 0, 90, 180, 270 graus
        self.tem_colisao = False
        self.fora_dos_limites = False

        # Configurar flags de interação
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
            | QGraphicsItem.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)
        self.setTransformOriginPoint(self.largura_mm / 2.0, self.altura_mm / 2.0)
        self.setToolTip(f"{self.nome}\n{self.largura_mm:.1f} × {self.altura_mm:.1f} mm")

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
        """Desenha a peça com indicação de colisão ou encaixe válido."""
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = self.boundingRect()
        tem_problema = self.tem_colisao or self.fora_dos_limites

        # Cores e estilos de borda
        if tem_problema:
            cor_borda = QColor(CoresTema.PERIGO)
            cor_fundo = QColor(CoresTema.PERIGO)
            cor_fundo.setAlpha(45)
            largura_pen = 2.5
        elif self.isSelected():
            cor_borda = QColor(CoresTema.ACENTO_PRIMARIO)
            cor_fundo = QColor(CoresTema.ACENTO_PRIMARIO)
            cor_fundo.setAlpha(55)
            largura_pen = 2.0
        else:
            cor_borda = QColor(CoresTema.SUCESSO)
            cor_fundo = QColor(CoresTema.CARTAO)
            cor_fundo.setAlpha(220)
            largura_pen = 1.5

        pen = QPen(cor_borda, largura_pen)
        if tem_problema:
            pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(cor_fundo))
        painter.drawRoundedRect(rect, 4.0, 4.0)

        # Desenhar miniatura caso exista
        if self.miniatura and not self.miniatura.isNull():
            margem = 6.0
            rect_foto = rect.adjusted(margem, margem, -margem, -margem - 24.0)
            if rect_foto.width() > 10 and rect_foto.height() > 10:
                pix_escalada = self.miniatura.scaled(
                    int(rect_foto.width()),
                    int(rect_foto.height()),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                px = rect_foto.x() + (rect_foto.width() - pix_escalada.width()) / 2
                py = rect_foto.y() + (rect_foto.height() - pix_escalada.height()) / 2
                painter.drawPixmap(int(px), int(py), pix_escalada)

        # Desenhar rótulo e dimensões
        painter.setPen(QColor(CoresTema.TEXTO_PRINCIPAL))
        fonte_nome = QFont("Segoe UI", 8, QFont.Bold)
        painter.setFont(fonte_nome)

        texto_dim = f"{self.largura_mm:.0f}×{self.altura_mm:.0f}mm"
        if self.rotacao > 0:
            texto_dim += f" ({self.rotacao:.0f}°)"

        # Placa inferior com metadados legíveis
        altura_tarja = min(22.0, rect.height() * 0.35)
        rect_tarja = QRectF(rect.x(), rect.bottom() - altura_tarja, rect.width(), altura_tarja)
        cor_tarja = QColor("#121318")
        cor_tarja.setAlpha(190)
        painter.fillRect(rect_tarja, cor_tarja)

        painter.setPen(QColor("#ffffff" if not tem_problema else CoresTema.PERIGO))
        texto_exibicao = f"{self.nome} | {texto_dim}"
        painter.drawText(
            rect_tarja.adjusted(4, 0, -4, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            painter.fontMetrics().elidedText(texto_exibicao, Qt.ElideRight, int(rect_tarja.width() - 8)),
        )

        # Indicador de colisão em texto se houver
        if tem_problema:
            aviso = "COLISÃO!" if self.tem_colisao else "FORA DA ÁREA ÚTIL!"
            painter.setPen(QColor(CoresTema.PERIGO))
            fonte_aviso = QFont("Segoe UI", 9, QFont.Black)
            painter.setFont(fonte_aviso)
            painter.drawText(rect.adjusted(6, 6, -6, -altura_tarja - 6), Qt.AlignCenter, aviso)


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

        self._pecas: List[PecaGraficaItem] = []
        self._espaco_pressionado = False
        self._arrastando_pan = False
        self._pos_mouse_anterior = QPointF()
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
        margem = 10.0
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
        """Arrasta a câmera durante o pan fluido."""
        if self._arrastando_pan:
            delta = event.position() - self._pos_mouse_anterior
            self._pos_mouse_anterior = event.position()
            # Mover barras de rolagem ou transladar
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finaliza operação de pan."""
        if self._arrastando_pan and (event.button() == Qt.MiddleButton or event.button() == Qt.LeftButton):
            self._arrastando_pan = False
            self.setCursor(Qt.OpenHandCursor if self._espaco_pressionado else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------------------
    # Renderização da Bobina, Margens e Réguas Métricas Dinâmicas
    # -------------------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Desenha a representação da mídia física e margens de corte."""
        super().drawBackground(painter, rect)
        painter.save()

        # Grade suave de fundo da cena
        pen_grade = QPen(QColor(CoresTema.GRADE_LINHA), 1, Qt.DotLine)
        painter.setPen(pen_grade)
        
        # Desenhar Mídia Física (Área Branca/Contrastada)
        rect_midia = QRectF(0.0, 0.0, self.largura_mm, self.comprimento_mm)
        brush_midia = QBrush(QColor(CoresTema.MIDIA_PAPEL))
        pen_borda_midia = QPen(QColor(CoresTema.MIDIA_BORDA), 1.5)
        painter.setBrush(brush_midia)
        painter.setPen(pen_borda_midia)
        painter.drawRect(rect_midia)

        # Margens de Segurança de Corte (Linhas tracejadas vermelhas/âmbar)
        rect_util = self.obter_limites_uteis()
        pen_margem = QPen(QColor(CoresTema.MARGEM_CORTE), 1.5, Qt.DashLine)
        painter.setPen(pen_margem)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect_util)

        # Rótulo de identificação da mídia no topo
        painter.setPen(QColor(CoresTema.TEXTO_MUTED))
        fonte_info = QFont("Segoe UI", 9)
        painter.setFont(fonte_info)
        texto_midia = f"MÍDIA: {self.largura_mm:.0f} mm × {self.comprimento_mm:.0f} mm (Área útil: {rect_util.width():.0f} mm)"
        painter.drawText(QRectF(0, -30, self.largura_mm, 25), Qt.AlignLeft | Qt.AlignVCenter, texto_midia)

        painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Desenha as réguas dinâmicas horizontal e vertical sobre a viewport."""
        super().drawForeground(painter, rect)
        painter.save()
        painter.resetTransform()  # Desenhar em coordenadas de tela fixas na viewport

        largura_view = self.viewport().width()
        altura_view = self.viewport().height()
        espessura_regua = 24

        cor_bg_regua = QColor(CoresTema.SUPERFICIE)
        cor_traco = QColor(CoresTema.BORDA_FOCO)
        cor_texto = QColor(CoresTema.TEXTO_SECUNDARIO)
        pen_traco = QPen(cor_traco, 1)
        fonte_regua = QFont("Segoe UI", 7)
        painter.setFont(fonte_regua)

        # 1. Régua Horizontal (Topo)
        rect_regua_h = QRectF(espessura_regua, 0, largura_view - espessura_regua, espessura_regua)
        painter.fillRect(rect_regua_h, cor_bg_regua)
        painter.setPen(QPen(QColor(CoresTema.BORDA), 1))
        painter.drawLine(espessura_regua, espessura_regua, largura_view, espessura_regua)

        # 2. Régua Vertical (Esquerda)
        rect_regua_v = QRectF(0, espessura_regua, espessura_regua, altura_view - espessura_regua)
        painter.fillRect(rect_regua_v, cor_bg_regua)
        painter.setPen(QPen(QColor(CoresTema.BORDA), 1))
        painter.drawLine(espessura_regua, espessura_regua, espessura_regua, altura_view)

        # Canto superior esquerdo
        painter.fillRect(QRectF(0, 0, espessura_regua, espessura_regua), QColor(CoresTema.CARTAO))

        # Calcular intervalo de marcações dinâmicas conforme zoom
        pt1 = self.mapToScene(espessura_regua, 0)
        pt2 = self.mapToScene(espessura_regua + 100, 0)
        pixels_por_mm = 100.0 / max(0.0001, abs(pt2.x() - pt1.x()))

        # Escolhe passo em mm: 10, 50, 100, 500, 1000
        passos = [10.0, 50.0, 100.0, 200.0, 500.0, 1000.0]
        passo_mm = 100.0
        for p in passos:
            if p * pixels_por_mm >= 50:
                passo_mm = p
                break

        # Graduações da régua horizontal
        x_min_cena = self.mapToScene(espessura_regua, 0).x()
        x_max_cena = self.mapToScene(largura_view, 0).x()
        primeiro_passo = math.floor(x_min_cena / passo_mm) * passo_mm

        curr_x = primeiro_passo
        while curr_x <= x_max_cena:
            view_pt = self.mapFromScene(curr_x, 0)
            vx = view_pt.x()
            if vx >= espessura_regua:
                painter.setPen(pen_traco)
                painter.drawLine(vx, espessura_regua - 8, vx, espessura_regua)
                # Texto da medida (em cm ou m)
                if curr_x >= 1000.0:
                    txt = f"{curr_x/1000.0:.1f}m"
                else:
                    txt = f"{curr_x/10.0:.0f}cm"
                painter.setPen(cor_texto)
                painter.drawText(QRectF(vx + 2, 2, 60, espessura_regua - 4), Qt.AlignLeft | Qt.AlignVCenter, txt)
            curr_x += passo_mm

        # Graduações da régua vertical
        y_min_cena = self.mapToScene(0, espessura_regua).y()
        y_max_cena = self.mapToScene(0, altura_view).y()
        primeiro_passo_y = math.floor(y_min_cena / passo_mm) * passo_mm

        curr_y = primeiro_passo_y
        while curr_y <= y_max_cena:
            view_pt = self.mapFromScene(0, curr_y)
            vy = view_pt.y()
            if vy >= espessura_regua:
                painter.setPen(pen_traco)
                painter.drawLine(espessura_regua - 8, vy, espessura_regua, vy)
                if curr_y >= 1000.0:
                    txt_y = f"{curr_y/1000.0:.1f}m"
                else:
                    txt_y = f"{curr_y/10.0:.0f}cm"
                painter.setPen(cor_texto)
                painter.save()
                painter.translate(2, vy - 2)
                painter.drawText(0, 0, txt_y)
                painter.restore()
            curr_y += passo_mm

        painter.restore()
