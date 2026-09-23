"""
As cores das telas, num lugar só — e a troca entre claro e escuro.

Pedido do usuário (2026-09-22): "mudar todas as telas para fundo escuro,
colocar um botão pequeno na primeira página para mudar a cor quando eu
desejar". Então a cor não pode mais ser constante espalhada por cinco
arquivos: vira atributo de um objeto que muda de valor.

COMO SE USA
    from tema import cores
    tk.Label(pai, bg=cores.cartao, fg=cores.texto)

Sempre na HORA de criar o widget, nunca guardado numa variável de módulo
— foi por isso que virou objeto. Widget já criado não muda de cor
sozinho; quem troca o tema reconstrói a tela (a principal) e as outras
janelas nascem na cor nova quando forem abertas.

O ESCURO NÃO É PALETA NOVA: são as cores que a caixa de log do programa
já usava desde o começo (#0f1116, #7ee787, #f0b854, #ff7b72) e as mesmas
dos diagnósticos da máquina do RIP.
"""
import config as _config

# Cores que NÃO mudam com o tema: o verde/âmbar/vermelho do log são os
# mesmos nos dois (é o log que sempre foi escuro), e branco é branco.
_FIXAS = {
    "ok": "#7ee787",
    "aviso": "#f0b854",
    "erro": "#ff7b72",
    "branco": "#ffffff",
}

CLARO = dict(
    _FIXAS,
    nome="claro",
    fundo="#f5f6f8",
    cartao="#ffffff",
    borda="#e3e4e8",
    texto="#1c1c1f",
    texto2="#6b7280",
    acento="#0067c0",
    sobre_acento="#ffffff",      # texto em cima do botão de acento
    acento_claro="#3387d6",      # o acento quando o mouse está em cima
    campo="#ffffff",             # fundo de caixa de digitar
    alerta="#b45309",
    alerta_fundo="#fdf1e0",
    positivo="#0f7a3d",
    parado="#b32d24",            # "parou de verdade", diferente de alerta
    marcado="#e8f1fb",           # item marcado numa lista
    previa="#eef1f4",            # atrás de miniatura
    log_fundo="#0f1116",         # o log sempre foi escuro, nos dois temas
    log_texto="#d6d9e0",
)

ESCURO = dict(
    _FIXAS,
    nome="escuro",
    fundo="#0f1116",
    cartao="#171a21",
    borda="#252a34",
    texto="#d6d9e0",
    texto2="#9aa4b2",
    acento="#4c9aff",            # o #0067c0 quase some no escuro
    sobre_acento="#0b1220",
    acento_claro="#6fb0ff",
    campo="#0c0e13",
    alerta="#f0b854",            # no escuro o âmbar lê melhor que o marrom
    alerta_fundo="#2a2113",
    positivo="#7ee787",
    parado="#ff7b72",
    marcado="#16273a",
    previa="#1b2028",
    log_fundo="#0c0e13",
    log_texto="#d6d9e0",
)

PALETAS = {"claro": CLARO, "escuro": ESCURO}
PADRAO = "escuro"


class Cores:
    """
    Os valores do tema de agora. Os atributos são os das paletas acima
    (cores.fundo, cores.texto, cores.acento...); trocar o tema troca
    todos de uma vez, sem ninguém precisar reimportar nada.
    """

    def __init__(self, nome=PADRAO):
        self.trocar(nome)

    def trocar(self, nome):
        self.__dict__.update(PALETAS.get(nome) or PALETAS[PADRAO])
        return self

    @property
    def escuro(self):
        return self.nome == "escuro"


cores = Cores()


def aplicar_padroes(raiz):
    """
    A cor PADRÃO de todo widget criado a partir de agora.

    Sem isto, "todas as telas escuras" seria reescrever 20 janelas: boa
    parte delas não pede cor nenhuma e fica com o cinza claro de fábrica
    do Tk — que no meio de uma tela escura vira um retângulo branco com
    texto preto. option_add resolve todas de uma vez, e só afeta widget
    que NÃO pediu cor explícita (os nossos cartões continuam mandando).

    Vale pro que for criado DEPOIS da chamada: por isso a troca de tema
    remonta a tela principal, e as outras janelas nascem certas quando
    forem abertas.
    """
    op = raiz.option_add
    op("*Background", cores.fundo)
    op("*background", cores.fundo)
    op("*Foreground", cores.texto)
    op("*foreground", cores.texto)
    op("*highlightBackground", cores.fundo)
    op("*highlightColor", cores.borda)
    op("*selectBackground", cores.acento)
    op("*selectForeground", cores.sobre_acento)
    for classe in ("Entry", "Text", "Listbox", "Spinbox"):
        op("*%s.background" % classe, cores.campo)
        op("*%s.foreground" % classe, cores.texto)
        op("*%s.insertBackground" % classe, cores.texto)
    op("*Canvas.background", cores.fundo)
    # o quadradinho de dentro do checkbox/radio: no escuro ele vem branco
    op("*Checkbutton.selectColor", cores.campo)
    op("*Radiobutton.selectColor", cores.campo)
    op("*Checkbutton.activeBackground", cores.fundo)
    op("*Button.activeBackground", cores.borda)
    op("*Button.activeForeground", cores.texto)
    op("*Menu.background", cores.cartao)
    op("*Menu.foreground", cores.texto)
    _estilo_ttk(raiz)


def _estilo_ttk(raiz):
    """
    Os widgets do ttk (Combobox, Treeview, barra de rolagem) não olham o
    option_add: eles têm tema próprio. E o tema nativo do Windows ignora
    cor — por isso o escuro precisa do 'clam', que aceita. No claro volta
    pro nativo, que é o que ele sempre viu.
    """
    import tkinter.ttk as ttk

    estilo = ttk.Style(raiz)
    if not cores.escuro:
        try:
            estilo.theme_use("vista")
        except Exception:
            estilo.theme_use("default")
        return
    try:
        estilo.theme_use("clam")
    except Exception:
        return
    estilo.configure(".", background=cores.fundo, foreground=cores.texto,
                     fieldbackground=cores.campo, bordercolor=cores.borda,
                     lightcolor=cores.borda, darkcolor=cores.borda,
                     troughcolor=cores.campo, arrowcolor=cores.texto,
                     insertcolor=cores.texto)
    # As cores de ESTADO (desligado, mouse em cima, apertado) não vêm do
    # configure acima: o clam tem um 'map' próprio pra elas, e map ganha
    # de configure. Sem desfazer esses mapas, o cinza claro de fábrica do
    # clam volta na hora — foi o que aconteceu com a barra de rolagem que
    # não tem o que rolar (ela fica 'disabled' e saía branca no escuro).
    estilo.map(".",
               background=[("disabled", cores.fundo), ("active", cores.borda)],
               foreground=[("disabled", cores.texto2)],
               selectbackground=[("!focus", cores.borda)])
    estilo.configure("TCombobox", fieldbackground=cores.campo, background=cores.cartao,
                     foreground=cores.texto, arrowcolor=cores.texto)
    estilo.map("TCombobox",
               fieldbackground=[("readonly", cores.campo)],
               selectbackground=[("readonly", cores.campo)],
               selectforeground=[("readonly", cores.texto)],
               background=[("active", cores.borda), ("pressed", cores.borda)],
               foreground=[("readonly", cores.texto)])
    for classe in ("TEntry", "TSpinbox"):
        estilo.configure(classe, fieldbackground=cores.campo, foreground=cores.texto,
                         insertcolor=cores.texto)
        estilo.map(classe, fieldbackground=[("readonly", cores.campo)],
                   background=[("readonly", cores.campo)])
    raiz.option_add("*TCombobox*Listbox.background", cores.campo)
    raiz.option_add("*TCombobox*Listbox.foreground", cores.texto)
    raiz.option_add("*TCombobox*Listbox.selectBackground", cores.acento)
    estilo.configure("Treeview", background=cores.campo, fieldbackground=cores.campo,
                     foreground=cores.texto, bordercolor=cores.borda)
    estilo.configure("Treeview.Heading", background=cores.cartao, foreground=cores.texto2)
    estilo.map("Treeview", background=[("selected", cores.acento)],
               foreground=[("selected", cores.sobre_acento)])
    estilo.configure("TScrollbar", background=cores.cartao, troughcolor=cores.fundo,
                     arrowcolor=cores.texto2, bordercolor=cores.borda)
    # barra sem nada pra rolar: some no fundo em vez de virar uma tarja
    estilo.map("TScrollbar",
               background=[("disabled", cores.fundo), ("active", cores.borda)],
               bordercolor=[("disabled", cores.fundo)],
               arrowcolor=[("disabled", cores.fundo)])
    estilo.configure("TNotebook", background=cores.fundo, bordercolor=cores.borda)
    estilo.configure("TNotebook.Tab", background=cores.cartao, foreground=cores.texto)
    estilo.map("TNotebook.Tab", background=[("selected", cores.fundo)])
    estilo.configure("TProgressbar", background=cores.acento, troughcolor=cores.campo)
    estilo.configure("TSeparator", background=cores.borda)
    estilo.configure("TButton", background=cores.cartao, foreground=cores.texto)
    estilo.map("TButton", background=[("active", cores.borda), ("pressed", cores.borda),
                                      ("disabled", cores.fundo)])


def placa_logo(pai, reduzir=2):
    """
    O logo da Uny CV numa plaquinha CLARA.

    O desenho tem preto e cinza escuro ("COMUNICAÇÃO VISUAL"), que somem
    no fundo escuro — a placa é o que mantém ele legível. Por isso mora
    aqui e não em cada tela: são quatro telas com o mesmo logo.

    Devolve o frame pra quem chamou posicionar (pack ou grid), ou None se
    o arquivo não existir — num clone sem a pasta assets a tela abre sem
    logo em vez de quebrar.
    """
    import tkinter as tk

    from branding import CAMINHO_LOGO_GUI

    if not CAMINHO_LOGO_GUI.exists():
        return None
    try:
        # subsample em vez de Pillow: aqui não vale puxar a dependência
        imagem = tk.PhotoImage(file=str(CAMINHO_LOGO_GUI))
        if reduzir > 1:
            imagem = imagem.subsample(reduzir, reduzir)
    except tk.TclError:
        return None
    placa = tk.Frame(pai, bg=cores.branco)
    placa.imagem = imagem          # sem guardar a referência o Tk descarta a foto
    tk.Label(placa, image=imagem, bg=cores.branco).pack(padx=6, pady=5)
    return placa


def carregar(config=None):
    """O tema gravado no config.json (ou o padrão). Chamar ao abrir o programa."""
    dados = config if config is not None else _config.carregar_config()
    cores.trocar(dados.get("tema") or PADRAO)
    return cores.nome


def alternar(config=None):
    """
    Troca claro <-> escuro, grava a escolha e devolve (nome, config).
    Gravar é o ponto: a escolha tem que valer na próxima vez que ele
    abrir o programa, senão o botão é um truque de festa.
    """
    novo = "claro" if cores.escuro else "escuro"
    cores.trocar(novo)
    dados = config if config is not None else _config.carregar_config()
    dados["tema"] = novo
    _config.salvar_config(dados)
    return novo, dados
