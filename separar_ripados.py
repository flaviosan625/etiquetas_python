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
    raiz = pathlib.Path(ripados_para_nuvem.PASTA_RIPADOS)
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


def _levar_entre_discos(ripado, destino):
    """C: -> D:. Devolve o motivo do erro, ou None quando o ripado saiu da origem e chegou inteiro."""
    try:
        st = ripado.stat()
        livre = shutil.disk_usage(destino.parent).free
    except OSError as e:
        return f"não consegui ler o espaço ({e})"
    if livre < st.st_size + MARGEM_LIVRE_BYTES:
        return (f"o D: tem {livre / 1024 ** 3:.1f} GB livres e o ripado tem "
                f"{st.st_size / 1024 ** 3:.1f} GB — não copiei pra não encher o disco")
    montagem = destino.with_name(f"~montando~{destino.name}.parcial")
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
    raiz = pathlib.Path(raiz or ripados_para_nuvem.PASTA_RIPADOS)
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
