"""
Montar arte para impressão — a tela de montagem.py.

Pedido dele (05/10/2026): *"criar um botão dentro do sistema MONTAR ARTE
PARA IMPRESSÃO, lá dentro um separador se é montagem para DOCAN ou a
SWJ"*, e logo em seguida *"ele vai pegar os arquivos que joguei na pasta,
calcular e passar os dados na tela"*.

Então a tela é uma aba por máquina que monta, e cada aba LÊ a pasta dela,
calcula o encaixe e mostra o resultado ANTES de escrever qualquer coisa:
como a folha vai fechar, quanto aproveita, e peça por peça o que o nome
pede, o que vai sair e a diferença entre os dois em milímetros. Montar é
um botão à parte.

A coluna da largura é zero por construção (ela é a âncora) e aparece
justamente por isso: é a prova, na tela que ele lê antes de mandar
imprimir, de que a regra está valendo. Quem muda é o comprimento.

A conta aqui não existe: é `montagem.prever_pasta`, a MESMA que monta de
verdade. Prévia calculada por fora é prévia que mente no dia em que uma
das duas mudar.
"""
import os
import pathlib
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import montagem
from tema import cores

# Quanto tempo o aviso de "pronto" fica na tela antes de voltar ao normal
_MOSTRA_RESULTADO_MS = 20000


class JanelaMontagem(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Montar arte para impressão — UNY CV")
        self.configure(bg=cores.fundo)
        self.geometry("1040x700")
        self.minsize(820, 480)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._montar_cabecalho()

        self._abas = {}
        caderno = ttk.Notebook(self)
        caderno.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        for nome_maquina in montagem.maquinas_que_montam():
            aba = _AbaMaquina(caderno, nome_maquina)
            caderno.add(aba, text=f"  {nome_maquina}  ")
            self._abas[nome_maquina] = aba
        if not self._abas:
            tk.Label(self, text="Nenhuma máquina está cadastrada para montar.",
                     bg=cores.fundo, fg=cores.alerta,
                     font=("Segoe UI", 10)).grid(row=1, column=0, padx=20, pady=20)

    def _montar_cabecalho(self):
        topo = tk.Frame(self, bg=cores.fundo)
        topo.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        tk.Label(topo, text="Montar arte para impressão", font=("Segoe UI", 15, "bold"),
                 bg=cores.fundo, fg=cores.texto).pack(anchor="w")
        tk.Label(topo,
                 text="Largue as artes na pasta da máquina. Aqui você vê como a folha vai "
                      "fechar antes de gerar o PDF.",
                 font=("Segoe UI", 9), bg=cores.fundo, fg=cores.texto2).pack(anchor="w")


class _AbaMaquina(tk.Frame):
    """Uma máquina: a pasta dela, a prévia do encaixe e o botão de montar."""

    def __init__(self, master, nome_maquina):
        super().__init__(master, bg=cores.fundo)
        self.nome_maquina = nome_maquina
        self.pasta = montagem.pasta_da_maquina(nome_maquina)
        self._previa = None
        self._ocupada = False
        self._job_resultado = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._montar_topo()
        self._montar_resumo()
        self._montar_tabela()
        self._montar_rodape()
        self.calcular()

    # ------------------------------------------------------------ montagem

    def _montar_topo(self):
        linha = tk.Frame(self, bg=cores.fundo)
        linha.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        medida = montagem.mesa(self.nome_maquina) or montagem.largura_util(self.nome_maquina)
        if isinstance(medida, tuple):
            dito = f"chapa de {medida[0]:.2f} x {medida[1]:.2f} m"
        else:
            dito = f"fecha em {medida:.2f} m de largura"
        tk.Label(linha, text=dito, font=("Segoe UI", 9, "bold"),
                 bg=cores.fundo, fg=cores.texto).pack(side="left")
        tk.Button(linha, text="📂  abrir a pasta", relief="flat", cursor="hand2",
                  bg=cores.cartao, fg=cores.acento, activebackground=cores.cartao,
                  command=self._abrir_pasta).pack(side="right")
        tk.Label(self, text=str(self.pasta), font=("Segoe UI", 8),
                 bg=cores.fundo, fg=cores.texto2, anchor="w",
                 justify="left").grid(row=1, column=0, sticky="ew", padx=16)

    def _montar_resumo(self):
        self.caixa_resumo = tk.Frame(self, bg=cores.cartao,
                                     highlightbackground=cores.borda, highlightthickness=1)
        self.caixa_resumo.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 0))
        self.var_resumo = tk.StringVar(value="lendo a pasta...")
        tk.Label(self.caixa_resumo, textvariable=self.var_resumo,
                 font=("Segoe UI", 10, "bold"), bg=cores.cartao, fg=cores.texto,
                 anchor="w", justify="left").pack(fill="x", padx=12, pady=(10, 2))
        self.var_margem = tk.StringVar(value="")
        tk.Label(self.caixa_resumo, textvariable=self.var_margem,
                 font=("Segoe UI", 9), bg=cores.cartao, fg=cores.texto2,
                 anchor="w", justify="left").pack(fill="x", padx=12, pady=(0, 4))
        self.var_recusadas = tk.StringVar(value="")
        self.rotulo_recusadas = tk.Label(
            self.caixa_resumo, textvariable=self.var_recusadas, font=("Segoe UI", 9),
            bg=cores.cartao, fg=cores.alerta, anchor="w", justify="left", wraplength=940)
        self.rotulo_recusadas.pack(fill="x", padx=12, pady=(0, 10))

    def _montar_tabela(self):
        quadro = tk.Frame(self, bg=cores.fundo)
        quadro.grid(row=2, column=0, sticky="nsew", padx=16, pady=(8, 0))
        quadro.columnconfigure(0, weight=1)
        quadro.rowconfigure(0, weight=1)
        colunas = ("numero", "arquivo", "pede", "sai", "largura", "comprimento", "giro")
        self.tabela = ttk.Treeview(quadro, columns=colunas, show="headings", height=10)
        titulos = {
            "numero": ("nº", 36, "center"),
            "arquivo": ("arquivo", 380, "w"),
            "pede": ("o nome pede", 120, "center"),
            "sai": ("vai sair", 120, "center"),
            "largura": ("largura", 80, "e"),
            "comprimento": ("comprimento", 100, "e"),
            "giro": ("giro", 60, "center"),
        }
        for coluna, (titulo, largura, alinhar) in titulos.items():
            self.tabela.heading(coluna, text=titulo)
            self.tabela.column(coluna, width=largura, anchor=alinhar,
                               stretch=(coluna == "arquivo"))
        self.tabela.grid(row=0, column=0, sticky="nsew")
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.tabela.yview)
        barra.grid(row=0, column=1, sticky="ns")
        self.tabela.configure(yscrollcommand=barra.set)
        # a linha cuja medida mudou sai assinalada: número deduzido nunca
        # se passa por declarado, nem na tela
        self.tabela.tag_configure("mudou", foreground=cores.alerta)
        self.tabela.tag_configure("folha", font=("Segoe UI", 9, "bold"))

    def _montar_rodape(self):
        linha = tk.Frame(self, bg=cores.fundo)
        linha.grid(row=4, column=0, sticky="ew", padx=16, pady=(10, 14))
        self.btn_atualizar = tk.Button(
            linha, text="↻  recalcular", relief="flat", cursor="hand2",
            bg=cores.cartao, fg=cores.texto, activebackground=cores.cartao,
            command=self.calcular)
        self.btn_atualizar.pack(side="left")
        self.btn_montar = tk.Button(
            linha, text="▶   Montar e salvar o PDF", relief="flat", cursor="hand2",
            bg=cores.acento, fg=cores.sobre_acento, activebackground=cores.acento_claro,
            activeforeground=cores.sobre_acento, font=("Segoe UI", 10, "bold"),
            padx=14, pady=6, command=self._montar_agora)
        self.btn_montar.pack(side="right")
        self.btn_abrir_pdf = tk.Button(
            linha, text="abrir o PDF", relief="flat", cursor="hand2",
            bg=cores.cartao, fg=cores.acento, activebackground=cores.cartao,
            command=self._abrir_pdf)
        self._feitas = []

    # ------------------------------------------------------------ calcular

    def calcular(self):
        """Lê a pasta e mostra o que a montagem FARIA. Não escreve nada."""
        if self._ocupada:
            return
        self._ocupada = True
        self.btn_montar.configure(state="disabled")
        self.btn_atualizar.configure(state="disabled")
        self.var_resumo.set("lendo a pasta...")

        def trabalhar():
            try:
                previa = montagem.prever_pasta(self.pasta, self.nome_maquina)
                erro = None
            except Exception as e:                       # noqa: BLE001
                previa, erro = None, f"{type(e).__name__}: {e}"
            self.after(0, lambda: self._mostrar(previa, erro))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _mostrar(self, previa, erro):
        self._ocupada = False
        self.btn_atualizar.configure(state="normal")
        for linha in self.tabela.get_children():
            self.tabela.delete(linha)

        if erro is not None:
            self.var_resumo.set("Não consegui ler a pasta")
            self.var_margem.set(erro)
            self.var_recusadas.set("")
            self.btn_montar.configure(state="disabled")
            return

        self._previa = previa
        self.var_recusadas.set(
            "" if not previa["recusadas"] else
            "Fica de fora: " + " · ".join(
                f"{r['arquivo']} ({r['motivo']})" for r in previa["recusadas"]))

        if not previa["folhas"]:
            self.var_resumo.set("Nada para montar nesta pasta")
            self.var_margem.set("Largue as artes na pasta da máquina e clique em recalcular.")
            self.btn_montar.configure(state="disabled")
            return

        pecas = sum(f["pecas"] for f in previa["folhas"])
        cliente = previa["cliente"] or "sem cliente reconhecido no nome"
        self.var_resumo.set(
            f"{pecas} peça(s) · {cliente} · "
            + "   ".join(f"{f['categoria']} em {f['tamanho']} "
                         f"({f['aproveitamento'] * 100:.0f}% de aproveitamento)"
                         for f in previa["folhas"]))
        pior = previa["pior_diferenca_mm"]
        self.var_margem.set(
            "A largura fecha exata, do nome. "
            + (f"A diferença fica no comprimento: até {pior:.0f} mm."
               if pior >= 0.5 else "O comprimento também bate o nome."))

        for folha in previa["folhas"]:
            if len(previa["folhas"]) > 1:
                self.tabela.insert(
                    "", "end", values=("", f"— {folha['categoria']} —", "", "", "", "", ""),
                    tags=("folha",))
            for item in folha["itens"]:
                mudou = abs(item["diferenca_comprimento_mm"]) >= 0.5
                self.tabela.insert("", "end", tags=("mudou",) if mudou else (), values=(
                    f"{item['numero']:02d}",
                    item["arquivo"],
                    f"{item['nome_m'][0]:.2f} x {item['nome_m'][1]:.2f}",
                    f"{item['medida_m'][0]:.3f} x {item['medida_m'][1]:.3f}",
                    f"{item['erro_largura_mm']:+.2f} mm",
                    f"{item['diferenca_comprimento_mm']:+.0f} mm",
                    "sim" if item["girada"] else "",
                ))
        self.btn_montar.configure(state="normal")

    # ------------------------------------------------------------ montar

    def _montar_agora(self):
        if self._ocupada or not self._previa or not self._previa["folhas"]:
            return
        self._ocupada = True
        self.btn_montar.configure(state="disabled", text="Montando...")
        self.btn_atualizar.configure(state="disabled")

        def trabalhar():
            try:
                resultado = montagem.montar_pasta(self.pasta, self.nome_maquina)
                erro = None
            except Exception as e:                       # noqa: BLE001
                resultado, erro = None, f"{type(e).__name__}: {e}"
            self.after(0, lambda: self._montou(resultado, erro))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _montou(self, resultado, erro):
        self._ocupada = False
        self.btn_montar.configure(text="▶   Montar e salvar o PDF")
        self.btn_atualizar.configure(state="normal")
        if erro is not None:
            messagebox.showerror("A montagem parou", erro, parent=self)
            self.calcular()
            return

        self._feitas = [f["arquivo"] for f in resultado["folhas"]]
        if self._feitas:
            self.btn_abrir_pdf.pack(side="right", padx=(0, 8))
            nomes = ", ".join(p.name for p in self._feitas)
            self.var_resumo.set(f"Pronto: {nomes}")
            self.var_margem.set("O PDF está na pasta da máquina, com a ficha .json ao lado.")
        if self._job_resultado is not None:
            try:
                self.after_cancel(self._job_resultado)
            except tk.TclError:
                pass
        self._job_resultado = self.after(_MOSTRA_RESULTADO_MS, self.calcular)
        for linha in self.tabela.get_children():
            self.tabela.delete(linha)

    # ------------------------------------------------------------ abrir

    def _abrir_pasta(self):
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._abrir(self.pasta)

    def _abrir_pdf(self):
        if self._feitas:
            self._abrir(self._feitas[0])

    def _abrir(self, caminho):
        try:
            os.startfile(str(pathlib.Path(caminho)))
        except OSError as e:
            messagebox.showerror("Erro", f"Não consegui abrir {caminho}: {e}", parent=self)
