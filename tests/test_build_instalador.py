"""
Testes unitários e de integração para a infraestrutura de compilação e instalador (ISSUE-15).

Valida:
1. Sintaxe, diretivas e seções obrigatórias de scripts/instalador.iss (Inno Setup 6).
2. Codificação (UTF-8 com BOM), sintaxe PowerShell e flags obrigatórias de scripts/compilar_nuitka.ps1.
3. Detecção de diretórios, assets, ícones e esquemas pelo scripts/build_dist.py.
4. Exclusão estrita de arquivos temporários, caches (.pyc), logs e segredos do manifesto de build.
5. Geração de comandos para os motores Nuitka e PyInstaller.
"""

import pathlib
import re
import subprocess
import sys

import pytest

# Adiciona scripts ao sys.path para importação direta de build_dist
RAIZ_PROJETO = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = RAIZ_PROJETO / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_dist


# =============================================================================
# 1. TESTES DO SCRIPT INNO SETUP (scripts/instalador.iss)
# =============================================================================

@pytest.fixture
def conteudo_iss() -> str:
    caminho = SCRIPTS_DIR / "instalador.iss"
    assert caminho.exists(), f"Arquivo não encontrado: {caminho}"
    return caminho.read_text(encoding="utf-8")


def test_instalador_iss_arquivo_existe():
    """Garante a existência do script Inno Setup no diretório scripts/."""
    caminho = SCRIPTS_DIR / "instalador.iss"
    assert caminho.is_file()
    assert caminho.stat().st_size > 0


def test_instalador_iss_definicoes_obrigatorias(conteudo_iss: str):
    """Valida as 4 diretivas fundamentais de metadados exigidas na ISSUE-15."""
    assert '#define MyAppName "AutoPrint Automation"' in conteudo_iss
    assert '#define MyAppVersion "2.0.0"' in conteudo_iss
    assert '#define MyAppPublisher "Soluções Gráficas"' in conteudo_iss
    assert '#define MyAppExeName "AutoPrint.exe"' in conteudo_iss


def test_instalador_iss_secoes_obrigatorias(conteudo_iss: str):
    """Garante que todas as seções padrão do Inno Setup 6 estejam presentes."""
    secoes_esperadas = [
        "[Setup]",
        "[Languages]",
        "[Tasks]",
        "[Files]",
        "[Icons]",
        "[Run]",
        "[UninstallDelete]",
    ]
    for secao in secoes_esperadas:
        assert secao in conteudo_iss, f"Seção obrigatória ausente no instalador.iss: {secao}"


def test_instalador_iss_configuracoes_setup(conteudo_iss: str):
    """Valida caminhos, estilo moderno e permissões da seção [Setup]."""
    assert "DefaultDirName={autopf}\\{#MyAppName}" in conteudo_iss
    assert "WizardStyle=modern" in conteudo_iss
    assert "PrivilegesRequired=lowest" in conteudo_iss
    assert "PrivilegesRequiredOverridesAllowed=dialog" in conteudo_iss
    assert "UninstallDisplayIcon={app}\\{#MyAppExeName}" in conteudo_iss
    assert "LicenseFile=..\\assets\\termos_de_uso.txt" in conteudo_iss


def test_instalador_iss_atalhos_e_execucao(conteudo_iss: str):
    """Verifica criação de atalhos e checkbox pós-instalação para execução."""
    # Atalho Desktop
    assert '{autodesktop}\\{#MyAppName}' in conteudo_iss
    # Atalho Menu Iniciar
    assert '{autoprograms}\\{#MyAppName}\\{#MyAppName}' in conteudo_iss
    # Desinstalador no menu
    assert '{uninstallexe}' in conteudo_iss
    # Execução opcional ao finalizar
    assert 'Filename: "{app}\\{#MyAppExeName}"' in conteudo_iss
    assert 'postinstall' in conteudo_iss


def test_instalador_iss_limpeza_desinstalacao(conteudo_iss: str):
    """Verifica que a desinstalação limpa resíduos gerados durante o uso."""
    assert '{app}\\__pycache__' in conteudo_iss
    assert '{app}\\*.log' in conteudo_iss
    assert '{app}\\*.tmp' in conteudo_iss
    assert 'Type: dirifempty; Name: "{app}"' in conteudo_iss


# =============================================================================
# 2. TESTES DO SCRIPT POWERSHELL NUITKA (scripts/compilar_nuitka.ps1)
# =============================================================================

@pytest.fixture
def conteudo_ps1() -> str:
    caminho = SCRIPTS_DIR / "compilar_nuitka.ps1"
    assert caminho.exists(), f"Arquivo não encontrado: {caminho}"
    return caminho.read_text(encoding="utf-8-sig")


def test_compilar_nuitka_ps1_existe():
    """Garante a existência do script PowerShell em scripts/."""
    caminho = SCRIPTS_DIR / "compilar_nuitka.ps1"
    assert caminho.is_file()
    assert caminho.stat().st_size > 0


def test_compilar_nuitka_ps1_bom_e_utf8():
    """
    Regra do projeto: todos os .ps1 DEVEM iniciar com UTF-8 BOM (\xef\xbb\xbf)
    para compatibilidade com PowerShell 5.1 no Windows sem quebra de acentuação.
    """
    caminho = SCRIPTS_DIR / "compilar_nuitka.ps1"
    raw_bytes = caminho.read_bytes()
    assert raw_bytes[:3] == b"\xef\xbb\xbf", "compilar_nuitka.ps1 deve iniciar com UTF-8 BOM."
    # Testa decodificação limpa
    texto = raw_bytes.decode("utf-8-sig")
    assert "AutoPrint Automation" in texto


def test_compilar_nuitka_ps1_flags_obrigatorias(conteudo_ps1: str):
    """Valida presença de todas as flags e parâmetros exigidos pela ISSUE-15."""
    flags_obrigatorias = [
        "--standalone",
        "--windows-disable-console",
        "--enable-plugin=",
        "--output-dir=",
        "--windows-icon-from-ico=",
        "--include-data-dir=",
        "--windows-company-name=",
        "--windows-product-name=",
        "--windows-file-version=",
    ]
    for flag in flags_obrigatorias:
        assert flag in conteudo_ps1, f"Flag obrigatória ausente em compilar_nuitka.ps1: {flag}"

    # Valida strings literais padrão
    assert "Comunicação Visual" in conteudo_ps1
    assert "AutoPrint Automation" in conteudo_ps1
    assert "2.0.0" in conteudo_ps1


def test_compilar_nuitka_ps1_verificacao_compilador_e_nuitka(conteudo_ps1: str):
    """Verifica que o script possui rotinas de diagnóstico para C++/MSVC e Nuitka."""
    assert "cl.exe" in conteudo_ps1 or "vswhere" in conteudo_ps1
    assert "nuitka" in conteudo_ps1.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell disponível nativamente no Windows")
def test_compilar_nuitka_ps1_sintaxe_e_dryrun():
    """Executa o script com -DryRun no PowerShell para assegurar integridade sintática."""
    caminho_ps1 = SCRIPTS_DIR / "compilar_nuitka.ps1"
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(caminho_ps1),
        "-DryRun",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=RAIZ_PROJETO)
    assert res.returncode == 0, f"Erro na execução de compilar_nuitka.ps1:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "[DRY RUN]" in res.stdout
    assert "AutoPrint Automation" in res.stdout


# =============================================================================
# 3. TESTES DO ORQUESTRADOR PYTHON (scripts/build_dist.py)
# =============================================================================

def test_build_dist_verificar_dependencias():
    """Valida a checagem de dependências essenciais do ecossistema."""
    todas_ok, status = build_dist.verificar_dependencias()
    assert isinstance(status, dict)
    for dep in ["PySide6", "PIL", "cryptography", "fitz", "openpyxl"]:
        assert dep in status
        assert status[dep] is True, f"Dependência essencial {dep} deveria estar instalada no venv."
    assert todas_ok is True


def test_build_dist_detecta_diretorios_e_assets():
    """Valida que o orquestrador localiza assets, esquemas SQL e arquivos de código."""
    manifesto = build_dist.obter_manifesto_arquivos(RAIZ_PROJETO)
    assert "assets" in manifesto
    assert "banco" in manifesto
    assert "codigo" in manifesto

    # Assets essenciais
    nomes_assets = [p.name for p in manifesto["assets"]]
    assert any(n.endswith(".ico") for n in nomes_assets), "Deveria detectar arquivo .ico em assets."
    assert any(n.endswith(".png") for n in nomes_assets), "Deveria detectar imagens PNG em assets."

    # Banco / Schema
    nomes_banco = [p.name for p in manifesto["banco"]]
    assert "esquema.sql" in nomes_banco, "Deveria detectar banco/esquema.sql."

    # Código
    nomes_codigo = [p.name for p in manifesto["codigo"]]
    assert "main.py" in nomes_codigo, "Deveria incluir main.py no código."
    assert "app.py" in nomes_codigo, "Deveria incluir ui/app.py no código."


def test_build_dist_manifesto_nao_contem_lixo_ou_segredos():
    """Garante que caches, arquivos temporários, logs e arquivos sensíveis são filtrados."""
    manifesto = build_dist.obter_manifesto_arquivos(RAIZ_PROJETO)
    todos_arquivos = []
    for lista in manifesto.values():
        todos_arquivos.extend(lista)

    for arq in todos_arquivos:
        partes = arq.parts
        assert "__pycache__" not in partes, f"Arquivo de cache detectado no manifesto: {arq}"
        assert ".pytest_cache" not in partes, f"Cache de teste detectado: {arq}"
        assert ".venv" not in partes, f"Arquivo da venv detectado: {arq}"
        assert ".git" not in partes, f"Arquivo git detectado: {arq}"
        assert not arq.name.startswith(".tmp"), f"Arquivo temporário detectado: {arq}"
        assert not arq.suffix.lower() in [".pyc", ".pyo", ".log", ".lock"], f"Extensão proibida: {arq}"

        nome_lower = arq.name.lower()
        assert "secret" not in nome_lower, f"Possível segredo detectado: {arq}"
        assert nome_lower not in ["registro_pendente.jsonl", "_aviso_fila.json"]


def test_build_dist_filtro_eh_arquivo_valido_dist(tmp_path):
    """Testa diretamente a função de filtragem com arquivos sintéticos variados."""
    raiz = tmp_path

    # Casos válidos
    f_valido1 = raiz / "assets" / "icone.ico"
    f_valido2 = raiz / "ui" / "janela.py"
    f_valido3 = raiz / "banco" / "esquema.sql"

    # Casos proibidos
    f_pyc = raiz / "ui" / "__pycache__" / "janela.cpython-312.pyc"
    f_log = raiz / "app.log"
    f_lock = raiz / "processo.lock"
    f_git = raiz / ".git" / "HEAD"
    f_venv = raiz / ".venv" / "pyvenv.cfg"
    f_tmp_dir = raiz / ".tmp_teste" / "relatorio.pdf"
    f_env = raiz / ".env"
    f_secret = raiz / "jwt_secret_token.txt"

    assert build_dist.eh_arquivo_valido_dist(f_valido1, raiz) is True
    assert build_dist.eh_arquivo_valido_dist(f_valido2, raiz) is True
    assert build_dist.eh_arquivo_valido_dist(f_valido3, raiz) is True

    assert build_dist.eh_arquivo_valido_dist(f_pyc, raiz) is False
    assert build_dist.eh_arquivo_valido_dist(f_log, raiz) is False
    assert build_dist.eh_arquivo_valido_dist(f_lock, raiz) is False
    assert build_dist.eh_arquivo_valido_dist(f_git, raiz) is False
    assert build_dist.eh_arquivo_valido_dist(f_venv, raiz) is False
    assert build_dist.eh_arquivo_valido_dist(f_tmp_dir, raiz) is False
    assert build_dist.eh_arquivo_valido_dist(f_env, raiz) is False
    assert build_dist.eh_arquivo_valido_dist(f_secret, raiz) is False


def test_build_dist_montar_comando_nuitka():
    """Valida os parâmetros do comando Nuitka gerados pelo orquestrador."""
    cmd = build_dist.montar_comando_nuitka(
        entrypoint="main.py",
        output_dir="dist",
        company_name="Comunicação Visual",
        product_name="AutoPrint Automation",
        file_version="2.0.0",
        product_version="2.0.0",
        raiz=RAIZ_PROJETO,
    )
    cmd_str = " ".join(cmd)
    assert "-m nuitka" in cmd_str
    assert "--standalone" in cmd_str
    assert "--windows-disable-console" in cmd_str
    assert "--enable-plugin=pyside6" in cmd_str
    assert "--output-dir=dist" in cmd_str
    assert "--windows-company-name=\"Comunicação Visual\"" in cmd_str
    assert "--windows-product-name=\"AutoPrint Automation\"" in cmd_str
    assert "--windows-file-version=\"2.0.0\"" in cmd_str
    assert cmd[-1] == "main.py"


def test_build_dist_montar_comando_pyinstaller():
    """Valida os parâmetros do comando PyInstaller gerados pelo orquestrador."""
    cmd = build_dist.montar_comando_pyinstaller(
        entrypoint="main.py",
        output_dir="dist",
        name="AutoPrint",
        raiz=RAIZ_PROJETO,
    )
    cmd_str = " ".join(cmd)
    assert "-m PyInstaller" in cmd_str
    assert "--onedir" in cmd_str
    assert "--windowed" in cmd_str
    assert "--name=AutoPrint" in cmd_str
    assert "--distpath=dist" in cmd_str
    assert cmd[-1] == "main.py"


def test_build_dist_limpar_diretorios(tmp_path):
    """Testa a remoção de diretórios temporários e de saída."""
    build_dir = tmp_path / "build"
    dist_dir = tmp_path / "dist"
    build_dir.mkdir()
    dist_dir.mkdir()
    (build_dir / "temp.obj").write_text("dummy")
    (dist_dir / "app.exe").write_text("dummy")

    assert build_dir.exists()
    assert dist_dir.exists()

    removidos = build_dist.limpar_diretorios(["build", "dist"], raiz=tmp_path)
    assert "build" in removidos
    assert "dist" in removidos
    assert not build_dir.exists()
    assert not dist_dir.exists()


def test_build_dist_executar_build_dry_run():
    """Testa o ciclo de build completo em modo dry-run para ambos os motores."""
    ok_nuitka = build_dist.executar_build(engine="nuitka", dry_run=True, raiz=RAIZ_PROJETO)
    assert ok_nuitka is True

    ok_pyinstaller = build_dist.executar_build(engine="pyinstaller", dry_run=True, raiz=RAIZ_PROJETO)
    assert ok_pyinstaller is True
