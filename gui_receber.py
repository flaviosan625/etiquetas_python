"""
Janela "Receber artes" — de um link do Drive ou do WeTransfer, de uma
pasta ou de um ZIP, até ARTES do cliente, em dois passos.

Pedidos do usuário que desenharam esta tela (2026-09-21):
  - "os links podem ser do Google Drive, OneDrive, WeTransfer etc.";
  - "essa prévia onde eu possa demarcar o que eu realmente quero que
    baixe" — PASSO 1, com a miniatura de cada arte ANTES de baixar;
  - "preciso informar o cliente e a pasta" — e a pasta do cliente nasce
    do nome digitado;
  - "todos os formatos que trabalhamos, sem limitações";
  - sem especificação: 1 unidade e A DEFINIR, sem perguntar; a medida da
    arte vale sempre.

PASSO 1 — escolher: a origem como ela está, pasta por pasta, com a
miniatura de cada arquivo. Vem marcado tudo que é arte (e o .ai de
trabalho); prévia exportada e mockup, desmarcados; o que já foi recebido,
desmarcado e sinalizado. Nada é baixado antes do botão.

PASSO 2 — conferir e arquivar: cada arte com a medida lida dela, a marca
de corte, o nome que vai ter. Ele muda descrição, material e quantidade;
o [+] faz a mesma arte servir outra peça. Arquivar tira a marca de corte
(Illustrator), confere e grava — nada é sobrescrito.

Toda a lógica está em origem_artes, receber_artes e clientes; aqui é só
tela. O trabalho pesado roda em segundo plano e devolve o resultado pela
fila (_na_tela): o Tk não pode ser mexido de outra thread.
"""
import concurrent.futures
import io
import os
import pathlib
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import caderno_arte
import caminhos
import clientes
import origem_artes as oa
import receber_artes as ra
from branding import CAMINHO_LOGO_GUI
from config import carregar_config
from gui import (
    COR_ACENTO, COR_ALERTA, COR_ALERTA_FUNDO, COR_BORDA_CARTAO, COR_CARTAO, COR_FUNDO_JANELA,
    COR_POSITIVO, COR_RIP_PARADO, COR_TEXTO, COR_TEXTO_SECUNDARIO,
)
from utils import sanitizar_nome_arquivo

COR_MARCADO = "#e8f1fb"
COR_PREVIA_FUNDO = "#eef1f4"
TAMANHO_TILE = (150, 92)
TAMANHO_LINHA = (72, 50)
COLUNAS_GRUPOS = 2
TILES_POR_LINHA = 3
_ORDEM_EXT = ("PDF", "TIF", "TIFF", "PSD", "EPS", "AI", "PNG", "JPG", "JPEG")


def _mb(n):
    return ("%.1f MB" % (n / 1024 ** 2)).replace(".", ",")


def _m2(medida, quantidade):
    return medida[0] * medida[1] * quantidade if medida else 0.0


def _abrir(caminho):
    try:
        os.startfile(str(caminho))
    except OSError as e:
        messagebox.showerror("Não abriu", str(e))


class _Rolavel(tk.Frame):
    """Área com barra de rolagem; a rodinha é repassada pela janela."""

    def __init__(self, pai, bg):
        super().__init__(pai, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.dentro = tk.Frame(self.canvas, bg=bg)
        janela = self.canvas.create_window((0, 0), window=self.dentro, anchor="nw")
        self.dentro.bind("<Configure>",
                         lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(janela, width=e.width))
        self.canvas.configure(yscrollcommand=barra.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

    def rolar(self, evento):
        self.canvas.yview_scroll(int(-evento.delta / 120), "units")


class JanelaReceber(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Receber artes — UNY CV")
        self.configure(bg=COR_FUNDO_JANELA)
        altura = min(900, self.winfo_screenheight() - 90)
        largura = min(1280, self.winfo_screenwidth() - 40)
        self.geometry("%dx%d+20+10" % (largura, altura))
        self.minsize(980, 620)

        self.config_dados = carregar_config()
        self.materiais = [caderno_arte.MATERIAL_A_DEFINIR] + list(self.config_dados["materiais"])
        self._fila = queue.Queue()
        self._trabalho = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._miniaturas = concurrent.futures.ThreadPoolExecutor(max_workers=6)
        self._fechando = False
        self._imagens = []
        self._rolavel = None
        self._destino_escolhido = None

        self.origem = None
        self.lote = None
        self.itens = []
        self.marcas = {}
        self.pecas = []
        self.recebidos = {}

        self._montar_topo()
        self._montar_origem()
        self.area = tk.Frame(self, bg=COR_FUNDO_JANELA)
        self.area.pack(fill="both", expand=True)
        self._mostrar_inicio()

        self.bind("<MouseWheel>", self._rodinha)
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self._bombear()
        self._no_fundo(oa.limpar_lotes_velhos)

    # ================================================================ infra

    def _na_tela(self, funcao, *args):
        self._fila.put((funcao, args))

    def _bombear(self):
        if self._fechando:
            return
        try:
            while True:
                funcao, args = self._fila.get_nowait()
                try:
                    funcao(*args)
                except tk.TclError:
                    pass   # widget de uma tela que já foi trocada
        except queue.Empty:
            pass
        self.after(60, self._bombear)

    def _no_fundo(self, trabalho, ao_terminar=None, ao_falhar=None, executor=None):
        def rodar():
            try:
                resultado = trabalho()
            except Exception as e:   # noqa: BLE001 — a tela mostra, não engole
                if not self._fechando:
                    self._na_tela(ao_falhar or self._falhou, e)
                return
            if ao_terminar and not self._fechando:
                self._na_tela(ao_terminar, resultado)
        (executor or self._trabalho).submit(rodar)

    def _falhou(self, erro):
        self._status(str(erro), "erro")
        self._ocupado(False)

    def _fechar(self):
        self._fechando = True
        self._trabalho.shutdown(wait=False, cancel_futures=True)
        self._miniaturas.shutdown(wait=False, cancel_futures=True)
        if self.origem:
            try:
                self.origem.fechar()
            except Exception:
                pass
        self.destroy()

    def _rodinha(self, evento):
        if self._rolavel is not None:
            self._rolavel.rolar(evento)
        return "break"

    def _sem_rodinha(self, widget):
        """Combobox e Spinbox trocam de valor com a rodinha: aqui ela só rola a lista."""
        widget.bind("<MouseWheel>", self._rodinha)
        return widget

    def _foto(self, dados, tamanho):
        if not dados:
            return None
        try:
            from PIL import Image, ImageTk
            with Image.open(io.BytesIO(dados)) as im:
                img = im.convert("RGB")
            img.thumbnail(tamanho)
            fundo = Image.new("RGB", tamanho, COR_PREVIA_FUNDO)
            fundo.paste(img, ((tamanho[0] - img.width) // 2, (tamanho[1] - img.height) // 2))
            foto = ImageTk.PhotoImage(fundo)
            self._imagens.append(foto)
            return foto
        except Exception:
            return None

    # ========================================================= parte fixa

    def _montar_topo(self):
        topo = tk.Frame(self, bg=COR_FUNDO_JANELA)
        topo.pack(fill="x", padx=18, pady=(12, 4))
        if CAMINHO_LOGO_GUI.exists():
            try:
                from PIL import Image, ImageTk
                im = Image.open(CAMINHO_LOGO_GUI)
                im.thumbnail((110, 36))
                self._logo = ImageTk.PhotoImage(im)
                tk.Label(topo, image=self._logo, bg=COR_FUNDO_JANELA).pack(side="left", padx=(0, 12))
            except Exception:
                pass
        caixa = tk.Frame(topo, bg=COR_FUNDO_JANELA)
        caixa.pack(side="left")
        tk.Label(caixa, text="Receber artes", font=("Segoe UI", 15, "bold"),
                 bg=COR_FUNDO_JANELA, fg=COR_TEXTO).pack(anchor="w")
        self.var_passo = tk.StringVar(value="Cole o link ou escolha a pasta/ZIP, e clique em Ler origem.")
        tk.Label(caixa, textvariable=self.var_passo, font=("Segoe UI", 9),
                 bg=COR_FUNDO_JANELA, fg=COR_TEXTO_SECUNDARIO).pack(anchor="w")

    def _montar_origem(self):
        c = tk.Frame(self, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        c.pack(fill="x", padx=18, pady=(4, 6))

        l0 = tk.Frame(c, bg=COR_CARTAO)
        l0.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(l0, text="Cliente", font=("Segoe UI", 9, "bold"), bg=COR_CARTAO,
                 fg=COR_TEXTO, width=10, anchor="w").pack(side="left")
        self.var_cliente = tk.StringVar()
        nomes = [cl.nome for cl in clientes.listar()]
        self.combo_cliente = ttk.Combobox(l0, textvariable=self.var_cliente, values=nomes,
                                          width=30, font=("Segoe UI", 10))
        self.combo_cliente.pack(side="left", padx=(0, 10))
        self._sem_rodinha(self.combo_cliente)
        self.lbl_cliente = tk.Label(l0, text="", font=("Segoe UI", 8, "bold"), bg=COR_CARTAO, anchor="w")
        self.lbl_cliente.pack(side="left")

        l1 = tk.Frame(c, bg=COR_CARTAO)
        l1.pack(fill="x", padx=14, pady=(6, 4))
        tk.Label(l1, text="Origem", font=("Segoe UI", 9, "bold"), bg=COR_CARTAO,
                 fg=COR_TEXTO, width=10, anchor="w").pack(side="left")
        self.var_origem = tk.StringVar()
        e = tk.Entry(l1, textvariable=self.var_origem, font=("Segoe UI", 9), width=70,
                     relief="solid", bd=1)
        e.pack(side="left", ipady=3)
        e.bind("<Return>", lambda ev: self._ler_origem())
        tk.Button(l1, text="Pasta...", font=("Segoe UI", 9), relief="solid", bd=1, bg=COR_CARTAO,
                  fg=COR_TEXTO, padx=8, pady=1, cursor="hand2",
                  command=self._escolher_pasta).pack(side="left", padx=(6, 2))
        tk.Button(l1, text="ZIP...", font=("Segoe UI", 9), relief="solid", bd=1, bg=COR_CARTAO,
                  fg=COR_TEXTO, padx=8, pady=1, cursor="hand2",
                  command=self._escolher_zip).pack(side="left", padx=2)
        self.btn_ler = tk.Button(l1, text="Ler origem", bg=COR_ACENTO, fg="white",
                                 font=("Segoe UI", 10, "bold"), relief="flat", padx=16, pady=3,
                                 cursor="hand2", command=self._ler_origem)
        self.btn_ler.pack(side="left", padx=6)
        tk.Label(c, text="   Google Drive e WeTransfer pelo link  ·  OneDrive sincronizado, pendrive e "
                         "ZIP baixado pelo navegador, por Pasta... ou ZIP...",
                 font=("Segoe UI", 7), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO).pack(anchor="w", padx=14)

        l2 = tk.Frame(c, bg=COR_CARTAO)
        l2.pack(fill="x", padx=14, pady=(6, 10))
        tk.Label(l2, text="Área", font=("Segoe UI", 9, "bold"), bg=COR_CARTAO,
                 fg=COR_TEXTO, width=10, anchor="w").pack(side="left")
        self.var_area = tk.StringVar()
        tk.Entry(l2, textvariable=self.var_area, font=("Segoe UI", 9), width=24,
                 relief="solid", bd=1).pack(side="left", ipady=3)
        tk.Label(l2, text="  vai na pasta e na frente do nome   Guardar em ", font=("Segoe UI", 8),
                 bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO).pack(side="left")
        self.lbl_destino = tk.Label(l2, text="", font=("Segoe UI", 9), bg=COR_CARTAO, fg=COR_TEXTO)
        self.lbl_destino.pack(side="left")
        tk.Button(l2, text="Mudar...", font=("Segoe UI", 8), relief="solid", bd=1, bg=COR_CARTAO,
                  fg=COR_TEXTO, padx=8, pady=1, cursor="hand2",
                  command=self._mudar_destino).pack(side="left", padx=8)

        self.var_cliente.trace_add("write", lambda *a: self._atualizar_cliente())
        self.var_area.trace_add("write", lambda *a: self._atualizar_destino())
        self._atualizar_cliente()

    # ------------------------------------------------------ cliente/destino

    def _atualizar_cliente(self):
        situacao, dado = clientes.situacao_do_nome(self.var_cliente.get())
        textos = {
            "vazio": ("digite o nome do cliente — a pasta dele nasce desse nome", COR_ALERTA),
            "invalido": (dado, COR_RIP_PARADO),
            "existe": ('cliente já cadastrado — usa a pasta dele' if dado and dado.nome == self.var_cliente.get().strip()
                       else 'é o cliente "%s" (já existe) — usa a pasta dele' % (dado.nome if dado else ""),
                       COR_POSITIVO),
            "parecido": ('parece com "%s", que já existe — vou perguntar antes de arquivar'
                         % (dado.nome if dado else ""), COR_ALERTA),
            "novo": ("cliente NOVO — a pasta Recebimento de Artes\\%s nasce ao arquivar"
                     % self.var_cliente.get().strip(), COR_ACENTO),
        }
        texto, cor = textos[situacao]
        self.lbl_cliente.configure(text=texto, fg=cor)
        self._atualizar_destino()

    def _pasta_do_cliente(self):
        situacao, dado = clientes.situacao_do_nome(self.var_cliente.get())
        if situacao == "existe":
            return dado.pasta
        nome = self.var_cliente.get().strip()
        return caminhos.RECEBIMENTO_DE_ARTES / (nome or "(digite o cliente)")

    def _destino(self):
        if self._destino_escolhido:
            return self._destino_escolhido
        area = sanitizar_nome_arquivo(self.var_area.get().strip()) if self.var_area.get().strip() else ""
        destino = self._pasta_do_cliente() / "ARTES"
        return destino / area if area else destino

    def _atualizar_destino(self):
        destino = self._destino()
        try:
            texto = str(destino.relative_to(caminhos.ONEDRIVE_UNY))
        except ValueError:
            texto = str(destino)
        self.lbl_destino.configure(text=texto + ("   (escolhido à mão)" if self._destino_escolhido else ""))
        if self.pecas and hasattr(self, "_linhas"):
            self._verificar_nomes()

    def _mudar_destino(self):
        inicio = self._destino() if self._destino().exists() else caminhos.RECEBIMENTO_DE_ARTES
        pasta = filedialog.askdirectory(parent=self, title="Onde guardar as artes", initialdir=str(inicio))
        if pasta:
            self._destino_escolhido = pathlib.Path(pasta)
            self._atualizar_destino()

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(parent=self, title="Pasta com as artes")
        if pasta:
            self.var_origem.set(pasta)
            self._ler_origem()

    def _escolher_zip(self):
        arquivo = filedialog.askopenfilename(parent=self, title="ZIP com as artes",
                                             filetypes=[("ZIP", "*.zip"), ("Todos", "*.*")])
        if arquivo:
            self.var_origem.set(arquivo)
            self._ler_origem()

    # ============================================================ estados

    def _limpar_area(self):
        for w in self.area.winfo_children():
            w.destroy()
        self._rolavel = None
        self._imagens = []

    def _status(self, texto, nivel="info"):
        cor = {"info": COR_TEXTO_SECUNDARIO, "ok": COR_POSITIVO, "aviso": COR_ALERTA,
               "erro": COR_RIP_PARADO}[nivel]
        if hasattr(self, "lbl_status") and self.lbl_status.winfo_exists():
            self.lbl_status.configure(text=texto, fg=cor)
        else:
            self.var_passo.set(texto)

    def _ocupado(self, sim):
        self.btn_ler.configure(state="disabled" if sim else "normal")
        self.configure(cursor="watch" if sim else "")

    def _mostrar_inicio(self):
        self._limpar_area()
        caixa = tk.Frame(self.area, bg=COR_FUNDO_JANELA)
        caixa.pack(fill="both", expand=True, padx=18)
        self.lbl_status = tk.Label(caixa, text="", font=("Segoe UI", 10), bg=COR_FUNDO_JANELA,
                                   fg=COR_TEXTO_SECUNDARIO, wraplength=900, justify="left")
        self.lbl_status.pack(anchor="w", pady=(20, 6))
        tk.Label(caixa, text=(
            "1. Digite o cliente (existe ou novo — a pasta nasce do nome).\n"
            "2. Cole o link do Drive ou do WeTransfer, ou escolha uma pasta ou um ZIP.\n"
            "3. Ler origem: aparece a prévia de cada arte. Nada é baixado antes de você marcar."),
            font=("Segoe UI", 10), bg=COR_FUNDO_JANELA, fg=COR_TEXTO, justify="left").pack(anchor="w")

    # ============================================================ passo 1

    def _ler_origem(self):
        texto = self.var_origem.get().strip()
        if not texto:
            messagebox.showinfo("Receber artes", "Cole um link ou escolha uma pasta ou ZIP.", parent=self)
            return
        self._ocupado(True)
        self._mostrar_inicio()
        self._status("Lendo a origem... (link do Drive pode abrir o login do Google no navegador)")
        if self.origem:
            try:
                self.origem.fechar()
            except Exception:
                pass
        self.origem = None
        self.pecas = []
        self._destino_escolhido = None
        lote = oa.novo_lote()

        def ler():
            origem = oa.abrir(texto, pasta_espera=lote)
            return origem, origem.listar()

        def pronto(resultado):
            self.origem, self.itens = resultado
            self.lote = lote
            if not self.var_area.get().strip() and self.origem.area_sugerida:
                self.var_area.set(self.origem.area_sugerida)
            self._ocupado(False)
            self._mostrar_passo1()

        self._no_fundo(ler, pronto)

    def _mostrar_passo1(self):
        self._limpar_area()
        self.var_passo.set("Passo 1 de 2 — veja as artes e marque o que baixa. Nada é baixado antes do botão.")
        situacao, dado = clientes.situacao_do_nome(self.var_cliente.get())
        self.recebidos = ra.ja_recebidos(dado) if situacao == "existe" else {}

        cab = tk.Frame(self.area, bg=COR_FUNDO_JANELA)
        cab.pack(fill="x", padx=18, pady=(2, 2))
        grupos = oa.agrupar(self.itens)
        tk.Label(cab, text="%s     %d arquivos em %d pasta%s" % (
            self.origem.rotulo, len(self.itens), len(grupos), "s" if len(grupos) != 1 else ""),
            font=("Segoe UI", 10, "bold"), bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
            anchor="w", wraplength=1150, justify="left").pack(fill="x")
        extras = []
        if self.origem.aviso:
            extras.append(self.origem.aviso)
        if self.origem.ignorados:
            extras.append("%d item(ns) ficaram de fora: %s" % (
                len(self.origem.ignorados), ", ".join("%s (%s)" % i for i in self.origem.ignorados[:3])))
        for texto in extras:
            tk.Label(cab, text=texto, font=("Segoe UI", 8), bg=COR_FUNDO_JANELA, fg=COR_ALERTA,
                     anchor="w", wraplength=1150, justify="left").pack(fill="x")
        if not self.itens:
            tk.Label(self.area, text="A origem não tem arquivo nenhum.", font=("Segoe UI", 11),
                     bg=COR_FUNDO_JANELA, fg=COR_ALERTA).pack(pady=40)
            return

        self._montar_rodape_passo1()
        self._rolavel = _Rolavel(self.area, COR_FUNDO_JANELA)
        self._rolavel.pack(fill="both", expand=True, padx=18, pady=(2, 4))
        grade = self._rolavel.dentro
        # uma pasta só (o ZIP do Mandarin): ela usa a largura toda; várias
        # pastas de peça (o LANDMARK): duas colunas de cartões
        colunas = 1 if len(grupos) == 1 else COLUNAS_GRUPOS
        self._tiles_por_linha = 6 if colunas == 1 else TILES_POR_LINHA
        for col in range(colunas):
            grade.columnconfigure(col, weight=1, uniform="g")

        self.marcas = {}
        self._tiles = {}
        self._pedidos_de_previa = {}
        for i, (grupo, arquivos) in enumerate(grupos.items()):
            cartao = self._cartao_grupo(grade, grupo, arquivos)
            cartao.grid(row=i // colunas, column=i % colunas, padx=4, pady=4, sticky="nsew")
        self._atualizar_total()
        self._pedir_previas()

    def _cartao_grupo(self, pai, grupo, arquivos):
        cartao = tk.Frame(pai, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        topo = tk.Frame(cartao, bg=COR_CARTAO)
        topo.pack(fill="x", padx=10, pady=(7, 3))
        var_pasta = tk.BooleanVar()
        membros = []

        def marcar_pasta():
            for a in arquivos:
                self.marcas[a.id].set(var_pasta.get())
                self._pintar_tile(a.id)
            self._atualizar_total()

        tk.Checkbutton(topo, variable=var_pasta, bg=COR_CARTAO, activebackground=COR_CARTAO,
                       cursor="hand2", command=marcar_pasta).pack(side="left")
        tk.Label(topo, text=grupo or "(raiz da origem)", font=("Segoe UI", 10, "bold"),
                 bg=COR_CARTAO, fg=COR_TEXTO, anchor="w").pack(side="left")
        tk.Label(topo, text="  %d arquivo%s" % (len(arquivos), "s" if len(arquivos) != 1 else ""),
                 font=("Segoe UI", 8), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO).pack(side="left")

        corpo = tk.Frame(cartao, bg=COR_CARTAO)
        corpo.pack(fill="x", padx=10, pady=(0, 9))
        ordem = sorted(arquivos, key=lambda a: (_ORDEM_EXT.index(a.ext) if a.ext in _ORDEM_EXT else 99,
                                                a.nome.lower()))
        for j, a in enumerate(ordem):
            ja = ra.foi_recebido(self.origem.chave(a), self.recebidos)
            var = tk.BooleanVar(value=oa.marcado_por_padrao(a, arquivos) and not ja)
            self.marcas[a.id] = var
            membros.append(var)
            tile = self._tile(corpo, a, arquivos, var, ja)
            tile.grid(row=j // self._tiles_por_linha, column=j % self._tiles_por_linha,
                      padx=(0, 8), pady=(0, 6), sticky="nw")

        def refletir(*_):
            var_pasta.set(all(v.get() for v in membros))
        for v in membros:
            v.trace_add("write", refletir)
        refletir()
        return cartao

    def _tile(self, pai, arquivo, irmaos, var, ja_recebido):
        tile = tk.Frame(pai, bg=COR_CARTAO, highlightthickness=1, highlightbackground=COR_BORDA_CARTAO)
        previa = tk.Label(tile, text="carregando...", width=20, height=5, bg=COR_PREVIA_FUNDO,
                          fg=COR_TEXTO_SECUNDARIO, font=("Segoe UI", 7))
        previa.pack(padx=4, pady=(4, 2))
        base = tk.Frame(tile, bg=COR_CARTAO)
        base.pack(fill="x", padx=4)

        def trocou():
            self._pintar_tile(arquivo.id)
            self._atualizar_total()

        chk = tk.Checkbutton(base, variable=var, bg=COR_CARTAO, activebackground=COR_CARTAO,
                             cursor="hand2", command=trocou)
        chk.pack(side="left")
        tk.Label(base, text=arquivo.ext or "?", font=("Segoe UI", 9, "bold"), bg=COR_CARTAO,
                 fg=COR_ACENTO).pack(side="left")
        tk.Label(base, text=" " + _mb(arquivo.bytes), font=("Segoe UI", 8), bg=COR_CARTAO,
                 fg=COR_TEXTO_SECUNDARIO).pack(side="left")
        fonte, emprestada = oa.fonte_da_previa(arquivo, irmaos)
        papel = {"arte": "arte", "trabalho": "trabalho (.ai)", "previa": "prévia exportada",
                 "outro": "outro formato"}[oa.papel(arquivo, irmaos)]
        if emprestada:
            papel += " · prévia do " + fonte.ext
        rodape = tk.Label(tile, text=papel, font=("Segoe UI", 7), bg=COR_CARTAO,
                          fg=COR_ALERTA if emprestada else COR_TEXTO_SECUNDARIO, anchor="w")
        rodape.pack(fill="x", padx=6)
        # largura fixa: nome comprido não pode alargar o cartão e empurrar o vizinho pra fora
        nome = tk.Label(tile, text=arquivo.nome if len(arquivo.nome) <= 26 else arquivo.nome[:24] + "…",
                        font=("Segoe UI", 7), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO, anchor="w", width=26)
        nome.pack(fill="x", padx=6, pady=(0, 2))
        if ja_recebido:
            tk.Label(tile, text="já recebido", font=("Segoe UI", 7, "bold"), bg=COR_CARTAO,
                     fg=COR_POSITIVO, anchor="w").pack(fill="x", padx=6)
        if arquivo.na_nuvem:
            tk.Label(tile, text="só na nuvem — baixa se marcar", font=("Segoe UI", 7), bg=COR_CARTAO,
                     fg=COR_TEXTO_SECUNDARIO, anchor="w").pack(fill="x", padx=6)
        tk.Frame(tile, bg=COR_CARTAO, height=3).pack()

        self._tiles[arquivo.id] = (tile, previa, [base, rodape, nome, chk])
        self._pedidos_de_previa.setdefault(fonte.id, (fonte, []))[1].append(previa)
        self._pintar_tile(arquivo.id)
        return tile

    def _pintar_tile(self, id_arquivo):
        tile, _, filhos = self._tiles[id_arquivo]
        marcado = self.marcas[id_arquivo].get()
        cor = COR_MARCADO if marcado else COR_CARTAO
        tile.configure(bg=cor, highlightbackground=COR_ACENTO if marcado else COR_BORDA_CARTAO)
        for w in filhos + [w for f in filhos for w in f.winfo_children()] + tile.winfo_children():
            try:
                if w.cget("bg") in (COR_MARCADO, COR_CARTAO):
                    w.configure(bg=cor)
                if isinstance(w, tk.Checkbutton):
                    w.configure(activebackground=cor)
            except tk.TclError:
                pass

    def _pedir_previas(self):
        origem = self.origem
        for id_fonte, (fonte, rotulos) in self._pedidos_de_previa.items():
            def buscar(f=fonte):
                return origem.miniatura(f)

            def chegou(dados, rs=rotulos):
                if origem is not self.origem:
                    return
                foto = self._foto(dados, TAMANHO_TILE)
                for r in rs:
                    if foto:
                        r.configure(image=foto, text="", width=TAMANHO_TILE[0], height=TAMANHO_TILE[1])
                    else:
                        r.configure(text="sem prévia")
            self._no_fundo(buscar, chegou, ao_falhar=lambda e, rs=rotulos: [r.configure(text="sem prévia") for r in rs],
                           executor=self._miniaturas)

    def _montar_rodape_passo1(self):
        pe = tk.Frame(self.area, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        pe.pack(side="bottom", fill="x", padx=18, pady=(2, 12))
        esq = tk.Frame(pe, bg=COR_CARTAO)
        esq.pack(side="left", padx=14, pady=9)
        tk.Label(esq, text="Marcar:", font=("Segoe UI", 9, "bold"), bg=COR_CARTAO,
                 fg=COR_TEXTO).pack(side="left")
        for rotulo, regra in (("Só PDF", "pdf"), ("Tudo que é arte", "arte"), ("Tudo", "tudo"), ("Nada", "nada")):
            tk.Button(esq, text=rotulo, font=("Segoe UI", 8), relief="solid", bd=1, bg=COR_CARTAO,
                      fg=COR_ACENTO, padx=9, pady=2, cursor="hand2",
                      command=lambda r=regra: self._marcar(r)).pack(side="left", padx=2)
        self.lbl_total = tk.Label(esq, text="", font=("Segoe UI", 9, "bold"), bg=COR_CARTAO, fg=COR_TEXTO)
        self.lbl_total.pack(side="left", padx=14)
        self.lbl_status = tk.Label(esq, text="", font=("Segoe UI", 8), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO)
        self.lbl_status.pack(side="left")
        dr = tk.Frame(pe, bg=COR_CARTAO)
        dr.pack(side="right", padx=14, pady=8)
        self.btn_baixar = tk.Button(dr, text="Baixar os marcados  >", bg=COR_ACENTO, fg="white",
                                    font=("Segoe UI", 10, "bold"), relief="flat", padx=18, pady=6,
                                    cursor="hand2", command=self._baixar_marcados)
        self.btn_baixar.pack(side="left")

    def _marcar(self, regra):
        grupos = oa.agrupar(self.itens)
        for a in self.itens:
            if regra == "pdf":
                valor = a.ext == "PDF"
            elif regra == "arte":
                valor = oa.marcado_por_padrao(a, grupos[a.grupo])
            else:
                valor = regra == "tudo"
            self.marcas[a.id].set(valor)
            self._pintar_tile(a.id)
        self._atualizar_total()

    def _marcados(self):
        return [a for a in self.itens if self.marcas.get(a.id) and self.marcas[a.id].get()]

    def _atualizar_total(self):
        marcados = self._marcados()
        self.lbl_total.configure(text="%d de %d marcados  ·  %s" % (
            len(marcados), len(self.itens), _mb(sum(a.bytes for a in marcados))))
        self.btn_baixar.configure(text="Baixar os %d marcados  >" % len(marcados),
                                  state="normal" if marcados else "disabled")

    def _baixar_marcados(self):
        marcados = self._marcados()
        if not marcados:
            return
        self._ocupado(True)
        self.btn_baixar.configure(state="disabled")
        origem, lote, itens = self.origem, self.lote, self.itens
        cliente = self.var_cliente.get().strip()
        area = self.var_area.get().strip()
        total = len(marcados)

        def baixar():
            baixados = []
            for n, a in enumerate(marcados, start=1):
                self._na_tela(self._status, "baixando %d de %d: %s" % (n, total, a.nome))
                baixados.append((a, origem.baixar(a, lote), origem.chave(a)))
            self._na_tela(self._status, "medindo as artes...")
            return ra.propor(baixados, todos=itens, cliente=cliente, area=area, config=self.config_dados)

        def pronto(pecas):
            self._ocupado(False)
            self.pecas = pecas
            self._mostrar_passo2()

        self._no_fundo(baixar, pronto)

    # ============================================================ passo 2

    def _mostrar_passo2(self):
        self._limpar_area()
        self.var_passo.set("Passo 2 de 2 — confira e arquive. Nada entrou em ARTES ainda.")
        artes = [p for p in self.pecas if p.leva_nome_do_padrao or p.papel == "arte"]
        apoio = [p for p in self.pecas if p not in artes]

        cab = tk.Frame(self.area, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        cab.pack(fill="x", padx=18, pady=(2, 6))
        tk.Label(cab, text="%d peça%s pra arquivar, %d arquivo%s de apoio — nada entrou em ARTES ainda" % (
            len(artes), "s" if len(artes) != 1 else "", len(apoio), "s" if len(apoio) != 1 else ""),
            font=("Segoe UI", 10, "bold"), bg=COR_CARTAO, fg=COR_TEXTO).pack(anchor="w", padx=14, pady=(8, 0))
        tk.Label(cab, text="A medida foi lida da arte. Sem especificação: 1 unidade e A DEFINIR — mude aqui "
                           "se souber. O [+] faz a mesma arte servir outra peça.",
                 font=("Segoe UI", 8), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO).pack(anchor="w", padx=14)
        massa = tk.Frame(cab, bg=COR_CARTAO)
        massa.pack(fill="x", padx=14, pady=(6, 9))
        tk.Label(massa, text="Material de todas:", font=("Segoe UI", 9, "bold"), bg=COR_CARTAO,
                 fg=COR_TEXTO).pack(side="left")
        for m in self.materiais:
            tk.Button(massa, text=m, font=("Segoe UI", 8), relief="solid", bd=1, bg=COR_CARTAO,
                      fg=COR_ACENTO, padx=7, pady=1, cursor="hand2",
                      command=lambda mm=m: self._material_de_todas(mm)).pack(side="left", padx=2)

        self._montar_rodape_passo2()
        self._rolavel = _Rolavel(self.area, COR_FUNDO_JANELA)
        self._rolavel.pack(fill="both", expand=True, padx=18, pady=(0, 4))
        self._linhas = {}
        for p in artes:
            self._linha(self._rolavel.dentro, p)
        if apoio:
            caixa = tk.Frame(self._rolavel.dentro, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO,
                             highlightthickness=1)
            caixa.pack(fill="x", pady=(8, 2))
            tk.Label(caixa, text="Vão junto, com o nome do cliente (%d):" % len(apoio),
                     font=("Segoe UI", 9, "bold"), bg=COR_CARTAO, fg=COR_TEXTO).pack(anchor="w", padx=10, pady=(6, 2))
            nomes = ra.nomes_do_lote(apoio)
            for p in apoio:
                tipo = {"trabalho": ".ai de trabalho", "previa": "prévia", "outro": "outro formato"}.get(p.papel, p.papel)
                tk.Label(caixa, text="   %s   (%s)" % (nomes[id(p)], tipo), font=("Segoe UI", 8),
                         bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO, anchor="w").pack(fill="x", padx=10)
            tk.Frame(caixa, bg=COR_CARTAO, height=6).pack()
        self._verificar_nomes()

    def _linha(self, pai, peca):
        cartao = tk.Frame(pai, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        cartao.pack(fill="x", pady=2)
        c = tk.Frame(cartao, bg=COR_CARTAO)
        c.pack(fill="x", padx=6, pady=5)

        previa = tk.Label(c, text="...", width=10, height=3, bg=COR_PREVIA_FUNDO, fg=COR_TEXTO_SECUNDARIO,
                          font=("Segoe UI", 7))
        previa.pack(side="left")

        def buscar(p=peca):
            if p.pagina:
                return oa.miniatura_da_pagina(p.local, p.pagina - 1)
            return oa.miniatura_de_caminho(p.local)

        def chegou(dados):
            foto = self._foto(dados, TAMANHO_LINHA)
            if foto:
                previa.configure(image=foto, text="", width=TAMANHO_LINHA[0], height=TAMANHO_LINHA[1])
            else:
                previa.configure(text=peca.arquivo.ext)
        self._no_fundo(buscar, chegou, ao_falhar=lambda e: None, executor=self._miniaturas)

        col = tk.Frame(c, bg=COR_CARTAO)
        col.pack(side="left", padx=(8, 0), fill="x", expand=True)
        var_desc = tk.StringVar(value=peca.descricao)
        tk.Entry(col, textvariable=var_desc, font=("Segoe UI", 9), width=44, relief="solid", bd=1).pack(anchor="w")
        lbl_nome = tk.Label(col, text="", font=("Segoe UI", 7), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO, anchor="w")
        lbl_nome.pack(anchor="w", pady=(2, 0))
        origem_txt = peca.arquivo.nome + ("  ·  página %d de %d" % (peca.pagina, peca.paginas) if peca.pagina
                                          else ("  ·  %d páginas" % peca.paginas if peca.paginas > 1 else ""))
        tk.Label(col, text="de: " + origem_txt, font=("Segoe UI", 7), bg=COR_CARTAO,
                 fg=COR_TEXTO_SECUNDARIO, anchor="w").pack(anchor="w")

        dados = tk.Frame(c, bg=COR_CARTAO)
        dados.pack(side="left", padx=6)
        tk.Label(dados, text=ra.formatar_medida(peca.arte_m) if peca.arte_m else "sem medida",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARTAO,
                 fg=COR_TEXTO if peca.arte_m else COR_ALERTA, width=15, anchor="w").grid(row=0, column=0, sticky="w")
        sangria = ("sangria " + ra.formatar_medida(peca.sangria_m)) if (
            peca.sangria_m and peca.arte_m and peca.sangria_m != peca.arte_m) else "sem sangria"
        tk.Label(dados, text=sangria, font=("Segoe UI", 7), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO,
                 anchor="w").grid(row=1, column=0, sticky="w")

        marca = tk.Frame(c, bg=COR_CARTAO)
        marca.pack(side="left", padx=6)
        imagem = peca.arquivo.ext in ("TIF", "TIFF", "JPG", "JPEG", "PNG", "PSD")
        if peca.corte_px:
            texto, cor = "imagem: corte\naprovado", COR_POSITIVO
        elif imagem and peca.marca == "tem":
            texto, cor = "imagem com marca:\naprove o corte", COR_RIP_PARADO
        elif imagem and peca.marca == "a verificar":
            texto, cor = "imagem: marca\na verificar", COR_ALERTA
        else:
            texto, cor = {
                "tem": ("marca de corte: tem\nIllustrator tira", COR_ALERTA),
                "nao tem": ("sem marca de corte", COR_POSITIVO),
                "nao sei": ("marca: não dá\npra saber", COR_TEXTO_SECUNDARIO),
            }.get(peca.marca, ("", COR_TEXTO_SECUNDARIO))
        tk.Label(marca, text=texto, font=("Segoe UI", 7), bg=COR_CARTAO, fg=cor, width=16,
                 anchor="w", justify="left").pack(anchor="w")
        if imagem and peca.marca in ("tem", "a verificar"):
            tk.Button(marca, text="ver corte", font=("Segoe UI", 7), relief="solid", bd=1, bg=COR_CARTAO,
                      fg=COR_ACENTO, cursor="hand2", command=lambda p=peca: self._ver_corte(p)).pack(anchor="w")

        var_mat = tk.StringVar(value=peca.material)
        combo = ttk.Combobox(c, textvariable=var_mat, values=self.materiais, width=11,
                             font=("Segoe UI", 9), state="readonly")
        combo.pack(side="left", padx=4)
        self._sem_rodinha(combo)
        var_qtd = tk.StringVar(value=str(peca.quantidade))
        spin = tk.Spinbox(c, from_=1, to=999, width=4, textvariable=var_qtd, font=("Segoe UI", 9),
                          relief="solid", bd=1, justify="center")
        spin.pack(side="left", padx=6)
        self._sem_rodinha(spin)
        tk.Label(c, text="un", font=("Segoe UI", 8), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO).pack(side="left")
        tk.Button(c, text="+", font=("Segoe UI", 9, "bold"), relief="solid", bd=1, bg=COR_CARTAO,
                  fg=COR_ACENTO, width=2, cursor="hand2",
                  command=lambda p=peca: self._duplicar(p)).pack(side="left", padx=(8, 2))
        if peca.copia > 1:
            tk.Button(c, text="−", font=("Segoe UI", 9, "bold"), relief="solid", bd=1, bg=COR_CARTAO,
                      fg=COR_RIP_PARADO, width=2, cursor="hand2",
                      command=lambda p=peca: self._remover(p)).pack(side="left", padx=2)
        if peca.paginas > 1 and not peca.pagina:
            tk.Button(c, text="separar\npáginas", font=("Segoe UI", 7), relief="solid", bd=1, bg=COR_CARTAO,
                      fg=COR_ACENTO, cursor="hand2",
                      command=lambda p=peca: self._separar(p)).pack(side="left", padx=4)

        avisos = list(peca.avisos)
        for campo in ("quantidade", "material"):
            if "sem especificação" in peca.de_onde.get(campo, ""):
                continue
            if peca.de_onde.get(campo):
                avisos.append("%s veio do %s" % (campo, peca.de_onde[campo]))
        for texto in avisos:
            tk.Label(cartao, text="   " + texto, font=("Segoe UI", 8), bg=COR_ALERTA_FUNDO, fg=COR_ALERTA,
                     anchor="w").pack(fill="x", padx=6, pady=(0, 3))

        def mudou(*_):
            peca.descricao = var_desc.get().strip()
            peca.material = var_mat.get() or caderno_arte.MATERIAL_A_DEFINIR
            try:
                peca.quantidade = max(1, int(var_qtd.get()))
            except ValueError:
                pass
            self._verificar_nomes()
        for v in (var_desc, var_mat, var_qtd):
            v.trace_add("write", mudou)
        self._linhas[id(peca)] = {"cartao": cartao, "nome": lbl_nome, "var_mat": var_mat}

    def _material_de_todas(self, material):
        for p in self.pecas:
            if p.papel == "arte":
                p.material = material
                linha = self._linhas.get(id(p))
                if linha:
                    linha["var_mat"].set(material)
        self._verificar_nomes()

    def _duplicar(self, peca):
        nova = ra.duplicar(peca, self.pecas)
        nova.descricao = "%s %d" % (peca.descricao, nova.copia)
        self.pecas.insert(self.pecas.index(peca) + 1, nova)
        self._mostrar_passo2()

    def _remover(self, peca):
        self.pecas.remove(peca)
        self._mostrar_passo2()

    def _separar(self, peca):
        i = self.pecas.index(peca)
        self.pecas[i:i + 1] = ra.separar_paginas(peca)
        self._mostrar_passo2()

    def _verificar_nomes(self):
        area = self.var_area.get().strip()
        nomes = ra.nomes_do_lote(self.pecas, area)
        ruins = {id(p) for ps in ra.repetidos(self.pecas, area).values() for p in ps}
        for p in self.pecas:
            linha = self._linhas.get(id(p))
            if not linha or not linha["nome"].winfo_exists():
                continue   # linha de uma tela que já foi trocada
            if id(p) in ruins:
                linha["nome"].configure(text="NOME REPETIDO — mude a descrição:  " + nomes[id(p)], fg=COR_RIP_PARADO)
                linha["cartao"].configure(highlightbackground=COR_RIP_PARADO)
            else:
                linha["nome"].configure(text="vai se chamar:  " + nomes[id(p)], fg=COR_TEXTO_SECUNDARIO)
                linha["cartao"].configure(highlightbackground=COR_BORDA_CARTAO)

        # m² sempre POR MATERIAL — nunca um total somando materiais diferentes
        por_material = {}
        for p in self.pecas:
            if p.leva_nome_do_padrao:
                qtd, m2 = por_material.get(p.material, (0, 0.0))
                por_material[p.material] = (qtd + p.quantidade, m2 + _m2(p.arte_m, p.quantidade))
        texto = "      ".join("%s  %d un · %s m²" % (m, q, ("%.2f" % a).replace(".", ","))
                              for m, (q, a) in sorted(por_material.items()))
        if hasattr(self, "lbl_totais") and self.lbl_totais.winfo_exists():
            self.lbl_totais.configure(text="Por material:   " + (texto or "—"))
            destino = self._destino()
            self.btn_arquivar.configure(
                text="Arquivar em %s" % destino.name,
                state="disabled" if ruins or not self.pecas else "normal")
            if ruins:
                self._status("há nomes repetidos — um arquivo apagaria o outro", "erro")
            elif hasattr(self, "lbl_status"):
                self._status("")

    def _montar_rodape_passo2(self):
        pe = tk.Frame(self.area, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        pe.pack(side="bottom", fill="x", padx=18, pady=(2, 12))
        esq = tk.Frame(pe, bg=COR_CARTAO)
        esq.pack(side="left", padx=14, pady=8, fill="x", expand=True)
        linha = tk.Frame(esq, bg=COR_CARTAO)
        linha.pack(anchor="w")
        self.var_tirar_marca = tk.BooleanVar(value=True)
        tk.Checkbutton(linha, text="Tirar a marca de corte (Illustrator — não use ele enquanto arquiva)",
                       variable=self.var_tirar_marca, font=("Segoe UI", 9), bg=COR_CARTAO, fg=COR_TEXTO,
                       activebackground=COR_CARTAO).pack(side="left")
        descartavel = self.origem is not None and self.origem.tipo in ("wetransfer", "zip")
        self.var_guardar = tk.BooleanVar(value=descartavel)
        if descartavel:
            tk.Checkbutton(linha, text="Guardar o que chegou, como chegou (_sistema\\recebidos)",
                           variable=self.var_guardar, font=("Segoe UI", 9), bg=COR_CARTAO, fg=COR_TEXTO,
                           activebackground=COR_CARTAO).pack(side="left", padx=(16, 0))
        self.lbl_totais = tk.Label(esq, text="", font=("Segoe UI", 9, "bold"), bg=COR_CARTAO, fg=COR_TEXTO,
                                   anchor="w")
        self.lbl_totais.pack(anchor="w", pady=(4, 0))
        self.lbl_status = tk.Label(esq, text="", font=("Segoe UI", 8), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO,
                                   anchor="w", wraplength=760, justify="left")
        self.lbl_status.pack(anchor="w")
        dr = tk.Frame(pe, bg=COR_CARTAO)
        dr.pack(side="right", padx=14, pady=8)
        tk.Button(dr, text="<  Voltar", font=("Segoe UI", 10), relief="solid", bd=1, bg=COR_CARTAO,
                  fg=COR_TEXTO, padx=14, pady=5, cursor="hand2",
                  command=self._mostrar_passo1).pack(side="left", padx=4)
        self.btn_arquivar = tk.Button(dr, text="Arquivar", bg=COR_ACENTO, fg="white",
                                      font=("Segoe UI", 10, "bold"), relief="flat", padx=18, pady=6,
                                      cursor="hand2", command=self._arquivar)
        self.btn_arquivar.pack(side="left")

    # ------------------------------------------------------------- corte

    def _ver_corte(self, peca):
        """A marca de corte numa imagem: o sistema propõe, ele aprova (decisão de 21/09)."""
        from gui_corte_imagem import JanelaCorteImagem

        def aprovado(retangulo, arte_m, fica_m):
            # a medida do nome passa a ser a da arte entre as marcas, não a
            # da imagem inteira com a moldura
            peca.corte_px = retangulo
            peca.marca = "tem"
            peca.avisos = [a for a in peca.avisos if "ver corte" not in a]
            if arte_m:
                peca.arte_m, peca.sangria_m = arte_m, fica_m
                peca.de_onde["medida"] = "da arte, entre as marcas de corte"
            self._mostrar_passo2()
        JanelaCorteImagem(self, peca, aprovado)

    # ---------------------------------------------------------- arquivar

    def _arquivar(self):
        situacao, dado = clientes.situacao_do_nome(self.var_cliente.get())
        if situacao in ("vazio", "invalido"):
            messagebox.showwarning("Receber artes", dado or "Digite o nome do cliente.", parent=self)
            return
        nome_cliente = self.var_cliente.get().strip()
        if situacao == "parecido":
            usar = messagebox.askyesnocancel(
                "Cliente parecido",
                'Já existe o cliente "%s".\n\nÉ ele?\n\nSim = usar "%s"\nNão = criar o cliente novo "%s"'
                % (dado.nome, dado.nome, nome_cliente), parent=self)
            if usar is None:
                return
            if usar:
                nome_cliente = dado.nome
                self.var_cliente.set(dado.nome)
        artes = [p for p in self.pecas if p.leva_nome_do_padrao]
        apoio = [p for p in self.pecas if not p.leva_nome_do_padrao]
        a_definir = sum(1 for p in artes if not p.material_definido)
        com_marca = sum(1 for p in artes if p.marca == "tem") if self.var_tirar_marca.get() else 0
        destino = self._destino()
        linhas = ["%d peça(s) com o nome do padrão e %d arquivo(s) de apoio" % (len(artes), len(apoio)),
                  "em: %s" % destino]
        if clientes.situacao_do_nome(nome_cliente)[0] == "novo":
            linhas.append("CLIENTE NOVO: a pasta Recebimento de Artes\\%s vai ser criada." % nome_cliente)
        if com_marca:
            linhas.append("%d arte(s) passam pelo Illustrator pra tirar a marca de corte (uns 30-60 s cada)."
                          % com_marca)
        if a_definir:
            linhas.append("%d peça(s) ficam como A DEFINIR — não mande pra máquina assim." % a_definir)
        if not messagebox.askokcancel("Arquivar", "\n\n".join(linhas), parent=self):
            return

        self._ocupado(True)
        self.btn_arquivar.configure(state="disabled")
        pecas, origem, area = list(self.pecas), self.origem, self.var_area.get().strip()
        tirar, guardar = self.var_tirar_marca.get(), self.var_guardar.get()
        escolhido = self._destino_escolhido

        def registrar(nivel, texto):
            self._na_tela(self._status, texto, {"ok": "ok", "warn": "aviso"}.get(nivel, "info"))

        def arquivar():
            cliente, criado = clientes.obter_ou_criar(nome_cliente)
            area_pasta = sanitizar_nome_arquivo(area) if area else ""
            alvo = escolhido or (cliente.pasta / "ARTES" / area_pasta if area_pasta else cliente.pasta / "ARTES")
            resumo = ra.arquivar(pecas, cliente, alvo, area=area, origem=origem, guardar_original=guardar,
                                 remover_marcas=tirar, logger=registrar)
            return cliente, criado, alvo, resumo

        self._no_fundo(arquivar, self._mostrar_resultado)

    def _mostrar_resultado(self, resultado):
        cliente, criado, destino, resumo = resultado
        self._ocupado(False)
        self._limpar_area()
        self.var_passo.set("Pronto.")
        caixa = tk.Frame(self.area, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        caixa.pack(fill="x", padx=18, pady=10)
        ok = len(resumo.arquivadas) + len(resumo.ja_estavam)
        tk.Label(caixa, text="%d arquivo(s) em %s" % (ok, destino), font=("Segoe UI", 11, "bold"),
                 bg=COR_CARTAO, fg=COR_POSITIVO if not resumo.falharam else COR_ALERTA,
                 anchor="w", wraplength=1150, justify="left").pack(fill="x", padx=14, pady=(10, 4))
        linhas = []
        if criado:
            linhas.append("Cliente novo criado: %s" % cliente.pasta)
        if resumo.ja_estavam:
            linhas.append("%d já estava(m) lá, idêntico(s) — não mexi." % len(resumo.ja_estavam))
        tiradas = sum(1 for p, _ in resumo.arquivadas if p.marca_removida)
        if tiradas:
            linhas.append("Marca de corte tirada de %d arte(s), conferida pixel a pixel." % tiradas)
        if resumo.originais:
            linhas.append("O que chegou foi guardado como chegou em %s" % resumo.originais[0].parent)
        for texto in linhas + resumo.avisos:
            tk.Label(caixa, text=texto, font=("Segoe UI", 9), bg=COR_CARTAO, fg=COR_TEXTO,
                     anchor="w", wraplength=1150, justify="left").pack(fill="x", padx=14)
        for peca, motivo in resumo.falharam:
            tk.Label(caixa, text="NÃO entrou: %s — %s" % (peca.arquivo.nome, motivo), font=("Segoe UI", 9),
                     bg=COR_ALERTA_FUNDO, fg=COR_RIP_PARADO, anchor="w", wraplength=1150,
                     justify="left").pack(fill="x", padx=14, pady=1)
        botoes = tk.Frame(caixa, bg=COR_CARTAO)
        botoes.pack(anchor="w", padx=14, pady=10)
        tk.Button(botoes, text="Abrir a pasta", bg=COR_ACENTO, fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=16, pady=5, cursor="hand2",
                  command=lambda: _abrir(destino)).pack(side="left", padx=(0, 8))
        if resumo.falharam:
            tk.Button(botoes, text="Voltar pro passo 2", font=("Segoe UI", 10), relief="solid", bd=1,
                      bg=COR_CARTAO, fg=COR_TEXTO, padx=14, pady=4, cursor="hand2",
                      command=self._voltar_com_as_que_falharam(resumo)).pack(side="left", padx=4)
        tk.Button(botoes, text="Receber outra origem", font=("Segoe UI", 10), relief="solid", bd=1,
                  bg=COR_CARTAO, fg=COR_TEXTO, padx=14, pady=4, cursor="hand2",
                  command=self._recomecar).pack(side="left", padx=4)
        self.lbl_status = tk.Label(caixa, text="", bg=COR_CARTAO)

    def _voltar_com_as_que_falharam(self, resumo):
        def voltar():
            self.pecas = [p for p, _ in resumo.falharam]
            self._mostrar_passo2()
        return voltar

    def _recomecar(self):
        # o cliente que acabou de nascer tem que aparecer na lista
        self.combo_cliente.configure(values=[cl.nome for cl in clientes.listar()])
        self.var_origem.set("")
        self.pecas = []
        self.itens = []
        self._destino_escolhido = None
        self._atualizar_destino()
        self._mostrar_inicio()
