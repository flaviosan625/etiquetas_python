"""
O atalho do sistema na área de trabalho, com o logo da Uny CV.

Pedido do usuário (2026-09-23): *"criar um botão atalho na área de
trabalho com logo da Uny CV para abrir o sistema, fica mais prático"*.

Duas coisas moram aqui:

  - `gerar_icone()` monta `assets/uny_cv.ico` a partir do logo. O logo é
    DEITADO (2,2 por 1) e ícone do Windows é quadrado: esticar viraria
    uma tarja ilegível a 48px, que é o tamanho que ele vê na área de
    trabalho. Então o ícone usa só o **símbolo** (a parte colorida da
    esquerda), numa plaquinha branca — o desenho tem preto e some em
    papel de parede escuro, mesmo motivo da placa da tela
    (`tema.placa_logo`).
  - `criar()` escreve o `.lnk` apontando pro **pythonw.exe** da `.venv`.
    pythonw e não python: com `python.exe` fica uma janela preta de
    console aberta atrás do programa o tempo todo — é por isso que o
    atalho não usa o `abrir_gerador.bat`, que existe pra quando se quer
    justamente ver o console.

Sem Tk aqui de propósito: é lógica, e uma tela pode chamar depois
("o sistema precisa funcionar totalmente pela janela").
"""
import pathlib
import sys

import branding
import caminhos

NOME_ATALHO = "Uny CV.lnk"
# ASCII PURO aqui: o campo de descrição do .lnk (a dica que aparece com o
# mouse parado em cima) é gravado em ANSI pelo WScript.Shell — um
# travessão vira "?" calado. Mesma história do .bat.
DESCRICAO = "Uny CV - etiquetas, OS, checklist, estoque e recebimento de artes"

# Os tamanhos que o Windows pede: 16 na barra de tarefas, 48 na área de
# trabalho, 256 no modo "ícones extra grandes".
TAMANHOS = (16, 24, 32, 48, 64, 128, 256)


def caminho_icone():
    return caminhos.PASTA_PROGRAMA / "assets" / "uny_cv.ico"


def _caixa_do_simbolo(logo):
    """
    Só o símbolo: a caixa dele dentro do logo inteiro.

    Acha o vão em branco entre o símbolo e a palavra "UNY" pelo canal de
    transparência, em vez de número cravado — assim trocar o arquivo do
    logo não quebra o ícone calado. Sem vão nenhum, devolve o logo todo.
    """
    from PIL import Image

    largura, altura = logo.size
    # a transparência espremida numa tirinha de 1px de altura: cada byte é
    # a média de uma coluna, e coluna sem desenho nenhum dá 0
    perfil = logo.split()[-1].resize((largura, 1), Image.BOX).tobytes()
    minimo_do_vao = max(8, largura // 50)
    inicio = next((x for x, v in enumerate(perfil) if v), 0)
    x = inicio
    while x < largura:
        if perfil[x]:
            x += 1
            continue
        fim = x
        while fim < largura and not perfil[fim]:
            fim += 1
        if fim - x >= minimo_do_vao and fim < largura:
            return (inicio, 0, x, altura)
        x = fim
    return (0, 0, largura, altura)


def gerar_icone(destino=None, forcar=False):
    """O .ico da plaquinha branca com o símbolo. Devolve o caminho."""
    from PIL import Image, ImageDraw

    destino = pathlib.Path(destino) if destino else caminho_icone()
    if destino.exists() and not forcar:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)

    logo = Image.open(branding.CAMINHO_LOGO).convert("RGBA")
    simbolo = logo.crop(_caixa_do_simbolo(logo))

    # desenhado em 4x e reduzido no fim: é o que deixa o canto arredondado
    # liso, porque o rounded_rectangle não tem antisserrilhado
    escala = 4
    lado = 256 * escala
    placa = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    ImageDraw.Draw(placa).rounded_rectangle((0, 0, lado - 1, lado - 1),
                                            radius=int(lado * 0.18), fill="white")
    simbolo.thumbnail((int(lado * 0.60), int(lado * 0.60)), Image.LANCZOS)
    placa.alpha_composite(simbolo, ((lado - simbolo.width) // 2, (lado - simbolo.height) // 2))
    placa = placa.resize((256, 256), Image.LANCZOS)
    placa.save(destino, format="ICO", sizes=[(n, n) for n in TAMANHOS])
    return destino


def alvo_do_atalho():
    """
    (programa, argumentos) que o atalho dispara.

    Rodando do código, é o pythonw.exe da venv com o main.py. Virando
    executável, é o próprio .exe sem argumento nenhum — e é só isto aqui
    que muda, como em `caminhos.comando_python`.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    programa, *_ = caminhos.comando_python(com_console=False)
    return programa, '"%s"' % (caminhos.PASTA_PROGRAMA / "main.py")


def criar(pasta=None, nome=NOME_ATALHO, shell=None, icone=None):
    """
    Escreve o atalho e devolve o caminho dele.

    Sem `pasta`, vai na área de trabalho que o PRÓPRIO Windows informa —
    não em `~/Desktop` cravado, que erra quando a área de trabalho está
    redirecionada pro OneDrive (é o caso de várias máquinas da empresa).
    """
    icone = icone or gerar_icone()
    programa, argumentos = alvo_do_atalho()
    if shell is None:
        from win32com.client import Dispatch

        shell = Dispatch("WScript.Shell")
    pasta = pathlib.Path(pasta) if pasta else pathlib.Path(shell.SpecialFolders("Desktop"))

    caminho = pasta / nome
    atalho = shell.CreateShortCut(str(caminho))
    atalho.TargetPath = programa
    atalho.Arguments = argumentos
    atalho.WorkingDirectory = str(caminhos.PASTA_PROGRAMA)
    atalho.IconLocation = str(icone)
    atalho.Description = DESCRICAO
    atalho.Save()
    return caminho


if __name__ == "__main__":
    print(criar())
