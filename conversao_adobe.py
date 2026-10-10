"""
Conversão de EPS/PSD/TIF pra PDF usando o Illustrator/Photoshop já
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
import math
import pathlib

try:
    import pythoncom
    import win32com.client
    COM_DISPONIVEL = True
except ImportError:
    COM_DISPONIVEL = False


def _garantir_com_iniciado():
    """
    COM precisa ser inicializado em CADA thread que for usá-lo — não é
    automático. A tela principal roda o processamento numa thread
    separada (pra não travar a janela — ver gui.py), então a primeira
    automação COM chamada ali sempre falhava com "CoInitialize não foi
    chamado" (bug real de produção, 2026-09-01: conversão de TIF da
    FESTA ALEMÃ falhou silenciosamente por causa disso — nunca tinha
    aparecido antes porque nenhum pedido anterior tinha EPS/PSD/TIF
    processado de verdade pela tela, só por script direto, que já roda
    numa thread com COM iniciado). Chamar de novo numa thread já
    iniciada não dá erro (só devolve S_FALSE) — seguro chamar sempre,
    no início de cada conversão.
    """
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

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

    _garantir_com_iniciado()
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

    _garantir_com_iniciado()
    app = win32com.client.Dispatch("Photoshop.Application")
    app.DisplayDialogs = _PS_NAO_EXIBIR_DIALOGOS
    doc = app.Open(str(caminho_psd))
    try:
        opcoes = win32com.client.Dispatch("Photoshop.PDFSaveOptions")
        doc.SaveAs(str(caminho_pdf_destino), opcoes, True)  # asCopy=True — nunca sobrescreve o .psd original
    finally:
        doc.Close(_PS_NAO_SALVAR)


def converter_tif_para_pdf(caminho_tif, caminho_pdf_destino):
    """
    Igual converter_psd_para_pdf, mesmo programa (Photoshop) — TIF de
    arte de impressão (alta resolução, CMYK, às vezes vários GB) trava
    o PyMuPDF por muito tempo só pra ABRIR (testado ao vivo, 2026-08-31:
    um TIF de 3,1GB não abriu nem depois de vários minutos), enquanto o
    Photoshop já é feito pra esse tipo de arquivo — pedido do usuário
    ("abertura do tif... no photoshop suporta").
    """
    if not COM_DISPONIVEL:
        raise RuntimeError("pywin32 não está instalado — não dá pra automatizar o Photoshop.")

    _garantir_com_iniciado()
    app = win32com.client.Dispatch("Photoshop.Application")
    app.DisplayDialogs = _PS_NAO_EXIBIR_DIALOGOS
    doc = app.Open(str(caminho_tif))
    try:
        opcoes = win32com.client.Dispatch("Photoshop.PDFSaveOptions")
        doc.SaveAs(str(caminho_pdf_destino), opcoes, True)  # asCopy=True — nunca sobrescreve o .tif original
    finally:
        doc.Close(_PS_NAO_SALVAR)


def reduzir_pdf_grande(caminho_pdf, caminho_pdf_reduzido, dpi_alvo=150):
    """
    Abre um PDF cuja imagem embutida está grande demais pra essa
    máquina processar (achado real, 2026-09-01: PDFs de produção
    nascidos de TIF gigante — malloc falhando ao gerar a etiqueta,
    mesmo com pouca memória de sobra) e salva uma CÓPIA com a
    resolução reduzida pra 'dpi_alvo' em 'caminho_pdf_reduzido' — nunca
    sobrescreve nem move o original, só cria um arquivo novo à parte.
    Pedido do usuário (2026-09-01): "pode reduzir o que precisar... a
    única coisa é não mexer nos arquivos originais".

    Só define a resolução de abertura (Photoshop.PDFOpenOptions) —
    deixa cor/anti-serrilhado no padrão do próprio Photoshop, pra não
    arriscar um valor de enum errado (ver o mesmo cuidado documentado
    em monitor_onedrive sobre nunca assumir um valor sem testar ao
    vivo). AINDA NÃO TESTADO contra o Photoshop de verdade (memória da
    máquina estava crítica demais pra testar com segurança no momento
    em que isso foi escrito) — testar com um arquivo real assim que a
    máquina estiver com memória livre de novo.
    """
    if not COM_DISPONIVEL:
        raise RuntimeError("pywin32 não está instalado — não dá pra automatizar o Photoshop.")

    _garantir_com_iniciado()
    app = win32com.client.Dispatch("Photoshop.Application")
    app.DisplayDialogs = _PS_NAO_EXIBIR_DIALOGOS
    opcoes_abertura = win32com.client.Dispatch("Photoshop.PDFOpenOptions")
    opcoes_abertura.Resolution = dpi_alvo
    app.Open(str(caminho_pdf), opcoes_abertura)
    doc = app.ActiveDocument
    try:
        opcoes_salvar = win32com.client.Dispatch("Photoshop.PDFSaveOptions")
        doc.SaveAs(str(caminho_pdf_reduzido), opcoes_salvar, True)  # asCopy=True — nunca sobrescreve o original
    finally:
        doc.Close(_PS_NAO_SALVAR)


def reduzir_imagem_grande(caminho_imagem, caminho_pdf_reduzido, largura_max_px=3000):
    """
    Mesma ideia de reduzir_pdf_grande, mas pra imagem crua (PNG/JPG) —
    pedido do usuário (2026-09-01): "preciso adicionar a extensão png,
    preciso que leia esse formato também via Photoshop" (mesmo caminho
    de resgate já usado pro PDF/TIF grande demais). PNG/JPG continuam
    lidos direto pelo PyMuPDF no caso normal (ver EXTENSOES_SUPORTADAS
    em processamento.py) — isso aqui só entra quando o arquivo já
    falhou por falta de memória (ver processamento._obter_arte_reduzida).

    Diferente do PDF (onde dá pra pedir a resolução já na abertura),
    imagem crua abre no tamanho nativo — por isso reduz DEPOIS de
    aberta (Document.ResizeImage), só se a largura já ultrapassar
    'largura_max_px'. Nunca sobrescreve nem move o original.

    AINDA NÃO TESTADO contra o Photoshop de verdade (mesma ressalva de
    reduzir_pdf_grande) — testar com um PNG real assim que possível.
    """
    if not COM_DISPONIVEL:
        raise RuntimeError("pywin32 não está instalado — não dá pra automatizar o Photoshop.")

    _garantir_com_iniciado()
    app = win32com.client.Dispatch("Photoshop.Application")
    app.DisplayDialogs = _PS_NAO_EXIBIR_DIALOGOS
    doc = app.Open(str(caminho_imagem))
    try:
        largura_atual = doc.Width
        if largura_atual > largura_max_px:
            altura_atual = doc.Height
            proporcao = largura_max_px / largura_atual
            doc.ResizeImage(largura_max_px, altura_atual * proporcao)
        opcoes = win32com.client.Dispatch("Photoshop.PDFSaveOptions")
        doc.SaveAs(str(caminho_pdf_reduzido), opcoes, True)  # asCopy=True — nunca sobrescreve o original
    finally:
        doc.Close(_PS_NAO_SALVAR)


CONVERSORES_POR_EXTENSAO = {
    ".eps": converter_eps_para_pdf,
    ".psd": converter_psd_para_pdf,
    ".tif": converter_tif_para_pdf,
    ".tiff": converter_tif_para_pdf,
}


def _validar_pdf_convertido(caminho_pdf):
    """Confere o resultado antes de retirar a arte original da entrada."""
    import pymupdf

    if not caminho_pdf.is_file() or caminho_pdf.stat().st_size == 0:
        raise ValueError("a conversão não gerou um PDF com conteúdo")
    with pymupdf.open(str(caminho_pdf)) as documento:
        if not documento.is_pdf:
            raise ValueError("o arquivo gerado não é um PDF")
        if documento.page_count <= 0:
            raise ValueError("o PDF gerado não contém páginas")
        for numero, pagina in enumerate(documento, start=1):
            if not pagina.get_bboxlog():
                raise ValueError(f"o PDF gerado está sem conteúdo de arte na página {numero}")
            if any(not math.isfinite(valor) or valor <= 0
                   for valor in (pagina.rect.width, pagina.rect.height)):
                raise ValueError(f"o PDF gerado tem medida inválida na página {numero}")


def _remover_pdf_da_tentativa(caminho_pdf, nome_arquivo, logger_emitir):
    """Desfaz apenas a saída nova; nunca toca o original ou um PDF anterior."""
    try:
        caminho_pdf.unlink(missing_ok=True)
    except OSError as erro:
        logger_emitir(
            "warn",
            f"'{nome_arquivo}': a saída desta tentativa '{caminho_pdf.name}' não pôde ser removida "
            f"({erro}). Não use esse PDF até resolver o aviso. O original foi mantido.",
            nome_arquivo, "AVISO - SAIDA NAO REMOVIDA",
        )


def converter_se_necessario(pasta_entrada, nome_arquivo, pasta_originais, logger_emitir,
                           conversores=None, guardar_original=True, pasta_pdf=None):
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

    Com 'guardar_original=False', mantém a arte de entrada no lugar;
    quem monta o lote pode arquivá-la só depois de publicar a montagem.
    No modo padrão, falha ao arquivar também desfaz o PDF novo, para
    evitar que original e conversão sejam produzidos separadamente.
    'pasta_pdf' permite preparar a derivada em outra pasta, preservando
    o caminho do original e o retorno do nome do PDF. Sem esse argumento,
    o PDF continua sendo gerado na própria pasta de entrada.

    Retorna o nome do PDF gerado (pra entrar no processamento normal
    dessa mesma rodada), ou None se o arquivo não precisava de
    conversão nenhuma. Falha de conversão nunca trava a rodada — só
    avisa e o arquivo original fica onde estava, intocado.
    """
    extensao = pathlib.Path(nome_arquivo).suffix.lower()
    conversor = (conversores or CONVERSORES_POR_EXTENSAO).get(extensao)
    if conversor is None:
        return None

    # sempre absoluto: o Illustrator/Photoshop roda num processo à parte
    # (COM), então um caminho relativo seria resolvido em cima do
    # diretório de trabalho DELE, não do processo Python que chamou —
    # sem isso, a conversão falhava com "arquivo não encontrado" mesmo
    # com o arquivo existindo de verdade (bug real visto em produção,
    # 2026-08-29).
    pasta = pathlib.Path(pasta_entrada).resolve()
    caminho_original = pasta / nome_arquivo
    pasta_destino = pasta if pasta_pdf is None else pathlib.Path(pasta_pdf).resolve()
    caminho_pdf = None
    destino_livre = False

    erro_conversao = None
    try:
        if pasta_pdf is not None:
            pasta_destino.mkdir(parents=True, exist_ok=True)
        caminho_pdf = pasta_destino / (pathlib.Path(nome_arquivo).stem + ".pdf")
        contador = 2
        while caminho_pdf.exists():
            caminho_pdf = pasta_destino / f"{pathlib.Path(nome_arquivo).stem} ({contador}).pdf"
            contador += 1
        destino_livre = True
        conversor(str(caminho_original), str(caminho_pdf))
        _validar_pdf_convertido(caminho_pdf)
    except Exception as e:
        erro_conversao = str(e)
    if erro_conversao is not None:
        # Fora do except: o traceback do leitor de PDF pode manter o
        # arquivo aberto no Windows até a exceção sair de contexto.
        # Este destino estava livre antes da tentativa. Um PDF inválido
        # não pode ficar na entrada para ser tratado como uma nova arte;
        # o homônimo anterior e o original nunca são apagados aqui.
        if destino_livre:
            _remover_pdf_da_tentativa(caminho_pdf, nome_arquivo, logger_emitir)
        logger_emitir(
            "err",
            f"'{nome_arquivo}': não foi possível converter e conferir o PDF "
            f"({extensao.upper()} via Adobe): {erro_conversao}. O original foi mantido.",
            nome_arquivo, f"ERRO - CONVERSAO {extensao.upper()} FALHOU",
        )
        return None

    if not guardar_original:
        logger_emitir("ok", f"'{nome_arquivo}' convertido pra PDF: {caminho_pdf.name}",
                      nome_arquivo, "CONVERTIDO")
        return caminho_pdf.name

    pasta_originais = pathlib.Path(pasta_originais)
    erro_arquivo_original = None
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
        erro_arquivo_original = str(e)
    if erro_arquivo_original is not None:
        _remover_pdf_da_tentativa(caminho_pdf, nome_arquivo, logger_emitir)
        logger_emitir(
            "err",
            f"'{nome_arquivo}': não foi possível arquivar o original em "
            f"'{pasta_originais.name}': {erro_arquivo_original}. "
            "A conversão não foi liberada; o original foi mantido. Feche a arte e tente novamente.",
            nome_arquivo, "ERRO - NAO ARQUIVOU ORIGINAL",
        )
        return None

    logger_emitir("ok", f"'{nome_arquivo}' convertido pra PDF: {caminho_pdf.name}",
                  nome_arquivo, "CONVERTIDO")
    return caminho_pdf.name
