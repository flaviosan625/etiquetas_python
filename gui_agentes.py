"""
Painel dos agentes — a tela de agentes.py.

Pedido do usuário (2026-09-13): "arrumar esses agentes para que eu possa
forçar um disparo caso ele não execute a tarefa, deixar sempre bem
dinâmico".

Um cartão por agente, no mesmo visual do Controle de Estoque (fundo cinza,
cartão branco). Cada cartão diz o que o agente faz, onde roda, se está vivo
— com a medida E o que ela significa — e a última coisa que ele fez.

DINÂMICO: relê o Agendador a cada 3 s (é leitura local, custa milissegundos)
e a última ação a cada 30 s (essa varre pasta do OneDrive).

DOIS BOTÕES, DUAS COISAS DIFERENTES:
  ▶ Disparar agora  -> pede ao Agendador pra rodar a tarefa (a passada de
                       sempre). O cartão acompanha até ela terminar.
  Rodar aqui        -> roda a passada direto e mostra o que ela escreveu.
                       É pra quando disparar não resolve: ver o erro.
O RIP (outro PC) e o Monitor de Pastas (congelado) não têm botão de disparo
de propósito.
"""
import datetime
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import agentes
from tema import cores

_INTERVALO_ESTADO_MS = 3000
_INTERVALO_ACAO_S = 30
# Quanto esperar o Agendador mostrar que o disparo rodou antes de avisar
# que ele não apareceu (o IgnoreNew engole disparo em cima de passada).
_ESPERA_DISPARO_S = 90
# Por quanto tempo o cartão mantém "Disparo forçado das HH:MM:SS: ..."
_MOSTRA_RESULTADO_S = 25

_COR_NIVEL = {
    "ok": cores.positivo,
    "atencao": cores.alerta,
    "parado": cores.parado,
    "sem_sinal": cores.texto2,
    "rodando": cores.acento,
    "congelado": cores.texto2,
}
_SIMBOLO_NIVEL = {"congelado": "❄"}

_POR_QUE_SEM_BOTAO = {
    "rip": "roda no PC do RIP — daqui só dá pra ver o sinal que ele deixa no OneDrive",
    "monitor": "congelado a seu pedido — sem botão de disparo de propósito",
}


def _ler_estado_google():
    import drive_artes

    try:
        return drive_artes.estado_do_token()
    except Exception as e:                           # noqa: BLE001
        return {"situacao": "vencido", "texto": "Não consegui ler: %s" % e}


def _capturar_snapshot(agentes_lista, agora, ler_acao, disparos):
    """Lê Agendador, processos e arquivos fora do thread da interface."""
    pythoncom = None
    com_inicializado = False
    servico = object()  # falha fechada: as leituras devolverão "sem sinal"
    try:
        import pythoncom as modulo_pythoncom
        pythoncom = modulo_pythoncom
        pythoncom.CoInitialize()
        com_inicializado = True
        servico = agentes._servico_agendador(inicializar_com=False)
    except Exception:
        pass

    estados = {}
    tarefas = {}
    acoes = {}
    try:
        for ag in agentes_lista:
            try:
                estados[ag.chave] = agentes.estado(ag, agora=agora, servico=servico)
            except Exception as e:                       # noqa: BLE001
                estados[ag.chave] = {
                    "nivel": "sem_sinal",
                    "texto": "Não consegui ler agora: %s" % e,
                }
            if ag.chave in disparos:
                try:
                    tarefas[ag.chave] = agentes.ler_tarefa_do_agente(ag, servico)
                except Exception as e:                   # noqa: BLE001
                    tarefas[ag.chave] = {"existe": None, "erro": str(e)}
            if ler_acao:
                try:
                    acoes[ag.chave] = agentes.ultima_acao(ag, agora)
                except Exception as e:                   # noqa: BLE001
                    acoes[ag.chave] = "não consegui ler: %s" % e
        google = _ler_estado_google() if ler_acao else None
        return {
            "agora": agora,
            "ler_acao": ler_acao,
            "estados": estados,
            "tarefas": tarefas,
            "acoes": acoes,
            "google": google,
        }
    finally:
        if com_inicializado:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _publicar_snapshot(resultados, agentes_lista, agora, ler_acao, disparos):
    try:
        resultado = _capturar_snapshot(agentes_lista, agora, ler_acao, disparos)
    except Exception as e:                               # noqa: BLE001
        resultado = {
            "agora": agora,
            "ler_acao": ler_acao,
            "estados": {a.chave: {"nivel": "sem_sinal", "texto": "Não consegui ler agora: %s" % e}
                        for a in agentes_lista},
            "tarefas": {},
            "acoes": {},
            "google": None,
        }
    resultados.put(resultado)


class JanelaAgentes(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Agentes — o que roda sozinho — UNY CV")
        self.configure(bg=cores.fundo)
        self.geometry("860x760")
        self.minsize(640, 420)

        self._cartoes = {}
        self._disparos = {}        # chave -> quando o disparo foi pedido
        self._concluidos = {}      # chave -> (quando terminou, texto)
        self._rodando_aqui = set()
        self._ultima_leitura_acao = None
        self._job = None
        self._fechando = False
        self._leitura_em_andamento = False
        self._resultados_leitura = queue.Queue()
        self._resultados_rodar_aqui = queue.Queue()
        self._resultados_disparar = queue.Queue()
        self._resultados_google = queue.Queue()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._montar_cabecalho()
        self._montar_lista()
        for ag in agentes.AGENTES:
            self._montar_cartao(ag)
        self._montar_cartao_google()

        self.bind("<Destroy>", self._ao_fechar)
        self._atualizar()

    # ------------------------------------------------------------ montagem

    def _montar_cabecalho(self):
        topo = tk.Frame(self, bg=cores.fundo)
        topo.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        tk.Label(topo, text="Agentes", font=("Segoe UI", 15, "bold"),
                 bg=cores.fundo, fg=cores.texto).pack(anchor="w")
        tk.Label(topo, text="O que roda sozinho, se está vivo, e o botão pra forçar quando não rodar.",
                 font=("Segoe UI", 9), bg=cores.fundo, fg=cores.texto2).pack(anchor="w")
        self.var_rodape = tk.StringVar(value="lendo...")
        tk.Label(topo, textvariable=self.var_rodape, font=("Segoe UI", 8),
                 bg=cores.fundo, fg=cores.texto2).pack(anchor="w", pady=(4, 0))

    def _montar_lista(self):
        # mesmo esquema do Controle de Estoque: a lista acompanha a largura
        # real do canvas pra aproveitar a janela quando ela é alargada
        frame_canvas = tk.Frame(self, bg=cores.fundo)
        frame_canvas.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        frame_canvas.columnconfigure(0, weight=1)
        frame_canvas.rowconfigure(0, weight=1)
        canvas = tk.Canvas(frame_canvas, highlightthickness=0, bg=cores.fundo)
        scrollbar = ttk.Scrollbar(frame_canvas, orient="vertical", command=canvas.yview)
        self.frame_lista = tk.Frame(canvas, bg=cores.fundo)
        janela_interna = canvas.create_window((0, 0), window=self.frame_lista, anchor="nw")
        self.frame_lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(janela_interna, width=e.width))
        self.frame_lista.columnconfigure(0, weight=1)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    def _montar_cartao(self, ag):
        cartao = tk.Frame(self.frame_lista, bg=cores.cartao,
                          highlightbackground=cores.borda, highlightthickness=1)
        cartao.grid(row=len(self._cartoes), column=0, sticky="ew", pady=(0, 10))
        cartao.columnconfigure(1, weight=1)

        simbolo = tk.Label(cartao, text="●", font=("Segoe UI", 16), bg=cores.cartao,
                           fg=cores.texto2)
        simbolo.grid(row=0, column=0, rowspan=2, sticky="n", padx=(14, 8), pady=(10, 0))

        tk.Label(cartao, text=ag.nome, font=("Segoe UI", 11, "bold"), bg=cores.cartao,
                 fg=cores.texto, anchor="w").grid(row=0, column=1, sticky="w", pady=(12, 0))
        tk.Label(cartao, text="%s  ·  %s" % (ag.faz, ag.onde), font=("Segoe UI", 9),
                 bg=cores.cartao, fg=cores.texto2, anchor="w", justify="left",
                 wraplength=520).grid(row=1, column=1, sticky="w")

        botoes = tk.Frame(cartao, bg=cores.cartao)
        botoes.grid(row=0, column=2, rowspan=2, sticky="ne", padx=14, pady=(10, 0))
        btn_disparar = btn_aqui = None
        if ag.pode_disparar:
            btn_disparar = tk.Button(
                botoes, text="▶  Disparar agora", bg=cores.acento, fg=cores.sobre_acento,
                activebackground=cores.acento, activeforeground=cores.sobre_acento, relief="flat",
                font=("Segoe UI", 9, "bold"), cursor="hand2", padx=10, pady=3,
                command=lambda a=ag: self._disparar(a))
            btn_disparar.pack(anchor="e")
            linha_links = tk.Frame(botoes, bg=cores.cartao)
            linha_links.pack(anchor="e", pady=(4, 0))
            btn_aqui = tk.Button(
                linha_links, text="Rodar aqui e ver saída", relief="flat", bg=cores.cartao,
                fg=cores.acento, cursor="hand2", font=("Segoe UI", 8),
                command=lambda a=ag: self._rodar_aqui(a))
            btn_aqui.pack(side="left")
        else:
            linha_links = tk.Frame(botoes, bg=cores.cartao)
            linha_links.pack(anchor="e")
        tk.Button(linha_links, text="📂 Pasta", relief="flat", bg=cores.cartao, fg=cores.acento,
                  cursor="hand2", font=("Segoe UI", 8),
                  command=lambda a=ag: self._abrir_pasta(a)).pack(side="left")
        if ag.chave == "checklist":
            # quem ele atende se escolhe em Clientes — o atalho fica no cartão
            tk.Button(linha_links, text="👥 Clientes", relief="flat", bg=cores.cartao, fg=cores.acento,
                      cursor="hand2", font=("Segoe UI", 8),
                      command=self._abrir_clientes).pack(side="left")

        var_estado = tk.StringVar(value="lendo...")
        lbl_estado = tk.Label(cartao, textvariable=var_estado, font=("Segoe UI", 10),
                              bg=cores.cartao, fg=cores.texto, anchor="w", justify="left", wraplength=760)
        lbl_estado.grid(row=2, column=1, columnspan=2, sticky="w", padx=(0, 14), pady=(8, 0))

        var_acao = tk.StringVar(value="")
        tk.Label(cartao, textvariable=var_acao, font=("Segoe UI", 8), bg=cores.cartao,
                 fg=cores.texto2, anchor="w", justify="left", wraplength=760,
                 ).grid(row=3, column=1, columnspan=2, sticky="w", padx=(0, 14), pady=(2, 0))

        motivo = _POR_QUE_SEM_BOTAO.get(ag.chave)
        if motivo:
            tk.Label(cartao, text=motivo, font=("Segoe UI", 8, "italic"), bg=cores.cartao,
                     fg=cores.texto2, anchor="w").grid(
                row=4, column=1, columnspan=2, sticky="w", padx=(0, 14), pady=(2, 0))

        # a saída do "Rodar aqui" só aparece depois de usado
        frame_saida = tk.Frame(cartao, bg=cores.cartao)
        var_titulo_saida = tk.StringVar()
        tk.Label(frame_saida, textvariable=var_titulo_saida, font=("Segoe UI", 8, "bold"),
                 bg=cores.cartao, fg=cores.texto, anchor="w").pack(anchor="w")
        texto_saida = tk.Text(frame_saida, height=7, bg=cores.log_fundo, fg=cores.log_texto,
                              font=("Consolas", 9), relief="flat", wrap="word")
        texto_saida.pack(fill="x", pady=(2, 0))

        tk.Frame(cartao, bg=cores.cartao, height=12).grid(row=6, column=0, columnspan=3)

        self._cartoes[ag.chave] = {
            "agente": ag, "simbolo": simbolo, "lbl_estado": lbl_estado,
            "var_estado": var_estado, "var_acao": var_acao,
            "btn_disparar": btn_disparar, "btn_aqui": btn_aqui,
            "frame_saida": frame_saida, "var_titulo_saida": var_titulo_saida,
            "texto_saida": texto_saida,
        }

    # ------------------------------------------------------------- ciclo

    def _montar_cartao_google(self):
        """
        A conta do Google não é um agente — não roda sozinha — mas é
        infraestrutura que VENCE, e o painel é onde se olha o que está
        vivo. Enquanto o app estiver em "Testing" no Google Cloud, o
        Google derruba a autorização a cada 7 dias; o botão aqui refaz o
        login em dez segundos, sem depender de ninguém.
        """
        cartao = tk.Frame(self.frame_lista, bg=cores.cartao,
                          highlightbackground=cores.borda, highlightthickness=1)
        cartao.grid(row=len(self._cartoes) + 1, column=0, sticky="ew", pady=(0, 10))
        cartao.columnconfigure(1, weight=1)

        self._simbolo_google = tk.Label(cartao, text="●", font=("Segoe UI", 16),
                                        bg=cores.cartao, fg=cores.texto2)
        self._simbolo_google.grid(row=0, column=0, rowspan=2, sticky="n", padx=(14, 8), pady=(10, 0))
        tk.Label(cartao, text="Conta do Google", font=("Segoe UI", 11, "bold"), bg=cores.cartao,
                 fg=cores.texto, anchor="w").grid(row=0, column=1, sticky="w", pady=(12, 0))
        tk.Label(cartao, text="Usada pra ler o Drive na tela de receber artes.",
                 font=("Segoe UI", 9), bg=cores.cartao, fg=cores.texto2, anchor="w",
                 justify="left", wraplength=520).grid(row=1, column=1, sticky="w")

        self.var_google = tk.StringVar(value="lendo...")
        self.lbl_google = tk.Label(cartao, textvariable=self.var_google, font=("Segoe UI", 10),
                                   bg=cores.cartao, fg=cores.texto, anchor="w", justify="left",
                                   wraplength=560)
        self.lbl_google.grid(row=2, column=1, columnspan=2, sticky="w", padx=(0, 14), pady=(6, 12))

        self.btn_google = tk.Button(
            cartao, text="🔑  Reconectar", bg=cores.acento, fg=cores.sobre_acento,
            activebackground=cores.acento, activeforeground=cores.sobre_acento, relief="flat",
            font=("Segoe UI", 9, "bold"), cursor="hand2", padx=10, pady=3,
            command=self._reconectar_google)
        self.btn_google.grid(row=0, column=2, rowspan=2, sticky="ne", padx=14, pady=(10, 0))

    def _reconectar_google(self):
        """Abre o navegador pra autorizar de novo. Trava o botão enquanto isso."""
        self.btn_google.configure(state="disabled", text="abrindo o navegador...")
        self.var_google.set("Confirme a conta no navegador. Se aparecer “o Google não verificou "
                            "este app”, clique em Avançado e siga — o app é nosso.")

        def trabalho():
            try:
                import drive_artes
                drive_artes.reautorizar()
                resultado = (None, _ler_estado_google())
            except Exception as e:                       # noqa: BLE001
                resultado = (str(e), _ler_estado_google())
            self._resultados_google.put(resultado)

        threading.Thread(target=trabalho, daemon=True).start()

    def _atualizar_google(self):
        self._aplicar_estado_google(_ler_estado_google())

    def _aplicar_estado_google(self, estado):
        cor = {"ok": cores.ok, "vence_logo": cores.aviso}.get(estado["situacao"], cores.erro)
        self._simbolo_google.configure(fg=cor)
        self.lbl_google.configure(fg=cores.texto if estado["situacao"] == "ok" else cor)
        self.var_google.set(estado["texto"])

    def _atualizar(self):
        if self._fechando:
            return

        try:
            snapshot = self._resultados_leitura.get_nowait()
        except queue.Empty:
            snapshot = None
        if snapshot is not None:
            self._leitura_em_andamento = False
            self._aplicar_snapshot(snapshot)

        while True:
            try:
                ag, inicio, resultado = self._resultados_rodar_aqui.get_nowait()
            except queue.Empty:
                break
            self._mostrar_saida(ag, inicio, resultado)

        while True:
            try:
                ag, ok, msg = self._resultados_disparar.get_nowait()
            except queue.Empty:
                break
            self._aplicar_resultado_disparo(ag, ok, msg)

        while True:
            try:
                erro, estado = self._resultados_google.get_nowait()
            except queue.Empty:
                break
            self.btn_google.configure(state="normal", text="🔑  Reconectar")
            if erro:
                messagebox.showerror("Reconectar", "Não consegui autorizar:\n\n%s" % erro, parent=self)
            self._aplicar_estado_google(estado)

        agora = datetime.datetime.now()
        ler_acao = (self._ultima_leitura_acao is None
                    or (agora - self._ultima_leitura_acao).total_seconds() >= _INTERVALO_ACAO_S)
        if not self._leitura_em_andamento:
            self._leitura_em_andamento = True
            args = (self._resultados_leitura, [c["agente"] for c in self._cartoes.values()],
                    agora, ler_acao, dict(self._disparos))
            threading.Thread(target=_publicar_snapshot, args=args, daemon=True).start()
        self.var_rodape.set("Atualiza sozinho a cada 3 s  ·  última leitura %s" % agora.strftime("%H:%M:%S"))
        self._job = self.after(_INTERVALO_ESTADO_MS, self._atualizar)

    def _aplicar_snapshot(self, snapshot):
        agora = snapshot["agora"]
        for chave, c in self._cartoes.items():
            ag = c["agente"]
            est = snapshot["estados"].get(chave, {
                "nivel": "sem_sinal", "texto": "Ainda não consegui ler o estado."})
            nivel, texto = est["nivel"], est["texto"]
            nivel, texto = self._acompanhar_disparo(
                ag, nivel, texto, agora, snapshot["tarefas"].get(chave))
            cor = _COR_NIVEL.get(nivel, cores.texto2)
            c["simbolo"].configure(text=_SIMBOLO_NIVEL.get(nivel, "●"), fg=cor)
            c["lbl_estado"].configure(fg=cor if nivel != "ok" else cores.texto)
            c["var_estado"].set(texto)
            if snapshot["ler_acao"]:
                c["var_acao"].set("Última ação: %s" % snapshot["acoes"].get(chave, "sem leitura"))

        if snapshot["ler_acao"]:
            self._ultima_leitura_acao = agora
            if snapshot["google"] is not None:
                self._aplicar_estado_google(snapshot["google"])

    def _acompanhar_disparo(self, ag, nivel, texto, agora, tarefa=None):
        """
        Enquanto um disparo forçado não aparece como terminado no Agendador,
        o cartão fala dele — e não do estado de antes do disparo.
        """
        pedido = self._disparos.get(ag.chave)
        if pedido:
            tarefa = tarefa or {}
            ultima = tarefa.get("ultima")
            rodando = tarefa.get("estado") == 4
            if rodando:
                return "rodando", "Disparo forçado das %s: rodando agora..." % pedido.strftime("%H:%M:%S")
            if ultima and ultima >= pedido - datetime.timedelta(seconds=2):
                del self._disparos[ag.chave]
                # guarda só o PREFIXO: o resto do texto continua sendo o
                # estado ao vivo, senão o "rodou há 3 s" congela na tela
                self._concluidos[ag.chave] = {
                    "quando": agora, "substituir": False,
                    "texto": "Disparo forçado das %s — " % pedido.strftime("%H:%M:%S")}
                self._habilitar(ag, True)
            elif (agora - pedido).total_seconds() > _ESPERA_DISPARO_S:
                del self._disparos[ag.chave]
                self._habilitar(ag, True)
                self._concluidos[ag.chave] = {
                    "quando": agora, "substituir": True, "nivel": "atencao",
                    "texto": ("O disparo das %s não apareceu no Agendador em %d s. Ele pode ter caído em "
                              "cima de uma passada que já rodava — use \"Rodar aqui\" pra ver o que acontece."
                              % (pedido.strftime("%H:%M:%S"), _ESPERA_DISPARO_S))}
            else:
                return "rodando", "Disparado às %s — esperando o Agendador começar..." % pedido.strftime("%H:%M:%S")

        aviso = self._concluidos.get(ag.chave)
        if aviso:
            if (agora - aviso["quando"]).total_seconds() > _MOSTRA_RESULTADO_S:
                del self._concluidos[ag.chave]
            elif aviso["substituir"]:
                return aviso.get("nivel", nivel), aviso["texto"]
            else:
                return nivel, aviso["texto"] + texto
        return nivel, texto

    # ------------------------------------------------------------- ações

    def _habilitar(self, ag, ligado):
        c = self._cartoes[ag.chave]
        for chave_botao in ("btn_disparar", "btn_aqui"):
            if c[chave_botao] is not None:
                c[chave_botao].configure(state="normal" if ligado else "disabled")

    def _disparar(self, ag):
        self._habilitar(ag, False)

        def trabalho():
            pythoncom = None
            inicializado = False
            try:
                import pythoncom as modulo_pythoncom
                pythoncom = modulo_pythoncom
                pythoncom.CoInitialize()
                inicializado = True
                servico = agentes._servico_agendador(inicializar_com=False)
                resultado = agentes.disparar(ag, servico=servico)
            except Exception as e:                      # noqa: BLE001
                resultado = (False, "Não consegui falar com o Agendador: %s" % e)
            finally:
                if inicializado:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass
            self._resultados_disparar.put((ag, resultado[0], resultado[1]))

        threading.Thread(target=trabalho, daemon=True).start()

    def _aplicar_resultado_disparo(self, ag, ok, msg):
        c = self._cartoes[ag.chave]
        if ok:
            self._disparos[ag.chave] = datetime.datetime.now()
            self._concluidos.pop(ag.chave, None)
            self._habilitar(ag, False)
            c["simbolo"].configure(fg=cores.acento)
            c["var_estado"].set(msg)
        else:
            self._habilitar(ag, True)
            self._concluidos[ag.chave] = {"quando": datetime.datetime.now(), "substituir": True,
                                          "nivel": "atencao", "texto": msg}
            c["lbl_estado"].configure(fg=cores.alerta)
            c["var_estado"].set(msg)

    def _rodar_aqui(self, ag):
        if ag.chave in self._rodando_aqui:
            return
        self._rodando_aqui.add(ag.chave)
        self._habilitar(ag, False)
        c = self._cartoes[ag.chave]
        inicio = datetime.datetime.now()
        c["frame_saida"].grid(row=5, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(8, 0))
        c["var_titulo_saida"].set("Rodando aqui desde %s..." % inicio.strftime("%H:%M:%S"))
        self._escrever_saida(ag, "")

        def trabalho():
            pythoncom = None
            inicializado = False
            try:
                import pythoncom as modulo_pythoncom
                pythoncom = modulo_pythoncom
                pythoncom.CoInitialize()
                inicializado = True
                servico = agentes._servico_agendador(inicializar_com=False)
                resultado = agentes.rodar_aqui(ag, servico=servico)
            except Exception as e:                      # noqa: BLE001
                resultado = {"recusado": "Não consegui confirmar o estado ou iniciar a passada: %s" % e}
            finally:
                if inicializado:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass
            self._resultados_rodar_aqui.put((ag, inicio, resultado))

        threading.Thread(target=trabalho, daemon=True).start()

    def _mostrar_saida(self, ag, inicio, resultado):
        if not self.winfo_exists():
            return
        self._rodando_aqui.discard(ag.chave)
        self._habilitar(ag, True)
        c = self._cartoes[ag.chave]
        if "recusado" in resultado:
            c["var_titulo_saida"].set("Não rodei")
            self._escrever_saida(ag, resultado["recusado"])
            return
        codigo = resultado["codigo"]
        situacao = ("código %s (%s)" % (codigo, "deu certo" if codigo == 0 else "saiu com erro")
                    if codigo is not None else "não terminou")
        c["var_titulo_saida"].set("Rodou aqui às %s  ·  %s  ·  %.1f s"
                                  % (inicio.strftime("%H:%M:%S"), situacao, resultado["durou_s"]))
        self._escrever_saida(ag, resultado["saida"])
        self._ultima_leitura_acao = None      # a última ação mudou; relê já

    def _escrever_saida(self, ag, texto):
        caixa = self._cartoes[ag.chave]["texto_saida"]
        caixa.configure(state="normal")
        caixa.delete("1.0", "end")
        caixa.insert("end", texto[-6000:])
        caixa.see("end")
        caixa.configure(state="disabled")

    def _abrir_clientes(self):
        abrir = getattr(self.master, "_abrir_clientes", None)
        if abrir is not None:
            abrir()                     # a janela principal cuida de não abrir duas
        else:
            from gui_clientes import JanelaClientes
            JanelaClientes(self)

    def _abrir_pasta(self, ag):
        pasta = agentes.pasta_do_agente(ag)
        try:
            os.startfile(str(pasta))
        except OSError as e:
            self._cartoes[ag.chave]["var_estado"].set("Não consegui abrir %s: %s" % (pasta, e))

    def _ao_fechar(self, evento):
        if evento.widget is self:
            self._fechando = True
        if evento.widget is self and self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
