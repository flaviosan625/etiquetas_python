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
import threading
import tkinter as tk
from tkinter import ttk

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
        try:
            self._servico = agentes._servico_agendador()
        except Exception:
            self._servico = None   # ler_tarefa cai pra "não sei", não quebra

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._montar_cabecalho()
        self._montar_lista()
        for ag in agentes.AGENTES:
            self._montar_cartao(ag)

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

    def _atualizar(self):
        agora = datetime.datetime.now()
        ler_acao = (self._ultima_leitura_acao is None
                    or (agora - self._ultima_leitura_acao).total_seconds() >= _INTERVALO_ACAO_S)

        for chave, c in self._cartoes.items():
            ag = c["agente"]
            try:
                est = agentes.estado(ag, agora=agora, servico=self._servico)
            except Exception as e:
                est = {"nivel": "sem_sinal", "texto": "Não consegui ler agora: %s" % e}
            nivel, texto = est["nivel"], est["texto"]
            nivel, texto = self._acompanhar_disparo(ag, nivel, texto, agora)

            cor = _COR_NIVEL.get(nivel, cores.texto2)
            c["simbolo"].configure(text=_SIMBOLO_NIVEL.get(nivel, "●"), fg=cor)
            c["lbl_estado"].configure(fg=cor if nivel != "ok" else cores.texto)
            c["var_estado"].set(texto)
            if ler_acao:
                c["var_acao"].set("Última ação: %s" % agentes.ultima_acao(ag, agora))

        if ler_acao:
            self._ultima_leitura_acao = agora
        self.var_rodape.set("Atualiza sozinho a cada 3 s  ·  última leitura %s" % agora.strftime("%H:%M:%S"))
        self._job = self.after(_INTERVALO_ESTADO_MS, self._atualizar)

    def _acompanhar_disparo(self, ag, nivel, texto, agora):
        """
        Enquanto um disparo forçado não aparece como terminado no Agendador,
        o cartão fala dele — e não do estado de antes do disparo.
        """
        pedido = self._disparos.get(ag.chave)
        if pedido:
            tarefa = agentes.ler_tarefa_do_agente(ag, self._servico)
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
        ok, msg = agentes.disparar(ag, servico=self._servico)
        c = self._cartoes[ag.chave]
        if ok:
            self._disparos[ag.chave] = datetime.datetime.now()
            self._concluidos.pop(ag.chave, None)
            self._habilitar(ag, False)
            c["simbolo"].configure(fg=cores.acento)
            c["var_estado"].set(msg)
        else:
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
            resultado = agentes.rodar_aqui(ag)
            self.after(0, lambda: self._mostrar_saida(ag, inicio, resultado))

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
        if evento.widget is self and self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
