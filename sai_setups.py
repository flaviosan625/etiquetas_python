"""
Os setups do SAi Production Manager, lidos do PMSetups.ini.

POR QUE LER, EM VEZ DE ESCREVER O CAMINHO DE CABEÇA
O SAi corta o nome da pasta em 12 letras. O setup
`XLF_HS_NET_EPS3200UV_LM` virou a pasta `XLF_HS_NET_E` — descoberto em
07/09/2026, depois de procurar uma pasta que "devia" existir. Quem monta
o caminho a partir do nome do setup acerta por sorte, e erra CALADO:
entrega o arquivo numa pasta que o Production Manager não vigia, o vigia
diz "enviado", e a máquina nunca recebe nada.

O arquivo é texto puro, quatro linhas por setup:

    Device:Docan-Docan
    Hotfolder:...\\Jobs and Settings\\Jobs\\Docan\\Docan
    PresetFolder:...\\Devices\\Docan\\Presets
    ICCFolder:Docan

SÓ LEITURA. Nada aqui escreve no SAi: o setup nasce na tela do
Production Manager, na mão, e o `xkeda / XLF_HS_NET_EPS3200UV_LM` é de
OUTRA máquina e não se toca (ordem do usuário, 07/09/2026).
"""
import pathlib

CAMINHO_PMSETUPS = pathlib.Path(
    r"C:\Program Files\SAi\SAi Production Suite 22\Jobs and Settings\PMSetups.ini")

# O nome da chave no .ini e o nome que usamos aqui.
_CAMPOS = {
    "Device": "device",
    "Hotfolder": "hot_folder",
    "PresetFolder": "presets",
    "ICCFolder": "icc",
}


def ler(caminho=None):
    """
    Os setups do Production Manager, na ordem em que aparecem.

    Devolve [] quando o arquivo não existe — este módulo roda em PC que
    pode não ter o SAi instalado, e não achar o arquivo é ausência, não
    defeito.
    """
    caminho = pathlib.Path(caminho or CAMINHO_PMSETUPS)
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # O SAi grava em ANSI; caminho com acento chega aqui como latin-1.
        texto = caminho.read_text(encoding="latin-1")
    except OSError:
        return []

    setups = []
    atual = None
    for linha in texto.splitlines():
        chave, _, valor = linha.partition(":")
        campo = _CAMPOS.get(chave.strip())
        if campo is None:
            continue
        if campo == "device":
            atual = {"device": valor.strip()}
            setups.append(atual)
        elif atual is not None:
            # 'Hotfolder:C:\...' — o partition acima cortou no primeiro
            # ':', que é o do rótulo; a letra do drive vem inteira no valor.
            atual[campo] = valor.strip()
    return setups


def hot_folder_de(device, caminho=None):
    """A hot folder de um setup pelo nome do Device, ou None se não houver."""
    for setup in ler(caminho):
        if setup["device"].casefold() == device.casefold():
            return setup.get("hot_folder")
    return None


def conferir_maquinas(maquinas, caminho=None):
    """
    Confere as hot folders cadastradas contra o que o SAi diz.

    Devolve a lista de divergências, cada uma {'maquina', 'cadastrada',
    'no_sai'} — 'no_sai' é None quando nenhum setup aponta pra essa
    pasta. Máquina que não é do SAi (as Mimaki) não entra na conferência:
    a hot folder delas é do RasterLink7 e não está neste arquivo.

    Existe pro caso do nome cortado em 12 letras aparecer de novo, e pro
    dia em que alguém refizer o setup e a pasta mudar de lugar sem
    ninguém avisar o sistema.
    """
    setups = ler(caminho)
    if not setups:
        return []

    pastas_do_sai = {
        (s.get("hot_folder") or "").casefold(): s["device"]
        for s in setups if s.get("hot_folder")
    }

    divergencias = []
    for nome, config in maquinas.items():
        cadastrada = config.get("hot_folder") if isinstance(config, dict) else config
        if not cadastrada or "SAi" not in str(cadastrada):
            continue
        if str(cadastrada).casefold() not in pastas_do_sai:
            divergencias.append({
                "maquina": nome,
                "cadastrada": str(cadastrada),
                "no_sai": hot_folder_de(_device_provavel(nome, setups), caminho),
            })
    return divergencias


def _device_provavel(nome_maquina, setups):
    """
    O setup que mais se parece com o nome da máquina — só pra dizer, na
    divergência, qual caminho o SAi tem hoje. É palpite de mensagem, e
    nunca escolhe pasta pra entregar arquivo.
    """
    alvo = nome_maquina.casefold()
    for setup in setups:
        if setup["device"].casefold().split("-")[0] in alvo:
            return setup["device"]
    return ""
