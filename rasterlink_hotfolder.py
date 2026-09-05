"""
Ponte entre o sistema de etiquetas e o RIP RasterLink7 (Mimaki) via
hot folder — mesmo princípio do printfactory.py, mas com dois passos a
mais:

  - A hot folder de verdade do RasterLink7 é vigiada ativamente pelo
    RIP e precisa ficar 100% LOCAL na máquina do RIP (nunca dentro de
    uma pasta sincronizada — um placeholder "só na nuvem" ainda
    baixando, ou outro dispositivo com acesso à mesma pasta, pode
    fazer o RIP tentar ler um arquivo incompleto ou disparar impressão
    sem querer — decidido com o usuário, 2026-09-04).
  - Tem MAIS DE UMA impressora ligada no mesmo RasterLink7 (cada uma
    com seu próprio Favorito + hot folder local, ex: "UJV100" e
    "UJV 100 UNY CV") — por isso a fila do OneDrive é dividida por
    máquina (uma subpasta por nome), pra saber pra qual impressora
    cada arquivo vai (pedido do usuário, 2026-09-04: "são duas
    máquinas como ele vai identificar qual fila entrar").

Fluxo, em duas pontas:
  1. Qualquer máquina chama enviar_para_fila(caminho, nome_maquina) —
     copia o arquivo pra pasta comum no OneDrive (PASTA_FILA_ONEDRIVE),
     dentro da subpasta da máquina escolhida (nome_maquina precisa
     bater com uma chave de MAQUINAS). Sincroniza sozinha pras duas
     máquinas.
  2. Só na máquina do RIP, rodando vigiar_fila(...) (loop contínuo,
     pensado pra rodar em segundo plano nessa máquina, do mesmo jeito
     que monitor_onedrive.py roda na máquina principal): a cada
     intervalo, olha CADA subpasta de MAQUINAS, espera cada arquivo
     novo ficar estável (parar de crescer — cobre tanto upload em
     andamento quanto download do OneDrive ainda em progresso) e só
     então copia pra hot folder local de verdade daquela máquina,
     movendo o original da fila pra uma subpasta "Enviados" dentro da
     subpasta da máquina (nunca apaga, só tira da fila pra não
     reenviar de novo no próximo ciclo).

MAQUINAS só tem a "UJV 100 UNY CV" preenchida até agora — adicione mais
entradas (nome do Favorito -> caminho da hot folder) conforme as outras
impressoras forem configuradas no RasterLink7.
"""
import datetime
import pathlib
import shutil
import time

# Pasta comum dentro do OneDrive — existe em qualquer máquina que
# tenha o OneDrive dessa conta sincronizado, por isso usa Path.home()
# em vez de um caminho fixo com o nome do usuário (mesma convenção já
# usada em rasterlink.py/RAIZ_BUSCA_OUTROS_CLIENTES).
PASTA_FILA_ONEDRIVE = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO" / "Fila de Impressao RasterLink"
NOME_SUBPASTA_ENVIADOS = "Enviados"

# {nome do Favorito no RasterLink7: caminho da hot folder local dessa
# impressora, NESSA máquina}. O nome tem que ser IDÊNTICO ao nome da
# subpasta que enviar_para_fila cria dentro da fila do OneDrive.
MAQUINAS = {
    "UJV 100 UNY CV": r"C:\MijCtrl\Hot\UJV 100 UNY CV",
    "SWJ320A": r"C:\MijCtrl\Hot\SWJ320A",
}

# Extensões que o RasterLink7 aceita como arte de impressão — mesma
# lista de formatos suportados pelo resto do projeto (ver
# processamento.py), pra nunca empurrar um .txt/.zip de referência
# pra dentro da hot folder do RIP sem querer.
_EXTENSOES_ACEITAS = (".pdf", ".ai", ".png", ".jpg", ".jpeg", ".eps", ".tif", ".tiff")


def enviar_para_fila(caminho_arquivo, nome_maquina, pasta_fila=None, maquinas=None):
    """
    Copia 'caminho_arquivo' pra fila comum no OneDrive, na subpasta da
    máquina 'nome_maquina' — chamável de qualquer máquina (não precisa
    ser a do RIP). NUNCA move: o original do pedido continua intacto
    onde estava.
    """
    maquinas = MAQUINAS if maquinas is None else maquinas
    if nome_maquina not in maquinas:
        raise ValueError(
            f"Máquina '{nome_maquina}' não reconhecida — máquinas configuradas: "
            f"{', '.join(maquinas) if maquinas else '(nenhuma)'}"
        )

    pasta = pathlib.Path(pasta_fila or PASTA_FILA_ONEDRIVE) / nome_maquina
    pasta.mkdir(parents=True, exist_ok=True)

    origem = pathlib.Path(caminho_arquivo)
    if not origem.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {origem}")

    destino = pasta / origem.name
    shutil.copy2(origem, destino)
    return destino


def _arquivo_estavel(caminho, espera_segundos=3):
    """
    Confere se 'caminho' parou de crescer nos últimos 'espera_segundos'
    — cobre tanto um upload/copy ainda em andamento quanto um
    placeholder do OneDrive ainda sendo baixado. Só depois disso é
    seguro copiar pra hot folder do RIP sem risco de mandar arquivo
    incompleto/corrompido pra impressão.
    """
    try:
        tamanho_antes = caminho.stat().st_size
    except OSError:
        return False
    time.sleep(espera_segundos)
    try:
        tamanho_depois = caminho.stat().st_size
    except OSError:
        return False
    return tamanho_antes == tamanho_depois


def _vigiar_uma_maquina(pasta_maquina, hot_folder_str, logger):
    """Um ciclo, só pra UMA máquina/hot folder — ver vigiar_fila_uma_vez."""
    hot_folder = pathlib.Path(hot_folder_str)
    if not hot_folder.is_dir():
        raise FileNotFoundError(f"Hot folder do RasterLink7 não encontrada: {hot_folder}")

    if not pasta_maquina.is_dir():
        return {"enviados": [], "ignorados": []}

    pasta_enviados = pasta_maquina / NOME_SUBPASTA_ENVIADOS
    pasta_enviados.mkdir(parents=True, exist_ok=True)

    resultado = {"enviados": [], "ignorados": []}
    for arquivo in [f for f in pasta_maquina.iterdir() if f.is_file()]:
        if arquivo.suffix.lower() not in _EXTENSOES_ACEITAS:
            resultado["ignorados"].append(arquivo.name)
            continue
        if not _arquivo_estavel(arquivo):
            logger("info", f"'{arquivo.name}' ainda mudando de tamanho (upload/download em andamento) — aguardando próximo ciclo.")
            continue

        destino_hot_folder = hot_folder / arquivo.name
        shutil.copy2(arquivo, destino_hot_folder)

        destino_enviados = pasta_enviados / arquivo.name
        if destino_enviados.exists():
            destino_enviados = pasta_enviados / f"{arquivo.stem}_{int(time.time())}{arquivo.suffix}"
        arquivo.rename(destino_enviados)

        logger("ok", f"'{arquivo.name}' enviado pra hot folder do RasterLink7 ({pasta_maquina.name}).")
        resultado["enviados"].append(arquivo.name)

    return resultado


def vigiar_fila_uma_vez(pasta_fila=None, maquinas=None, logger=print):
    """
    Um ciclo só: pra cada máquina configurada, olha a subpasta dela
    dentro da fila, manda pra hot folder local o que já estiver
    estável, e move da fila pra 'Enviados' (dentro da subpasta da
    máquina). Separado de vigiar_fila (loop contínuo) pra dar pra
    chamar isoladamente em teste, ou de um agendador externo
    (Agendador de Tarefas do Windows) em vez de um processo eternamente
    rodando.

    Devolve {nome_maquina: {"enviados": [...], "ignorados": [...]}}.
    """
    maquinas = MAQUINAS if maquinas is None else maquinas
    if not maquinas:
        raise RuntimeError(
            "Nenhuma máquina configurada ainda — preencha o dicionário "
            "MAQUINAS em rasterlink_hotfolder.py com {nome do favorito: "
            "caminho da hot folder} depois de criar o Favorito + Hot "
            "Folder no RasterLink7."
        )

    pasta_raiz = pathlib.Path(pasta_fila or PASTA_FILA_ONEDRIVE)

    resultado_por_maquina = {}
    for nome_maquina, hot_folder_str in maquinas.items():
        pasta_maquina = pasta_raiz / nome_maquina
        resultado_por_maquina[nome_maquina] = _vigiar_uma_maquina(pasta_maquina, hot_folder_str, logger)

    if pasta_raiz.is_dir():
        for item in pasta_raiz.iterdir():
            if item.is_dir() and item.name not in maquinas:
                logger(
                    "warn",
                    f"Pasta '{item.name}' dentro da fila não corresponde a nenhuma máquina "
                    f"configurada em MAQUINAS — ignorada (confira o nome).",
                )

    return resultado_por_maquina


def vigiar_fila(pasta_fila=None, maquinas=None, intervalo_segundos=15, logger=print):
    """
    Loop contínuo — pensado pra rodar em segundo plano SÓ na máquina
    do RIP (nunca nas outras, que só usam enviar_para_fila). Nunca
    para sozinho por causa de um erro num ciclo — registra e segue
    tentando no próximo, do mesmo jeito que monitor_onedrive.py nunca
    deixa um erro de organização derrubar o monitor inteiro.
    """
    nomes = ", ".join(maquinas if maquinas is not None else MAQUINAS) or "(nenhuma)"
    logger("info", f"Vigiando fila do RasterLink7 em: {pasta_fila or PASTA_FILA_ONEDRIVE} (máquinas: {nomes})")
    while True:
        try:
            vigiar_fila_uma_vez(pasta_fila, maquinas, logger)
        except Exception as e:
            logger("err", f"Erro inesperado no ciclo da fila do RasterLink7: {e}")
        time.sleep(intervalo_segundos)


# Caminho do log de arquivo — usado quando roda sem console (pythonw,
# atalho na inicialização do Windows). Fica do lado do script, não da
# pasta de onde é chamado, pra sempre ir pro mesmo lugar independente
# de onde o atalho aponta.
CAMINHO_LOG = pathlib.Path(__file__).resolve().parent / "rasterlink_hotfolder.log"


def logger_arquivo(nivel, mensagem, caminho_log=None):
    """
    Logger padrão pra rodar sem console (pythonw.exe/.pyw — sem isso,
    'print()' sozinho quebra: sys.stdout é None, não só fechado, sem
    console pra escrever). Tenta imprimir também (não faz mal nenhum
    quando tem console de verdade, ex: rodando 'py rasterlink_hotfolder.
    py' na mão pra testar) mas nunca deixa a falta de console derrubar
    o vigia — só grava no arquivo de log nesse caso.
    """
    linha = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} [{nivel}] {mensagem}"
    try:
        print(linha)
    except Exception:
        pass
    try:
        with open(caminho_log or CAMINHO_LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    # Diagnóstico bruto (2026-09-04), caminho fixo, sem depender de
    # __file__/pathlib pra nada — só pra confirmar se o processo
    # chegou até aqui de verdade quando rodado via pythonw.exe.
    try:
        with open(r"C:\RasterLink\diagnostico_inicio.txt", "a", encoding="utf-8") as _f:
            _f.write(f"iniciado em {datetime.datetime.now()}\n")
    except Exception:
        pass

    try:
        vigiar_fila(logger=logger_arquivo)
    except BaseException:
        # Rede de segurança de diagnóstico (2026-09-04): sem console
        # (pythonw.exe/.pyw), um erro bem no início — antes até do
        # primeiro logger_arquivo(...) conseguir rodar — desaparecia
        # sem deixar rastro nenhum, nem no log normal. Isso aqui grava
        # o traceback completo, não importa em qual ponto quebrou.
        import traceback
        try:
            caminho_crash = pathlib.Path(__file__).resolve().parent / "rasterlink_hotfolder_crash.log"
            with open(caminho_crash, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n{traceback.format_exc()}\n")
        except Exception:
            pass
