"""
Tela de montagem: seleção por arquivo, avisos e mapa do encaixe real.

A prévia e a montagem usam o mesmo plano. Miniaturas são apenas recursos
da tela; o caminho de produção preserva a arte original.
"""
import io
import math
import os
import pathlib
import queue
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import messagebox, ttk

import montagem
import previas_impressao
import tempo_impressao
from config import carregar_config, salvar_config
from tema import cores

_MOSTRA_RESULTADO_MS = 20000
_CONSUMIR_MS = 80
_LIMITE_CACHE = 120


def _folga_m_do_texto(texto):
    """O controle mostra centímetros; o motor recebe metros."""
    try:
        centimetros = float(str(texto).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError("Informe o espaçamento em centímetros.") from None
    if not math.isfinite(centimetros) or centimetros < 1:
        raise ValueError("O espaçamento deve ser de pelo menos 1 cm.")
    return centimetros / 100


def _resolucao_em_palavras(item):
    qualidade = item.get("qualidade", item.get("estado", "nao_verificada"))
    if qualidade == "vetor":
        return "sem imagens raster detectadas"
    dpi = item.get("dpi")
    if dpi is None:
        return "resolução não verificada"
    if qualidade == "ok":
        return f"{dpi:.0f} dpi — boa de perto"
    distancia = item.get("distancia_limpa_m")
    if distancia is None:
        distancia = montagem.distancia_limpa_m(dpi)
    return f"{dpi:.0f} dpi — limpa a partir de {distancia:.1f} m"


def _medida_em_palavras(valores, casas=2):
    if not valores:
        return "—"
    return " × ".join(f"{v:.{casas}f}".replace(".", ",") for v in valores) + " m"


def _itens_por_arquivo(previa):
    juntos = {}
    for folha in previa.get("folhas", []):
        for item in folha.get("itens", []):
            juntos.setdefault(item["arquivo"], []).append(item)
    return juntos


def _avisos_dos_itens(itens):
    avisos = []
    for item in itens:
        for aviso in item.get("avisos", []):
            if aviso not in avisos:
                avisos.append(aviso)
        if item.get("qualidade") in ("aviso", "atencao", "nao_verificada"):
            resolucao = _resolucao_em_palavras(item)
            if resolucao not in avisos:
                avisos.append(resolucao)
        diferenca = item.get("diferenca_mm", 0)
        if abs(diferenca) >= 0.5:
            recado = f"outro lado {diferenca:+.0f} mm do nome"
            if recado not in avisos:
                avisos.append(recado)
    return avisos


def _cor_do_item(item):
    estado = item.get("estado", item.get("qualidade", "ok"))
    if estado in ("aviso", "atencao", "nao_verificada") or item.get("avisos"):
        return cores.alerta
    return cores.acento


class JanelaMontagem(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Montar arte para impressão — UNY CV")
        self.configure(bg=cores.fundo)
        self.config_montagem = carregar_config()
        montagem.garantir_pastas()
        largura = max(640, min(1500, self.winfo_screenwidth() - 60))
        altura = max(480, min(900, self.winfo_screenheight() - 100))
        self.geometry(f"{largura}x{altura}")
        self.minsize(min(1120, largura), min(680, altura))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        topo = tk.Frame(self, bg=cores.fundo)
        topo.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        tk.Label(topo, text="Montar arte para impressão",
                 font=("Segoe UI", 15, "bold"), bg=cores.fundo,
                 fg=cores.texto).pack(anchor="w")
        tk.Label(topo, text="Confira imagem, nome e avisos. Marque as artes, escolha o "
                 "espaçamento e recalcule antes de montar.",
                 font=("Segoe UI", 9), bg=cores.fundo,
                 fg=cores.texto2).pack(anchor="w")
        self.btn_montagem_automatica = tk.Button(
            topo, relief="flat", cursor="hand2", command=self._alternar_montagem_automatica)
        self.btn_montagem_automatica.pack(anchor="e")
        self._atualizar_estado_montagem_automatica()
        self._abas = {}
        caderno = ttk.Notebook(self)
        caderno.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        for nome_maquina in montagem.maquinas_que_montam():
            aba = _AbaMaquina(caderno, nome_maquina)
            caderno.add(aba, text=f"  {montagem.nome_pasta_maquina(nome_maquina)}  ")
            self._abas[nome_maquina] = aba
        if not self._abas:
            tk.Label(self, text="Nenhuma máquina está cadastrada para montar.",
                     bg=cores.fundo, fg=cores.alerta,
                     font=("Segoe UI", 10)).grid(row=1, column=0, padx=20, pady=20)

    def destroy(self):
        for aba in getattr(self, "_abas", {}).values():
            aba.fechar()
        super().destroy()

    def _atualizar_estado_montagem_automatica(self):
        ativa = bool(self.config_montagem.get("montagem_automatica", False))
        estado = "ATIVA" if ativa else "PAUSADA"
        acao = "pausar" if ativa else "reativar"
        self.btn_montagem_automatica.configure(
            text=f"Montagem automática: {estado} · clique para {acao}",
            fg=cores.alerta if ativa else cores.texto2)

    def _alternar_montagem_automatica(self):
        self.config_montagem["montagem_automatica"] = not bool(
            self.config_montagem.get("montagem_automatica", False))
        salvar_config(self.config_montagem)
        self._atualizar_estado_montagem_automatica()


class _AbaMaquina(tk.Frame):
    def __init__(self, master, nome_maquina):
        super().__init__(master, bg=cores.fundo)
        self.nome_maquina = nome_maquina
        self.pasta = montagem.pasta_da_maquina(nome_maquina)
        self._previa = None
        self._ocupada = False
        self._fechando = False
        self._suja = True
        self._geracao = 0
        self._job_resultado = None
        self._job_fila = None
        self._arquivos = {}
        self._selecionados = set()
        self._linhas = {}
        self._nomes_por_linha = {}
        self._config_calculada = None
        self._itens = {}
        self._feitas = []
        self._fila = queue.Queue()
        self._trabalho = ThreadPoolExecutor(max_workers=1, thread_name_prefix="montagem")
        self._trabalho_previas = ThreadPoolExecutor(max_workers=2,
                                                   thread_name_prefix="previa_montagem")
        self._cache_previas = OrderedDict()
        self._previas_pendentes = set()
        self._fotos = {}
        self._zoom = 1.0
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._montar_topo()
        self._montar_conteudo()
        self._montar_resumo()
        self._montar_rodape()
        self.var_folga.trace_add("write", lambda *_: self._configuracao_mudou())
        self.var_largura.trace_add("write", lambda *_: self._configuracao_mudou())
        self.bind("<Destroy>", self._destruida, add="+")
        self._job_fila = self.after(_CONSUMIR_MS, self._consumir)
        self.calcular()

    def _montar_topo(self):
        topo = tk.Frame(self, bg=cores.fundo)
        topo.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        medida = montagem.mesa(self.nome_maquina) or montagem.largura_util(self.nome_maquina)
        texto = (f"chapa de {medida[0]:.2f} × {medida[1]:.2f} m"
                 if isinstance(medida, tuple)
                 else f"largura de montagem até {medida:.2f} m")
        tk.Label(topo, text=texto, font=("Segoe UI", 9, "bold"),
                 bg=cores.fundo, fg=cores.texto).pack(side="left")
        tk.Button(topo, text="📤 abrir a saída", relief="flat", cursor="hand2",
                  command=self._abrir_saida, bg=cores.cartao,
                  fg=cores.acento).pack(side="right")
        tk.Button(topo, text="📂 abrir a pasta", relief="flat", cursor="hand2",
                  command=self._abrir_pasta, bg=cores.cartao,
                  fg=cores.acento).pack(side="right", padx=(0, 8))
        controles = tk.Frame(self, bg=cores.fundo)
        controles.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 8))
        tk.Button(controles, text="Marcar todos", command=self._marcar_todos,
                  relief="flat", bg=cores.cartao, fg=cores.texto,
                  cursor="hand2").pack(side="left")
        tk.Button(controles, text="Limpar seleção", command=self._limpar_selecao,
                  relief="flat", bg=cores.cartao, fg=cores.texto,
                  cursor="hand2").pack(side="left", padx=(6, 14))
        tk.Label(controles, text="Espaço entre artes (cm):",
                 bg=cores.fundo, fg=cores.texto).pack(side="left")
        preferida = montagem.folga_da_montagem(self.nome_maquina, config=carregar_config())
        self.var_folga = tk.StringVar(value=f"{preferida * 100:g}")
        self.entrada_folga = tk.Spinbox(controles, from_=1, to=100, increment=1,
                                       width=6, textvariable=self.var_folga)
        self.entrada_folga.pack(side="left", padx=6)
        tk.Label(controles, text="Largura máx. (cm):", bg=cores.fundo,
                 fg=cores.texto).pack(side="left", padx=(8, 0))
        self.config_preferencias = carregar_config()
        max_largura = montagem.largura_util(self.nome_maquina)
        largura_salva = self.config_preferencias.get("montagem", {}).get(
            self.nome_maquina, {}).get("largura_m", max_largura)
        self.var_largura = tk.StringVar(value=f"{largura_salva * 100:g}")
        largura_minima = (montagem.ROTULO_LARGURA_M
                          + 2 * montagem.margem(self.nome_maquina)) * 100
        self.entrada_largura = tk.Spinbox(controles, from_=largura_minima, to=max_largura * 100,
                                         increment=5, width=8, textvariable=self.var_largura)
        self.entrada_largura.pack(side="left", padx=6)
        tk.Button(controles, text="Salvar preferências desta máquina",
                  command=self._salvar_folga, relief="flat", bg=cores.cartao,
                  fg=cores.acento, cursor="hand2").pack(side="left", padx=6)
        tk.Label(controles, text="Nome protegido na faixa",
                 bg=cores.fundo, fg=cores.texto2,
                 font=("Segoe UI", 8)).pack(side="left", padx=8)

    def _montar_conteudo(self):
        paineis = tk.PanedWindow(self, orient="horizontal", bg=cores.fundo,
                                sashwidth=8, relief="flat")
        paineis.grid(row=2, column=0, sticky="nsew", padx=16)
        lista = tk.Frame(paineis, bg=cores.fundo)
        mapa = tk.Frame(paineis, bg=cores.fundo)
        largura_tela = max(620, self.winfo_screenwidth() - 120)
        paineis.add(lista, minsize=min(600, int(largura_tela * 0.55)),
                    width=900, stretch="always")
        paineis.add(mapa, minsize=min(380, int(largura_tela * 0.38)),
                    width=520, stretch="always")
        lista.columnconfigure(0, weight=1)
        lista.rowconfigure(0, weight=1)
        estilo = ttk.Style(self)
        self._estilo_tabela = f"Montagem{id(self)}.Treeview"
        estilo.configure(self._estilo_tabela, rowheight=86)
        colunas = ("marcar", "quantidade", "pede", "sai", "defeitos")
        self.tabela = ttk.Treeview(lista, columns=colunas, show="tree headings",
                                  height=6, style=self._estilo_tabela,
                                  selectmode="browse")
        self.tabela.heading("#0", text="Imagem + nome · clique para marcar")
        self.tabela.column("#0", width=390, minwidth=240, stretch=True)
        titulos = {
            "marcar": ("✓", 36, "center"),
            "quantidade": ("Páginas / unidades", 110, "center"),
            "pede": ("O nome pede", 110, "center"),
            "sai": ("Vai sair", 115, "center"),
            "defeitos": ("Possíveis defeitos / atenção", 255, "w"),
        }
        for coluna, (titulo, largura, alinhar) in titulos.items():
            self.tabela.heading(coluna, text=titulo)
            self.tabela.column(coluna, width=largura, minwidth=largura,
                               stretch=(coluna == "defeitos"), anchor=alinhar)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        barra_v = ttk.Scrollbar(lista, orient="vertical", command=self.tabela.yview)
        barra_v.grid(row=0, column=1, sticky="ns")
        barra_h = ttk.Scrollbar(lista, orient="horizontal", command=self.tabela.xview)
        barra_h.grid(row=1, column=0, sticky="ew")
        self.tabela.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)
        self.tabela.tag_configure("atencao", foreground=cores.alerta)
        self.tabela.tag_configure("aviso", foreground=cores.parado)
        self.tabela.bind("<Button-1>", self._clicar_arquivo)
        self.tabela.bind("<space>", self._espaco_arquivo)
        self.tabela.bind("<<TreeviewSelect>>", self._detalhar_selecao)
        self.var_arquivo = tk.StringVar(value=str(self.pasta))
        tk.Label(lista, textvariable=self.var_arquivo, bg=cores.fundo,
                 fg=cores.texto2, font=("Segoe UI", 8), anchor="w",
                 justify="left", wraplength=940).grid(row=2, column=0,
                                                     sticky="ew", pady=(5, 0))
        mapa.columnconfigure(0, weight=1)
        mapa.rowconfigure(2, weight=1)
        tk.Label(mapa, text="Prévia do encaixe", bg=cores.fundo, fg=cores.texto,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.escolha_folha = ttk.Combobox(mapa, state="readonly")
        self.escolha_folha.grid(row=1, column=0, sticky="ew", pady=(5, 6))
        self.escolha_folha.bind("<<ComboboxSelected>>", lambda _: self._desenhar_mapa())
        area = tk.Frame(mapa, bg=cores.fundo)
        area.grid(row=2, column=0, sticky="nsew")
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(area, bg=cores.cartao, highlightthickness=1,
                                highlightbackground=cores.borda, width=480, height=480)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        barra = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        barra.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.canvas.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=barra.set, xscrollcommand=horizontal.set)
        self.canvas.bind("<Configure>", lambda _: self._desenhar_mapa())
        zoom = tk.Frame(mapa, bg=cores.fundo)
        zoom.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        for texto, fator in (("−", 0.5), ("+", 2)):
            tk.Button(zoom, text=texto, width=3, command=lambda f=fator: self._alterar_zoom(f),
                      bg=cores.cartao, fg=cores.texto,
                      relief="flat").pack(side="left", padx=(0, 4))
        tk.Button(zoom, text="Ajustar", command=self._ajustar_mapa, relief="flat",
                  bg=cores.cartao, fg=cores.texto).pack(side="left")
        self.var_mapa = tk.StringVar(value="O mapa usa o tamanho e as posições da montagem.")
        tk.Label(mapa, textvariable=self.var_mapa, bg=cores.fundo, fg=cores.texto2,
                 font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=380).grid(row=4, column=0, sticky="ew", pady=(5, 0))
        tk.Label(mapa, text="Amarelo: atenção, confira antes de montar.\n"
                 "Vermelho na lista: pendente, fica fora da montagem.\n"
                 "Miniaturas são apenas para conferência na tela.",
                 bg=cores.fundo, fg=cores.texto2, font=("Segoe UI", 8),
                 justify="left", anchor="w", wraplength=380).grid(
                     row=5, column=0, sticky="ew", pady=(5, 0))

    def _montar_resumo(self):
        caixa = tk.Frame(self, bg=cores.cartao,
                         highlightbackground=cores.borda, highlightthickness=1)
        caixa.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 0))
        self.var_passadas_docan = tk.StringVar(value=tempo_impressao.OPCOES_PASSADAS[0])
        if self.nome_maquina == tempo_impressao.MAQUINA_DOCAN:
            linha_tempo = tk.Frame(caixa, bg=cores.cartao)
            linha_tempo.pack(fill="x", padx=12, pady=4)
            tk.Label(linha_tempo, text="Estimativa — passadas:",
                     bg=cores.cartao, fg=cores.texto2).pack(side="left")
            self.escolha_passadas_docan = ttk.Combobox(
                linha_tempo, textvariable=self.var_passadas_docan,
                values=tempo_impressao.OPCOES_PASSADAS, state="readonly", width=16)
            self.escolha_passadas_docan.pack(side="left", padx=6)
            self.escolha_passadas_docan.bind(
                "<<ComboboxSelected>>", lambda _e: self._configuracao_mudou())
            tk.Label(linha_tempo, text="Planejamento; configure o modo no RIP.",
                     bg=cores.cartao, fg=cores.texto2).pack(side="left")
        self.var_resumo = tk.StringVar(value="Lendo a pasta...")
        self.var_margem = tk.StringVar(value="")
        self.var_recusadas = tk.StringVar(value="")
        for variavel, cor, fonte in (
                (self.var_resumo, cores.texto, ("Segoe UI", 10, "bold")),
                (self.var_margem, cores.texto2, ("Segoe UI", 9)),
                (self.var_recusadas, cores.alerta, ("Segoe UI", 9))):
            tk.Label(caixa, textvariable=variavel, font=fonte, bg=cores.cartao, fg=cor,
                     anchor="w", justify="left", wraplength=1380).pack(
                         fill="x", padx=12, pady=4)

    def _montar_rodape(self):
        linha = tk.Frame(self, bg=cores.fundo)
        linha.grid(row=4, column=0, sticky="ew", padx=16, pady=(10, 14))
        self.btn_atualizar = tk.Button(linha, text="↻ Recalcular seleção",
                                      relief="flat", cursor="hand2", bg=cores.cartao,
                                      fg=cores.texto, command=self.calcular)
        self.btn_atualizar.pack(side="left")
        self.btn_converter = tk.Button(linha, text="Converter EPS/PSD selecionados",
                                       relief="flat", cursor="hand2",
                                       bg=cores.cartao, fg=cores.acento,
                                       command=self._converter)
        self.btn_montar = tk.Button(linha, text="▶ Montar e salvar o PDF",
                                   relief="flat", cursor="hand2",
                                   bg=cores.acento, fg=cores.sobre_acento,
                                   font=("Segoe UI", 10, "bold"), padx=14, pady=6,
                                   command=self._montar_agora)
        self.btn_montar.pack(side="right")
        self.btn_abrir_pdf = tk.Button(linha, text="Abrir PDFs gerados",
                                      relief="flat", cursor="hand2",
                                      bg=cores.cartao, fg=cores.acento,
                                      command=self._abrir_pdf)

    def _sincronizar_arquivos(self):
        antigos = set(self._arquivos)
        arquivos = {}
        if self.pasta.is_dir():
            for arquivo in sorted(self.pasta.iterdir()):
                if (arquivo.is_file() and not arquivo.name.startswith("~")
                        and arquivo.suffix.lower() in montagem.EXTENSOES_DE_ARTE
                        and not montagem.e_folha_montada(arquivo)):
                    arquivos[arquivo.name] = arquivo
        self._arquivos = arquivos
        self._selecionados.intersection_update(arquivos)
        self._selecionados.update(set(arquivos) - antigos)
        for linha in self.tabela.get_children():
            self.tabela.delete(linha)
        self._linhas.clear()
        self._nomes_por_linha.clear()
        self._fotos.clear()
        for nome, arquivo in arquivos.items():
            linha = self.tabela.insert("", "end", text=nome, values=(
                "☑" if nome in self._selecionados else "�?", "—", "—", "—", "Lendo dados..."))
            self._linhas[nome] = linha
            self._nomes_por_linha[linha] = nome

    def _configuracao(self):
        return tuple(sorted(self._selecionados)), _folga_m_do_texto(self.var_folga.get())

    def _largura_m(self):
        try:
            largura = float(self.var_largura.get().strip().replace(",", ".")) / 100
        except (TypeError, ValueError) as erro:
            raise ValueError("Informe a largura máxima em centímetros.") from erro
        return montagem.largura_util(self.nome_maquina, largura_m=largura)

    def _configuracao_mudou(self):
        if self._fechando:
            return
        self._suja = True
        self.btn_montar.configure(state="disabled")
        if not self._ocupada:
            self.var_margem.set("Seleção ou espaçamento mudou. Recalcule antes de montar.")

    def _marcar_todos(self):
        if self._ocupada:
            return
        self._selecionados = set(self._arquivos)
        self._atualizar_marcas()
        self._configuracao_mudou()

    def _limpar_selecao(self):
        if self._ocupada:
            return
        self._selecionados.clear()
        self._atualizar_marcas()
        self._configuracao_mudou()

    def _salvar_folga(self):
        if self._ocupada or self._fechando:
            return
        try:
            folga = _folga_m_do_texto(self.var_folga.get())
            largura = self._largura_m()
            config = carregar_config()
            preferencia = config.setdefault("montagem", {}).setdefault(self.nome_maquina, {})
            preferencia["folga_m"] = folga
            preferencia["largura_m"] = largura
            salvar_config(config)
        except (OSError, ValueError, TypeError, AttributeError) as erro:
            self.var_margem.set(f"Não consegui salvar o espaçamento: {erro}")
            return
        self.var_margem.set(f"Espaçamento de {folga * 100:g} cm e largura de {largura * 100:g} cm "
                           f"salvos para {self.nome_maquina}. "
                           + ("Recalcule a seleção antes de montar." if self._suja else ""))

    def _atualizar_marcas(self):
        for nome, linha in self._linhas.items():
            self.tabela.set(linha, "marcar", "☑" if nome in self._selecionados else "�?")

    def _alternar_arquivo(self, nome):
        if self._ocupada or nome not in self._arquivos:
            return
        if nome in self._selecionados:
            self._selecionados.remove(nome)
        else:
            self._selecionados.add(nome)
        self._atualizar_marcas()
        self._configuracao_mudou()

    def _clicar_arquivo(self, evento):
        linha = self.tabela.identify_row(evento.y)
        coluna = self.tabela.identify_column(evento.x)
        if linha and coluna in ("#0", "#1"):
            self._alternar_arquivo(self._nomes_por_linha.get(linha))
            self.tabela.selection_set(linha)
            return "break"
        return None

    def _espaco_arquivo(self, _evento):
        linhas = self.tabela.selection()
        if linhas:
            self._alternar_arquivo(self._nomes_por_linha.get(linhas[0]))
        return "break"

    def calcular(self):
        if self._ocupada or self._fechando:
            return
        try:
            self._sincronizar_arquivos()
            configuracao = self._configuracao()
            largura = self._largura_m()
        except (OSError, ValueError) as erro:
            self.var_resumo.set("Não consegui calcular a seleção")
            self.var_margem.set(str(erro))
            self.btn_montar.configure(state="disabled")
            self._suja = True
            return
        self._ocupada = True
        self._geracao += 1
        geracao = self._geracao
        self.btn_montar.configure(state="disabled")
        self.btn_atualizar.configure(state="disabled")
        self.btn_converter.configure(state="disabled")
        self.var_resumo.set("Calculando as artes selecionadas...")
        nomes, folga = configuracao
        variavel_passadas = getattr(self, "var_passadas_docan", None)
        self._trabalho.submit(self._calcular_no_worker, geracao, configuracao,
                              list(nomes), folga, tempo_impressao.passadas_da_escolha(
                                  variavel_passadas.get()) if variavel_passadas else None,
                              largura)

    def _calcular_no_worker(self, geracao, configuracao, nomes, folga, passadas=None,
                            largura=None):
        try:
            argumentos = dict(arquivos=nomes, folga_m=folga,
                              passadas_docan=passadas, largura_m=largura)
            try:
                previa = montagem.prever_pasta(
                    self.pasta, self.nome_maquina, **argumentos)
            except TypeError as erro:
                # Mantém a tela testável com motores/adaptadores antigos que
                # ainda não conhecem a largura configurável. O motor atual
                # sempre segue pelo caminho acima.
                if "largura_m" not in str(erro):
                    raise
                argumentos.pop("largura_m")
                previa = montagem.prever_pasta(
                    self.pasta, self.nome_maquina, **argumentos)
            erro = None
        except Exception as exc:
            previa, erro = None, f"{type(exc).__name__}: {exc}"
        self._fila.put(("calculo", geracao, previa, erro, configuracao))

    def _consumir(self):
        if self._fechando:
            return
        try:
            for _ in range(40):
                dados = self._fila.get_nowait()
                if dados[0] == "miniatura":
                    self._receber_miniatura(*dados[1:])
                elif dados[1] == self._geracao:
                    if dados[0] == "calculo":
                        self._mostrar(dados[2], dados[3], dados[4])
                    elif dados[0] == "montagem":
                        self._montou(dados[2], dados[3])
                    elif dados[0] == "conversao":
                        self._converteu(dados[2], dados[3], dados[4])
        except queue.Empty:
            pass
        self._solicitar_previas_visiveis()
        self._job_fila = self.after(_CONSUMIR_MS, self._consumir)

    def _mostrar(self, previa, erro, configuracao):
        self._ocupada = False
        self.btn_atualizar.configure(state="normal")
        self.btn_converter.configure(state="normal")
        if erro is not None:
            self._previa = None
            self.var_resumo.set("Não consegui calcular a seleção")
            self.var_margem.set(erro)
            self.var_recusadas.set("")
            self.btn_montar.configure(state="disabled")
            self._suja = True
            return
        self._previa = previa
        self._config_calculada = configuracao
        try:
            self._suja = self._configuracao() != configuracao
            largura_calculada = previa.get("largura_m", self._largura_m())
            self._suja |= abs(self._largura_m() - largura_calculada) > 1e-9
            variavel_passadas = getattr(self, "var_passadas_docan", None)
            if variavel_passadas is not None:
                self._suja |= previa.get("passadas_docan") != tempo_impressao.passadas_da_escolha(
                    variavel_passadas.get())
        except ValueError:
            self._suja = True
        self._itens = _itens_por_arquivo(previa)
        recusadas = {}
        for recusada in previa.get("recusadas", []):
            recusadas.setdefault(recusada["arquivo"], []).append(recusada["motivo"])
        pendentes_adobe = set(previa.get("a_converter", []))
        for nome, linha in self._linhas.items():
            itens = self._itens.get(nome, [])
            avisos = _avisos_dos_itens(itens)
            avisos.extend(r for r in recusadas.get(nome, []) if r not in avisos)
            if nome in pendentes_adobe:
                avisos.append("Converter no Illustrator/Photoshop antes da conferência")
            if nome not in self._selecionados:
                resumo, pede, sai = "Não marcado", "—", "—"
                avisos = ["Fica para outro lote"]
            elif itens:
                paginas = {i.get("pagina", 0) for i in itens}
                quantidade = max(i.get("quantidade", 1) for i in itens)
                resumo = f"{len(paginas)} pág · {quantidade} un"
                medidas_nome = {tuple(i["nome_m"]) for i in itens}
                medidas_saida = {tuple(i["medida_m"]) for i in itens}
                pede = (_medida_em_palavras(next(iter(medidas_nome)))
                        if len(medidas_nome) == 1 else "Várias medidas")
                sai = (_medida_em_palavras(next(iter(medidas_saida)), 3)
                       if len(medidas_saida) == 1 else "Várias medidas")
                if len(paginas) > 1:
                    avisos.append("Miniatura da primeira página; confira as demais no arquivo")
            else:
                resumo, pede, sai = "Pendente", "—", "—"
            tag = ("aviso",) if nome in recusadas else (("atencao",) if avisos and itens else ())
            self.tabela.item(linha, tags=tag)
            self.tabela.set(linha, "quantidade", resumo)
            self.tabela.set(linha, "pede", pede)
            self.tabela.set(linha, "sai", sai)
            self.tabela.set(linha, "defeitos", " · ".join(avisos) or "Conferência sem alertas")
        if pendentes_adobe:
            self.btn_converter.pack(side="left", padx=(8, 0))
        else:
            self.btn_converter.pack_forget()
        folhas = previa.get("folhas", [])
        total_pecas = sum(f["pecas"] for f in folhas)
        cliente = previa.get("cliente") or "cliente não reconhecido no nome"
        metragem = previa.get("metragem_rolo", sum(f.get("folha_m", 0) for f in folhas))
        aproveitamento = previa.get("aproveitamento_rolo")
        extra = (f" · {metragem:.2f} m de comprimento estimado" if metragem else "")
        if aproveitamento is not None:
            extra += f" · {aproveitamento * 100:.0f}% de uso da largura escolhida (estimativa)"
        self.var_resumo.set(
            f"{len(self._selecionados)} arquivo(s) marcado(s) · {total_pecas} peça(s) "
            f"· {len(folhas)} folha(s) · {cliente}{extra}")
        pior = previa.get("pior_diferenca_mm", 0)
        self.var_margem.set(
            f"O maior lado segue o nome; diferença no outro lado até {pior:.0f} mm. "
            f"Espaçamento: {previa.get('folga_m', configuracao[1]) * 100:g} cm · "
            f"largura máxima: {previa.get('largura_m', 0) * 100:g} cm."
            if folhas else "Nada pronto para montar na seleção. Confira os arquivos e avisos.")
        recados = []
        if recusadas:
            recados.append("Pendente: " + " · ".join(
                f"{nome}: {'; '.join(motivos)}" for nome, motivos in recusadas.items()))
        if pendentes_adobe:
            recados.append(f"{len(pendentes_adobe)} arquivo(s) ainda precisam de conversão. "
                           "Converta e recalcule, ou desmarque esses arquivos.")
        avisos_gerais = previa.get("avisos", [])
        recados.extend(f["categoria"] + " · " + tempo_impressao.texto(f["estimativa_impressao"])
                       for f in folhas if f.get("estimativa_impressao"))
        recados.extend(str(a) for a in avisos_gerais)
        self.var_recusadas.set("\n".join(recados))
        opcoes = [f"{n} · {f['categoria']} · {f['tamanho']}"
                  for n, f in enumerate(folhas, 1)]
        self.escolha_folha.configure(values=opcoes)
        if opcoes:
            self.escolha_folha.current(0)
        else:
            self.escolha_folha.set("")
        self._zoom = 1.0
        self._desenhar_mapa()
        self.btn_montar.configure(
            state="normal" if folhas and not self._suja and not pendentes_adobe else "disabled")
        if self._suja:
            self.var_margem.set("Seleção ou espaçamento mudou. Recalcule antes de montar.")

    def _detalhar_selecao(self, _evento=None):
        linhas = self.tabela.selection()
        if not linhas:
            return
        nome = self._nomes_por_linha.get(linhas[0])
        if nome is None:
            return
        itens = self._itens.get(nome, [])
        avisos = _avisos_dos_itens(itens)
        detalhe = f"{nome} · {len(itens)} peça(s)"
        if itens:
            primeiro = itens[0]
            detalhe += (f"\nNome: {_medida_em_palavras(primeiro['nome_m'])} · "
                        f"Saída: {_medida_em_palavras(primeiro['medida_m'], 3)} · "
                        + _resolucao_em_palavras(primeiro))
            if len({i.get("pagina", 0) for i in itens}) > 1:
                detalhe += "\nMiniatura da primeira página; confira as demais no arquivo."
        if avisos:
            detalhe += "\n" + " · ".join(avisos)
        else:
            motivos = [r["motivo"] for r in (self._previa or {}).get("recusadas", [])
                       if r["arquivo"] == nome]
            if motivos:
                detalhe += "\n" + " · ".join(motivos)
        self.var_arquivo.set(detalhe)

    def _desenhar_mapa(self):
        if self._fechando:
            return
        self.canvas.delete("all")
        folhas = (self._previa or {}).get("folhas", [])
        qual = self.escolha_folha.current()
        if qual < 0 or qual >= len(folhas):
            self.canvas.create_text(12, 20, anchor="nw", text="Recalcule para ver o encaixe.",
                                    fill=cores.texto2)
            return
        folha = folhas[qual]
        largura = folha.get("largura_m")
        if largura is None:
            tamanho = folha.get("tamanho", "").split(" x ")
            try:
                largura = float(tamanho[0])
            except (ValueError, IndexError):
                largura = montagem.largura_util(self.nome_maquina)
        altura = folha.get("folha_m", 0)
        if not largura or not altura:
            return
        disponivel_l = max(220, self.canvas.winfo_width()) - 40
        disponivel_a = max(250, self.canvas.winfo_height()) - 60
        escala = min(disponivel_l / largura, disponivel_a / altura) * self._zoom
        margem_x, margem_y = 20, 36
        self._escala_mapa = escala
        self.canvas.create_text(20, 8, anchor="nw",
                                text=f"{largura:.2f} × {altura:.2f} m · proporção real",
                                fill=cores.texto2, font=("Segoe UI", 8))
        self.canvas.create_rectangle(margem_x, margem_y, margem_x + largura * escala,
                                     margem_y + altura * escala, fill="white",
                                     outline=cores.borda, width=1)
        for indice, item in enumerate(folha.get("itens", [])):
            posicao = item.get("posicao_m")
            if not posicao or len(posicao) != 4:
                continue
            x, y, w, h = posicao
            rect = (margem_x + x * escala, margem_y + y * escala,
                    margem_x + (x + w) * escala, margem_y + (y + h) * escala)
            tag = f"peca_{indice}"
            self.canvas.create_rectangle(*rect, fill=cores.cartao,
                                         outline=_cor_do_item(item), width=2, tags=(tag,))
            if rect[2] - rect[0] >= 18 and rect[3] - rect[1] >= 16:
                self.canvas.create_text((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2,
                                        text=f"{item.get('numero', indice + 1):02d}",
                                        fill=_cor_do_item(item), tags=(tag,))
            self.canvas.tag_bind(tag, "<Enter>", lambda _, i=item: self._detalhar_peca(i))
            self.canvas.tag_bind(tag, "<Button-1>", lambda _, i=item: self._destacar_arquivo(i))
        self.canvas.configure(scrollregion=(0, 0, max(disponivel_l + 40,
                              margem_x * 2 + largura * escala),
                              max(disponivel_a + 60, margem_y + altura * escala + 20)))

    def _detalhar_peca(self, item):
        self.var_mapa.set(
            f"{item.get('numero', 0):02d} · {item['arquivo']}\n"
            f"Página {item.get('pagina', 0) + 1} · cópia {item.get('copia', 1)}"
            f"/{item.get('quantidade', 1)}"
            + ("\n" + " · ".join(_avisos_dos_itens([item]))
               if _avisos_dos_itens([item]) else ""))

    def _destacar_arquivo(self, item):
        self._detalhar_peca(item)
        linha = self._linhas.get(item["arquivo"])
        if linha:
            self.tabela.selection_set(linha)
            self.tabela.see(linha)
            self._detalhar_selecao()

    def _alterar_zoom(self, fator):
        self._zoom = max(0.5, min(16, self._zoom * fator))
        self._desenhar_mapa()

    def _ajustar_mapa(self):
        self._zoom = 1
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._desenhar_mapa()

    def _solicitar_previas_visiveis(self):
        if self._fechando:
            return
        solicitadas = 0
        for nome, linha in self._linhas.items():
            if not self.tabela.bbox(linha):
                continue
            caminho = self._arquivos[nome]
            chave = previas_impressao.chave_do_arquivo(caminho)
            if self._fotos.get(nome, (None,))[0] == chave:
                continue
            if chave in self._cache_previas:
                dados, recado = self._cache_previas[chave]
                self._cache_previas.move_to_end(chave)
                self._aplicar_miniatura(nome, chave, dados, recado)
            elif chave not in self._previas_pendentes:
                self._previas_pendentes.add(chave)
                self._trabalho_previas.submit(self._carregar_miniatura, caminho, chave)
                solicitadas += 1
                if solicitadas >= 6:
                    break

    def _carregar_miniatura(self, caminho, chave):
        dados, recado = previas_impressao.carregar(caminho, chave)
        self._fila.put(("miniatura", pathlib.Path(caminho).name, chave, dados, recado))

    def _receber_miniatura(self, nome, chave, dados, recado):
        self._previas_pendentes.discard(chave)
        self._cache_previas[chave] = dados, recado
        self._cache_previas.move_to_end(chave)
        while len(self._cache_previas) > _LIMITE_CACHE:
            self._cache_previas.popitem(last=False)
        self._aplicar_miniatura(nome, chave, dados, recado)

    def _aplicar_miniatura(self, nome, chave, dados, recado):
        caminho = self._arquivos.get(nome)
        if caminho is None or previas_impressao.chave_do_arquivo(caminho) != chave:
            return
        foto = None
        if dados:
            try:
                from PIL import Image, ImageTk
                with Image.open(io.BytesIO(dados)) as origem:
                    imagem = origem.convert("RGB")
                imagem.thumbnail((112, 80))
                foto = ImageTk.PhotoImage(imagem, master=self)
            except Exception:
                recado = "Prévia indisponível"
        self._fotos[nome] = chave, foto, recado
        linha = self._linhas.get(nome)
        if linha:
            self.tabela.item(linha, image=foto or "")
            if recado and not dados:
                atual = self.tabela.set(linha, "defeitos")
                if recado not in atual:
                    self.tabela.set(linha, "defeitos", (atual + " · " + recado).strip(" ·"))

    def _montar_agora(self):
        if self._ocupada or self._fechando or self._suja or not self._previa:
            return
        try:
            configuracao = self._configuracao()
            largura = self._largura_m()
        except ValueError as erro:
            self.var_margem.set(str(erro))
            return
        if configuracao != self._config_calculada:
            self._configuracao_mudou()
            return
        if abs(largura - self._previa.get("largura_m", largura)) > 1e-9:
            self._configuracao_mudou()
            return
        if not self._previa.get("folhas") or self._previa.get("a_converter"):
            return
        nomes, folga = configuracao
        self._ocupada = True
        self.btn_montar.configure(state="disabled", text="Montando...")
        self.btn_atualizar.configure(state="disabled")
        self.btn_converter.configure(state="disabled")
        self.entrada_folga.configure(state="disabled")
        self.entrada_largura.configure(state="disabled")
        escolha_passadas = getattr(self, "escolha_passadas_docan", None)
        if escolha_passadas is not None:
            escolha_passadas.configure(state="disabled")
        self._trabalho.submit(self._montar_no_worker, self._geracao, list(nomes), folga,
                              self._previa.get("versoes", {}), self._previa.get("passadas_docan"),
                              largura)

    def _montar_no_worker(self, geracao, nomes, folga, versoes, passadas=None, largura=None):
        try:
            argumentos = dict(arquivos=nomes, folga_m=folga,
                              versoes_esperadas=versoes, passadas_docan=passadas)
            # O valor padrão já é o limite cadastrado; deixar o argumento
            # ausente mantém compatibilidade com motores antigos. Só uma
            # largura escolhida pelo operador precisa ser explicitada.
            if largura is not None and abs(
                    largura - montagem.largura_util(self.nome_maquina)) > 1e-9:
                argumentos["largura_m"] = largura
            resultado = montagem.montar_pasta(
                self.pasta, self.nome_maquina, **argumentos)
            erro = None
        except Exception as exc:
            resultado, erro = None, f"{type(exc).__name__}: {exc}"
        self._fila.put(("montagem", geracao, resultado, erro))

    def _montou(self, resultado, erro):
        self._ocupada = False
        self.btn_montar.configure(text="▶ Montar e salvar o PDF")
        self.btn_atualizar.configure(state="normal")
        self.btn_converter.configure(state="normal")
        self.entrada_folga.configure(state="normal")
        self.entrada_largura.configure(state="normal")
        escolha_passadas = getattr(self, "escolha_passadas_docan", None)
        if escolha_passadas is not None:
            escolha_passadas.configure(state="readonly")
        self._suja = True
        if erro is not None:
            messagebox.showerror("A montagem parou", erro, parent=self)
            self.calcular()
            return
        self._feitas = [f["arquivo"] for f in resultado.get("folhas", [])]
        if self._feitas:
            self.btn_abrir_pdf.pack(side="right", padx=(0, 8))
            self.var_resumo.set("Pronto: " + ", ".join(p.name for p in self._feitas))
            self.var_margem.set("PDFs na pasta de saída, com a ficha de cada montagem ao lado.")
        else:
            self.var_resumo.set("Nenhum PDF foi gerado.")
        recusadas = resultado.get("recusadas", [])
        recados = (["Pendentes: " + " · ".join(
            f"{r['arquivo']}: {r['motivo']}" for r in recusadas)] if recusadas else [])
        recados.extend(resultado.get("avisos", []))
        self.var_recusadas.set("\n".join(recados))
        if self._job_resultado is not None:
            self.after_cancel(self._job_resultado)
        self._job_resultado = self.after(_MOSTRA_RESULTADO_MS, self.calcular)

    def _converter(self):
        if self._ocupada or self._fechando:
            return
        self._ocupada = True
        self.btn_converter.configure(state="disabled", text="Convertendo...")
        self.btn_montar.configure(state="disabled")
        self.btn_atualizar.configure(state="disabled")
        self._trabalho.submit(self._converter_no_worker, self._geracao,
                              list(sorted(self._selecionados)))

    def _converter_no_worker(self, geracao, nomes):
        recados = []
        try:
            gerados = montagem.converter_o_que_precisa(
                self.pasta, arquivos=nomes, logger=lambda nivel, msg: recados.append(msg))
            erro = None
        except Exception as exc:
            gerados, erro = [], f"{type(exc).__name__}: {exc}"
        self._fila.put(("conversao", geracao, gerados, erro, recados))

    def _converteu(self, gerados, erro, recados):
        self._ocupada = False
        self.btn_converter.configure(state="normal", text="Converter EPS/PSD selecionados")
        if erro is not None:
            messagebox.showerror("A conversão parou", erro, parent=self)
        elif not gerados:
            messagebox.showwarning("Nada foi convertido", "\n".join(recados) or
                                   "O Illustrator/Photoshop não respondeu. "
                                   "Abra o programa e tente novamente.", parent=self)
        self.calcular()

    def _abrir_pasta(self):
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._abrir(self.pasta)

    def _abrir_saida(self):
        saida = montagem.pasta_de_saida(self.nome_maquina)
        saida.mkdir(parents=True, exist_ok=True)
        self._abrir(saida)

    def _abrir_pdf(self):
        for caminho in self._feitas:
            self._abrir(caminho)

    def _abrir(self, caminho):
        try:
            os.startfile(str(pathlib.Path(caminho)))
        except OSError as erro:
            messagebox.showerror("Erro", f"Não consegui abrir {caminho}: {erro}", parent=self)

    def _destruida(self, evento):
        if evento.widget is self:
            self.fechar()

    def fechar(self):
        if self._fechando:
            return
        self._fechando = True
        for job in (self._job_fila, self._job_resultado):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self._trabalho.shutdown(wait=False, cancel_futures=True)
        self._trabalho_previas.shutdown(wait=False, cancel_futures=True)

