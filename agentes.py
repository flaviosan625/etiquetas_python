"""
Os agentes do sistema — as automações que rodam sozinhas — num lugar só:
o que cada um faz, se está vivo, e como forçar um disparo.

Pedido do usuário (2026-09-13): "arrumar esses agentes para que eu possa
forçar um disparo caso ele não execute a tarefa, deixar sempre bem
dinâmico". Este módulo é a parte sem tela (lê, classifica, dispara); a
janela é gui_agentes.py.

FORÇAR DISPARO É DISPARAR A TAREFA DE VERDADE
'disparar' pede ao Agendador do Windows pra rodar a tarefa agora
(IRegisteredTask.Run). Sondado em 2026-09-13: funciona SEM administrador e
a "Última execução" muda na hora. É a passada de sempre — mesmo Python,
mesmo usuário, mesma pasta — e o IgnoreNew da tarefa impede duas juntas.
Não é um "jeito parecido" de rodar: é o mesmo.

'rodar_aqui' é outra coisa, pro caso em que disparar não adianta: roda a
passada direto deste PC e devolve o que ela escreveu. Serve pra VER o erro
quando a tarefa roda e falha, ou pra fazer o trabalho quando a tarefa
sumiu ou foi desligada no Agendador.

CADA LINHA DIZ O QUE MEDIU E O QUE AQUILO SIGNIFICA
Regra do usuário (2026-09-05, nascida na tela de envio): "rodou há 22 min"
sozinho obriga quem lê a lembrar da regra de cabeça — e na pressa ninguém
lembra. Todo texto de estado traz a medida E a leitura dela.

O QUE NÃO SE DISPARA DAQUI
- O vigia do RIP roda em OUTRO PC. Daqui só dá pra ler o sinal de vida que
  ele deixa no OneDrive — a mesma leitura da tela de envio
  (envio_impressao.estado_do_rip), não uma segunda regra.
- O Monitor de Pastas está CONGELADO por ordem do usuário (2026-09-12): ele
  organiza a pasta de produção. Nenhum botão aqui o religa.
"""
import dataclasses
import datetime
import os
import pathlib
import subprocess

import caminhos

# A pasta de onde as passadas rodam. Vem de caminhos.py: é lá que mora a
# diferença entre rodar do código e rodar do executável.
RAIZ = caminhos.PASTA_PROGRAMA

# Estados de uma tarefa no Agendador (TASK_STATE_*).
_TAREFA_DESLIGADA, _TAREFA_RODANDO = 1, 4

# Até quanto tempo sem rodar um agente "de minuto em minuto" ainda é
# normal, e a partir de quando é defeito. 12 min é a mesma fronteira que o
# RIP já usa ("não conclua que parou antes de uns 12 minutos").
_MINUTO_OK_S = 3 * 60
_MINUTO_PARADO_S = 12 * 60
# Um agente diário tem folga de umas horas: o PC pode ter ligado depois
# das 06:00, e a tarefa roda assim que dá (StartWhenAvailable).
_DIARIO_PARADO_S = 26 * 3600

PASTA_INICIALIZACAO = (pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home()))
                       / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
PASTA_CONGELADO = RAIZ / "_congelado"
ATALHO_MONITOR = "Uny CV - Monitor de Pastas.lnk"


@dataclasses.dataclass(frozen=True)
class Agente:
    chave: str
    nome: str
    faz: str
    onde: str
    # "minuto" / "diario" = tarefa neste PC; "rip" = outro PC; "congelado"
    tipo: str
    tarefa: str | None = None
    # Nomes que a mesma tarefa já teve no Agendador. O painel acha a tarefa
    # por qualquer um deles até alguém reinstalar com o nome novo.
    tarefas_antigas: tuple = ()
    argumentos: tuple = ()
    pode_disparar: bool = True


AGENTES = (
    Agente(
        chave="docan", nome="Vigia das DOCAN (R5200 e H2525)",
        faz="Pega o que chega na fila do OneDrive e entrega nas hot folders das duas "
            "DOCAN — a de rolo e a plana.",
        onde="este PC · a cada 1 min", tipo="minuto",
        tarefa="Vigia DOCAN (SAi)",
        argumentos=("-m", "rasterlink_hotfolder", "--uma-vez", "--posto", "sai"),
    ),
    Agente(
        chave="checklist", nome="Checklist de Produção",
        faz="Regenera a OS de cada cliente com checklist ligado quando algo entra, sai "
            "ou vai pra Prontos na produção dele.",
        onde="este PC · a cada 1 min", tipo="minuto",
        # nasceu presa ao Mercado Livre; desde 2026-09-13 atende todos os
        # clientes do cadastro (clientes.py) e o nome passou a ser genérico
        tarefa="Checklist de Producao",
        tarefas_antigas=("Checklist Producao - Mercado Livre",),
        argumentos=("-m", "vigia_checklist", "--uma-vez"),
    ),
    Agente(
        chave="relatorio", nome="Relatório de Impressão Diária",
        faz="Gera o PDF do que passou nas máquinas nos últimos dias.",
        onde="este PC · todo dia às 06:00", tipo="diario",
        tarefa="Relatorio Producao RIP",
        argumentos=("relatorio_producao.py",),
    ),
    Agente(
        chave="rip", nome="Vigia do RIP (UJV 100 e SWJ320A)",
        faz="Pega a fila do OneDrive e entrega nas hot folders do RasterLink.",
        onde="PC do RIP · a cada 1 min", tipo="rip", pode_disparar=False,
    ),
    Agente(
        chave="monitor", nome="Monitor de Pastas",
        faz="Organizava sozinho a pasta de produção ao ligar o PC.",
        onde="este PC · na inicialização", tipo="congelado", pode_disparar=False,
    ),
)


def agente(chave):
    return next(a for a in AGENTES if a.chave == chave)


# ------------------------------------------------------------ leitura

def quanto_faz(segundos):
    """'40 s' abaixo de um minuto; dali pra cima, a mesma fala da tela de envio."""
    if segundos is None:
        return "?"
    segundos = max(0, segundos)
    if segundos < 60:
        return "%d s" % segundos
    from envio_impressao import _quanto_faz
    return _quanto_faz(segundos / 60)


def _dia_e_hora(quando, agora):
    if quando.date() == agora.date():
        return "hoje às %s" % quando.strftime("%H:%M")
    if quando.date() == agora.date() - datetime.timedelta(days=1):
        return "ontem às %s" % quando.strftime("%H:%M")
    return quando.strftime("%d/%m às %H:%M")


def _data_local(valor):
    """
    O Agendador devolve a hora LOCAL marcada como se fosse UTC. Descarta o
    fuso e fica só com o relógio. "Nunca rodou" vem como 30/12/1899.
    """
    if valor is None:
        return None
    try:
        data = datetime.datetime(valor.year, valor.month, valor.day,
                                 valor.hour, valor.minute, valor.second)
    except (AttributeError, ValueError, TypeError):
        return None
    return data if data.year >= 2000 else None


def traduzir_resultado(codigo):
    """O número cru não diz nada — é a mesma tabela do instalador do RIP."""
    if codigo is None:
        return "sem resultado"
    codigo &= 0xFFFFFFFF
    return {
        0: "deu certo",
        1: "o programa saiu com erro",
        0x41300: "tarefa pronta, nunca rodou",
        0x41301: "rodando agora",
        0x41303: "nunca rodou ainda",
        0x41306: "a tarefa foi encerrada por alguém ou algo",
        0x80070002: "arquivo não encontrado (caminho errado na tarefa)",
        0x80070005: "acesso negado",
        0xC000013A: "o processo foi morto (console fechado ou logoff)",
    }.get(codigo, "código 0x%08X" % codigo)


def _servico_agendador():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    servico = win32com.client.Dispatch("Schedule.Service")
    servico.Connect()
    return servico


def _tarefa_com(nome, servico):
    servico = servico or _servico_agendador()
    try:
        return servico.GetFolder("\\").GetTask(nome)
    except Exception:
        return None


def ler_tarefa(nome, servico=None):
    """
    {'existe', 'habilitada', 'estado', 'ultima', 'resultado', 'proxima'}.
    Nunca levanta: sem conseguir falar com o Agendador devolve
    {'existe': None, 'erro': ...} — "não sei" não é "parado".
    """
    try:
        tarefa = _tarefa_com(nome, servico)
    except Exception as e:
        return {"existe": None, "erro": str(e)}
    if tarefa is None:
        return {"existe": False}
    try:
        return {
            "existe": True,
            "habilitada": bool(tarefa.Enabled),
            "estado": int(tarefa.State),
            "ultima": _data_local(tarefa.LastRunTime),
            "resultado": int(tarefa.LastTaskResult) & 0xFFFFFFFF,
            "proxima": _data_local(tarefa.NextRunTime),
        }
    except Exception as e:
        return {"existe": None, "erro": str(e)}


def classificar_tarefa(ag, tarefa, agora=None):
    """
    Transforma o que o Agendador disse em {'nivel', 'texto'}. Função pura:
    é aqui que mora a regra, e é aqui que os testes olham.

    Níveis: ok · atencao · parado · rodando · sem_sinal
    """
    agora = agora or datetime.datetime.now()

    if not tarefa or tarefa.get("existe") is None:
        return {"nivel": "sem_sinal",
                "texto": "Não consegui ler o Agendador agora — não é \"parado\", é \"não sei\"."}
    if tarefa["existe"] is False:
        return {"nivel": "parado",
                "texto": "A tarefa NÃO EXISTE no Agendador deste PC: não roda sozinha. "
                         "\"Rodar aqui\" faz a passada mesmo assim."}
    if not tarefa["habilitada"] or tarefa["estado"] == _TAREFA_DESLIGADA:
        return {"nivel": "parado",
                "texto": "A tarefa está DESLIGADA no Agendador: não roda sozinha. "
                         "\"Rodar aqui\" faz a passada mesmo assim."}

    ultima = tarefa.get("ultima")
    idade = (agora - ultima).total_seconds() if ultima else None

    if tarefa["estado"] == _TAREFA_RODANDO or tarefa.get("resultado") == 0x41301:
        return {"nivel": "rodando",
                "texto": "Rodando agora%s." % (" (começou há %s)" % quanto_faz(idade) if ultima else "")}
    if ultima is None:
        return {"nivel": "atencao",
                "texto": "A tarefa existe mas nunca rodou. Force um disparo pra ver se ela pega."}

    resultado = tarefa.get("resultado", 0)
    if resultado not in (0, 0x41300, 0x41303):
        return {"nivel": "parado",
                "texto": "A última passada (há %s) terminou com erro: %s. "
                         "\"Rodar aqui\" mostra o que ele diz." % (quanto_faz(idade), traduzir_resultado(resultado))}

    if ag.tipo == "diario":
        if idade <= _DIARIO_PARADO_S:
            proxima = tarefa.get("proxima")
            return {"nivel": "ok",
                    "texto": "Rodou %s e terminou sem erro. Normal — é uma vez por dia%s."
                             % (_dia_e_hora(ultima, agora),
                                "; a próxima é %s" % _dia_e_hora(proxima, agora) if proxima else "")}
        return {"nivel": "parado",
                "texto": "Não roda há %s — devia rodar todo dia às 06:00. Force um disparo."
                         % quanto_faz(idade)}

    if idade <= _MINUTO_OK_S:
        return {"nivel": "ok",
                "texto": "Rodou há %s e terminou sem erro. Normal — ele passa a cada 1 min."
                         % quanto_faz(idade)}
    if idade <= _MINUTO_PARADO_S:
        return {"nivel": "atencao",
                "texto": "Não roda há %s. Ainda pode ser o PC ocupado ou acordando — a partir de "
                         "12 min é defeito. Dá pra forçar um disparo." % quanto_faz(idade)}
    return {"nivel": "parado",
            "texto": "Não roda há %s — isso não é atraso normal. Force um disparo; se não pegar, "
                     "\"Rodar aqui\" mostra o erro." % quanto_faz(idade)}


def estado_monitor():
    """O monitor está onde deveria (congelado) — ou o atalho voltou sozinho?"""
    na_inicializacao = (PASTA_INICIALIZACAO / ATALHO_MONITOR).exists()
    guardado = (PASTA_CONGELADO / ATALHO_MONITOR).exists()
    if na_inicializacao:
        return {"nivel": "atencao",
                "texto": "O atalho VOLTOU pra inicialização do Windows: no próximo boot ele "
                         "organiza a pasta de produção. Se não foi você, tire de lá."}
    if guardado:
        return {"nivel": "congelado",
                "texto": "Congelado a seu pedido — o atalho está guardado em _congelado e "
                         "nada organiza a produção sozinho."}
    return {"nivel": "sem_sinal",
            "texto": "Não achei o atalho nem na inicialização nem em _congelado."}


def nomes_da_tarefa(ag):
    return tuple(n for n in (ag.tarefa, *ag.tarefas_antigas) if n)


def ler_tarefa_do_agente(ag, servico=None):
    """
    Lê a tarefa pelo nome atual e, se ela não existir, pelos antigos.
    Devolve o mesmo dicionário de ler_tarefa, com 'nome' dizendo qual achou.
    """
    primeira = None
    for nome in nomes_da_tarefa(ag):
        tarefa = ler_tarefa(nome, servico)
        if primeira is None:
            primeira = tarefa
        if tarefa.get("existe"):
            return dict(tarefa, nome=nome)
        if tarefa.get("existe") is None:
            return tarefa                   # "não sei" não vira "não existe"
    return primeira or {"existe": False}


def _tarefa_com_do_agente(ag, servico):
    for nome in nomes_da_tarefa(ag):
        tarefa = _tarefa_com(nome, servico)
        if tarefa is not None:
            return tarefa
    return None


def estado(ag, agora=None, servico=None):
    """{'nivel', 'texto'} de um agente, lendo o que for preciso."""
    if ag.tipo == "rip":
        from envio_impressao import estado_do_rip
        r = estado_do_rip(agora=agora)
        return {"nivel": r["nivel"], "texto": r["texto"]}
    if ag.tipo == "congelado":
        return estado_monitor()
    return classificar_tarefa(ag, ler_tarefa_do_agente(ag, servico), agora)


def _ultima_linha(caminho):
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            linhas = [l.strip() for l in f if l.strip()]
        return linhas[-1] if linhas else None
    except OSError:
        return None


def _linha_de_log_legivel(linha, agora):
    """'[2026-09-13 01:48:50] ok    checklist regenerado...' -> 'hoje às 01:48 — checklist regenerado...'"""
    import re
    m = re.match(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+\S+\s+(.*)$", linha)
    if not m:
        return linha
    try:
        quando = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return linha
    return "%s — %s" % (_dia_e_hora(quando, agora), m.group(2).strip())


def _ultima_acao_do_checklist(agora):
    """
    Uma linha por cliente com checklist ligado, com a última coisa que o
    vigia fez pra ele. Cliente ligado cuja produção sumiu é dito com todas
    as letras — senão ele só desapareceria da lista em silêncio.
    """
    import clientes
    import vigia_checklist

    ligados = [c for c in clientes.listar() if c.checklist_ativo]
    if not ligados:
        return "nenhum cliente com checklist ligado — ligue em Clientes"
    partes = []
    for c in ligados:
        if not c.producao_existe:
            partes.append("%s: ⚠ pasta de produção não encontrada" % c.nome)
            continue
        linha = _ultima_linha(vigia_checklist.arquivo_log(c))
        partes.append("%s: %s" % (c.nome, _linha_de_log_legivel(linha, agora) if linha else "nada regenerado ainda"))
    return "  ·  ".join(partes)


def ultima_acao(ag, agora=None):
    """Uma linha com a última coisa concreta que o agente deixou registrada."""
    agora = agora or datetime.datetime.now()
    try:
        if ag.chave == "checklist":
            return _ultima_acao_do_checklist(agora)

        if ag.chave in ("docan", "rip"):
            from rasterlink_hotfolder import ler_sinal_de_vida
            sinal = ler_sinal_de_vida(posto="sai" if ag.chave == "docan" else None, agora=agora)
            if sinal is None:
                return "nenhum sinal de vida gravado ainda"
            maquinas = ", ".join("%s: %s" % (m, erro or "ok") for m, erro in sinal["maquinas"].items())
            linha = "sinal de vida %s — %s" % (_dia_e_hora(sinal["quando"], agora), maquinas or "sem máquinas")
            if sinal.get("registro_pendente"):
                linha += " · %d entrega(s) ainda fora do relatório" % sinal["registro_pendente"]
            return linha

        if ag.chave == "relatorio":
            from rasterlink_hotfolder import PASTA_RELATORIOS
            pdfs = [p for p in pathlib.Path(PASTA_RELATORIOS).rglob("*.pdf")]
            if not pdfs:
                return "nenhum relatório gerado ainda"
            mais_novo = max(pdfs, key=lambda p: p.stat().st_mtime)
            quando = datetime.datetime.fromtimestamp(mais_novo.stat().st_mtime)
            return "último PDF: %s (%s)" % (mais_novo.name, _dia_e_hora(quando, agora))

        if ag.chave == "monitor":
            return "atalho guardado em %s" % (PASTA_CONGELADO / ATALHO_MONITOR)
    except Exception as e:
        return "não consegui ler: %s" % e
    return ""


def pasta_do_agente(ag):
    """A pasta que faz sentido abrir pra conferir o trabalho daquele agente."""
    if ag.chave == "checklist":
        return caminhos.ETIQUETAS_GERADAS
    if ag.chave in ("docan", "rip"):
        from rasterlink_hotfolder import PASTA_FILA_ONEDRIVE
        return PASTA_FILA_ONEDRIVE
    if ag.chave == "relatorio":
        from rasterlink_hotfolder import PASTA_RELATORIOS
        return PASTA_RELATORIOS
    return PASTA_CONGELADO


# ------------------------------------------------------------- ações

def disparar(ag, servico=None, agora=None):
    """
    Pede ao Agendador pra rodar a tarefa AGORA. Devolve (ok, mensagem).
    Nunca levanta.
    """
    agora = agora or datetime.datetime.now()
    if not ag.pode_disparar or not ag.tarefa:
        return False, "Este agente não se dispara daqui."
    try:
        tarefa = _tarefa_com_do_agente(ag, servico)
    except Exception as e:
        return False, "Não consegui falar com o Agendador: %s" % e
    if tarefa is None:
        return False, "A tarefa não existe no Agendador. Use \"Rodar aqui\"."
    try:
        if not tarefa.Enabled:
            return False, "A tarefa está desligada no Agendador. Use \"Rodar aqui\"."
        if int(tarefa.State) == _TAREFA_RODANDO:
            return False, "Ela já está rodando agora — espere terminar."
        tarefa.Run(None)
    except Exception as e:
        return False, "O Agendador recusou o disparo: %s" % e
    return True, "Disparado às %s — o resultado aparece aqui assim que terminar." % agora.strftime("%H:%M:%S")



def rodar_aqui(ag, timeout_s=600, servico=None, executar=subprocess.run):
    """
    Roda a passada do agente direto deste PC e devolve
    {'codigo', 'saida', 'durou_s'} — ou {'recusado': motivo}.

    Recusa quando a tarefa já está rodando pelo Agendador: as passadas têm
    trava, mas não há por que disputar com ela.
    """
    if not ag.pode_disparar or not ag.argumentos:
        return {"recusado": "Este agente não roda daqui."}
    if ag.tarefa:
        tarefa = ler_tarefa_do_agente(ag, servico)
        if tarefa.get("existe") and tarefa.get("estado") == _TAREFA_RODANDO:
            return {"recusado": "Ela está rodando agora pelo Agendador — espere terminar."}

    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    inicio = datetime.datetime.now()
    try:
        r = executar(
            caminhos.comando_python(*ag.argumentos),
            cwd=str(RAIZ), env=ambiente, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"codigo": None, "durou_s": timeout_s,
                "saida": "Passou de %d s sem terminar — abandonei a espera." % timeout_s}
    except OSError as e:
        return {"codigo": None, "durou_s": 0, "saida": "Não consegui iniciar: %s" % e}

    saida = ((r.stdout or "") + (r.stderr or "")).strip()
    return {
        "codigo": r.returncode,
        "durou_s": (datetime.datetime.now() - inicio).total_seconds(),
        "saida": saida or "(terminou sem escrever nada na tela — o que ele faz fica no log dele)",
    }
