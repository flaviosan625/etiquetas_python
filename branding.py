"""
Módulo central de Identidade Visual e Branding (desacoplamento de marca).

Gerencia:
  - Nome da empresa e slogan configuráveis (para títulos de janelas, cabeçalhos e relatórios).
  - Caminhos dos logotipos (alta resolução para impressão e reduzido para a interface gráfica).
  - Ícone da aplicação (.ico) para atalho e barra de tarefas.
  - Função utilitária para inserir o logo em páginas de PDF (PyMuPDF), mantendo proporção e qualidade.
  - Texto de rodapé para romaneios de retirada e documentos.

Por padrão, assume os dados da Uny CV com fallback seguro: se o arquivo do logo não existir
(ex: pasta 'assets' não veio num clone novo), não quebra o programa — apenas omite o desenho
silenciosamente.
"""
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent
_ASSETS_DIR = BASE_DIR / "assets"

# Caminhos padrão originais (mantidos no topo para compatibilidade com testes e monkeypatch)
CAMINHO_LOGO_PADRAO = _ASSETS_DIR / "logo_empresa.png"
if not CAMINHO_LOGO_PADRAO.exists() and (_ASSETS_DIR / "logo_uny_cv.png").exists():
    CAMINHO_LOGO_PADRAO = _ASSETS_DIR / "logo_uny_cv.png"

CAMINHO_LOGO_GUI_PADRAO = _ASSETS_DIR / "logo_empresa_gui.png"
if not CAMINHO_LOGO_GUI_PADRAO.exists() and (_ASSETS_DIR / "logo_uny_cv_gui.png").exists():
    CAMINHO_LOGO_GUI_PADRAO = _ASSETS_DIR / "logo_uny_cv_gui.png"

CAMINHO_ICONE_PADRAO = _ASSETS_DIR / "icone.ico"
if not CAMINHO_ICONE_PADRAO.exists() and (_ASSETS_DIR / "uny_cv.ico").exists():
    CAMINHO_ICONE_PADRAO = _ASSETS_DIR / "uny_cv.ico"

# Constantes de módulo esperadas pelo sistema e pela suíte de testes
CAMINHO_LOGO = CAMINHO_LOGO_PADRAO
CAMINHO_LOGO_GUI = CAMINHO_LOGO_GUI_PADRAO

NOME_EMPRESA_PADRAO = "Comunicação Visual"
SLOGAN_PADRAO = "Automação e Pré-Impressão"


def _carregar_config_seguro(config=None):
    """Obtém o dicionário de configurações sem falhar se o arquivo não existir."""
    if isinstance(config, dict):
        return config
    try:
        from config import carregar_config
        return carregar_config()
    except Exception:
        return {}


def obter_config_empresa(config=None):
    """Retorna o bloco 'empresa' de configurações ou um dicionário padrão."""
    cfg = _carregar_config_seguro(config)
    return cfg.get("empresa", {})


def obter_nome_empresa(config=None):
    """Nome oficial da empresa cadastrado (padrão: 'Uny CV')."""
    empresa = obter_config_empresa(config)
    nome = empresa.get("nome")
    if nome and str(nome).strip():
        return str(nome).strip()
    return NOME_EMPRESA_PADRAO


def obter_slogan_empresa(config=None):
    """Slogan ou ramo de atividade da empresa (padrão: 'Comunicação Visual')."""
    empresa = obter_config_empresa(config)
    slogan = empresa.get("slogan")
    if slogan and str(slogan).strip():
        return str(slogan).strip()
    return SLOGAN_PADRAO


def obter_caminho_logo(caminho=None, config=None):
    """
    Localiza o logotipo de alta resolução:
      1. Se 'caminho' explícito foi passado, usa ele.
      2. Se CAMINHO_LOGO do módulo foi monkeypatched em teste, usa ele.
      3. Se houver caminho customizado no config ('empresa.logo') e o arquivo existir, usa ele.
      4. Se houver 'assets/logo_empresa.png' na pasta do programa, usa ele.
      5. Fallback para CAMINHO_LOGO_PADRAO (assets/logo_uny_cv.png).
    """
    if caminho:
        return pathlib.Path(caminho)
    # Respeita monkeypatch direto no módulo em tempo de teste
    if CAMINHO_LOGO != CAMINHO_LOGO_PADRAO:
        return pathlib.Path(CAMINHO_LOGO)
    empresa = obter_config_empresa(config)
    logo_cfg = empresa.get("logo")
    if logo_cfg:
        p = pathlib.Path(logo_cfg)
        if not p.is_absolute():
            p = BASE_DIR / p
        if p.exists():
            return p
    candidato_empresa = _ASSETS_DIR / "logo_empresa.png"
    if candidato_empresa.exists():
        return candidato_empresa
    return CAMINHO_LOGO_PADRAO


def obter_caminho_logo_gui(caminho=None, config=None):
    """
    Localiza o logotipo reduzido para a interface gráfica (230px de largura):
      1. Se 'caminho' explícito foi passado, usa ele.
      2. Se CAMINHO_LOGO_GUI do módulo foi monkeypatched em teste, usa ele.
      3. Se houver caminho customizado no config ('empresa.logo_gui') e existir, usa ele.
      4. Se houver 'assets/logo_empresa_gui.png', usa ele.
      5. Fallback para CAMINHO_LOGO_GUI_PADRAO (assets/logo_uny_cv_gui.png).
    """
    if caminho:
        return pathlib.Path(caminho)
    # Respeita monkeypatch direto no módulo em tempo de teste
    if CAMINHO_LOGO_GUI != CAMINHO_LOGO_GUI_PADRAO:
        return pathlib.Path(CAMINHO_LOGO_GUI)
    empresa = obter_config_empresa(config)
    logo_gui_cfg = empresa.get("logo_gui")
    if logo_gui_cfg:
        p = pathlib.Path(logo_gui_gui := logo_gui_cfg)
        if not p.is_absolute():
            p = BASE_DIR / p
        if p.exists():
            return p
    candidato_empresa_gui = _ASSETS_DIR / "logo_empresa_gui.png"
    if candidato_empresa_gui.exists():
        return candidato_empresa_gui
    return CAMINHO_LOGO_GUI_PADRAO


def obter_caminho_icone(config=None):
    """Localiza o arquivo de ícone (.ico) para a janela e atalhos."""
    empresa = obter_config_empresa(config)
    icone_cfg = empresa.get("icone")
    if icone_cfg:
        p = pathlib.Path(icone_cfg)
        if not p.is_absolute():
            p = BASE_DIR / p
        if p.exists():
            return p
    candidato_empresa_ico = _ASSETS_DIR / "icone.ico"
    if candidato_empresa_ico.exists():
        return candidato_empresa_ico
    return CAMINHO_ICONE_PADRAO


def titulo_janela(titulo_base, config=None):
    """
    Monta o título padrão das janelas do sistema:
    Ex: 'Gerador de Etiquetas - Uny CV' ou 'Gerador de Etiquetas - Minha Empresa'
    """
    nome = obter_nome_empresa(config)
    return f"{titulo_base} - {nome}" if nome else titulo_base


def obter_texto_rodape(config=None):
    """Texto impresso no rodapé de documentos (como no romaneio de retirada)."""
    empresa = obter_config_empresa(config)
    rodape = empresa.get("rodape_retirada")
    if rodape and str(rodape).strip():
        return str(rodape).strip()
    nome = obter_nome_empresa(config)
    if nome and nome != "Comunicação Visual":
        return f"{nome} · Conferir os materiais e preencher na retirada"
    return "Conferir os materiais e preencher na retirada"


def logo_disponivel(caminho=None, config=None):
    """Informa se o arquivo de logo existe em disco."""
    return obter_caminho_logo(caminho=caminho, config=config).exists()


def inserir_logo(pagina, rect, alinhamento="left", caminho=None, xref=None, config=None):
    """
    Insere o logotipo da empresa dentro de 'rect', mantendo a proporção
    original da imagem (nunca distorce) e centralizado verticalmente
    dentro do espaço disponível.

    'alinhamento' controla onde a imagem fica dentro de 'rect' quando a
    proporção do logo não preenche o espaço todo: "left", "right" ou "center".

    'caminho' permite forçar um arquivo específico. Se omitido, busca o logo
    configurado para a empresa ou o padrão do sistema.

    'xref' reaproveita uma imagem JÁ embutida neste mesmo PDF, economizando
    bytes em relatórios de muitas páginas.

    Não faz nada se o arquivo do logo não existir.
    """
    caminho_logo = obter_caminho_logo(caminho=caminho, config=config)
    if not caminho_logo.exists():
        return None

    try:
        from PIL import Image
        with Image.open(str(caminho_logo)) as im:
            largura_px, altura_px = im.size
    except Exception:
        try:
            import pymupdf
            pix = pymupdf.Pixmap(str(caminho_logo))
            largura_px, altura_px = pix.width, pix.height
        except Exception:
            return None

    if altura_px == 0:
        return None

    proporcao = largura_px / altura_px

    largura_disponivel = getattr(rect, "width", 0.0)
    altura_disponivel = getattr(rect, "height", 0.0)

    if altura_disponivel <= 0 or largura_disponivel <= 0:
        return None

    if largura_disponivel / altura_disponivel > proporcao:
        altura_final = altura_disponivel
        largura_final = altura_final * proporcao
    else:
        largura_final = largura_disponivel
        altura_final = largura_final / proporcao

    rx0 = getattr(rect, "x0", 0.0)
    rx1 = getattr(rect, "x1", largura_disponivel)
    ry0 = getattr(rect, "y0", 0.0)

    if alinhamento == "right":
        x0 = rx1 - largura_final
    elif alinhamento == "center":
        x0 = rx0 + (largura_disponivel - largura_final) / 2
    else:
        x0 = rx0

    y0 = ry0 + (altura_disponivel - altura_final) / 2

    # Suporte nativo para RelatorioA4Builder / motor_pdf
    if hasattr(pagina, "desenhar_imagem"):
        with open(str(caminho_logo), "rb") as f:
            dados = f.read()
        return pagina.desenhar_imagem(x0, y0, largura_final, altura_final, dados)

    try:
        import pymupdf
        rect_final = pymupdf.Rect(x0, y0, x0 + largura_final, y0 + altura_final)
        if xref:
            return pagina.insert_image(rect_final, xref=xref)
        return pagina.insert_image(rect_final, filename=str(caminho_logo))
    except Exception:
        return None


def salvar_identidade(nome=None, slogan=None, logo=None, logo_gui=None, icone=None,
                      rodape_retirada=None, config=None):
    """
    Atualiza as configurações de branding no config.json e retorna o config atualizado.
    """
    from config import carregar_config, atualizar_empresa
    cfg = config if isinstance(config, dict) else carregar_config()
    return atualizar_empresa(
        cfg,
        nome=nome,
        slogan=slogan,
        logo=logo,
        logo_gui=logo_gui,
        icone=icone,
        rodape_retirada=rodape_retirada
    )
