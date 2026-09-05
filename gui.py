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
import json
import pathlib
import queue
import subprocess
import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

# arquivamento.py não é mais importado aqui: o checkbox que enviava a
# OS pro OneDrive foi removido (2026-09-05). O módulo continua no
# projeto, testado, caso o envio volte em outro formato.
from branding import CAMINHO_LOGO_GUI
from config import atualizar_ultimo_uso, atualizar_ultima_impressora, carregar_config, salvar_config
from dimensoes import formatar_variante
from documento_enviados import (
    carregar as carregar_envios, caminho_pdf as caminho_documento_pdf,
    miniatura as gerar_miniatura, registrar as registrar_envios, regravar_pdf as regravar_documento,
)
from envio_impressao import (
    cabe_na_maquina, conferir as conferir_envio, enviar as enviar_para_maquinas,
    listar as listar_para_envio, prever_giro, raiz_do_cliente, subtotais_por_material,
)
from estado_pedido import estado_existe, localizar_pastas_cliente
from estoque import (
    carregar_estoque, saldo_produto, registrar_movimento, desfazer_movimento,
    prever_saida_os, confirmar_saida_os, pedido_ja_teve_saida, produtos_por_categoria,
    novo_produto, adicionar_produto, atualizar_produto, remover_produto,
    meses_disponiveis, resumo_mensal, rendimento_tinta_mensal,
)
from impressao import imprimir_pdf, impressora_padrao, listar_impressoras
from processamento import processar_etiquetas
from rasterlink import rastrear as rastrear_rip
from rasterlink_hotfolder import MAQUINAS as MAQUINAS_RIP
from utils import sanitizar_nome_arquivo

# Onde o seletor de pasta da tela de envio começa quando ainda não há
# uma última pasta usada — mesma raiz que o monitor de pastas vigia.
PASTA_EVENTOS = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO" / "EVENTOS"

COR_ACENTO = "#0067c0"
COR_FUNDO_JANELA = "#f5f6f8"
COR_CARTAO = "#ffffff"
COR_BORDA_CARTAO = "#e3e4e8"
COR_TEXTO = "#1c1c1f"
COR_TEXTO_SECUNDARIO = "#6b7280"
COR_ALERTA = "#b45309"
COR_ALERTA_FUNDO = "#fdf1e0"
COR_POSITIVO = "#0f7a3d"


def _rotulo_variantes(variantes):
    return f"Variantes ({len(variantes)})" if variantes else "Variantes..."


def _pedidos_para_impressao(pasta_base="etiquetas_geradas"):
    """
    Lista cada pasta de pedido que tem OS e/ou Checklist em disco, mais
    recente primeiro — usado pela tela de reimpressão manual (não
    reaproveita arquivamento.listar_pedidos porque essa só devolve os
    PDFs de OS, e aqui precisamos do Checklist também).
    """
    base = pathlib.Path(pasta_base)
    if not base.exists():
        return []
    pedidos = []
    for pasta in sorted(base.iterdir(), reverse=True):
        if not pasta.is_dir():
            continue
        arquivos_os = sorted(pasta.glob("OS - *.pdf"))
        arquivos_checklist = sorted(pasta.glob("Checklist *.pdf"))
        if not arquivos_os and not arquivos_checklist:
            continue
        pedidos.append({"pasta": pasta, "nome": pasta.name, "os": arquivos_os, "checklist": arquivos_checklist})
    return pedidos


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

    def report_callback_exception(self, exc, val, tb):
        # Tkinter chama isso quando um comando de botão/atalho/evento
        # levanta uma exceção não tratada — o padrão é só imprimir no
        # console, que rodando via pythonw.exe (sem console, o jeito
        # normal de abrir o programa) não existe: o erro simplesmente
        # desaparece e a tela fica num estado esquisito sem explicação
        # nenhuma. Aqui ele pelo menos aparece no log da própria tela.
        import traceback
        mensagem = "".join(traceback.format_exception(exc, val, tb)).strip()
        try:
            self._registrar_log("err", f"Erro inesperado: {mensagem}")
        except Exception:
            pass

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
        ).pack(anchor="w", padx=16, pady=(4, 2))

        tk.Button(
            self, text="📦 Controle de Estoque...", relief="flat",
            fg=COR_ACENTO, cursor="hand2", command=self._abrir_estoque,
        ).pack(anchor="w", padx=16, pady=(0, 2))

        tk.Button(
            self, text="🖨 Imprimir OS/Checklist de um pedido...", relief="flat",
            fg=COR_ACENTO, cursor="hand2", command=self._abrir_impressao_manual,
        ).pack(anchor="w", padx=16, pady=(0, 2))

        tk.Button(
            self, text="📤 Enviar para impressão...", relief="flat",
            fg=COR_ACENTO, cursor="hand2", command=self._abrir_envio_impressao,
        ).pack(anchor="w", padx=16, pady=(0, 2))

        # DESATIVADO a pedido do usuário (2026-09-05): "ficou muito
        # complicado de operar, vou pensar em alguma coisa melhor pra
        # essa função". O botão saiu da tela, mas JanelaCruzarRIP e
        # rasterlink.py continuam inteiros (e testados) — pra religar,
        # é só devolver este tk.Button:
        #     tk.Button(
        #         self, text="🔀 Cruzar pasta com lista do RIP...", relief="flat",
        #         fg=COR_ACENTO, cursor="hand2", command=self._abrir_cruzamento_rip,
        #     ).pack(anchor="w", padx=16, pady=(0, 2))

        ttk.Separator(self).pack(fill="x", padx=16, pady=(0, 10))

        # O checkbox "Enviar a OS pro OneDrive depois de gerar" foi
        # removido a pedido do usuário (2026-09-05): o recurso não era
        # usado, e a pasta de destino no OneDrive foi apagada junto.
        # arquivamento.py continua existindo e testado, só não tem mais
        # nada na interface que dispare o envio.

        frame_impressao = tk.Frame(self)
        frame_impressao.pack(fill="x", padx=16, pady=(0, 6))
        linha_impressora = tk.Frame(frame_impressao)
        linha_impressora.pack(fill="x")
        tk.Label(linha_impressora, text="Impressora:").pack(side="left")
        self.var_impressora = tk.StringVar()
        self.combo_impressora = ttk.Combobox(
            linha_impressora, textvariable=self.var_impressora, state="readonly", width=32,
        )
        self.combo_impressora.pack(side="left", padx=(6, 6), fill="x", expand=True)
        self.combo_impressora.bind("<<ComboboxSelected>>", self._impressora_selecionada)
        tk.Button(linha_impressora, text="↻", width=3, command=self._atualizar_impressoras).pack(side="left")
        self._atualizar_impressoras(selecionar_salva=True)

        self.var_imprimir_ao_gerar = tk.BooleanVar(value=False)
        tk.Checkbutton(
            frame_impressao, text="🖨 Imprimir OS e Checklist assim que gerar", variable=self.var_imprimir_ao_gerar,
        ).pack(anchor="w")

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
        pasta = filedialog.askdirectory(title="Selecione a pasta com os arquivos (PDF, AI, PNG, JPG)")
        if pasta:
            self.var_pasta.set(pasta)

    def _abrir_configuracoes(self):
        JanelaConfiguracoes(self, self.config_dados, self._config_atualizada)

    def _abrir_estoque(self):
        JanelaEstoque(self, self.config_dados)

    def _abrir_impressao_manual(self):
        JanelaImprimirPedido(self, self.var_impressora.get())

    def _abrir_envio_impressao(self):
        JanelaEnviarImpressao(self, self.config_dados)

    def _abrir_cruzamento_rip(self):
        # sem botão que chame isso hoje — ver comentário do botão
        # desativado no __init__ (2026-09-05)
        JanelaCruzarRIP(self)

    def _config_atualizada(self, nova_config):
        self.config_dados = nova_config

    def _atualizar_impressoras(self, selecionar_salva=False):
        """
        Repopula a lista de impressoras que o Windows reconhece agora
        (pode ter mudado — impressora ligada/desligada, USB conectado).
        Na primeira chamada (selecionar_salva=True), tenta manter a
        última impressora escolhida; senão cai pra impressora padrão do
        Windows, ou a primeira da lista se nem isso houver.
        """
        impressoras = listar_impressoras()
        self.combo_impressora["values"] = impressoras
        if not impressoras:
            self.var_impressora.set("")
            return
        if selecionar_salva:
            salva = self.config_dados.get("ultima_impressora", "")
            if salva in impressoras:
                self.var_impressora.set(salva)
                return
        padrao = impressora_padrao()
        self.var_impressora.set(padrao if padrao in impressoras else impressoras[0])

    def _impressora_selecionada(self, event=None):
        self.config_dados = atualizar_ultima_impressora(self.config_dados, self.var_impressora.get())

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

        pasta_saida_existente = self._resolver_pasta_saida(cliente)

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
            args=(
                pasta, cliente, gerente, produtor, pasta_saida_existente,
                self.var_imprimir_ao_gerar.get(), self.var_impressora.get(),
            ),
            daemon=True,
        )
        thread.start()

    def _resolver_pasta_saida(self, cliente):
        """
        Checa se já existe pedido desse cliente antes de processar, e
        pergunta se é pra atualizar (só os arquivos novos da pasta de
        entrada entram, mesmo que ela venha inteira de novo misturada
        com o que já foi mandado) ou criar um pedido novo. Pastas de
        antes desse recurso existir (sem estado_pedido.json) não entram
        na lista de opções — não dá pra saber com segurança o que já
        foi processado nelas, então a única opção seria criar de novo.

        Devolve o Path da pasta a atualizar, ou None pra criar uma
        pasta nova (comportamento de sempre).
        """
        nome_seguro = sanitizar_nome_arquivo(cliente).upper()
        todas = localizar_pastas_cliente(nome_seguro)
        atualizaveis = [p for p in todas if estado_existe(p)]
        legado = [p for p in todas if not estado_existe(p)]

        if not atualizaveis:
            if legado:
                messagebox.showinfo(
                    "Pedidos antigos encontrados",
                    f"Já existem pasta(s) de '{cliente}', mas de antes desse recurso existir — não é "
                    "possível saber com segurança quais arquivos já foram processados nelas. Um "
                    "pedido novo será criado.",
                )
            return None

        if len(atualizaveis) == 1:
            pasta = atualizaveis[0]
            resposta = messagebox.askyesno(
                "Pedido existente encontrado",
                f"Já existe um pedido de '{cliente}' em:\n{pasta.name}\n\n"
                "Atualizar esse pedido (só os arquivos novos da pasta de entrada entram, com o selo "
                "de data) em vez de criar um pedido novo?",
            )
            return pasta if resposta else None

        janela = JanelaEscolherPedido(self, atualizaveis)
        self.wait_window(janela)
        return janela.resultado

    def _executar_em_thread(
        self, pasta, cliente, gerente, produtor, pasta_saida_existente,
        imprimir_ao_gerar, impressora,
    ):
        def on_log(nivel, msg):
            self.fila_eventos.put(("log", nivel, msg))

        def on_progress(atual, total):
            self.fila_eventos.put(("progress", atual, total))

        try:
            resultado = processar_etiquetas(
                pasta, cliente, gerente, produtor, self.config_dados,
                on_log=on_log, on_progress=on_progress, pasta_saida_existente=pasta_saida_existente,
            )
        except Exception as e:
            self.fila_eventos.put(("log", "err", f"Erro inesperado: {e}"))
            resultado = None

        if resultado and imprimir_ao_gerar:
            try:
                self._imprimir_os_checklist(resultado, impressora, on_log)
            except Exception as e:
                self.fila_eventos.put(("log", "err", f"Erro inesperado ao imprimir: {e}"))

        self.fila_eventos.put(("fim", resultado, None))

    def _imprimir_os_checklist(self, resultado, impressora, on_log):
        """
        Roda logo depois do processamento, na mesma thread, só quando o
        checkbox "Imprimir OS e Checklist assim que gerar" estava
        marcado. Erro numa impressão (ex: impressora desligada) não
        impede a outra de tentar.
        """
        for rotulo, caminho in (("OS", resultado.get("os")), ("Checklist", resultado.get("unificado"))):
            if not caminho:
                continue
            on_log("info", f"Imprimindo {rotulo}...")
            try:
                imprimir_pdf(caminho, impressora)
                on_log("ok", f"{rotulo} enviada pra impressora: {pathlib.Path(caminho).name}")
            except RuntimeError as e:
                on_log("err", str(e))

    def _checar_fila(self):
        # O 'finally' é o que garante que essa checagem sempre volta a
        # se reagendar (self.after mais abaixo) — sem isso, um erro
        # inesperado ao tratar UM evento (ex: um resultado com um
        # formato que a tela não esperava) quebrava esse
        # reagendamento pra sempre: a tela parava de atualizar (barra
        # de progresso, log, botão "Processando...") ainda no meio de
        # um processamento longo, mesmo que a thread de verdade
        # continuasse rodando por trás — pro usuário isso é
        # indistinguível de "travou" (achado real, 2026-09-04).
        try:
            while True:
                try:
                    evento = self.fila_eventos.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._tratar_evento_fila(evento)
                except Exception as e:
                    self._registrar_log("err", f"Erro inesperado ao atualizar a tela: {e}")
        finally:
            self.after(150, self._checar_fila)

    def _tratar_evento_fila(self, evento):
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
                novos = resultado.get("arquivos_novos", 0)
                ignorados = resultado.get("arquivos_ignorados", 0)
                if resultado.get("atualizacao") and novos == 0:
                    messagebox.showinfo(
                        "Nada novo pra processar",
                        f"Todos os {ignorados} arquivo(s) da pasta de entrada já tinham sido "
                        f"processados nesse pedido antes. Nada foi gerado.",
                    )
                elif resultado.get("atualizacao"):
                    texto = f"{novos} arquivo(s) novo(s) processado(s) em:\n{resultado['pasta_saida']}"
                    if ignorados:
                        texto += f"\n\n({ignorados} arquivo(s) já processado(s) antes foram ignorados.)"
                    messagebox.showinfo("Pedido atualizado", texto)
                else:
                    messagebox.showinfo("Concluído", f"Etiquetas geradas em:\n{resultado['pasta_saida']}")
            else:
                self.var_progresso_texto.set("Processamento interrompido — veja o log acima.")


class JanelaEscolherPedido(tk.Toplevel):
    """
    Quando há mais de um pedido atualizável pra esse cliente, deixa
    escolher qual (ou seguir com um pedido novo mesmo assim). Modal —
    quem abre usa self.wait_window(janela) e lê janela.resultado depois
    que ela fechar: o Path escolhido, ou None pra pedido novo.
    """

    def __init__(self, mestre, pastas):
        super().__init__(mestre)
        self.title("Pedido existente encontrado")
        self.geometry("460x320")
        self.transient(mestre)
        self.pastas = pastas
        self.resultado = None

        tk.Label(
            self, text="Já existem pedidos desse cliente", font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            self, fg="#666666", justify="left", wraplength=420,
            text="Escolha qual pedido atualizar (só os arquivos novos da pasta de entrada entram) "
                 "ou crie um pedido novo.",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        self.lista = tk.Listbox(self, activestyle="dotbox")
        for pasta in pastas:
            self.lista.insert("end", pasta.name)
        self.lista.selection_set(0)
        self.lista.pack(fill="both", expand=True, padx=16)

        frame_botoes = tk.Frame(self)
        frame_botoes.pack(fill="x", padx=16, pady=14)
        tk.Button(frame_botoes, text="Criar pedido novo", command=self._criar_novo).pack(side="left")
        tk.Button(
            frame_botoes, text="Atualizar selecionado", bg=COR_ACENTO, fg="white", relief="flat",
            command=self._atualizar_selecionado,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._criar_novo)
        self.grab_set()

    def _atualizar_selecionado(self):
        selecao = self.lista.curselection()
        if selecao:
            self.resultado = self.pastas[selecao[0]]
        self.destroy()

    def _criar_novo(self):
        self.resultado = None
        self.destroy()


class JanelaImprimirPedido(tk.Toplevel):
    """
    Reimprime a OS e/ou o Checklist de um pedido já gerado — pra quando
    a via impressa se perde ou estraga na fábrica e precisa de outra
    via, sem regenerar nada.
    """

    def __init__(self, mestre, impressora_inicial):
        super().__init__(mestre)
        self.title("Imprimir OS/Checklist de um pedido")
        self.geometry("480x420")
        self.transient(mestre)
        self.pedidos = _pedidos_para_impressao()

        tk.Label(self, text="Escolha o pedido", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 2))

        self.lista = tk.Listbox(self, activestyle="dotbox")
        for pedido in self.pedidos:
            rotulos = []
            if pedido["os"]:
                rotulos.append("OS")
            if pedido["checklist"]:
                rotulos.append("Checklist")
            self.lista.insert("end", f"{pedido['nome']}  ({' + '.join(rotulos)})")
        if self.pedidos:
            self.lista.selection_set(0)
        self.lista.pack(fill="both", expand=True, padx=16)

        self.var_os = tk.BooleanVar(value=True)
        self.var_checklist = tk.BooleanVar(value=True)
        frame_opcoes = tk.Frame(self)
        frame_opcoes.pack(anchor="w", padx=16, pady=(10, 4))
        tk.Checkbutton(frame_opcoes, text="OS", variable=self.var_os).pack(side="left")
        tk.Checkbutton(frame_opcoes, text="Checklist", variable=self.var_checklist).pack(side="left", padx=(10, 0))

        frame_impressora = tk.Frame(self)
        frame_impressora.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(frame_impressora, text="Impressora:").pack(side="left")
        self.var_impressora = tk.StringVar(value=impressora_inicial)
        ttk.Combobox(
            frame_impressora, textvariable=self.var_impressora, state="readonly",
            values=listar_impressoras(), width=32,
        ).pack(side="left", padx=(6, 0), fill="x", expand=True)

        self.var_status = tk.StringVar(value="")
        tk.Label(self, textvariable=self.var_status, fg="#666666", wraplength=440, justify="left").pack(
            anchor="w", padx=16,
        )

        frame_botoes = tk.Frame(self)
        frame_botoes.pack(fill="x", padx=16, pady=14)
        tk.Button(frame_botoes, text="Fechar", command=self.destroy).pack(side="left")
        self.btn_imprimir = tk.Button(
            frame_botoes, text="🖨 Imprimir", bg=COR_ACENTO, fg="white", relief="flat", command=self._imprimir,
        )
        self.btn_imprimir.pack(side="right")

        if not self.pedidos:
            tk.Label(self, text="Nenhum pedido com OS ou Checklist encontrado.", fg=COR_ALERTA).pack(padx=16)
            self.btn_imprimir.configure(state="disabled")

        self.grab_set()

    def _imprimir(self):
        selecao = self.lista.curselection()
        if not selecao:
            messagebox.showwarning("Escolha um pedido", "Selecione um pedido na lista.")
            return
        pedido = self.pedidos[selecao[0]]
        arquivos = []
        if self.var_os.get():
            arquivos += pedido["os"]
        if self.var_checklist.get():
            arquivos += pedido["checklist"]
        if not arquivos:
            messagebox.showwarning("Nada selecionado", "Marque OS e/ou Checklist pra imprimir.")
            return

        impressora = self.var_impressora.get()
        self.btn_imprimir.configure(state="disabled", text="Imprimindo...")
        self.var_status.set("")
        thread = threading.Thread(target=self._imprimir_em_thread, args=(arquivos, impressora), daemon=True)
        thread.start()

    def _imprimir_em_thread(self, arquivos, impressora):
        erros = []
        for caminho in arquivos:
            try:
                imprimir_pdf(caminho, impressora)
            except RuntimeError as e:
                erros.append(str(e))
        self.after(0, lambda: self._imprimir_concluido(len(arquivos) - len(erros), erros))

    def _imprimir_concluido(self, ok, erros):
        self.btn_imprimir.configure(state="normal", text="🖨 Imprimir")
        if erros:
            self.var_status.set(f"{ok} arquivo(s) enviado(s), {len(erros)} com erro.")
            messagebox.showerror("Erro ao imprimir", "\n".join(erros))
        else:
            self.var_status.set(f"{ok} arquivo(s) enviado(s) pra impressora.")


class JanelaCruzarRIP(tk.Toplevel):
    """
    Cola a lista de tarefas de um RIP (RasterLink...) e cruza com uma
    pasta de produção: o que bate EXATO no nome move sozinho (solto ->
    Prontos, ou Prontos -> solto quando não está mais na lista); o
    resto só é avisado, nunca movido sem confirmação — ver
    rasterlink.rastrear. Não existe exportação nativa de lista no
    RasterLink, por isso a lista sempre é colada à mão (de um print da
    Job List), nunca lida automaticamente de um arquivo do RIP.
    """

    def __init__(self, mestre):
        super().__init__(mestre)
        self.title("Cruzar pasta com lista do RIP")
        self.geometry("640x600")
        self.minsize(560, 520)
        self.transient(mestre)

        tk.Label(self, text="Pasta de produção", font=("Segoe UI", 11, "bold")).pack(
            anchor="w", padx=16, pady=(14, 2),
        )
        frame_pasta = tk.Frame(self)
        frame_pasta.pack(fill="x", padx=16)
        self.var_pasta = tk.StringVar()
        tk.Entry(frame_pasta, textvariable=self.var_pasta).pack(side="left", fill="x", expand=True)
        tk.Button(frame_pasta, text="Procurar...", command=self._escolher_pasta).pack(side="left", padx=(6, 0))

        tk.Label(
            self, text='Trecho a ignorar na comparação (opcional — ex: nome do cliente inserido depois)',
        ).pack(anchor="w", padx=16, pady=(10, 2))
        self.var_termo = tk.StringVar()
        tk.Entry(self, textvariable=self.var_termo).pack(fill="x", padx=16)

        tk.Label(
            self, text="Cole aqui a lista de tarefas do RIP (uma por linha)", font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(10, 2))
        self.texto_lista = tk.Text(self, height=8, wrap="none")
        self.texto_lista.pack(fill="both", padx=16)

        self.btn_cruzar = tk.Button(
            self, text="🔀 Cruzar", bg=COR_ACENTO, fg="white", relief="flat", command=self._cruzar,
        )
        self.btn_cruzar.pack(anchor="e", padx=16, pady=(10, 6))

        tk.Label(self, text="Resultado", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16)
        self.texto_resultado = tk.Text(self, height=12, state="disabled", wrap="word", bg="#fafafa")
        self.texto_resultado.pack(fill="both", expand=True, padx=16, pady=(2, 14))

        self.grab_set()

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.var_pasta.set(pasta)

    def _cruzar(self):
        pasta = self.var_pasta.get().strip()
        if not pasta:
            messagebox.showwarning("Pasta vazia", "Escolha a pasta de produção.")
            return
        lista = [linha for linha in self.texto_lista.get("1.0", "end").splitlines() if linha.strip()]
        if not lista:
            messagebox.showwarning("Lista vazia", "Cole a lista de tarefas do RIP, uma por linha.")
            return

        termo = self.var_termo.get().strip() or None
        try:
            resultado = rastrear_rip(pasta, lista, termo_ignorado=termo)
        except FileNotFoundError as e:
            messagebox.showerror("Pasta não encontrada", str(e))
            return
        except OSError as e:
            messagebox.showerror("Erro ao mover arquivo", str(e))
            return

        self._mostrar_resultado(resultado)

    def _mostrar_resultado(self, resultado):
        linhas = [f"Movidos pra Prontos ({len(resultado['movidos_pra_prontos'])}):"]
        linhas += [f"  {nome}" for nome in resultado["movidos_pra_prontos"]] or ["  (nenhum)"]
        linhas.append("")
        linhas.append(f"Movidos de volta pra solto ({len(resultado['movidos_pra_solto'])}):")
        linhas += [f"  {nome}" for nome in resultado["movidos_pra_solto"]] or ["  (nenhum)"]
        linhas.append("")
        linhas.append(f"Achados em pasta de OUTRO cliente e inseridos no Prontos de lá ({len(resultado['achados_em_outra_pasta'])}):")
        if resultado["achados_em_outra_pasta"]:
            for entrada_rip, origem, destino in resultado["achados_em_outra_pasta"]:
                linhas.append(f"  {entrada_rip}")
                linhas.append(f"      de: {origem}")
                linhas.append(f"      pra: {destino}")
        else:
            linhas.append("  (nenhum)")
        linhas.append("")
        linhas.append(f"Duvidosos, NÃO movidos ({len(resultado['duvidosos'])}):")
        if resultado["duvidosos"]:
            for direcao, nome, parecido_com in resultado["duvidosos"]:
                linhas.append(f"  [{direcao}] {nome}")
                linhas.append(f"      parecido com: {parecido_com}")
        else:
            linhas.append("  (nenhum)")
        if resultado["nao_encontrados"]:
            linhas.append("")
            linhas.append(f"Não encontrados em pasta nenhuma ({len(resultado['nao_encontrados'])}):")
            linhas += [f"  {nome}" for nome in resultado["nao_encontrados"]]
        if resultado["erros"]:
            linhas.append("")
            linhas.append(f"Colisões, NÃO movidos ({len(resultado['erros'])}):")
            linhas += [f"  {msg}" for msg in resultado["erros"]]

        self.texto_resultado.configure(state="normal")
        self.texto_resultado.delete("1.0", "end")
        self.texto_resultado.insert("1.0", "\n".join(linhas))
        self.texto_resultado.configure(state="disabled")


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
            text="Edite as medidas existentes ou adicione um material novo. As mudanças valem para o cálculo\n"
                 "de desperdício e para o reconhecimento de categoria pelo nome do arquivo. \"Min/m²\" é\n"
                 "opcional — quantos minutos a máquina leva pra imprimir/cortar 1m² dessa categoria; se\n"
                 "preenchido, a OS mostra a estimativa de tempo de máquina ao lado do m² de cada material.",
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        cabecalho = tk.Frame(self)
        cabecalho.pack(fill="x", padx=16)
        for texto, largura in [
            ("Categoria", 16), ("Tipo", 10), ("Largura (cm)", 12), ("Compr. (cm)", 12),
            ("Min/m² (opcional)", 15), ("", 3),
        ]:
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
            self._adicionar_linha(
                categoria, dados["tipo"], dados["largura_cm"], dados["comprimento_cm"],
                dados.get("variantes", []), dados.get("minutos_por_m2", ""),
            )

        tk.Button(
            self, text="➕ Adicionar novo material", relief="flat", fg=COR_ACENTO, cursor="hand2",
            command=lambda: self._adicionar_linha("", "rolo", "", "", [], ""),
        ).pack(anchor="w", padx=16, pady=8)

        frame_botoes = tk.Frame(self)
        frame_botoes.pack(fill="x", padx=16, pady=14)
        tk.Button(frame_botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        tk.Button(frame_botoes, text="Salvar", bg=COR_ACENTO, fg="white", relief="flat", command=self._salvar).pack(side="right")

    def _adicionar_linha(self, categoria, tipo, largura, comprimento, variantes, minutos_por_m2=""):
        linha = tk.Frame(self.frame_linhas)
        linha.pack(fill="x", pady=2)

        var_categoria = tk.StringVar(value=categoria)
        var_tipo = tk.StringVar(value=tipo or "rolo")
        var_largura = tk.StringVar(value=str(largura))
        var_comprimento = tk.StringVar(value=str(comprimento))
        var_minutos_m2 = tk.StringVar(value=str(minutos_por_m2) if minutos_por_m2 else "")

        tk.Entry(linha, textvariable=var_categoria, width=16).pack(side="left")
        ttk.Combobox(linha, textvariable=var_tipo, values=["rolo", "chapa"], width=8, state="readonly").pack(side="left", padx=4)
        tk.Entry(linha, textvariable=var_largura, width=12).pack(side="left", padx=4)
        tk.Entry(linha, textvariable=var_comprimento, width=12).pack(side="left", padx=4)
        tk.Entry(linha, textvariable=var_minutos_m2, width=15).pack(side="left", padx=4)

        registro = {
            "frame": linha, "categoria": var_categoria, "tipo": var_tipo,
            "largura": var_largura, "comprimento": var_comprimento, "variantes": list(variantes or []),
            "minutos_por_m2": var_minutos_m2,
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

            texto_minutos_m2 = registro["minutos_por_m2"].get().strip().replace(",", ".")
            if texto_minutos_m2:
                try:
                    minutos_m2 = float(texto_minutos_m2)
                    if minutos_m2 <= 0:
                        raise ValueError
                except ValueError:
                    messagebox.showwarning(
                        "Valor inválido",
                        f"'Min/m²' de '{categoria}' precisa ser um número maior que zero (ou fique em branco pra não estimar tempo).",
                    )
                    return
                material["minutos_por_m2"] = minutos_m2

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

class JanelaEstoque(tk.Toplevel):
    """
    Painel de controle de estoque: saldo atual de cada produto
    cadastrado (rolo/chapa/insumo), com atalhos pra registrar entrada,
    saída manual, saída automática a partir do arquivo gerado junto com
    a OS, cadastrar produto novo na mão, e consultar/desfazer o
    histórico de movimentos.

    Layout inteiro em grid (não pack) pra ser responsivo de verdade: a
    lista de produtos ocupa a linha que sobra e cresce/encolhe junto
    com a janela, e a barra de botões fica numa grade de 3 colunas fixas
    — nunca estoura a largura da janela e "come" botão, porque cada
    botão tem sua própria célula reservada em vez de ficar todo numa
    fila só que pode passar da borda.
    """

    _NOMES_TIPO = {"rolo": "Rolo", "chapa": "Chapa", "insumo": "Insumo"}

    def __init__(self, mestre, config_dados):
        super().__init__(mestre)
        self.title("Controle de Estoque — UNY CV")
        self.geometry("860x660")
        self.minsize(740, 520)
        self.configure(bg=COR_FUNDO_JANELA)
        self.transient(mestre)
        self.config_dados = config_dados
        self.estoque = carregar_estoque()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self._montar_layout()
        self.grab_set()

    def _montar_layout(self):
        linha = 0
        if CAMINHO_LOGO_GUI.exists():
            try:
                self.imagem_logo = tk.PhotoImage(file=str(CAMINHO_LOGO_GUI))
                tk.Label(self, image=self.imagem_logo, bg=COR_FUNDO_JANELA).grid(
                    row=linha, column=0, sticky="w", padx=20, pady=(16, 0))
                linha += 1
            except tk.TclError:
                pass

        tk.Label(self, text="Saldo atual", font=("Segoe UI", 14, "bold"), bg=COR_FUNDO_JANELA, fg=COR_TEXTO).grid(
            row=linha, column=0, sticky="w", padx=20, pady=(14, 2))
        linha += 1
        tk.Label(
            self, fg=COR_TEXTO_SECUNDARIO, bg=COR_FUNDO_JANELA, justify="left", wraplength=780,
            text="Clique duas vezes num produto pra editar seus dados. Toda entrada/saída fica registrada "
                 "no histórico e pode ser desfeita.",
        ).grid(row=linha, column=0, sticky="w", padx=20, pady=(0, 10))
        linha += 1

        linha_conteudo = linha
        linha += 1

        frame_canvas = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_canvas.grid(row=linha_conteudo, column=0, sticky="nsew", padx=20)
        frame_canvas.columnconfigure(0, weight=1)
        frame_canvas.rowconfigure(0, weight=1)

        canvas = tk.Canvas(frame_canvas, highlightthickness=0, bg=COR_FUNDO_JANELA)
        scrollbar = ttk.Scrollbar(frame_canvas, orient="vertical", command=canvas.yview)
        self.frame_lista = tk.Frame(canvas, bg=COR_FUNDO_JANELA)
        janela_interna = canvas.create_window((0, 0), window=self.frame_lista, anchor="nw")
        self.frame_lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # a lista precisa acompanhar a largura real do canvas (não só a
        # largura "natural" do conteúdo) pra aproveitar o espaço quando a
        # janela é alargada — sem isso o conteúdo fica sempre esquerdo,
        # colado, mesmo numa janela bem larga
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_interna, width=e.width))
        self.frame_lista.columnconfigure(0, weight=1)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        frame_botoes = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_botoes.grid(row=linha, column=0, sticky="ew", padx=20, pady=14)
        for col in range(4):
            frame_botoes.columnconfigure(col, weight=1, uniform="botoes")

        tk.Button(
            frame_botoes, text="➕ Entrada", relief="flat", bg=COR_ACENTO, fg="white",
            activebackground=COR_ACENTO, cursor="hand2", command=lambda: self._abrir_movimento("entrada"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4), ipady=3)
        tk.Button(
            frame_botoes, text="➖ Saída manual", relief="flat", cursor="hand2",
            command=lambda: self._abrir_movimento("saida"),
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=(0, 4), ipady=3)
        tk.Button(
            frame_botoes, text="📄 Saída pela OS...", relief="flat", cursor="hand2", command=self._abrir_saida_os,
        ).grid(row=0, column=2, sticky="ew", padx=4, pady=(0, 4), ipady=3)
        tk.Button(
            frame_botoes, text="📊 Dashboard...", relief="flat", cursor="hand2", command=self._abrir_dashboard,
        ).grid(row=0, column=3, sticky="ew", padx=(4, 0), pady=(0, 4), ipady=3)
        tk.Button(
            frame_botoes, text="🧾 Cadastrar produto...", relief="flat", cursor="hand2",
            command=self._abrir_novo_produto,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 4), ipady=3)
        tk.Button(
            frame_botoes, text="🕒 Histórico", relief="flat", cursor="hand2", command=self._abrir_historico,
        ).grid(row=1, column=1, sticky="ew", padx=4, ipady=3)
        tk.Button(frame_botoes, text="Fechar", relief="flat", cursor="hand2", command=self.destroy).grid(
            row=1, column=3, sticky="ew", padx=(4, 0), ipady=3)

        self._preencher_lista()

    def _preencher_lista(self):
        for widget in self.frame_lista.winfo_children():
            widget.destroy()

        produtos = self.estoque["produtos"]
        for tipo in ["rolo", "chapa", "insumo"]:
            itens_tipo = sorted(
                [(c, p) for c, p in produtos.items() if p["tipo"] == tipo],
                key=lambda cp: cp[1]["descricao"],
            )
            if not itens_tipo:
                continue
            tk.Label(
                self.frame_lista, text=self._NOMES_TIPO[tipo].upper(), font=("Segoe UI", 9, "bold"),
                fg=COR_ACENTO, bg=COR_FUNDO_JANELA,
            ).grid(row=len(self.frame_lista.grid_slaves()), column=0, sticky="w", pady=(12, 4))
            for codigo, produto in itens_tipo:
                self._linha_produto(codigo, produto)

    def _linha_produto(self, codigo, produto):
        saldo = saldo_produto(self.estoque, codigo)
        abaixo_minimo = produto.get("minimo", 0) > 0 and saldo < produto["minimo"]

        linha_idx = len(self.frame_lista.grid_slaves())
        cartao = tk.Frame(
            self.frame_lista, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO,
            highlightthickness=1, cursor="hand2",
        )
        cartao.grid(row=linha_idx, column=0, sticky="ew", pady=3)
        cartao.columnconfigure(0, weight=1)

        clicaveis = [cartao]

        frame_esq = tk.Frame(cartao, bg=COR_CARTAO)
        frame_esq.grid(row=0, column=0, sticky="ew", padx=(12, 4), pady=9)
        clicaveis.append(frame_esq)

        texto_desc = produto["descricao"]
        if produto.get("variante_vinculada"):
            texto_desc += f"  ·  {formatar_variante(produto['variante_vinculada'])}"
        rotulo_desc = tk.Label(
            frame_esq, text=texto_desc, anchor="w", bg=COR_CARTAO, fg=COR_TEXTO, wraplength=420, justify="left",
        )
        rotulo_desc.pack(anchor="w")
        clicaveis.append(rotulo_desc)

        if abaixo_minimo:
            rotulo_badge = tk.Label(
                frame_esq, text="ABAIXO DO MÍNIMO", bg=COR_ALERTA_FUNDO, fg=COR_ALERTA,
                font=("Segoe UI", 7, "bold"), padx=6, pady=1,
            )
            rotulo_badge.pack(anchor="w", pady=(4, 0))
            clicaveis.append(rotulo_badge)

        frame_dir = tk.Frame(cartao, bg=COR_CARTAO)
        frame_dir.grid(row=0, column=1, sticky="e", padx=(4, 10), pady=9)
        clicaveis.append(frame_dir)

        texto_saldo = f"{saldo:g} {produto['unidade']}"
        acumulado = produto.get("acumulado_m", 0.0)
        if produto["tipo"] == "rolo" and acumulado > 0:
            texto_saldo += f"  (+{acumulado:.2f}m ac.)"
        rotulo_saldo = tk.Label(frame_dir, text=texto_saldo, bg=COR_CARTAO, fg=COR_TEXTO, font=("Segoe UI", 10, "bold"))
        rotulo_saldo.pack(side="left")
        clicaveis.append(rotulo_saldo)

        tem_movimento = any(m["produto"] == codigo for m in self.estoque["movimentos"])
        if not tem_movimento:
            tk.Button(
                frame_dir, text="🗑", relief="flat", bg=COR_CARTAO, fg="#b0b0b8", cursor="hand2",
                activebackground=COR_CARTAO, command=lambda: self._remover_produto(codigo, produto),
            ).pack(side="left", padx=(10, 0))

        for widget in clicaveis:
            widget.bind("<Double-Button-1>", lambda e, c=codigo: self._abrir_edicao(c))

    def _remover_produto(self, codigo, produto):
        if not messagebox.askyesno("Remover produto", f"Remover '{produto['descricao']}' do estoque?"):
            return
        remover_produto(self.estoque, codigo)
        self._atualizar()

    def _atualizar(self):
        self.estoque = carregar_estoque()
        self._preencher_lista()

    def _abrir_movimento(self, tipo):
        JanelaMovimentoManual(self, self.estoque, tipo, self._atualizar)

    def _abrir_saida_os(self):
        JanelaSaidaOS(self, self.estoque, self.config_dados, self._atualizar)

    def _abrir_historico(self):
        JanelaHistorico(self, self.estoque, self._atualizar)

    def _abrir_novo_produto(self):
        JanelaNovoProduto(self, self.estoque, self.config_dados, self._atualizar)

    def _abrir_edicao(self, codigo):
        JanelaNovoProduto(self, self.estoque, self.config_dados, self._atualizar, codigo_edicao=codigo)

    def _abrir_dashboard(self):
        JanelaDashboard(self, self.estoque)


class JanelaMovimentoManual(tk.Toplevel):
    """Formulário simples de entrada ou saída manual de um produto."""

    def __init__(self, mestre, estoque, tipo, ao_salvar):
        super().__init__(mestre)
        self.title("Entrada de material" if tipo == "entrada" else "Saída manual de material")
        self.geometry("420x280")
        self.transient(mestre)
        self.estoque = estoque
        self.tipo = tipo
        self.ao_salvar = ao_salvar

        self.produtos_ordenados = sorted(estoque["produtos"].items(), key=lambda cp: cp[1]["descricao"])
        rotulos = [p["descricao"] for _, p in self.produtos_ordenados]

        pad = {"padx": 16, "pady": 6}
        tk.Label(self, text="Produto").pack(anchor="w", **pad)
        self.var_produto = tk.StringVar(value=rotulos[0] if rotulos else "")
        ttk.Combobox(self, textvariable=self.var_produto, values=rotulos, state="readonly").pack(fill="x", padx=16)

        tk.Label(self, text="Quantidade").pack(anchor="w", **pad)
        self.var_quantidade = tk.StringVar()
        tk.Entry(self, textvariable=self.var_quantidade).pack(fill="x", padx=16)

        tk.Label(self, text="Observação (opcional)").pack(anchor="w", **pad)
        self.var_obs = tk.StringVar()
        tk.Entry(self, textvariable=self.var_obs).pack(fill="x", padx=16)

        frame_botoes = tk.Frame(self)
        frame_botoes.pack(fill="x", padx=16, pady=16)
        tk.Button(frame_botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        tk.Button(
            frame_botoes, text="Salvar", bg=COR_ACENTO, fg="white", relief="flat", command=self._salvar,
        ).pack(side="right")

        self.grab_set()

    def _salvar(self):
        if not self.produtos_ordenados:
            messagebox.showwarning("Sem produtos", "Nenhum produto cadastrado no estoque.")
            return
        rotulos = [p["descricao"] for _, p in self.produtos_ordenados]
        try:
            indice = rotulos.index(self.var_produto.get())
        except ValueError:
            messagebox.showwarning("Produto inválido", "Escolha um produto da lista.")
            return
        codigo, produto = self.produtos_ordenados[indice]

        texto_qtd = self.var_quantidade.get().strip().replace(",", ".")
        try:
            quantidade = float(texto_qtd)
            if quantidade <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Quantidade inválida", "Informe uma quantidade maior que zero.")
            return

        sinal = 1 if self.tipo == "entrada" else -1
        registrar_movimento(
            self.estoque, codigo, self.tipo, sinal * quantidade, observacao=self.var_obs.get().strip(),
        )
        saldo_novo = saldo_produto(self.estoque, codigo)
        self.ao_salvar()
        if saldo_novo < 0:
            messagebox.showwarning(
                "Estoque negativo",
                f"'{produto['descricao']}' ficou com saldo negativo ({saldo_novo:g} {produto['unidade']}). "
                f"O lançamento foi salvo mesmo assim — confira se está correto.",
            )
        self.destroy()


class JanelaSaidaOS(tk.Toplevel):
    """
    Dá baixa no estoque a partir do arquivo JSON gerado junto com a OS
    (nunca a partir do PDF direto — ver relatorios.salvar_dados_os).
    Sempre mostra uma prévia do que seria descontado antes de confirmar,
    e nunca escolhe sozinho qual produto debitar quando há mais de um
    possível pra mesma categoria (caso do ADESIVO).
    """

    def __init__(self, mestre, estoque, config_dados, ao_salvar):
        super().__init__(mestre)
        self.title("Saída pela OS")
        self.geometry("560x500")
        self.transient(mestre)
        self.estoque = estoque
        self.config_dados = config_dados
        self.ao_salvar = ao_salvar
        self.dados_os = None
        self.previsao = None
        self.resolucoes_manuais = {}

        pad = {"padx": 16, "pady": 6}
        tk.Label(self, text="Escolha o arquivo da OS", font=("Segoe UI", 11, "bold")).pack(anchor="w", **pad)
        tk.Label(
            self, fg="#666666", justify="left", wraplength=520,
            text='Esse arquivo fica na mesma pasta do PDF da OS ("OS - CLIENTE.json"). A escolha é sempre '
                 "manual, pra evitar dar baixa com o pedido errado.",
        ).pack(anchor="w", padx=16)

        tk.Button(
            self, text="📂 Escolher arquivo...", relief="flat", fg=COR_ACENTO, cursor="hand2",
            command=self._escolher_arquivo,
        ).pack(anchor="w", padx=16, pady=8)

        self.var_arquivo = tk.StringVar(value="Nenhum arquivo escolhido.")
        tk.Label(self, textvariable=self.var_arquivo, fg="#333333", wraplength=520, justify="left").pack(anchor="w", padx=16)

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.frame_previa = tk.Frame(canvas)
        self.frame_previa.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.frame_previa, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(16, 0), pady=8)
        scrollbar.pack(side="left", fill="y", padx=(0, 16), pady=8)

        frame_botoes = tk.Frame(self)
        frame_botoes.pack(fill="x", padx=16, pady=12)
        tk.Button(frame_botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        self.btn_confirmar = tk.Button(
            frame_botoes, text="Confirmar baixa", bg=COR_ACENTO, fg="white", relief="flat",
            state="disabled", command=self._confirmar,
        )
        self.btn_confirmar.pack(side="right")

        self.grab_set()

    def _escolher_arquivo(self):
        pasta_entrada = pathlib.Path("etiquetas_geradas")
        caminho = filedialog.askopenfilename(
            title="Escolha o arquivo da OS (.json)", filetypes=[("Arquivo da OS", "*.json")],
            initialdir=str(pasta_entrada.resolve()) if pasta_entrada.exists() else None,
        )
        if not caminho:
            return
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                self.dados_os = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror("Arquivo inválido", f"Não foi possível ler esse arquivo:\n{e}")
            return

        self.var_arquivo.set(
            f"{pathlib.Path(caminho).name} — Cliente: {self.dados_os.get('cliente', '?')} "
            f"({self.dados_os.get('data_hora', '?')})"
        )
        self.resolucoes_manuais = {}
        self.previsao = prever_saida_os(self.estoque, self.dados_os["itens"], self.config_dados["materiais"])
        self._mostrar_previa()
        self.btn_confirmar.configure(state="normal")

    def _resolver_ambiguidade(self, categoria, codigo):
        self.resolucoes_manuais[categoria] = codigo
        self.previsao = prever_saida_os(
            self.estoque, self.dados_os["itens"], self.config_dados["materiais"], self.resolucoes_manuais,
        )
        self._mostrar_previa()

    def _nome_pedido(self):
        return f"{self.dados_os.get('cliente', '?')} ({self.dados_os.get('data_hora', '?')})"

    def _mostrar_previa(self):
        for widget in self.frame_previa.winfo_children():
            widget.destroy()

        # aviso ANTES da lista de itens, bem visível — evita que a
        # mesma OS seja escolhida duas vezes (ou confirmada duas vezes
        # sem querer) e dobre o consumo no estoque silenciosamente
        if pedido_ja_teve_saida(self.estoque, self._nome_pedido()):
            tk.Label(
                self.frame_previa,
                text="⚠ Esse pedido já teve baixa registrada antes. Confirmar de novo vai DOBRAR o consumo.",
                fg=COR_ALERTA, bg=COR_ALERTA_FUNDO, anchor="w", justify="left", wraplength=500,
                font=("Segoe UI", 9, "bold"), padx=8, pady=4,
            ).pack(anchor="w", pady=(0, 8), fill="x")

        for linha in self.previsao:
            variante_txt = f" · {formatar_variante(linha['variante'])}" if linha.get("variante") else ""
            if linha["produto"] is None and linha.get("ambiguo"):
                candidatos = produtos_por_categoria(self.estoque, linha["categoria"])
                descricoes = {produto["descricao"]: codigo for codigo, produto in candidatos}

                frame_item = tk.Frame(self.frame_previa)
                frame_item.pack(anchor="w", fill="x", pady=4)
                tk.Label(
                    frame_item, text=f"{linha['categoria']}{variante_txt} — mais de um produto possível, escolha qual baixar:",
                    anchor="w", fg=COR_ALERTA, justify="left", wraplength=500,
                ).pack(anchor="w")

                var_escolha = tk.StringVar()
                codigo_ja_escolhido = self.resolucoes_manuais.get(linha["categoria"])
                for descricao, codigo in descricoes.items():
                    if codigo == codigo_ja_escolhido:
                        var_escolha.set(descricao)
                        break
                combo = ttk.Combobox(frame_item, textvariable=var_escolha, values=list(descricoes.keys()), state="readonly", width=45)
                combo.bind(
                    "<<ComboboxSelected>>",
                    lambda evento, categoria=linha["categoria"], descricoes=descricoes, var=var_escolha:
                        self._resolver_ambiguidade(categoria, descricoes[var.get()]),
                )
                combo.pack(anchor="w", pady=(2, 0))
                continue

            if linha["produto"] is None:
                motivo = "mais de um produto possível, dê baixa manual" if linha.get("ambiguo") else "sem produto vinculado no estoque"
                texto = f"{linha['categoria']}{variante_txt} — {motivo}"
                cor = COR_ALERTA
            else:
                texto = (
                    f"{linha['produto']} — baixa de {linha['descontado']:g} {linha['unidade']} "
                    f"(saldo ficaria: {linha['saldo_resultante']:g})"
                )
                cor = COR_TEXTO
            tk.Label(
                self.frame_previa, text=texto, anchor="w", fg=cor, justify="left", wraplength=500,
            ).pack(anchor="w", pady=2)

    def _confirmar(self):
        if not self.dados_os:
            return
        nome_pedido = self._nome_pedido()
        if pedido_ja_teve_saida(self.estoque, nome_pedido):
            if not messagebox.askyesno(
                "Baixa já registrada",
                f"Esse pedido ({nome_pedido}) já teve baixa registrada antes. Confirmar de novo vai "
                "DOBRAR o consumo no estoque. Tem certeza que quer lançar mesmo assim?",
                icon="warning",
            ):
                return
        resumo = confirmar_saida_os(
            self.estoque, self.dados_os["itens"], self.config_dados["materiais"], nome_pedido, self.resolucoes_manuais,
        )
        negativos = [r for r in resumo if r["saldo_resultante"] is not None and r["saldo_resultante"] < 0]
        self.ao_salvar()
        if negativos:
            nomes = ", ".join(r["produto"] for r in negativos)
            messagebox.showwarning(
                "Baixa concluída — atenção",
                f"Baixa registrada no estoque. Ficou negativo em: {nomes}. Confira se está correto.",
            )
        else:
            messagebox.showinfo("Baixa concluída", "Estoque atualizado com sucesso.")
        self.destroy()


class JanelaHistorico(tk.Toplevel):
    """Lista os movimentos de estoque (mais recente primeiro), com opção de desfazer cada um."""

    def __init__(self, mestre, estoque, ao_salvar):
        super().__init__(mestre)
        self.title("Histórico de movimentos")
        self.geometry("640x480")
        self.transient(mestre)
        self.estoque = estoque
        self.ao_salvar = ao_salvar

        tk.Label(
            self, text="Movimentos mais recentes primeiro", font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.frame_lista = tk.Frame(canvas)
        self.frame_lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.frame_lista, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(16, 0))
        scrollbar.pack(side="left", fill="y", padx=(0, 16))

        tk.Button(self, text="Fechar", command=self.destroy).pack(anchor="e", padx=16, pady=12)

        self._preencher()
        self.grab_set()

    def _preencher(self):
        for widget in self.frame_lista.winfo_children():
            widget.destroy()

        movimentos = list(reversed(self.estoque["movimentos"]))
        ids_estornados = {m["estorno_de"] for m in self.estoque["movimentos"] if m.get("estorno_de")}

        if not movimentos:
            tk.Label(self.frame_lista, text="Nenhum movimento registrado ainda.", fg="#666666").pack(anchor="w", pady=10)
            return

        for mov in movimentos:
            produto = self.estoque["produtos"].get(mov["produto"])
            nome_produto = produto["descricao"] if produto else mov["produto"]
            unidade = produto["unidade"] if produto else ""

            linha = tk.Frame(self.frame_lista)
            linha.pack(fill="x", pady=3)

            sinal = "+" if mov["quantidade"] > 0 else ""
            cor = COR_POSITIVO if mov["quantidade"] > 0 else COR_TEXTO
            texto = f"{mov['data']} · {nome_produto} · {sinal}{mov['quantidade']:g} {unidade}"
            if mov.get("observacao"):
                texto += f" · {mov['observacao']}"
            if mov.get("origem_pedido"):
                texto += f" · Pedido: {mov['origem_pedido']}"

            tk.Label(linha, text=texto, fg=cor, anchor="w", justify="left", wraplength=460).pack(side="left", fill="x", expand=True)

            e_estorno = mov.get("estorno_de") is not None
            ja_estornado = mov["id"] in ids_estornados
            if not e_estorno and not ja_estornado:
                tk.Button(
                    linha, text="Desfazer", relief="flat", fg="#c92a2a", cursor="hand2",
                    command=lambda mid=mov["id"]: self._desfazer(mid),
                ).pack(side="right")

    def _desfazer(self, movimento_id):
        if not messagebox.askyesno(
            "Desfazer movimento",
            "Confirma desfazer esse lançamento? Um lançamento de estorno será criado "
            "(o histórico original não é apagado).",
        ):
            return
        desfazer_movimento(self.estoque, movimento_id)
        self.ao_salvar()
        self._preencher()


class JanelaNovoProduto(tk.Toplevel):
    """
    Cadastro manual de um produto no estoque — tanto pra criar um novo
    (pra quando aparece um material que não veio na leva inicial da
    planilha) quanto pra editar um já existente (aberta com duplo
    clique num produto na lista, via `codigo_edicao`). Os campos mudam
    de acordo com o tipo escolhido: espessura/cor (a "variação")
    aparecem só pra chapa, e a metragem do rolo aparece só pra rolo —
    mesmo espírito da tela de variantes de material (JanelaVariantes),
    só que aqui cadastra o produto de estoque inteiro, não só a
    variante.
    """

    def __init__(self, mestre, estoque, config_dados, ao_salvar, codigo_edicao=None):
        super().__init__(mestre)
        self.codigo_edicao = codigo_edicao
        self.produto_original = estoque["produtos"][codigo_edicao] if codigo_edicao else None
        self.title("Editar produto" if codigo_edicao else "Cadastrar produto novo")
        self.geometry("460x580")
        self.minsize(420, 500)
        self.configure(bg=COR_FUNDO_JANELA)
        self.transient(mestre)
        self.estoque = estoque
        self.config_dados = config_dados
        self.ao_salvar = ao_salvar

        self._montar_layout()
        self.grab_set()

    def _montar_layout(self):
        pad = {"padx": 16, "pady": 6}
        p = self.produto_original

        tk.Label(self, text="Descrição do produto", bg=COR_FUNDO_JANELA).pack(anchor="w", **pad)
        self.var_descricao = tk.StringVar(value=p["descricao"] if p else "")
        tk.Entry(self, textvariable=self.var_descricao).pack(fill="x", padx=16)

        tk.Label(self, text="Tipo", bg=COR_FUNDO_JANELA).pack(anchor="w", **pad)
        self.var_tipo = tk.StringVar(value=p["tipo"] if p else "chapa")
        combo_tipo = ttk.Combobox(
            self, textvariable=self.var_tipo, values=["rolo", "chapa", "insumo"], state="readonly",
        )
        combo_tipo.pack(fill="x", padx=16)
        combo_tipo.bind("<<ComboboxSelected>>", lambda e: self._atualizar_campos_por_tipo())

        tk.Label(self, text="Categoria vinculada (pra baixa automática pela OS)", bg=COR_FUNDO_JANELA).pack(
            anchor="w", **pad)
        categorias = ["(sem vínculo — insumo avulso)"] + list(self.config_dados["materiais"].keys())
        valor_categoria = (p["categoria_vinculada"] if p and p.get("categoria_vinculada") else categorias[0])
        self.var_categoria = tk.StringVar(value=valor_categoria)
        ttk.Combobox(self, textvariable=self.var_categoria, values=categorias, state="readonly").pack(fill="x", padx=16)

        # área que muda de acordo com o tipo escolhido — os "espaços pra
        # variação" (espessura/cor) pra chapa, ou a metragem do rolo
        self.frame_dinamico = tk.Frame(self, bg=COR_FUNDO_JANELA)
        self.frame_dinamico.pack(fill="x", padx=16, pady=(8, 0))

        variante_atual = (p.get("variante_vinculada") or {}) if p else {}
        self.var_espessura = tk.StringVar(value=variante_atual.get("espessura", ""))
        self.var_cor = tk.StringVar(value=variante_atual.get("cor", ""))
        self.var_comprimento_rolo = tk.StringVar(value=str(p["comprimento_rolo_m"]) if p and p.get("tipo") == "rolo" else "50")
        self.var_unidade = tk.StringVar(value=p["unidade"] if p else "un")

        frame_min_max = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_min_max.pack(fill="x", padx=16, pady=(10, 6))
        col1 = tk.Frame(frame_min_max, bg=COR_FUNDO_JANELA)
        col1.pack(side="left", fill="x", expand=True)
        col2 = tk.Frame(frame_min_max, bg=COR_FUNDO_JANELA)
        col2.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(col1, text="Estoque mínimo", bg=COR_FUNDO_JANELA).pack(anchor="w")
        self.var_minimo = tk.StringVar(value=str(p["minimo"]) if p else "0")
        tk.Entry(col1, textvariable=self.var_minimo).pack(fill="x")
        tk.Label(col2, text="Estoque máximo", bg=COR_FUNDO_JANELA).pack(anchor="w")
        self.var_maximo = tk.StringVar(value=str(p["maximo"]) if p else "0")
        tk.Entry(col2, textvariable=self.var_maximo).pack(fill="x")

        tk.Label(self, text="Código da planilha (opcional)", bg=COR_FUNDO_JANELA).pack(anchor="w", padx=16, pady=(4, 2))
        self.var_codigo_planilha = tk.StringVar(value=(p.get("codigo_planilha") or "") if p else "")
        tk.Entry(self, textvariable=self.var_codigo_planilha).pack(fill="x", padx=16)

        if p:
            saldo_atual = saldo_produto(self.estoque, self.codigo_edicao)
            tk.Label(
                self, bg=COR_FUNDO_JANELA, fg=COR_TEXTO_SECUNDARIO,
                text=f"Saldo atual: {saldo_atual:g} {p['unidade']} (editar aqui não muda o saldo — "
                     f"use entrada/saída/histórico pra isso).",
                justify="left", wraplength=420,
            ).pack(anchor="w", padx=16, pady=(6, 0))

        frame_botoes = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_botoes.pack(fill="x", padx=16, pady=16)
        tk.Button(frame_botoes, text="Cancelar", relief="flat", cursor="hand2", command=self.destroy).pack(
            side="right", padx=(6, 0))
        tk.Button(
            frame_botoes, text="Salvar alterações" if self.codigo_edicao else "Cadastrar",
            bg=COR_ACENTO, fg="white", relief="flat", cursor="hand2", command=self._salvar,
        ).pack(side="right")

        self._atualizar_campos_por_tipo()

    def _atualizar_campos_por_tipo(self):
        for widget in self.frame_dinamico.winfo_children():
            widget.destroy()

        tipo = self.var_tipo.get()
        if tipo == "chapa":
            tk.Label(
                self.frame_dinamico, text="Variação (opcional)", font=("Segoe UI", 9, "bold"), fg="#666666",
            ).pack(anchor="w")
            linha = tk.Frame(self.frame_dinamico)
            linha.pack(fill="x", pady=2)
            tk.Label(linha, text="Espessura").pack(side="left")
            tk.Entry(linha, textvariable=self.var_espessura, width=10).pack(side="left", padx=(4, 10))
            tk.Label(linha, text="Cor").pack(side="left")
            tk.Entry(linha, textvariable=self.var_cor, width=12).pack(side="left", padx=4)
            tk.Label(
                self.frame_dinamico, fg="#888888", wraplength=400, justify="left",
                text="Preenchendo espessura/cor, esse produto casa automaticamente com a variante equivalente "
                     "das etiquetas (ex: 10MM + BRANCO) na hora da baixa pela OS.",
            ).pack(anchor="w", pady=(2, 0))
            tk.Label(self.frame_dinamico, text="Unidade").pack(anchor="w", pady=(8, 0))
            self.var_unidade.set("chapa")
            tk.Entry(self.frame_dinamico, textvariable=self.var_unidade).pack(fill="x")
        elif tipo == "rolo":
            tk.Label(self.frame_dinamico, text="Comprimento do rolo (metros)").pack(anchor="w")
            tk.Entry(self.frame_dinamico, textvariable=self.var_comprimento_rolo).pack(fill="x")
            self.var_unidade.set("rolo")
        else:
            tk.Label(self.frame_dinamico, text="Unidade (ex: un, caixa, litro)").pack(anchor="w")
            self.var_unidade.set(self.var_unidade.get() or "un")
            tk.Entry(self.frame_dinamico, textvariable=self.var_unidade).pack(fill="x")

    def _salvar(self):
        descricao = self.var_descricao.get().strip()
        if not descricao:
            messagebox.showwarning("Campo obrigatório", "Informe a descrição do produto.")
            return

        tipo = self.var_tipo.get()
        categoria_escolhida = self.var_categoria.get()
        categoria_vinculada = None if categoria_escolhida.startswith("(sem vínculo") else categoria_escolhida

        espessura = self.var_espessura.get().strip().upper()
        cor = self.var_cor.get().strip().upper()
        variante = None
        if tipo == "chapa" and espessura:
            variante = {"espessura": espessura}
            if cor:
                variante["cor"] = cor

        comprimento_rolo_m = None
        if tipo == "rolo":
            texto = self.var_comprimento_rolo.get().strip().replace(",", ".")
            try:
                comprimento_rolo_m = float(texto)
                if comprimento_rolo_m <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Valor inválido", "Informe o comprimento do rolo em metros (maior que zero).")
                return

        try:
            minimo = float(self.var_minimo.get().strip().replace(",", ".") or 0)
            maximo = float(self.var_maximo.get().strip().replace(",", ".") or 0)
        except ValueError:
            messagebox.showwarning("Valor inválido", "Mínimo e máximo precisam ser números.")
            return

        unidade = self.var_unidade.get().strip() or None
        codigo_planilha = self.var_codigo_planilha.get().strip() or None

        if self.codigo_edicao:
            atualizar_produto(
                self.estoque, self.codigo_edicao, tipo, descricao, unidade=unidade,
                categoria_vinculada=categoria_vinculada, variante=variante,
                comprimento_rolo_m=comprimento_rolo_m, minimo=minimo, maximo=maximo,
                codigo_planilha=codigo_planilha,
            )
            self.ao_salvar()
            messagebox.showinfo("Alterações salvas", f"'{descricao}' foi atualizado.")
        else:
            produto = novo_produto(
                tipo, descricao, unidade=unidade, categoria_vinculada=categoria_vinculada, variante=variante,
                comprimento_rolo_m=comprimento_rolo_m, minimo=minimo, maximo=maximo,
                codigo_planilha=codigo_planilha,
            )
            adicionar_produto(self.estoque, produto)
            self.ao_salvar()
            messagebox.showinfo("Produto cadastrado", f"'{descricao}' foi adicionado ao estoque com saldo zero.")
        self.destroy()


class JanelaDashboard(tk.Toplevel):
    """
    Dashboard do estoque: pra um mês escolhido (com navegação ◀ ▶),
    mostra o volume COMPLETO de entrada e de saída de cada produto que
    teve movimento nesse mês — não um "top N" resumido, a lista inteira
    do maior pro menor, cada uma com uma barrinha proporcional — mais a
    contagem de lançamentos e quais produtos estão abaixo do mínimo
    agora. Cada linha do ranking é sempre de um produto só, com a
    unidade dele: nunca soma quantidade entre produtos de unidades
    diferentes (chapa com rolo, por exemplo), mesmo princípio já usado
    no resto do sistema pros subtotais de m².
    """

    _NOMES_MES = [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]

    def __init__(self, mestre, estoque):
        super().__init__(mestre)
        self.title("Dashboard de Estoque — UNY CV")
        self.geometry("880x680")
        self.minsize(720, 520)
        self.configure(bg=COR_FUNDO_JANELA)
        self.transient(mestre)
        self.estoque = estoque

        hoje = date.today()
        meses = meses_disponiveis(estoque)
        self.ano_mes_atual = meses[0] if meses else (hoje.year, hoje.month)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self._montar_layout()
        self.grab_set()

    def _montar_layout(self):
        linha = 0
        if CAMINHO_LOGO_GUI.exists():
            try:
                self.imagem_logo = tk.PhotoImage(file=str(CAMINHO_LOGO_GUI))
                tk.Label(self, image=self.imagem_logo, bg=COR_FUNDO_JANELA).grid(
                    row=linha, column=0, sticky="w", padx=20, pady=(16, 0))
                linha += 1
            except tk.TclError:
                pass

        tk.Label(
            self, text="Dashboard de Estoque", font=("Segoe UI", 14, "bold"), bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
        ).grid(row=linha, column=0, sticky="w", padx=20, pady=(14, 6))
        linha += 1

        frame_mes = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_mes.grid(row=linha, column=0, sticky="w", padx=20, pady=(0, 10))
        tk.Button(frame_mes, text="◀", relief="flat", cursor="hand2", command=self._mes_anterior).pack(side="left")
        self.var_mes_label = tk.StringVar()
        tk.Label(
            frame_mes, textvariable=self.var_mes_label, font=("Segoe UI", 11, "bold"), bg=COR_FUNDO_JANELA,
            fg=COR_TEXTO, width=16, anchor="center",
        ).pack(side="left", padx=6)
        tk.Button(frame_mes, text="▶", relief="flat", cursor="hand2", command=self._mes_seguinte).pack(side="left")
        linha += 1

        self.frame_cards = tk.Frame(self, bg=COR_FUNDO_JANELA)
        self.frame_cards.grid(row=linha, column=0, sticky="ew", padx=20, pady=(0, 10))
        linha += 1

        linha_conteudo = linha
        linha += 1

        frame_canvas = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_canvas.grid(row=linha_conteudo, column=0, sticky="nsew", padx=20)
        frame_canvas.columnconfigure(0, weight=1)
        frame_canvas.rowconfigure(0, weight=1)
        canvas = tk.Canvas(frame_canvas, highlightthickness=0, bg=COR_FUNDO_JANELA)
        scrollbar = ttk.Scrollbar(frame_canvas, orient="vertical", command=canvas.yview)
        self.frame_conteudo = tk.Frame(canvas, bg=COR_FUNDO_JANELA)
        janela_interna = canvas.create_window((0, 0), window=self.frame_conteudo, anchor="nw")
        self.frame_conteudo.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_interna, width=e.width))
        self.frame_conteudo.columnconfigure(0, weight=1)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        frame_botoes = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_botoes.grid(row=linha, column=0, sticky="e", padx=20, pady=14)
        tk.Button(frame_botoes, text="Fechar", relief="flat", cursor="hand2", command=self.destroy).pack()

        self._atualizar()

    def _mes_anterior(self):
        ano, mes = self.ano_mes_atual
        self.ano_mes_atual = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
        self._atualizar()

    def _mes_seguinte(self):
        ano, mes = self.ano_mes_atual
        self.ano_mes_atual = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
        self._atualizar()

    def _atualizar(self):
        ano, mes = self.ano_mes_atual
        self.var_mes_label.set(f"{self._NOMES_MES[mes]}/{ano}")
        resumo = resumo_mensal(self.estoque, ano, mes)
        rendimento = rendimento_tinta_mensal(self.estoque, ano, mes)
        self._preencher_cards(resumo)
        self._preencher_conteudo(resumo, rendimento)

    def _preencher_cards(self, resumo):
        for widget in self.frame_cards.winfo_children():
            widget.destroy()

        cards = [
            ("Lançamentos no mês", str(resumo["total_lancamentos"]), COR_TEXTO),
            ("Entradas", str(resumo["total_entradas_lancamentos"]), COR_POSITIVO),
            ("Saídas", str(resumo["total_saidas_lancamentos"]), COR_TEXTO),
            ("Abaixo do mínimo (hoje)", str(len(resumo["produtos_abaixo_minimo"])), COR_ALERTA),
        ]
        for i, (rotulo, valor, cor) in enumerate(cards):
            self.frame_cards.columnconfigure(i, weight=1)
            cartao = tk.Frame(
                self.frame_cards, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1,
            )
            cartao.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            tk.Label(cartao, text=valor, font=("Segoe UI", 18, "bold"), bg=COR_CARTAO, fg=cor).pack(
                anchor="w", padx=12, pady=(10, 0))
            tk.Label(cartao, text=rotulo, font=("Segoe UI", 8), bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO).pack(
                anchor="w", padx=12, pady=(0, 10))

    def _preencher_conteudo(self, resumo, rendimento):
        for widget in self.frame_conteudo.winfo_children():
            widget.destroy()

        self._secao_ranking(
            "📦 Volume de entrada no mês — todos os produtos, do maior pro menor",
            resumo["ranking_entradas"], COR_POSITIVO,
        )
        self._secao_ranking(
            "📤 Volume de saída no mês — todos os produtos, do maior pro menor",
            resumo["ranking_saidas"], COR_ACENTO,
        )
        self._secao_rendimento_tinta(rendimento)

        if resumo["produtos_abaixo_minimo"]:
            tk.Label(
                self.frame_conteudo, text="ABAIXO DO MÍNIMO AGORA", font=("Segoe UI", 9, "bold"),
                fg=COR_ALERTA, bg=COR_FUNDO_JANELA,
            ).grid(row=len(self.frame_conteudo.grid_slaves()), column=0, sticky="w", pady=(16, 4))
            nomes = ", ".join(self.estoque["produtos"][c]["descricao"] for c in resumo["produtos_abaixo_minimo"])
            tk.Label(
                self.frame_conteudo, text=nomes, fg=COR_TEXTO_SECUNDARIO, bg=COR_FUNDO_JANELA,
                wraplength=800, justify="left",
            ).grid(row=len(self.frame_conteudo.grid_slaves()), column=0, sticky="w")

    def _secao_rendimento_tinta(self, rendimento):
        """
        Rendimento real de tinta por máquina (ADESIVO sai pela UJV100-160,
        LONA sai pela SWJ-320EA — regra do usuário). A Mimaki não publica
        um mL/m² fixo pra nenhuma das duas (depende da cobertura de cada
        arte), então esse número é calculado a partir do uso real: tinta
        consumida no mês ÷ m² produzidos no mês, os dois vindos do próprio
        histórico do estoque — fica mais preciso que qualquer tabela
        genérica porque reflete o mix de trabalho real da empresa.
        """
        tk.Label(
            self.frame_conteudo, text="🖨️ Rendimento de tinta por máquina",
            font=("Segoe UI", 10, "bold"), fg=COR_TEXTO, bg=COR_FUNDO_JANELA,
        ).grid(row=len(self.frame_conteudo.grid_slaves()), column=0, sticky="w", pady=(14, 6))

        for maquina, dados in rendimento.items():
            linha = tk.Frame(
                self.frame_conteudo, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1,
            )
            linha.grid(row=len(self.frame_conteudo.grid_slaves()), column=0, sticky="ew", pady=3)
            linha.columnconfigure(0, weight=1)

            tk.Label(
                linha, text=f"{maquina}  ·  {dados['categoria']}", anchor="w", bg=COR_CARTAO, fg=COR_TEXTO,
            ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))

            if dados["rendimento_ml_m2"] is not None:
                texto_valor = f"{dados['rendimento_ml_m2']:.1f} mL/m²"
                cor_valor = COR_TEXTO
            else:
                texto_valor = "dados insuficientes ainda"
                cor_valor = COR_TEXTO_SECUNDARIO
            tk.Label(
                linha, text=texto_valor, anchor="e", bg=COR_CARTAO, fg=cor_valor, font=("Segoe UI", 10, "bold"),
            ).grid(row=0, column=1, sticky="e", padx=12, pady=(8, 0))

            tk.Label(
                linha, text=f"{dados['tinta_ml']:.0f} mL de tinta consumida  ·  {dados['area_m2']:.2f} m² produzidos no mês",
                anchor="w", bg=COR_CARTAO, fg=COR_TEXTO_SECUNDARIO, font=("Segoe UI", 8),
            ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

    def _secao_ranking(self, titulo, ranking, cor_barra):
        tk.Label(
            self.frame_conteudo, text=titulo, font=("Segoe UI", 10, "bold"), fg=COR_TEXTO, bg=COR_FUNDO_JANELA,
        ).grid(row=len(self.frame_conteudo.grid_slaves()), column=0, sticky="w", pady=(6, 6))

        if not ranking:
            tk.Label(
                self.frame_conteudo, text="Nenhum movimento nesse mês.", fg=COR_TEXTO_SECUNDARIO, bg=COR_FUNDO_JANELA,
            ).grid(row=len(self.frame_conteudo.grid_slaves()), column=0, sticky="w", pady=(0, 8))
            return

        valor_maximo = ranking[0][1]
        largura_max = 240
        for codigo, valor in ranking:
            produto = self.estoque["produtos"].get(codigo)
            if not produto:
                continue

            linha = tk.Frame(self.frame_conteudo, bg=COR_FUNDO_JANELA)
            linha.grid(row=len(self.frame_conteudo.grid_slaves()), column=0, sticky="ew", pady=(2, 0))
            linha.columnconfigure(0, weight=1)
            tk.Label(linha, text=produto["descricao"], anchor="w", bg=COR_FUNDO_JANELA, fg=COR_TEXTO).grid(
                row=0, column=0, sticky="ew")
            tk.Label(
                linha, text=f"{valor:g} {produto['unidade']}", anchor="e", bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
                font=("Segoe UI", 9, "bold"), width=14,
            ).grid(row=0, column=1, sticky="e", padx=(8, 0))

            largura = max(4, int((valor / valor_maximo) * largura_max)) if valor_maximo > 0 else 4
            barra_fundo = tk.Frame(self.frame_conteudo, bg="#e9eaee", height=6, width=largura_max)
            barra_fundo.grid_propagate(False)
            barra_fundo.grid(row=len(self.frame_conteudo.grid_slaves()), column=0, sticky="w", pady=(0, 7))
            tk.Frame(barra_fundo, bg=cor_barra, height=6, width=largura).place(x=0, y=0)


class JanelaEnviarImpressao(tk.Toplevel):
    """
    Manda pra fila das máquinas o que está numa pasta de produção.

    Fluxo em três tempos, na ordem em que o usuário pediu (2026-09-05):
    escolhe a pasta -> marca e confere -> envia. Entre marcar e enviar
    entra a conferência: nada se mexe até ela passar.

    Duas regras de tela que vêm direto do usuário:
      - Nada vem marcado. A lista mistura material de vários dias e um
        clique distraído mandaria arte que não devia.
      - A máquina sugerida NUNCA fica travada: "não sabemos o que pode
        acontecer no meio de uma produção".
    """

    def __init__(self, mestre, config_dados):
        super().__init__(mestre)
        self.title("Enviar para impressão — UNY CV")
        self.geometry("1120x680")
        self.minsize(900, 520)
        self.configure(bg=COR_FUNDO_JANELA)
        self.transient(mestre)

        self.config_dados = config_dados
        self.pasta = None
        self.itens = []
        self.marcados = {}     # índice do item -> BooleanVar
        self.combos_maquina = {}   # índice do item -> StringVar da máquina escolhida
        self.envios_anteriores = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._montar_layout()
        self.grab_set()
        self.after(80, self._escolher_pasta)

    # ---------- montagem ----------

    def _montar_layout(self):
        tk.Label(
            self, text="Enviar para impressão", font=("Segoe UI", 14, "bold"),
            bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 2))

        barra = tk.Frame(self, bg=COR_FUNDO_JANELA)
        barra.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 8))
        barra.columnconfigure(0, weight=1)

        self.var_pasta = tk.StringVar(value="Nenhuma pasta escolhida")
        tk.Label(
            barra, textvariable=self.var_pasta, bg=COR_CARTAO, fg=COR_TEXTO, anchor="w",
            relief="solid", bd=1, padx=8, pady=4, font=("Consolas", 9),
        ).grid(row=0, column=0, sticky="ew")
        tk.Button(barra, text="📁 Trocar pasta...", relief="flat", cursor="hand2",
                  command=self._escolher_pasta).grid(row=0, column=1, padx=(6, 0))
        tk.Button(barra, text="↻", width=3, relief="flat", cursor="hand2",
                  command=self._recarregar).grid(row=0, column=2, padx=(4, 0))

        self.var_contagem = tk.StringVar(value="")
        tk.Label(barra, textvariable=self.var_contagem, bg=COR_FUNDO_JANELA, fg=COR_TEXTO_SECUNDARIO).grid(
            row=0, column=3, padx=(10, 0))

        frame_canvas = tk.Frame(self, bg=COR_FUNDO_JANELA)
        frame_canvas.grid(row=2, column=0, sticky="nsew", padx=20)
        frame_canvas.columnconfigure(0, weight=1)
        frame_canvas.rowconfigure(0, weight=1)

        canvas = tk.Canvas(frame_canvas, highlightthickness=0, bg=COR_FUNDO_JANELA)
        scrollbar = ttk.Scrollbar(frame_canvas, orient="vertical", command=canvas.yview)
        self.frame_lista = tk.Frame(canvas, bg=COR_FUNDO_JANELA)
        janela_interna = canvas.create_window((0, 0), window=self.frame_lista, anchor="nw")
        self.frame_lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_interna, width=e.width))
        self.frame_lista.columnconfigure(1, weight=1)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        rodape = tk.Frame(self, bg=COR_FUNDO_JANELA)
        rodape.grid(row=3, column=0, sticky="ew", padx=20, pady=14)
        rodape.columnconfigure(0, weight=1)

        self.var_subtotais = tk.StringVar(value="")
        tk.Label(
            rodape, textvariable=self.var_subtotais, bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
            font=("Segoe UI", 9, "bold"), anchor="w", justify="left",
        ).grid(row=0, column=0, sticky="w")

        tk.Button(rodape, text="📄 Abrir o Enviados", relief="flat", fg=COR_ACENTO, cursor="hand2",
                  command=self._abrir_documento).grid(row=0, column=1, padx=(0, 8))
        self.btn_enviar = tk.Button(
            rodape, text="Enviar", relief="flat", bg=COR_ACENTO, fg="white",
            activebackground=COR_ACENTO, cursor="hand2", font=("Segoe UI", 10, "bold"),
            command=self._conferir_e_enviar, state="disabled",
        )
        self.btn_enviar.grid(row=0, column=2, ipadx=14, ipady=4)
        tk.Button(rodape, text="Fechar", relief="flat", cursor="hand2", command=self.destroy).grid(
            row=0, column=3, padx=(8, 0))

    # ---------- pasta e lista ----------

    def _escolher_pasta(self):
        inicial = self.config_dados.get("ultima_pasta_envio") or str(PASTA_EVENTOS)
        escolhida = filedialog.askdirectory(
            title="Escolha a pasta de produção (ex: EVENTOS\\CLIENTE\\PRODUCAO 03_09)",
            initialdir=inicial, parent=self,
        )
        if not escolhida:
            if self.pasta is None:
                self.destroy()
            return
        self.pasta = pathlib.Path(escolhida)
        self.config_dados["ultima_pasta_envio"] = str(self.pasta)
        salvar_config(self.config_dados)
        self._recarregar()

    def _recarregar(self):
        if self.pasta is None:
            return
        raiz = raiz_do_cliente(self.pasta)
        self.envios_anteriores = carregar_envios(raiz)["envios"]
        self.itens = listar_para_envio(self.pasta, self.config_dados, self.envios_anteriores)
        self.var_pasta.set(str(self.pasta))
        self._preencher_lista()

    def _preencher_lista(self):
        for widget in self.frame_lista.winfo_children():
            widget.destroy()
        self.marcados = {}
        self.combos_maquina = {}

        if not self.itens:
            tk.Label(
                self.frame_lista, bg=COR_FUNDO_JANELA, fg=COR_ALERTA, justify="left", wraplength=800,
                text="Nenhum arquivo de arte nesta pasta.\n\n"
                     "Lembrando: CORTES não aparece aqui (não passa por impressora) e Prontos nunca é lido.",
            ).grid(row=0, column=0, columnspan=6, sticky="w", pady=20)
            self._atualizar_rodape()
            return

        por_pasta = {}
        for indice, item in enumerate(self.itens):
            por_pasta.setdefault(item["pasta_trabalho"], []).append((indice, item))

        linha = 0
        for nome_pasta in sorted(por_pasta):
            grupo = por_pasta[nome_pasta]
            nunca_enviados = [i for i, item in grupo if not item["envios_anteriores"]]
            cabecalho = tk.Frame(self.frame_lista, bg="#e9ebef")
            cabecalho.grid(row=linha, column=0, columnspan=6, sticky="ew", pady=(12, 0))
            tk.Button(
                cabecalho, text=f"marcar todos  ·  {nome_pasta}", relief="flat", bg="#e9ebef", fg=COR_TEXTO,
                font=("Segoe UI", 9, "bold"), cursor="hand2", anchor="w",
                command=lambda ids=nunca_enviados: self._marcar_todos(ids),
            ).pack(side="left", padx=6, pady=3)
            tk.Label(
                cabecalho, text=f"{len(grupo)} arquivo(s)", bg="#e9ebef", fg=COR_TEXTO_SECUNDARIO,
            ).pack(side="left")
            linha += 1

            # já enviados vão pro fim do grupo: o que interessa marcar
            # fica em cima, e o histórico continua visível embaixo
            for indice, item in sorted(grupo, key=lambda par: bool(par[1]["envios_anteriores"])):
                self._linha_item(linha, indice, item)
                linha += 1

        self._atualizar_rodape()

    def _linha_item(self, linha, indice, item):
        ja_foi = bool(item["envios_anteriores"])
        cor_texto = COR_TEXTO_SECUNDARIO if ja_foi else COR_TEXTO

        var = tk.BooleanVar(value=False)
        var.trace_add("write", lambda *_: self._atualizar_rodape())
        self.marcados[indice] = var
        tk.Checkbutton(self.frame_lista, variable=var, bg=COR_FUNDO_JANELA).grid(
            row=linha, column=0, sticky="w", padx=(2, 4))

        tk.Label(
            self.frame_lista, text=item["arquivo"], bg=COR_FUNDO_JANELA, fg=cor_texto,
            font=("Consolas", 8), anchor="w", justify="left", wraplength=400,
        ).grid(row=linha, column=1, sticky="w", pady=1)

        if item["dimensao"]:
            medida = (
                f'{item["dimensao"]["largura_m"]:.2f} x {item["dimensao"]["altura_m"]:.2f} m'
                f'  ·  {item["quantidade"]} un  ·  {item["area_total_m2"]:.2f} m²'
            ).replace(".", ",")
        else:
            medida = f'sem medida no nome  ·  {item["quantidade"]} un'
        tk.Label(self.frame_lista, text=medida, bg=COR_FUNDO_JANELA, fg=cor_texto, anchor="w").grid(
            row=linha, column=2, sticky="w", padx=8)

        var_maquina = tk.StringVar(value=item["maquina"])
        self.combos_maquina[indice] = var_maquina
        combo = ttk.Combobox(
            self.frame_lista, textvariable=var_maquina, state="readonly", width=16,
            values=list(MAQUINAS_RIP),
        )
        combo.grid(row=linha, column=3, padx=6)
        combo.bind("<<ComboboxSelected>>", lambda e, i=indice: self._trocar_maquina(i))

        tk.Label(
            self.frame_lista, text=self._observacao(item), bg=COR_FUNDO_JANELA,
            fg=COR_ALERTA if (ja_foi or not item["cabe"]) else (COR_POSITIVO if item["giro"] else COR_TEXTO_SECUNDARIO),
            anchor="w", justify="left", wraplength=270,
        ).grid(row=linha, column=4, sticky="w", padx=(4, 2))

    def _observacao(self, item):
        partes = []
        if item["envios_anteriores"]:
            quando = item["envios_anteriores"][-1]["quando"]
            quantas = len(item["envios_anteriores"])
            partes.append(f"já enviado {quantas}x · último {quando[8:10]}/{quando[5:7]} {quando[11:16]}")
        if not item["cabe"]:
            partes.append("não cabe nem girado — vai assim mesmo")
        elif item["giro"]:
            if item["giro"]["motivo"] == "nao_cabe":
                partes.append("deve girar · não cabe em pé")
            else:
                partes.append(f'deve girar · economiza {item["giro"]["economia_m"]:.2f} m'.replace(".", ","))
        elif not item["dimensao"]:
            partes.append("sem medida — sem previsão de giro")
        return "\n".join(partes) or "—"

    def _trocar_maquina(self, indice):
        """A máquina mudou: o giro previsto depende da largura útil dela, então a linha é refeita."""
        item = self.itens[indice]
        item["maquina"] = self.combos_maquina[indice].get()
        item["giro"] = prever_giro(item["dimensao"], item["maquina"])
        item["cabe"] = cabe_na_maquina(item["dimensao"], item["maquina"])
        marcados_antes = {i for i, v in self.marcados.items() if v.get()}
        self._preencher_lista()
        for i in marcados_antes:
            if i in self.marcados:
                self.marcados[i].set(True)

    def _marcar_todos(self, indices):
        alvo = not all(self.marcados[i].get() for i in indices) if indices else False
        for i in indices:
            self.marcados[i].set(alvo)

    def _itens_marcados(self):
        return [self.itens[i] for i, var in self.marcados.items() if var.get()]

    def _atualizar_rodape(self):
        marcados = self._itens_marcados()
        nunca_enviados = sum(1 for i in self.itens if not i["envios_anteriores"])
        ja_enviados = len(self.itens) - nunca_enviados
        self.var_contagem.set(
            f"{nunca_enviados} nunca enviados · {len(marcados)} marcados"
            + (f" · {ja_enviados} já enviados" if ja_enviados else "")
        )

        totais = subtotais_por_material(marcados)
        self.var_subtotais.set(
            "     ".join(f"{cat} {m2:.2f} m²".replace(".", ",") for cat, m2 in sorted(totais.items()))
            or "Nada marcado"
        )
        self.btn_enviar.config(
            text=f"Enviar {len(marcados)} arquivo(s)" if marcados else "Enviar",
            state="normal" if marcados else "disabled",
        )

    # ---------- conferência e envio ----------

    def _conferir_e_enviar(self):
        marcados = self._itens_marcados()
        if not marcados:
            return
        resultado = conferir_envio(marcados)
        if not JanelaConferenciaEnvio(self, resultado).confirmado:
            return

        liberados = resultado["limpos"] + [item for item, _ in resultado["atencao"]]
        if not liberados:
            messagebox.showinfo(
                "Nada a enviar",
                "Todos os arquivos marcados estão travados pela conferência. "
                "Resolva os conflitos e tente de novo.",
                parent=self,
            )
            return

        self._executar_envio(liberados, resultado["bloqueados"])

    def _executar_envio(self, itens, bloqueados):
        self.btn_enviar.config(state="disabled", text="Enviando...")
        self.update_idletasks()
        try:
            resultado = enviar_para_maquinas(itens, self.pasta)
            raiz = raiz_do_cliente(self.pasta)

            # a miniatura só é feita pra quem ainda não tem uma guardada:
            # o arquivo acabou de ser copiado, então está local — mas
            # reabrir um TIF de 1,83 GB a cada reenvio seria desperdício
            ja_tem = {e["arquivo"] for e in self.envios_anteriores if e.get("miniatura_b64")}
            miniaturas = {}
            for registro in resultado["enviados"]:
                if registro["arquivo"] not in ja_tem:
                    caminho = next(i["caminho"] for i in itens if i["arquivo"] == registro["arquivo"])
                    miniaturas[registro["arquivo"]] = gerar_miniatura(caminho)

            caminho_documento, erro_pdf = None, None
            if resultado["enviados"]:
                registrar_envios(raiz, resultado["enviados"], miniaturas)
                caminho_documento, erro_pdf = regravar_documento(raiz, list(self.config_dados["materiais"]))
        except Exception as e:
            messagebox.showerror("Erro no envio", str(e), parent=self)
            self._atualizar_rodape()
            return

        self._recarregar()
        JanelaResultadoEnvio(self, resultado, bloqueados, self.itens, caminho_documento, erro_pdf)

    def _abrir_documento(self):
        if self.pasta is None:
            return
        caminho = caminho_documento_pdf(raiz_do_cliente(self.pasta))
        if not caminho.exists():
            messagebox.showinfo(
                "Ainda não existe",
                "O documento de enviados deste cliente só é criado no primeiro envio.",
                parent=self,
            )
            return
        try:
            # explorer.exe em vez de os.startfile: ShellExecute depende de
            # COM inicializado na thread que chama, e isso já falhou em
            # silêncio neste projeto (ver monitor_onedrive._abrir_pasta)
            subprocess.Popen(["explorer", str(caminho)])
        except Exception as e:
            messagebox.showerror("Erro", f"Não consegui abrir o documento: {e}", parent=self)


class JanelaConferenciaEnvio(tk.Toplevel):
    """
    A régua fina antes de qualquer coisa se mexer. Mostra o que trava, o
    que merece atenção e o que está limpo — e só continua com um clique
    explícito. Fechar no X é cancelar.
    """

    def __init__(self, mestre, resultado):
        super().__init__(mestre)
        self.title("Conferência antes de enviar")
        self.geometry("740x560")
        self.configure(bg=COR_FUNDO_JANELA)
        self.transient(mestre)
        self.confirmado = False

        total = len(resultado["bloqueados"]) + len(resultado["atencao"]) + len(resultado["limpos"])
        tk.Label(
            self, text=f"Conferência — {total} arquivo(s) marcado(s)", font=("Segoe UI", 12, "bold"),
            bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
        ).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(
            self, text="Nada foi copiado nem alterado ainda.", bg=COR_FUNDO_JANELA, fg=COR_TEXTO_SECUNDARIO,
        ).pack(anchor="w", padx=18, pady=(0, 10))

        texto = tk.Text(self, wrap="word", bg=COR_CARTAO, relief="solid", bd=1, padx=10, pady=8)
        texto.pack(fill="both", expand=True, padx=18)
        texto.tag_config("bloq", foreground="#9b2117", font=("Segoe UI", 9, "bold"))
        texto.tag_config("atn", foreground=COR_ALERTA, font=("Segoe UI", 9, "bold"))
        texto.tag_config("ok", foreground=COR_POSITIVO, font=("Segoe UI", 9, "bold"))
        texto.tag_config("arquivo", font=("Consolas", 8))
        texto.tag_config("motivo", foreground="#444444")

        if resultado["bloqueados"]:
            texto.insert("end", f"TRAVA O ENVIO — {len(resultado['bloqueados'])}\n\n", "bloq")
            for item, motivo in resultado["bloqueados"]:
                texto.insert("end", f"  {item['arquivo']}\n", "arquivo")
                texto.insert("end", f"      {motivo}\n\n", "motivo")
        if resultado["atencao"]:
            texto.insert("end", f"VAI, MAS OLHA ISSO — {len(resultado['atencao'])}\n\n", "atn")
            for item, avisos in resultado["atencao"]:
                texto.insert("end", f"  {item['arquivo']}\n", "arquivo")
                for aviso in avisos:
                    texto.insert("end", f"      {aviso}\n", "motivo")
                texto.insert("end", "\n")
        if resultado["limpos"]:
            texto.insert("end", f"LIMPO — {len(resultado['limpos'])}\n\n", "ok")
            for item in resultado["limpos"]:
                area = f'{item["area_total_m2"]:.2f} m²'.replace(".", ",") if item["area_total_m2"] else "sem medida"
                texto.insert("end", f"  {item['arquivo']}\n", "arquivo")
                texto.insert("end", f"      {item['maquina']} · {area}\n\n", "motivo")
        texto.config(state="disabled")

        liberados = len(resultado["limpos"]) + len(resultado["atencao"])
        botoes = tk.Frame(self, bg=COR_FUNDO_JANELA)
        botoes.pack(fill="x", padx=18, pady=14)
        tk.Button(botoes, text="Cancelar", relief="flat", cursor="hand2", command=self.destroy).pack(side="left")
        tk.Button(
            botoes, text=f"Enviar {liberados} arquivo(s)", relief="flat", bg=COR_ACENTO, fg="white",
            activebackground=COR_ACENTO, cursor="hand2", font=("Segoe UI", 10, "bold"),
            state="normal" if liberados else "disabled", command=self._confirmar,
        ).pack(side="right", ipadx=12, ipady=3)

        self.grab_set()
        self.wait_window(self)

    def _confirmar(self):
        self.confirmado = True
        self.destroy()


class JanelaResultadoEnvio(tk.Toplevel):
    """
    O que aconteceu de verdade. A seção do fim é a resposta ao "não pode
    ficar nenhum arquivo pra trás": como nenhum arquivo sai do lugar,
    quem sabe o que já foi é o documento — então a tela relê a pasta e
    conta o que continua sem nenhum envio registrado.
    """

    def __init__(self, mestre, resultado, bloqueados, itens_recarregados, caminho_documento, erro_pdf):
        super().__init__(mestre)
        self.title("Resultado do envio")
        self.geometry("740x520")
        self.configure(bg=COR_FUNDO_JANELA)
        self.transient(mestre)

        tk.Label(
            self, text="Resultado do envio", font=("Segoe UI", 12, "bold"),
            bg=COR_FUNDO_JANELA, fg=COR_TEXTO,
        ).pack(anchor="w", padx=18, pady=(16, 8))

        texto = tk.Text(self, wrap="word", bg=COR_CARTAO, relief="solid", bd=1, padx=10, pady=8)
        texto.pack(fill="both", expand=True, padx=18)
        texto.tag_config("ok", foreground=COR_POSITIVO, font=("Segoe UI", 9, "bold"))
        texto.tag_config("bloq", foreground="#9b2117", font=("Segoe UI", 9, "bold"))
        texto.tag_config("atn", foreground=COR_ALERTA, font=("Segoe UI", 9, "bold"))
        texto.tag_config("arquivo", font=("Consolas", 8))
        texto.tag_config("motivo", foreground="#444444")

        if resultado["enviados"]:
            texto.insert("end", f"ENVIADOS E ANOTADOS — {len(resultado['enviados'])}\n\n", "ok")
            for registro in resultado["enviados"]:
                texto.insert("end", f"  {registro['arquivo']}\n", "arquivo")
                texto.insert("end", f"      {registro['maquina']} · cópia conferida\n\n", "motivo")

        nao_foram = list(resultado["falhas"]) + list(bloqueados)
        if nao_foram:
            texto.insert("end", f"NÃO FORAM — {len(nao_foram)}\n\n", "bloq")
            for item, motivo in nao_foram:
                texto.insert("end", f"  {item['arquivo']}\n", "arquivo")
                texto.insert("end", f"      {motivo}\n\n", "motivo")

        faltando = {}
        for item in itens_recarregados:
            if not item["envios_anteriores"]:
                faltando[item["pasta_trabalho"]] = faltando.get(item["pasta_trabalho"], 0) + 1
        total_faltando = sum(faltando.values())
        texto.insert("end", f"NUNCA ENVIADOS NESTA PASTA — {total_faltando}\n\n", "atn" if total_faltando else "ok")
        if faltando:
            for nome_pasta, quantos in sorted(faltando.items()):
                texto.insert("end", f"  {nome_pasta}: {quantos}\n", "motivo")
        else:
            texto.insert("end", "  Nada ficou pra trás nesta pasta.\n", "motivo")

        if erro_pdf:
            texto.insert("end", "\nDOCUMENTO NÃO REGRAVADO\n", "atn")
            texto.insert(
                "end",
                f"  Os envios estão salvos, mas o PDF não pôde ser regravado: {erro_pdf}\n"
                f"  Normalmente é o documento estar aberto no leitor de PDF. Feche e clique em "
                f"'Abrir o Enviados' pra gerar de novo.\n",
                "motivo",
            )
        elif caminho_documento:
            texto.insert("end", f"\nDocumento atualizado: {caminho_documento.name}\n", "motivo")
        texto.config(state="disabled")

        tk.Button(self, text="Fechar", relief="flat", bg=COR_ACENTO, fg="white",
                  activebackground=COR_ACENTO, cursor="hand2", command=self.destroy).pack(pady=14, ipadx=16, ipady=3)

        self.grab_set()
