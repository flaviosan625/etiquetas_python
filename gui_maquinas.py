"""
Interface gráfica para configuração visual de máquinas e softwares RIP.

Substitui a necessidade de editar rasterlink_hotfolder.py manualmente,
permitindo cadastrar, editar e remover impressoras, definir larguras
úteis (rolo ou mesa plana), configurar hot folders e selecionar o software RIP
(Mimaki RasterLink, SAi Production Manager, BYHX Printer Manager ou Hot Folder Genérico).

As alterações são salvas no config.json e propagadas imediatamente em memória
para rasterlink_hotfolder.MAQUINAS.
"""
import copy
import os
import pathlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import branding
from hardware import MaquinaInfo, obter_gerenciador_hardware
from rasterlink_hotfolder import (
    MAQUINAS,
    MAQUINAS_PADRAO,
    POSTO_RIP,
    POSTO_SAI,
    salvar_maquinas_config,
    atualizar_maquinas_em_memoria,
    carregar_maquinas_config,
)
from tema import cores

OPCOES_RIP = [
    ("Mimaki RasterLink", "rasterlink", POSTO_RIP),
    ("SAi Production Manager / Flexi", "sai", POSTO_SAI),
    ("BYHX Printer Manager (Docan/Chinesas)", "byhx", POSTO_SAI),
    ("Hot Folder Genérico (Caldera/Onyx/PrintFactory)", "generico", "local"),
]

MAPA_RIP_EXIBICAO = {cod: rotulo for rotulo, cod, _ in OPCOES_RIP}
MAPA_EXIBICAO_RIP = {rotulo: (cod, posto) for rotulo, cod, posto in OPCOES_RIP}


class JanelaConfigurarMaquinas(tk.Toplevel):
    """
    Janela modal para gerenciamento e configuração de máquinas/impressoras e RIPs.
    """

    def __init__(self, mestre, config_dados=None, ao_salvar=None):
        super().__init__(mestre)
        self.title(branding.titulo_janela("Configurar Máquinas / RIPs"))
        self.geometry("980x660")
        self.minsize(860, 520)
        self.configure(bg=cores.fundo)
        self.transient(mestre)

        self.config_dados = config_dados
        self.ao_salvar = ao_salvar

        # Gerenciador de hardware gráfico e catálogo de drivers
        self.gerenciador = obter_gerenciador_hardware()
        maqs_gerenciadas = {m.nome: m.to_dict() for m in self.gerenciador.listar_maquinas()}
        self.maquinas = maqs_gerenciadas if maqs_gerenciadas else copy.deepcopy(MAQUINAS)
        self.nome_em_edicao = None

        self._montar_layout()
        self._recarregar_lista()

        # Seleciona a primeira máquina se houver
        if self.maquinas:
            primeira = list(self.maquinas.keys())[0]
            self._selecionar_maquina_por_nome(primeira)
        else:
            self._nova_maquina()

        self.grab_set()

    def _montar_layout(self):
        # Cabeçalho
        topo = tk.Frame(self, bg=cores.fundo)
        topo.pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(
            topo, text="🖨️ Cadastro e Configuração de Máquinas & RIPs",
            font=("Segoe UI", 13, "bold"), bg=cores.fundo, fg=cores.texto,
        ).pack(anchor="w")

        tk.Label(
            topo,
            text="Configure as impressoras da gráfica, larguras úteis (bobina ou mesa), pastas de hot folder e o "
                 "software RIP de destino.\nAs alterações passam a valer imediatamente para o envio de artes e montagem.",
            font=("Segoe UI", 9), bg=cores.fundo, fg=cores.texto2, justify="left",
        ).pack(anchor="w", pady=(2, 0))

        # Painel Central Dividido (Esquerda: Lista / Direita: Formulário)
        painel = tk.Frame(self, bg=cores.fundo)
        painel.pack(fill="both", expand=True, padx=16, pady=4)
        painel.columnconfigure(0, weight=4)
        painel.columnconfigure(1, weight=6)
        painel.rowconfigure(0, weight=1)

        # === COLUNA ESQUERDA: LISTA DE MÁQUINAS ===
        col_esq = tk.Frame(painel, bg=cores.cartao, highlightbackground=cores.borda, highlightthickness=1)
        col_esq.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        col_esq.columnconfigure(0, weight=1)
        col_esq.rowconfigure(1, weight=1)

        cab_esq = tk.Frame(col_esq, bg=cores.cartao)
        cab_esq.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        tk.Label(
            cab_esq, text="Impressoras Cadastradas", font=("Segoe UI", 10, "bold"),
            bg=cores.cartao, fg=cores.texto,
        ).pack(side="left")

        # Treeview
        frame_tree = tk.Frame(col_esq, bg=cores.cartao)
        frame_tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=2)
        frame_tree.columnconfigure(0, weight=1)
        frame_tree.rowconfigure(0, weight=1)

        colunas = ("formato", "rip")
        self.tree = ttk.Treeview(
            frame_tree, columns=colunas, show="tree headings", selectmode="browse"
        )
        self.tree.heading("#0", text="Nome")
        self.tree.heading("formato", text="Mídia / Formato")
        self.tree.heading("rip", text="RIP")

        self.tree.column("#0", width=140, minwidth=100)
        self.tree.column("formato", width=110, minwidth=80)
        self.tree.column("rip", width=110, minwidth=80)

        scroll_tree = ttk.Scrollbar(frame_tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_tree.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_tree.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._ao_selecionar_item)

        # Botões de Ação na Lista
        botoes_esq = tk.Frame(col_esq, bg=cores.cartao)
        botoes_esq.grid(row=2, column=0, sticky="ew", padx=10, pady=10)

        self.btn_novo = tk.Button(
            botoes_esq, text="➕ Nova Máquina", bg=cores.acento, fg=cores.sobre_acento,
            relief="flat", cursor="hand2", font=("Segoe UI", 9, "bold"),
            command=self._nova_maquina,
        )
        self.btn_novo.pack(side="left", padx=(0, 4))

        self.btn_excluir = tk.Button(
            botoes_esq, text="🗑️ Excluir", relief="flat", fg=cores.erro if hasattr(cores, "erro") else "#d32f2f",
            cursor="hand2", command=self._excluir_maquina,
        )
        self.btn_excluir.pack(side="left", padx=4)

        self.btn_restaurar = tk.Button(
            botoes_esq, text="🔄 Padrões", relief="flat", fg=cores.texto2,
            cursor="hand2", command=self._restaurar_padrao,
        )
        self.btn_restaurar.pack(side="right")

        # === COLUNA DIREITA: FORMULÁRIO DE EDIÇÃO ===
        col_dir = tk.Frame(painel, bg=cores.cartao, highlightbackground=cores.borda, highlightthickness=1)
        col_dir.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=4)
        col_dir.columnconfigure(0, weight=1)
        col_dir.rowconfigure(1, weight=1)

        # Cabeçalho do formulário
        cab_dir = tk.Frame(col_dir, bg=cores.cartao)
        cab_dir.pack(fill="x", padx=14, pady=(10, 6))
        self.lbl_form_titulo = tk.Label(
            cab_dir, text="Detalhes da Máquina", font=("Segoe UI", 10, "bold"),
            bg=cores.cartao, fg=cores.texto,
        )
        self.lbl_form_titulo.pack(side="left")

        # Área rolável do formulário
        canvas_form = tk.Canvas(col_dir, bg=cores.cartao, highlightthickness=0)
        scroll_form = ttk.Scrollbar(col_dir, orient="vertical", command=canvas_form.yview)
        self.form_conteudo = tk.Frame(canvas_form, bg=cores.cartao)

        self.form_conteudo.bind(
            "<Configure>",
            lambda e: canvas_form.configure(scrollregion=canvas_form.bbox("all")),
        )
        canvas_form.create_window((0, 0), window=self.form_conteudo, anchor="nw")
        canvas_form.configure(yscrollcommand=scroll_form.set)

        canvas_form.pack(side="left", fill="both", expand=True, padx=(14, 0))
        scroll_form.pack(side="right", fill="y")

        self._montar_campos_formulario()

        # Rodapé da janela
        rodape = tk.Frame(self, bg=cores.fundo)
        rodape.pack(fill="x", padx=16, pady=(8, 12))

        self.lbl_status = tk.Label(
            rodape, text="", font=("Segoe UI", 9), bg=cores.fundo, fg=cores.positivo,
        )
        self.lbl_status.pack(side="left")

        tk.Button(
            rodape, text="Fechar", relief="flat", cursor="hand2", padx=14,
            command=self.destroy,
        ).pack(side="right")

    def _montar_campos_formulario(self):
        f = self.form_conteudo

        # Variáveis do formulário
        self.var_nome = tk.StringVar()
        self.var_tipo = tk.StringVar(value="rolo")  # "rolo" ou "mesa"
        self.var_largura_util = tk.StringVar(value="1.50")
        self.var_mesa_x = tk.StringVar(value="2.50")
        self.var_mesa_y = tk.StringVar(value="2.50")
        self.var_rip_opcao = tk.StringVar(value=OPCOES_RIP[0][0])
        self.var_pasta_entrada = tk.StringVar()
        self.var_hot_folder = tk.StringVar()
        self.var_posto = tk.StringVar(value=POSTO_RIP)
        self.var_setup_sai = tk.StringVar()
        self.var_montagem = tk.BooleanVar(value=True)
        self.var_largura_montagem = tk.StringVar(value="1.50")
        self.var_margem_montagem = tk.StringVar(value="0.0")
        self.var_girar = tk.BooleanVar(value=True)
        self.var_entrega_byhx = tk.BooleanVar(value=False)

        # 1. Nome da Máquina
        grp1 = tk.LabelFrame(f, text="Identificação", bg=cores.cartao, fg=cores.acento, font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        grp1.pack(fill="x", pady=4)

        tk.Label(grp1, text="Nome da Máquina / Fila:", bg=cores.cartao, fg=cores.texto).grid(row=0, column=0, sticky="w", pady=2)
        self.entry_nome = tk.Entry(grp1, textvariable=self.var_nome, width=32, font=("Segoe UI", 9))
        self.entry_nome.grid(row=0, column=1, sticky="w", padx=6, pady=2)
        tk.Label(grp1, text="(Identificador único, ex: 'SWJ320A', 'UJV 100', 'DOCAN R5200')", bg=cores.cartao, fg=cores.texto2, font=("Segoe UI", 8)).grid(row=1, column=1, sticky="w", padx=6)

        # 2. Formato e Dimensões
        grp2 = tk.LabelFrame(f, text="Mídia e Dimensões Físicas", bg=cores.cartao, fg=cores.acento, font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        grp2.pack(fill="x", pady=6)

        tk.Label(grp2, text="Tipo de Mídia:", bg=cores.cartao, fg=cores.texto).grid(row=0, column=0, sticky="w", pady=2)
        frame_tipo = tk.Frame(grp2, bg=cores.cartao)
        frame_tipo.grid(row=0, column=1, sticky="w", padx=6, pady=2)
        tk.Radiobutton(
            frame_tipo, text="Rolo / Bobina", variable=self.var_tipo, value="rolo",
            bg=cores.cartao, fg=cores.texto, selectcolor=cores.cartao,
            command=self._ao_alternar_tipo_midia,
        ).pack(side="left")
        tk.Radiobutton(
            frame_tipo, text="Mesa Plana (Chapa Rígida)", variable=self.var_tipo, value="mesa",
            bg=cores.cartao, fg=cores.texto, selectcolor=cores.cartao,
            command=self._ao_alternar_tipo_midia,
        ).pack(side="left", padx=10)

        # Painel Rolo
        self.frame_dim_rolo = tk.Frame(grp2, bg=cores.cartao)
        self.frame_dim_rolo.grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        tk.Label(self.frame_dim_rolo, text="Largura Útil de Impressão (m):", bg=cores.cartao, fg=cores.texto).pack(side="left")
        tk.Entry(self.frame_dim_rolo, textvariable=self.var_largura_util, width=8, font=("Segoe UI", 9)).pack(side="left", padx=6)
        tk.Label(self.frame_dim_rolo, text="m  (ex: 1.27, 3.24, 5.04)", bg=cores.cartao, fg=cores.texto2, font=("Segoe UI", 8)).pack(side="left")

        # Painel Mesa
        self.frame_dim_mesa = tk.Frame(grp2, bg=cores.cartao)
        self.frame_dim_mesa.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        tk.Label(self.frame_dim_mesa, text="Área Útil da Mesa (Largura X × Altura Y):", bg=cores.cartao, fg=cores.texto).pack(side="left")
        tk.Entry(self.frame_dim_mesa, textvariable=self.var_mesa_x, width=7, font=("Segoe UI", 9)).pack(side="left", padx=(6, 2))
        tk.Label(self.frame_dim_mesa, text="×", bg=cores.cartao, fg=cores.texto).pack(side="left", padx=2)
        tk.Entry(self.frame_dim_mesa, textvariable=self.var_mesa_y, width=7, font=("Segoe UI", 9)).pack(side="left", padx=(2, 6))
        tk.Label(self.frame_dim_mesa, text="m  (ex: 2.50 × 2.50)", bg=cores.cartao, fg=cores.texto2, font=("Segoe UI", 8)).pack(side="left")

        # 3. RIP e Hot Folder
        grp3 = tk.LabelFrame(f, text="Software RIP & Integração de Fila", bg=cores.cartao, fg=cores.acento, font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        grp3.pack(fill="x", pady=6)

        tk.Label(grp3, text="Software RIP:", bg=cores.cartao, fg=cores.texto).grid(row=0, column=0, sticky="w", pady=2)
        nomes_rip = [r[0] for r in OPCOES_RIP]
        self.combo_rip = ttk.Combobox(
            grp3, textvariable=self.var_rip_opcao, values=nomes_rip, state="readonly", width=34,
        )
        self.combo_rip.grid(row=0, column=1, sticky="w", padx=6, pady=2)
        self.combo_rip.bind("<<ComboboxSelected>>", self._ao_mudar_rip)

        # Pasta de Entrada (Fila onde alimenta os arquivos para a máquina)
        tk.Label(grp3, text="Pasta de Entrada (Alimentação):", bg=cores.cartao, fg=cores.texto).grid(row=1, column=0, sticky="w", pady=2)
        frame_pe = tk.Frame(grp3, bg=cores.cartao)
        frame_pe.grid(row=1, column=1, sticky="ew", padx=6, pady=2)
        self.entry_pe = tk.Entry(frame_pe, textvariable=self.var_pasta_entrada, width=28, font=("Segoe UI", 9))
        self.entry_pe.pack(side="left", fill="x", expand=True)
        tk.Button(frame_pe, text="📁 Procurar...", relief="flat", cursor="hand2", command=self._procurar_pasta_entrada).pack(side="left", padx=(4, 2))
        tk.Button(frame_pe, text="📂 Abrir", relief="flat", cursor="hand2", command=self._abrir_pasta_entrada).pack(side="left", padx=2)

        # Pasta de Saída do RIP (Hot Folder monitorada pelo software RIP)
        tk.Label(grp3, text="Pasta de Saída do RIP (Hot Folder):", bg=cores.cartao, fg=cores.texto).grid(row=2, column=0, sticky="w", pady=2)
        frame_hf = tk.Frame(grp3, bg=cores.cartao)
        frame_hf.grid(row=2, column=1, sticky="ew", padx=6, pady=2)
        self.entry_hf = tk.Entry(frame_hf, textvariable=self.var_hot_folder, width=28, font=("Segoe UI", 9))
        self.entry_hf.pack(side="left", fill="x", expand=True)
        tk.Button(frame_hf, text="📁 Procurar...", relief="flat", cursor="hand2", command=self._procurar_hotfolder).pack(side="left", padx=(4, 2))
        tk.Button(frame_hf, text="📂 Abrir", relief="flat", cursor="hand2", command=self._abrir_hotfolder).pack(side="left", padx=2)
        tk.Button(frame_hf, text="🔍 Testar", relief="flat", cursor="hand2", command=self._testar_conexao_hotfolder).pack(side="left", padx=2)

        tk.Label(grp3, text="Posto do Vigia:", bg=cores.cartao, fg=cores.texto).grid(row=3, column=0, sticky="w", pady=2)
        frame_posto = tk.Frame(grp3, bg=cores.cartao)
        frame_posto.grid(row=3, column=1, sticky="w", padx=6, pady=2)
        ttk.Combobox(
            frame_posto, textvariable=self.var_posto, values=["rip", "sai", "local"],
            width=10,
        ).pack(side="left")
        tk.Label(frame_posto, text="(PC onde o vigia entrega o arquivo para a hot folder)", bg=cores.cartao, fg=cores.texto2, font=("Segoe UI", 8)).pack(side="left", padx=6)

        # Setup SAi (visível/ativo apenas para SAi)
        self.frame_sai = tk.Frame(grp3, bg=cores.cartao)
        self.frame_sai.grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
        tk.Label(self.frame_sai, text="Setup SAi (Nome do Dispositivo):", bg=cores.cartao, fg=cores.texto).pack(side="left")
        tk.Entry(self.frame_sai, textvariable=self.var_setup_sai, width=18, font=("Segoe UI", 9)).pack(side="left", padx=6)
        tk.Label(self.frame_sai, text="(ex: 'Docan', 'Docan_H2525')", bg=cores.cartao, fg=cores.texto2, font=("Segoe UI", 8)).pack(side="left")

        # 4. Montagem e Automações
        grp4 = tk.LabelFrame(f, text="Montagem Automática & Ajustes", bg=cores.cartao, fg=cores.acento, font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        grp4.pack(fill="x", pady=6)

        tk.Checkbutton(
            grp4, text="Criar pasta e habilitar Montagem Automática (Nesting / Imposição)",
            variable=self.var_montagem, bg=cores.cartao, fg=cores.texto,
            selectcolor=cores.cartao, command=self._ao_alternar_montagem,
        ).pack(anchor="w", pady=2)

        self.frame_det_montagem = tk.Frame(grp4, bg=cores.cartao)
        self.frame_det_montagem.pack(fill="x", padx=16, pady=2)
        tk.Label(self.frame_det_montagem, text="Largura de Fechamento (m):", bg=cores.cartao, fg=cores.texto).grid(row=0, column=0, sticky="w")
        tk.Entry(self.frame_det_montagem, textvariable=self.var_largura_montagem, width=7, font=("Segoe UI", 9)).grid(row=0, column=1, padx=4)
        tk.Label(self.frame_det_montagem, text="Margem Lateral (m):", bg=cores.cartao, fg=cores.texto).grid(row=0, column=2, padx=(10, 0), sticky="w")
        tk.Entry(self.frame_det_montagem, textvariable=self.var_margem_montagem, width=7, font=("Segoe UI", 9)).grid(row=0, column=3, padx=4)

        tk.Checkbutton(
            grp4, text="Giro automático de peças (girar para caber ou economizar mídia)",
            variable=self.var_girar, bg=cores.cartao, fg=cores.texto, selectcolor=cores.cartao,
        ).pack(anchor="w", pady=2)

        self.chk_byhx = tk.Checkbutton(
            grp4, text="Entregar ripado (.prt) diretamente ao BYHX Printer Manager",
            variable=self.var_entrega_byhx, bg=cores.cartao, fg=cores.texto, selectcolor=cores.cartao,
        )
        self.chk_byhx.pack(anchor="w", pady=2)

        # Botão Salvar Formulário
        botoes_form = tk.Frame(f, bg=cores.cartao)
        botoes_form.pack(fill="x", pady=(10, 14))

        self.btn_salvar_maquina = tk.Button(
            botoes_form, text="💾 Salvar Máquina", bg=cores.acento, fg=cores.sobre_acento,
            relief="flat", cursor="hand2", font=("Segoe UI", 9, "bold"), padx=16, pady=4,
            command=self._salvar_maquina,
        )
        self.btn_salvar_maquina.pack(side="left")

        # Atualiza visibilidade inicial
        self._ao_alternar_tipo_midia()
        self._ao_alternar_montagem()

    # ========================== LÓGICA DE INTERFACE ==========================

    def _ao_alternar_tipo_midia(self):
        tipo = self.var_tipo.get()
        if tipo == "mesa":
            self.frame_dim_rolo.grid_remove()
            self.frame_dim_mesa.grid()
        else:
            self.frame_dim_mesa.grid_remove()
            self.frame_dim_rolo.grid()

    def _ao_alternar_montagem(self):
        if self.var_montagem.get():
            self.frame_det_montagem.pack(fill="x", padx=16, pady=2)
        else:
            self.frame_det_montagem.pack_forget()

    def _ao_mudar_rip(self, _evento=None):
        rotulo = self.var_rip_opcao.get()
        if rotulo in MAPA_EXIBICAO_RIP:
            cod, posto_sugerido = MAPA_EXIBICAO_RIP[rotulo]
            # Se for máquina nova ou posto vazio, sugere o posto padrão
            if not self.var_posto.get():
                self.var_posto.set(posto_sugerido)
            if cod == "sai":
                self.frame_sai.grid()
                self.chk_byhx.pack(anchor="w", pady=2)
            else:
                if cod == "rasterlink":
                    self.var_girar.set(True)
                self.chk_byhx.pack_forget()
                self.frame_sai.grid_remove()

    def _procurar_pasta_entrada(self):
        caminho_inicial = self.var_pasta_entrada.get().strip()
        if not caminho_inicial or not os.path.exists(caminho_inicial):
            caminho_inicial = "C:\\"
        escolhida = filedialog.askdirectory(
            parent=self, title="Selecione a Pasta de Entrada (Fila/Alimentação)",
            initialdir=caminho_inicial,
        )
        if escolhida:
            self.var_pasta_entrada.set(os.path.normpath(escolhida))

    def _abrir_pasta_entrada(self):
        caminho = self.var_pasta_entrada.get().strip()
        if caminho and os.path.isdir(caminho):
            import subprocess
            subprocess.Popen(["explorer", os.path.normpath(caminho)])
        else:
            messagebox.showinfo("Pasta Inexistente", "A pasta de entrada informada não existe ou não foi configurada.", parent=self)

    def _procurar_hotfolder(self):
        caminho_inicial = self.var_hot_folder.get().strip()
        if not caminho_inicial or not os.path.exists(caminho_inicial):
            caminho_inicial = "C:\\"
        escolhida = filedialog.askdirectory(
            parent=self, title="Selecione a Pasta Hot Folder do RIP",
            initialdir=caminho_inicial,
        )
        if escolhida:
            self.var_hot_folder.set(os.path.normpath(escolhida))

    def _abrir_hotfolder(self):
        caminho = self.var_hot_folder.get().strip()
        if caminho and os.path.isdir(caminho):
            import subprocess
            subprocess.Popen(["explorer", os.path.normpath(caminho)])
        else:
            messagebox.showinfo("Pasta Inexistente", "A pasta de saída do RIP informada não existe ou não foi configurada.", parent=self)

    def _recarregar_lista(self):
        self.tree.delete(*self.tree.get_children())
        for nome, cfg in sorted(self.maquinas.items()):
            formato = self._descricao_formato(cfg)
            rip = self._descricao_rip(cfg)
            self.tree.insert("", "end", iid=nome, text=nome, values=(formato, rip))

    def _descricao_formato(self, cfg):
        if not isinstance(cfg, dict):
            return "—"
        if cfg.get("mesa_util_m"):
            x, y = cfg["mesa_util_m"]
            return f"Mesa {x:.2f} × {y:.2f} m".replace(".", ",")
        if cfg.get("largura_util_m"):
            return f"Rolo {cfg['largura_util_m']:.2f} m".replace(".", ",")
        return "Sem limite"

    def _descricao_rip(self, cfg):
        if not isinstance(cfg, dict):
            return "Genérico"
        cod = cfg.get("rip_tipo")
        if not cod:
            hf = cfg.get("hot_folder", "")
            if "SAi" in hf or cfg.get("setup_sai"):
                cod = "sai"
            elif "MijCtrl" in hf or "rasterlink" in hf.lower():
                cod = "rasterlink"
            else:
                cod = "generico"
        return MAPA_RIP_EXIBICAO.get(cod, cod.title())

    def _ao_selecionar_item(self, _evento=None):
        selecionados = self.tree.selection()
        if not selecionados:
            return
        nome = selecionados[0]
        self._carregar_maquina_no_form(nome)

    def _selecionar_maquina_por_nome(self, nome):
        if self.tree.exists(nome):
            self.tree.selection_set(nome)
            self.tree.focus(nome)
            self._carregar_maquina_no_form(nome)

    def _carregar_maquina_no_form(self, nome):
        self.nome_em_edicao = nome
        self.lbl_form_titulo.config(text=f"Editando Máquina: {nome}")
        cfg = self.maquinas.get(nome, {})
        if not isinstance(cfg, dict):
            cfg = {"hot_folder": str(cfg)}

        self.var_nome.set(nome)
        self.var_pasta_entrada.set(cfg.get("pasta_entrada", ""))
        self.var_hot_folder.set(cfg.get("hot_folder", ""))
        self.var_posto.set(cfg.get("posto", POSTO_RIP))
        self.var_setup_sai.set(cfg.get("setup_sai", ""))
        self.var_girar.set(cfg.get("girar", True))
        self.var_entrega_byhx.set(cfg.get("entrega_byhx", False))

        # Formato (Mesa vs Rolo)
        if cfg.get("mesa_util_m"):
            self.var_tipo.set("mesa")
            x, y = cfg["mesa_util_m"]
            self.var_mesa_x.set(str(x))
            self.var_mesa_y.set(str(y))
        else:
            self.var_tipo.set("rolo")
            self.var_largura_util.set(str(cfg.get("largura_util_m", "1.50")))

        # Montagem
        monta = bool(cfg.get("montagem", False))
        self.var_montagem.set(monta)
        self.var_largura_montagem.set(str(cfg.get("largura_montagem_m", cfg.get("largura_util_m", "1.50"))))
        self.var_margem_montagem.set(str(cfg.get("margem_montagem_m", "0.0")))

        # RIP
        rip_cod = cfg.get("rip_tipo")
        if not rip_cod:
            hf = cfg.get("hot_folder", "")
            if "SAi" in hf or cfg.get("setup_sai"):
                rip_cod = "sai"
            elif "MijCtrl" in hf:
                rip_cod = "rasterlink"
            else:
                rip_cod = "generico"
        rotulo_rip = MAPA_RIP_EXIBICAO.get(rip_cod, OPCOES_RIP[0][0])
        self.var_rip_opcao.set(rotulo_rip)

        self._ao_alternar_tipo_midia()
        self._ao_alternar_montagem()
        self._ao_mudar_rip()

    def _nova_maquina(self):
        self.nome_em_edicao = None
        self.lbl_form_titulo.config(text="Cadastrar Nova Máquina")
        self.tree.selection_remove(self.tree.selection())

        self.var_nome.set("Nova Impressora")
        self.var_tipo.set("rolo")
        self.var_largura_util.set("1.50")
        self.var_mesa_x.set("2.50")
        self.var_mesa_y.set("2.50")
        self.var_rip_opcao.set(OPCOES_RIP[0][0])
        self.var_pasta_entrada.set("")
        self.var_hot_folder.set("C:\\HotFolder")
        self.var_posto.set(POSTO_RIP)
        self.var_setup_sai.set("")
        self.var_montagem.set(True)
        self.var_largura_montagem.set("1.50")
        self.var_margem_montagem.set("0.0")
        self.var_girar.set(True)
        self.var_entrega_byhx.set(False)

        self._ao_alternar_tipo_midia()
        self._ao_alternar_montagem()
        self._ao_mudar_rip()
        self.entry_nome.focus_set()
        self.entry_nome.select_range(0, tk.END)

    def _testar_conexao_hotfolder(self):
        """Valida a pasta de saída do RIP (Hot Folder) usando o driver de hardware adequado."""
        caminho = self.var_hot_folder.get().strip()
        if not caminho:
            messagebox.showwarning(
                "Aviso", "Por favor, informe a pasta de saída do RIP (Hot Folder).", parent=self
            )
            return

        rotulo_rip = self.var_rip_opcao.get()
        rip_cod, _ = MAPA_EXIBICAO_RIP.get(rotulo_rip, ("generico", "local"))
        info_teste = MaquinaInfo(
            nome=self.var_nome.get().strip() or "Teste",
            hot_folder=caminho,
            rip_tipo=rip_cod,
            setup_sai=self.var_setup_sai.get().strip() or None,
        )
        try:
            driver = self.gerenciador.obter_driver(info_teste)
            ok = driver.validar_conexao()
            status = driver.obter_status()
            if ok:
                msg = f"✓ Conexão validada com sucesso!\n\nPasta: {caminho}\nStatus: {status.mensagem}"
                if status.espaco_livre_bytes is not None:
                    gb = status.espaco_livre_bytes / (1024 ** 3)
                    msg += f"\nEspaço Livre no Disco: {gb:.2f} GB"
                msg += f"\nTrabalhos Pendentes: {status.total_pendentes}"
                messagebox.showinfo("Conexão Validada", msg, parent=self)
            else:
                messagebox.showerror(
                    "Falha na Conexão",
                    f"Não foi possível validar a pasta do RIP:\n{caminho}\n\n"
                    f"Detalhe: {status.mensagem or 'Pasta inexistente ou sem permissão de escrita.'}",
                    parent=self,
                )
        except Exception as e:
            messagebox.showerror("Erro ao Validar", f"Erro ao testar conexão: {e}", parent=self)

    def _salvar_maquina(self):
        nome = self.var_nome.get().strip()
        if not nome:
            messagebox.showwarning("Nome Obrigatório", "Por favor, informe o nome da máquina.", parent=self)
            self.entry_nome.focus_set()
            return

        # Validação numérica
        tipo = self.var_tipo.get()
        largura_util = None
        mesa_util = None

        try:
            if tipo == "mesa":
                x = float(self.var_mesa_x.get().strip().replace(",", "."))
                y = float(self.var_mesa_y.get().strip().replace(",", "."))
                if x <= 0 or y <= 0:
                    raise ValueError
                mesa_util = (round(x, 3), round(y, 3))
            else:
                l_val = float(self.var_largura_util.get().strip().replace(",", "."))
                if l_val <= 0:
                    raise ValueError
                largura_util = round(l_val, 3)
        except (ValueError, TypeError):
            msg = "Informe dimensões úteis válidas (números maiores que zero)."
            messagebox.showwarning("Medida Inválida", msg, parent=self)
            return

        # Validação de montagem
        largura_mont = None
        margem_mont = 0.0
        if self.var_montagem.get():
            try:
                l_m = float(self.var_largura_montagem.get().strip().replace(",", "."))
                m_m = float(self.var_margem_montagem.get().strip().replace(",", "."))
                largura_mont = round(l_m, 3)
                margem_mont = round(m_m, 3)
            except (ValueError, TypeError):
                messagebox.showwarning("Medida de Montagem Inválida", "Verifique as medidas de fechamento e margem da montagem.", parent=self)
                return

        rotulo_rip = self.var_rip_opcao.get()
        rip_cod, _ = MAPA_EXIBICAO_RIP.get(rotulo_rip, ("generico", "local"))

        # Monta dict da máquina
        cfg = {
            "pasta_entrada": self.var_pasta_entrada.get().strip().strip('"'),
            "hot_folder": self.var_hot_folder.get().strip().strip('"'),
            "tipo": tipo,
            "posto": self.var_posto.get().strip() or "local",
            "rip_tipo": rip_cod,
            "montagem": self.var_montagem.get(),
            "girar": self.var_girar.get(),
            "entrega_byhx": self.var_entrega_byhx.get() if rip_cod == "sai" else False,
        }

        if tipo == "mesa":
            cfg["mesa_util_m"] = mesa_util
        else:
            cfg["largura_util_m"] = largura_util

        if self.var_montagem.get():
            cfg["largura_montagem_m"] = largura_mont or largura_util or 1.50
            cfg["margem_montagem_m"] = margem_mont

        if rip_cod == "sai":
            cfg["setup_sai"] = self.var_setup_sai.get().strip()

        # Se mudou o nome da máquina, remove o antigo
        if self.nome_em_edicao and self.nome_em_edicao != nome:
            if self.nome_em_edicao in self.maquinas:
                del self.maquinas[self.nome_em_edicao]

        self.maquinas[nome] = cfg
        m_info = MaquinaInfo.from_dict(nome, cfg)
        self.gerenciador.atualizar_maquina(self.nome_em_edicao or nome, m_info, persistir=False)
        self._persistir_alteracoes()
        self._recarregar_lista()
        self._selecionar_maquina_por_nome(nome)
        self.lbl_status.config(text=f"✓ Máquina '{nome}' salva com sucesso!")

    def _excluir_maquina(self):
        selecionados = self.tree.selection()
        if not selecionados:
            messagebox.showinfo("Nenhuma seleção", "Selecione uma máquina na lista para excluir.", parent=self)
            return

        nome = selecionados[0]
        if not messagebox.askyesno("Confirmar Exclusão", f"Deseja realmente remover a máquina '{nome}'?", parent=self):
            return

        if nome in self.maquinas:
            del self.maquinas[nome]
            self.gerenciador.remover_maquina(nome, persistir=False)
            self._persistir_alteracoes()
            self._recarregar_lista()
            if self.maquinas:
                primeira = list(self.maquinas.keys())[0]
                self._selecionar_maquina_por_nome(primeira)
            else:
                self._nova_maquina()
            self.lbl_status.config(text=f"✓ Máquina '{nome}' removida.")

    def _restaurar_padrao(self):
        if not messagebox.askyesno(
            "Restaurar Padrões de Fábrica",
            "Deseja restaurar as 4 máquinas padrão de fábrica?\n"
            "(UJV 100 UNY CV, SWJ320A, DOCAN R5200, DOCAN H2525)",
            parent=self,
        ):
            return

        self.gerenciador.restaurar_padroes(persistir=False)
        self.maquinas = {m.nome: m.to_dict() for m in self.gerenciador.listar_maquinas()}
        self._persistir_alteracoes()
        self._recarregar_lista()
        primeira = list(self.maquinas.keys())[0]
        self._selecionar_maquina_por_nome(primeira)
        self.lbl_status.config(text="✓ Padrões de fábrica restaurados!")

    def _persistir_alteracoes(self):
        """Salva no config.json, atualiza memória de rasterlink_hotfolder e persiste hardware."""
        self.gerenciador.persistir()
        salvar_maquinas_config(self.maquinas)
        atualizar_maquinas_em_memoria(self.maquinas)

        # Atualiza config_dados em memória da aplicação se fornecido
        if self.config_dados is not None and isinstance(self.config_dados, dict):
            self.config_dados["maquinas"] = copy.deepcopy(self.maquinas)

        # Notifica callback externo
        if self.ao_salvar and callable(self.ao_salvar):
            try:
                self.ao_salvar()
            except Exception:
                pass
