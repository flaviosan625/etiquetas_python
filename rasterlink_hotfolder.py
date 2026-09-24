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
  2. Num vigia por POSTO, rodando vigiar_fila(...) (loop contínuo, ou
     vigiar_fila_uma_vez pela tarefa agendada): a cada intervalo, olha
     CADA subpasta das máquinas DAQUELE posto, espera cada arquivo novo
     ficar estável (parar de crescer — cobre tanto upload em andamento
     quanto download do OneDrive ainda em progresso) e só então copia
     pra hot folder local de verdade daquela máquina, movendo o
     original da fila pra uma subpasta "Enviados" dentro da subpasta da
     máquina (nunca apaga, só tira da fila pra não reenviar de novo no
     próximo ciclo).

Hoje são DOIS postos, porque as hot folders não estão todas no mesmo PC
(2026-09-07):

  POSTO_RIP  — PC do RasterLink7, atende a UJV 100 UNY CV e a SWJ320A.
               É o vigia que já roda pelo Agendador desde 2026-09-05, e
               continua sendo o posto assumido quando ninguém diz qual é.
  POSTO_SAI  — PC principal, onde roda o SAi Production Manager, que é
               quem ripa pra DOCAN. A hot folder dela é o Setup do SAi.

Cada vigia se identifica com '--posto rip' / '--posto sai' e cuida só
das máquinas dele. Pasta de máquina do outro posto é pulada em silêncio;
hot folder sumida de máquina DO posto continua sendo erro alto.

O que a DOCAN tem de diferente e este módulo NÃO faz: nas Mimaki, chegar
na hot folder é chegar na impressora. Na DOCAN, chegar na hot folder é
só começar — o SAi ripa e cospe um .prt (1,5 GB é o tamanho normal), que
ainda precisa ir pra máquina. Essa segunda perna é outro caminho.
"""
import datetime
import json
import os
import pathlib
import platform
import shutil
import sys
import time

# Pasta comum dentro do OneDrive — existe em qualquer máquina que
# tenha o OneDrive dessa conta sincronizado, por isso usa Path.home()
# em vez de um caminho fixo com o nome do usuário (mesma convenção já
# usada em rasterlink.py/RAIZ_BUSCA_OUTROS_CLIENTES).
#
# Chamava-se "Fila de Impressao RasterLink" até 23/09/2026. O nome
# mudou a pedido dele — "vamos concentrar no mesmo lugar as impressoras,
# que fica bem mais fácil": a fila deixou de ser só das Mimaki quando a
# DOCAN entrou, e RasterLink no nome fazia parecer que ela não cabia
# aqui. É UMA subpasta por máquina, e o posto de cada uma diz qual PC a
# atende.
#
# Trocar este nome muda as DUAS máquinas: o PC do RIP só passa a olhar
# a pasta nova depois do maquina_rip/atualizar.bat rodar lá.
PASTA_FILA_ONEDRIVE = (pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO"
                       / "FILA PARA IMPRESSÃO MAQUINAS")
NOME_SUBPASTA_ENVIADOS = "Enviados"

# Posto = o PC onde mora a hot folder de uma máquina, ou seja, quem
# consegue atendê-la. Existe porque as hot folders NÃO estão todas no
# mesmo lugar (2026-09-07): as duas Mimaki são atendidas pelo
# RasterLink7 no PC do RIP, e a DOCAN é atendida pelo SAi Production
# Manager no PC principal.
#
# Sem isso, um vigia só percorreria as três e reclamaria eternamente da
# pasta que não existe do lado dele — e pior, o arquivo mandado pra
# DOCAN ficaria encalhado na fila esperando um vigia que nunca vem.
# Cada vigia cuida do posto dele; pasta de máquina de OUTRO posto é
# pulada em silêncio, porque não é problema dele.
POSTO_RIP = "rip"   # PC do RasterLink7 (as Mimaki)
POSTO_SAI = "sai"   # PC principal, onde roda o SAi Production Manager (a DOCAN)

# Posto assumido quando ninguém diz qual é. É o do RIP de propósito: a
# tarefa agendada que já roda naquela máquina desde 2026-09-05 não passa
# argumento nenhum, e tem que continuar funcionando exatamente igual
# depois de receber esta versão do arquivo.
POSTO_PADRAO = POSTO_RIP

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
#
# 'mesa_util_m' é (x, y) e substitui a largura em máquina PLANA, que
# imprime em chapa: ali os dois lados são teto, e girar serve só pra
# encaixar — nunca pra economizar bobina, que não existe. Declarar uma
# plana com 'largura_util_m' deixaria passar arte comprida demais pra
# mesa; por isso 'mesa_util_m' ganha quando as duas aparecem. Quem
# aplica a diferença é LimiteDaMaquina, e não um 'if' espalhado.
MAQUINAS = {
    "UJV 100 UNY CV": {
        "hot_folder": r"C:\MijCtrl\Hot\UJV 100 UNY CV",
        "largura_util_m": 1.48,
        "posto": POSTO_RIP,
    },
    "SWJ320A": {
        "hot_folder": r"C:\MijCtrl\Hot\SWJ320A",
        "largura_util_m": 3.20,
        "posto": POSTO_RIP,
    },
    # A hot folder da DOCAN é a do SETUP do SAi Production Manager, lida
    # do PMSetups.ini dele (Device 'Docan-Docan'), não uma pasta
    # inventada: é ali que o Production Manager fica olhando sozinho, e
    # foi por ali que o teste de 2026-09-07 passou de ponta a ponta.
    #
    # 5,00 m é a largura ÚTIL, não a da mídia. A mídia é de 5,20 m; quem
    # diz 5,00 é a própria máquina (BYHX, Media/Width = 5000.00 mm).
    # Usar 5,20 aqui faria o giro automático deixar passar uma arte que
    # a máquina corta na borda.
    #
    # A DOCAN roda mais de um rolo, mas 'largura_util_m' aqui é UMA só,
    # a maior. Chegou a existir escolha de rolo por arquivo e o usuário
    # cortou (2026-09-07): "não colocar medidas somente as máquinas, eu
    # seleciono qual devo usar sem se basear pelas medidas". Quem sabe
    # que rolo está montado é quem está na máquina.
    #
    # O que isso custa, dito de frente: com o rolo de 3,20 montado, o
    # giro automático continua raciocinando por 5,00 e deixa passar reta
    # uma arte que o material corta na borda. É consequência aceita da
    # simplificação, não descuido.
    # Chamava-se só "DOCAN" até 23/09/2026, quando a segunda chegou e o
    # nome cru ficou ambíguo na tela. Renomear saiu barato porque o
    # registro dela tinha ZERO linha (ele mandou começar do zero no mesmo
    # dia) — com histórico, o nome antigo teria que continuar valendo nas
    # linhas velhas, que guardam o nome da máquina como texto.
    "DOCAN R5200": {
        "hot_folder": r"C:\Program Files\SAi\SAi Production Suite 22\Jobs and Settings\Jobs\Docan\Docan",
        "largura_util_m": 5.00,
        "posto": POSTO_SAI,
    },
    # A segunda DOCAN (2026-09-23): PLANA, imprime em chapa rígida de até
    # 100 mm de espessura. Setup 'Docan-Docan_H2525' no mesmo SAi, ao
    # lado da R5200 — por isso POSTO_SAI, e por isso o vigia que já roda
    # neste PC atende as duas sem tarefa nova no Agendador.
    #
    # A HOT FOLDER É A QUE O SAi VIGIA DE VERDADE, não a que o PMSetups.ini
    # diz. O setup nasceu com 'Jobs\Docan\Docan_1' (o SAi não usou o nome
    # H2525 porque 'Docan' já existia), e em 24/09/2026, madrugada, o campo
    # "Nome do Hot Folder" do setup foi trocado na tela para
    # 'D:\RIPADOS\DOCAN H2525' — achando que era a saída. O PMSetups.ini
    # continuou dizendo Docan_1 (ele atrasa), o vigia entregava lá, e nada
    # entrava no RIP: o adesivo das 06:39 ficou parado em Docan_1. A prova
    # de qual pasta o SAi vigia foi um ripado que caiu em D:\RIPADOS\DOCAN
    # H2525 e ele PUXOU como trabalho novo. Então o cadastro segue o SAi.
    #
    # ARMADILHA: com a entrada aqui, a SAÍDA da H2525 NUNCA pode ser esta
    # mesma pasta ("Localização padrão" em Mudar porta). Entrada e saída
    # juntas fazem o SAi puxar o próprio ripado como trabalho novo — já
    # aconteceu com a 'Lona Gaveta .prt'. Hoje a saída é D:\RIPADOS (raiz).
    # Se o campo do SAi voltar pra Docan_1, este valor volta junto.
    #
    # 'mesa_util_m' e não largura: numa plana os dois lados são teto. Os
    # 2,50 × 2,50 são a ÁREA DE IMPRESSÃO da ficha do fabricante — aqui
    # o catálogo dá a medida certa, diferente da R5200, onde ele dava a
    # mídia (5,20) e a útil (5,00) só apareceu no BYHX. Confirmar no
    # BYHX dela assim que estiver montada.
    "DOCAN H2525": {
        "hot_folder": r"D:\RIPADOS\DOCAN H2525",
        "mesa_util_m": (2.50, 2.50),
        "posto": POSTO_SAI,
    },
}


def maquinas_do_posto(posto, maquinas=None):
    """
    Só as máquinas que ESTE posto consegue atender. Máquina sem 'posto'
    declarado conta como POSTO_PADRAO, pra que uma entrada antiga (só o
    caminho da hot folder em texto) continue valendo sem alteração.
    """
    maquinas = MAQUINAS if maquinas is None else maquinas
    if not posto:
        return dict(maquinas)
    return {
        nome: config for nome, config in maquinas.items()
        if _posto_da_maquina(config) == posto
    }


def _posto_da_maquina(valor):
    if isinstance(valor, dict):
        return valor.get("posto") or POSTO_PADRAO
    return POSTO_PADRAO

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


# --- sinal de vida -------------------------------------------------
#
# Um arquivinho na raiz da fila, escrito pela máquina do RIP a cada
# passada, pra que a máquina PRINCIPAL consiga responder "o RIP está
# vivo?" sem ninguém atravessar a sala.
#
# O problema real que isso resolve: quando o OneDrive daquela máquina
# engasga (já ficou 40 min só recebendo) a tela fica IDÊNTICA à de um
# vigia morto. Sem o sinal, "está demorando" e "está parado" são a
# mesma coisa aos olhos de quem espera — e o jeito de saber era ir até
# a outra máquina olhar "Última execução" no Agendador.
NOME_ARQUIVO_SINAL = "_sinal_de_vida.json"

# De quanto em quanto tempo o sinal é reescrito. NÃO é a cada passada
# de propósito: seriam 1.440 gravações por dia numa pasta sincronizada,
# na máquina cujo OneDrive é justamente o ponto fraco. A cada 5 min dá
# resolução de sobra pra regra prática ("não conclua que parou antes de
# uns 12 minutos") com 5x menos tráfego. Mudança de ERRO de máquina
# fura a espera e grava na hora — isso é notícia.
_INTERVALO_SINAL_MINUTOS = 5


def caminho_do_sinal(pasta_fila=None, posto=None):
    """
    Um sinal POR POSTO. Dois vigias gravando o mesmo arquivo se
    apagariam mutuamente a cada ciclo — cada um escreve só as máquinas
    dele, então o estado nunca bateria com o anterior e a espera de 5
    minutos deixaria de valer: viraria uma gravação por minuto de cada
    lado, numa pasta sincronizada, que é exatamente o que
    _INTERVALO_SINAL_MINUTOS existe pra evitar.

    O posto do RIP mantém o nome antigo do arquivo de propósito: é o que
    a tarefa que já roda naquela máquina grava, e o que as telas já leem.
    """
    pasta = pathlib.Path(pasta_fila or PASTA_FILA_ONEDRIVE)
    if not posto or posto == POSTO_PADRAO:
        return pasta / NOME_ARQUIVO_SINAL
    raiz, ponto, extensao = NOME_ARQUIVO_SINAL.partition(".")
    return pasta / f"{raiz}_{posto}{ponto}{extensao}"


def ler_sinal_de_vida(pasta_fila=None, agora=None, posto=None):
    """
    O que a máquina do RIP deixou dito por último, ou None se não houver
    sinal nenhum. Nunca levanta: sinal ilegível é o mesmo que sem sinal,
    e nenhuma tela pode quebrar por causa disso.

    Devolve {'quando': datetime, 'idade_minutos': float, 'maquina': str,
    'maquinas': {nome: erro ou None}}.
    """
    caminho = caminho_do_sinal(pasta_fila, posto)
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        quando = datetime.datetime.fromisoformat(dados["quando"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None

    agora = agora or datetime.datetime.now()
    maquinas = dados.get("maquinas")
    try:
        pendente = int(dados.get("registro_pendente") or 0)
    except (TypeError, ValueError):
        pendente = 0
    return {
        "quando": quando,
        "idade_minutos": (agora - quando).total_seconds() / 60,
        "maquina": dados.get("maquina") or "?",
        "maquinas": maquinas if isinstance(maquinas, dict) else {},
        "registro_pendente": pendente,
    }


def registrar_sinal_de_vida(pasta_fila=None, resultado_por_maquina=None, agora=None, posto=None,
                            registro_pendente=None):
    """
    Deixa (ou atualiza) o sinal de vida. Devolve o caminho quando
    gravou, None quando decidiu não gravar ainda.

    'registro_pendente' é quantas entregas ainda não entraram no
    registro de produção. Vai junto pra que o PC principal enxergue a
    pendência sem ir até a máquina do RIP ler log — antes, uma linha
    perdida só aparecia meses depois, quando a comprovação fizesse falta.

    Nunca levanta: falhar em avisar que está vivo não pode impedir de
    trabalhar — é a mesma regra de registrar_envio.
    """
    agora = agora or datetime.datetime.now()
    estado = {
        nome: (r.get("erro") or None)
        for nome, r in (resultado_por_maquina or {}).items()
    }

    pendente = int(registro_pendente or 0)
    anterior = ler_sinal_de_vida(pasta_fila, agora=agora, posto=posto)
    # Pendência que mudou fura a espera pelo mesmo motivo que erro de
    # máquina fura: é notícia, não rotina.
    if (anterior is not None and anterior["maquinas"] == estado
            and anterior["registro_pendente"] == pendente):
        if 0 <= anterior["idade_minutos"] < _INTERVALO_SINAL_MINUTOS:
            return None

    caminho = caminho_do_sinal(pasta_fila, posto)
    conteudo = {
        "quando": agora.strftime("%Y-%m-%dT%H:%M:%S"),
        "maquina": platform.node(),
        "posto": posto or POSTO_PADRAO,
        "maquinas": estado,
        "registro_pendente": pendente,
    }
    # grava atômico: quem lê do outro lado nunca pode pegar meio arquivo
    temporario = caminho.with_suffix(".json.tmp")
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(conteudo, f, ensure_ascii=False, indent=2)
        os.replace(temporario, caminho)
    except OSError:
        try:
            temporario.unlink()
        except OSError:
            pass
        return None
    return caminho


# --- registro que não se perde ---------------------------------------
#
# Fila LOCAL das linhas que ainda não foram confirmadas lá no registro
# do OneDrive. Mora ao lado do módulo, no disco da própria máquina do
# RIP — de propósito: o que ela existe pra cobrir é justamente o
# OneDrive falhar.
#
# Aconteceu de verdade, de 09 a 16/09/2026: 61 entregas sumiram do
# relatório, 1.311 m² só de lona entre elas. O vigia entregava a arte,
# tentava anotar a linha, a gravação falhava, ele avisava no log daquela
# máquina (que ninguém lê) e seguia em frente. A linha morria ali. Dava
# pra ver o buraco de fora: dentro de UMA rajada, umas gravavam e outras
# não — às 15:27 de 16/09 entraram seis lonas e só uma foi registrada.
#
# Por isso nenhuma linha nasce mais direto no OneDrive: nasce aqui, e só
# sai daqui quando for LIDA DE VOLTA lá dentro. Escrever sem erro não é
# prova de que ficou.
CAMINHO_REGISTRO_PENDENTE = pathlib.Path(__file__).resolve().parent / "registro_pendente.jsonl"

# Por quantos dias a fila local continua CONFERINDO uma linha que já
# entrou no registro, antes de largar ela de vez.
#
# Não basta conferir uma vez: a linha pode sumir depois. Enquanto ela
# estiver aqui, toda passada relê o registro e reescreve o que faltar —
# é a mesma ideia dos 15 dias de "Enviados", que foram o que permitiu
# recuperar as 61 entregas perdidas. Um pouco mais que aqueles 15, de
# propósito: a fila local é a primeira linha de defesa, a pasta
# "Enviados" é a segunda.
DIAS_GUARDA_REGISTRO = 20


def _chave_do_registro(dados):
    """Identidade de uma linha do registro: quando + máquina + arquivo."""
    return (dados.get("quando"), dados.get("maquina"), dados.get("arquivo"))


def _entrada_do_diario(item):
    """
    Uma entrada da fila local: a linha do registro + quando ela foi
    conferida lá dentro pela última vez ('None' = ainda não entrou).

    Aceita também a linha crua, sem embrulho, pra que um arquivo escrito
    por uma versão anterior deste módulo continue sendo lido em vez de
    virar lixo — é fila de comprovação, não pode se perder numa
    atualização.
    """
    if isinstance(item, dict) and isinstance(item.get("linha"), dict):
        return {"linha": item["linha"], "conferida_em": item.get("conferida_em")}
    return {"linha": item, "conferida_em": None}


def _ler_jsonl(caminho):
    """
    As linhas de um .jsonl como dicionários. Nunca levanta: arquivo que
    não abre é o mesmo que vazio, e linha truncada (queda no meio de uma
    gravação) é pulada em vez de derrubar a leitura inteira.
    """
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            achados = []
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    dados = json.loads(linha)
                except ValueError:
                    continue
                if isinstance(dados, dict):
                    achados.append(dados)
            return achados
    except OSError:
        return []


def _ler_diario(caminho=None):
    """A fila local inteira, cada linha do registro com a última conferência dela."""
    caminho = pathlib.Path(caminho or CAMINHO_REGISTRO_PENDENTE)
    return [_entrada_do_diario(item) for item in _ler_jsonl(caminho)]


def _guardar_pendentes(entradas, caminho=None):
    """
    Regrava a fila local inteira, atômico. False quando não conseguiu.

    Aceita entrada embrulhada ou a linha crua — quem chama de fora
    (teste, recuperação na mão) não precisa saber do embrulho.
    """
    caminho = pathlib.Path(caminho or CAMINHO_REGISTRO_PENDENTE)
    temporario = caminho.with_suffix(".jsonl.tmp")
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with open(temporario, "w", encoding="utf-8") as f:
            for item in entradas:
                f.write(json.dumps(_entrada_do_diario(item), ensure_ascii=False) + "\n")
        os.replace(temporario, caminho)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temporario.unlink()
        except OSError:
            pass
        return False


def _arquivo_do_mes(quando_iso, pasta_relatorios=None):
    """O .jsonl do mês a que a linha pertence ('2026-09-16T21:02:06' -> 2026-09.jsonl)."""
    pasta = pathlib.Path(pasta_relatorios or PASTA_RELATORIOS) / NOME_SUBPASTA_REGISTRO
    return pasta / f"{str(quando_iso)[:7]}.jsonl"


def _acrescentar_conferindo(destino, dados):
    """
    Acrescenta a linha no registro e CONFERE relendo o arquivo.

    A releitura não é paranoia: gravar sem erro não provou nada nas
    perdas de setembro/2026 — a linha saía do vigia e não estava lá
    depois. Enquanto não for lida de volta, ela continua na fila local.
    """
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(dados, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        return False
    return _chave_do_registro(dados) in {_chave_do_registro(d) for d in _ler_jsonl(destino)}


def _data_da_linha(linha):
    """A hora da entrega, ou None quando a linha não disser (nunca levanta)."""
    try:
        return datetime.datetime.fromisoformat(linha.get("quando"))
    except (TypeError, ValueError):
        return None


def conciliar_registro(pasta_relatorios=None, caminho_pendente=None, logger=None, agora=None):
    """
    Confere a fila local contra o registro do OneDrive: reescreve o que
    não estiver lá e só então marca a linha como conferida.

    Roda a cada passada, não só quando chega arquivo. São duas defesas
    numa só:

      - a linha que NÃO conseguiu ser gravada entra sozinha na passada
        seguinte, sem ninguém perceber que houve problema;
      - a linha que foi gravada e SUMIU depois volta, porque a fila
        continua conferindo ela por DIAS_GUARDA_REGISTRO dias. Em
        setembro/2026 isso aconteceu de verdade, e gravar sem erro não
        impediu a entrega de desaparecer do relatório.

    Linha velha e já provada a fila larga. Linha que nunca entrou fica,
    por mais antiga que seja: comprovação não caduca.

    Devolve {'gravadas': n, 'pendentes': n}.
    """
    caminho_pendente = pathlib.Path(caminho_pendente or CAMINHO_REGISTRO_PENDENTE)
    entradas = _ler_diario(caminho_pendente)
    if not entradas:
        return {"gravadas": 0, "pendentes": 0}

    agora = agora or datetime.datetime.now()
    velho_demais = agora - datetime.timedelta(days=DIAS_GUARDA_REGISTRO)
    gravadas, pendentes, ficam, chaves_por_mes = 0, 0, [], {}

    for entrada in entradas:
        linha = entrada["linha"]
        destino = _arquivo_do_mes(linha.get("quando"), pasta_relatorios)
        if destino not in chaves_por_mes:
            chaves_por_mes[destino] = {_chave_do_registro(d) for d in _ler_jsonl(destino)}
        chaves = chaves_por_mes[destino]
        chave = _chave_do_registro(linha)

        if chave in chaves:
            conferida = True
        elif _acrescentar_conferindo(destino, linha):
            chaves.add(chave)
            gravadas += 1
            conferida = True
        else:
            conferida = False
            pendentes += 1

        entrada["conferida_em"] = agora.strftime("%Y-%m-%dT%H:%M:%S") if conferida else None
        entregue_em = _data_da_linha(linha)
        if conferida and entregue_em is not None and entregue_em < velho_demais:
            continue
        ficam.append(entrada)

    if ficam != entradas or gravadas:
        _guardar_pendentes(ficam, caminho_pendente)
    if pendentes and logger:
        logger(
            "warn",
            f"{pendentes} entrega(s) ainda não entraram no registro de produção — ficaram "
            f"guardadas em '{caminho_pendente.name}' e o vigia tenta de novo na próxima passada.",
        )
    return {"gravadas": gravadas, "pendentes": pendentes}


def medida_da_pagina(caminho):
    """
    (largura_m, altura_m, páginas) do arquivo, ou None.

    É o mesmo número que o vigia guarda no registro quando entrega — vive
    aqui pra quem precisa REFAZER uma linha perdida medir do mesmo jeito
    que o vigia mediria (ver recuperar_registro.py).
    """
    pymupdf = _importar_pymupdf()
    if pymupdf is None:
        return None
    return _largura_altura_m(pathlib.Path(caminho), pymupdf)


def registrar_envio(maquina, arquivo, girado, pasta_relatorios=None, quando=None,
                   logger=None, pagina=None, recuperado=None):
    """
    Anota uma linha no registro permanente do mês: uma linha JSON por
    arquivo entregue à máquina. É de propósito que grave só FATO BRUTO
    (quando, qual máquina, qual arquivo, tamanho, se girou, o tamanho
    físico da página) e nenhuma interpretação: a máquina do RIP só tem
    este módulo instalado, não o projeto inteiro — quem lê
    medida/material/m² do nome do arquivo é o gerador de relatório, lá
    no PC principal, que tem config.json e dimensoes.py.

    'pagina' é (largura_m, altura_m, quantas_páginas) do arquivo COMO
    CHEGOU, antes de qualquer giro — o vigia já abre o PDF pra decidir
    o giro, então essa medida não custa nada e não é palpite, é o
    arquivo. Existe porque nome de arquivo falha: "arquivos
    emendas_01_montado.pdf" não tem medida nenhuma escrita, e o
    relatório do dia 08/09/2026 mostrou "medida não lida" pra material
    que rodou de verdade na UJV. Com isso guardado, o relatório de
    qualquer dia futuro tem de onde tirar o m² quando o nome não disser.

    A linha vai primeiro pra fila LOCAL (ver CAMINHO_REGISTRO_PENDENTE)
    e só de lá pro OneDrive. Devolve True quando chegou no registro,
    False quando ficou na fila — e nesse caso nada se perdeu, a passada
    seguinte leva. Nunca levanta exceção: falha de registro não pode
    impedir a arte de chegar na impressora.
    """
    quando = quando or datetime.datetime.now()
    try:
        tamanho = arquivo.stat().st_size
    except OSError:
        tamanho = None

    dados = {
        "quando": quando.strftime("%Y-%m-%dT%H:%M:%S"),
        "maquina": maquina,
        "arquivo": arquivo.name,
        "bytes": tamanho,
        "girado": bool(girado),
    }
    if pagina:
        largura_m, altura_m, paginas = pagina
        dados["pagina_m"] = [round(largura_m, 4), round(altura_m, 4)]
        dados["paginas"] = paginas
    # Linha REFEITA depois, a partir do arquivo guardado em "Enviados",
    # e não escrita na hora da entrega. Guarda o porquê junto: número
    # deduzido nunca pode se passar por declarado, e o relatório é
    # comprovação pro cliente. Ver recuperar_registro.py.
    if recuperado:
        dados["recuperado"] = recuperado

    caminho_pendente = pathlib.Path(CAMINHO_REGISTRO_PENDENTE)
    _guardar_pendentes([*_ler_diario(caminho_pendente), dados], caminho_pendente)
    conciliar_registro(pasta_relatorios, caminho_pendente)

    ficou_pendente = any(
        not entrada["conferida_em"]
        and _chave_do_registro(entrada["linha"]) == _chave_do_registro(dados)
        for entrada in _ler_diario(caminho_pendente)
    )
    if ficou_pendente and logger:
        logger(
            "warn",
            f"NÃO consegui gravar '{arquivo.name}' no registro de produção "
            f"({_arquivo_do_mes(dados['quando'], pasta_relatorios)}). O arquivo foi enviado pra "
            f"impressão normalmente e a linha ficou guardada em '{caminho_pendente.name}' — "
            f"ela entra sozinha numa próxima passada, nada sai do relatório do dia.",
        )
    return not ficou_pendente


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


class LimiteDaMaquina:
    """
    O que a máquina consegue imprimir — e, por consequência, quando a
    arte tem que girar. Existem duas naturezas aqui, e tratar uma como
    a outra produz peça errada:

    ROLO (UJV, SWJ, DOCAN R5200) — uma medida só é teto, a largura
    útil; o comprimento é a bobina, que anda. Por isso girar tem um
    SEGUNDO motivo além de caber: ECONOMIA. Deitar uma arte alta e
    estreita faz o lado maior atravessar a bobina e sobra material
    (regra do usuário, 2026-09-05: "reaproveitar o máximo de material").

    MESA (DOCAN H2525, plana) — as duas medidas são teto, porque a
    chapa é finita nos dois sentidos. Não existe bobina pra economizar:
    ou cabe, ou não cabe. Girar aqui serve só pra ENCAIXAR o que não
    entrou na orientação original. Girar por "economia" numa plana não
    economizaria nada e ainda brigaria com quem posicionou a chapa na
    mesa — por isso a mesa nunca gira por esse motivo.

    A regra mora aqui, num lugar só, porque ela é respondida em três
    momentos diferentes: na tela antes de mandar (prever_giro), no
    vigia na hora de copiar (_montar_para_hot_folder) e no relatório
    depois (nao_cabe). Já esteve escrita três vezes.
    """

    def __init__(self, largura_util_m=None, mesa_util_m=None):
        self.largura_util_m = largura_util_m
        self.mesa_util_m = tuple(mesa_util_m) if mesa_util_m else None

    @property
    def plana(self):
        return self.mesa_util_m is not None

    def _tetos(self):
        """(teto do eixo X, teto do eixo Y) já com a tolerância. Y é None no rolo."""
        if self.plana:
            x, y = self.mesa_util_m
            return x + _TOLERANCIA_LARGURA_M, y + _TOLERANCIA_LARGURA_M
        return self.largura_util_m + _TOLERANCIA_LARGURA_M, None

    def cabe_em_pe(self, largura_m, altura_m):
        x, y = self._tetos()
        return largura_m <= x and (y is None or altura_m <= y)

    def cabe_deitado(self, largura_m, altura_m):
        x, y = self._tetos()
        return altura_m <= x and (y is None or largura_m <= y)

    def cabe(self, largura_m, altura_m):
        return self.cabe_em_pe(largura_m, altura_m) or self.cabe_deitado(largura_m, altura_m)

    def decidir_giro(self, largura_m, altura_m):
        """
        None quando não gira. Senão {"motivo", "economia_m"}, com motivo
        em 'nao_cabe' (girou porque não entrava em pé) ou 'economia' (já
        cabia, gira pra gastar menos bobina — só existe em rolo).
        """
        em_pe = self.cabe_em_pe(largura_m, altura_m)
        deitado = self.cabe_deitado(largura_m, altura_m)

        if em_pe and self.plana:
            return None  # numa mesa, o que já cabe fica como está
        if not deitado:
            return None  # girar não resolveria: ou já cabe em pé, ou não cabe de jeito nenhum
        if not em_pe:
            return {"motivo": "nao_cabe", "economia_m": max(0.0, altura_m - largura_m)}
        if largura_m >= altura_m:
            return None
        return {"motivo": "economia", "economia_m": altura_m - largura_m}

    def descricao(self):
        if self.plana:
            x, y = self.mesa_util_m
            return f"mesa de {x:.2f} × {y:.2f} m".replace(".", ",")
        return f"{self.largura_util_m:.2f} m úteis".replace(".", ",")

    def porque_nao_cabe(self):
        """A frase que explica a recusa — o rolo mede um lado, a mesa mede os dois."""
        if self.plana:
            return f"não entra na {self.descricao()} nem girada"
        return f"menor lado maior que a largura útil ({self.descricao()})"


def limite_da_maquina(valor):
    """
    O LimiteDaMaquina de uma entrada de MAQUINAS, ou None quando a
    máquina não declara medida nenhuma — nesse caso nada gira sozinho e
    nada é recusado, que é o comportamento de sempre.

    'mesa_util_m' ganha de 'largura_util_m' quando as duas aparecem: uma
    plana com largura solta na configuração seria lida como rolo e
    passaria arte comprida demais pra mesa.
    """
    if not isinstance(valor, dict):
        return None
    mesa = valor.get("mesa_util_m")
    if mesa:
        return LimiteDaMaquina(mesa_util_m=(float(mesa[0]), float(mesa[1])))
    largura = valor.get("largura_util_m")
    if largura:
        return LimiteDaMaquina(largura_util_m=float(largura))
    return None


def limite_de(nome_maquina, maquinas=None):
    """O limite da máquina pelo nome — o mesmo que a fila usa como subpasta."""
    maquinas = MAQUINAS if maquinas is None else maquinas
    return limite_da_maquina(maquinas.get(nome_maquina))


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
    """
    Tamanho físico da 1ª página do PDF em metros mais quantas páginas
    o arquivo tem, ou None se não der pra ler.

    A contagem de páginas anda junto porque um PDF de 4 páginas gasta 4
    vezes o material de uma — e o relatório de produção usa essa medida
    quando o nome do arquivo não traz nenhuma.
    """
    metros_por_ponto = 0.0254 / 72
    try:
        doc = pymupdf.open(str(caminho))
        try:
            rect = doc.load_page(0).rect
            paginas = doc.page_count
        finally:
            doc.close()
    except Exception:
        return None
    return (rect.width * metros_por_ponto, rect.height * metros_por_ponto, paginas)


# Caixas que descrevem a página em papel: a física (MediaBox), a
# visível (CropBox) e as de acabamento — sangria, corte e arte. Todas
# viram junto com o desenho; senão a sangria de um arquivo girado
# ficaria apontando pro lado errado da lona.
_CAIXAS_DA_PAGINA = ("MediaBox", "CropBox", "TrimBox", "BleedBox", "ArtBox")

# Matriz do giro, em coordenadas de PDF. Só rotação e translação: não
# tem escala nenhuma aqui, e é isso que garante que a arte chega na
# máquina do mesmo tamanho e na mesma proporção com que saiu.
_MATRIZ_DO_GIRO = {
    90: "0 -1 1 0 {a} {b} cm",
    180: "-1 0 0 -1 {a} {b} cm",
    270: "0 1 -1 0 {a} {b} cm",
}


def _numero_de_pdf(valor):
    """
    Número do jeito que o PDF entende. Precisa ser notação fixa: com
    '%g' um zero que sobrou da conta vira '1.86265e-09', o leitor de
    PDF não conhece notação científica e lê aquilo como 'null' — a
    caixa da página inteira se perde por causa de um expoente.
    """
    if abs(valor) < 1e-6:
        valor = 0.0
    return ("%.5f" % valor).rstrip("0").rstrip(".") or "0"


def _caixa_girada(caixa, mx0, my0, largura, altura, graus):
    """A mesma transformação do desenho, aplicada aos cantos da caixa."""
    def levar(x, y):
        if graus == 90:
            return (y - my0, largura + mx0 - x)
        if graus == 180:
            return (largura + mx0 - x, altura + my0 - y)
        if graus == 270:
            return (altura + my0 - y, x - mx0)
        return (x - mx0, y - my0)

    canto_a = levar(caixa[0], caixa[1])
    canto_b = levar(caixa[2], caixa[3])
    return (min(canto_a[0], canto_b[0]), min(canto_a[1], canto_b[1]),
            max(canto_a[0], canto_b[0]), max(canto_a[1], canto_b[1]))


def _assar_giro(pagina, graus, pymupdf):
    """
    Gira a página MUDANDO A GEOMETRIA DELA, e não pendurando um
    '/Rotate 90' no canto.

    Por que isso importa (prejuízo real, 2026-09-10): marcar '/Rotate'
    deixa o arquivo com duas leituras possíveis. A MediaBox continua
    dizendo, por exemplo, 5,65 x 1,80m — deitado — e o '/Rotate' pede
    que o desenho apareça em pé. Quem obedece as duas coisas ao mesmo
    tempo espreme o desenho em pé dentro da caixa deitada, e a arte sai
    DISTORCIDA. Foi o que aconteceu numa lona da SWJ. E o pior nem é a
    lona perdida: quem estivesse imprimindo sem ter visto a arte
    original acharia que ela é daquele jeito.

    Assando o giro na geometria não sobra leitura dupla — a página
    passa a SER retrato em vez de dizer que é, e o '/Rotate' vai
    zerado. A arte não é tocada: entra só uma matriz de rotação, sem
    escala, sem redesenhar, sem recomprimir imagem. Está provado por
    pixel: o render deste arquivo é idêntico ao do arquivo com
    '/Rotate' em quem lê '/Rotate' direito.
    """
    total = (pagina.rotation + graus) % 360
    mx0, my0, mx1, my1 = pagina.mediabox
    largura, altura = mx1 - mx0, my1 - my0

    if total == 90:
        a, b = -my0, largura + mx0
    elif total == 180:
        a, b = largura + mx0, altura + my0
    elif total == 270:
        a, b = altura + my0, -mx0
    else:
        a = b = 0.0

    doc = pagina.parent
    caixas = {}
    for nome in _CAIXAS_DA_PAGINA:
        if nome == "MediaBox":
            cantos = [mx0, my0, mx1, my1]
        else:
            tipo, valor = doc.xref_get_key(pagina.xref, nome)
            if tipo != "array":
                continue
            try:
                cantos = [float(n) for n in valor.strip("[]").split()]
            except ValueError:
                continue
            if len(cantos) != 4:
                continue
        caixas[nome] = _caixa_girada(cantos, mx0, my0, largura, altura, total)

    if total:
        cm = _MATRIZ_DO_GIRO[total].format(a=_numero_de_pdf(a), b=_numero_de_pdf(b))
        # 'q' e 'Q' em volta: o desenho da página pode ter um 'Q' a mais
        # sobrando no fim, e sem o 'q' nosso ele devolveria a matriz ao
        # que era — o giro se perderia no meio da arte.
        pymupdf.TOOLS._insert_contents(pagina, ("q " + cm + " ").encode("latin-1"), False)
        pymupdf.TOOLS._insert_contents(pagina, b" Q", True)

    pagina.set_rotation(0)
    for nome, caixa in caixas.items():
        doc.xref_set_key(pagina.xref, nome,
                         "[%s]" % " ".join(_numero_de_pdf(v) for v in caixa))


# Marca dos arquivos de montagem. O prefixo '~' e o sufixo juntos
# existem pra que a faxina NUNCA apague nada que não tenha sido nosso.
_PREFIXO_MONTAGEM = "~montando~"
_SUFIXO_MONTAGEM = ".parcial"


def _caminho_de_montagem(destino):
    """
    Onde o arquivo é montado ANTES de entrar na hot folder — ou None
    quando não dá, e aí escreve direto como era antes.

    Fica na pasta-MÃE da hot folder de propósito. O RasterLink vigia a
    hot folder ativamente: escrever 1,83 GB direto lá dentro significa
    que ele enxerga o nome do arquivo já no primeiro byte e pode tentar
    ripar um arquivo pela metade — impressão perdida e material gasto à
    toa. Na pasta-mãe ele não olha; e como é o mesmo volume, a entrada
    final vira um os.replace, que é atômico: o arquivo aparece inteiro
    ou não aparece.

    Com 45 MB isso passava despercebido. O usuário avisou (2026-09-05)
    que vêm arquivos MUITO maiores — e já existe um TIF de 1,83 GB
    nessas pastas.
    """
    pasta_mae = destino.parent.parent
    try:
        if pasta_mae.is_dir() and os.access(pasta_mae, os.W_OK):
            return pasta_mae / f"{_PREFIXO_MONTAGEM}{destino.parent.name}~{destino.name}{_SUFIXO_MONTAGEM}"
    except OSError:
        pass
    return None


def _limpar_montagens_abandonadas(hot_folder, horas=6, logger=print, agora=None):
    """
    Apaga restos de uma montagem que foi morta no meio (a tarefa tem
    limite de tempo). Só olha a pasta-mãe, e só o que tem a NOSSA marca
    — nunca entra na hot folder.
    """
    pasta_mae = pathlib.Path(hot_folder).parent
    if not pasta_mae.is_dir():
        return []

    agora = agora or datetime.datetime.now()
    limite = agora - datetime.timedelta(hours=horas)
    apagados = []
    for resto in pasta_mae.iterdir():
        if not resto.is_file():
            continue
        if not (resto.name.startswith(_PREFIXO_MONTAGEM) and resto.name.endswith(_SUFIXO_MONTAGEM)):
            continue
        try:
            if datetime.datetime.fromtimestamp(resto.stat().st_mtime) >= limite:
                continue
            resto.unlink()
        except OSError:
            continue
        apagados.append(resto.name)

    if apagados:
        logger("warn", f"{len(apagados)} montagem(ns) abandonada(s) apagada(s) de '{pasta_mae}' — "
                       f"alguma passada foi interrompida no meio de uma cópia grande.")
    return apagados


def _copiar_para_hot_folder(arquivo, destino, limite, logger):
    """
    Põe 'arquivo' na hot folder do RIP — montando fora dela e entrando
    com um rename atômico, pra o RIP nunca ver arquivo pela metade (ver
    _caminho_de_montagem). Devolve (girou, página), onde página é a
    medida real do arquivo como chegou — ver registrar_envio.
    """
    montagem = _caminho_de_montagem(destino)
    if montagem is None:
        return _montar_para_hot_folder(arquivo, destino, limite, logger)

    try:
        girado, pagina = _montar_para_hot_folder(arquivo, montagem, limite, logger)
        os.replace(montagem, destino)
    except BaseException:
        # inclui a morte por limite de tempo da tarefa: o resto não pode
        # ficar ocupando disco nem confundir quem for olhar a pasta
        try:
            montagem.unlink()
        except OSError:
            pass
        raise
    return girado, pagina


def _montar_para_hot_folder(arquivo, destino, limite, logger):
    """
    Escreve a cópia em 'destino', girando 90° quando for um PDF mais
    largo que a máquina que caberia deitado. O giro é sempre só na
    CÓPIA — o arquivo que fica guardado em 'Enviados' continua
    exatamente como chegou.

    Devolve (girou, página): 'página' é (largura_m, altura_m, páginas)
    do arquivo como chegou, pro registro de produção — ver
    registrar_envio. É None quando não deu pra medir.

    Quando não cabe nem girado, manda assim mesmo e registra o aviso
    (escolha do usuário, 2026-09-05: prefere decidir dentro do
    RasterLink a ter arquivo represado sem ele ver).
    """
    if not limite or arquivo.suffix.lower() != ".pdf":
        shutil.copy2(arquivo, destino)
        return False, None

    pymupdf = _importar_pymupdf()
    if pymupdf is None:
        logger("warn", f"pymupdf não instalado nesta máquina — '{arquivo.name}' enviado sem conferir a largura.")
        shutil.copy2(arquivo, destino)
        return False, None

    # 'medida', nao 'pagina': logo abaixo o laco que gira usa 'pagina'
    # como variavel e sobrescreveria esta — ja aconteceu, e o registro
    # de producao do dia se perdia inteiro sem ninguem ver.
    medida = _largura_altura_m(arquivo, pymupdf)
    if medida is None:
        logger("warn", f"Não consegui ler o tamanho de '{arquivo.name}' — enviado sem conferir a largura.")
        shutil.copy2(arquivo, destino)
        return False, None

    largura_m, altura_m, _paginas = medida

    # Quem decide é o LimiteDaMaquina, com a tolerância de 1mm dentro
    # dele: uma arte fechada exatamente na largura da bobina vira
    # 3.2000000038m depois da conversão de pontos pra metros, e sem
    # folga seria recusada por erro de arredondamento. É a MESMA regra
    # que a tela usa antes de mandar — o que muda é a fonte da medida.
    if not limite.cabe(largura_m, altura_m):
        logger(
            "warn",
            f"'{arquivo.name}' tem {largura_m:.2f}x{altura_m:.2f}m e não cabe nem girado na "
            f"máquina ({limite.descricao()}) — enviado assim mesmo, confira no RIP.",
        )
        shutil.copy2(arquivo, destino)
        return False, medida

    giro = limite.decidir_giro(largura_m, altura_m)
    if giro is None:
        shutil.copy2(arquivo, destino)
        return False, medida

    economia_m = giro["economia_m"]

    try:
        doc = pymupdf.open(str(arquivo))
        try:
            for pagina in doc:
                _assar_giro(pagina, 90, pymupdf)
            doc.save(str(destino))
        finally:
            doc.close()
    except Exception as e:
        logger("warn", f"Falhei ao girar '{arquivo.name}' ({e}) — enviado sem girar.")
        shutil.copy2(arquivo, destino)
        return False, medida

    if giro["motivo"] == "economia":
        motivo = f"economiza {economia_m:.2f}m de bobina ({altura_m:.2f}m em pé contra {largura_m:.2f}m deitado)"
    elif limite.plana:
        motivo = f"em pé ({largura_m:.2f}x{altura_m:.2f}m) não entrava na {limite.descricao()}"
    else:
        motivo = f"tinha {largura_m:.2f}m de largura, mais que os {limite.descricao()} da máquina"
    logger("ok", f"'{arquivo.name}' girado 90° automaticamente: {motivo}.")
    return True, medida


def _vigiar_uma_maquina(pasta_maquina, config_maquina, logger, pasta_relatorios=None, dias_retencao=None):
    """Um ciclo, só pra UMA máquina/hot folder — ver vigiar_fila_uma_vez."""
    hot_folder_str, _ = _config_maquina(config_maquina)
    limite = limite_da_maquina(config_maquina)
    hot_folder = pathlib.Path(hot_folder_str)
    if not hot_folder.is_dir():
        raise FileNotFoundError(f"Hot folder do RasterLink7 não encontrada: {hot_folder}")

    if not pasta_maquina.is_dir():
        return {"enviados": [], "ignorados": [], "falharam": []}

    pasta_enviados = pasta_maquina / NOME_SUBPASTA_ENVIADOS
    pasta_enviados.mkdir(parents=True, exist_ok=True)
    _limpar_montagens_abandonadas(hot_folder, logger=logger)

    resultado = {"enviados": [], "ignorados": [], "falharam": []}
    for arquivo in [f for f in pasta_maquina.iterdir() if f.is_file()]:
        if arquivo.suffix.lower() not in _EXTENSOES_ACEITAS:
            resultado["ignorados"].append(arquivo.name)
            continue
        if not _arquivo_estavel(arquivo):
            logger("info", f"'{arquivo.name}' ainda mudando de tamanho (upload/download em andamento) — aguardando próximo ciclo.")
            continue

        # UM arquivo com problema não pode prender a fila inteira atrás
        # dele. Aconteceu de verdade (2026-09-05): 6 arquivos passaram,
        # o sétimo falhou na cópia, e os 5 seguintes ficaram parados —
        # pra sempre, porque todo ciclo novo recomeçava pelo mesmo
        # arquivo ruim e morria no mesmo ponto. A causa provável é o
        # OneDrive desta máquina não conseguir baixar o placeholder, que
        # é justamente um erro que passa sozinho no ciclo seguinte; por
        # isso aqui só pula e continua tentando, nunca desiste do arquivo.
        try:
            _processar_arquivo_da_fila(
                arquivo, hot_folder, pasta_enviados, pasta_maquina.name,
                limite, logger, pasta_relatorios,
            )
        except Exception as e:
            resultado["falharam"].append(arquivo.name)
            _avisar_erro_de_arquivo(arquivo.name, str(e), logger)
            continue

        _avisar_erro_de_arquivo(arquivo.name, None, logger)
        resultado["enviados"].append(arquivo.name)

    limpar_enviados_antigos(pasta_enviados, dias=dias_retencao, logger=logger)
    return resultado


def _processar_arquivo_da_fila(arquivo, hot_folder, pasta_enviados, nome_maquina,
                               limite, logger, pasta_relatorios):
    """Um arquivo: copia pra hot folder, registra e tira da fila."""
    destino_hot_folder = hot_folder / arquivo.name
    girado, pagina = _copiar_para_hot_folder(arquivo, destino_hot_folder, limite, logger)

    # registra ANTES de mover: depois do rename o caminho muda, e o
    # que interessa guardar é o nome com que o arquivo entrou na fila
    registrar_envio(nome_maquina, arquivo, girado, pasta_relatorios=pasta_relatorios,
                    logger=logger, pagina=pagina)

    destino_enviados = pasta_enviados / arquivo.name
    if destino_enviados.exists():
        destino_enviados = pasta_enviados / f"{arquivo.stem}_{int(time.time())}{arquivo.suffix}"
    arquivo.rename(destino_enviados)

    # Não diz mais "do RasterLink7": o RIP da DOCAN é o SAi Production
    # Manager, e essa linha é justamente a que alguém lê quando vai
    # descobrir por que um arquivo não imprimiu. Mandá-la procurar no
    # RasterLink7 um trabalho que está no SAi custa a manhã da pessoa.
    logger("ok", f"'{arquivo.name}' entregue na hot folder da {nome_maquina}.")


# Último erro já avisado de cada máquina e de cada arquivo, pra não
# repetir a mesma linha a cada 15 segundos: uma hot folder faltando por
# um fim de semana encheria o log com milhares de linhas iguais e
# esconderia o resto.
_ultimo_erro_por_maquina = {}
_ultimo_erro_por_arquivo = {}


def _avisar_erro_de_arquivo(nome_arquivo, erro, logger):
    """
    Avisa quando um arquivo passa a falhar, ou quando finalmente passa.
    O vigia continua tentando a cada ciclo — falha de download do
    OneDrive costuma resolver sozinha — mas o log registra uma linha
    só, não uma a cada 15 segundos.
    """
    anterior = _ultimo_erro_por_arquivo.get(nome_arquivo)
    if erro == anterior:
        return
    if erro:
        _ultimo_erro_por_arquivo[nome_arquivo] = erro
        logger(
            "err",
            f"Não consegui enviar '{nome_arquivo}': {erro}. Ele continua na fila e vou tentar "
            f"de novo no próximo ciclo; os outros arquivos seguem normalmente.",
        )
    elif anterior:
        _ultimo_erro_por_arquivo.pop(nome_arquivo, None)
        logger("ok", f"'{nome_arquivo}' passou depois de falhar antes.")


def _avisar_erro_de_maquina(nome_maquina, erro, logger):
    """Avisa quando o estado de uma máquina MUDA — quebrou agora, ou voltou a funcionar."""
    anterior = _ultimo_erro_por_maquina.get(nome_maquina)
    if erro == anterior:
        return
    _ultimo_erro_por_maquina[nome_maquina] = erro
    if erro:
        logger(
            "err",
            f"Máquina '{nome_maquina}' com problema: {erro}. As outras máquinas continuam "
            f"funcionando normalmente; os arquivos desta ficam esperando na fila.",
        )
    elif anterior:
        logger("ok", f"Máquina '{nome_maquina}' voltou a funcionar.")


# Os dois dicionários acima guardam o estado dos avisos na MEMÓRIA do
# processo, o que bastava enquanto o vigia era um processo eterno. No
# modo "--uma-vez" (uma passada por minuto, disparada pelo Agendador) o
# processo morre a cada minuto e a memória vai junto: uma hot folder
# faltando num fim de semana escreveria a MESMA linha de erro umas 4.300
# vezes no log, em vez de uma — que é exatamente o que a deduplicação
# existe pra impedir. Por isso o estado vai e volta do disco a cada
# passada.
CAMINHO_ESTADO_AVISOS = pathlib.Path(__file__).resolve().parent / "rasterlink_hotfolder_avisos.json"


def carregar_estado_avisos(caminho=None):
    """
    Traz de volta os avisos já dados numa passada anterior. Nunca
    estoura: no pior caso o log repete uma linha, e linha repetida é
    infinitamente melhor que fila parada.
    """
    caminho = pathlib.Path(caminho or CAMINHO_ESTADO_AVISOS)
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return
    if not isinstance(dados, dict):
        return
    for destino, chave in ((_ultimo_erro_por_maquina, "maquinas"), (_ultimo_erro_por_arquivo, "arquivos")):
        guardado = dados.get(chave)
        if isinstance(guardado, dict):
            destino.clear()
            destino.update({k: v for k, v in guardado.items() if v is None or isinstance(v, str)})


def salvar_estado_avisos(caminho=None):
    """Guarda quais avisos já foram dados, pra próxima passada não repetir."""
    caminho = pathlib.Path(caminho or CAMINHO_ESTADO_AVISOS)
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(
                {"maquinas": _ultimo_erro_por_maquina, "arquivos": _ultimo_erro_por_arquivo},
                f, ensure_ascii=False, indent=2,
            )
    except OSError:
        pass


def garantir_pastas_da_fila(pasta_raiz, maquinas, logger=None):
    """
    Cria a subpasta de fila de cada máquina DESTE posto, com o 'Enviados'
    dentro. Devolve as que acabaram de nascer.

    Até 23/09/2026 a pasta só nascia no primeiro envio (enviar_para_fila),
    e máquina recém-cadastrada simplesmente não aparecia na fila: a DOCAN
    H2525 entrou no sistema e ele foi procurar a pasta dela pra largar
    arquivo — não existia. Pasta que não existe também não dá pra usar na
    mão, que é como um arquivo urgente entra na fila.

    Falha de criação NÃO derruba a passada: a pasta é conforto, e
    entregar o que já está na fila é o trabalho de verdade. O OneDrive
    pendurado é motivo de sobra pra um mkdir falhar num minuto e
    funcionar no seguinte.
    """
    nascidas = []
    for nome_maquina in maquinas:
        pasta = pasta_raiz / nome_maquina
        if pasta.is_dir():
            continue
        try:
            (pasta / NOME_SUBPASTA_ENVIADOS).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            if logger:
                logger("warn", f"Não consegui criar a pasta de fila da '{nome_maquina}': {e}")
            continue
        nascidas.append(nome_maquina)
        if logger:
            logger("ok", f"Pasta de fila da '{nome_maquina}' criada — ela já pode receber arquivo.")
    return nascidas


def vigiar_fila_uma_vez(pasta_fila=None, maquinas=None, logger=print, pasta_relatorios=None,
                        dias_retencao=None, posto=None):
    """
    Um ciclo só: pra cada máquina DESTE POSTO, olha a subpasta dela
    dentro da fila, manda pra hot folder local o que já estiver
    estável, e move da fila pra 'Enviados' (dentro da subpasta da
    máquina). Separado de vigiar_fila (loop contínuo) pra dar pra
    chamar isoladamente em teste, ou de um agendador externo
    (Agendador de Tarefas do Windows) em vez de um processo eternamente
    rodando.

    'posto' diz de quais máquinas este vigia cuida (ver POSTO_RIP /
    POSTO_SAI). Máquina de outro posto é pulada em silêncio — a hot
    folder dela não existe deste lado, e reclamar disso todo minuto
    seria ruído, não notícia. Já a hot folder de uma máquina DESTE posto
    que sumiu continua sendo erro alto, como sempre foi.

    Devolve {nome_maquina: {"enviados": [...], "ignorados": [...]}}.
    """
    todas = MAQUINAS if maquinas is None else maquinas
    if not todas:
        raise RuntimeError(
            "Nenhuma máquina configurada ainda — preencha o dicionário "
            "MAQUINAS em rasterlink_hotfolder.py com {nome do favorito: "
            "caminho da hot folder} depois de criar o Favorito + Hot "
            "Folder no RasterLink7."
        )

    maquinas = maquinas_do_posto(posto, todas) if posto else dict(todas)
    if posto and not maquinas:
        raise RuntimeError(
            f"Nenhuma máquina configurada para o posto '{posto}' — confira o "
            f"campo 'posto' em MAQUINAS (postos conhecidos: {POSTO_RIP}, {POSTO_SAI})."
        )

    pasta_raiz = pathlib.Path(pasta_fila or PASTA_FILA_ONEDRIVE)
    garantir_pastas_da_fila(pasta_raiz, maquinas, logger)

    resultado_por_maquina = {}
    for nome_maquina, config_maquina in maquinas.items():
        pasta_maquina = pasta_raiz / nome_maquina
        try:
            resultado_por_maquina[nome_maquina] = _vigiar_uma_maquina(
                pasta_maquina, config_maquina, logger,
                pasta_relatorios=pasta_relatorios, dias_retencao=dias_retencao,
            )
        except Exception as e:
            # Uma máquina com problema NÃO pode parar as outras. Antes
            # isso derrubava o ciclo inteiro: a hot folder da UJV sumindo
            # (RasterLink reinstalado, Favorito renomeado) fazia a SWJ
            # parar junto, sem ninguém entender por quê — e a UJV é a
            # primeira do dicionário, então nem chegava na SWJ.
            resultado_por_maquina[nome_maquina] = {"enviados": [], "ignorados": [], "erro": str(e)}
            _avisar_erro_de_maquina(nome_maquina, str(e), logger)
        else:
            _avisar_erro_de_maquina(nome_maquina, None, logger)

    # Toda passada tenta fechar o que ficou pendente no registro, mesmo
    # quando não chegou arquivo nenhum agora: é assim que uma linha que
    # não passou entra sozinha no minuto seguinte, sem ninguém precisar
    # perceber que houve problema.
    pendencia = conciliar_registro(pasta_relatorios, logger=logger)
    registrar_sinal_de_vida(pasta_raiz, resultado_por_maquina, posto=posto,
                            registro_pendente=pendencia["pendentes"])

    if pasta_raiz.is_dir():
        for item in pasta_raiz.iterdir():
            # A conferência é contra TODAS as máquinas, não só as deste
            # posto: a pasta da DOCAN é legítima e tem dono, só que o
            # dono é o outro vigia. Avisar dela aqui seria acusar de
            # errado o que está certo.
            if item.is_dir() and item.name not in todas:
                logger(
                    "warn",
                    f"Pasta '{item.name}' dentro da fila não corresponde a nenhuma máquina "
                    f"configurada em MAQUINAS — ignorada (confira o nome).",
                )

    return resultado_por_maquina


def vigiar_fila(pasta_fila=None, maquinas=None, intervalo_segundos=15, logger=print,
                pasta_relatorios=None, dias_retencao=None, posto=None):
    """
    Loop contínuo — um por POSTO, em segundo plano na máquina daquele
    posto (nunca nas outras, que só usam enviar_para_fila). Nunca para
    sozinho por causa de um erro num ciclo — registra e segue tentando
    no próximo, do mesmo jeito que monitor_onedrive.py nunca deixa um
    erro de organização derrubar o monitor inteiro.
    """
    lista = maquinas_do_posto(posto, maquinas) if posto else (maquinas if maquinas is not None else MAQUINAS)
    nomes = ", ".join(lista) or "(nenhuma)"
    logger(
        "info",
        f"Vigiando fila em: {pasta_fila or PASTA_FILA_ONEDRIVE} "
        f"(posto: {posto or POSTO_PADRAO} · máquinas: {nomes})",
    )
    while True:
        try:
            vigiar_fila_uma_vez(pasta_fila, maquinas, logger, pasta_relatorios, dias_retencao, posto)
        except Exception as e:
            logger("err", f"Erro inesperado no ciclo da fila: {e}")
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

# Onde o traceback de um erro logo no início é despejado (ver
# _rodar_protegido). É constante de módulo, e não um caminho calculado
# lá dentro, por um motivo prático: assim o teste consegue desviá-lo.
#
# Enquanto foi calculado inline, TODA rodada de teste que passasse por
# _rodar_protegido escrevia no arquivo de verdade do repositório — e as
# 49 entradas que se acumularam ali eram, todas, o mesmo teste. Alguém
# (eu, 2026-09-07) gastou uma investigação inteira atrás de um defeito
# de produção que nunca existiu.
CAMINHO_CRASH = pathlib.Path(__file__).resolve().parent / "rasterlink_hotfolder_crash.log"


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


def _rodar_protegido(alvo, posto=None):
    """
    Roda 'alvo' segurando a trava de instância única, e grava o
    traceback num arquivo se quebrar.

    A rede de diagnóstico existe (2026-09-04) porque sem console
    (pythonw.exe/.pyw) um erro bem no início — antes até do primeiro
    logger_arquivo(...) conseguir rodar — desaparecia sem deixar rastro
    nenhum, nem no log normal.

    A trava é POR POSTO. O que ela impede é duas passadas pegarem o
    MESMO arquivo e o RIP criar job duplicado — material impresso duas
    vezes. Dois postos nunca olham a mesma pasta, então travar um contra
    o outro só faria o vigia da DOCAN desistir do ciclo à toa se algum
    dia os dois rodarem no mesmo PC.
    """
    trava_do_posto = None
    if posto and posto != POSTO_PADRAO:
        trava_do_posto = CAMINHO_TRAVA.with_name(f"{CAMINHO_TRAVA.stem}_{posto}{CAMINHO_TRAVA.suffix}")

    pode_rodar, trava = _travar_instancia_unica(trava_do_posto)
    if not pode_rodar:
        logger_arquivo(
            "warn",
            f"Já existe outro vigia do posto '{posto or POSTO_PADRAO}' rodando nesta máquina — "
            f"esta instância vai sair pra não mandar arquivo duplicado pro RIP.",
        )
        return False

    try:
        alvo()
    except BaseException:
        import traceback
        try:
            with open(CAMINHO_CRASH, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n{traceback.format_exc()}\n")
        except Exception:
            pass
    finally:
        if trava is not None:
            trava.close()
    return True


def posto_pedido(argv=None):
    """
    Lê '--posto rip' / '--posto sai' (ou '--posto=sai') da linha de
    comando. Sem o argumento, devolve POSTO_PADRAO — que é o do RIP, e é
    o que faz a tarefa já agendada naquela máquina continuar idêntica
    depois de receber esta versão, sem tocar no Agendador.
    """
    argv = list(sys.argv if argv is None else argv)
    for i, arg in enumerate(argv):
        if arg.startswith("--posto="):
            return arg.split("=", 1)[1].strip().lower() or POSTO_PADRAO
        if arg == "--posto" and i + 1 < len(argv):
            return argv[i + 1].strip().lower() or POSTO_PADRAO
    return POSTO_PADRAO


def principal_uma_vez(posto=None):
    """
    Uma passada na fila e sai — é este o modo que a tarefa do Agendador
    usa na máquina do RIP, disparada de minuto em minuto.

    Por que não o loop eterno (vigiar_fila): ele já morreu sem deixar
    rastro e a fila ficou parada até alguém abrir o Agendador e clicar
    em "Executar" na mão (2026-09-05, três vezes). Um processo que
    nasce, trabalha dois segundos e morre não tem como morrer sem
    ninguém ver: se parar de disparar, a coluna "Última execução" do
    Agendador envelhece na cara de quem olha, e o pior estrago possível
    passa a ser um minuto de atraso — não o dia inteiro.

    A trava de instância única continua valendo: é ela que impede duas
    passadas de se atropelarem se alguma demorar mais que o intervalo.
    """
    posto = posto or posto_pedido()
    carregar_estado_avisos()
    resultado = {}
    try:
        _rodar_protegido(
            lambda: resultado.update(vigiar_fila_uma_vez(logger=logger_arquivo, posto=posto)),
            posto=posto,
        )
    finally:
        salvar_estado_avisos()

    _avisar_fila_parada()

    for linha in resumo_da_passada(resultado):
        _falar(linha)


def _avisar_fila_parada():
    """
    Notifica o Windows quando tem arquivo parado na fila há tempo demais.

    Fica DEPOIS do finally de propósito: passada que deu errado é
    justamente quando mais importa alguém ficar sabendo.

    O import é tardio e o erro é engolido porque este módulo viaja
    sozinho pro PC do RIP, sem o resto do projeto — lá `aviso_fila` não
    existe e a passada tem que seguir igual. Aviso é conforto: nunca
    pode atrapalhar a entrega de arquivo, que é o trabalho de verdade.
    """
    try:
        import aviso_fila

        avisadas = aviso_fila.conferir()
    except Exception as erro:  # noqa: BLE001 - ver docstring
        logger_arquivo("warn", f"aviso de fila parada não saiu: {erro}")
        return
    for maquina, (quantos, minutos) in sorted(avisadas.items()):
        logger_arquivo(
            "warn", f"AVISADO na tela: {maquina} com {quantos} arquivo(s) "
                    f"parado(s) há {minutos} min")


def _tem_saida():
    """
    Tem pra onde escrever? Com pythonw.exe — que é como a tarefa roda —
    sys.stdout é None (não é só fechado), e um print() sozinho quebra.

    De propósito NÃO exige isatty(): redirecionar pra arquivo
    ('... --uma-vez > saida.txt') é justamente o que alguém faz pra
    guardar o resultado de uma passada, e nesse caso o resumo tem que ir
    junto. É a mesma regra que logger_arquivo já segue.
    """
    try:
        return sys.stdout is not None
    except Exception:
        return False


def _falar(texto):
    """
    Escreve NA TELA e só na tela — nunca no log.

    Rodando na mão, uma passada com a fila vazia não escrevia nada e a
    pessoa ficava olhando pro prompt sem saber se tinha funcionado ou se
    o comando nem chegou a rodar (aconteceu aqui, 2026-09-05 19:37).
    Mas isso NÃO pode ir pro log: a tarefa roda 1.440 vezes por dia, e
    uma linha "passada ok" por minuto soterraria o que interessa. Como a
    tarefa roda por pythonw.exe (sem console), a distinção sai de graça.
    """
    if _tem_saida():
        print(texto)


def resumo_da_passada(resultado, agora=None):
    """Uma linha por máquina, pra quem rodou na mão ver que aconteceu alguma coisa."""
    agora = agora or datetime.datetime.now()
    linhas = [f"Passada concluída às {agora:%H:%M:%S}."]
    for maquina, r in resultado.items():
        if r.get("erro"):
            linhas.append(f"  {maquina}: PROBLEMA — {r['erro']}")
            continue
        partes = [f"{len(r.get('enviados') or [])} enviado(s)"]
        for chave, rotulo in (("falharam", "falharam"), ("ignorados", "ignorados")):
            if r.get(chave):
                partes.append(f"{len(r[chave])} {rotulo}")
        linhas.append(f"  {maquina}: {', '.join(partes)}")
    if not resultado:
        linhas.append("  (nenhuma máquina respondeu — veja o log)")
    return linhas


def rodando_de_dentro_do_onedrive(caminho=None):
    """O script está morando numa pasta sincronizada em vez de local?"""
    caminho = pathlib.Path(caminho or __file__).resolve()
    return any(parte.upper().startswith("ONEDRIVE") for parte in caminho.parts)


def principal(posto=None):
    """O vigia como processo eterno — modo antigo, mantido pra rodar na mão e ver acontecendo."""
    posto = posto or posto_pedido()
    # Dois cliques no .py DENTRO da pasta do OneDrive é o jeito errado
    # mais fácil de acontecer, e aconteceu (2026-09-05, 18:59): a pessoa
    # abre a pasta de deploy pra rodar o instalador e clica no arquivo
    # errado. O estrago não é o loop em si — é que a trava, o log e o
    # estado de avisos moram AO LADO do script. Rodando de dentro do
    # OneDrive, a trava vai parar numa pasta sincronizada, e aí o loop
    # e a tarefa agendada (que roda de C:\RasterLink) travam em arquivos
    # DIFERENTES: os dois se acham sozinhos, pegam o mesmo arquivo e o
    # RIP cria job duplicado — material impresso duas vezes.
    if rodando_de_dentro_do_onedrive():
        logger_arquivo(
            "err",
            f"NÃO vou rodar de dentro do OneDrive ({pathlib.Path(__file__).resolve().parent}). "
            f"Este é o script de instalação, não o lugar de rodar. Rode o 'instalar_tarefa.bat' "
            f"desta mesma pasta — ele copia pra C:\\RasterLink e agenda direito.",
        )
        raise SystemExit(1)
    _rodar_protegido(lambda: vigiar_fila(logger=logger_arquivo, posto=posto), posto=posto)


if __name__ == "__main__":
    import sys

    if "--autoteste" in sys.argv:
        # Só pra provar que este Python CONSEGUE iniciar este módulo
        # deste jeito. Existe porque na máquina do RIP o pythonw.exe não
        # inicia script por caminho de arquivo e falha em silêncio
        # absoluto — sem uma linha no log não dá pra saber se a tarefa
        # do Agendador não disparou ou se disparou e morreu no ar.
        logger_arquivo("info", f"autoteste ok — iniciei por: {sys.executable} {' '.join(sys.argv)}")
    elif "--uma-vez" in sys.argv:
        principal_uma_vez()
    else:
        principal()
