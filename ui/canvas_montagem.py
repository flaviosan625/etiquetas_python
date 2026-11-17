"""
Canvas WYSIWYG Interativo com PySide6 / QGraphicsView para Montagem de Bobina/Chapa.

Regras Históricas e de Fábrica (montagem.py - 04/10/2026):
- Rótulo de Identificação Técnica de cada Arte com numeração sequencial (01, 02...) e NOME EXATO DO ARQUIVO:
  montagem._texto_do_rotulo(peca, numero) -> f"{numero:02d}  {nome_do_arquivo}"
  Com cópias (>1): f"{numero:02d}  {nome_do_arquivo} ({copia}/{quantidade})"
  Encostado na arte com encolhimento de fonte antes de cortar.
- Cabeçalho Oficial da Montagem no Topo da Bobina (CABECALHO_M = 80mm):
  MONTAGEM  ·  {CLIENTE}  ·  {MATERIAL}  ·  {N} PEÇAS  ·  LARGURA {L}m  ·  APROVEITAMENTO {APROV}%  ·  RIPAR A 100%, NÃO REDIMENSIONAR
- Renderização visual aperfeiçoada de rolo de mídia contínuo com sombra suave de elevação 3D.
- Zonas de presilha e linhas tracejadas de margem de segurança lateral e topo da máquina.
- Réguas de medição dinâmica métrica em cm/m ajustadas ao zoom com marcações legíveis a cada 10cm, 50cm, 1m.
- Guia reticular do cursor do mouse em tempo real sobre as réguas métricas.
- PecaGraficaItem com substrato chanfrado, miniatura nítida (Anti-aliasing + SmoothPixmapTransform),
  destaque azul elétrico para seleção e alerta vermelho vivo para colisão.
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
    Representação visual e interativa de uma peça a ser montada na bobina/chapa,
    seguindo as regras de identificação e rotulagem técnica de fábrica (montagem.py).
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
        numero: int = 1,
        copia: int = 1,
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
        if isinstance(quantidade, (tuple, list)):
            self.quantidade = int(quantidade[0]) if quantidade else 1
        else:
            try:
                self.quantidade = max(1, int(quantidade))
            except Exception:
                self.quantidade = 1
        self.metadados = metadados or {}
        if isinstance(numero, (tuple, list)):
            self.numero = int(numero[0]) if numero else 1
        else:
            try:
                self.numero = max(1, int(numero))
            except Exception:
                self.numero = 1
        if isinstance(copia, (tuple, list)):
            self.copia = int(copia[0]) if copia else 1
        else:
            try:
                self.copia = max(1, int(copia or self.metadados.get("copia", 1)))
            except Exception:
                self.copia = 1

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
        self.setToolTip(f"{self.texto_do_rotulo()}\n{self.material} • {self.largura_mm:.1f} × {self.altura_mm:.1f} mm")

    def texto_do_rotulo(self) -> str:
        """
        Retorna o texto oficial do rótulo conforme a regra consagrada de montagem.py (04/10/2026):
        f"{numero:02d}  {nome_do_arquivo}"
        E se houver cópias (>1): f"{numero:02d}  {nome_do_arquivo} ({copia}/{quantidade})"
        """
        if self.caminho_arquivo:
            nome_arquivo = Path(self.caminho_arquivo).stem
        else:
            nome_arquivo = Path(self.nome).stem if "." in self.nome else self.nome

        if not nome_arquivo:
            nome_arquivo = self.nome

        copia = self.copia or self.metadados.get("copia", 1)
        if self.quantidade > 1:
            return f"{self.numero:02d}  {nome_arquivo} ({copia}/{self.quantidade})"
        return f"{self.numero:02d}  {nome_arquivo}"

    def nome_arquivo_puro(self) -> str:
        """Retorna o nome do arquivo sem extensão e sem o número da peça."""
        if self.caminho_arquivo:
            return Path(self.caminho_arquivo).stem
        return Path(self.nome).stem if "." in self.nome else self.nome

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
        Desenha a peça gráfica com substrato elevado, rótulo técnico oficial encostado
        na arte com número e nome exato do arquivo, miniatura nítida e tarja de dimensões.
        """
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = self.boundingRect()
        tem_problema = self.tem_colisao or self.fora_dos_limites

        # ---------------------------------------------------------------------
        # 1. Substrato Físico Branco Limpo (Sem Tarja para Não Gastar Tinta)
        # ---------------------------------------------------------------------
        path_peca = QPainterPath()
        path_peca.addRoundedRect(rect, 2.0, 2.0)

        # Fundo do substrato em branco puro / papel fotográfico / vinil
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawPath(path_peca)

        # ---------------------------------------------------------------------
        # 2. Rótulo Oficial da Peça em PRETO e SEM TARJA (Regra de montagem.py)
        # "Nome precisa ser em preto sem tarja assim gasta mais tinta"
        # ---------------------------------------------------------------------
        altura_rotulo = min(20.0, max(12.0, rect.height() * 0.12))

        texto_rotulo_oficial = self.texto_do_rotulo()

        x_texto = rect.x() + 3.0
        w_disp_texto = rect.width() - 6.0
        rect_area_nome = QRectF(x_texto, rect.y() + 1.0, max(0.0, w_disp_texto), altura_rotulo)

        # Cor da letra: PRETO PURO (#000000), SEM TARJA de fundo!
        cor_texto_rotulo = QColor("#b91c1c") if tem_problema else QColor("#000000")

        if w_disp_texto > 10.0:
            # Algoritmo de encolhimento para preservar o nome exato (regra de montagem.py)
            tam_max_pt = max(6, int(altura_rotulo * 0.52))
            fonte_escolhida = QFont("Segoe UI", tam_max_pt, QFont.Bold)
            for tam_pt in range(tam_max_pt, 4, -1):
                f_teste = QFont("Segoe UI", tam_pt, QFont.Bold)
                painter.setFont(f_teste)
                if painter.fontMetrics().horizontalAdvance(texto_rotulo_oficial) <= w_disp_texto:
                    fonte_escolhida = f_teste
                    break
            painter.setFont(fonte_escolhida)
            painter.setPen(cor_texto_rotulo)
            txt_formatado = painter.fontMetrics().elidedText(texto_rotulo_oficial, Qt.ElideRight, int(w_disp_texto))
            painter.drawText(rect_area_nome, Qt.AlignVCenter | Qt.AlignLeft, txt_formatado)

        # ---------------------------------------------------------------------
        # 3. Miniatura de Arte Renderizada Perfeitamente Nítida
        # ---------------------------------------------------------------------
        if (self.miniatura is None or self.miniatura.isNull()) and self.caminho_arquivo:
            self._carregar_miniatura_arquivo()

        # Espaço para rodapé técnico apenas se a peça tiver altura suficiente
        tem_espaco_rodape = rect.height() >= 55.0
        h_rodape = 14.0 if tem_espaco_rodape else 0.0

        y_arte = rect.top() + altura_rotulo + 2.0
        h_arte = rect.bottom() - y_arte - h_rodape - 2.0
        rect_arte = QRectF(rect.x() + 2.0, y_arte, rect.width() - 4.0, max(0.0, h_arte))

        if rect_arte.height() > 8.0 and rect_arte.width() > 8.0:
            if self.miniatura and not self.miniatura.isNull():
                pix_w = self.miniatura.width()
                pix_h = self.miniatura.height()
                if pix_w > 0 and pix_h > 0:
                    escala = min(rect_arte.width() / pix_w, rect_arte.height() / pix_h)
                    w_alvo = pix_w * escala
                    h_alvo = pix_h * escala
                    x_alvo = rect_arte.x() + (rect_arte.width() - w_alvo) / 2.0
                    y_alvo = rect_arte.y() + (rect_arte.height() - h_alvo) / 2.0
                    target_rect = QRectF(x_alvo, y_alvo, w_alvo, h_alvo)

                    painter.fillRect(target_rect, QColor("#ffffff"))
                    painter.drawPixmap(target_rect, self.miniatura, QRectF(self.miniatura.rect()))

                    painter.setPen(QPen(QColor("#cbd5e1"), 0.6))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(target_rect)
            elif rect_arte.width() > 20 and rect_arte.height() > 15:
                # Placeholder CAD vetorial limpo
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor("#f8fafc")))
                painter.drawRoundedRect(rect_arte, 2.0, 2.0)

                painter.setPen(QPen(QColor("#e2e8f0"), 0.8, Qt.DotLine))
                centro_x = rect_arte.center().x()
                centro_y = rect_arte.center().y()
                painter.drawLine(QPointF(rect_arte.left(), centro_y), QPointF(rect_arte.right(), centro_y))
                painter.drawLine(QPointF(centro_x, rect_arte.top()), QPointF(centro_x, rect_arte.bottom()))

                painter.setPen(QColor("#64748b"))
                tam_fonte_ph = max(6, int(min(rect_arte.width(), rect_arte.height()) * 0.12))
                painter.setFont(QFont("Segoe UI", min(tam_fonte_ph, 11), QFont.Bold))
                painter.drawText(
                    rect_arte,
                    Qt.AlignCenter,
                    f"{self.material}\n{self.largura_mm:.0f} × {self.altura_mm:.0f} mm",
                )

        # ---------------------------------------------------------------------
        # 4. Rodapé Técnico Limpo (Texto em Cinza, SEM TARJA Escura)
        # ---------------------------------------------------------------------
        if tem_espaco_rodape and rect.width() > 60.0:
            texto_dim = f"{self.largura_mm:.0f}×{self.altura_mm:.0f}mm  |  {self.material}"
            if self.rotacao > 0:
                texto_dim += f" (↻{self.rotacao:.0f}°)"

            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            painter.setPen(QColor("#64748b"))
            rect_texto_rodape = QRectF(rect.x() + 4.0, rect.bottom() - h_rodape, rect.width() - 8.0, h_rodape)
            texto_formatado = painter.fontMetrics().elidedText(texto_dim, Qt.ElideRight, int(rect_texto_rodape.width()))
            painter.drawText(rect_texto_rodape, Qt.AlignVCenter | Qt.AlignLeft, texto_formatado)

        # ---------------------------------------------------------------------
        # 5. Borda de Destaque Interativa / Seleção / Alerta de Colisão
        # ---------------------------------------------------------------------
        if tem_problema:
            cor_borda = QColor(CoresTema.PERIGO)
            painter.setPen(QPen(cor_borda, 2.8, Qt.SolidLine))
            cor_overlay = QColor(239, 68, 68, 45)
            painter.setBrush(QBrush(cor_overlay))
            painter.drawPath(path_peca)

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
            cor_borda = QColor(CoresTema.ACENTO_PRIMARIO)
            painter.setPen(QPen(cor_borda, 2.5, Qt.SolidLine))
            cor_overlay = QColor(14, 165, 233, 35)
            painter.setBrush(QBrush(cor_overlay))
            painter.drawPath(path_peca)

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
            cor_borda = QColor("#0284c7")
            painter.setPen(QPen(cor_borda, 1.2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path_peca)

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
    Incorpora o cabeçalho técnico oficial de 80mm de montagem.py e réguas dinâmicas.
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
        cliente: Optional[str] = None,
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
        self.cliente = cliente or "CLIENTE PADRÃO"

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

    def definir_cliente(self, cliente: str) -> None:
        """Configura o nome do cliente para o cabeçalho técnico oficial."""
        self.cliente = str(cliente).strip() if cliente else "CLIENTE PADRÃO"
        self.scene().update()

    def extrair_cliente_das_pecas(self) -> str:
        """Determina o cliente da montagem a partir dos metadados ou regras históricas."""
        if hasattr(self, "cliente") and self.cliente and self.cliente != "CLIENTE PADRÃO":
            return self.cliente.upper()
        for p in self._pecas:
            if p.metadados and p.metadados.get("cliente"):
                return str(p.metadados["cliente"]).upper()
        try:
            from montagem import cliente_das_pecas
            pecas_lista = [{"nome": p.nome, "arquivo": p.caminho_arquivo or p.nome} for p in self._pecas]
            cli = cliente_das_pecas(pecas_lista)
            if cli:
                return str(cli).upper()
        except Exception:
            pass
        return getattr(self, "cliente", "CLIENTE PADRÃO").upper()

    def extrair_material_das_pecas(self) -> str:
        """Determina a categoria/material predominante da montagem."""
        materiais = [p.material for p in self._pecas if p.material]
        if not materiais:
            return "VINIL / ADESIVO"
        unicos = sorted(set(materiais))
        if len(unicos) == 1:
            return unicos[0]
        return f"MISTO ({', '.join(unicos[:2])})"

    def obter_titulo_cabecalho(self) -> str:
        """
        Gera o texto oficial do cabeçalho de 80mm de acordo com a regra consagrada de montagem.py:
        MONTAGEM  ·  {CLIENTE}  ·  {MATERIAL}  ·  {N} PEÇAS  ·  LARGURA {L}m  ·  APROVEITAMENTO {APROV}%  ·  RIPAR A 100%, NÃO REDIMENSIONAR
        """
        cliente = self.extrair_cliente_das_pecas()
        material = self.extrair_material_das_pecas()
        n_pecas = len(self._pecas)
        largura_m = self.largura_mm / 1000.0
        stats = self.calcular_estatisticas()
        aprov_pct = stats["aproveitamento_pct"]

        return (
            f"MONTAGEM  ·  {cliente}  ·  {material}  ·  "
            f"{n_pecas} PEÇAS  ·  LARGURA {largura_m:.2f}m  ·  "
            f"APROVEITAMENTO {aprov_pct:.0f}%  ·  "
            f"RIPAR A 100%, NÃO REDIMENSIONAR"
        )

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
        """Recalcula a área total da cena considerando a bobina, cabeçalho de 80mm e folga ao redor."""
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

    def _atualizar_numeracao_pecas(self) -> None:
        """Atualiza a numeração sequencial oficial (01, 02...) de todas as peças."""
        for idx, p in enumerate(self._pecas, start=1):
            p.numero = idx
            p.update()

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
        numero: Optional[int] = None,
        copia: Optional[int] = None,
    ) -> PecaGraficaItem:
        """Adiciona uma nova peça gráfica ao canvas com numeração e rótulo oficiais."""
        num_peca = numero if numero is not None else (len(self._pecas) + 1)
        num_copia = copia if copia is not None else (metadados.get("copia", 1) if metadados else 1)

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
            numero=num_peca,
            copia=num_copia,
        )

        # Posicionamento inteligente padrão caso não fornecido
        if pos_x is None or pos_y is None:
            pos_x, pos_y = self._calcular_proxima_posicao_livre(largura_mm, altura_mm)

        peca.setPos(pos_x, pos_y)
        self.scene().addItem(peca)
        self._pecas.append(peca)
        self._atualizar_numeracao_pecas()

        self._atualizar_geometria_bobina()
        self.verificar_todas_colisoes()
        self.emitir_estatisticas()
        self.pecas_modificadas.emit()
        return peca

    def remover_peca(self, peca: PecaGraficaItem) -> None:
        """Remove uma peça do canvas e renumera as restantes."""
        if peca in self._pecas:
            self._pecas.remove(peca)
            if peca.scene():
                peca.scene().removeItem(peca)
            self._atualizar_numeracao_pecas()
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
        """Determina uma posição inicial inteligente para nova peça dentro da área útil."""
        limites = self.obter_limites_uteis()
        margem = getattr(self, "espacamento_mm", 10.0)

        if not self._pecas:
            return limites.left() + margem, limites.top() + margem

        # Tenta posicionar à direita da última peça inserida
        ultima_peca = self._pecas[-1]
        br_ultima = ultima_peca.sceneBoundingRect()
        x_candidato = br_ultima.right() + margem
        y_candidato = br_ultima.top()

        if x_candidato + largura <= limites.right() - margem:
            return x_candidato, y_candidato

        # Se não couber na linha atual da bobina, desce para a próxima linha
        max_y = max(p.sceneBoundingRect().bottom() for p in self._pecas)
        return limites.left() + margem, max_y + margem

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

    def exportar_pdf_montado(
        self,
        caminho_destino: Union[str, Path],
        nome_maquina: Optional[str] = None,
        cliente: Optional[str] = None,
    ) -> Path:
        """
        Exporta o layout exato do Canvas WYSIWYG para um PDF vetorial de alta definição.
        Em conformidade com as regras históricas de fábrica de montagem.py:
        - Escala exata em pontos por metro (PT_M = 72 / 0.0254).
        - Cabeçalho oficial no topo (CABECALHO_M = 80 mm).
        - Posicionamento milimétrico exato de cada arte conforme visualizado na tela.
        - Rótulo oficial em PRETO PURO (color=(0,0,0)) SEM NENHUMA TARJA de fundo.
        - Embutimento 100% vetorial e de imagem sem perdas (deflate_images=False).
        """
        import pymupdf
        import json
        import datetime
        import montagem

        pecas = self.obter_pecas()
        if not pecas:
            raise ValueError("O canvas não possui peças montadas para exportar.")

        destino = Path(caminho_destino)
        destino.parent.mkdir(parents=True, exist_ok=True)

        PT_M = montagem.PT_M  # 72.0 / 0.0254 = 2834.645669 pt/m
        CABECALHO_M = montagem.CABECALHO_M  # 0.08 m (80 mm)

        largura_m = self.largura_mm / 1000.0
        largura_pt = largura_m * PT_M

        max_y_mm = max((p.sceneBoundingRect().bottom() for p in pecas), default=self.comprimento_mm)
        folga_m = getattr(self, "espacamento_mm", 10.0) / 1000.0
        comprimento_total_m = CABECALHO_M + (max_y_mm / 1000.0) + folga_m
        comprimento_pt = comprimento_total_m * PT_M

        doc = pymupdf.open()
        pagina = doc.new_page(width=largura_pt, height=comprimento_pt)
        pagina.draw_rect(pagina.rect, color=None, fill=(1, 1, 1))

        # 1. Faixa de Cabeçalho Oficial no Topo (CABECALHO_M = 80 mm)
        titulo = self.obter_titulo_cabecalho()
        if cliente:
            titulo = titulo.replace("SEM CLIENTE NO NOME", cliente)
        if nome_maquina:
            titulo = f"[{nome_maquina}]  " + titulo

        caixa_cab = pymupdf.Rect(0.02 * PT_M, 0.018 * PT_M, (largura_m - 0.02) * PT_M, CABECALHO_M * PT_M)
        for tam_mm in (30, 25, 20, 15, 12, 10, 8, 6, 4, 3, 2):
            if pagina.insert_textbox(
                caixa_cab,
                titulo,
                fontsize=(tam_mm / 1000.0) * PT_M,
                fontname="hebo",
                color=(0.35, 0.35, 0.35),
            ) >= 0:
                break

        # Linha divisória de 1 pt abaixo do cabeçalho
        pagina.draw_line(
            pymupdf.Point(0, CABECALHO_M * PT_M),
            pymupdf.Point(largura_pt, CABECALHO_M * PT_M),
            color=(0.7, 0.7, 0.7),
            width=1,
        )

        # 2. Posicionamento e Embutimento de Cada Arte
        for peca in pecas:
            s_rect = peca.sceneBoundingRect()
            x0_pt = (s_rect.left() / 1000.0) * PT_M
            y0_pt = (CABECALHO_M + (s_rect.top() / 1000.0)) * PT_M
            w_pt = (s_rect.width() / 1000.0) * PT_M
            h_pt = (s_rect.height() / 1000.0) * PT_M
            caixa_arte = pymupdf.Rect(x0_pt, y0_pt, x0_pt + w_pt, y0_pt + h_pt)
            rot = int(peca.rotacao) % 360

            caminho = peca.caminho_arquivo
            if caminho and Path(caminho).is_file():
                p_arq = Path(caminho)
                if p_arq.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"):
                    with pymupdf.open(str(p_arq)) as img_doc:
                        bytes_pdf = img_doc.convert_to_pdf()
                    origem = pymupdf.open("pdf", bytes_pdf)
                    num_pag = 0
                else:
                    origem = pymupdf.open(str(p_arq))
                    num_pag = peca.metadados.get("pagina", 0)

                try:
                    recorte = montagem.caixa_da_arte(origem.load_page(num_pag), pymupdf)
                    pagina.show_pdf_page(
                        caixa_arte,
                        origem,
                        num_pag,
                        clip=recorte,
                        rotate=rot,
                        keep_proportion=True,
                    )
                finally:
                    origem.close()
            else:
                pagina.draw_rect(caixa_arte, color=(0.8, 0.8, 0.8), fill=(0.98, 0.98, 0.98))
                texto_demo = f"{peca.material}\n{peca.largura_mm:.0f} × {peca.altura_mm:.0f} mm"
                pagina.insert_textbox(
                    caixa_arte,
                    texto_demo,
                    fontsize=12,
                    fontname="hebo",
                    color=(0.4, 0.4, 0.4),
                )

            # Acabamentos opcionais (Ilhós)
            if peca.metadados.get("aplicar_ilhos"):
                try:
                    import acabamento
                    acabamento.desenhar_ilhos_na_caixa(pagina, caixa_arte)
                except Exception:
                    pass

            # 3. Rótulo Oficial da Arte em PRETO PURO e SEM TARJA
            # Regra: "Nome precisa ser em preto sem tarja assim gasta mais tinta"
            texto_rotulo = peca.texto_do_rotulo()
            largura_rotulo_m = min(0.30, s_rect.width() / 1000.0)
            base_pt = caixa_arte.y0 - (0.001 * PT_M)

            largura_1pt = pymupdf.get_text_length(texto_rotulo, fontname="hebo", fontsize=1)
            if largura_1pt > 0:
                pedido_mm = (largura_rotulo_m / largura_1pt) * 1000.0
                tamanho_mm = max(4.0, min(pedido_mm, 14.0))
            else:
                tamanho_mm = 10.0

            font_pt = (tamanho_mm / 1000.0) * PT_M
            caixa_rotulo = pymupdf.Rect(
                caixa_arte.x0,
                base_pt - (tamanho_mm * 1.8 / 1000.0) * PT_M,
                caixa_arte.x0 + (largura_rotulo_m * PT_M),
                base_pt,
            )
            # NENHUM FUNDO (SEM TARJA) - PURE BLACK:
            pagina.insert_textbox(
                caixa_rotulo,
                texto_rotulo,
                fontsize=font_pt,
                fontname="hebo",
                color=(0, 0, 0),
            )

        doc.save(str(destino), deflate_images=False)
        doc.close()

        # Ficha JSON complementar ao lado do PDF
        try:
            stats = self.calcular_estatisticas()
            ficha = {
                "quando": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "cliente": cliente or self.extrair_cliente_das_pecas(),
                "maquina": nome_maquina or "DOCAN 5200",
                "material": self.extrair_material_das_pecas(),
                "largura_folha_m": round(largura_m, 3),
                "comprimento_folha_m": round(comprimento_total_m, 3),
                "area_total_m2": round(largura_m * comprimento_total_m, 3),
                "area_pecas_m2": round(stats["area_pecas_m2"], 3),
                "aproveitamento_pct": round(stats["aproveitamento_pct"], 1),
                "total_pecas": len(pecas),
                "pecas": [
                    {
                        "numero": p.numero,
                        "arquivo": p.nome,
                        "caminho": p.caminho_arquivo,
                        "material": p.material,
                        "largura_mm": p.largura_mm,
                        "altura_mm": p.altura_mm,
                        "rotacao": p.rotacao,
                        "pos_x_mm": round(p.sceneBoundingRect().left(), 1),
                        "pos_y_mm": round(p.sceneBoundingRect().top(), 1),
                    }
                    for p in pecas
                ],
            }
            with destino.with_suffix(".json").open("w", encoding="utf-8") as f:
                json.dump(ficha, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return destino

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
        """Ajusta a visão para enquadrar perfeitamente a bobina e o cabeçalho."""
        rect_bobina = QRectF(0, -80.0, self.largura_mm, self.comprimento_mm + 80.0)
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
        """Desenha a representação da mídia física, cabeçalho de 80mm e margens de corte."""
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

        # 4. Faixa Técnica Oficial da Montagem no Topo da Bobina (CABECALHO_M = 80mm)
        cabecalho_h_mm = 80.0
        rect_cabecalho = QRectF(0.0, -cabecalho_h_mm, self.largura_mm, cabecalho_h_mm)

        grad_cabecalho = QLinearGradient(rect_cabecalho.topLeft(), rect_cabecalho.bottomLeft())
        grad_cabecalho.setColorAt(0.0, QColor("#181d2a"))
        grad_cabecalho.setColorAt(1.0, QColor("#0f131c"))
        painter.fillRect(rect_cabecalho, QBrush(grad_cabecalho))

        painter.setPen(QPen(QColor(CoresTema.ACENTO_PRIMARIO), 1.5))
        painter.drawRect(rect_cabecalho)

        painter.setPen(QPen(QColor("#38bdf8"), 2.0))
        painter.drawLine(rect_cabecalho.topLeft(), rect_cabecalho.topRight())

        painter.setPen(QColor("#38bdf8"))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(
            QRectF(15.0, -cabecalho_h_mm + 4.0, 360.0, 14.0),
            Qt.AlignLeft | Qt.AlignVCenter,
            "CABEÇALHO OFICIAL DE MONTAGEM (CABECALHO_M = 80 mm)",
        )

        # Texto Oficial: MONTAGEM · {CLIENTE} · {MATERIAL} · {N} PEÇAS · LARGURA {L}m · APROVEITAMENTO {APROV}% · RIPAR A 100%, NÃO REDIMENSIONAR
        texto_cabecalho = self.obter_titulo_cabecalho()
        margem_h_texto = 15.0
        largura_disp_texto = max(100.0, self.largura_mm - (2.0 * margem_h_texto))
        rect_area_texto = QRectF(margem_h_texto, -cabecalho_h_mm + 18.0, largura_disp_texto, 38.0)

        fonte_cab = QFont("Segoe UI", 12, QFont.Bold)
        for tam_pt in (14, 13, 12, 11, 10, 9, 8, 7, 6):
            fonte_teste = QFont("Segoe UI", tam_pt, QFont.Bold)
            painter.setFont(fonte_teste)
            if painter.fontMetrics().horizontalAdvance(texto_cabecalho) <= largura_disp_texto:
                fonte_cab = fonte_teste
                break

        painter.setFont(fonte_cab)
        painter.setPen(QColor("#ffffff"))
        texto_elidido = painter.fontMetrics().elidedText(texto_cabecalho, Qt.ElideRight, int(largura_disp_texto))
        painter.drawText(rect_area_texto, Qt.AlignCenter, texto_elidido)

        painter.setPen(QColor("#64748b"))
        painter.setFont(QFont("Segoe UI", 7, QFont.DemiBold))
        painter.drawText(
            QRectF(15.0, -18.0, self.largura_mm - 30.0, 14.0),
            Qt.AlignCenter,
            "▲ EIXO Y = 0 mm  ·  INÍCIO DA ÁREA DE IMPRESSÃO / CORTE  ▲",
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

        # 7. Fim da Bobina / Extensão Contínua
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
        vx_margem_esq = self.mapFromScene(self.margem_lateral_mm, 0).x()
        if vx_margem_esq >= espessura_regua:
            painter.setPen(QPen(QColor(CoresTema.MARGEM_CORTE), 1.5, Qt.DashLine))
            painter.drawLine(vx_margem_esq, 0, vx_margem_esq, espessura_regua)

        vx_margem_dir = self.mapFromScene(self.largura_mm - self.margem_lateral_mm, 0).x()
        if vx_margem_dir >= espessura_regua and vx_margem_dir <= largura_view:
            painter.setPen(QPen(QColor(CoresTema.MARGEM_CORTE), 1.5, Qt.DashLine))
            painter.drawLine(vx_margem_dir, 0, vx_margem_dir, espessura_regua)

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
                painter.drawLine(mx, 0, mx, espessura_regua)
                painter.drawLine(0, my, espessura_regua, my)

        painter.restore()
