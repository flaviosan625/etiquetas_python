"""
gui_triagem.py — Interface Gráfica e Lógica de Triagem Visual em Lote (ISSUE-09).

Permite:
- Triagem visual rápida de arquivos de produção gráfica e grandes formatos.
- Inspeção e auditoria de medidas nativas de arquivos PDF via motor_pdf.
- Detecção e sugestão automática de escalas industriais (1:1, 1:10, 1:20, etc.).
- Cruzamento e reconciliação entre arquivos locais e planilhas de corte/pedidos (CSV/XLSX).
- Edição rápida individual e edição em lote para múltiplos arquivos selecionados.
- Despacho seguro de itens com validação prévia de material, dimensões e quantidades.
- Totalmente compatível com o tema claro e escuro de tema.py.
"""

from __future__ import annotations

import math
import os
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import config as modulo_config
from importador_planilha import cruzar_arquivos_com_planilha, ler_planilha
from motor_pdf import abrir_pdf
from parser_regras import ParserRegrasNomes, ResultadoParse
import tema
from tema import cores

ESCALAS_COMUNS = ["1:1", "1:2", "1:5", "1:10", "1:20", "1:25", "1:50", "1:100"]

FATORES_ESCALA_PADRAO = {
    "1:1": 1.0,
    "1:2": 2.0,
    "1:5": 5.0,
    "1:10": 10.0,
    "1:20": 20.0,
    "1:25": 25.0,
    "1:50": 50.0,
    "1:100": 100.0,
}


def interpretar_escala(escala_str: str) -> float:
    """
    Interpreta uma string de escala e devolve o multiplicador (fator de escala)
    para converter a medida reduzida na medida real final.
    Exemplos:
      '1:1' -> 1.0
      '1:10' -> 10.0
      '1:20' -> 20.0
      '1:5' -> 5.0
      '2:1' -> 0.5
      '10' -> 10.0
    """
    if not escala_str:
        return 1.0

    s = str(escala_str).strip().replace(" ", "").replace("/", ":")
    if s in FATORES_ESCALA_PADRAO:
        return FATORES_ESCALA_PADRAO[s]

    m_escala = re.match(r'^1:(\d+(?:[.,]\d+)?)$', s)
    if m_escala:
        val = float(m_escala.group(1).replace(",", "."))
        return val if val > 0 else 1.0

    m_inversa = re.match(r'^(\d+(?:[.,]\d+)?):1$', s)
    if m_inversa:
        val = float(m_inversa.group(1).replace(",", "."))
        return (1.0 / val) if val > 0 else 1.0

    try:
        val = float(s.replace(",", "."))
        return val if val > 0 else 1.0
    except ValueError:
        return 1.0


def detectar_ou_sugerir_escala(
    larg_pdf_m: float,
    alt_pdf_m: float,
    larg_alvo_m: float,
    alt_alvo_m: float,
    tolerancia: float = 0.05,
) -> Tuple[float, str]:
    """
    Compara as medidas do PDF com as medidas desejadas (alvo) e determina
    se existe uma escala industrial proporcional (1:1, 1:10, 1:20...),
    inclusive testando orientação girada 90 graus.

    Retorna:
      (fator_escala: float, nome_escala: str)
      Exemplo: (10.0, '1:10')
    """
    if (
        larg_pdf_m <= 0
        or alt_pdf_m <= 0
        or larg_alvo_m <= 0
        or alt_alvo_m <= 0
    ):
        return 1.0, "1:1"

    # 1. Relação direta (orientação idêntica)
    rl = larg_alvo_m / larg_pdf_m
    ra = alt_alvo_m / alt_pdf_m

    # 2. Relação cruzada (girada 90 graus)
    rl_rot = larg_alvo_m / alt_pdf_m
    ra_rot = alt_alvo_m / larg_pdf_m

    # Lista de escalas padrão ordenadas
    escalas_teste = [1.0, 2.0, 5.0, 10.0, 20.0, 25.0, 50.0, 100.0]

    for fat in escalas_teste:
        # Testa orientação direta
        if abs(rl - fat) / fat <= tolerancia and abs(ra - fat) / fat <= tolerancia:
            nome = "1:1" if fat == 1.0 else f"1:{int(fat)}"
            return fat, nome
        # Testa orientação rotacionada
        if abs(rl_rot - fat) / fat <= tolerancia and abs(ra_rot - fat) / fat <= tolerancia:
            nome = "1:1" if fat == 1.0 else f"1:{int(fat)}"
            return fat, nome

    # Proporção não padronizada porém uniforme direta
    media_dir = (rl + ra) / 2.0
    if media_dir > 0 and abs(rl - ra) / media_dir <= tolerancia:
        fator_arred = round(media_dir, 2)
        nome = f"1:{int(fator_arred)}" if fator_arred == int(fator_arred) else f"1:{fator_arred:g}"
        return fator_arred, nome

    # Proporção não padronizada porém uniforme rotacionada
    media_rot = (rl_rot + ra_rot) / 2.0
    if media_rot > 0 and abs(rl_rot - ra_rot) / media_rot <= tolerancia:
        fator_arred = round(media_rot, 2)
        nome = f"1:{int(fator_arred)}" if fator_arred == int(fator_arred) else f"1:{fator_arred:g}"
        return fator_arred, nome

    return 1.0, "1:1"


@dataclass
class ItemTriagem:
    """Representa um item individual em processo de triagem visual."""
    arquivo: str
    caminho_completo: Optional[pathlib.Path] = None
    larg_pdf_m: float = 0.0
    alt_pdf_m: float = 0.0
    escala: str = "1:1"
    fator_escala: float = 1.0
    larg_final_m: float = 0.0
    alt_final_m: float = 0.0
    quantidade: int = 1
    material: Optional[str] = None
    cliente: Optional[str] = None
    os: Optional[str] = None
    descricao: Optional[str] = None
    status: str = "PENDENTE"  # "PENDENTE", "VALIDO", "DESPACHADO"
    avisos: List[str] = field(default_factory=list)
    origem_dados: str = "arquivo"
    tipo_match: Optional[str] = None
    linha_planilha: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.fator_escala <= 0:
            self.fator_escala = interpretar_escala(self.escala)
        if self.larg_final_m <= 0 and self.larg_pdf_m > 0:
            self.larg_final_m = round(self.larg_pdf_m * self.fator_escala, 4)
        if self.alt_final_m <= 0 and self.alt_pdf_m > 0:
            self.alt_final_m = round(self.alt_pdf_m * self.fator_escala, 4)
        self.validar()

    def aplicar_escala(self, escala: str):
        """Atualiza a escala, recalcula dimensões finais e revalida o item."""
        self.escala = str(escala or "1:1").strip()
        self.fator_escala = interpretar_escala(self.escala)
        if self.larg_pdf_m > 0 and self.alt_pdf_m > 0:
            self.larg_final_m = round(self.larg_pdf_m * self.fator_escala, 4)
            self.alt_final_m = round(self.alt_pdf_m * self.fator_escala, 4)
        self.validar()

    def validar(self) -> bool:
        """
        Verifica integridade das informações necessárias para despacho:
        - Material preenchido
        - Quantidade >= 1
        - Dimensões finais (largura e altura) > 0
        """
        if self.status == "DESPACHADO":
            return True

        erros: List[str] = []
        if not self.material or not str(self.material).strip():
            erros.append("Material não definido")
        if self.quantidade <= 0:
            erros.append("Quantidade deve ser >= 1")
        if self.larg_final_m <= 0:
            erros.append("Largura final não informada ou zero")
        if self.alt_final_m <= 0:
            erros.append("Altura final não informada ou zero")

        if erros:
            self.status = "PENDENTE"
            self.avisos = erros
            return False

        self.status = "VALIDO"
        self.avisos = []
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arquivo": self.arquivo,
            "caminho_completo": str(self.caminho_completo) if self.caminho_completo else None,
            "larg_pdf_m": self.larg_pdf_m,
            "alt_pdf_m": self.alt_pdf_m,
            "escala": self.escala,
            "fator_escala": self.fator_escala,
            "larg_final_m": self.larg_final_m,
            "alt_final_m": self.alt_final_m,
            "quantidade": self.quantidade,
            "material": self.material,
            "cliente": self.cliente,
            "os": self.os,
            "descricao": self.descricao,
            "status": self.status,
            "avisos": list(self.avisos),
            "origem_dados": self.origem_dados,
            "tipo_match": self.tipo_match,
            "linha_planilha": self.linha_planilha,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ItemTriagem":
        caminho = pathlib.Path(d["caminho_completo"]) if d.get("caminho_completo") else None
        return cls(
            arquivo=d["arquivo"],
            caminho_completo=caminho,
            larg_pdf_m=float(d.get("larg_pdf_m", 0.0)),
            alt_pdf_m=float(d.get("alt_pdf_m", 0.0)),
            escala=str(d.get("escala", "1:1")),
            fator_escala=float(d.get("fator_escala", 1.0)),
            larg_final_m=float(d.get("larg_final_m", 0.0)),
            alt_final_m=float(d.get("alt_final_m", 0.0)),
            quantidade=int(d.get("quantidade", 1)),
            material=d.get("material"),
            cliente=d.get("cliente"),
            os=d.get("os"),
            descricao=d.get("descricao"),
            status=d.get("status", "PENDENTE"),
            avisos=list(d.get("avisos", [])),
            origem_dados=d.get("origem_dados", "manual"),
            tipo_match=d.get("tipo_match"),
            linha_planilha=d.get("linha_planilha"),
        )


def preparar_itens_para_triagem(
    arquivos: Union[List[Union[str, pathlib.Path]], pathlib.Path, str],
    config: Optional[dict] = None,
    dados_planilha: Optional[List[Dict[str, Any]]] = None,
) -> List[ItemTriagem]:
    """
    Prepara e pré-carrega os itens para a tela de triagem:
    1. Lê arquivos locais e suas medidas físicas reais via motor_pdf (para PDFs).
    2. Aplica análise sintática do nome de arquivo com parser_regras.
    3. Cruza dados com a planilha importada se fornecida.
    4. Detecta ou sugere escalas industriais automaticamente.
    5. Gera os objetos ItemTriagem validados.
    """
    # Normaliza lista de arquivos
    caminhos: List[pathlib.Path] = []
    if isinstance(arquivos, (str, pathlib.Path)):
        p = pathlib.Path(arquivos)
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    caminhos.append(f)
        else:
            caminhos.append(p)
    else:
        for item in arquivos:
            caminhos.append(pathlib.Path(str(item)))

    cfg = config or modulo_config.carregar_config()
    parser = ParserRegrasNomes.obter_instancia(cfg)

    # Executa cruzamento com planilha se disponível
    matches_map: Dict[str, Any] = {}
    if dados_planilha:
        lista_matches = cruzar_arquivos_com_planilha(caminhos, dados_planilha)
        for m in lista_matches:
            matches_map[m.arquivo_nome] = m

    itens_triagem: List[ItemTriagem] = []

    for cam in caminhos:
        nome_arquivo = cam.name
        avisos_leitura: List[str] = []

        # 1. Medidas reais nativas do arquivo PDF
        larg_pdf_m = 0.0
        alt_pdf_m = 0.0
        if cam.suffix.lower() == ".pdf" and cam.is_file():
            try:
                with abrir_pdf(cam) as doc:
                    if doc.paginas:
                        larg_pdf_m = round(doc.paginas[0].largura_m, 4)
                        alt_pdf_m = round(doc.paginas[0].altura_m, 4)
            except Exception as erro:
                avisos_leitura.append(f"Aviso ao ler PDF: {erro}")

        # 2. Parse sintático do nome do arquivo
        res_parse: ResultadoParse = parser.parsear(nome_arquivo, cfg)

        # 3. Cruzamento com planilha
        match_info = matches_map.get(nome_arquivo)
        linha_planilha = match_info.linha_planilha if match_info else None
        tipo_match = match_info.tipo_match if match_info else None

        # 4. Determinação dos campos prioritários (Planilha > Nome > PDF)
        origem = "arquivo"
        if linha_planilha:
            origem = f"planilha ({tipo_match})"
        elif res_parse.sucesso:
            origem = "nome"

        # Material
        material_final = None
        if linha_planilha and linha_planilha.get("material"):
            material_final = str(linha_planilha["material"]).strip()
        elif res_parse.material:
            material_final = res_parse.material

        # Cliente
        cliente_final = None
        if linha_planilha and linha_planilha.get("cliente"):
            cliente_final = str(linha_planilha["cliente"]).strip()
        elif res_parse.cliente:
            cliente_final = res_parse.cliente

        # OS / Pedido
        os_final = None
        if linha_planilha and linha_planilha.get("os"):
            os_final = str(linha_planilha["os"]).strip()
        elif res_parse.os:
            os_final = res_parse.os

        # Quantidade
        qtd_final = 1
        if linha_planilha and linha_planilha.get("quantidade"):
            qtd_final = int(linha_planilha["quantidade"])
        elif res_parse.qtd and res_parse.qtd > 0:
            qtd_final = int(res_parse.qtd)

        # Descrição
        desc_final = None
        if linha_planilha and linha_planilha.get("descricao"):
            desc_final = str(linha_planilha["descricao"]).strip()
        elif res_parse.descricao:
            desc_final = res_parse.descricao

        # Medidas alvo pretendidas
        larg_alvo_m = None
        alt_alvo_m = None
        if linha_planilha and linha_planilha.get("largura_m") and linha_planilha.get("altura_m"):
            larg_alvo_m = float(linha_planilha["largura_m"])
            alt_alvo_m = float(linha_planilha["altura_m"])
        elif res_parse.sucesso and res_parse.largura_m and res_parse.altura_m:
            larg_alvo_m = float(res_parse.largura_m)
            alt_alvo_m = float(res_parse.altura_m)

        # Escala e medidas finais
        escala_final = "1:1"
        fator_escala = 1.0

        if linha_planilha and linha_planilha.get("escala"):
            escala_final = str(linha_planilha["escala"]).strip()
            fator_escala = interpretar_escala(escala_final)
        elif larg_pdf_m > 0 and alt_pdf_m > 0 and larg_alvo_m and alt_alvo_m:
            fator_escala, escala_final = detectar_ou_sugerir_escala(
                larg_pdf_m, alt_pdf_m, larg_alvo_m, alt_alvo_m
            )

        if larg_pdf_m > 0 and alt_pdf_m > 0 and escala_final != "1:1":
            larg_calculada = round(larg_pdf_m * fator_escala, 4)
            alt_calculada = round(alt_pdf_m * fator_escala, 4)
        elif larg_alvo_m and alt_alvo_m and larg_alvo_m > 0 and alt_alvo_m > 0:
            larg_calculada = round(larg_alvo_m, 4)
            alt_calculada = round(alt_alvo_m, 4)
        else:
            larg_calculada = round(larg_pdf_m, 4)
            alt_calculada = round(alt_pdf_m, 4)

        item = ItemTriagem(
            arquivo=nome_arquivo,
            caminho_completo=cam,
            larg_pdf_m=larg_pdf_m,
            alt_pdf_m=alt_pdf_m,
            escala=escala_final,
            fator_escala=fator_escala,
            larg_final_m=larg_calculada,
            alt_final_m=alt_calculada,
            quantidade=qtd_final,
            material=material_final,
            cliente=cliente_final,
            os=os_final,
            descricao=desc_final,
            status="PENDENTE",
            avisos=avisos_leitura,
            origem_dados=origem,
            tipo_match=tipo_match,
            linha_planilha=linha_planilha,
        )
        itens_triagem.append(item)

    return itens_triagem


class JanelaEdicaoLote(tk.Toplevel):
    """Diálogo modal para aplicar alterações conjuntas em múltiplos itens selecionados."""

    def __init__(self, pai: JanelaTriagem, itens_selecionados: List[ItemTriagem]):
        super().__init__(pai)
        self.pai = pai
        self.itens = itens_selecionados
        self.title(f"Edição em Lote ({len(itens_selecionados)} itens selecionados)")
        self.geometry("480x420")
        self.minsize(420, 360)
        self.configure(bg=cores.fundo)
        tema.aplicar_padroes(self)

        self.transient(pai)
        self.grab_set()

        self._montar_ui()

    def _montar_ui(self):
        container = tk.Frame(self, bg=cores.cartao, padx=16, pady=16)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(
            container,
            text=f"Aplicar a {len(self.itens)} item(ns) selecionado(s):",
            font=("Segoe UI", 10, "bold"),
            bg=cores.cartao,
            fg=cores.texto,
        ).pack(anchor="w", pady=(0, 12))

        # Checkboxes e campos
        # 1. Material
        self.var_ch_mat = tk.BooleanVar(value=False)
        self.var_mat = tk.StringVar(value="")
        f_mat = tk.Frame(container, bg=cores.cartao)
        f_mat.pack(fill="x", pady=4)
        tk.Checkbutton(
            f_mat,
            text="Material:",
            variable=self.var_ch_mat,
            font=("Segoe UI", 9),
            bg=cores.cartao,
            fg=cores.texto,
            activebackground=cores.cartao,
        ).pack(side="left")
        materiais_disponiveis = list(self.pai.config_dados.get("materiais", {}).keys())
        self.cb_mat = ttk.Combobox(f_mat, textvariable=self.var_mat, values=materiais_disponiveis, width=22)
        self.cb_mat.pack(side="right")

        # 2. Cliente
        self.var_ch_cli = tk.BooleanVar(value=False)
        self.var_cli = tk.StringVar(value="")
        f_cli = tk.Frame(container, bg=cores.cartao)
        f_cli.pack(fill="x", pady=4)
        tk.Checkbutton(
            f_cli,
            text="Cliente:",
            variable=self.var_ch_cli,
            font=("Segoe UI", 9),
            bg=cores.cartao,
            fg=cores.texto,
            activebackground=cores.cartao,
        ).pack(side="left")
        self.ent_cli = tk.Entry(f_cli, textvariable=self.var_cli, width=24, bg=cores.campo, fg=cores.texto)
        self.ent_cli.pack(side="right")

        # 3. OS
        self.var_ch_os = tk.BooleanVar(value=False)
        self.var_os = tk.StringVar(value="")
        f_os = tk.Frame(container, bg=cores.cartao)
        f_os.pack(fill="x", pady=4)
        tk.Checkbutton(
            f_os,
            text="OS / Pedido:",
            variable=self.var_ch_os,
            font=("Segoe UI", 9),
            bg=cores.cartao,
            fg=cores.texto,
            activebackground=cores.cartao,
        ).pack(side="left")
        self.ent_os = tk.Entry(f_os, textvariable=self.var_os, width=24, bg=cores.campo, fg=cores.texto)
        self.ent_os.pack(side="right")

        # 4. Escala
        self.var_ch_esc = tk.BooleanVar(value=False)
        self.var_esc = tk.StringVar(value="1:1")
        f_esc = tk.Frame(container, bg=cores.cartao)
        f_esc.pack(fill="x", pady=4)
        tk.Checkbutton(
            f_esc,
            text="Escala:",
            variable=self.var_ch_esc,
            font=("Segoe UI", 9),
            bg=cores.cartao,
            fg=cores.texto,
            activebackground=cores.cartao,
        ).pack(side="left")
        self.cb_esc = ttk.Combobox(f_esc, textvariable=self.var_esc, values=ESCALAS_COMUNS, width=22)
        self.cb_esc.pack(side="right")

        # 5. Quantidade
        self.var_ch_qtd = tk.BooleanVar(value=False)
        self.var_qtd = tk.StringVar(value="1")
        f_qtd = tk.Frame(container, bg=cores.cartao)
        f_qtd.pack(fill="x", pady=4)
        tk.Checkbutton(
            f_qtd,
            text="Quantidade:",
            variable=self.var_ch_qtd,
            font=("Segoe UI", 9),
            bg=cores.cartao,
            fg=cores.texto,
            activebackground=cores.cartao,
        ).pack(side="left")
        self.ent_qtd = tk.Entry(f_qtd, textvariable=self.var_qtd, width=24, bg=cores.campo, fg=cores.texto)
        self.ent_qtd.pack(side="right")

        # Botões de confirmação
        botoes = tk.Frame(container, bg=cores.cartao)
        botoes.pack(fill="x", pady=(20, 0))

        tk.Button(
            botoes,
            text="Cancelar",
            font=("Segoe UI", 9),
            bg=cores.cartao,
            fg=cores.texto,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            botoes,
            text="Aplicar Alterações",
            font=("Segoe UI", 9, "bold"),
            bg=cores.acento,
            fg=cores.sobre_acento,
            relief="flat",
            padx=14,
            pady=4,
            command=self._confirmar,
        ).pack(side="right")

    def _confirmar(self):
        valores_aplicar: Dict[str, Any] = {}
        if self.var_ch_mat.get() and self.var_mat.get().strip():
            valores_aplicar["material"] = self.var_mat.get().strip()
        if self.var_ch_cli.get() and self.var_cli.get().strip():
            valores_aplicar["cliente"] = self.var_cli.get().strip()
        if self.var_ch_os.get() and self.var_os.get().strip():
            valores_aplicar["os"] = self.var_os.get().strip()
        if self.var_ch_esc.get() and self.var_esc.get().strip():
            valores_aplicar["escala"] = self.var_esc.get().strip()
        if self.var_ch_qtd.get():
            try:
                qtd = int(self.var_qtd.get().strip())
                if qtd > 0:
                    valores_aplicar["quantidade"] = qtd
            except ValueError:
                pass

        if not valores_aplicar:
            messagebox.showwarning("Aviso", "Nenhum campo selecionado para aplicação em lote.", parent=self)
            return

        self.pai.aplicar_edicao_lote(self.itens, valores_aplicar)
        self.destroy()


class JanelaTriagem(tk.Toplevel):
    """
    Janela de Triagem Visual em Lote com tabela interativa, edição rápida,
    edição em lote e despacho de itens validados.
    """

    def __init__(
        self,
        parent=None,
        config: Optional[dict] = None,
        arquivos: Optional[List[Union[str, pathlib.Path]]] = None,
        dados_planilha: Optional[List[Dict[str, Any]]] = None,
        ao_despachar: Optional[Callable[[List[ItemTriagem]], None]] = None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.config_dados = config or modulo_config.carregar_config()
        self.ao_despachar = ao_despachar

        self.itens: List[ItemTriagem] = []
        self.dados_planilha_carregados: Optional[List[Dict[str, Any]]] = dados_planilha

        self.title("Triagem Visual em Lote — Produção e Escalas")
        self.geometry("1180x720")
        self.minsize(940, 560)
        self.configure(bg=cores.fundo)
        tema.aplicar_padroes(self)

        self._montar_cabecalho()
        self._montar_barra_ferramentas()
        self._montar_tabela()
        self._montar_painel_edicao_rapida()

        # Carregar arquivos iniciais se fornecidos
        if arquivos:
            self.carregar_arquivos(arquivos, dados_planilha=self.dados_planilha_carregados)

    def _montar_cabecalho(self):
        topo = tk.Frame(self, bg=cores.cartao, highlightbackground=cores.borda, highlightthickness=1)
        topo.pack(fill="x", padx=16, pady=(12, 6))

        titulo_box = tk.Frame(topo, bg=cores.cartao)
        titulo_box.pack(side="left", padx=16, pady=10)

        tk.Label(
            titulo_box,
            text="TRIAGEM VISUAL EM LOTE",
            font=("Segoe UI", 12, "bold"),
            bg=cores.cartao,
            fg=cores.texto,
        ).pack(anchor="w")

        tk.Label(
            titulo_box,
            text="Auditoria de medidas de PDFs, escalas gráficas (1:10, 1:20...) e cruzamento com planilhas",
            font=("Segoe UI", 8),
            bg=cores.cartao,
            fg=cores.texto2,
        ).pack(anchor="w")

        # Contadores de status
        chips = tk.Frame(topo, bg=cores.cartao)
        chips.pack(side="right", padx=16, pady=10)

        self.var_total = tk.StringVar(value="Total: 0")
        self.var_validos = tk.StringVar(value="Válidos: 0")
        self.var_pendentes = tk.StringVar(value="Pendentes: 0")
        self.var_despachados = tk.StringVar(value="Despachados: 0")

        self.lbl_chip_total = tk.Label(chips, textvariable=self.var_total, font=("Segoe UI", 9, "bold"),
                                       bg=cores.campo, fg=cores.texto, padx=8, pady=3)
        self.lbl_chip_total.pack(side="left", padx=3)

        self.lbl_chip_validos = tk.Label(chips, textvariable=self.var_validos, font=("Segoe UI", 9, "bold"),
                                         bg=cores.campo, fg=cores.ok, padx=8, pady=3)
        self.lbl_chip_validos.pack(side="left", padx=3)

        self.lbl_chip_pendentes = tk.Label(chips, textvariable=self.var_pendentes, font=("Segoe UI", 9, "bold"),
                                           bg=cores.campo, fg=cores.aviso, padx=8, pady=3)
        self.lbl_chip_pendentes.pack(side="left", padx=3)

        self.lbl_chip_despachados = tk.Label(chips, textvariable=self.var_despachados, font=("Segoe UI", 9, "bold"),
                                             bg=cores.campo, fg=cores.acento, padx=8, pady=3)
        self.lbl_chip_despachados.pack(side="left", padx=3)

    def _montar_barra_ferramentas(self):
        barra = tk.Frame(self, bg=cores.fundo)
        barra.pack(fill="x", padx=16, pady=(4, 6))

        tk.Button(
            barra,
            text="📁  Carregar Pasta...",
            font=("Segoe UI", 9, "bold"),
            bg=cores.cartao,
            fg=cores.texto,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.ao_clicar_carregar_pasta,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            barra,
            text="📊  Importar Planilha (CSV/XLSX)...",
            font=("Segoe UI", 9, "bold"),
            bg=cores.cartao,
            fg=cores.texto,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.ao_clicar_importar_planilha,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            barra,
            text="✏️  Editar em Lote (Seleção)...",
            font=("Segoe UI", 9),
            bg=cores.cartao,
            fg=cores.texto,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.abrir_edicao_lote,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            barra,
            text="🔄  Revalidar Tudo",
            font=("Segoe UI", 9),
            bg=cores.cartao,
            fg=cores.texto,
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.revalidar_tudo,
        ).pack(side="left", padx=(0, 6))

        self.btn_despachar = tk.Button(
            barra,
            text="🚀  Despachar Validados",
            font=("Segoe UI", 10, "bold"),
            bg=cores.acento,
            fg=cores.sobre_acento,
            relief="flat",
            padx=16,
            pady=4,
            cursor="hand2",
            command=self.despachar_validados,
        )
        self.btn_despachar.pack(side="right")

    def _montar_tabela(self):
        quadro_tab = tk.Frame(self, bg=cores.cartao, highlightbackground=cores.borda, highlightthickness=1)
        quadro_tab.pack(fill="both", expand=True, padx=16, pady=4)

        colunas = (
            "status",
            "arquivo",
            "qtd",
            "escala",
            "medida_pdf",
            "medida_final",
            "material",
            "cliente",
            "os",
            "origem",
        )

        self.tree = ttk.Treeview(quadro_tab, columns=colunas, show="headings", selectmode="extended")

        self.tree.heading("status", text="Status")
        self.tree.heading("arquivo", text="Arquivo / Arte")
        self.tree.heading("qtd", text="Qtd")
        self.tree.heading("escala", text="Escala")
        self.tree.heading("medida_pdf", text="Medida PDF")
        self.tree.heading("medida_final", text="Medida Final")
        self.tree.heading("material", text="Material")
        self.tree.heading("cliente", text="Cliente")
        self.tree.heading("os", text="OS")
        self.tree.heading("origem", text="Cruzamento")

        self.tree.column("status", width=95, anchor="center")
        self.tree.column("arquivo", width=250, anchor="w")
        self.tree.column("qtd", width=45, anchor="center")
        self.tree.column("escala", width=65, anchor="center")
        self.tree.column("medida_pdf", width=110, anchor="center")
        self.tree.column("medida_final", width=110, anchor="center")
        self.tree.column("material", width=140, anchor="w")
        self.tree.column("cliente", width=120, anchor="w")
        self.tree.column("os", width=80, anchor="center")
        self.tree.column("origem", width=110, anchor="w")

        # Scrollbars
        sb_y = ttk.Scrollbar(quadro_tab, orient="vertical", command=self.tree.yview)
        sb_x = ttk.Scrollbar(quadro_tab, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        quadro_tab.grid_rowconfigure(0, weight=1)
        quadro_tab.grid_columnconfigure(0, weight=1)

        # Tags para coloração
        self.tree.tag_configure("tag_valido", foreground=cores.ok)
        self.tree.tag_configure("tag_pendente", foreground=cores.aviso)
        self.tree.tag_configure("tag_despachado", foreground=cores.acento)

        self.tree.bind("<<TreeviewSelect>>", self._ao_selecionar_linha)

    def _montar_painel_edicao_rapida(self):
        painel = tk.Frame(self, bg=cores.cartao, highlightbackground=cores.borda, highlightthickness=1)
        painel.pack(fill="x", padx=16, pady=(6, 12))

        topo_p = tk.Frame(painel, bg=cores.cartao)
        topo_p.pack(fill="x", padx=12, pady=(8, 4))

        tk.Label(
            topo_p,
            text="EDIÇÃO RÁPIDA DA LINHA SELECIONADA",
            font=("Segoe UI", 8, "bold"),
            bg=cores.cartao,
            fg=cores.texto2,
        ).pack(side="left")

        self.lbl_arquivo_selecionado = tk.Label(
            topo_p,
            text="(Nenhum arquivo selecionado)",
            font=("Segoe UI", 8),
            bg=cores.cartao,
            fg=cores.texto,
        )
        self.lbl_arquivo_selecionado.pack(side="left", padx=12)

        linha_campos = tk.Frame(painel, bg=cores.cartao)
        linha_campos.pack(fill="x", padx=12, pady=(0, 10))

        # Variáveis
        self.var_ed_qtd = tk.StringVar(value="1")
        self.var_ed_escala = tk.StringVar(value="1:1")
        self.var_ed_larg = tk.StringVar(value="0.0")
        self.var_ed_alt = tk.StringVar(value="0.0")
        self.var_ed_material = tk.StringVar(value="")
        self.var_ed_cliente = tk.StringVar(value="")
        self.var_ed_os = tk.StringVar(value="")

        def campo_pequeno(rotulo, var, largura=10):
            c = tk.Frame(linha_campos, bg=cores.cartao)
            c.pack(side="left", padx=(0, 10))
            tk.Label(c, text=rotulo, font=("Segoe UI", 8), bg=cores.cartao, fg=cores.texto2).pack(anchor="w")
            ent = tk.Entry(c, textvariable=var, width=largura, bg=cores.campo, fg=cores.texto, font=("Segoe UI", 9))
            ent.pack(anchor="w")
            return ent

        campo_pequeno("Qtd", self.var_ed_qtd, largura=5)

        # Escala combobox
        c_esc = tk.Frame(linha_campos, bg=cores.cartao)
        c_esc.pack(side="left", padx=(0, 10))
        tk.Label(c_esc, text="Escala", font=("Segoe UI", 8), bg=cores.cartao, fg=cores.texto2).pack(anchor="w")
        cb_esc = ttk.Combobox(c_esc, textvariable=self.var_ed_escala, values=ESCALAS_COMUNS, width=7)
        cb_esc.pack(anchor="w")
        cb_esc.bind("<<ComboboxSelected>>", self._ao_mudar_escala_edicao)

        campo_pequeno("Larg. Final (m)", self.var_ed_larg, largura=11)
        campo_pequeno("Alt. Final (m)", self.var_ed_alt, largura=11)

        # Material Combobox
        c_mat = tk.Frame(linha_campos, bg=cores.cartao)
        c_mat.pack(side="left", padx=(0, 10))
        tk.Label(c_mat, text="Material", font=("Segoe UI", 8), bg=cores.cartao, fg=cores.texto2).pack(anchor="w")
        materiais = list(self.config_dados.get("materiais", {}).keys())
        self.cb_ed_mat = ttk.Combobox(c_mat, textvariable=self.var_ed_material, values=materiais, width=18)
        self.cb_ed_mat.pack(anchor="w")

        campo_pequeno("Cliente", self.var_ed_cliente, largura=16)
        campo_pequeno("OS / Pedido", self.var_ed_os, largura=10)

        self.btn_salvar_linha = tk.Button(
            linha_campos,
            text="💾  Salvar Linha",
            font=("Segoe UI", 9, "bold"),
            bg=cores.acento,
            fg=cores.sobre_acento,
            relief="flat",
            padx=12,
            pady=3,
            cursor="hand2",
            command=self.salvar_edicao_rapida,
        )
        self.btn_salvar_linha.pack(side="right", pady=(12, 0))

    def _ao_mudar_escala_edicao(self, _evento=None):
        """Ao mudar a escala no combobox de edição rápida, recalcula as medidas finais."""
        selecionados = self.obter_selecionados()
        if not selecionados:
            return
        item = selecionados[0]
        if item.larg_pdf_m > 0 and item.alt_pdf_m > 0:
            fator = interpretar_escala(self.var_ed_escala.get())
            self.var_ed_larg.set(str(round(item.larg_pdf_m * fator, 4)))
            self.var_ed_alt.set(str(round(item.alt_pdf_m * fator, 4)))

    def _ao_selecionar_linha(self, _evento=None):
        selecionados = self.obter_selecionados()
        if not selecionados:
            self.lbl_arquivo_selecionado.config(text="(Nenhum arquivo selecionado)")
            return

        item = selecionados[0]
        self.lbl_arquivo_selecionado.config(
            text=f"{item.arquivo} | PDF: {item.larg_pdf_m:.2f}x{item.alt_pdf_m:.2f}m | Status: {item.status}"
        )
        self.var_ed_qtd.set(str(item.quantidade))
        self.var_ed_escala.set(item.escala)
        self.var_ed_larg.set(str(item.larg_final_m))
        self.var_ed_alt.set(str(item.alt_final_m))
        self.var_ed_material.set(item.material or "")
        self.var_ed_cliente.set(item.cliente or "")
        self.var_ed_os.set(item.os or "")

    def salvar_edicao_rapida(self):
        """Aplica os valores da edição rápida no item selecionado."""
        selecionados = self.obter_selecionados()
        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione uma linha para salvar alterações.", parent=self)
            return

        item = selecionados[0]
        try:
            qtd = max(1, int(self.var_ed_qtd.get().strip()))
            item.quantidade = qtd
        except ValueError:
            pass

        item.escala = self.var_ed_escala.get().strip() or "1:1"
        item.fator_escala = interpretar_escala(item.escala)

        try:
            item.larg_final_m = float(self.var_ed_larg.get().strip().replace(",", "."))
            item.alt_final_m = float(self.var_ed_alt.get().strip().replace(",", "."))
        except ValueError:
            pass

        item.material = self.var_ed_material.get().strip() or None
        item.cliente = self.var_ed_cliente.get().strip() or None
        item.os = self.var_ed_os.get().strip() or None

        item.validar()
        self.atualizar_tabela()

    def adicionar_itens(self, novos_itens: List[ItemTriagem]):
        """Adiciona itens à lista e atualiza a interface."""
        self.itens.extend(novos_itens)
        self.atualizar_tabela()

    def limpar_itens(self):
        """Limpa todos os itens da triagem."""
        self.itens.clear()
        self.atualizar_tabela()

    def obter_itens(self) -> List[ItemTriagem]:
        return list(self.itens)

    def obter_selecionados(self) -> List[ItemTriagem]:
        selecionados: List[ItemTriagem] = []
        for iid in self.tree.selection():
            try:
                idx = int(iid)
                if 0 <= idx < len(self.itens):
                    selecionados.append(self.itens[idx])
            except ValueError:
                pass
        return selecionados

    def atualizar_tabela(self):
        """Re-renderiza a Treeview e atualiza os contadores."""
        selecionados_idx = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())

        qtd_validos = 0
        qtd_pendentes = 0
        qtd_despachados = 0

        for idx, item in enumerate(self.itens):
            tag = "tag_pendente"
            status_icone = "🟡 PENDENTE"
            if item.status == "VALIDO":
                tag = "tag_valido"
                status_icone = "🟢 VÁLIDO"
                qtd_validos += 1
            elif item.status == "DESPACHADO":
                tag = "tag_despachado"
                status_icone = "🚀 DESPACHADO"
                qtd_despachados += 1
            else:
                qtd_pendentes += 1

            medida_pdf_txt = f"{item.larg_pdf_m:.2f} x {item.alt_pdf_m:.2f} m" if item.larg_pdf_m > 0 else "-"
            medida_final_txt = f"{item.larg_final_m:.2f} x {item.alt_final_m:.2f} m" if item.larg_final_m > 0 else "-"

            iid = str(idx)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    status_icone,
                    item.arquivo,
                    item.quantidade,
                    item.escala,
                    medida_pdf_txt,
                    medida_final_txt,
                    item.material or "—",
                    item.cliente or "—",
                    item.os or "—",
                    item.origem_dados,
                ),
                tags=(tag,),
            )

        # Restaurar seleção se possível
        for iid in selecionados_idx:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)

        # Atualizar contadores
        self.var_total.set(f"Total: {len(self.itens)}")
        self.var_validos.set(f"Válidos: {qtd_validos}")
        self.var_pendentes.set(f"Pendentes: {qtd_pendentes}")
        self.var_despachados.set(f"Despachados: {qtd_despachados}")

    def carregar_arquivos(
        self,
        arquivos: Union[List[Union[str, pathlib.Path]], pathlib.Path, str],
        dados_planilha: Optional[List[Dict[str, Any]]] = None,
    ):
        """Carrega e prepara arquivos para a triagem."""
        itens = preparar_itens_para_triagem(arquivos, config=self.config_dados, dados_planilha=dados_planilha)
        self.itens = itens
        self.atualizar_tabela()

    def ao_clicar_carregar_pasta(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta de arquivos de impressão", parent=self)
        if not pasta:
            return
        self.carregar_arquivos(pasta, dados_planilha=self.dados_planilha_carregados)

    def ao_clicar_importar_planilha(self):
        caminho_arq = filedialog.askopenfilename(
            title="Importar Planilha de Pedido / Corte",
            filetypes=[
                ("Planilhas Suportadas (*.csv, *.xlsx, *.xlsm)", "*.csv;*.xlsx;*.xlsm"),
                ("Arquivos CSV (*.csv)", "*.csv"),
                ("Arquivos Excel (*.xlsx, *.xlsm)", "*.xlsx;*.xlsm"),
                ("Todos os Arquivos (*.*)", "*.*"),
            ],
            parent=self,
        )
        if not caminho_arq:
            return

        try:
            dados = ler_planilha(caminho_arq)
            if not dados:
                messagebox.showwarning("Planilha Vazia", "A planilha não contém linhas de dados válidas.", parent=self)
                return

            self.dados_planilha_carregados = dados

            # Se já temos arquivos carregados, refaz o cruzamento
            if self.itens:
                arquivos = [it.caminho_completo or it.arquivo for it in self.itens]
                self.carregar_arquivos(arquivos, dados_planilha=dados)
            else:
                messagebox.showinfo(
                    "Planilha Carregada",
                    f"Foram lidas {len(dados)} linhas da planilha com sucesso.\nCarregue a pasta de arquivos para cruzar os dados.",
                    parent=self,
                )
        except Exception as e:
            messagebox.showerror("Erro ao Importar Planilha", f"Falha ao ler planilha:\n{e}", parent=self)

    def abrir_edicao_lote(self):
        selecionados = self.obter_selecionados()
        if not selecionados:
            messagebox.showwarning("Aviso", "Selecione ao menos um item na tabela para editar em lote.", parent=self)
            return

        JanelaEdicaoLote(self, selecionados)

    def aplicar_edicao_lote(self, itens_alvo: List[ItemTriagem], valores: Dict[str, Any]):
        """Aplica alterações aos itens indicados e atualiza a interface."""
        for item in itens_alvo:
            if "material" in valores:
                item.material = valores["material"]
            if "cliente" in valores:
                item.cliente = valores["cliente"]
            if "os" in valores:
                item.os = valores["os"]
            if "quantidade" in valores:
                item.quantidade = int(valores["quantidade"])
            if "escala" in valores:
                item.aplicar_escala(valores["escala"])
            else:
                item.validar()

        self.atualizar_tabela()

    def revalidar_tudo(self):
        """Executa revalidação de todos os itens da triagem."""
        for item in self.itens:
            item.validar()
        self.atualizar_tabela()

    def despachar_validados(self) -> List[ItemTriagem]:
        """Marca itens válidos como despachados e executa callback."""
        validos = [item for item in self.itens if item.status == "VALIDO"]
        if not validos:
            messagebox.showwarning(
                "Nenhum Item Válido",
                "Não há nenhum item com status 'VÁLIDO' pronto para despacho.\nVerifique pendências de material, escala ou medidas.",
                parent=self,
            )
            return []

        for item in validos:
            item.status = "DESPACHADO"

        self.atualizar_tabela()

        if self.ao_despachar:
            try:
                self.ao_despachar(validos)
            except Exception as e:
                messagebox.showerror("Erro no Despacho", f"Ocorreu um erro ao processar o despacho:\n{e}", parent=self)
                return validos

        messagebox.showinfo(
            "Sucesso",
            f"{len(validos)} arquivo(s) despachado(s) com sucesso!",
            parent=self,
        )
        return validos
