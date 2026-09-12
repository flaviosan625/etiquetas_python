"""
Vigia do Checklist de Produção — uma passada por vez.

Pedido do usuário (2026-09-12): "atualizar a cada movimento — se entrar algo
novo, atualizar OS e Checklist". Este vigia é o que dispara isso: a cada
passada ele OLHA a pasta PRODUCAO e, se algo mudou desde a última vez
(entrou, saiu, mudou de pasta ou de tamanho), regenera o PDF do checklist
em etiquetas_geradas. Se nada mudou, não faz nada — passada barata.

SÓ LEITURA. Este vigia NUNCA move, renomeia ou organiza arquivo nenhum
dentro de PRODUCAO — a organização automática segue congelada (ver
reference_venv_e_congelamento / _congelado). Ele só lê a pasta e escreve o
PDF FORA dela (em etiquetas_geradas), então também nunca dispara a si
mesmo.

Roda no modelo confiável da casa (igual ao rasterlink_hotfolder): uma
passada que trabalha uns segundos e morre, chamada de minuto em minuto por
uma tarefa do Agendador. Nada de processo eterno que morre calado.
"""
import datetime
import hashlib
import json
import pathlib

import checklist_producao

# A pasta vigiada e para onde vai o PDF. O PDF mora FORA da pasta vigiada
# (em etiquetas_geradas, na área de trabalho, junto das OS) de propósito:
# assim o vigia não vê a própria gravação e não se dispara.
PASTA_PRODUCAO = pathlib.Path(
    r"C:\Users\flavi\OneDrive\UNYCOMUNICACAO\EVENTOS\MERCADO LIVRE 26\PRODUCAO")
PASTA_SAIDA = pathlib.Path(
    r"C:\Users\flavi\Desktop\etiquetas_python\etiquetas_geradas\MERCADO LIVRE 26")
NOME_CLIENTE = "MERCADO LIVRE 26"
# O nome do arquivo é o que relatorios.gerar_os escreve — convenção da casa.
DESTINO_PDF = PASTA_SAIDA / ("OS - %s.pdf" % NOME_CLIENTE.upper())
ARQUIVO_ESTADO = PASTA_SAIDA / "_vigia_estado.json"
ARQUIVO_LOG = PASTA_SAIDA / "_vigia_checklist.log"


def _log(nivel, texto):
    ARQUIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
    linha = "[%s] %-5s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nivel, texto)
    with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
        f.write(linha)


def assinatura(pasta):
    """
    Um resumo do estado da pasta: cada PDF com seu caminho, tamanho e
    data de modificação. Qualquer movimento — entrar, sair, mudar de
    pasta (status), renomear ou reexportar — muda essa assinatura.
    """
    pasta = pathlib.Path(pasta)
    itens = []
    for pdf in sorted(pasta.rglob("*.pdf")):
        try:
            st = pdf.stat()
            itens.append("%s|%d|%d" % (pdf.relative_to(pasta).as_posix(), st.st_size, int(st.st_mtime)))
        except OSError:
            itens.append("%s|?" % pdf.relative_to(pasta).as_posix())
    bruto = "\n".join(itens)
    return {
        "hash": hashlib.sha256(bruto.encode("utf-8")).hexdigest(),
        "quantidade": len(itens),
    }


def _ler_estado():
    try:
        return json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _gravar_estado(estado):
    ARQUIVO_ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def passada(forcar=False):
    """
    Uma passada. Regenera o PDF se a pasta mudou (ou se o PDF sumiu, ou
    se 'forcar'). Devolve True se regenerou. Nunca levanta pra fora — uma
    falha vira linha no log, não um erro que mata a tarefa.
    """
    try:
        if not PASTA_PRODUCAO.is_dir():
            _log("warn", "pasta de produção não encontrada: %s" % PASTA_PRODUCAO)
            return False

        atual = assinatura(PASTA_PRODUCAO)
        anterior = _ler_estado()
        mudou = atual["hash"] != anterior.get("hash")
        sem_pdf = not DESTINO_PDF.is_file()

        if not (mudou or sem_pdf or forcar):
            return False

        checklist_producao.gerar(PASTA_SAIDA, PASTA_PRODUCAO, nome_cliente=NOME_CLIENTE)
        motivo = "forçado" if forcar else ("PDF faltando" if sem_pdf and not mudou else "movimento na pasta")
        _log("ok", "checklist regenerado (%s) — %d PDFs na pasta" % (motivo, atual["quantidade"]))
        _gravar_estado(atual)
        return True
    except Exception as e:
        _log("erro", "falhou ao regenerar: %s: %s" % (type(e).__name__, e))
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vigia do checklist de produção (uma passada).")
    parser.add_argument("--uma-vez", action="store_true", help="uma passada e sai (padrão)")
    parser.add_argument("--forcar", action="store_true", help="regenera mesmo sem mudança")
    parser.add_argument("--autoteste", action="store_true", help="só diz se consegue iniciar")
    args = parser.parse_args()

    if args.autoteste:
        _log("info", "autoteste ok — vigia_checklist iniciou")
        print("autoteste ok")
    else:
        regenerou = passada(forcar=args.forcar)
        print("regenerou" if regenerou else "sem mudança")
