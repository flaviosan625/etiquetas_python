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
import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from arquivamento import PASTA_DESTINO_PADRAO, enviar_os, listar_pedidos
from branding import CAMINHO_LOGO_GUI
from config import atualizar_ultimo_uso, carregar_config, salvar_config
from dimensoes import formatar_variante
from estado_pedido import estado_existe, localizar_pastas_cliente
from estoque import (
    carregar_estoque, saldo_produto, registrar_movimento, desfazer_movimento,
    prever_saida_os, confirmar_saida_os, novo_produto, adicionar_produto, atualizar_produto, remover_produto,
    meses_disponiveis, resumo_mensal, rendimento_tinta_mensal,
)
from processamento import processar_etiquetas
from utils import sanitizar_nome_arquivo

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
        ).pack(anchor="w", padx=16, pady=(4, 2))

        tk.Button(
            self, text="📦 Controle de Estoque...", relief="flat",
            fg=COR_ACENTO, cursor="hand2", command=self._abrir_estoque,
        ).pack(anchor="w", padx=16, pady=(0, 2))

        ttk.Separator(self).pack(fill="x", padx=16, pady=(0, 10))

        self.var_enviar_onedrive = tk.BooleanVar(value=False)
        frame_onedrive = tk.Frame(self)
        frame_onedrive.pack(anchor="w", padx=16, pady=(0, 6))
        tk.Checkbutton(
            frame_onedrive, text="☁ Enviar a OS pro OneDrive depois de gerar", variable=self.var_enviar_onedrive,
        ).pack(anchor="w")
        tk.Label(
            frame_onedrive, text=f"    Destino: {PASTA_DESTINO_PADRAO}", fg="#888888", font=("Segoe UI", 8),
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
        pasta = filedialog.askdirectory(title="Selecione a pasta com os PDFs")
        if pasta:
            self.var_pasta.set(pasta)

    def _abrir_configuracoes(self):
        JanelaConfiguracoes(self, self.config_dados, self._config_atualizada)

    def _abrir_estoque(self):
        JanelaEstoque(self, self.config_dados)

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
            args=(pasta, cliente, gerente, produtor, pasta_saida_existente, self.var_enviar_onedrive.get()),
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

    def _executar_em_thread(self, pasta, cliente, gerente, produtor, pasta_saida_existente, enviar_onedrive):
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

        if resultado and enviar_onedrive:
            try:
                self._enviar_os_onedrive(resultado["pasta_saida"], on_log)
            except Exception as e:
                # nunca deixa um erro inesperado aqui travar o "fim" de
                # ser enfileirado — sem isso, o botão "Processar Etiquetas"
                # ficaria desabilitado pra sempre (self.processando nunca
                # voltaria a False), mesmo com as etiquetas/OS já geradas
                # com sucesso antes disso.
                self.fila_eventos.put(("log", "err", f"Erro inesperado ao enviar a OS pro OneDrive: {e}"))

        self.fila_eventos.put(("fim", resultado, None))

    def _enviar_os_onedrive(self, pasta_saida, on_log):
        """
        Roda logo depois do processamento, na mesma thread, só quando o
        checkbox "Enviar a OS pro OneDrive" estava marcado — copia (nunca
        move) a OS desse pedido específico que acabou de ser gerado/
        atualizado. Nunca apaga nada localmente (ver arquivamento.py).
        """
        on_log("info", "Enviando a OS pro OneDrive...")
        pasta_gerada = pathlib.Path(pasta_saida)
        pedido = next((p for p in listar_pedidos() if p["pasta"] == pasta_gerada), None)
        if not pedido:
            on_log("warn", "Não encontrei arquivo de OS pra enviar pro OneDrive (a OS pode não ter sido gerada nessa rodada).")
            return

        resumo = enviar_os([pedido])[0]
        if resumo["erros"]:
            on_log("warn", f"OS não pôde ser totalmente enviada pro OneDrive: {'; '.join(resumo['erros'])}")
        else:
            destino = PASTA_DESTINO_PADRAO / pedido["cliente"] / pedido["subpasta"]
            on_log("ok", f"OS enviada pro OneDrive: {destino}")

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
        except queue.Empty:
            pass
        self.after(150, self._checar_fila)


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
        self.previsao = prever_saida_os(self.estoque, self.dados_os["itens"], self.config_dados["materiais"])
        self._mostrar_previa()
        self.btn_confirmar.configure(state="normal")

    def _mostrar_previa(self):
        for widget in self.frame_previa.winfo_children():
            widget.destroy()
        for linha in self.previsao:
            variante_txt = f" · {formatar_variante(linha['variante'])}" if linha.get("variante") else ""
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
        nome_pedido = f"{self.dados_os.get('cliente', '?')} ({self.dados_os.get('data_hora', '?')})"
        resumo = confirmar_saida_os(self.estoque, self.dados_os["itens"], self.config_dados["materiais"], nome_pedido)
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
