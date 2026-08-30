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
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

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
    """

    def __init__(self, pasta_raiz, notificar, agora=time.monotonic):
        self._pasta_raiz = pathlib.Path(pasta_raiz)
        self._notificar = notificar
        self._agora = agora
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

    def on_created(self, event):
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


def _icone_bandeja():
    """Ícone simples gerado na hora — sem depender de nenhum arquivo de imagem externo."""
    from PIL import Image, ImageDraw

    imagem = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    desenho.ellipse((4, 4, 60, 60), fill=(37, 99, 235, 255))
    return imagem


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

    def _sair(icon, item):
        vigia.parar()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Monitorando", _alternar, checked=lambda item: vigia.ativo),
        pystray.MenuItem("Abrir pasta", _abrir_pasta),
        pystray.MenuItem("Sair", _sair),
    )
    icon = pystray.Icon("uny_cv_monitor", _icone_bandeja(), "Monitor de Pastas - Uny CV", menu)

    vigia.iniciar()
    icon.run()


if __name__ == "__main__":
    rodar_com_bandeja()
