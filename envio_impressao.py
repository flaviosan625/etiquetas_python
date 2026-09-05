"""
Envio de arquivos de uma pasta de produção pra fila de impressão das
máquinas, com conferência antes e registro depois.

Este módulo é só a lógica — não desenha tela nem gera PDF (ver
gui.JanelaEnviarImpressao e documento_enviados.py). Ele responde três
perguntas, nesta ordem:

  1. listar(...)    — o que tem nesta pasta pra mandar, pra qual máquina,
                      quanto é em m², o que já foi antes
  2. conferir(...)  — o que trava, o que merece atenção, o que está limpo
  3. enviar(...)    — copia pra fila, confere a cópia, e só então anota

Três regras que vieram do usuário e que o código respeita literalmente:

  - **O arquivo original nunca sai do lugar** (2026-09-05). Nem pra
    Prontos, nem pra pasta nenhuma. Pra fila vai sempre uma CÓPIA, e
    quem sabe o que já foi é o documento de Enviados, não a posição do
    arquivo na pasta.
  - **A máquina é decidida pelo material no nome, não pela largura**
    (2026-09-05): lona sempre na SWJ320A, adesivo/vinil/adesivado
    sempre na UJV — "na SWJ não colocamos adesivos". A largura útil
    virou só alerta. A sugestão vem preenchida mas NUNCA fica travada:
    "não sabemos o que pode acontecer no meio de uma produção".
  - **Reenvio soma, não substitui**: mandar o mesmo arquivo de novo é
    caso real (peça danificada na instalação, arte corrigida salva por
    cima) — vira uma linha nova, com a hora dela, e conta no subtotal,
    porque material foi gasto de novo. Mesma regra do relatório diário.
"""
import datetime
import pathlib
import shutil

from dimensoes import extrair_dimensoes, extrair_quantidade, identificar_categoria, identificar_categoria_extra
from producao import NOME_PASTA_PRODUCAO, NOME_SUBPASTA_PRONTOS, PASTA_CORTE, _pasta_de_trabalho_para
from rasterlink_hotfolder import (
    EXTENSOES_ACEITAS, MAQUINAS, PASTA_FILA_ONEDRIVE, _config_maquina, enviar_para_fila,
)

# Nome da máquina de cada destino. Tem que bater EXATO com uma chave de
# rasterlink_hotfolder.MAQUINAS — é o nome da subpasta da fila.
MAQUINA_LONA = "SWJ320A"
MAQUINA_ADESIVO = "UJV 100 UNY CV"

# Categoria que manda pra UJV. Não é só a categoria "ADESIVO" pura: o
# config.json já mapeia VINIL como sinônimo de ADESIVO e ADESIVADO como
# gatilho de material composto, então "PVC ADESIVADO" e "VINIL IMPRESSO"
# caem aqui pelo mesmo caminho, sem regra nova (conferido no config real,
# 2026-09-05).
_CATEGORIA_ADESIVO = "ADESIVO"
_CATEGORIA_LONA = "LONA"

# Pasta que nunca entra na lista: corte direto não passa por impressora.
_SUBPASTA_FORA = PASTA_CORTE

# Pastas que a varredura nunca abre. 'Prontos' é a confirmação manual do
# usuário de que a peça está acabada — o sistema não mexe nem lê de lá.
# 'Enviados' é onde mora o documento (ver documento_enviados.py), não
# arte pra mandar.
NOME_PASTA_ENVIADOS = "Enviados"
_PASTAS_IGNORADAS = {NOME_SUBPASTA_PRONTOS.upper(), NOME_PASTA_ENVIADOS.upper(), _SUBPASTA_FORA.upper()}

# Atributos do Windows que marcam arquivo "só na nuvem" do OneDrive.
# Copiar um desses força o download inteiro — e nesta casa tem TIF de
# 1,83 GB na pasta de produção. Detectar isso é só ler o atributo, nunca
# abre o arquivo, então não dispara download nenhum.
_ATTR_OFFLINE = 0x1000
_ATTR_RECALL_ON_OPEN = 0x40000
_ATTR_RECALL_ON_DATA_ACCESS = 0x400000
_ATTRS_SO_NA_NUVEM = _ATTR_OFFLINE | _ATTR_RECALL_ON_OPEN | _ATTR_RECALL_ON_DATA_ACCESS


def sugerir_maquina(nome_arquivo, config):
    """
    Máquina sugerida pelo material que aparece no NOME do arquivo —
    nunca pela largura (regra do usuário, 2026-09-05).

    Adesivo é conferido ANTES de lona de propósito: "PVC ADESIVADO"
    tem categoria PVC e categoria_extra ADESIVO, e o que manda é a
    palavra adesivo. Nome sem lona nem adesivo (ex: "PS IMPRESSO
    REFILE") também vai pra UJV — decisão do usuário até a DOCAN, que
    faz impressão direta, ser resolvida; quando ela entrar, é só mais
    uma entrada em MAQUINAS e mais um caso aqui.
    """
    nome_upper = nome_arquivo.upper()
    materiais = config["materiais"]
    categoria, _ = identificar_categoria(nome_upper, materiais, config.get("sinonimos_categoria", {}))
    categoria_extra = identificar_categoria_extra(nome_upper, materiais, config.get("materiais_compostos", {}))

    if _CATEGORIA_ADESIVO in (categoria, categoria_extra):
        return MAQUINA_ADESIVO
    if categoria == _CATEGORIA_LONA:
        return MAQUINA_LONA
    return MAQUINA_ADESIVO


def prever_giro(dimensao, nome_maquina, maquinas=None):
    """
    Diz se a arte deve girar 90° na máquina escolhida, a partir da
    medida lida do NOME — é previsão, não decisão: quem abre o PDF e
    gira de verdade é o vigia no PC do RIP (ver rasterlink_hotfolder.
    _copiar_para_hot_folder). A regra é a mesma dos dois lados, o que
    muda é a fonte da medida.

    Devolve None quando não dá pra prever (sem medida no nome, máquina
    sem largura útil configurada) ou quando não gira. Senão devolve
    {"motivo": "economia"|"nao_cabe", "economia_m": float}.
    """
    if not dimensao:
        return None
    maquinas = MAQUINAS if maquinas is None else maquinas
    _, largura_util_m = _config_maquina(maquinas.get(nome_maquina))
    if not largura_util_m:
        return None

    largura_m = dimensao["largura_m"]
    altura_m = dimensao["altura_m"]
    # mesma folga de 1mm do vigia: arte fechada exatamente na largura da
    # bobina vira 3.2000000038m depois da conversão e seria recusada por
    # arredondamento
    limite = largura_util_m + 0.001
    cabe_em_pe = largura_m <= limite
    cabe_deitado = altura_m <= limite

    if not cabe_deitado:
        return None
    if not cabe_em_pe:
        return {"motivo": "nao_cabe", "economia_m": max(0.0, altura_m - largura_m)}
    if largura_m >= altura_m:
        return None
    return {"motivo": "economia", "economia_m": altura_m - largura_m}


def cabe_na_maquina(dimensao, nome_maquina, maquinas=None):
    """
    False só quando a arte não cabe na máquina NEM girada — caso em que
    o envio continua acontecendo, com aviso (escolha do usuário,
    2026-09-05: prefere decidir dentro do RasterLink a ter arquivo
    represado sem ele ver). True quando cabe ou quando não dá pra saber.
    """
    if not dimensao:
        return True
    maquinas = MAQUINAS if maquinas is None else maquinas
    _, largura_util_m = _config_maquina(maquinas.get(nome_maquina))
    if not largura_util_m:
        return True
    limite = largura_util_m + 0.001
    return dimensao["largura_m"] <= limite or dimensao["altura_m"] <= limite


def _so_na_nuvem(caminho):
    """
    True se o arquivo é um placeholder "só na nuvem" do OneDrive. Lê só
    o atributo (st_file_attributes) — nunca abre o arquivo, então não
    dispara o download. Fora do Windows, ou em qualquer erro, devolve
    False: é um aviso, não pode virar obstáculo.
    """
    try:
        return bool(caminho.stat().st_file_attributes & _ATTRS_SO_NA_NUVEM)
    except (AttributeError, OSError):
        return False


def _aberto_em_outro_programa(caminho):
    """
    True se outro processo está com o arquivo aberto de um jeito que
    impede acesso exclusivo (designer com a arte aberta no Illustrator,
    por exemplo) — a cópia sairia da última versão salva em disco, que
    pode não ser a que está na tela dele.

    Usa CreateFileW com dwShareMode=0, que é o único teste confiável de
    lock no Windows, e passa FILE_FLAG_OPEN_NO_RECALL pra NUNCA hidratar
    um arquivo que está só na nuvem. Qualquer erro inesperado devolve
    False — é aviso, não trava nada.
    """
    if _so_na_nuvem(caminho):
        return False  # nem tenta: não vale arriscar disparar download por causa de um aviso
    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, ValueError):
        return False

    GENERIC_READ = 0x80000000
    OPEN_EXISTING = 3
    FILE_FLAG_OPEN_NO_RECALL = 0x00100000
    INVALID_HANDLE = ctypes.c_void_p(-1).value
    ERRO_COMPARTILHAMENTO = 32  # ERROR_SHARING_VIOLATION

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        handle = kernel32.CreateFileW(
            str(caminho), GENERIC_READ, 0, None, OPEN_EXISTING, FILE_FLAG_OPEN_NO_RECALL, None,
        )
        if handle == INVALID_HANDLE:
            return ctypes.get_last_error() == ERRO_COMPARTILHAMENTO
        kernel32.CloseHandle(handle)
        return False
    except Exception:
        return False


def raiz_do_cliente(pasta_escolhida):
    """
    Pasta do cliente a partir de qualquer pasta escolhida dentro dela —
    é onde vai morar a pasta 'Enviados' com o documento (pedido do
    usuário, 2026-09-05: "criar a pasta de enviados na raiz daquele
    cliente").

    Sobe o caminho procurando o trecho que começa com 'PRODUCAO'; o
    cliente é o pai dele. Escolhendo 'FESTA ALEMA\\PRODUCAO 03_09' ou
    'FESTA ALEMA\\PRODUCAO 03_09\\LONAS', os dois chegam em
    'FESTA ALEMA'. Sem nenhum trecho PRODUCAO no caminho (pasta fora do
    padrão), devolve a própria pasta escolhida — o documento fica ali
    dentro mesmo, que é previsível, em vez de tentar adivinhar.
    """
    pasta = pathlib.Path(pasta_escolhida).resolve()
    for parte in [pasta, *pasta.parents]:
        if parte.name.upper().startswith(NOME_PASTA_PRODUCAO):
            return parte.parent
    return pasta


def nome_da_producao(pasta_escolhida):
    """
    Nome da pasta de produção de onde o envio saiu, pra virar a coluna
    "de qual produção" no documento.

    Sobe procurando o trecho que começa com 'PRODUCAO': apontando
    'PRODUCAO 03_09\\LONAS' o nome tem que continuar sendo
    'PRODUCAO 03_09', não 'LONAS'. Fora do padrão, usa o nome da própria
    pasta escolhida.
    """
    pasta = pathlib.Path(pasta_escolhida).resolve()
    for parte in [pasta, *pasta.parents]:
        if parte.name.upper().startswith(NOME_PASTA_PRODUCAO):
            return parte.name
    return pasta.name


def _arquivos_da_pasta(pasta):
    """
    Todo arquivo de arte abaixo de 'pasta', pulando 'Prontos',
    'Enviados' e 'CORTES' em qualquer nível.

    Desce nas subpastas de propósito: a pasta de produção real tem
    subpasta solta criada na mão (achado na FESTA ALEMÃ: 'enchanted_
    land', 'PS impres_dupla face recorte') e um arquivo escondido numa
    delas ficaria invisível na tela. O filtro de extensão já barra
    readme.txt e .zip.
    """
    pasta = pathlib.Path(pasta)
    if not pasta.is_dir():
        return []

    achados = []
    for item in sorted(pasta.iterdir(), key=lambda p: p.name.lower()):
        if item.is_dir():
            if item.name.upper() in _PASTAS_IGNORADAS:
                continue
            achados.extend(_arquivos_da_pasta(item))
        elif item.suffix.lower() in EXTENSOES_ACEITAS:
            achados.append(item)
    return achados


def listar(pasta_escolhida, config, envios_anteriores=None, maquinas=None):
    """
    Lista o que dá pra mandar desta pasta, já com máquina sugerida,
    medida, m² total e o histórico de envios daquele arquivo.

    'envios_anteriores' é a lista de envios já registrados no documento
    do cliente (ver documento_enviados.carregar) — usada só pra marcar
    "já enviado", nunca pra esconder nada da lista: reimpressão é caso
    real e quem decide é o usuário.

    Cada item devolvido:
      caminho, arquivo, pasta_trabalho, categoria, quantidade, dimensao,
      area_total_m2, maquina, giro, cabe, envios_anteriores
    """
    materiais = config["materiais"]
    sinonimos = config.get("sinonimos_categoria", {})
    compostos = config.get("materiais_compostos", {})
    por_arquivo = {}
    for envio in (envios_anteriores or []):
        por_arquivo.setdefault(envio["arquivo"], []).append(envio)

    itens = []
    for caminho in _arquivos_da_pasta(pasta_escolhida):
        nome_upper = caminho.name.upper()
        categoria, _ = identificar_categoria(nome_upper, materiais, sinonimos)
        quantidade, _ = extrair_quantidade(nome_upper)
        dimensao = extrair_dimensoes(nome_upper, config)
        maquina = sugerir_maquina(caminho.name, config)

        itens.append({
            "caminho": caminho,
            "arquivo": caminho.name,
            "pasta_trabalho": _pasta_de_trabalho_para(caminho.name, materiais, sinonimos, compostos),
            "categoria": categoria,
            "quantidade": quantidade,
            "dimensao": dimensao,
            "area_total_m2": round(dimensao["area_m2"] * quantidade, 2) if dimensao else None,
            "maquina": maquina,
            "giro": prever_giro(dimensao, maquina, maquinas),
            "cabe": cabe_na_maquina(dimensao, maquina, maquinas),
            "envios_anteriores": sorted(por_arquivo.get(caminho.name, []), key=lambda e: e["quando"]),
        })
    return itens


def subtotais_por_material(itens):
    """
    m² somado por material — NUNCA um total combinado entre materiais
    diferentes (regra fixa desta casa: cada material roda numa máquina
    diferente e um número somado não representaria nada real).

    Soma o valor JÁ ARREDONDADO de cada linha, igual ao relatório
    diário: quem confere o documento soma a coluna que está vendo, e o
    subtotal precisa fechar com ela.
    """
    totais = {}
    for item in itens:
        if item["area_total_m2"] is None or not item.get("categoria"):
            continue
        totais[item["categoria"]] = round(totais.get(item["categoria"], 0.0) + item["area_total_m2"], 2)
    return totais


def conferir(itens, pasta_fila=None, maquinas=None):
    """
    Passa a régua fina ANTES de qualquer coisa se mexer. Não copia, não
    escreve, não move nada — só olha nome, tamanho e atributo, que é o
    que não dispara download do OneDrive.

    Devolve {"bloqueados": [(item, motivo)], "atencao": [(item, [motivos])],
    "limpos": [item]}. Item bloqueado nunca é enviado; item em atenção
    é enviado normalmente — o aviso existe pra você decidir antes, não
    pra segurar arquivo.
    """
    maquinas = MAQUINAS if maquinas is None else maquinas
    raiz_fila = pathlib.Path(pasta_fila or PASTA_FILA_ONEDRIVE)

    # (máquina, nome) porque a colisão é na PASTA DA FILA: o mesmo nome
    # indo pra duas máquinas diferentes cai em pastas diferentes e não
    # se atropela.
    vistos = {}
    for item in itens:
        vistos.setdefault((item["maquina"], item["arquivo"].lower()), []).append(item)

    resultado = {"bloqueados": [], "atencao": [], "limpos": []}
    for item in itens:
        caminho = item["caminho"]

        if len(vistos[(item["maquina"], item["arquivo"].lower())]) > 1:
            resultado["bloqueados"].append((
                item,
                f"Dois arquivos marcados com este mesmo nome vão pra fila da {item['maquina']} — "
                f"um sobrescreveria o outro em silêncio.",
            ))
            continue

        if not caminho.is_file():
            resultado["bloqueados"].append((item, "O arquivo não está mais nesta pasta — foi movido ou apagado."))
            continue

        try:
            tamanho = caminho.stat().st_size
        except OSError as e:
            resultado["bloqueados"].append((item, f"Não consegui ler o arquivo: {e}"))
            continue

        if tamanho == 0:
            resultado["bloqueados"].append((item, "Está com 0 byte — salvamento que falhou, nunca é arte de verdade."))
            continue

        na_fila = raiz_fila / item["maquina"] / item["arquivo"]
        if na_fila.exists():
            resultado["bloqueados"].append((
                item,
                f"Já tem um arquivo com este nome na fila da {item['maquina']}, ainda não puxado pelo RIP. "
                f"Sobrescrever agora pode mandar arquivo pela metade pra impressão.",
            ))
            continue

        avisos = []
        if _so_na_nuvem(caminho):
            avisos.append(f"Está só na nuvem — vai baixar {_tamanho_legivel(tamanho)} antes de copiar.")
        elif _aberto_em_outro_programa(caminho):
            avisos.append("Aberto em outro programa — a cópia pode sair de uma versão ainda não salva.")

        if item["envios_anteriores"]:
            ultimo = item["envios_anteriores"][-1]
            quantas = len(item["envios_anteriores"])
            vezes = "1 vez" if quantas == 1 else f"{quantas} vezes"
            avisos.append(
                f"Já foi enviado {vezes} — último em {_data_curta(ultimo['quando'])} "
                f"para a {ultimo['maquina']}. Reimpressão?"
            )

        if not item["cabe"]:
            d = item["dimensao"]
            avisos.append(
                f"Tem {d['largura_m']:.2f}x{d['altura_m']:.2f}m e não cabe nem girado na "
                f"{item['maquina']} — vai assim mesmo, confira no RasterLink."
            )

        if avisos:
            resultado["atencao"].append((item, avisos))
        else:
            resultado["limpos"].append(item)

    return resultado


def fila_parada(pasta_fila=None, maquinas=None, minutos=20, agora=None):
    """
    Diz quais filas têm arquivo esperando há mais de 'minutos' — sinal
    de que o vigia no PC do RIP parou, ou de que o OneDrive daquela
    máquina não está recebendo.

    Existe por causa de um caso real (2026-09-05): dois arquivos foram
    pra fila da UJV às 16:04 e continuaram lá, porque do outro lado
    ninguém puxou. A tela de envio dizia "enviado" e estava certa — o
    arquivo tinha saído daqui — mas ninguém percebeu que ele não tinha
    chegado na máquina. Em condição normal a fila esvazia em segundos.

    Devolve {nome_maquina: (quantos, minutos_do_mais_antigo)}.
    """
    maquinas = MAQUINAS if maquinas is None else maquinas
    raiz = pathlib.Path(pasta_fila or PASTA_FILA_ONEDRIVE)
    agora = agora or datetime.datetime.now()

    parados = {}
    for nome_maquina in maquinas:
        pasta = raiz / nome_maquina
        if not pasta.is_dir():
            continue
        idades = []
        for arquivo in pasta.iterdir():
            if not arquivo.is_file() or arquivo.suffix.lower() not in EXTENSOES_ACEITAS:
                continue
            try:
                # ctime, não mtime: copy2 preserva a data do ORIGINAL, então
                # mtime é a data da arte, não a hora em que ela entrou na fila
                entrou = datetime.datetime.fromtimestamp(arquivo.stat().st_ctime)
            except OSError:
                continue
            idades.append((agora - entrou).total_seconds() / 60)
        if idades and max(idades) >= minutos:
            parados[nome_maquina] = (len(idades), int(max(idades)))
    return parados


def _data_curta(quando_iso):
    """'2026-09-05T14:22:03' -> '05/09 14:22'. Devolve o original se não for uma data que a gente entenda."""
    try:
        return datetime.datetime.fromisoformat(quando_iso).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return str(quando_iso)


def _tamanho_legivel(bytes_):
    """Tamanho em GB/MB/KB/B — sem isso um arquivo de 1120 bytes aparece como '0 MB'."""
    if bytes_ is None:
        return "?"
    for limite, unidade, divisor in (
        (1024 ** 3, "GB", 1024 ** 3), (1024 ** 2, "MB", 1024 ** 2), (1024, "KB", 1024),
    ):
        if bytes_ >= limite:
            return f"{bytes_ / divisor:.2f} {unidade}".replace(".", ",")
    return f"{bytes_} B"


def enviar(itens, pasta_producao, pasta_fila=None, maquinas=None, agora=None, logger=None):
    """
    Copia cada item pra fila da sua máquina, CONFERE que a cópia chegou
    inteira, e só então monta o registro do envio. A ordem nunca
    inverte: se a cópia falhar ou chegar com tamanho diferente, a cópia
    é apagada da fila e nada é anotado — nunca existe linha no documento
    de um arquivo que não chegou.

    O original não é tocado em momento nenhum.

    Devolve {"enviados": [registro], "falhas": [(item, motivo)]}. Cada
    'registro' é o que vai virar linha no documento do cliente (ver
    documento_enviados.registrar).
    """
    agora = agora or datetime.datetime.now()
    resultado = {"enviados": [], "falhas": []}
    nome_producao = nome_da_producao(pasta_producao)

    for item in itens:
        caminho = item["caminho"]
        try:
            tamanho_origem = caminho.stat().st_size
        except OSError as e:
            resultado["falhas"].append((item, f"Não consegui ler o arquivo: {e}"))
            continue

        try:
            destino = enviar_para_fila(caminho, item["maquina"], pasta_fila=pasta_fila, maquinas=maquinas)
        except (OSError, ValueError, FileNotFoundError, shutil.Error) as e:
            resultado["falhas"].append((item, f"Falhei ao copiar pra fila: {e}"))
            continue

        try:
            tamanho_copia = destino.stat().st_size
        except OSError as e:
            resultado["falhas"].append((item, f"A cópia não pôde ser conferida: {e}"))
            _apagar_copia(destino, logger)
            continue

        if tamanho_copia != tamanho_origem:
            resultado["falhas"].append((
                item,
                f"A cópia chegou com {_tamanho_legivel(tamanho_copia)} e o original tem "
                f"{_tamanho_legivel(tamanho_origem)} — cópia incompleta, desfeita.",
            ))
            _apagar_copia(destino, logger)
            continue

        resultado["enviados"].append({
            "quando": agora.strftime("%Y-%m-%dT%H:%M:%S"),
            "arquivo": item["arquivo"],
            "maquina": item["maquina"],
            "producao": nome_producao,
            "pasta_trabalho": item["pasta_trabalho"],
            "categoria": item["categoria"],
            "quantidade": item["quantidade"],
            "dimensao": item["dimensao"],
            "area_total_m2": item["area_total_m2"],
            "girou_previsto": bool(item["giro"]),
            "bytes": tamanho_origem,
        })
        if logger:
            logger("ok", f"'{item['arquivo']}' enviado pra fila da {item['maquina']}.")

    return resultado


def _apagar_copia(destino, logger=None):
    """Desfaz uma cópia que não passou na conferência — nunca deixa arquivo meio copiado esperando o RIP puxar."""
    try:
        destino.unlink()
    except OSError as e:
        if logger:
            logger(
                "warn",
                f"A cópia de '{destino.name}' não passou na conferência mas eu não consegui apagá-la "
                f"da fila ({e}) — apague na mão antes que o RIP puxe.",
            )
