"""
Gera o DXF de corte de cada PDF de uma pasta, com as camadas CORTE
INTERNO e CORTE EXTERNO já separadas.

Rode assim (a pasta é o único argumento):

    python gerar_dxf_de_corte.py "C:\\...\\ASICS\\PRODUCAO\\CORTES"

Por que isto existe em vez de arrastar o PDF direto pro Aspire
(2026-09-08): o Aspire abre PDF, sim, mas a API dele **não expõe os
pontos do vetor** — só a caixa envolvente. E a caixa não distingue
"dentro do desenho" de "dentro do retângulo do desenho".

Isso não é teoria. No arquivo "Mova Belo Horizonte" as 13 letras do
texto caem dentro da CAIXA do logo (uma forma varrida, com as letras no
vazio embaixo da curva) sem estarem dentro do logo. Classificadas como
furo, sairiam cortadas por dentro — 4 mm menores. No "Rio de Janeiro" o
mesmo cálculo acertou, mas por sorte: o logo de lá é mais baixo e a
caixa não alcança o texto.

Aqui, lendo o PDF, os pontos estão disponíveis e o teste é o de verdade
(ponto dentro do polígono). O DXF sai com a classificação pronta, e o
gadget do Aspire só precisa obedecer.

O PDF nunca é tocado: o DXF é arquivo novo, mesmo nome, mesma pasta.
"""
import pathlib
import sys

import corte_dxf


def gerar(pasta, aceitar_tudo=True):
    """
    Converte todos os PDFs da pasta. Devolve a lista de relatórios.

    'aceitar_tudo' liga o modo que pega TODO vetor quando o arquivo não
    traz nem magenta nem camada nomeada. É ligado aqui porque uma pasta
    CORTES é, por definição, só arquivo de corte — quem aponta pra ela
    está afirmando isso. Em arquivo avulso o padrão continua sendo
    recusar, que é o certo: DXF com o que não era corte vai pra fresa e
    só se descobre com a chapa na máquina.
    """
    pasta = pathlib.Path(pasta)
    if not pasta.is_dir():
        raise NotADirectoryError(f"não achei a pasta: {pasta}")

    relatorios = []
    for pdf in sorted(pasta.glob("*.pdf")):
        # Prontos é a confirmação manual do usuário — nunca se lê de lá.
        if pdf.parent.name.upper() == "PRONTOS":
            continue
        try:
            rel = corte_dxf.converter(pdf, aceitar_tudo=aceitar_tudo)
        except Exception as e:                   # um PDF ruim não derruba a pasta
            rel = {"pdf": str(pdf), "dxf": None, "motivo": f"não consegui ler: {e}"}
        rel["arquivo"] = pdf.name
        relatorios.append(rel)
    return relatorios


def _linha(rel):
    nome = rel["arquivo"][:52]
    if rel["dxf"] is None:
        return f"  RECUSADO  {nome:<54} {rel['motivo']}"
    marca = "  " if rel.get("criterio") != "tudo" else " *"
    return (f"  ok      {marca}{nome:<54} "
            f"fora={rel['externos']:<4} dentro={rel['internos']}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1

    relatorios = gerar(argv[1])
    if not relatorios:
        print("Nenhum PDF nessa pasta.")
        return 0

    for rel in relatorios:
        print(_linha(rel))

    feitos = sum(1 for r in relatorios if r["dxf"])
    por_tudo = sum(1 for r in relatorios if r.get("criterio") == "tudo")
    print()
    print(f"{feitos} de {len(relatorios)} viraram DXF.")
    if por_tudo:
        # Não é detalhe: nesses arquivos ninguém disse o que era corte, e
        # o programa levou TUDO. Se havia sanca, gabarito ou moldura de
        # outro material no arquivo, eles foram junto.
        print(f"{por_tudo} marcado(s) com * não tinham magenta nem camada de corte —")
        print("peguei TODOS os vetores. Confira no Aspire antes de cortar:")
        print("moldura, sanca e gabarito, se existirem, vieram junto.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
