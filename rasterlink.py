"""
Cruza os arquivos de uma pasta de produção (com subpasta "Prontos")
contra uma lista de tarefas de um RIP (RasterLink...), colada pelo
usuário — pra saber o que já foi impresso (bate na lista, pode ir pra
Prontos) e o que estava em Prontos mas não está mais na lista
(precisa voltar pra fila de impressão).

Não existe exportação nativa de lista no RasterLink (confirmado no
manual oficial, 2026-09-01) — por isso a lista sempre vem colada à
mão pelo usuário (lida de um print da Job List), nunca lida
automaticamente de algum arquivo do RIP.

Regra (meio-termo, decidido com o usuário em 2026-09-01):
  - Nome bate EXATO com a lista -> confiável, move sozinho:
      solto (ainda não mandado pra Prontos) mas está na lista -> Prontos
      dentro de Prontos mas NÃO está na lista -> volta pra solto
  - Nome parecido mas não idêntico -> só avisa, nunca move (duvidoso).
  - Sem nenhuma semelhança -> fica como está.

Regra extra (2026-09-02): item da lista do RIP que não bate com NADA
na pasta apontada (nem solto, nem Prontos) provavelmente é de OUTRO
cliente — a mesma Job List do RIP serve a fábrica inteira, não só o
pedido apontado. Nesse caso procura pelo nome em toda a árvore de
RAIZ_BUSCA_OUTROS_CLIENTES; achando exato num lugar só, insere na
pasta Prontos de LÁ (a menos que já esteja lá — aí só ignora).

Nunca apaga nada — só move dentro da árvore de pastas do cliente.
"""
import difflib
import pathlib
import re

NOME_SUBPASTA_PRONTOS = "Prontos"
LIMIAR_PARECIDO = 0.85

# Raiz onde procurar um item da lista do RIP que não bate com nada na
# pasta apontada — a Job List do RIP serve a fábrica inteira, não só o
# pedido que a gente apontou, então um item sem match local
# provavelmente é de OUTRO cliente, arquivado em outra pasta aqui
# dentro (pedido do usuário, 2026-09-02).
RAIZ_BUSCA_OUTROS_CLIENTES = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO"

# Extensões conhecidas pra tirar do nome antes de comparar — NUNCA usar
# pathlib.Path(...).stem aqui: os nomes desse projeto têm ponto decimal
# na medida (ex: "1.00X2.00M"), e pathlib trata o ÚLTIMO ponto de
# qualquer string como se fosse extensão de arquivo — cortaria o nome
# no lugar errado quando o "nome" vem sem extensão de verdade (caso do
# Job Name do RIP, colado sem ".pdf").
_EXTENSOES_CONHECIDAS = (".pdf", ".ai", ".png", ".jpg", ".jpeg", ".eps", ".psd", ".tif", ".tiff")


def _normalizar(nome, termo_ignorado=None):
    nome = nome.strip().upper()
    for ext in _EXTENSOES_CONHECIDAS:
        if nome.endswith(ext.upper()):
            nome = nome[: -len(ext)]
            break
    if termo_ignorado:
        # útil quando um lado (pasta ou lista do RIP) ganhou um trecho
        # a mais depois (ex: nome do cliente inserido no arquivo depois
        # que o RIP já tinha importado o job) — sem isso, TUDO que
        # difere só por esse trecho vira "parecido" em vez de "exato"
        # (achado ao vivo, FESTA ALEMÃ, 2026-09-01)
        padrao = re.compile(r"[_ ]*" + re.escape(termo_ignorado.strip().upper()) + r"[_ ]*")
        nome = padrao.sub("_", nome)
        nome = re.sub(r"_+", "_", nome).strip("_ ")
    return nome


def classificar(nome_arquivo, lista_rip, termo_ignorado=None, limiar_parecido=LIMIAR_PARECIDO):
    """Devolve ('exato'|'parecido'|'nenhum', melhor_correspondencia_ou_None)."""
    alvo = _normalizar(nome_arquivo, termo_ignorado)
    melhor_razao = 0.0
    melhor_nome = None
    for nome_rip in lista_rip:
        nome_rip = nome_rip.strip()
        if not nome_rip:
            continue
        razao = difflib.SequenceMatcher(None, alvo, _normalizar(nome_rip, termo_ignorado)).ratio()
        if razao > melhor_razao:
            melhor_razao = razao
            melhor_nome = nome_rip
    if melhor_razao == 1.0:
        return "exato", melhor_nome
    if melhor_razao >= limiar_parecido:
        return "parecido", melhor_nome
    return "nenhum", None


def _indexar_arvore(raiz, termo_ignorado=None):
    """
    Indexa (nome normalizado -> lista de Paths) todo arquivo abaixo de
    'raiz', sem NUNCA abrir/ler o conteúdo — só o nome. Importante numa
    pasta do OneDrive: arquivo "só na nuvem" baixa por completo assim
    que algo tenta LER o conteúdo dele, e um TIF de produção pode ser
    gigante; olhar só o nome/metadado nunca dispara esse download.
    Devolve vazio (nunca estoura erro) se a raiz não existir — essa
    busca é um extra best-effort, não pode travar o cruzamento
    principal se o caminho mudar de máquina pra máquina.
    """
    raiz = pathlib.Path(raiz)
    if not raiz.is_dir():
        return {}
    indice = {}
    for caminho in raiz.rglob("*"):
        if not caminho.is_file():
            continue
        chave = _normalizar(caminho.name, termo_ignorado)
        indice.setdefault(chave, []).append(caminho)
    return indice


def _buscar_em_outra_pasta(entrada_rip, indice_externo, termo_ignorado, limiar_parecido, resultado):
    """
    Acha 'entrada_rip' no índice de outras pastas de cliente e, se
    achar exato num lugar só, insere na pasta Prontos de LÁ (não da
    pasta original que o usuário apontou) — a menos que já esteja
    dentro de um Prontos, aí não faz nada (já está no lugar certo).
    Nunca decide sozinho entre mais de um arquivo com o mesmo nome em
    pastas diferentes — isso vira erro, pra conferir na mão.
    """
    chave = _normalizar(entrada_rip, termo_ignorado)
    exatos = indice_externo.get(chave, [])

    if not exatos:
        melhor_razao, melhor_caminho = 0.0, None
        for chave_indexada, caminhos in indice_externo.items():
            razao = difflib.SequenceMatcher(None, chave, chave_indexada).ratio()
            if razao > melhor_razao:
                melhor_razao, melhor_caminho = razao, caminhos[0]
        if melhor_caminho is not None and melhor_razao >= limiar_parecido:
            resultado["duvidosos"].append(("achado em outra pasta?", str(melhor_caminho), entrada_rip))
        else:
            resultado["nao_encontrados"].append(entrada_rip)
        return

    if len(exatos) > 1:
        resultado["erros"].append(
            f"'{entrada_rip}' bate exato com MAIS DE UM arquivo em pastas diferentes "
            f"({', '.join(str(c) for c in exatos)}) — não movido, confira na mão"
        )
        return

    caminho = exatos[0]
    if caminho.parent.name == NOME_SUBPASTA_PRONTOS:
        return  # já está no Prontos certo de lá — nada a fazer

    pasta_prontos_dele = caminho.parent / NOME_SUBPASTA_PRONTOS
    pasta_prontos_dele.mkdir(parents=True, exist_ok=True)
    destino = pasta_prontos_dele / caminho.name
    if destino.exists():
        resultado["erros"].append(
            f"'{caminho.name}' achado solto em '{caminho.parent}', mas já existe um arquivo com esse "
            f"nome no Prontos de lá — não movido, confira na mão"
        )
        return
    caminho.rename(destino)
    resultado["achados_em_outra_pasta"].append((entrada_rip, str(caminho), str(destino)))


def rastrear(
    pasta_producao, lista_rip, termo_ignorado=None, limiar_parecido=LIMIAR_PARECIDO,
    raiz_busca_outros_clientes=RAIZ_BUSCA_OUTROS_CLIENTES,
):
    """
    Move de verdade os arquivos que baterem EXATO (ver regra no
    docstring do módulo). Retorna um dict com o resumo de tudo que
    aconteceu, pra quem chamou (tela ou script) decidir como mostrar.
    """
    pasta = pathlib.Path(pasta_producao)
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")
    pasta_prontos = pasta / NOME_SUBPASTA_PRONTOS
    pasta_prontos.mkdir(parents=True, exist_ok=True)

    soltos = [f for f in pasta.iterdir() if f.is_file()]
    prontos = [f for f in pasta_prontos.iterdir() if f.is_file()]

    resultado = {
        "movidos_pra_prontos": [], "movidos_pra_solto": [], "duvidosos": [], "erros": [],
        "achados_em_outra_pasta": [], "nao_encontrados": [],
    }

    for arquivo in soltos:
        classe, correspondencia = classificar(arquivo.name, lista_rip, termo_ignorado, limiar_parecido)
        if classe == "exato":
            destino = pasta_prontos / arquivo.name
            if destino.exists():
                resultado["erros"].append(
                    f"'{arquivo.name}' bate na lista, mas já existe um arquivo com esse nome em "
                    f"Prontos — não movido, confira na mão"
                )
                continue
            arquivo.rename(destino)
            resultado["movidos_pra_prontos"].append(arquivo.name)
        elif classe == "parecido":
            resultado["duvidosos"].append(("solto->Prontos?", arquivo.name, correspondencia))
        # "nenhum": continua solto, ainda precisa imprimir — nada a fazer

    for arquivo in prontos:
        classe, correspondencia = classificar(arquivo.name, lista_rip, termo_ignorado, limiar_parecido)
        if classe == "nenhum":
            destino = pasta / arquivo.name
            if destino.exists():
                resultado["erros"].append(
                    f"'{arquivo.name}' não está na lista, mas já existe um arquivo com esse nome "
                    f"solto — não movido, confira na mão"
                )
                continue
            arquivo.rename(destino)
            resultado["movidos_pra_solto"].append(arquivo.name)
        elif classe == "parecido":
            resultado["duvidosos"].append(("Prontos->solto?", arquivo.name, correspondencia))
        # "exato": já está certo em Prontos, nada a fazer

    # Regra extra (pedido do usuário, 2026-09-02): item da lista do RIP
    # que não bate com NADA nessa pasta (nem solto, nem Prontos)
    # provavelmente é de OUTRO cliente — procura pelo nome em toda a
    # árvore de 'raiz_busca_outros_clientes' (ver _indexar_arvore e
    # _buscar_em_outra_pasta). 'nomes_locais' usa os arquivos de ANTES
    # dos laços acima, pra não re-buscar algo que acabou de ser
    # resolvido localmente nesta mesma rodada.
    nomes_locais = [f.name for f in soltos] + [f.name for f in prontos]
    indice_externo = None
    for entrada in lista_rip:
        entrada = entrada.strip()
        if not entrada:
            continue
        teve_match_local = any(
            classificar(nome, [entrada], termo_ignorado, limiar_parecido)[0] in ("exato", "parecido")
            for nome in nomes_locais
        )
        if teve_match_local:
            continue

        if indice_externo is None:
            indice_externo = _indexar_arvore(raiz_busca_outros_clientes, termo_ignorado)
        _buscar_em_outra_pasta(entrada, indice_externo, termo_ignorado, limiar_parecido, resultado)

    return resultado
