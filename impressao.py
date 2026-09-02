"""
Impressão de PDFs (OS/Checklist) numa impressora física.

Usa os verbos "print"/"printto" do Shell do Windows em vez de uma
biblioteca própria de renderização — quem realmente imprime é o leitor
de PDF registrado pro .pdf no Windows (neste computador, o Acrobat DC,
que já registra os dois verbos e imprime sem abrir janela nenhuma na
tela). Isso significa que a impressão só funciona se houver algum
leitor de PDF instalado com esses verbos registrados.
"""
import pathlib

try:
    import win32api
    import win32print
    DISPONIVEL = True
except ImportError:
    DISPONIVEL = False


def listar_impressoras():
    """Nomes de todas as impressoras que o Windows reconhece neste computador (instaladas/conectadas)."""
    if not DISPONIVEL:
        return []
    impressoras = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
    return sorted(nome for _, _, nome, _ in impressoras)


def impressora_padrao():
    """Impressora padrão configurada no Windows, ou None se não houver nenhuma."""
    if not DISPONIVEL:
        return None
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def imprimir_pdf(caminho, impressora=None):
    """
    Manda o PDF em 'caminho' pra impressora, sem abrir nada na tela. Se
    'impressora' vier vazio/None, usa a impressora padrão do Windows.

    Levanta RuntimeError se não conseguir (arquivo inexistente, nenhum
    leitor de PDF com os verbos de impressão registrado, impressora
    desligada/removida, etc.) — nunca deixa uma exceção genérica do
    win32api vazar pra fora.
    """
    if not DISPONIVEL:
        raise RuntimeError("Impressão não disponível nesse computador (pywin32 não instalado).")
    caminho = pathlib.Path(caminho)
    if not caminho.exists():
        raise RuntimeError(f"Arquivo não encontrado: {caminho}")

    try:
        if impressora:
            resultado = win32api.ShellExecute(0, "printto", str(caminho), f'"{impressora}"', ".", 0)
        else:
            resultado = win32api.ShellExecute(0, "print", str(caminho), None, ".", 0)
    except Exception as e:
        raise RuntimeError(f"Não foi possível imprimir '{caminho.name}': {e}") from e

    if resultado <= 32:
        raise RuntimeError(
            f"Não foi possível imprimir '{caminho.name}' — o Windows recusou o pedido "
            "(confira se há um leitor de PDF instalado, ex. Adobe Acrobat, e se a impressora está ligada)."
        )
