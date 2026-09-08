"""
Leva o arquivo já ripado da DOCAN pro OneDrive, pra máquina do outro
lado baixar e imprimir.

É a SEGUNDA perna do caminho da DOCAN. A primeira (fila -> vigia -> hot
folder do SAi) é do rasterlink_hotfolder.py; daí o SAi ripa e cospe um
.prt na pasta de saída. Este módulo pega esse .prt e o entrega na nuvem.

Três coisas que este arquivo existe pra acertar, todas medidas na
prática em 2026-09-07/08:

  1. **O tamanho do .prt não tem nada a ver com o do PDF.** Ele
     acompanha a ÁREA impressa e a resolução:

         lona 3,90x0,95m     PDF 219,6 MB  ->  .prt  1,5 GB
         vinil 1,00x1,37m    PDF      —    ->  .prt  0,5 GB
         prancha técnica     PDF 582 KB    ->  .prt 13,8 GB

     O menor PDF virou de longe o maior .prt. Qualquer regra baseada no
     peso do arquivo de origem seria mentira.

  2. **Ele é escrito DEVAGAR e por muito tempo.** O de 13,8 GB cresceu
     por mais de dez minutos, a uns 107 MB/s. Copiar no meio disso
     mandaria meia arte pra máquina — e do outro lado ninguém tem como
     saber que veio pela metade. Por isso nada sai daqui sem passar pelo
     _arquivo_estavel.

  3. **A entrega é um rename, não uma cópia.** As duas pastas moram no
     mesmo volume, então os.replace é instantâneo e atômico: o arquivo
     aparece inteiro na pasta sincronizada ou não aparece. Copiar 14 GB
     pra dentro de uma pasta do OneDrive faria ele começar a subir um
     arquivo pela metade.

O teto de 20 GB é decisão do usuário (2026-09-08): "a intenção é subir
pelo menos vinte gigas de uma vez (...) sempre vai existir uma fila pra
subir, quatro, cinco arquivos, então não sabemos o tamanho certo, melhor
deixar um limite de até vinte gigas". Arquivo maior que isso NÃO é
apagado nem escondido — fica onde está e vira aviso, porque quem decide
o que fazer com ele é uma pessoa.
"""
import datetime
import os
import pathlib
import time

# Onde o SAi larga o ripado nesta máquina, e pra onde ele vai. O nome da
# pasta de destino é o mesmo que está escrito no COMO LIGAR NA MAQUINA
# DA DOCAN.txt que fica lá dentro — se mudar aqui, muda lá também.
PASTA_RIPADOS = pathlib.Path.home() / "Desktop" / "Ripados"
PASTA_NUVEM = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO" / "RIP DOCAN" / "Para imprimir"

EXTENSAO_RIPADO = ".prt"

# Teto por arquivo. Não é palpite técnico: é o número que o usuário deu
# depois de ver o de 13,8 GB passar (2026-09-08).
LIMITE_BYTES = 20 * 1024 ** 3

# Quanto tempo o arquivo precisa ficar do mesmo tamanho pra ser
# considerado pronto. Mais folgado que os 3s do vigia da fila de
# propósito: lá o que se espera é uma cópia terminando; aqui é um RIP
# ESCREVENDO, que tem pausas próprias entre blocos. Três segundos de
# quietude no meio de um RIP de dez minutos é coisa que acontece.
ESPERA_ESTAVEL_SEGUNDOS = 20


def _tamanho_legivel(bytes_):
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024 or unidade == "TB":
            return f"{bytes_:.1f} {unidade}".replace(".", ",")
        bytes_ /= 1024


def _arquivo_estavel(caminho, espera_segundos=None):
    """
    O arquivo parou de crescer? Mesma ideia do vigia da fila, com espera
    maior — ver ESPERA_ESTAVEL_SEGUNDOS.

    Devolve False em qualquer erro de leitura: não saber é motivo pra
    deixar quieto, nunca pra mandar assim mesmo.
    """
    espera = ESPERA_ESTAVEL_SEGUNDOS if espera_segundos is None else espera_segundos
    try:
        antes = caminho.stat().st_size
    except OSError:
        return False
    time.sleep(espera)
    try:
        return caminho.stat().st_size == antes
    except OSError:
        return False


def listar(pasta_ripados=None):
    """
    O que tem pra levar, do mais antigo pro mais novo. Só olha nome e
    tamanho — não abre arquivo nenhum.

    A ordem importa: com quatro ou cinco na fila, quem ripou primeiro é
    quem está esperando há mais tempo do outro lado.
    """
    pasta = pathlib.Path(pasta_ripados or PASTA_RIPADOS)
    if not pasta.is_dir():
        return []
    ripados = [f for f in pasta.iterdir()
               if f.is_file() and f.suffix.lower() == EXTENSAO_RIPADO]
    return sorted(ripados, key=lambda f: f.stat().st_mtime)


def conferir(caminho, limite_bytes=None):
    """
    Pode ir? Devolve (pode, motivo). 'motivo' é None quando pode.

    Não escreve nem move nada — dá pra chamar de uma tela pra mostrar a
    situação antes de mexer.
    """
    limite = LIMITE_BYTES if limite_bytes is None else limite_bytes
    try:
        tamanho = caminho.stat().st_size
    except OSError as e:
        return False, f"Não consegui ler o arquivo: {e}"

    if tamanho == 0:
        return False, "Está com 0 byte — RIP que não chegou a escrever nada."

    if tamanho > limite:
        return False, (
            f"Tem {_tamanho_legivel(tamanho)} e o limite combinado é "
            f"{_tamanho_legivel(limite)}. Ficou parado aqui de propósito: "
            f"o que fazer com um trabalho desse tamanho é decisão sua."
        )

    return True, None


def levar(caminho, pasta_nuvem=None, limite_bytes=None, logger=None, esperar_estavel=True):
    """
    Entrega UM ripado na pasta do OneDrive. Devolve (destino, None) ou
    (None, motivo).

    A ordem é sempre esta, e não inverte: confere -> espera parar de
    crescer -> confere de novo -> move. A segunda conferência não é
    exagero: o arquivo pode ter passado do limite justamente durante a
    espera, que é quando ele está sendo escrito.
    """
    caminho = pathlib.Path(caminho)
    destino_pasta = pathlib.Path(pasta_nuvem or PASTA_NUVEM)

    pode, motivo = conferir(caminho, limite_bytes)
    if not pode:
        return None, motivo

    if esperar_estavel and not _arquivo_estavel(caminho):
        return None, "Ainda está sendo escrito pelo RIP — fica pro próximo ciclo."

    # De novo, agora que ele parou: durante a espera ele cresceu.
    pode, motivo = conferir(caminho, limite_bytes)
    if not pode:
        return None, motivo

    try:
        destino_pasta.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return None, f"Não consegui abrir a pasta do OneDrive: {e}"

    destino = destino_pasta / caminho.name
    if destino.exists():
        return None, (
            f"Já existe um '{caminho.name}' esperando na nuvem. "
            f"Sobrescrever poderia trocar um trabalho por outro no meio da subida."
        )

    try:
        # Rename, não cópia: mesmo volume, então é instantâneo e atômico.
        # O OneDrive nunca vê um arquivo pela metade com o nome final.
        os.replace(caminho, destino)
    except OSError as e:
        # Volumes diferentes (o Desktop redirecionado, um pendrive) caem
        # aqui. Não tenta copiar por conta própria: uma cópia de 14 GB
        # pra dentro de pasta sincronizada é exatamente o que o rename
        # existe pra evitar.
        return None, (
            f"Não consegui mover pra nuvem ({e}). Se as duas pastas não estão no mesmo "
            f"disco, o movimento deixa de ser atômico e precisa ser resolvido antes."
        )

    if logger:
        logger("ok", f"'{caminho.name}' ({_tamanho_legivel(destino.stat().st_size)}) entregue na nuvem.")
    return destino, None


def levar_todos(pasta_ripados=None, pasta_nuvem=None, limite_bytes=None, logger=None,
                esperar_estavel=True):
    """
    Uma passada na pasta inteira. Devolve
    {"levados": [destino], "esperando": [(caminho, motivo)]}.

    UM arquivo com problema não pode prender os outros atrás dele —
    mesma regra do vigia da fila, e pelo mesmo motivo real: um travado no
    começo já deixou cinco parados pra sempre porque todo ciclo novo
    recomeçava por ele.
    """
    resultado = {"levados": [], "esperando": []}
    for caminho in listar(pasta_ripados):
        destino, motivo = levar(
            caminho, pasta_nuvem=pasta_nuvem, limite_bytes=limite_bytes,
            logger=logger, esperar_estavel=esperar_estavel,
        )
        if destino is None:
            resultado["esperando"].append((caminho, motivo))
            if logger:
                logger("info", f"'{caminho.name}': {motivo}")
        else:
            resultado["levados"].append(destino)
    return resultado


def resumo(resultado, agora=None):
    """Uma linha por coisa que aconteceu, pra quem rodou na mão ver alguma resposta."""
    agora = agora or datetime.datetime.now()
    linhas = [f"Passada concluída às {agora:%H:%M:%S}."]
    for destino in resultado["levados"]:
        linhas.append(f"  levado   {destino.name}")
    for caminho, motivo in resultado["esperando"]:
        linhas.append(f"  esperando {caminho.name} — {motivo}")
    if not resultado["levados"] and not resultado["esperando"]:
        linhas.append("  (nada pra levar)")
    return linhas


if __name__ == "__main__":
    for linha in resumo(levar_todos(logger=lambda nivel, msg: None)):
        print(linha)
