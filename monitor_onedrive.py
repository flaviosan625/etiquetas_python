"""
Vigia uma pasta do OneDrive e avisa com notificação do Windows toda vez
que um arquivo for criado, modificado, apagado ou renomeado lá dentro
— pra não "deixar arquivo pra trás" numa pasta que recebe material aos
poucos (ex: pasta de eventos).

Roda separado do sistema de etiquetas — não mexe em nada do
processamento, só observa uma pasta e notifica. Uso: rodar
"python monitor_onedrive.py" (fica rodando até fechar a janela) ou
importar `vigiar()` de outro lugar.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import carregar_config
from producao import (
    varrer_e_organizar_todas, gerar_relatorio_pendencias, abrir_relatorio_pendencias,
    garantir_estrutura_producao, organizar_pasta_producao, NOME_PASTA_PRODUCAO,
)

PASTA_PADRAO = pathlib.Path.home() / "OneDrive" / "UNYCOMUNICACAO" / "EVENTOS"

# Identidade que a notificação usa junto do Windows. Sem um atalho no
# Menu Iniciar registrado com esse mesmo ID (ver _garantir_atalho_
# registrado), o Windows aceita a chamada sem erro nenhum mas nunca
# mostra a notificação — descoberto testando ao vivo (2026-08-30):
# nem um ID inventado nem SetCurrentProcessExplicitAppUserModelID
# sozinho bastam, só funcionou com o atalho de verdade no Menu Iniciar.
_AUMID = "Uny.CV.MonitorDePastas"
_NOME_ATALHO = "Uny CV - Monitor de Pastas.lnk"


def _caminho_pythonw():
    """
    pythonw.exe (sem janela de console) na MESMA instalação/venv que
    está rodando agora — nunca deduzido a partir de os.__file__ (bug
    real: isso calcula certo pra instalação base do Python, mas erra
    num venv, onde os executáveis ficam numa subpasta "Scripts" à
    parte; achado ao vivo, 2026-08-30, o atalho apontava pro Python
    base do sistema, sem watchdog/pywin32 instalados, e morria na hora
    sem aviso nenhum por não ter console pra mostrar o erro).
    """
    caminho = pathlib.Path(sys.executable).parent / "pythonw.exe"
    return caminho if caminho.exists() else pathlib.Path(sys.executable)


def _garantir_atalho_registrado():
    """
    Cria (se ainda não existir) o atalho no Menu Iniciar que registra
    _AUMID junto do Windows — só assim a notificação aparece de
    verdade. Idempotente: não faz nada se o atalho já existe. Nunca
    trava o programa se falhar (falta de permissão, COM indisponível)
    — só a notificação fica sem funcionar, o resto do vigia continua.
    """
    caminho_lnk = pathlib.Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / _NOME_ATALHO
    if caminho_lnk.exists():
        return True

    try:
        import pythoncom
        from win32comext.shell import shell
        from win32com.propsys import propsys, pscon

        python_exe = _caminho_pythonw()
        script = pathlib.Path(__file__).resolve()

        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
        )
        link.SetPath(str(python_exe))
        link.SetArguments(f'"{script}"')
        link.SetDescription("Monitor da pasta de eventos da Uny CV")

        store = link.QueryInterface(propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(_AUMID))
        store.Commit()

        persist = link.QueryInterface(pythoncom.IID_IPersistFile)
        persist.Save(str(caminho_lnk), 0)
        return True
    except Exception:
        return False


def ativar_inicializacao_automatica():
    """
    Cria um atalho na pasta de Inicialização do Windows pra 'vigiar()'
    começar sozinho no login, sem janela visível (pythonw, não
    python). Ação deliberada, chamada só quando o usuário pede — nunca
    automática (mesmo espírito de arquivamento.py, que também só manda
    arquivo com confirmação explícita).
    """
    import pythoncom
    from win32com.client import Dispatch

    pasta_inicializacao = pathlib.Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    caminho_lnk = pasta_inicializacao / _NOME_ATALHO

    python_exe = _caminho_pythonw()
    script = pathlib.Path(__file__).resolve()

    shell = Dispatch("WScript.Shell")
    atalho = shell.CreateShortCut(str(caminho_lnk))
    atalho.TargetPath = str(python_exe)
    atalho.Arguments = f'"{script}"'
    atalho.WorkingDirectory = str(script.parent)
    atalho.Description = "Monitor da pasta de eventos da Uny CV"
    atalho.Save()
    return caminho_lnk


# OneDrive/editores geram arquivo temporário durante sincronização/save
# (ex: "~$relatorio.docx", "arquivo.crdownload") — nunca é o arquivo
# real que importa avisar, só ruído.
_PREFIXOS_IGNORADOS = ("~$", ".~lock")
_SUFIXOS_IGNORADOS = (".tmp", ".crdownload", ".partial")

# Tempo de espera antes de avisar de novo sobre o MESMO caminho: evita
# notificação duplicada quando o Windows dispara vários eventos
# (criado + modificado, várias vezes) pra uma única gravação de
# arquivo. Não atrasa o primeiro aviso — só suprime os repetidos logo
# em seguida.
_JANELA_DEBOUNCE_SEGUNDOS = 2.0


def _deve_ignorar(caminho):
    nome = pathlib.Path(caminho).name
    if nome.startswith(_PREFIXOS_IGNORADOS):
        return True
    if nome.lower().endswith(_SUFIXOS_IGNORADOS):
        return True
    return False


def _mensagem_evento(tipo, caminho, pasta_raiz):
    rotulos = {"criado": "Novo arquivo", "modificado": "Modificado", "apagado": "Apagado"}
    try:
        caminho_relativo = pathlib.Path(caminho).relative_to(pasta_raiz)
    except ValueError:
        caminho_relativo = pathlib.Path(caminho).name
    return f"{rotulos[tipo]}: {caminho_relativo}"


def _mensagem_movido(origem, destino, pasta_raiz):
    destino_relativo = pathlib.Path(destino).relative_to(pasta_raiz)
    try:
        origem_relativa = pathlib.Path(origem).relative_to(pasta_raiz)
        return f"Renomeado/movido: {origem_relativa} -> {destino_relativo}"
    except ValueError:
        return f"Novo arquivo (movido de fora): {destino_relativo}"


class _Handler(FileSystemEventHandler):
    """
    'notificar' e 'agora' são injetáveis pra dar pra testar a lógica
    de debounce/filtro sem precisar de um relógio de verdade nem
    disparar notificação real (ver tests/test_monitor_onedrive.py).
    'carregar_config_fn' é injetável pelo mesmo motivo, pra reagir a
    pasta de produção em teste sem depender do config.json real.
    """

    def __init__(self, pasta_raiz, notificar, agora=time.monotonic, carregar_config_fn=carregar_config):
        self._pasta_raiz = pathlib.Path(pasta_raiz)
        self._notificar = notificar
        self._agora = agora
        self._carregar_config = carregar_config_fn
        self._ultimo_aviso = {}

    def _pronto_pra_avisar(self, caminho):
        marca = self._agora()
        anterior = self._ultimo_aviso.get(caminho)
        self._ultimo_aviso[caminho] = marca
        if anterior is not None and marca - anterior < _JANELA_DEBOUNCE_SEGUNDOS:
            return False
        return True

    def _avisar(self, tipo, caminho):
        if _deve_ignorar(caminho):
            return
        if not self._pronto_pra_avisar(caminho):
            return
        self._notificar(_mensagem_evento(tipo, caminho, self._pasta_raiz))

    def _reagir_producao(self, caminho, eh_diretorio):
        """
        Pedido do usuário (2026-09-03): não precisa esperar reiniciar
        o monitor pra organizar — reage na hora. Pasta nova cujo nome
        começa com "PRODUCAO" (ex: "PRODUCAO 01_09") já ganha a
        estrutura (IMPRESSAO/CORTE/COMPOSTOS + Prontos) na hora que é
        criada; arquivo novo caindo solto direto dentro de uma pasta
        de produção já existente é reorganizado na hora, sem esperar
        próxima vez que o monitor ligar. Nunca estoura erro — reação
        best-effort, não pode derrubar o monitor.
        """
        try:
            caminho = pathlib.Path(caminho)
            if eh_diretorio:
                pasta_producao = caminho if caminho.name.upper().startswith(NOME_PASTA_PRODUCAO) else None
            else:
                pasta_producao = caminho.parent if caminho.parent.name.upper().startswith(NOME_PASTA_PRODUCAO) else None

            if pasta_producao is None:
                return

            config = self._carregar_config()
            if eh_diretorio:
                garantir_estrutura_producao(pasta_producao)
            organizar_pasta_producao(pasta_producao, config)
        except Exception:
            pass

    def on_created(self, event):
        self._reagir_producao(event.src_path, event.is_directory)
        if not event.is_directory:
            self._avisar("criado", event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._avisar("modificado", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._avisar("apagado", event.src_path)

    def on_moved(self, event):
        if event.is_directory or _deve_ignorar(event.dest_path):
            return
        if not self._pronto_pra_avisar(event.dest_path):
            return
        self._notificar(_mensagem_movido(event.src_path, event.dest_path, self._pasta_raiz))


# Título/mensagem NUNCA são embutidos como texto direto no script do
# PowerShell (isso foi o bug real: a biblioteca winotify montava um
# comando gigante com o texto embutido e mandava com stderr descartado
# — qualquer caractere que atrapalhasse a montagem do comando fazia a
# notificação falhar em silêncio total, sem erro nenhum em lugar
# nenhum. Achado testando ao vivo, 2026-08-30). Em vez disso, o texto
# vai pra um arquivo temporário e o PowerShell só lê o arquivo — não
# tem como um caractere do nome de um arquivo real quebrar isso.
_SCRIPT_TOAST = """
$titulo = Get-Content -Raw -Encoding UTF8 "{caminho_titulo}"
$mensagem = Get-Content -Raw -Encoding UTF8 "{caminho_mensagem}"

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$tituloXml = [System.Security.SecurityElement]::Escape($titulo)
$mensagemXml = [System.Security.SecurityElement]::Escape($mensagem)

$template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>$tituloXml</text>
      <text>$mensagemXml</text>
    </binding>
  </visual>
</toast>
"@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{aumid}").Show($toast)
"""


def notificar_windows(mensagem, titulo="Pasta EVENTOS atualizada"):
    _garantir_atalho_registrado()

    with tempfile.TemporaryDirectory() as pasta_tmp:
        caminho_titulo = pathlib.Path(pasta_tmp) / "titulo.txt"
        caminho_mensagem = pathlib.Path(pasta_tmp) / "mensagem.txt"
        caminho_titulo.write_text(titulo, encoding="utf-8")
        caminho_mensagem.write_text(mensagem, encoding="utf-8")

        script = _SCRIPT_TOAST.format(
            caminho_titulo=caminho_titulo, caminho_mensagem=caminho_mensagem, aumid=_AUMID,
        )
        caminho_script = pathlib.Path(pasta_tmp) / "toast.ps1"
        caminho_script.write_text(script, encoding="utf-8")

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        resultado = subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(caminho_script)],
            capture_output=True, startupinfo=si, timeout=15,
        )
        if resultado.returncode != 0:
            raise RuntimeError(f"PowerShell falhou ao notificar: {resultado.stderr.decode('utf-8', 'replace')}")


def vigiar(pasta=None, notificar=notificar_windows, on_status=print):
    """Fica rodando (bloqueia) até Ctrl+C, avisando a cada mudança na pasta (recursivo)."""
    pasta = pathlib.Path(pasta or PASTA_PADRAO)
    if not pasta.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")

    if not _garantir_atalho_registrado():
        on_status(
            "Aviso: não consegui registrar o atalho de notificação — os avisos podem não aparecer. "
            "O resto do vigia continua funcionando normalmente."
        )

    handler = _Handler(pasta, notificar)
    observer = Observer()
    observer.schedule(handler, str(pasta), recursive=True)
    observer.start()
    on_status(f"Vigiando: {pasta} (Ctrl+C pra parar)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        on_status("Parando...")
    finally:
        observer.stop()
        observer.join()


class EstadoVigia:
    """
    Liga/desliga o Observer do watchdog sob demanda — usado pelo ícone
    da bandeja pra dar um jeito fácil de ativar/desativar sem fechar o
    programa. Uma vez parado, um Observer do watchdog não pode ser
    reiniciado (é de uso único), então 'iniciar' sempre cria um
    Observer novo por baixo.
    """

    def __init__(self, pasta, handler):
        self._pasta = pasta
        self._handler = handler
        self._observer = None

    @property
    def ativo(self):
        return self._observer is not None

    def iniciar(self):
        if self._observer is not None:
            return
        observer = Observer()
        observer.schedule(self._handler, str(self._pasta), recursive=True)
        observer.start()
        self._observer = observer

    def parar(self):
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join()
        self._observer = None


def _inicio_do_dia(dias_atras=0):
    """Meia-noite do dia alvo (hoje - dias_atras), como timestamp — usado como corte do relatório."""
    alvo = datetime.now().date() - timedelta(days=dias_atras)
    return datetime.combine(alvo, datetime.min.time()).timestamp()


def gerar_relatorio_atividade(pasta=None, dias=1, data_inicio=None, data_fim=None):
    """
    Lista, agrupado por subpasta de primeiro nível (cliente/evento),
    todo arquivo com data de modificação dentro do período pedido —
    pra dar uma visão rápida de "o que mudou" sem precisar abrir a
    pasta e conferir subpasta por subpasta na mão.

    Por padrão considera os últimos 'dias' dias corridos a partir de
    hoje (1 = só hoje, contado desde meia-noite). Pra um dia específico
    do passado (ex: "o relatório do dia 15/08") ou um intervalo, passe
    'data_inicio' (e opcionalmente 'data_fim' — um único dia se
    omitido) como `datetime.date`; nesse caso 'dias' é ignorado.

    Só reflete o ARQUIVO COMO ESTÁ AGORA (data de modificação) — não
    é um histórico completo de todo evento que já passou (isso exigiria
    o vigia ter ficado rodando o tempo todo, guardando cada evento;
    isso aqui funciona mesmo sobre arquivo que já estava lá antes do
    vigia existir). Por isso também não mostra arquivo apagado.
    """
    pasta = pathlib.Path(pasta or PASTA_PADRAO)

    if data_inicio is not None:
        data_fim = data_fim or data_inicio
        limite_inicio = datetime.combine(data_inicio, datetime.min.time()).timestamp()
        limite_fim = datetime.combine(data_fim, datetime.min.time()).timestamp() + 86400
        periodo = data_inicio.strftime("%d/%m/%Y") if data_fim == data_inicio else (
            f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
        )
    else:
        limite_inicio = _inicio_do_dia(dias_atras=dias - 1)
        limite_fim = None
        periodo = "hoje" if dias == 1 else f"últimos {dias} dias"

    por_subpasta = {}
    for caminho in pasta.rglob("*"):
        if caminho.is_dir() or _deve_ignorar(caminho):
            continue
        try:
            mtime = caminho.stat().st_mtime
        except OSError:
            continue
        if mtime < limite_inicio:
            continue
        if limite_fim is not None and mtime >= limite_fim:
            continue
        relativo = caminho.relative_to(pasta)
        subpasta = relativo.parts[0] if len(relativo.parts) > 1 else "(raiz)"
        por_subpasta.setdefault(subpasta, []).append((mtime, relativo))

    linhas = [f"Relatório de atividade — {periodo}", f"Pasta: {pasta}", ""]

    if not por_subpasta:
        linhas.append("Nenhum arquivo modificado nesse período.")
        return "\n".join(linhas)

    total_arquivos = 0
    for subpasta in sorted(por_subpasta, key=str.lower):
        itens = sorted(por_subpasta[subpasta], reverse=True)
        total_arquivos += len(itens)
        linhas.append(f"{subpasta}  ({len(itens)} arquivo{'s' if len(itens) != 1 else ''})")
        for mtime, relativo in itens:
            hora = datetime.fromtimestamp(mtime).strftime("%d/%m %H:%M")
            linhas.append(f"  [{hora}] {relativo.name}")
        linhas.append("")

    linhas.insert(2, f"{total_arquivos} arquivo{'s' if total_arquivos != 1 else ''} em {len(por_subpasta)} pasta{'s' if len(por_subpasta) != 1 else ''}")
    linhas.insert(3, "")
    return "\n".join(linhas)


def abrir_relatorio_atividade(pasta=None, dias=1, data_inicio=None, data_fim=None):
    """Gera o relatório, salva num arquivo temporário e abre no Bloco de Notas."""
    texto = gerar_relatorio_atividade(pasta, dias, data_inicio, data_fim)
    caminho = pathlib.Path(tempfile.gettempdir()) / f"relatorio_atividade_{datetime.now():%Y%m%d_%H%M%S}.txt"
    caminho.write_text(texto, encoding="utf-8")
    subprocess.Popen(["notepad.exe", str(caminho)])
    return caminho


_NOME_MUTEX = "Uny.CV.MonitorDePastas.InstanciaUnica"
_mutex_instancia = None  # precisa ficar viva até o processo terminar — ver _ja_esta_rodando


def _ja_esta_rodando(nome_mutex=_NOME_MUTEX):
    """
    Trava de instância única via mutex nomeado do Windows — o Windows
    libera esse mutex sozinho quando o processo termina, não importa
    como (crash incluso), então nunca fica "preso" do jeito que um
    arquivo de lock comum ficaria. Achado ao vivo (2026-09-02): o
    atalho de inicialização automática rodou 2x sem ninguém perceber
    (2 pythonw.exe idênticos), consumindo RAM à toa numa máquina que
    já estava com só 0,4GB livre.

    'nome_mutex' só existe pro teste conseguir usar um nome exclusivo
    (nunca o mesmo mutex da instância real rodando de verdade).
    """
    global _mutex_instancia
    import win32api
    import win32event
    import winerror

    _mutex_instancia = win32event.CreateMutex(None, False, nome_mutex)
    return win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS


def _icone_bandeja(alerta=False):
    """
    Ícone simples gerado na hora — sem depender de nenhum arquivo de
    imagem externo. Com 'alerta=True', ganha um selo vermelho no canto
    (pedido do usuário, 2026-09-03: saber de relance se algum cliente
    tem pendência, sem precisar abrir nada).
    """
    from PIL import Image, ImageDraw

    imagem = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    desenho.ellipse((4, 4, 60, 60), fill=(37, 99, 235, 255))
    if alerta:
        desenho.ellipse((40, 2, 62, 24), fill=(220, 38, 38, 255), outline=(255, 255, 255, 255), width=2)
    return imagem


def _tem_pendencia(pasta_eventos):
    """True se algum cliente tiver arquivo fora do Prontos — nunca estoura erro (extra best-effort)."""
    try:
        return bool(gerar_relatorio_pendencias(pasta_eventos))
    except Exception:
        return False


def _monitorar_pendencias_pra_icone(icon, pasta_eventos, intervalo_segundos=300):
    """
    Roda numa thread separada (daemon — some sozinha quando o programa
    fecha) recalculando de tempos em tempos se tem pendência, pra
    manter o ícone da bandeja atualizado mesmo sem nenhum evento de
    arquivo disparar nesse meio tempo.
    """
    estado_anterior = None
    while True:
        tem_pendencia = _tem_pendencia(pasta_eventos)
        if tem_pendencia != estado_anterior:
            try:
                icon.icon = _icone_bandeja(alerta=tem_pendencia)
            except Exception:
                pass
            estado_anterior = tem_pendencia
        time.sleep(intervalo_segundos)


def _organizar_producao_ao_iniciar(pasta_eventos, notificar):
    """
    Varredura de "arrumar tudo que ficou bagunçado enquanto o
    computador estava desligado" (pedido do usuário, 2026-09-03: tem
    funcionário que joga arquivo direto na pasta de madrugada, tudo
    misturado). Roda uma vez, ao iniciar o monitor — nunca decide
    sozinho o que está "pronto" (impresso/cortado), só garante a
    estrutura de pastas (IMPRESSAO/CORTE/COMPOSTOS + Prontos) e separa
    o que caiu solto pra pasta certa (ver producao.py).

    Nunca trava o monitor se der problema (config ilegível, etc.) —
    só a organização automática fica sem rodar dessa vez.
    """
    try:
        config = carregar_config()
        resultado = varrer_e_organizar_todas(pasta_eventos, config)
    except Exception:
        return

    total_movidos = sum(len(r["movidos"]) for r in resultado.values())
    if total_movidos == 0:
        return

    linhas = [f"{cliente}: {len(r['movidos'])} arquivo(s) organizado(s)" for cliente, r in resultado.items() if r["movidos"]]
    try:
        notificar("\n".join(linhas), titulo="Produção organizada automaticamente")
    except Exception:
        pass


def rodar_com_bandeja(pasta=None, notificar=notificar_windows):
    """
    Modo usado quando o programa inicia sozinho com o Windows: fica
    rodando com um ícone na bandeja (perto do relógio) — clique direito
    pra Pausar/Retomar o monitoramento ou Sair, sem precisar de
    terminal nenhum.
    """
    import pystray

    pasta = pathlib.Path(pasta or PASTA_PADRAO)
    if not pasta.exists():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")

    _garantir_atalho_registrado()
    _organizar_producao_ao_iniciar(pasta, notificar)

    handler = _Handler(pasta, notificar)
    vigia = EstadoVigia(pasta, handler)

    def _alternar(icon, item):
        vigia.parar() if vigia.ativo else vigia.iniciar()
        icon.update_menu()

    def _abrir_pasta(icon, item):
        # os.startfile (ShellExecute) depende de COM inicializado na
        # thread que chama — a thread de clique do pystray não
        # inicializa isso, então falhava em silêncio (sem erro visível
        # nenhum, sem console pra mostrar, achado ao vivo 2026-08-30).
        # subprocess com explorer.exe direto não tem essa dependência.
        try:
            subprocess.Popen(["explorer", str(pasta)])
        except Exception as e:
            try:
                notificar("Não consegui abrir a pasta: " + str(e), titulo="Erro")
            except Exception:
                pass

    def _relatorio_hoje(icon, item):
        try:
            abrir_relatorio_atividade(pasta, dias=1)
        except Exception as e:
            try:
                notificar("Não consegui gerar o relatório: " + str(e), titulo="Erro")
            except Exception:
                pass

    def _relatorio_semana(icon, item):
        try:
            abrir_relatorio_atividade(pasta, dias=7)
        except Exception as e:
            try:
                notificar("Não consegui gerar o relatório: " + str(e), titulo="Erro")
            except Exception:
                pass

    def _pendencias_por_cliente(icon, item):
        try:
            abrir_relatorio_pendencias(pasta)
        except Exception as e:
            try:
                notificar("Não consegui gerar o relatório: " + str(e), titulo="Erro")
            except Exception:
                pass

    def _sair(icon, item):
        vigia.parar()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Monitorando", _alternar, checked=lambda item: vigia.ativo),
        pystray.MenuItem("Abrir pasta", _abrir_pasta),
        pystray.MenuItem("Relatório de hoje", _relatorio_hoje),
        pystray.MenuItem("Relatório dos últimos 7 dias", _relatorio_semana),
        pystray.MenuItem("Pendências por cliente", _pendencias_por_cliente),
        pystray.MenuItem("Sair", _sair),
    )
    icon = pystray.Icon(
        "uny_cv_monitor", _icone_bandeja(alerta=_tem_pendencia(pasta)), "Monitor de Pastas - Uny CV", menu,
    )

    thread_pendencias = threading.Thread(
        target=_monitorar_pendencias_pra_icone, args=(icon, pasta), daemon=True,
    )
    thread_pendencias.start()

    vigia.iniciar()
    icon.run()


if __name__ == "__main__":
    if _ja_esta_rodando():
        sys.exit(0)
    rodar_com_bandeja()
