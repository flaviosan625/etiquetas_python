#!/usr/bin/env python3
"""
Orquestrador Multiplataforma de Empacotamento e Build de Distribuição.
AutoPrint Automation - Comunicação Visual (ISSUE-15).

Responsabilidades:
- Limpeza de diretórios temporários e de saída (build/, dist/).
- Verificação de dependências essenciais do ecossistema (PySide6, Pillow, cryptography, etc.).
- Construção de manifesto de arquivos necessários (assets, esquemas SQL, fontes, ícones).
- Filtragem rígida de arquivos temporários, caches (.pyc, __pycache__), logs e segredos.
- Suporte a múltiplos motores de compilação: Nuitka (--engine=nuitka) e PyInstaller (--engine=pyinstaller).
- Modo dry-run para inspeção de comandos e validações em CI/CD e testes unitários.
"""

import argparse
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

# Constantes de Build e Metadados do Produto
NOME_APLICACAO = "AutoPrint Automation"
EMPRESA_PADRAO = "Comunicação Visual"
VERSAO_PADRAO = "2.0.0"
EXECUTAVEL_PADRAO = "AutoPrint.exe" if sys.platform == "win32" else "AutoPrint"

DIRETORIOS_LIMPEZA = ["build", "dist"]

DEPENDENCIAS_ESSENCIAIS = [
    "PySide6",
    "PIL",             # Pillow
    "cryptography",
    "fitz",            # PyMuPDF
    "openpyxl",
]

# Dependências opcionais ou específicas de plataforma
DEPENDENCIAS_OPCIONAIS = [
    "win32api",        # pywin32 (somente Windows)
    "watchdog",
]

# Padrões e arquivos estritamente proibidos no manifesto final de distribuição
PADROES_IGNORADOS: Set[str] = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".continue",
    ".claude",
    ".google",
    "__pycache__",
    "build",
    "dist",
}

EXTENSOES_IGNORADAS: Set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".tmp",
    ".log",
    ".lock",
    ".env",
    ".bak",
    ".swp",
}

ARQUIVOS_SENSIVEIS: Set[str] = {
    ".env",
    "registro_pendente.jsonl",
    "_aviso_fila.json",
    "_aviso_sinal.json",
    "rasterlink_hotfolder.log",
    "rasterlink_hotfolder_crash.log",
    "rasterlink_hotfolder_sai.lock",
}


def obter_raiz_projeto(caminho_base: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Retorna o diretório raiz absoluto do projeto."""
    if caminho_base is not None:
        return pathlib.Path(caminho_base).resolve()
    return pathlib.Path(__file__).resolve().parent.parent


def limpar_diretorios(
    diretorios: Optional[List[str]] = None,
    raiz: Optional[pathlib.Path] = None,
) -> List[str]:
    """
    Remove recursivamente diretórios temporários e de compilação.
    Retorna a lista dos diretórios efetivamente limpos/removidos.
    """
    base = obter_raiz_projeto(raiz)
    alvos = diretorios if diretorios is not None else DIRETORIOS_LIMPEZA
    removidos = []

    for nome in alvos:
        caminho = base / nome
        if caminho.exists():
            if caminho.is_dir():
                shutil.rmtree(caminho, ignore_errors=True)
            else:
                caminho.unlink(missing_ok=True)
            removidos.append(nome)

    return removidos


def verificar_dependencias(
    essenciais: Optional[List[str]] = None,
) -> Tuple[bool, Dict[str, bool]]:
    """
    Verifica a presença de módulos essenciais no ambiente Python corrente.
    Retorna uma tupla (todas_presentes, dicionario_status).
    """
    pacotes = essenciais if essenciais is not None else DEPENDENCIAS_ESSENCIAIS
    status: Dict[str, bool] = {}

    for pacote in pacotes:
        # Se for no windows e pywin32, mapear win32api se solicitado
        spec = importlib.util.find_spec(pacote)
        status[pacote] = spec is not None

    todas_ok = all(status.values())
    return todas_ok, status


def eh_arquivo_valido_dist(caminho: pathlib.Path, raiz: pathlib.Path) -> bool:
    """
    Avalia se um arquivo é elegível para compor o manifesto de build,
    garantindo a exclusão de lixo, caches, logs, segredos e pastas de teste.
    """
    rel = caminho.relative_to(raiz)
    partes = rel.parts

    # Verifica se qualquer parte do caminho pertence aos diretórios proibidos
    for p in partes:
        if p in PADROES_IGNORADOS:
            return False
        if p.startswith((".", "_codex_", "_tmp_", "tmp_")):
            return False

    # Extensão
    if caminho.suffix.lower() in EXTENSOES_IGNORADAS:
        return False

    # Arquivos sensíveis ou temporários por nome exato
    nome_lower = caminho.name.lower()
    if nome_lower in ARQUIVOS_SENSIVEIS:
        return False
    if "secret" in nome_lower or "password" in nome_lower or "token" in nome_lower:
        return False

    return True


def obter_manifesto_arquivos(
    raiz: Optional[pathlib.Path] = None,
) -> Dict[str, List[pathlib.Path]]:
    """
    Coleta e organiza os arquivos necessários para o pacote de distribuição:
    - assets: imagens, logos, ícones, termos de uso
    - banco: esquema SQL e migrações
    - fontes: módulos python essenciais da raiz e subpacotes
    - configs: templates de configuração necessários
    """
    base = obter_raiz_projeto(raiz)
    manifesto: Dict[str, List[pathlib.Path]] = {
        "assets": [],
        "banco": [],
        "codigo": [],
        "documentos": [],
    }

    # 1. Assets
    pasta_assets = base / "assets"
    if pasta_assets.exists():
        for arq in sorted(pasta_assets.rglob("*")):
            if arq.is_file() and eh_arquivo_valido_dist(arq, base):
                manifesto["assets"].append(arq)

    # 2. Banco e esquemas
    pasta_banco = base / "banco"
    if pasta_banco.exists():
        for arq in sorted(pasta_banco.rglob("*")):
            if arq.is_file() and eh_arquivo_valido_dist(arq, base):
                manifesto["banco"].append(arq)

    # 3. Código fonte principal e subpastas de negócio
    pastas_codigo = ["ui", "motor_pdf", "licenciamento", "hardware", "ferramentas"]
    for sub in pastas_codigo:
        p = base / sub
        if p.exists():
            for arq in sorted(p.rglob("*.py")):
                if arq.is_file() and eh_arquivo_valido_dist(arq, base):
                    manifesto["codigo"].append(arq)

    # Arquivos .py soltos na raiz
    for arq in sorted(base.glob("*.py")):
        if arq.is_file() and eh_arquivo_valido_dist(arq, base):
            manifesto["codigo"].append(arq)

    return manifesto


def montar_comando_nuitka(
    entrypoint: str = "main.py",
    output_dir: str = "dist",
    company_name: str = EMPRESA_PADRAO,
    product_name: str = NOME_APLICACAO,
    file_version: str = VERSAO_PADRAO,
    product_version: str = VERSAO_PADRAO,
    icon_path: str = "assets/icone.ico",
    data_dir: str = "assets=assets",
    plugin: str = "pyside6",
    disable_console: bool = True,
    standalone: bool = True,
    extra_flags: Optional[List[str]] = None,
    raiz: Optional[pathlib.Path] = None,
) -> List[str]:
    """Monta os argumentos de linha de comando para o Nuitka."""
    base = obter_raiz_projeto(raiz)
    cmd = [sys.executable, "-m", "nuitka"]

    if standalone:
        cmd.append("--standalone")

    if disable_console:
        cmd.append("--windows-disable-console")

    if plugin:
        cmd.append(f"--enable-plugin={plugin}")

    cmd.append(f"--output-dir={output_dir}")

    # Checa ícone
    full_icon = base / icon_path
    if full_icon.exists():
        cmd.append(f"--windows-icon-from-ico={icon_path}")
    elif (base / "assets/uny_cv.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/uny_cv.ico")

    cmd.append(f"--include-data-dir={data_dir}")

    # Esquema SQL do banco
    if (base / "banco" / "esquema.sql").exists():
        cmd.append("--include-data-file=banco/esquema.sql=banco/esquema.sql")

    # Metadados
    cmd.append(f'--windows-company-name="{company_name}"')
    cmd.append(f'--windows-product-name="{product_name}"')
    cmd.append(f'--windows-file-version="{file_version}"')
    cmd.append(f'--windows-product-version="{product_version}"')

    if extra_flags:
        cmd.extend(extra_flags)

    cmd.append(entrypoint)
    return cmd


def montar_comando_pyinstaller(
    entrypoint: str = "main.py",
    output_dir: str = "dist",
    name: str = "AutoPrint",
    icon_path: str = "assets/icone.ico",
    disable_console: bool = True,
    extra_flags: Optional[List[str]] = None,
    raiz: Optional[pathlib.Path] = None,
) -> List[str]:
    """Monta os argumentos de linha de comando para o PyInstaller."""
    base = obter_raiz_projeto(raiz)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        f"--distpath={output_dir}",
        f"--name={name}",
    ]

    if disable_console:
        cmd.append("--windowed")
    else:
        cmd.append("--console")

    full_icon = base / icon_path
    if full_icon.exists():
        cmd.append(f"--icon={icon_path}")
    elif (base / "assets/uny_cv.ico").exists():
        cmd.append("--icon=assets/uny_cv.ico")

    # Separador de add-data no Windows é ';' e no Linux/macOS é ':'
    sep = ";" if sys.platform == "win32" else ":"

    if (base / "assets").exists():
        cmd.append(f"--add-data=assets{sep}assets")

    if (base / "banco" / "esquema.sql").exists():
        cmd.append(f"--add-data=banco/esquema.sql{sep}banco")

    if extra_flags:
        cmd.extend(extra_flags)

    cmd.append(entrypoint)
    return cmd


def executar_build(
    engine: str = "nuitka",
    clean: bool = True,
    dry_run: bool = False,
    skip_deps: bool = False,
    entrypoint: str = "main.py",
    output_dir: str = "dist",
    version: str = VERSAO_PADRAO,
    raiz: Optional[pathlib.Path] = None,
) -> bool:
    """Orquestra o ciclo completo de build e retorna se foi bem-sucedido."""
    base = obter_raiz_projeto(raiz)
    print("=" * 60)
    print(f" Orquestrador de Build: {NOME_APLICACAO} v{version}")
    print(f" Motor selecionado: {engine.upper()}")
    print("=" * 60)

    # 1. Limpeza prévia
    if clean:
        print("\n--> [1/4] Limpando diretórios temporários e de saída...")
        removidos = limpar_diretorios(raiz=base)
        print(f"    Diretórios limpos: {removidos if removidos else 'nenhum'}")

    # 2. Verificação de dependências
    print("\n--> [2/4] Verificando dependências do ambiente...")
    if not skip_deps:
        todas_ok, status_deps = verificar_dependencias()
        for dep, ok in status_deps.items():
            simbolo = "✓" if ok else "✗"
            print(f"    [{simbolo}] {dep}")
        if not todas_ok and not dry_run:
            print("\n❌ ERRO: Dependências obrigatórias estão ausentes no ambiente.")
            return False
    else:
        print("    [!] Verificação de dependências ignorada (--skip-deps).")

    # 3. Montagem do manifesto
    print("\n--> [3/4] Coletando manifesto de arquivos...")
    manifesto = obter_manifesto_arquivos(base)
    total_arquivos = sum(len(lista) for lista in manifesto.values())
    print(f"    Assets:      {len(manifesto['assets'])} arquivo(s)")
    print(f"    Banco/SQL:   {len(manifesto['banco'])} arquivo(s)")
    print(f"    Código py:   {len(manifesto['codigo'])} arquivo(s)")
    print(f"    Total geral: {total_arquivos} arquivo(s) elegíveis no manifesto.")

    # 4. Montagem do comando e disparo
    print("\n--> [4/4] Montando comando de compilação...")
    if engine.lower() == "nuitka":
        cmd = montar_comando_nuitka(
            entrypoint=entrypoint,
            output_dir=output_dir,
            file_version=version,
            product_version=version,
            raiz=base,
        )
    elif engine.lower() == "pyinstaller":
        cmd = montar_comando_pyinstaller(
            entrypoint=entrypoint,
            output_dir=output_dir,
            raiz=base,
        )
    else:
        print(f"❌ Motor desconhecido: {engine}. Escolha 'nuitka' ou 'pyinstaller'.")
        return False

    print("    Comando gerado:")
    print("    " + " ".join(cmd))

    if dry_run:
        print("\n[DRY RUN] Validação do orquestrador concluída com sucesso! Processo não executado.")
        return True

    print(f"\n--> Iniciando execução via {engine.upper()}...")
    resultado = subprocess.run(cmd, cwd=base)
    if resultado.returncode == 0:
        print(f"\n✅ Build concluído com sucesso! Saída gerada em: {base / output_dir}")
        return True
    else:
        print(f"\n❌ Falha no build ({engine}). Código de retorno: {resultado.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description=f"Orquestrador de Build Multiplataforma - {NOME_APLICACAO}"
    )
    parser.add_argument(
        "--engine",
        choices=["nuitka", "pyinstaller"],
        default="nuitka",
        help="Motor de compilação a utilizar (padrão: nuitka)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=True,
        help="Limpa diretórios build/ e dist/ antes de compilar (padrão: True)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_false",
        dest="clean",
        help="Não limpa diretórios antes de compilar",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida o ambiente, dependências e manifesto sem executar compilação",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Pula a validação de dependências instaladas",
    )
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Diretório de saída dos binários (padrão: dist)",
    )
    parser.add_argument(
        "--entrypoint",
        default="main.py",
        help="Script de ponto de entrada (padrão: main.py)",
    )
    parser.add_argument(
        "--version",
        default=VERSAO_PADRAO,
        help=f"Versão do executável (padrão: {VERSAO_PADRAO})",
    )

    args = parser.parse_args()
    sucesso = executar_build(
        engine=args.engine,
        clean=args.clean,
        dry_run=args.dry_run,
        skip_deps=args.skip_deps,
        entrypoint=args.entrypoint,
        output_dir=args.output_dir,
        version=args.version,
    )
    sys.exit(0 if sucesso else 1)


if __name__ == "__main__":
    main()
