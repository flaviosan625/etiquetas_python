"""
Separa os ripados das duas DOCAN, cada um na pasta da sua máquina no D:.

POR QUE ISTO EXISTE
Desenho do usuário (24/09/2026): "FILA\\DOCAN H2525 entrada, D:\\RIPADOS\\
DOCAN H2525 saída", e o da R5200 na dela. Só que no SAi a porta de saída é
do DISPOSITIVO, não da configuração: as duas DOCAN são configurações do
mesmo dispositivo `Docan Docan@FILE:`, e trocar a "Localização padrão" de
uma trocou a das duas (conferido no SETTINGS.PRF às 06:58). O SAi, sozinho,
não consegue mandar cada DOCAN pra uma pasta. Quem separa é isto aqui.

A PROVA DE QUEM GEROU CADA RIPADO
O RIPLOG.HTML do SAi grava um bloco "Iniciar a impressão" por saída, com
"Nome do dispositivo" (Docan / Docan_H2525), o nome do trabalho e a "Data
e Hora de Término da Saída" — que bate com a hora do .prt no disco em
menos de 1 s (TOTEM BASE: 07:01:46 nos dois). Um ripado só muda de pasta
com TRÊS coisas: mesmo nome de trabalho, término a até FOLGA_SEGUNDOS da
hora do arquivo, e o arquivo parado há pelo menos PARADO_HA_SEGUNDOS.

A terceira não é enfeite. O SAi grava o .prt já com o nome final, e
durante a gravação a hora do arquivo acompanha o relógio. Sem ela, um
arquivo ainda crescendo herdaria a "prova" de uma saída ANTERIOR com o
mesmo nome — a revisão de 24/09 mostrou isso no log real (ACAUTELAMENTO
saiu às 00:35:35 e de novo às 00:36:46) e reproduziu um ripado truncado
sendo "levado". Com a folga de 3 s e o arquivo parado há 30 s, isso não
acontece.

Sem prova, fica onde está e vira aviso: ripado de plana mandado pra máquina
de rolo é chapa perdida, e número deduzido não se passa por declarado.

NUNCA PERDE ARQUIVO
- Nunca sobrescreve: a entrada final é os.rename, que no Windows FALHA se o
  destino existir, e o nome livre é procurado até achar.
- Cópia só entre discos DIFERENTES (erro 17). Qualquer outra falha do
  rename — arquivo aberto por alguém, por exemplo — é "em uso" e espera.
- "Copiei mas a origem não saiu" não é sucesso: a cópia é desfeita. Sem
  isso, cada passada fazia uma cópia inteira nova até encher o D:.
- Confere espaço livre antes de copiar, e confere que a origem não mudou
  durante a cópia.

ONDE PROCURA
Nas pastas das máquinas (a porta pode voltar pra qualquer uma, e trocar
uma troca as duas), na raiz de D:\\RIPADOS e em Desktop\\Ripados — porque
cada trabalho guarda o destino da hora em que ENTROU no SAi: um trabalho
antigo reenviado às 06:36 de 24/09 ainda gravou 3,2 GB no C:. O .prn do
setup XLF (a Epson de OUTRA máquina, que também grava em Desktop\\Ripados)
nunca é tocado: só .prt, e só de dispositivo DOCAN.
"""
import datetime
import errno
import html
import os
import pathlib
import re
import shutil

import ripados_para_nuvem

CAMINHO_RIPLOG = pathlib.Path(
    r"C:\Program Files\SAi\SAi Production Suite 22\Jobs and Settings\RIPLOG.HTML")

# Onde o SAi gravava ANTES de 24/09/2026 00:45 — e onde trabalho antigo
# reenviado ainda grava. Constante de módulo pra teste conseguir desviar.
PASTA_RIPADOS_ANTIGA = pathlib.Path.home() / "Desktop" / "Ripados"

# Medido no log real: hora do .prt e "Término da Saída" batem em menos de 1 s.
FOLGA_SEGUNDOS = 3
# Arquivo terminado tem a hora parada; arquivo sendo gravado acompanha o relógio.
PARADO_HA_SEGUNDOS = 30
# Folga de disco além do tamanho do próprio ripado, pra não encher o D:
# e derrubar a porta do SAi ("Não foi possível abrir a porta").
MARGEM_LIVRE_BYTES = 2 * 1024 ** 3
# Montagem de cópia interrompida (queda de energia, tarefa morta no meio)
MONTAGEM_VELHA_HORAS = 1

_ERRO_OUTRO_DISCO = 17  # ERROR_NOT_SAME_DEVICE
_BLOCO = re.compile(r"<TABLE\b(.*?)</TABLE>", re.S | re.I)
_CAMPO = re.compile(r"<TH[^>]*>(.*?)</TH>\s*<TD[^>]*>(.*?)</TD>", re.S | re.I)


def _limpo(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").strip()


def _chave(caminho):
    """Identidade física do caminho: junção e maiúscula não enganam."""
    return os.path.normcase(os.path.realpath(caminho))


def maquina_do_dispositivo(maquinas=None):
    """{nome do dispositivo no RIPLOG: nome da máquina no sistema}, pelo campo 'setup_sai'."""
    if maquinas is None:
        # tardio: rasterlink_hotfolder chama este módulo, e o import no topo
        # viraria circular no dia em que alguém o mover pra lá
        from rasterlink_hotfolder import MAQUINAS as maquinas
    return {cfg["setup_sai"]: nome for nome, cfg in maquinas.items()
            if isinstance(cfg, dict) and cfg.get("setup_sai")}


def pastas_onde_o_sai_grava(maquinas=None):
    """Onde o SAi grava ou já gravou ripado de DOCAN. Lido na hora do uso."""
    raiz = ripados_para_nuvem.raiz_dos_ripados()
    pastas = [raiz / nome for nome in maquina_do_dispositivo(maquinas).values()]
    return pastas + [raiz, pathlib.Path(PASTA_RIPADOS_ANTIGA)]


def saidas_do_riplog(caminho=None):
    """
    Cada saída gravada pelo SAi: [{dispositivo, trabalho, fim}], na ordem do log.
    'trabalho' é o nome do arquivo de origem sem extensão (é o nome do .prt).
    Log ausente ou ilegível devolve [] — sem log não há prova, e nada se mexe.
    """
    caminho = pathlib.Path(caminho or CAMINHO_RIPLOG)
    try:
        texto = caminho.read_bytes().decode("utf-8", "replace")
    except OSError:
        return []
    saidas = []
    for bloco in _BLOCO.findall(texto):
        if "Iniciar a impress" not in bloco:
            continue
        campos = {}
        for k, v in _CAMPO.findall(bloco):
            # o 1o rótulo vem grudado no título do bloco: fica a última linha
            rotulo = _limpo(k).rsplit("\n", 1)[-1].strip().rstrip(":").strip()
            campos[rotulo] = _limpo(v)
        dispositivo = campos.get("Nome do dispositivo")
        arquivo = campos.get("Arquivo")
        fim = campos.get("Data e Hora de Término da Saída")
        if not (dispositivo and arquivo and fim):
            continue
        try:
            fim = datetime.datetime.strptime(fim, "%H:%M:%S %d/%m/%Y")
        except ValueError:
            continue
        nome = arquivo.replace("/", "\\").rsplit("\\", 1)[-1]
        saidas.append({"dispositivo": dispositivo, "trabalho": pathlib.PurePath(nome).stem, "fim": fim})
    return saidas


def quem_gerou(ripado, saidas, agora=None, folga_s=None):
    """
    O dispositivo que gravou este .prt, ou None quando não há prova.

    Exige: arquivo parado há PARADO_HA_SEGUNDOS, mesmo nome de trabalho e
    término a até FOLGA_SEGUNDOS da hora do arquivo. Duas saídas de
    dispositivos DIFERENTES dentro da folga: não há como saber — None.
    """
    folga = FOLGA_SEGUNDOS if folga_s is None else folga_s
    agora = agora or datetime.datetime.now()
    try:
        hora = datetime.datetime.fromtimestamp(ripado.stat().st_mtime)
    except OSError:
        return None
    if (agora - hora).total_seconds() < PARADO_HA_SEGUNDOS:
        return None  # ainda pode estar sendo gravado
    perto = {s["dispositivo"] for s in saidas
             if s["trabalho"] == ripado.stem and abs((hora - s["fim"]).total_seconds()) <= folga}
    return perto.pop() if len(perto) == 1 else None


def _nome_livre(destino):
    """O próprio destino se estiver livre; senão _<epoch>, _<epoch>_2, ... até achar."""
    if not destino.exists():
        return destino
    epoch = int(datetime.datetime.now().timestamp())
    n = 1
    while True:
        sufixo = f"_{epoch}" if n == 1 else f"_{epoch}_{n}"
        candidato = destino.with_name(f"{destino.stem}{sufixo}{destino.suffix}")
        if not candidato.exists():
            return candidato
        n += 1


def _em_uso(caminho):
    """
    Alguém está com o arquivo aberto, de qualquer jeito? No Windows abre
    SEM compartilhamento nenhum: falha se existir qualquer outro handle,
    seja qual for o modo de quem abriu. ('r+b' só pegava quem negava
    escrita — e um escritor que compartilha passava como livre.)
    """
    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, ValueError):
        ctypes = None
    if ctypes is not None and hasattr(ctypes, "windll"):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        h = k32.CreateFileW(str(caminho), 0x80000000, 0, None, 3, 0x80, None)  # GENERIC_READ, sem share
        if h == ctypes.c_void_p(-1).value:
            return True
        k32.CloseHandle(h)
        return False
    try:
        with open(caminho, "r+b"):
            return False
    except OSError:
        return True


def _mesmo_arquivo(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _ja_esta_la(ripado, pasta_certa):
    """Cópia idêntica (nome, tamanho e hora) já na pasta certa: não copia de novo."""
    alvo = pasta_certa / ripado.name
    try:
        a, b = ripado.stat(), alvo.stat()
    except OSError:
        return False
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def _levar_entre_discos(ripado, destino, pasta_montagem=None):
    """
    C: -> D:. Devolve o motivo do erro, ou None quando o ripado saiu da origem e chegou inteiro.

    A cópia é montada ao lado do destino, a menos que `pasta_montagem` diga
    outra (tem que ser do mesmo disco do destino, pro rename final ser local).
    A entrega ao BYHX usa isso: lá o destino é uma pasta que um programa
    VIGIA, e montagem dentro dela é arquivo pela metade à vista.
    """
    try:
        st = ripado.stat()
        livre = shutil.disk_usage(destino.parent).free
    except OSError as e:
        return f"não consegui ler o espaço ({e})"
    if livre < st.st_size + MARGEM_LIVRE_BYTES:
        return (f"o D: tem {livre / 1024 ** 3:.1f} GB livres e o ripado tem "
                f"{st.st_size / 1024 ** 3:.1f} GB — não copiei pra não encher o disco")
    montagem = pathlib.Path(pasta_montagem or destino.parent) / f"~montando~{destino.name}.parcial"
    try:
        shutil.copy2(ripado, montagem)
        depois = ripado.stat()
        if montagem.stat().st_size != st.st_size or depois.st_size != st.st_size \
                or depois.st_mtime != st.st_mtime:
            raise OSError("a origem mudou durante a cópia")
        os.rename(montagem, destino)  # não sobrescreve
    except OSError as e:
        try:
            montagem.unlink()
        except OSError:
            pass
        return f"não consegui copiar ({e})"
    try:
        ripado.unlink()
    except OSError as e:
        # Origem ficou: desfaz a cópia. Contar como sucesso fazia uma cópia
        # inteira nova a cada passada, até o D: encher.
        try:
            destino.unlink()
        except OSError:
            pass
        return f"copiei mas a origem não saiu ({e}) — desfiz a cópia"
    return None


def _faxina_montagens(pastas, agora):
    limite = agora - datetime.timedelta(hours=MONTAGEM_VELHA_HORAS)
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for resto in pasta.glob("~montando~*.parcial"):
            try:
                if datetime.datetime.fromtimestamp(resto.stat().st_mtime) < limite:
                    resto.unlink()
            except OSError:
                pass


def separar(pastas=None, raiz=None, riplog=None, maquinas=None, logger=None, mover=True, agora=None):
    """
    Uma passada. Devolve {'movidos': [(de, para, máquina)], 'sem_prova': [caminho],
    'em_uso': [caminho], 'erros': [(caminho, motivo)]}. Com mover=False só diz o que faria.
    """
    agora = agora or datetime.datetime.now()
    raiz = pathlib.Path(raiz) if raiz else ripados_para_nuvem.raiz_dos_ripados()
    mapa = maquina_do_dispositivo(maquinas)
    pastas = pastas_onde_o_sai_grava(maquinas) if pastas is None else [pathlib.Path(p) for p in pastas]
    saidas = saidas_do_riplog(riplog)
    resultado = {"movidos": [], "sem_prova": [], "em_uso": [], "erros": []}
    if mover:
        _faxina_montagens([raiz / m for m in mapa.values()], agora)

    pastas_vistas, vistos = set(), set()
    for pasta in pastas:
        if not pasta.is_dir() or _chave(pasta) in pastas_vistas:
            continue
        pastas_vistas.add(_chave(pasta))
        for ripado in sorted(pasta.iterdir()):
            if not ripado.is_file() or ripado.suffix.lower() != ".prt" or _chave(ripado) in vistos:
                continue
            vistos.add(_chave(ripado))
            maquina = mapa.get(quem_gerou(ripado, saidas, agora=agora))
            if maquina is None:
                resultado["sem_prova"].append(ripado)
                continue
            pasta_certa = raiz / maquina
            if pasta_certa.is_dir() and _mesmo_arquivo(ripado.parent, pasta_certa):
                continue
            if _ja_esta_la(ripado, pasta_certa):
                continue
            if _em_uso(ripado):
                resultado["em_uso"].append(ripado)
                continue
            if not mover:
                resultado["movidos"].append((ripado, pasta_certa / ripado.name, maquina))
                continue
            pasta_certa.mkdir(parents=True, exist_ok=True)
            destino = _nome_livre(pasta_certa / ripado.name)
            try:
                os.rename(ripado, destino)  # mesmo disco: instantâneo, atômico, não sobrescreve
                erro = None
            except OSError as e:
                if getattr(e, "winerror", None) == _ERRO_OUTRO_DISCO or e.errno == errno.EXDEV:
                    erro = _levar_entre_discos(ripado, destino)
                else:
                    resultado["em_uso"].append(ripado)  # aberto por alguém: espera
                    continue
            if erro:
                resultado["erros"].append((ripado, erro))
                if logger:
                    logger("warn", f"Não consegui levar '{ripado.name}' pra {maquina}: {erro}")
                continue
            if logger:
                logger("ok", f"Ripado '{ripado.name}' levado pra pasta da {maquina} ({destino.parent}).")
            resultado["movidos"].append((ripado, destino, maquina))
    return resultado


# --- a última perna: do ripado pra hot folder do BYHX -----------------------
#
# O SAi ripa, o .prt nasce neste PC e a máquina é comandada pelo BYHX Printer
# Manager. Falta só levar o .prt até a lista de trabalhos dele — sem OneDrive
# no meio — e isso SUPÕE a Hot Folder do BYHX (aba Preference): pasta que,
# quando o .prt cai nela, entra na lista.
#
# A opção existe: está na aba Preference da janela Setting do BYHX (visto em
# captura de 27/10/2026), com "Hot Folder", "Browse..." e "Print Immediately".
# O diagnóstico de 03/10 não a achou porque só olhava arquivos de configuração,
# não o Registro. Naquela captura a Hot Folder estava DESMARCADA (o caminho
# mostrado é o valor de fábrica do programa) e a Print Immediately também:
# só crie o arquivo abaixo depois de ligar a Hot Folder numa pasta nova e vazia.
#
# O endereço dessa pasta é DESTE PC e NÃO se escreve de cabeça: quem sabe é a
# aba Preference do próprio BYHX, e endereço errado aqui erra calado (o ripado
# de 14 GB entraria numa pasta que ninguém vigia). Por isso a entrega nasce
# DESLIGADA: só existe depois que alguém grava esse arquivo, ao lado do módulo,
# com UMA linha — o caminho. Apagar o arquivo desliga.
CAMINHO_HOT_FOLDER_BYHX = pathlib.Path(__file__).resolve().parent / "hot_folder_byhx.txt"


def hot_folder_do_byhx(caminho=None):
    """
    (pasta, desde) da entrega ao BYHX, ou (None, None) quando está desligada.

    `desde` é a hora em que o arquivo de configuração foi gravado, e só vale
    ripado gravado DEPOIS dela. Sem isso, ligar a entrega levaria de uma vez
    pra lista da máquina tudo que já estava parado na pasta da DOCAN — em
    04/10/2026 eram ~198 GB de ripados de 02/10 que nunca foram impressos.
    """
    caminho = pathlib.Path(caminho or CAMINHO_HOT_FOLDER_BYHX)
    try:
        cru = caminho.read_bytes()
        desde = datetime.datetime.fromtimestamp(caminho.stat().st_mtime)
    except OSError:
        return None, None
    try:
        texto = cru.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = cru.decode("cp1252", errors="replace")  # Bloco de Notas antigo, com acento no caminho
    for linha in texto.splitlines():
        linha = linha.strip().strip('"').strip()
        if linha and not linha.startswith("#"):
            return pathlib.Path(linha), desde
    return None, None


def _mover_ripado(ripado, destino, pasta_montagem=None):
    """
    Leva o arquivo sem nunca sobrescrever. Devolve ('ok', None), ('em_uso', None)
    ou ('erro', motivo). Mesmo mecanismo do separar(): rename quando é o mesmo
    disco, cópia por montagem quando não é.
    """
    try:
        os.rename(ripado, destino)  # mesmo disco: instantâneo, atômico, não sobrescreve
        return "ok", None
    except OSError as e:
        if getattr(e, "winerror", None) != _ERRO_OUTRO_DISCO and e.errno != errno.EXDEV:
            return "em_uso", None  # aberto por alguém: espera
    erro = _levar_entre_discos(ripado, destino, pasta_montagem)
    return ("erro", erro) if erro else ("ok", None)


def entregar_ao_byhx(maquinas=None, raiz=None, riplog=None, caminho=None, logger=None,
                     mover=True, agora=None):
    """
    Uma passada. Leva cada ripado novo da DOCAN que usa o BYHX pra hot folder
    dele. Devolve {'entregues': [(de, para, máquina)], 'em_uso': [caminho],
    'erros': [(caminho, motivo)], 'sem_pasta': pasta ou None, 'conflito': pasta
    ou None}. Com mover=False só diz o que faria.

    Cinco travas, todas por perda de material:
      - desligada sem o arquivo de configuração (ver CAMINHO_HOT_FOLDER_BYHX);
      - a pasta do BYHX tem que EXISTIR, e nunca é criada — pasta criada por
        mim é pasta que o programa não vigia;
      - a pasta do BYHX NÃO pode ser uma das que o separar() varre (a raiz do
        ripado, a pasta de cada máquina ou o Desktop/Ripados antigo). Ele
        levaria o .prt de volta na passada seguinte, a cada minuto, e o
        trabalho na lista do BYHX ficaria apontando pra arquivo que sumiu
        (o BYHX referencia o .prt no lugar). Sai em 'conflito';
      - só máquina com `entrega_byhx` no cadastro. A H2525 (plana) não tem: um
        .prt de chapa na lista do BYHX do rolo é chapa perdida;
      - só .prt com a prova do RIPLOG (o mesmo quem_gerou da separação, que
        pede o arquivo parado há 30 s) e gravado depois de ligar. Estar na
        pasta da máquina não basta: sem prova o arquivo também fica lá.
    """
    agora = agora or datetime.datetime.now()
    resultado = {"entregues": [], "em_uso": [], "erros": [], "sem_pasta": None, "conflito": None}
    pasta, desde = hot_folder_do_byhx(caminho)
    if pasta is None:
        return resultado
    if not pasta.is_dir():
        resultado["sem_pasta"] = pasta
        return resultado
    if maquinas is None:
        from rasterlink_hotfolder import MAQUINAS as maquinas  # tardio: ver maquina_do_dispositivo
    dispositivos = {nome: cfg["setup_sai"] for nome, cfg in maquinas.items()
                    if isinstance(cfg, dict) and cfg.get("entrega_byhx") and cfg.get("setup_sai")}
    if not dispositivos:
        return resultado
    raiz = pathlib.Path(raiz) if raiz else ripados_para_nuvem.raiz_dos_ripados()
    varridas = [raiz, pathlib.Path(PASTA_RIPADOS_ANTIGA)] + [raiz / n for n in maquina_do_dispositivo(maquinas).values()]
    if _chave(pasta) in {_chave(p) for p in varridas}:
        resultado["conflito"] = pasta
        return resultado
    saidas = saidas_do_riplog(riplog)
    if mover:
        _faxina_montagens([pasta.parent], agora)

    for nome, dispositivo in dispositivos.items():
        origem = raiz / nome
        if not origem.is_dir():
            continue
        for ripado in sorted(origem.iterdir()):
            if not ripado.is_file() or ripado.suffix.lower() != ".prt":
                continue
            try:
                gravado = datetime.datetime.fromtimestamp(ripado.stat().st_mtime)
            except OSError:
                continue
            if gravado < desde:
                continue  # já estava aqui antes de ligar: decisão dele, não minha
            if quem_gerou(ripado, saidas, agora=agora) != dispositivo:
                continue  # sem prova, ainda gravando ou de outra DOCAN: separar() é quem avisa
            if _em_uso(ripado):
                resultado["em_uso"].append(ripado)
                continue
            destino = _nome_livre(pasta / ripado.name)
            if not mover:
                resultado["entregues"].append((ripado, destino, nome))
                continue
            situacao, erro = _mover_ripado(ripado, destino, pasta_montagem=pasta.parent)
            if situacao == "em_uso":
                resultado["em_uso"].append(ripado)
            elif situacao == "erro":
                resultado["erros"].append((ripado, erro))
                if logger:
                    logger("warn", f"Não consegui entregar '{ripado.name}' ao BYHX: {erro}")
            else:
                resultado["entregues"].append((ripado, destino, nome))
                if logger:
                    logger("ok", f"Ripado '{destino.name}' entregue na hot folder do BYHX ({pasta}).")
    return resultado
