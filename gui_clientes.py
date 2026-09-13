"""
Janela de Clientes — a tela de clientes.py.

Pedido do usuário (2026-09-13): "eu preciso criar uma pasta lá dentro de
Recebimento de Artes com o nome do novo cliente, ou arruma um jeito dessa
criação pela nossa janela deixando interativo — nosso sistema precisa
funcionar totalmente pela janela".

Um cartão por cliente (cada pasta em Recebimento de Artes), no mesmo visual
do Controle de Estoque e dos Agentes. Por cliente dá pra:
  - escolher a pasta de produção (seletor nativo do Windows — o que ele
    escolheu pro envio, e não prévia de pasta, que foi recusada duas vezes);
  - ligar/desligar o checklist automático (a OS que o vigia mantém);
  - ver quantas artes chegaram desde o último checklist de etiquetas e gerar
    o lote delas — sempre com confirmação antes, como é regra ao regerar;
  - abrir a pasta do cliente e a OS atual.

Pasta criada à mão no Explorer aparece sozinha (a lista relê a cada 15 s),
como cliente "sem configuração".

A lógica toda está em clientes.py e checklist_etiquetas.py; aqui é só tela —
é o que vai pro executável sem mudar nada.
"""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import caminhos
import clientes
from gui import (
    COR_ACENTO, COR_ALERTA, COR_BORDA_CARTAO, COR_CARTAO, COR_FUNDO_JANELA,
    COR_POSITIVO, COR_TEXTO, COR_TEXTO_SECUNDARIO,
)

_INTERVALO_RELEITURA_MS = 15000


def _abrir(caminho):
    try:
        os.startfile(str(caminho))
        return None
    except OSError as e:
        return str(e)


def _ligar_botao(botao, ligado):
    """Botão cheio desligado continua parecendo clicável no Tk — apaga a cor junto."""
    if ligado:
        botao.configure(state="normal", bg=COR_ACENTO, fg="white", cursor="hand2")
    else:
        botao.configure(state="disabled", bg=COR_BORDA_CARTAO, disabledforeground=COR_TEXTO_SECUNDARIO,
                        cursor="arrow")


class JanelaClientes(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Clientes — UNY CV")
        self.configure(bg=COR_FUNDO_JANELA)
        self.geometry("820x700")
        self.minsize(600, 420)

        self._cartoes = {}
        self._gerando = set()
        self._job = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._montar_cabecalho()
        self._montar_lista()
        self._reler()
        self.bind("<Destroy>", self._ao_fechar)

    # ------------------------------------------------------------ montagem

    def _montar_cabecalho(self):
        topo = tk.Frame(self, bg=COR_FUNDO_JANELA)
        topo.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 10))
        topo.columnconfigure(0, weight=1)

        tk.Label(topo, text="Clientes", font=("Segoe UI", 15, "bold"),
                 bg=COR_FUNDO_JANELA, fg=COR_TEXTO).grid(row=0, column=0, sticky="w")
        tk.Label(topo, text="Cada cliente é uma pasta em Recebimento de Artes. Vários ao mesmo tempo.",
                 font=("Segoe UI", 9), bg=COR_FUNDO_JANELA, fg=COR_TEXTO_SECUNDARIO,
                 ).grid(row=1, column=0, sticky="w")

        acoes = tk.Frame(topo, bg=COR_FUNDO_JANELA)
        acoes.grid(row=0, column=1, rowspan=2, sticky="e")
        tk.Button(acoes, text="➕  Novo cliente", bg=COR_ACENTO, fg="white",
                  activebackground=COR_ACENTO, activeforeground="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2", padx=12, pady=4,
                  command=self._novo_cliente).pack(anchor="e")
        tk.Button(acoes, text="📂 Abrir Recebimento de Artes", relief="flat", bg=COR_FUNDO_JANELA,
                  fg=COR_ACENTO, cursor="hand2", font=("Segoe UI", 8),
                  command=lambda: _abrir(caminhos.RECEBIMENTO_DE_ARTES)).pack(anchor="e", pady=(4, 0))

    def _montar_lista(self):
        # mesmo esquema do Controle de Estoque e dos Agentes
        frame_canvas = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_canvas.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        frame_canvas.columnconfigure(0, weight=1)
        frame_canvas.rowconfigure(0, weight=1)
        canvas = tk.Canvas(frame_canvas, highlightthickness=0, bg=COR_FUNDO_JANELA)
        scrollbar = ttk.Scrollbar(frame_canvas, orient="vertical", command=canvas.yview)
        self.frame_lista = tk.Frame(canvas, bg=COR_FUNDO_JANELA)
        janela_interna = canvas.create_window((0, 0), window=self.frame_lista, anchor="nw")
        self.frame_lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_interna, width=e.width))
        self.frame_lista.columnconfigure(0, weight=1)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def _reler(self):
        """Relê a pasta. Refaz os cartões só se a lista de clientes mudou."""
        lista = clientes.listar()
        nomes = [c.nome for c in lista]
        if nomes != list(self._cartoes):
            for filho in self.frame_lista.winfo_children():
                filho.destroy()
            self._cartoes = {}
            if not lista:
                tk.Label(self.frame_lista, bg=COR_FUNDO_JANELA, fg=COR_TEXTO_SECUNDARIO,
                         font=("Segoe UI", 10), justify="left",
                         text="Nenhum cliente ainda.\n\nClique em \"Novo cliente\", ou crie uma pasta com o "
                              "nome do cliente dentro de Recebimento de Artes.",
                         ).grid(row=0, column=0, sticky="w", pady=20)
            for c in lista:
                self._montar_cartao(c)
        for c in lista:
            self._atualizar_cartao(c)
        self._job = self.after(_INTERVALO_RELEITURA_MS, self._reler)

    def _montar_cartao(self, cliente):
        cartao = tk.Frame(self.frame_lista, bg=COR_CARTAO,
                          highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        cartao.grid(row=len(self._cartoes), column=0, sticky="ew", pady=(0, 10))
        cartao.columnconfigure(0, weight=1)

        tk.Label(cartao, text=cliente.nome, font=("Segoe UI", 12, "bold"), bg=COR_CARTAO,
                 fg=COR_TEXTO, anchor="w").grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))

        links = tk.Frame(cartao, bg=COR_CARTAO)
        links.grid(row=0, column=1, sticky="e", padx=14, pady=(12, 0))
        tk.Button(links, text="📂 Pasta do cliente", relief="flat", bg=COR_CARTAO, fg=COR_ACENTO,
                  cursor="hand2", font=("Segoe UI", 8),
                  command=lambda n=cliente.nome: self._abrir_pasta_cliente(n)).pack(side="left")
        btn_os = tk.Button(links, text="📄 OS atual", relief="flat", bg=COR_CARTAO, fg=COR_ACENTO,
                           cursor="hand2", font=("Segoe UI", 8),
                           command=lambda n=cliente.nome: self._abrir_os(n))
        btn_os.pack(side="left", padx=(6, 0))

        var_producao = tk.StringVar()
        lbl_producao = tk.Label(cartao, textvariable=var_producao, font=("Segoe UI", 9), bg=COR_CARTAO,
                                fg=COR_TEXTO_SECUNDARIO, anchor="w", justify="left", wraplength=620)
        lbl_producao.grid(row=1, column=0, sticky="w", padx=16, pady=(4, 0))
        tk.Button(cartao, text="Escolher pasta de produção...", relief="flat", bg=COR_CARTAO,
                  fg=COR_ACENTO, cursor="hand2", font=("Segoe UI", 8),
                  command=lambda n=cliente.nome: self._escolher_producao(n),
                  ).grid(row=1, column=1, sticky="e", padx=14, pady=(4, 0))

        var_checklist = tk.BooleanVar()
        chk = tk.Checkbutton(cartao, text="Checklist automático — a OS se atualiza sozinha a cada movimento",
                             variable=var_checklist, bg=COR_CARTAO, activebackground=COR_CARTAO,
                             fg=COR_TEXTO, font=("Segoe UI", 9), anchor="w",
                             command=lambda n=cliente.nome: self._alternar_checklist(n))
        chk.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(6, 0))

        ttk.Separator(cartao).grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 0))

        var_etiquetas = tk.StringVar()
        lbl_etiquetas = tk.Label(cartao, textvariable=var_etiquetas, font=("Segoe UI", 10), bg=COR_CARTAO,
                                 fg=COR_TEXTO, anchor="w", justify="left", wraplength=560)
        lbl_etiquetas.grid(row=4, column=0, sticky="w", padx=16, pady=(8, 12))
        btn_lote = tk.Button(cartao, text="🏷  Gerar checklist das novas", bg=COR_ACENTO, fg="white",
                             activebackground=COR_ACENTO, activeforeground="white", relief="flat",
                             font=("Segoe UI", 9, "bold"), cursor="hand2", padx=10, pady=3,
                             command=lambda n=cliente.nome: self._gerar_lote(n))
        btn_lote.grid(row=4, column=1, sticky="e", padx=14, pady=(8, 12))

        self._cartoes[cliente.nome] = {
            "var_producao": var_producao, "lbl_producao": lbl_producao,
            "var_checklist": var_checklist, "chk": chk, "btn_os": btn_os,
            "var_etiquetas": var_etiquetas, "lbl_etiquetas": lbl_etiquetas, "btn_lote": btn_lote,
        }

    def _atualizar_cartao(self, cliente):
        import checklist_etiquetas
        import vigia_checklist

        c = self._cartoes.get(cliente.nome)
        if c is None:
            return

        if cliente.pasta_producao is None:
            c["var_producao"].set("⚠ Sem pasta de produção — escolha pra poder ligar o checklist e gerar etiquetas.")
            c["lbl_producao"].configure(fg=COR_ALERTA)
        elif not cliente.producao_existe:
            c["var_producao"].set("⚠ A pasta de produção não existe mais: %s"
                                  % caminhos.relativo_ao_onedrive(cliente.pasta_producao))
            c["lbl_producao"].configure(fg=COR_ALERTA)
        else:
            c["var_producao"].set("Produção: %s" % caminhos.relativo_ao_onedrive(cliente.pasta_producao))
            c["lbl_producao"].configure(fg=COR_TEXTO_SECUNDARIO)

        c["var_checklist"].set(cliente.checklist_ativo)
        c["chk"].configure(state="normal" if cliente.producao_existe else "disabled")
        c["btn_os"].configure(state="normal" if vigia_checklist.destino_pdf(cliente).is_file() else "disabled")

        if cliente.nome in self._gerando:
            return                          # o cartão está mostrando o andamento do lote
        if not cliente.producao_existe:
            c["var_etiquetas"].set("Etiquetas: sem pasta de produção.")
            c["lbl_etiquetas"].configure(fg=COR_TEXTO_SECUNDARIO)
            _ligar_botao(c["btn_lote"], False)
            return
        novas = len(checklist_etiquetas.artes_novas_do_cliente(cliente))
        if novas:
            c["var_etiquetas"].set("🏷 %d arte%s nova%s sem etiqueta desde o último checklist."
                                   % (novas, "s" if novas != 1 else "", "s" if novas != 1 else ""))
            c["lbl_etiquetas"].configure(fg=COR_ALERTA)
            _ligar_botao(c["btn_lote"], True)
        else:
            c["var_etiquetas"].set("✓ Todas as artes da produção já têm etiqueta.")
            c["lbl_etiquetas"].configure(fg=COR_POSITIVO)
            _ligar_botao(c["btn_lote"], False)

    # ------------------------------------------------------------- ações

    def _recarregar_agora(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        self._reler()

    def _abrir_pasta_cliente(self, nome):
        cliente = clientes.obter(nome)
        if cliente:
            _abrir(cliente.pasta)

    def _abrir_os(self, nome):
        import vigia_checklist
        cliente = clientes.obter(nome)
        if cliente and vigia_checklist.destino_pdf(cliente).is_file():
            _abrir(vigia_checklist.destino_pdf(cliente))

    def _escolher_producao(self, nome):
        cliente = clientes.obter(nome)
        if cliente is None:
            return
        inicial = cliente.pasta_producao if cliente.producao_existe else caminhos.EVENTOS
        pasta = filedialog.askdirectory(parent=self, title="Pasta de produção de %s" % nome,
                                        initialdir=str(inicial))
        if not pasta:
            return
        primeira_vez = cliente.pasta_producao is None
        cliente.pasta_producao = caminhos.resolver_do_onedrive(caminhos.relativo_ao_onedrive(pasta))
        if primeira_vez:
            cliente.checklist_ativo = True  # cadastrou a produção: é pra acompanhar
        clientes.salvar(cliente)
        self._recarregar_agora()

    def _alternar_checklist(self, nome):
        cliente = clientes.obter(nome)
        if cliente is None:
            return
        cliente.checklist_ativo = bool(self._cartoes[nome]["var_checklist"].get()) and cliente.producao_existe
        clientes.salvar(cliente)
        self._recarregar_agora()

    def _gerar_lote(self, nome):
        import checklist_etiquetas

        cliente = clientes.obter(nome)
        if cliente is None or nome in self._gerando:
            return
        novas = len(checklist_etiquetas.artes_novas_do_cliente(cliente))
        if not novas:
            return
        if not messagebox.askyesno(
                "Gerar checklist", "Gerar o checklist de etiquetas de %s com %d arte%s nova%s?\n\n"
                                   "Sai uma pasta nova em etiquetas_geradas, só com essas etiquetas."
                                   % (nome, novas, "s" if novas != 1 else "", "s" if novas != 1 else ""),
                parent=self):
            return

        self._gerando.add(nome)
        c = self._cartoes[nome]
        _ligar_botao(c["btn_lote"], False)
        c["var_etiquetas"].set("Gerando o checklist de %d etiqueta%s..." % (novas, "s" if novas != 1 else ""))
        c["lbl_etiquetas"].configure(fg=COR_ACENTO)

        def andamento(nivel, texto):
            if nivel in ("ok", "info") and texto:
                self.after(0, lambda t=texto: self._mostrar_andamento(nome, t))

        def trabalho():
            try:
                r = checklist_etiquetas.gerar_lote_do_cliente(cliente, on_log=andamento)
            except Exception as e:
                r = {"gerou": False, "motivo": "erro: %s" % e}
            self.after(0, lambda: self._fim_do_lote(nome, r))

        threading.Thread(target=trabalho, daemon=True).start()

    def _mostrar_andamento(self, nome, texto):
        if nome in self._gerando and nome in self._cartoes and self.winfo_exists():
            self._cartoes[nome]["var_etiquetas"].set("Gerando... %s" % texto[:110])

    def _fim_do_lote(self, nome, resultado):
        if not self.winfo_exists():
            return
        self._gerando.discard(nome)
        if resultado.get("gerou"):
            if messagebox.askyesno("Checklist pronto",
                                   "Checklist com %d etiqueta%s gerado.\n\nAbrir a pasta agora?"
                                   % (resultado["quantidade"], "s" if resultado["quantidade"] != 1 else ""),
                                   parent=self):
                _abrir(resultado["pasta_saida"])
        else:
            messagebox.showwarning("Checklist não gerado", resultado.get("motivo") or "sem motivo", parent=self)
        self._recarregar_agora()

    def _novo_cliente(self):
        JanelaNovoCliente(self, ao_criar=lambda _c: self._recarregar_agora())

    def _ao_fechar(self, evento):
        if evento.widget is self and self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None


class JanelaNovoCliente(tk.Toplevel):
    """Formulário curto: nome, pasta de produção (sugerida sozinha) e checklist."""

    def __init__(self, master, ao_criar):
        super().__init__(master)
        self.title("Novo cliente")
        self.configure(bg=COR_FUNDO_JANELA)
        self.resizable(False, False)
        self.transient(master)
        self._ao_criar = ao_criar
        self._producao_sugerida = False
        self._job_sugestao = None

        corpo = tk.Frame(self, bg=COR_FUNDO_JANELA)
        corpo.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(corpo, text="Nome do cliente", bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.var_nome = tk.StringVar()
        entrada = tk.Entry(corpo, textvariable=self.var_nome, width=52, font=("Segoe UI", 10))
        entrada.pack(anchor="w", fill="x", pady=(2, 0))
        tk.Label(corpo, text="Vira a pasta em Recebimento de Artes.", bg=COR_FUNDO_JANELA,
                 fg=COR_TEXTO_SECUNDARIO, font=("Segoe UI", 8)).pack(anchor="w")
        self.var_nome.trace_add("write", lambda *_: self._agendar_sugestao())

        tk.Label(corpo, text="Pasta de produção", bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(12, 0))
        linha = tk.Frame(corpo, bg=COR_FUNDO_JANELA)
        linha.pack(anchor="w", fill="x", pady=(2, 0))
        self.var_producao = tk.StringVar()
        tk.Entry(linha, textvariable=self.var_producao, width=42, font=("Segoe UI", 9)).pack(
            side="left", fill="x", expand=True)
        tk.Button(linha, text="Procurar...", command=self._procurar).pack(side="left", padx=(6, 0))
        self.var_dica = tk.StringVar(value="Opcional agora — dá pra escolher depois no cartão do cliente.")
        tk.Label(corpo, textvariable=self.var_dica, bg=COR_FUNDO_JANELA, fg=COR_TEXTO_SECUNDARIO,
                 font=("Segoe UI", 8)).pack(anchor="w")

        self.var_checklist = tk.BooleanVar(value=True)
        tk.Checkbutton(corpo, text="Ligar o checklist automático (OS atualizada a cada movimento)",
                       variable=self.var_checklist, bg=COR_FUNDO_JANELA, activebackground=COR_FUNDO_JANELA,
                       font=("Segoe UI", 9)).pack(anchor="w", pady=(12, 0))

        self.var_erro = tk.StringVar()
        tk.Label(corpo, textvariable=self.var_erro, bg=COR_FUNDO_JANELA, fg=COR_ALERTA,
                 font=("Segoe UI", 9), wraplength=420, justify="left").pack(anchor="w", pady=(10, 0))

        botoes = tk.Frame(corpo, bg=COR_FUNDO_JANELA)
        botoes.pack(anchor="e", pady=(10, 0))
        tk.Button(botoes, text="Cancelar", relief="flat", command=self.destroy).pack(side="left")
        tk.Button(botoes, text="Criar cliente", bg=COR_ACENTO, fg="white", activebackground=COR_ACENTO,
                  activeforeground="white", relief="flat", font=("Segoe UI", 9, "bold"), padx=12, pady=3,
                  cursor="hand2", command=self._criar).pack(side="left", padx=(8, 0))

        self.bind("<Return>", lambda e: self._criar())
        self.bind("<Escape>", lambda e: self.destroy())
        entrada.focus_set()
        self.grab_set()

    def _agendar_sugestao(self):
        if self._job_sugestao is not None:
            self.after_cancel(self._job_sugestao)
        self._job_sugestao = self.after(400, self._sugerir)

    def _sugerir(self):
        self._job_sugestao = None
        if self.var_producao.get() and not self._producao_sugerida:
            return                          # o usuário escolheu à mão: não sobrescreve
        sugestao = clientes.sugerir_pasta_producao(self.var_nome.get())
        if sugestao:
            self.var_producao.set(str(sugestao))
            self._producao_sugerida = True
            self.var_dica.set("Sugerida pelo nome — confira. %s" % caminhos.relativo_ao_onedrive(sugestao))
        elif self._producao_sugerida:
            self.var_producao.set("")
            self._producao_sugerida = False
            self.var_dica.set("Opcional agora — dá pra escolher depois no cartão do cliente.")

    def _procurar(self):
        pasta = filedialog.askdirectory(parent=self, title="Pasta de produção", initialdir=str(caminhos.EVENTOS))
        if pasta:
            self.var_producao.set(pasta)
            self._producao_sugerida = False
            self.var_dica.set("Escolhida por você.")

    def _criar(self):
        try:
            cliente = clientes.criar(self.var_nome.get(), pasta_producao=self.var_producao.get() or None,
                                     checklist_ativo=self.var_checklist.get())
        except clientes.ErroCliente as e:
            self.var_erro.set(str(e))
            return
        self.destroy()
        self._ao_criar(cliente)
