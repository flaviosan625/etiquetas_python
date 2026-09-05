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
import json
import pathlib
import shutil
import time

# Pasta comum dentro do OneDrive — existe em qualquer máquina que
# tenha o OneDrive dessa conta sincronizado, por isso usa Path.home()
# em vez de um caminho fixo com o nome do usuário (mesma convenção já
# usada em rasterlink.py/RAIZ_BUSCA_OUTROS_CLIENTES).
PASTA_FILA_ONEDRIVE = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO" / "Fila de Impressao RasterLink"
NOME_SUBPASTA_ENVIADOS = "Enviados"

# {nome do Favorito no RasterLink7: config da impressora NESSA máquina}.
# O nome tem que ser IDÊNTICO ao nome da subpasta que enviar_para_fila
# cria dentro da fila do OneDrive.
#
# 'largura_util_m' é a largura que a máquina realmente imprime (já
# descontada a margem lateral, medida na prática pelo usuário —
# 2026-09-05), usada pra girar sozinho o arquivo que vier mais largo
# que isso. É opcional: uma máquina configurada só com o caminho da
# hot folder (string) continua funcionando, só não ganha o giro
# automático.
MAQUINAS = {
    "UJV 100 UNY CV": {"hot_folder": r"C:\MijCtrl\Hot\UJV 100 UNY CV", "largura_util_m": 1.48},
    "SWJ320A": {"hot_folder": r"C:\MijCtrl\Hot\SWJ320A", "largura_util_m": 3.20},
}

# Extensões que o RasterLink7 aceita como arte de impressão — mesma
# lista de formatos suportados pelo resto do projeto (ver
# processamento.py), pra nunca empurrar um .txt/.zip de referência
# pra dentro da hot folder do RIP sem querer.
_EXTENSOES_ACEITAS = (".pdf", ".ai", ".png", ".jpg", ".jpeg", ".eps", ".tif", ".tiff")

# Mesmo conteúdo, com nome público: a tela de envio (envio_impressao.py)
# precisa filtrar exatamente pelas mesmas extensões que o vigia aceita,
# senão ela ofereceria pra mandar um arquivo que o vigia depois ignoraria
# em silêncio dentro da fila.
EXTENSOES_ACEITAS = _EXTENSOES_ACEITAS

# Folga de 1mm na comparação de largura — ver _copiar_para_hot_folder.
_TOLERANCIA_LARGURA_M = 0.001

# Onde mora o registro permanente do que passou pelas máquinas, e mais
# tarde os PDFs diários gerados a partir dele. Fica FORA da fila de
# propósito: a fila se auto-limpa (ver DIAS_RETENCAO_ENVIADOS) e é
# pasta técnica; isto aqui é documento de comprovação, irmão da
# "Ordem de Serviço" (decidido com o usuário, 2026-09-05).
PASTA_RELATORIOS = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO" / "Relatório de Impressão Diária"
NOME_SUBPASTA_REGISTRO = "_registro"

# Por quantos dias o arquivo enviado fica guardado em "Enviados" antes
# de ser apagado. Apagar direto é seguro porque o original nunca sai da
# pasta do cliente em EVENTOS — pra fila sempre vai uma CÓPIA (regra do
# usuário, 2026-09-05). O registro do envio, esse, é permanente.
DIAS_RETENCAO_ENVIADOS = 15


def registrar_envio(maquina, arquivo, girado, pasta_relatorios=None, quando=None, logger=None):
    """
    Anota uma linha no registro permanente do mês: uma linha JSON por
    arquivo entregue à máquina. É de propósito que grave só FATO BRUTO
    (quando, qual máquina, qual arquivo, tamanho, se girou) e nenhuma
    interpretação: a máquina do RIP só tem este módulo instalado, não o
    projeto inteiro — quem lê medida/material/m² do nome do arquivo é o
    gerador de relatório, lá no PC principal, que tem config.json e
    dimensoes.py.

    Nunca levanta exceção: falha de registro não pode impedir a arte de
    chegar na impressora. Mas AVISA no log quando falha — este arquivo é
    a comprovação do que foi produzido, e falhar em silêncio significaria
    descobrir o buraco só no dia em que o documento fizesse falta.
    """
    quando = quando or datetime.datetime.now()
    destino = pathlib.Path(pasta_relatorios or PASTA_RELATORIOS) / NOME_SUBPASTA_REGISTRO
    try:
        pasta = destino
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            tamanho = arquivo.stat().st_size
        except OSError:
            tamanho = None
        linha = json.dumps({
            "quando": quando.strftime("%Y-%m-%dT%H:%M:%S"),
            "maquina": maquina,
            "arquivo": arquivo.name,
            "bytes": tamanho,
            "girado": bool(girado),
        }, ensure_ascii=False)
        with open(pasta / f"{quando:%Y-%m}.jsonl", "a", encoding="utf-8") as f:
            f.write(linha + "\n")
        return True
    except (OSError, TypeError, ValueError) as e:
        if logger:
            logger(
                "warn",
                f"NÃO consegui registrar '{arquivo.name}' no histórico de produção ({destino}): {e}. "
                f"O arquivo foi enviado pra impressão normalmente, mas não vai aparecer no relatório do dia.",
            )
        return False


def limpar_enviados_antigos(pasta_enviados, dias=None, logger=print, agora=None):
    """
    Apaga de "Enviados" o que passou do prazo de retenção. Só olha
    ARQUIVO dentro dessa pasta — nunca toca na fila em si, nem em
    subpasta. Devolve a lista de nomes apagados.
    """
    dias = DIAS_RETENCAO_ENVIADOS if dias is None else dias
    pasta_enviados = pathlib.Path(pasta_enviados)
    if not pasta_enviados.is_dir():
        return []

    agora = agora or datetime.datetime.now()
    limite = agora - datetime.timedelta(days=dias)
    apagados = []
    for arquivo in [f for f in pasta_enviados.iterdir() if f.is_file()]:
        try:
            modificado = datetime.datetime.fromtimestamp(arquivo.stat().st_mtime)
        except OSError:
            continue
        if modificado >= limite:
            continue
        try:
            arquivo.unlink()
        except OSError as e:
            logger("warn", f"Não consegui apagar '{arquivo.name}' de Enviados: {e}")
            continue
        apagados.append(arquivo.name)

    if apagados:
        logger("ok", f"{len(apagados)} arquivo(s) com mais de {dias} dias apagados de '{pasta_enviados.parent.name}/Enviados'.")
    return apagados


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


def _config_maquina(valor):
    """
    Aceita as duas formas de configurar uma máquina em MAQUINAS: só o
    caminho da hot folder (string) ou um dict com 'hot_folder' e
    'largura_util_m'. Devolve sempre (hot_folder, largura_util_m), com
    largura None quando não foi informada — nesse caso o giro
    automático simplesmente não acontece pra essa máquina.
    """
    if isinstance(valor, dict):
        return valor.get("hot_folder"), valor.get("largura_util_m")
    return valor, None


def _importar_pymupdf():
    """
    Devolve o módulo pymupdf, ou None se não estiver instalado. A
    máquina do RIP tem um Python instalado do zero só pra rodar esse
    vigia (2026-09-04) e pode não ter a biblioteca — sem ela o vigia
    perde só a análise de largura, nunca para de enviar arquivo.
    """
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        return None


def _largura_altura_m(caminho, pymupdf):
    """Tamanho físico da 1ª página do PDF em metros, ou None se não der pra ler."""
    metros_por_ponto = 0.0254 / 72
    try:
        doc = pymupdf.open(str(caminho))
        try:
            rect = doc.load_page(0).rect
        finally:
            doc.close()
    except Exception:
        return None
    return rect.width * metros_por_ponto, rect.height * metros_por_ponto


def _copiar_para_hot_folder(arquivo, destino, largura_util_m, logger):
    """
    Copia 'arquivo' pra hot folder do RIP, girando 90° quando for um
    PDF mais largo que a máquina que caberia deitado. O giro é sempre
    só na CÓPIA — o arquivo que fica guardado em 'Enviados' continua
    exatamente como chegou.

    Quando não cabe nem girado, manda assim mesmo e registra o aviso
    (escolha do usuário, 2026-09-05: prefere decidir dentro do
    RasterLink a ter arquivo represado sem ele ver).
    """
    if not largura_util_m or arquivo.suffix.lower() != ".pdf":
        shutil.copy2(arquivo, destino)
        return False

    pymupdf = _importar_pymupdf()
    if pymupdf is None:
        logger("warn", f"pymupdf não instalado nesta máquina — '{arquivo.name}' enviado sem conferir a largura.")
        shutil.copy2(arquivo, destino)
        return False

    tamanho = _largura_altura_m(arquivo, pymupdf)
    if tamanho is None:
        logger("warn", f"Não consegui ler o tamanho de '{arquivo.name}' — enviado sem conferir a largura.")
        shutil.copy2(arquivo, destino)
        return False

    largura_m, altura_m = tamanho
    # Tolerância de 1mm: uma arte fechada exatamente na largura da
    # bobina vira 3.2000000038m depois da conversão de pontos pra
    # metros, e sem folga ela seria recusada por erro de arredondamento.
    limite = largura_util_m + _TOLERANCIA_LARGURA_M
    cabe_em_pe = largura_m <= limite
    cabe_deitado = altura_m <= limite

    if not cabe_em_pe and not cabe_deitado:
        logger(
            "warn",
            f"'{arquivo.name}' tem {largura_m:.2f}x{altura_m:.2f}m e não cabe nem girado na "
            f"máquina ({largura_util_m:.2f}m úteis) — enviado assim mesmo, confira no RasterLink.",
        )
        shutil.copy2(arquivo, destino)
        return False

    # O que gasta bobina é o lado que corre no comprimento: em pé
    # gasta 'altura_m', deitado gasta 'largura_m'. Então deitar só
    # compensa quando a arte é mais alta do que larga — aí o lado
    # maior atravessa a bobina e sobra material (pedido do usuário,
    # 2026-09-05: "a ideia é reaproveitar o máximo de material").
    if not cabe_deitado or (cabe_em_pe and largura_m >= altura_m):
        shutil.copy2(arquivo, destino)
        return False

    economia_m = altura_m - largura_m

    try:
        doc = pymupdf.open(str(arquivo))
        try:
            for pagina in doc:
                pagina.set_rotation((pagina.rotation + 90) % 360)
            doc.save(str(destino))
        finally:
            doc.close()
    except Exception as e:
        logger("warn", f"Falhei ao girar '{arquivo.name}' ({e}) — enviado sem girar.")
        shutil.copy2(arquivo, destino)
        return False

    if cabe_em_pe:
        motivo = f"economiza {economia_m:.2f}m de bobina ({altura_m:.2f}m em pé contra {largura_m:.2f}m deitado)"
    else:
        motivo = f"tinha {largura_m:.2f}m de largura, mais que os {largura_util_m:.2f}m úteis da máquina"
    logger("ok", f"'{arquivo.name}' girado 90° automaticamente: {motivo}.")
    return True


def _vigiar_uma_maquina(pasta_maquina, config_maquina, logger, pasta_relatorios=None, dias_retencao=None):
    """Um ciclo, só pra UMA máquina/hot folder — ver vigiar_fila_uma_vez."""
    hot_folder_str, largura_util_m = _config_maquina(config_maquina)
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
        girado = _copiar_para_hot_folder(arquivo, destino_hot_folder, largura_util_m, logger)

        # registra ANTES de mover: depois do rename o caminho muda, e o
        # que interessa guardar é o nome com que o arquivo entrou na fila
        registrar_envio(pasta_maquina.name, arquivo, girado, pasta_relatorios=pasta_relatorios, logger=logger)

        destino_enviados = pasta_enviados / arquivo.name
        if destino_enviados.exists():
            destino_enviados = pasta_enviados / f"{arquivo.stem}_{int(time.time())}{arquivo.suffix}"
        arquivo.rename(destino_enviados)

        logger("ok", f"'{arquivo.name}' enviado pra hot folder do RasterLink7 ({pasta_maquina.name}).")
        resultado["enviados"].append(arquivo.name)

    limpar_enviados_antigos(pasta_enviados, dias=dias_retencao, logger=logger)
    return resultado


def vigiar_fila_uma_vez(pasta_fila=None, maquinas=None, logger=print, pasta_relatorios=None, dias_retencao=None):
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
    for nome_maquina, config_maquina in maquinas.items():
        pasta_maquina = pasta_raiz / nome_maquina
        resultado_por_maquina[nome_maquina] = _vigiar_uma_maquina(
            pasta_maquina, config_maquina, logger,
            pasta_relatorios=pasta_relatorios, dias_retencao=dias_retencao,
        )

    if pasta_raiz.is_dir():
        for item in pasta_raiz.iterdir():
            if item.is_dir() and item.name not in maquinas:
                logger(
                    "warn",
                    f"Pasta '{item.name}' dentro da fila não corresponde a nenhuma máquina "
                    f"configurada em MAQUINAS — ignorada (confira o nome).",
                )

    return resultado_por_maquina


def vigiar_fila(pasta_fila=None, maquinas=None, intervalo_segundos=15, logger=print,
                pasta_relatorios=None, dias_retencao=None):
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
            vigiar_fila_uma_vez(pasta_fila, maquinas, logger, pasta_relatorios, dias_retencao)
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


CAMINHO_TRAVA = pathlib.Path(__file__).resolve().parent / "rasterlink_hotfolder.lock"


def _travar_instancia_unica(caminho_trava=None):
    """
    Impede dois vigias rodando ao mesmo tempo na mesma máquina. Dois
    processos varrendo a mesma fila conseguem pegar o MESMO arquivo no
    mesmo ciclo e copiar duas vezes pra hot folder — e aí o RasterLink
    cria job duplicado, que vira material impresso duas vezes.
    Aconteceu de verdade (2026-09-05): a tarefa agendada e uma
    execução manual ficaram vivas juntas.

    Devolve (pode_rodar, trava). A 'trava' precisa continuar
    referenciada enquanto o vigia roda: fechar o arquivo solta a trava.
    """
    caminho = pathlib.Path(caminho_trava or CAMINHO_TRAVA)
    try:
        arquivo = open(caminho, "a+")
    except OSError:
        # Sem conseguir nem criar o arquivo de trava, deixa rodar: fila
        # parada é pior que o risco de duplicata, e é a mesma regra do
        # resto do módulo — falha nossa nunca segura arquivo.
        return True, None

    try:
        import msvcrt
    except ImportError:
        return True, arquivo  # fora do Windows não trava, mas não atrapalha

    try:
        arquivo.seek(0)
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        arquivo.close()
        return False, None
    return True, arquivo


if __name__ == "__main__":
    _pode_rodar, _trava = _travar_instancia_unica()
    if not _pode_rodar:
        logger_arquivo(
            "warn",
            "Já existe outro vigia rodando nesta máquina — esta instância vai sair "
            "pra não mandar arquivo duplicado pro RIP.",
        )
        raise SystemExit(0)

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
