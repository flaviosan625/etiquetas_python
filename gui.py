"""
Interface gráfica (tkinter) do programa. Duas janelas:

  - JanelaPrincipal: escolher a pasta de entrada, preencher cliente /
    gerente / produtor, disparar o processamento e acompanhar o log e
    a barra de progresso em tempo real.
  - JanelaConfiguracoes: cadastrar/editar/remover materiais (rolos e
    chapas), incluindo medidas novas ou categorias novas, sem precisar
    editar nenhum arquivo de código.

O processamento roda numa thread separada para a janela não travar
("não responder") durante o processamento de muitos arquivos. A thread
não mexe direto nos widgets (tkinter não é thread-safe); em vez disso,
ela só coloca eventos numa fila, e a janela principal lê essa fila
periodicamente com root.after(...).
"""
import pathlib
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from branding import CAMINHO_LOGO_GUI
from config import atualizar_ultimo_uso, carregar_config, salvar_config
from processamento import processar_etiquetas

COR_ACENTO = "#0067c0"


def _rotulo_variantes(variantes):
    return f"Variantes ({len(variantes)})" if variantes else "Variantes..."


class JanelaPrincipal(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerador de Etiquetas — UNY CV")
        self.geometry("640x600")
        self.minsize(560, 520)

        self.config_dados = carregar_config()
        self.fila_eventos = queue.Queue()
        self.processando = False

        self._montar_layout()
        self.after(100, self._checar_fila)

    # ---------- montagem da tela ----------

    def _montar_layout(self):
        pad = {"padx": 16, "pady": 6}

        self._montar_cabecalho()

        tk.Label(self, text="Gerar etiquetas e OS", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(14, 4))

        frame_pasta = tk.Frame(self)
        frame_pasta.pack(fill="x", **pad)
        tk.Label(frame_pasta, text="Pasta de entrada (PDFs)").pack(anchor="w")
        sub = tk.Frame(frame_pasta)
        sub.pack(fill="x")
        self.var_pasta = tk.StringVar(value=str(pathlib.Path("entrada").resolve()))
        tk.Entry(sub, textvariable=self.var_pasta).pack(side="left", fill="x", expand=True)
        tk.Button(sub, text="Procurar...", command=self._escolher_pasta).pack(side="left", padx=(6, 0))

        self._campo(pad, "Cliente", "var_cliente")

        frame_pessoas = tk.Frame(self)
        frame_pessoas.pack(fill="x", **pad)
        col1 = tk.Frame(frame_pessoas)
        col1.pack(side="left", fill="x", expand=True)
        col2 = tk.Frame(frame_pessoas)
        col2.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(col1, text="Gerente operacional").pack(anchor="w")
        self.var_gerente = tk.StringVar(value=self.config_dados.get("ultimo_gerente", ""))
        tk.Entry(col1, textvariable=self.var_gerente).pack(fill="x")
        tk.Label(col2, text="Produtor responsável").pack(anchor="w")
        self.var_produtor = tk.StringVar(value=self.config_dados.get("ultimo_produtor", ""))
        tk.Entry(col2, textvariable=self.var_produtor).pack(fill="x")

        tk.Button(
            self, text="⚙ Configurar medidas de rolos e chapas...", relief="flat",
            fg=COR_ACENTO, cursor="hand2", command=self._abrir_configuracoes,
        ).pack(anchor="w", padx=16, pady=(4, 10))

        ttk.Separator(self).pack(fill="x", padx=16)

        self.btn_processar = tk.Button(
            self, text="▶  Processar Etiquetas", bg=COR_ACENTO, fg="white",
            font=("Segoe UI", 11, "bold"), relief="flat", command=self._iniciar_processamento,
        )
        self.btn_processar.pack(fill="x", padx=16, pady=12, ipady=8)

        self.var_progresso_texto = tk.StringVar(value="")
        tk.Label(self, textvariable=self.var_progresso_texto, fg="#555555").pack(anchor="w", padx=16)
        self.barra_progresso = ttk.Progressbar(self, mode="determinate")
        self.barra_progresso.pack(fill="x", padx=16, pady=(2, 10))

        self.texto_log = tk.Text(self, height=12, bg="#0f1116", fg="#d6d9e0", font=("Consolas", 9), state="disabled")
        self.texto_log.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.texto_log.tag_config("ok", foreground="#7ee787")
        self.texto_log.tag_config("warn", foreground="#f0b854")
        self.texto_log.tag_config("err", foreground="#ff7b72")
        self.texto_log.tag_config("info", foreground="#9aa4b2")

    def _montar_cabecalho(self):
        """
        Mostra o logo da Uny CV no topo da janela, se o arquivo existir
        (CAMINHO_LOGO_GUI, em assets/). Se não existir — por exemplo,
        clonando o repositório numa máquina onde a pasta assets ainda
        não foi copiada — a tela simplesmente abre sem o logo, sem
        travar o programa.
        """
        if not CAMINHO_LOGO_GUI.exists():
            return
        try:
            self.imagem_logo = tk.PhotoImage(file=str(CAMINHO_LOGO_GUI))
        except tk.TclError:
            return
        tk.Label(self, image=self.imagem_logo).pack(anchor="w", padx=16, pady=(14, 0))

    def _campo(self, pad, rotulo, nome_var):
        frame = tk.Frame(self)
        frame.pack(fill="x", **pad)
        tk.Label(frame, text=rotulo).pack(anchor="w")
        var = tk.StringVar()
        setattr(self, nome_var, var)
        tk.Entry(frame, textvariable=var).pack(fill="x")

    # ---------- ações ----------

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta com os PDFs")
        if pasta:
            self.var_pasta.set(pasta)

    def _abrir_configuracoes(self):
        JanelaConfiguracoes(self, self.config_dados, self._config_atualizada)

    def _config_atualizada(self, nova_config):
        self.config_dados = nova_config

    def _registrar_log(self, nivel, mensagem):
        prefixos = {"ok": "✅ ", "warn": "⚠️ ", "err": "❌ ", "info": "ℹ️ "}
        self.texto_log.configure(state="normal")
        self.texto_log.insert("end", prefixos.get(nivel, "") + mensagem + "\n", nivel)
        self.texto_log.see("end")
        self.texto_log.configure(state="disabled")

    def _iniciar_processamento(self):
        if self.processando:
            return

        pasta = self.var_pasta.get().strip()
        cliente = self.var_cliente.get().strip()
        gerente = self.var_gerente.get().strip()
        produtor = self.var_produtor.get().strip()

        if not cliente:
            messagebox.showwarning("Campo obrigatório", "Preencha o nome do cliente antes de processar.")
            return
        if not gerente or not produtor:
            messagebox.showwarning("Campo obrigatório", "Preencha o gerente operacional e o produtor responsável.")
            return

        self.texto_log.configure(state="normal")
        self.texto_log.delete("1.0", "end")
        self.texto_log.configure(state="disabled")
        self.barra_progresso["value"] = 0
        self.var_progresso_texto.set("Iniciando...")
        self.processando = True
        self.btn_processar.configure(state="disabled", text="Processando...")

        self.config_dados = atualizar_ultimo_uso(self.config_dados, gerente, produtor)

        thread = threading.Thread(
            target=self._executar_em_thread,
            args=(pasta, cliente, gerente, produtor),
            daemon=True,
        )
        thread.start()

    def _executar_em_thread(self, pasta, cliente, gerente, produtor):
        def on_log(nivel, msg):
            self.fila_eventos.put(("log", nivel, msg))

        def on_progress(atual, total):
            self.fila_eventos.put(("progress", atual, total))

        try:
            resultado = processar_etiquetas(
                pasta, cliente, gerente, produtor, self.config_dados,
                on_log=on_log, on_progress=on_progress,
            )
        except Exception as e:
            self.fila_eventos.put(("log", "err", f"Erro inesperado: {e}"))
            resultado = None

        self.fila_eventos.put(("fim", resultado, None))

    def _checar_fila(self):
        try:
            while True:
                evento = self.fila_eventos.get_nowait()
                tipo = evento[0]
                if tipo == "log":
                    self._registrar_log(evento[1], evento[2])
                elif tipo == "progress":
                    atual, total = evento[1], evento[2]
                    self.barra_progresso["maximum"] = max(total, 1)
                    self.barra_progresso["value"] = atual
                    self.var_progresso_texto.set(f"Processando {atual} de {total}...")
                elif tipo == "fim":
                    self.processando = False
                    self.btn_processar.configure(state="normal", text="▶  Processar Etiquetas")
                    resultado = evento[1]
                    if resultado:
                        self.var_progresso_texto.set("Concluído.")
                        messagebox.showinfo("Concluído", f"Etiquetas geradas em:\n{resultado['pasta_saida']}")
                    else:
                        self.var_progresso_texto.set("Processamento interrompido — veja o log acima.")
        except queue.Empty:
            pass
        self.after(150, self._checar_fila)


class JanelaConfiguracoes(tk.Toplevel):
    """
    Tela de cadastro de materiais (rolos e chapas). É aqui que, no
    futuro, uma medida nova de rolo/chapa (ou uma categoria de material
    inteiramente nova) pode ser adicionada sem tocar em código.
    """

    def __init__(self, mestre, config_dados, ao_salvar):
        super().__init__(mestre)
        self.title("Configurar Materiais")
        self.geometry("580x500")
        self.transient(mestre)
        self.config_dados = config_dados
        self.ao_salvar = ao_salvar
        self.linhas = []

        self._montar_layout()
        self.grab_set()

    def _montar_layout(self):
        tk.Label(self, text="Rolos e chapas cadastrados", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            self, fg="#666666",
            text="Edite as medidas existentes ou adicione um material novo. As mudanças valem para o cálculo\nde desperdício e para o reconhecimento de categoria pelo nome do arquivo.",
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        cabecalho = tk.Frame(self)
        cabecalho.pack(fill="x", padx=16)
        for texto, largura in [("Categoria", 16), ("Tipo", 10), ("Largura (cm)", 12), ("Compr. (cm)", 12), ("", 3)]:
            tk.Label(cabecalho, text=texto, fg="#666666", width=largura, anchor="w").pack(side="left")

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.frame_linhas = tk.Frame(canvas)
        self.frame_linhas.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.frame_linhas, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(16, 0))
        scrollbar.pack(side="left", fill="y", padx=(0, 16))

        for categoria, dados in self.config_dados["materiais"].items():
            self._adicionar_linha(categoria, dados["tipo"], dados["largura_cm"], dados["comprimento_cm"], dados.get("variantes", []))

        tk.Button(
            self, text="➕ Adicionar novo material", relief="flat", fg=COR_ACENTO, cursor="hand2",
            command=lambda: self._adicionar_linha("", "rolo", "", "", []),
        ).pack(anchor="w", padx=16, pady=8)

        frame_botoes = tk.Frame(self)
        frame_botoes.pack(fill="x", padx=16, pady=14)
        tk.Button(frame_botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        tk.Button(frame_botoes, text="Salvar", bg=COR_ACENTO, fg="white", relief="flat", command=self._salvar).pack(side="right")

    def _adicionar_linha(self, categoria, tipo, largura, comprimento, variantes):
        linha = tk.Frame(self.frame_linhas)
        linha.pack(fill="x", pady=2)

        var_categoria = tk.StringVar(value=categoria)
        var_tipo = tk.StringVar(value=tipo or "rolo")
        var_largura = tk.StringVar(value=str(largura))
        var_comprimento = tk.StringVar(value=str(comprimento))

        tk.Entry(linha, textvariable=var_categoria, width=16).pack(side="left")
        ttk.Combobox(linha, textvariable=var_tipo, values=["rolo", "chapa"], width=8, state="readonly").pack(side="left", padx=4)
        tk.Entry(linha, textvariable=var_largura, width=12).pack(side="left", padx=4)
        tk.Entry(linha, textvariable=var_comprimento, width=12).pack(side="left", padx=4)

        registro = {
            "frame": linha, "categoria": var_categoria, "tipo": var_tipo,
            "largura": var_largura, "comprimento": var_comprimento, "variantes": list(variantes or []),
        }

        def abrir_variantes():
            def salvar_variantes(novas_variantes):
                registro["variantes"] = novas_variantes
                btn_variantes.configure(text=_rotulo_variantes(novas_variantes))
            JanelaVariantes(self, var_categoria.get(), registro["variantes"], salvar_variantes)

        btn_variantes = tk.Button(
            linha, text=_rotulo_variantes(registro["variantes"]), relief="flat", fg=COR_ACENTO, cursor="hand2",
            command=abrir_variantes,
        )
        btn_variantes.pack(side="left", padx=4)

        def remover():
            linha.destroy()
            self.linhas.remove(registro)

        tk.Button(linha, text="🗑", relief="flat", fg="#c92a2a", cursor="hand2", command=remover).pack(side="left", padx=4)

        self.linhas.append(registro)

    def _salvar(self):
        novos_materiais = {}
        for registro in self.linhas:
            categoria = registro["categoria"].get().strip().upper()
            if not categoria:
                continue
            texto_largura = registro["largura"].get().strip().replace(",", ".")
            texto_comprimento = registro["comprimento"].get().strip().replace(",", ".")
            try:
                largura = float(texto_largura)
                comprimento = float(texto_comprimento)
                if largura <= 0 or comprimento <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(
                    "Valor inválido",
                    f"Largura e comprimento de '{categoria}' precisam ser números maiores que zero.",
                )
                return
            material = {
                "tipo": registro["tipo"].get(),
                "largura_cm": largura,
                "comprimento_cm": comprimento,
            }
            if registro["variantes"]:
                material["variantes"] = registro["variantes"]
            novos_materiais[categoria] = material

        if not novos_materiais:
            messagebox.showwarning("Nenhum material", "Cadastre ao menos um material antes de salvar.")
            return

        self.config_dados["materiais"] = novos_materiais
        # mantém, na ordem do PDF unificado, só quem ainda existe, e
        # adiciona no final categorias novas que não tinham ordem definida
        ordem_antiga = [c for c in self.config_dados.get("ordem_unificado", []) if c in novos_materiais]
        self.config_dados["ordem_unificado"] = ordem_antiga + [c for c in novos_materiais if c not in ordem_antiga]

        salvar_config(self.config_dados)
        self.ao_salvar(self.config_dados)
        messagebox.showinfo("Salvo", "Configurações de materiais salvas com sucesso.")
        self.destroy()


class JanelaVariantes(tk.Toplevel):
    """
    Cadastro das variantes (espessura + cor) de uma chapa especial, como
    PVC 10mm preto ou Acrílico 3mm cristal. O tamanho da chapa continua
    sendo o mesmo já cadastrado para a categoria — a variante serve só
    pra reconhecer automaticamente, pelo nome do arquivo, qual espessura
    e cor é (as duas palavras precisam aparecer no nome).
    """

    def __init__(self, mestre, nome_categoria, variantes_atuais, ao_salvar):
        super().__init__(mestre)
        self.title(f"Variantes — {nome_categoria.strip() or '(novo material)'}")
        self.geometry("420x460")
        self.transient(mestre)
        self.ao_salvar = ao_salvar
        self.linhas_variantes = []

        self._montar_layout(variantes_atuais)
        self.grab_set()

    def _montar_layout(self, variantes_atuais):
        tk.Label(self, text="Espessura e cor de cada variante", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            self, fg="#666666", justify="left",
            text="O tamanho da chapa é o mesmo já cadastrado para a categoria.\n"
                 "Cor é opcional — deixe em branco pra uma variante que só depende\n"
                 "da espessura (ex: MDF cru). Rótulo é opcional, pra quando o nome\n"
                 "comercial é diferente da cor usada no nome do arquivo (ex: cor\n"
                 "\"VERDE\" no arquivo, mas rótulo \"MDF HIDRO\" na exibição).",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        cabecalho = tk.Frame(self)
        cabecalho.pack(fill="x", padx=16)
        for texto, largura in [("Espessura", 12), ("Cor (opcional)", 12), ("Rótulo (opcional)", 14)]:
            tk.Label(cabecalho, text=texto, fg="#666666", width=largura, anchor="w").pack(side="left")

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.frame_linhas = tk.Frame(canvas)
        self.frame_linhas.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.frame_linhas, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(16, 0))
        scrollbar.pack(side="left", fill="y", padx=(0, 16))

        for variante in variantes_atuais:
            self._adicionar_linha_variante(variante.get("espessura", ""), variante.get("cor", ""), variante.get("rotulo", ""))

        tk.Button(
            self, text="➕ Adicionar variante", relief="flat", fg=COR_ACENTO, cursor="hand2",
            command=lambda: self._adicionar_linha_variante("", "", ""),
        ).pack(anchor="w", padx=16, pady=8)

        frame_botoes = tk.Frame(self)
        frame_botoes.pack(fill="x", padx=16, pady=14)
        tk.Button(frame_botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        tk.Button(frame_botoes, text="Salvar", bg=COR_ACENTO, fg="white", relief="flat", command=self._salvar).pack(side="right")

    def _adicionar_linha_variante(self, espessura, cor, rotulo):
        linha = tk.Frame(self.frame_linhas)
        linha.pack(fill="x", pady=2)

        var_espessura = tk.StringVar(value=espessura)
        var_cor = tk.StringVar(value=cor)
        var_rotulo = tk.StringVar(value=rotulo)

        tk.Entry(linha, textvariable=var_espessura, width=12).pack(side="left")
        tk.Entry(linha, textvariable=var_cor, width=12).pack(side="left", padx=4)
        tk.Entry(linha, textvariable=var_rotulo, width=14).pack(side="left", padx=4)

        registro = {"frame": linha, "espessura": var_espessura, "cor": var_cor, "rotulo": var_rotulo}

        def remover():
            linha.destroy()
            self.linhas_variantes.remove(registro)

        tk.Button(linha, text="🗑", relief="flat", fg="#c92a2a", cursor="hand2", command=remover).pack(side="left", padx=4)

        self.linhas_variantes.append(registro)

    def _salvar(self):
        novas_variantes = []
        for registro in self.linhas_variantes:
            espessura = registro["espessura"].get().strip().upper()
            cor = registro["cor"].get().strip().upper()
            rotulo = registro["rotulo"].get().strip().upper()
            if not espessura:
                continue
            variante = {"espessura": espessura}
            if cor:
                variante["cor"] = cor
            if rotulo:
                variante["rotulo"] = rotulo
            novas_variantes.append(variante)

        self.ao_salvar(novas_variantes)
        self.destroy()
