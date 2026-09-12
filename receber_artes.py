"""
Orquestra o recebimento das artes: baixa do Drive todas as peças
LIBERADAS, tira a marca de corte, renomeia no padrão da casa e registra —
tudo a partir do caderno de arte do cliente.

É a junção das peças que já existem, cada uma provada sozinha:
  caderno_arte  -> lê a ficha e o status de cada peça
  drive_artes   -> baixa SÓ o PDF da pasta do Drive
  arte_recebida -> tira a marca sem tocar na arte, renomeia, registra
  controle_artes-> a planilha que cruza com a planilha do cliente

REGRA DE QUEM ENTRA (pedido do usuário, 2026-09-11): "baixar todas as
liberadas". Liberada = carimbo APROVADO no caderno, com link de pasta e
com medida/material que dão um nome utilizável. Aprovada sem link, ou com
medida incompleta, NÃO entra — fica registrada na planilha pra conferir,
nunca baixada no escuro.

RETOMÁVEL: o que já baixou (em _baixados.json) é pulado. Se o lote parar
no meio — Illustrator travou, rede caiu — é só rodar de novo que ele
continua de onde estava, sem refazer o que já está pronto.

RESILIENTE: uma peça que falha não derruba o lote. O gargalo é o
Illustrator (uma arte por vez, ~30-60s cada), e ele já travou de vez uma
vez; por isso a remoção tem tempo-limite e a falha de uma peça só a
sinaliza, seguindo para a próxima.
"""
import pathlib

import arte_recebida
import caderno_arte
import drive_artes


def pecas_liberadas(caminho_caderno, config=None):
    """
    As peças que entram no lote: aprovadas e com link de pasta.

    O nome utilizável NÃO é exigido aqui. Quando o caderno traz a medida
    pela metade — um número só, "0,80" — a peça ainda entra: o nome é
    completado na hora do processamento, medindo a arte baixada (regra do
    usuário, 2026-09-12: "aprovada com link deve baixar, mesmo com a ficha
    pela metade"; vale para as áreas 'aguardando 3D' também). Se nem a arte
    der um nome, aí sim ela fica em '_entrada', sinalizada, sem entrar em
    ARTES no escuro — quem decide isso é arte_recebida.processar_pdf.
    """
    fichas = caderno_arte.fichas_com_nome(caminho_caderno, config)
    return [f for f in fichas
            if f.get("situacao") == "APROVADO" and f.get("links")]


def baixar_lote(caminho_caderno, pasta, drive=None, limite=None, refazer=False,
                logger=print, config=None):
    """
    Baixa e processa as peças liberadas do caderno. Devolve um resumo
    {baixadas, puladas, falharam}. Nunca levanta por causa de uma peça —
    a falha dela vira uma linha em 'falharam'.

    'limite' baixa só as N primeiras que faltam (pra um primeiro teste).
    'refazer' ignora o que já foi baixado e baixa tudo de novo.
    """
    caminho_caderno = pathlib.Path(caminho_caderno)
    pasta = pathlib.Path(pasta)
    entrada = pasta / arte_recebida.NOME_ENTRADA
    entrada.mkdir(parents=True, exist_ok=True)
    caderno_nome = caminho_caderno.stem

    liberadas = pecas_liberadas(caminho_caderno, config)
    ja_baixadas = arte_recebida.ler_baixados(pasta)
    drive = drive or drive_artes.servico()

    resumo = {"baixadas": [], "puladas": [], "falharam": []}
    feitas = 0
    for ficha in liberadas:
        chave = arte_recebida._chave_peca(caderno_nome, ficha)
        if not refazer and chave in ja_baixadas:
            resumo["puladas"].append(ficha["nome"])
            continue
        if limite is not None and feitas >= limite:
            break
        feitas += 1

        rotulo = "slide %s (%s)" % (ficha["slide"], ficha["nome"])
        try:
            caminho, msg = drive_artes.baixar_arte_para_entrada(ficha, entrada, drive)
        except Exception as e:
            resumo["falharam"].append((ficha["nome"], "erro ao baixar: %s" % e))
            logger("warn", "%s — erro ao baixar: %s" % (rotulo, e))
            continue
        if caminho is None:
            resumo["falharam"].append((ficha["nome"], msg))
            logger("warn", "%s — %s" % (rotulo, msg))
            continue

        try:
            ok, msg2, _ = arte_recebida.processar_pdf(caminho, caminho_caderno, pasta,
                                                      logger=logger, ficha=ficha)
        except Exception as e:
            resumo["falharam"].append((ficha["nome"], "erro ao processar: %s" % e))
            logger("warn", "%s — erro ao processar: %s" % (rotulo, e))
            continue
        if ok:
            resumo["baixadas"].append(ficha["nome"])
            logger("ok", msg2)
        else:
            resumo["falharam"].append((ficha["nome"], msg2))
            logger("warn", msg2)

    return resumo


if __name__ == "__main__":
    import argparse
    import datetime

    parser = argparse.ArgumentParser(description="Baixa as artes liberadas do caderno.")
    parser.add_argument("caderno", help="caminho do .pptx do caderno de arte")
    parser.add_argument("pasta", help="pasta de recebimento (onde ficam _entrada e ARTES)")
    parser.add_argument("--limite", type=int, default=None, help="baixa só as N primeiras que faltam")
    parser.add_argument("--refazer", action="store_true", help="baixa de novo o que já foi baixado")
    args = parser.parse_args()

    def registrar(nivel, texto):
        print("[%s] %-5s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), nivel, texto), flush=True)

    resumo = baixar_lote(args.caderno, args.pasta, limite=args.limite,
                         refazer=args.refazer, logger=registrar)
    print(flush=True)
    print("=" * 60, flush=True)
    print("BAIXADAS: %d  |  PULADAS (já tinha): %d  |  FALHARAM: %d"
          % (len(resumo["baixadas"]), len(resumo["puladas"]), len(resumo["falharam"])), flush=True)
    if resumo["falharam"]:
        print("\nFALHARAM (pra conferir e tentar de novo):", flush=True)
        for nome, motivo in resumo["falharam"]:
            print("  - %s: %s" % (nome, motivo), flush=True)
