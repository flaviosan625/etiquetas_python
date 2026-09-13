"""
Clientes — cada um é uma pasta dentro de "Recebimento de Artes".

Pedido do usuário (2026-09-13): "a pasta do Mercado Livre amanhã pode ser
outro cliente... podemos estar baixando artes de outro cliente em
paralelo". E: "eu preciso criar uma pasta lá dentro de Recebimento de
Artes com o nome do novo cliente, ou arruma um jeito dessa criação pela
nossa janela — nosso sistema precisa funcionar totalmente pela janela".

A PASTA É O CADASTRO
Criou a pasta (pela janela ou no Explorer), o cliente existe. O que o
sistema precisa saber a mais — onde fica a pasta de produção dele, se o
checklist automático está ligado — mora num `cliente.json` DENTRO da
própria pasta do cliente. Não existe uma lista central pra ficar
desatualizada: apagou a pasta, o cliente sumiu de tudo junto.

Pasta criada à mão no Explorer, sem `cliente.json`, aparece como cliente
"sem configuração" — nada roda pra ela até alguém dizer onde é a produção.

O caminho da produção é gravado RELATIVO ao OneDrive ("EVENTOS\\REPSOL\\
PRODUCAO"): o nome de usuário do Windows muda de um PC pro outro — e de um
executável pro outro —, o pedaço dentro do OneDrive não.

Este módulo não tem tela (a janela é gui_clientes.py): é o que vai pro
executável sem mudar nada.
"""
import dataclasses
import datetime
import json
import pathlib

import caminhos
from utils import sanitizar_nome_arquivo

NOME_CONFIG = "cliente.json"

# O que o sistema precisa LEMBRAR de um cliente (etiquetas já impressas,
# estado do vigia, log) mora aqui dentro da pasta do cliente — e não em
# etiquetas_geradas. Aprendido em 2026-09-13: etiquetas_geradas é saída, e
# foi limpa pelo Explorer como tem que poder ser; junto foi pra Lixeira a
# lista das 50 etiquetas já impressas, e o próximo lote teria reimpresso
# tudo. O PDF se regera; a memória do que já saiu, não.
PASTA_SISTEMA = "_sistema"

# As pastas que o recebimento já usa (arte_recebida.NOME_ENTRADA/ARTES).
# Repetidas aqui como texto pra este módulo não carregar o PyMuPDF só pra
# criar duas pastas; um teste confere que continuam iguais.
PASTAS_DO_CLIENTE = ("ARTES", "_entrada")


class ErroCliente(Exception):
    """Erro com mensagem pronta pra mostrar na tela, em português."""


@dataclasses.dataclass
class Cliente:
    nome: str
    pasta: pathlib.Path
    pasta_producao: pathlib.Path | None = None
    checklist_ativo: bool = False
    # Nome que vai nos documentos (OS - <nome>.pdf). Normalmente o nome em
    # maiúsculas; existe separado porque um cliente pode ter documento com
    # outro nome já em uso (a pasta "Mercado Livre" gera "MERCADO LIVRE 26").
    nome_documento: str = ""
    configurado: bool = False
    criado_em: str = ""

    @property
    def documento(self):
        return self.nome_documento or self.nome.upper()

    @property
    def pasta_documentos(self):
        """Onde saem a OS e o checklist deste cliente. Pode ser apagada: é saída."""
        return caminhos.ETIQUETAS_GERADAS / self.documento

    @property
    def pasta_sistema(self):
        """A memória do sistema sobre este cliente. NÃO é saída — não apagar."""
        return self.pasta / PASTA_SISTEMA

    @property
    def producao_existe(self):
        return bool(self.pasta_producao and self.pasta_producao.is_dir())


def _raiz(raiz=None):
    return pathlib.Path(raiz or caminhos.RECEBIMENTO_DE_ARTES)


def _ler(pasta):
    pasta = pathlib.Path(pasta)
    cliente = Cliente(nome=pasta.name, pasta=pasta)
    caminho = pasta / NOME_CONFIG
    if not caminho.is_file():
        return cliente
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return cliente              # config ilegível = sem configuração, nunca quebra a lista
    cliente.pasta_producao = caminhos.resolver_do_onedrive(dados.get("pasta_producao"))
    cliente.checklist_ativo = bool(dados.get("checklist_ativo"))
    cliente.nome_documento = dados.get("nome_documento") or ""
    cliente.criado_em = dados.get("criado_em") or ""
    cliente.configurado = True
    return cliente


def listar(raiz=None):
    """Todos os clientes, em ordem alfabética. Pasta começando com _ ou . não é cliente."""
    raiz = _raiz(raiz)
    if not raiz.is_dir():
        return []
    pastas = [p for p in raiz.iterdir()
              if p.is_dir() and not p.name.startswith(("_", "."))]
    return [_ler(p) for p in sorted(pastas, key=lambda p: p.name.lower())]


def obter(nome, raiz=None):
    for cliente in listar(raiz):
        if cliente.nome.lower() == str(nome).strip().lower():
            return cliente
    return None


def salvar(cliente):
    """Grava o cliente.json. Cria a pasta do cliente se não existir."""
    cliente.pasta.mkdir(parents=True, exist_ok=True)
    dados = {
        "nome_documento": cliente.nome_documento or None,
        "pasta_producao": caminhos.relativo_ao_onedrive(cliente.pasta_producao) if cliente.pasta_producao else None,
        "checklist_ativo": bool(cliente.checklist_ativo),
        "criado_em": cliente.criado_em or datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (cliente.pasta / NOME_CONFIG).write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    cliente.configurado = True
    cliente.criado_em = dados["criado_em"]
    return cliente


def validar_nome(nome, raiz=None):
    """Devolve o nome limpo, ou levanta ErroCliente dizendo o que está errado."""
    bruto = (nome or "").strip()
    if not bruto:
        raise ErroCliente("Digite o nome do cliente.")
    limpo = sanitizar_nome_arquivo(bruto)
    if limpo != bruto:
        raise ErroCliente('O nome tem caractere que o Windows não aceita em pasta (\\ / : * ? " < > |). '
                          'Sugestão: "%s".' % limpo)
    if limpo.startswith(("_", ".")):
        raise ErroCliente("O nome não pode começar com _ ou . — pasta assim o sistema ignora.")
    if obter(limpo, raiz):
        raise ErroCliente('Já existe um cliente "%s".' % limpo)
    return limpo


def criar(nome, pasta_producao=None, checklist_ativo=True, nome_documento="", raiz=None):
    """
    Cria a pasta do cliente (com ARTES e _entrada dentro) e o cliente.json.
    Levanta ErroCliente com a mensagem pra tela quando algo não serve.
    """
    nome = validar_nome(nome, raiz)
    producao = pathlib.Path(pasta_producao) if pasta_producao else None
    if producao is not None and not producao.is_dir():
        raise ErroCliente("A pasta de produção escolhida não existe: %s" % producao)

    pasta = _raiz(raiz) / nome
    try:
        for sub in PASTAS_DO_CLIENTE:
            (pasta / sub).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ErroCliente("Não consegui criar a pasta do cliente: %s" % e)

    cliente = Cliente(nome=nome, pasta=pasta, pasta_producao=producao,
                      checklist_ativo=bool(checklist_ativo and producao), nome_documento=nome_documento)
    return salvar(cliente)


def sugerir_pasta_producao(nome):
    """
    Se existe EVENTOS\\<algo parecido com o nome>\\PRODUCAO, devolve. É só
    sugestão pra já vir preenchido na janela — quem confirma é o usuário.
    """
    alvo = (nome or "").strip().lower()
    if not alvo or not caminhos.EVENTOS.is_dir():
        return None
    candidatos = []
    for evento in caminhos.EVENTOS.iterdir():
        producao = evento / "PRODUCAO"
        if evento.is_dir() and producao.is_dir():
            nome_evento = evento.name.lower()
            if nome_evento == alvo:
                return producao
            if nome_evento.startswith(alvo) or alvo in nome_evento:
                candidatos.append(producao)
    return candidatos[0] if len(candidatos) == 1 else None


def com_checklist(raiz=None):
    """Os clientes que o vigia do checklist deve atender agora."""
    return [c for c in listar(raiz) if c.checklist_ativo and c.producao_existe]
