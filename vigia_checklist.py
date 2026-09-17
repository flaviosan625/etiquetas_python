"""
Vigia do Checklist de Produção — uma passada por vez, pra TODOS os clientes
com o checklist ligado.

Pedido do usuário (2026-09-12): "atualizar a cada movimento — se entrar algo
novo, atualizar OS e Checklist". E em 2026-09-13: "amanhã pode ser outro
cliente... podemos estar com outro cliente em paralelo". Então cada passada
percorre os clientes de `clientes.com_checklist()` e, pra cada um cuja
pasta de produção mudou desde a última vez (entrou, saiu, mudou de pasta ou
de tamanho), regenera a OS dele. Se nada mudou, não faz nada — passada
barata. Cliente novo entra pelo cadastro — uma pasta em Recebimento de
Artes —, sem mexer em código e sem reinstalar tarefa.

SÓ LEITURA NA PRODUÇÃO. Este vigia NUNCA move, renomeia ou organiza arquivo
nenhum dentro de PRODUCAO — a organização automática segue congelada (ver
_congelado). Ele lê a pasta e escreve a OS FORA dela, então também nunca se
dispara sozinho.

ONDE MORA CADA COISA
  a OS gerada   -> etiquetas_geradas/<DOCUMENTO>/            saída: pode apagar
  estado e log  -> Recebimento de Artes/<cliente>/_sistema/   memória: não apagar
Até 2026-09-13 os dois moravam em etiquetas_geradas, e uma limpeza pelo
Explorer levou a memória junto (história em clientes.PASTA_SISTEMA).

Roda no modelo confiável da casa (igual ao rasterlink_hotfolder): uma
passada que trabalha uns segundos e morre, chamada de minuto em minuto por
uma tarefa do Agendador. Nada de processo eterno que morre calado.
"""
import datetime
import hashlib
import json
import pathlib

import caminhos
import checklist_producao
import clientes

NOME_ESTADO = "vigia_estado.json"
NOME_LOG = "vigia_checklist.log"
# O que não é de cliente nenhum (autoteste, trava ocupada) vai pro log geral.
NOME_LOG_GERAL = "_vigia_checklist.log"
# Trava de instância única. Desde que o painel de agentes pode forçar um
# disparo, a passada agendada e a forçada podem se encontrar — e gravar a
# mesma OS ao mesmo tempo.
NOME_TRAVA = "_vigia_checklist.trava"


def arquivo_estado(cliente):
    return cliente.pasta_sistema / NOME_ESTADO


def arquivo_log(cliente):
    return cliente.pasta_sistema / NOME_LOG


def arquivo_log_geral():
    return caminhos.ETIQUETAS_GERADAS / NOME_LOG_GERAL


def arquivo_trava():
    return caminhos.ETIQUETAS_GERADAS / NOME_TRAVA


def destino_pdf(cliente):
    # o nome é o que relatorios.gerar_os escreve — convenção da casa
    return cliente.pasta_documentos / ("OS - %s.pdf" % cliente.documento.upper())


def _log(cliente, nivel, texto):
    caminho = arquivo_log(cliente) if cliente is not None else arquivo_log_geral()
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        linha = "[%s] %-5s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nivel, texto)
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(linha)
    except OSError:
        pass        # não conseguir escrever o log nunca derruba a passada


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


def _ler_estado(cliente):
    try:
        return json.loads(arquivo_estado(cliente).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _gravar_estado(cliente, estado):
    caminho = arquivo_estado(cliente)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def passada_do_cliente(cliente, forcar=False):
    """
    Regenera a OS de UM cliente se a pasta dele mudou (ou se a OS sumiu,
    ou se 'forcar'). Devolve True se regenerou. Nunca levanta: a falha de
    um cliente vira linha no log dele e não impede os outros.
    """
    try:
        if not cliente.producao_existe:
            _log(cliente, "warn", "pasta de produção não encontrada: %s" % cliente.pasta_producao)
            return False

        import custos
        from config import carregar_config

        atual = assinatura(cliente.pasta_producao)
        # preço cadastrado também é "movimento": sem isto, a cópia de custos
        # do evento ficaria com o valor velho até alguém mexer na produção
        atual["precos"] = custos.assinatura_precos(carregar_config().get("materiais", {}))
        # a regra "só Prontos" também é movimento: ligou na janela, a OS
        # tem que mudar já, não quando alguém mexer na pasta de novo
        atual["so_prontos"] = bool(cliente.so_prontos)
        anterior = _ler_estado(cliente)
        mudou_pasta = atual["hash"] != anterior.get("hash")
        mudou_preco = atual["precos"] != anterior.get("precos", "")
        mudou_regra = atual["so_prontos"] != bool(anterior.get("so_prontos", False))
        sem_pdf = not destino_pdf(cliente).is_file()
        if not (mudou_pasta or mudou_preco or mudou_regra or sem_pdf or forcar):
            return False

        checklist_producao.gerar(cliente.pasta_documentos, cliente.pasta_producao,
                                 nome_cliente=cliente.documento,
                                 on_aviso=lambda nivel, texto: _log(cliente, nivel, texto),
                                 so_prontos=cliente.so_prontos)
        if forcar:
            motivo = "forçado"
        elif mudou_pasta:
            motivo = "movimento na pasta"
        elif mudou_regra:
            motivo = "regra de Prontos mudou"
        elif mudou_preco:
            motivo = "preço mudou"
        else:
            motivo = "OS faltando"
        _log(cliente, "ok", "OS regenerada (%s) — %d PDFs na pasta%s" % (
            motivo, atual["quantidade"], ", só os de Prontos na OS" if cliente.so_prontos else ""))
        _gravar_estado(cliente, atual)
        return True
    except Exception as e:
        _log(cliente, "erro", "falhou ao regenerar: %s: %s" % (type(e).__name__, e))
        return False


def passada(forcar=False, raiz=None):
    """
    Uma passada por todos os clientes com checklist ligado. Devolve a lista
    dos que tiveram a OS regenerada ([] = nada mudou), ou None quando outra
    passada já está rodando e esta desistiu.

    A trava é a do rasterlink_hotfolder — a mesma que já impede job
    duplicado no RIP — e não uma segunda escrita à mão.
    """
    from rasterlink_hotfolder import _travar_instancia_unica

    try:
        arquivo_trava().parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    pode_rodar, trava = _travar_instancia_unica(arquivo_trava())
    if not pode_rodar:
        _log(None, "info", "outra passada já está rodando — esta saiu sem fazer nada")
        return None
    try:
        return [c.nome for c in clientes.com_checklist(raiz) if passada_do_cliente(c, forcar)]
    finally:
        if trava is not None:
            trava.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vigia do checklist de produção (uma passada).")
    parser.add_argument("--uma-vez", action="store_true", help="uma passada e sai (padrão)")
    parser.add_argument("--forcar", action="store_true", help="regenera mesmo sem mudança")
    parser.add_argument("--autoteste", action="store_true", help="só diz se consegue iniciar")
    args = parser.parse_args()

    if args.autoteste:
        _log(None, "info", "autoteste ok — vigia_checklist iniciou")
        print("autoteste ok")
    else:
        regenerados = passada(forcar=args.forcar)
        if regenerados is None:
            print("outra passada já está rodando")
        elif regenerados:
            print("regenerou: " + ", ".join(regenerados))
        else:
            print("sem mudança")
