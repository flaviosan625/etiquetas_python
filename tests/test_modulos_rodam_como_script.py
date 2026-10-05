"""
O que o teste NÃO pega quando só importa o módulo.

Em 05/10/2026 a tarefa "Checklist de Produção" falhava a cada passada,
de minuto em minuto, com `NameError: name '_montar_artes' is not
defined` — e a montagem automática nunca tinha rodado uma vez sequer.
A função estava definida DEPOIS do `if __name__ == "__main__":`, então
rodando como script (`python -m vigia_checklist`) o bloco principal
executava antes de a `def` ser alcançada.

Nenhum teste pegou isso, e não era descuido: teste IMPORTA o módulo, e
na importação o arquivo roda inteiro — todas as `def` existem, o bloco
`__main__` não executa, e `passada()` chamada direto funciona. O defeito
só aparece pelo caminho que nenhum teste usava: a linha de comando.

O erro ficou escondido mais ainda porque ele acontece DEPOIS do trabalho
útil: a OS era regerada, o caderno era conferido, e só então o processo
morria. De fora via-se uma tarefa com resultado 1 e nada de montagem.
"""
import ast
import pathlib
import subprocess
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _nao_sujar_o_log_de_verdade():
    """
    O `--autoteste` roda num SUBPROCESSO, e subprocesso não vê
    monkeypatch: ele escreve no log real do vigia, que fica ao lado do
    programa. Então este teste devolve o log como o encontrou.

    A limpeza é cirúrgica de propósito — tira só as linhas de autoteste
    que ESTE teste criou e preserva qualquer coisa que a tarefa agendada
    tenha escrito no meio (ela roda de minuto em minuto). Reescrever o
    arquivo inteiro apagaria a linha dela.
    """
    import caminhos

    log = caminhos.ETIQUETAS_GERADAS / "_vigia_checklist.log"
    antes = log.read_text(encoding="utf-8").split("\n") if log.is_file() else None
    yield
    if antes is None or not log.is_file():
        return
    ja_estava = set(antes)
    depois = log.read_text(encoding="utf-8").split("\n")
    limpo = [linha for linha in depois
             if linha in ja_estava or "autoteste ok" not in linha]
    if limpo != depois:
        log.write_text("\n".join(limpo), encoding="utf-8")


def modulos_com_main():
    """Os módulos que têm bloco `if __name__ == "__main__":`."""
    achados = []
    for arquivo in sorted(RAIZ.glob("*.py")):
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"), str(arquivo))
        except SyntaxError:     # noqa: PERF203 - outro teste cuida disso
            continue
        for no in arvore.body:
            if (isinstance(no, ast.If) and isinstance(no.test, ast.Compare)
                    and getattr(no.test.left, "id", "") == "__name__"):
                achados.append((arquivo, arvore, no.lineno))
                break
    return achados


def test_tem_modulo_com_bloco_main():
    """Se isto falhar, a varredura abaixo parou de olhar alguma coisa."""
    assert modulos_com_main(), "nenhum módulo com __main__: a varredura quebrou"


@pytest.mark.parametrize("caminho", [a.name for a, _t, _l in modulos_com_main()])
def test_nada_e_definido_DEPOIS_do_bloco_main(caminho):
    """
    Função ou classe definida depois do `__main__` não existe quando o
    bloco roda. Importando o módulo ela existe — é por isso que passa
    despercebida até alguém rodar pela linha de comando, que é como as
    tarefas agendadas rodam.
    """
    arquivo, arvore, linha_main = next(
        (a, t, l) for a, t, l in modulos_com_main() if a.name == caminho)
    depois = [no.name for no in arvore.body
              if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
              and no.lineno > linha_main]
    assert not depois, (
        f"{arquivo.name}: {', '.join(depois)} definido(s) depois do bloco "
        f"__main__ (linha {linha_main}). Rodando como script, o bloco "
        f"executa antes e dá NameError — e nenhum teste que IMPORTA o "
        f"módulo pega isso.")


def modulos_com_autoteste():
    """Quem oferece `--autoteste` se descobre sozinho: lista na mão envelhece."""
    return sorted(arquivo.stem for arquivo in RAIZ.glob("*.py")
                  if "--autoteste" in arquivo.read_text(encoding="utf-8"))


def test_tem_modulo_com_autoteste():
    assert modulos_com_autoteste(), "a varredura do --autoteste quebrou"


@pytest.mark.parametrize("modulo", modulos_com_autoteste())
def test_o_autoteste_roda_COMO_SCRIPT(modulo):
    """
    O caminho que nenhum outro teste usa: a linha de comando, que é como
    a tarefa agendada chama. `--autoteste` existe pra isso — ele percorre
    a carga do módulo inteira sem tocar em pasta de produção.
    """
    saida = subprocess.run(
        [sys.executable, "-m", modulo, "--autoteste"],
        cwd=str(RAIZ), capture_output=True, text=True, timeout=180)
    assert saida.returncode == 0, (
        f"{modulo} não roda como script:\n{saida.stdout}\n{saida.stderr}")
