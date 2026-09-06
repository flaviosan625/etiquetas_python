"""
Confere se um arquivo .lua tem string quebrada ou escape invalido.

Existe porque o mesmo erro me pegou QUATRO vezes nesta sessao: escrever
Lua atraves de um script Python dentro de um heredoc do shell come um
nivel de escape a cada camada. Ja virou quebra de linha literal no meio
de string, ja virou "\\U" invalido no caminho.

A primeira versao deste verificador so olhava escape invalido — e deixou
passar exatamente o caso mais comum, que e a string aberta por uma
quebra de linha literal. Agora conta as aspas de cada linha: numero
impar significa string que nao fecha onde comecou.
"""
import pathlib
import re
import sys

VALIDOS = set('abfnrtv\\"\'0123456789\n')


def _aspas_soltas(linha):
    """Aspas nao escapadas na linha, ignorando o que vier depois de '--'."""
    codigo = linha.split("--", 1)[0] if not linha.strip().startswith("--") else ""
    return len(re.findall(r'(?<!\\)"', codigo))


def conferir(caminho):
    texto = pathlib.Path(caminho).read_text(encoding="utf-8")
    problemas = []

    for numero, linha in enumerate(texto.splitlines(), 1):
        if linha.strip().startswith("--"):
            continue

        # String que nao fecha na propria linha. Em Lua, aspas simples nao
        # atravessam linha — se sobrou uma, a string foi partida ao meio.
        if _aspas_soltas(linha) % 2 == 1 and "[[" not in linha:
            problemas.append((numero, "string nao fecha nesta linha", linha.strip()[:70]))

        for achado in re.finditer(r"\\(.)", linha):
            if achado.group(1) not in VALIDOS:
                problemas.append((numero, f"escape invalido {achado.group(0)!r}",
                                  linha.strip()[:70]))

    for posicao, byte in enumerate(texto.encode("utf-8")):
        if byte < 32 and byte not in (9, 10, 13):
            problemas.append((0, f"byte de controle {byte}", f"posicao {posicao}"))
            break

    return problemas


if __name__ == "__main__":
    ruins = conferir(sys.argv[1])
    if ruins:
        for numero, oque, trecho in ruins:
            print(f"  linha {numero}: {oque} -> {trecho}")
        raise SystemExit(1)
    print("Lua sem string quebrada nem escape invalido")
