"""
Uma regra so, sobre os .ps1 do projeto: eles TEM que comecar com BOM.

Por que isso vira teste em vez de ficar so na cabeca de alguem: sem BOM,
o PowerShell 5.1 (o que vem no Windows) le o arquivo como ANSI, e cada
acento vira dois ou tres caracteres. O travessao '—' em particular vira
uma sequencia terminada em '"' — aspa curva, que o PowerShell ACEITA
como aspa de verdade. Ela fecha a string no meio e desmonta o bloco
inteiro.

Aconteceu aqui em 2026-09-07: o instalar_tarefa.ps1 da maquina do SAi
morreu com "'}' de fechamento ausente" numa linha que estava perfeita —
a culpada estava duas linhas abaixo, invisivel. E o script so quebra na
mao do usuario, porque e ele quem roda como administrador.

Todo texto que aparece pra quem roda esses scripts e em portugues, entao
acento nao e evitavel. O BOM e.
"""
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"


def _scripts_powershell():
    return sorted(p for p in RAIZ.rglob("*.ps1") if ".venv" not in p.parts)


def test_existe_pelo_menos_um_script_pra_conferir():
    """Se um dia a busca parar de achar nada, o teste abaixo passaria vazio e calado."""
    assert _scripts_powershell()


@pytest.mark.parametrize("caminho", _scripts_powershell(), ids=lambda p: p.name)
def test_ps1_comeca_com_bom(caminho):
    inicio = caminho.read_bytes()[:3]
    assert inicio == BOM, (
        f"{caminho.relative_to(RAIZ)} esta sem BOM. O PowerShell 5.1 vai ler os acentos "
        f"como ANSI e pode quebrar o script com erro de sintaxe numa linha inocente. "
        f"Conserto: reescrever com encoding='utf-8-sig'."
    )


@pytest.mark.parametrize("caminho", _scripts_powershell(), ids=lambda p: p.name)
def test_ps1_e_utf8_valido(caminho):
    """BOM certo mas bytes quebrados seria o mesmo estrago, so que mais dificil de ver."""
    try:
        caminho.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        pytest.fail(f"{caminho.relative_to(RAIZ)} nao e UTF-8 valido: {e}")


@pytest.mark.parametrize("caminho", sorted(p for p in RAIZ.rglob("*.bat") if ".venv" not in p.parts),
                         ids=lambda p: p.name)
def test_bat_nao_tem_acento(caminho):
    """
    O contrario dos .ps1: .bat depende da pagina de codigo do console, e
    acento ali vira lixo na tela mesmo com chcp. A convencao do projeto
    (ver maquina_rip/instalar_tarefa.bat) e escrever os .bat sem acento
    nenhum e deixar o texto bonito pro .ps1 que eles chamam.
    """
    texto = caminho.read_bytes().decode("utf-8", errors="replace")
    acentuados = sorted({c for c in texto if ord(c) > 127})
    assert not acentuados, (
        f"{caminho.relative_to(RAIZ)} tem caractere fora do ASCII: {acentuados}. "
        f"Escreva a mensagem sem acento, ou mova o texto pro .ps1."
    )
