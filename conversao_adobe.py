"""
Conversão de EPS/PSD pra PDF usando o Illustrator/Photoshop já
instalados na máquina, via automação COM (Windows) — não depende de
Ghostscript nem de nenhuma instalação nova, só dos programas que já
existem aqui.

Nunca fecha (Quit) o Illustrator/Photoshop — se o usuário já estiver
com um dos dois aberto trabalhando em outra coisa, Dispatch() conecta
nessa MESMA instância em vez de abrir uma nova; fechar o app inteiro
derrubaria o trabalho dele sem aviso. Só fecha (Close) o documento
específico que essa conversão abriu, sempre sem salvar em cima do
arquivo original.
"""
import pathlib

try:
    import win32com.client
    COM_DISPONIVEL = True
except ImportError:
    COM_DISPONIVEL = False

# aiDontDisplayAlerts / psDisplayNoDialogs — impede caixa de diálogo
# (fonte faltando, perfil de cor etc.) de travar a automação esperando
# clique que nunca vem.
_AI_NAO_EXIBIR_ALERTAS = 2
_PS_NAO_EXIBIR_DIALOGOS = 3
_AI_NAO_SALVAR = 2  # aiDoNotSaveChanges
_PS_NAO_SALVAR = 2  # psDoNotSaveChanges


def converter_eps_para_pdf(caminho_eps, caminho_pdf_destino):
    """
    Abre 'caminho_eps' no Illustrator e salva como PDF em
    'caminho_pdf_destino'. Levanta exceção se o Illustrator não estiver
    instalado/registrado ou se a conversão falhar por qualquer motivo —
    quem chama decide como reagir (nunca deixa o arquivo original sem
    aviso nenhum).
    """
    if not COM_DISPONIVEL:
        raise RuntimeError("pywin32 não está instalado — não dá pra automatizar o Illustrator.")

    app = win32com.client.Dispatch("Illustrator.Application")
    app.UserInteractionLevel = _AI_NAO_EXIBIR_ALERTAS
    doc = app.Open(str(caminho_eps))
    try:
        opcoes = win32com.client.Dispatch("Illustrator.PDFSaveOptions")
        doc.SaveAs(str(caminho_pdf_destino), opcoes)
    finally:
        doc.Close(_AI_NAO_SALVAR)


def converter_psd_para_pdf(caminho_psd, caminho_pdf_destino):
    """
    Abre 'caminho_psd' no Photoshop e salva como PDF em
    'caminho_pdf_destino'. Mesmo espírito de converter_eps_para_pdf —
    levanta exceção em caso de falha, nunca inventa um resultado.
    """
    if not COM_DISPONIVEL:
        raise RuntimeError("pywin32 não está instalado — não dá pra automatizar o Photoshop.")

    app = win32com.client.Dispatch("Photoshop.Application")
    app.DisplayDialogs = _PS_NAO_EXIBIR_DIALOGOS
    doc = app.Open(str(caminho_psd))
    try:
        opcoes = win32com.client.Dispatch("Photoshop.PDFSaveOptions")
        doc.SaveAs(str(caminho_pdf_destino), opcoes, True)  # asCopy=True — nunca sobrescreve o .psd original
    finally:
        doc.Close(_PS_NAO_SALVAR)


CONVERSORES_POR_EXTENSAO = {
    ".eps": converter_eps_para_pdf,
    ".psd": converter_psd_para_pdf,
}


def converter_se_necessario(pasta_entrada, nome_arquivo, pasta_originais, logger_emitir, conversores=None):
    """
    Se 'nome_arquivo' for um EPS/PSD (ver CONVERSORES_POR_EXTENSAO),
    converte pra PDF na mesma pasta de entrada (nome novo, nunca
    sobrescreve — sufixo numérico em caso de colisão) e move o arquivo
    original pra dentro de 'pasta_originais' (nunca apaga — mesmo
    espírito de todo o resto do projeto, só tira da vista pra não ficar
    tentando converter de novo toda rodada).

    'conversores' (opcional) sobrescreve CONVERSORES_POR_EXTENSAO — só
    existe pra teste automatizado poder simular a conversão sem abrir
    Illustrator/Photoshop de verdade (lento e depende do programa estar
    instalado); em uso normal, sempre usa o dicionário real.

    Retorna o nome do PDF gerado (pra entrar no processamento normal
    dessa mesma rodada), ou None se o arquivo não precisava de
    conversão nenhuma. Falha de conversão nunca trava a rodada — só
    avisa e o arquivo original fica onde estava, intocado.
    """
    extensao = pathlib.Path(nome_arquivo).suffix.lower()
    conversor = (conversores or CONVERSORES_POR_EXTENSAO).get(extensao)
    if conversor is None:
        return None

    pasta = pathlib.Path(pasta_entrada)
    caminho_original = pasta / nome_arquivo
    caminho_pdf = pasta / (pathlib.Path(nome_arquivo).stem + ".pdf")
    if caminho_pdf.exists():
        contador = 2
        while caminho_pdf.exists():
            caminho_pdf = pasta / f"{pathlib.Path(nome_arquivo).stem} ({contador}).pdf"
            contador += 1

    try:
        conversor(str(caminho_original), str(caminho_pdf))
    except Exception as e:
        logger_emitir(
            "err",
            f"'{nome_arquivo}': não foi possível converter pra PDF ({extensao.upper()} via Adobe): {e}",
            nome_arquivo, f"ERRO - CONVERSAO {extensao.upper()} FALHOU",
        )
        return None

    logger_emitir("ok", f"'{nome_arquivo}' convertido pra PDF: {caminho_pdf.name}", nome_arquivo, "CONVERTIDO")

    pasta_originais = pathlib.Path(pasta_originais)
    try:
        pasta_originais.mkdir(parents=True, exist_ok=True)
        destino_original = pasta_originais / nome_arquivo
        if destino_original.exists():
            contador = 2
            while destino_original.exists():
                destino_original = pasta_originais / f"{pathlib.Path(nome_arquivo).stem} ({contador}){extensao}"
                contador += 1
        caminho_original.rename(destino_original)
    except OSError as e:
        logger_emitir(
            "warn",
            f"'{nome_arquivo}': convertido com sucesso, mas não foi possível mover o original pra "
            f"'{pasta_originais.name}': {e}. O arquivo original ficou onde estava.",
            nome_arquivo, "AVISO - NAO MOVEU ORIGINAL",
        )

    return caminho_pdf.name
