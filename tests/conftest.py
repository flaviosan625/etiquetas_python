"""
Trava de isolamento da suíte inteira: nenhum teste escreve na pasta do
programa de verdade sem pedir.

Existe porque *isolar o OneDrive não basta*. As constantes de `caminhos`
apontam pra pasta do programa DE VERDADE, e teste distraído escreve lá
sem errar nada — nenhuma asserção falha, o arquivo simplesmente nasce no
lugar do usuário. Três vezes já:

- uma limpeza do `estoque.json` em 2026-09-13;
- um `RuntimeError: boom` carimbado no log do vigia do caderno a cada
  rodada, lido em 05/10/2026 como falha de produção (fui investigar um
  vigia que estava são);
- e, até 10/10/2026, um aviso de ``fila parada: UJV 100 UNY CV (1
  arquivo(s) há 65 min)`` por rodada — 11 linhas falsas num log que se lê
  justamente pra achar falha de verdade. A fila estava vazia todas as
  vezes, e o "65 min" era o número do caso real citado no docstring do
  teste.

Log de diagnóstico sujo é exatamente como a falha de verdade passa
batido, então o padrão passou a ser pasta descartável. Quem precisa do
caminho real, ou de outro, continua podendo: o `monkeypatch` do teste
roda DEPOIS deste e ganha.

`_controle_producao` (o registro de material em produção) e o
`_aviso_fila.json` moram em `PASTA_PROGRAMA`; a saída de etiquetas e o
log do vigia em `ETIQUETAS_GERADAS`; o estoque em `ESTOQUE`. Os três
derivam da pasta do programa, mas são constantes separadas — calculadas
no import —, então cada uma é redirecionada na mão.
"""
import pytest

import caminhos
import separar_ripados


@pytest.fixture(autouse=True)
def pasta_do_programa_isolada(tmp_path_factory, monkeypatch):
    """
    A pasta do programa de cada teste, descartável e só dele.

    Nasce pelo `tmp_path_factory`, AO LADO do `tmp_path` e nunca dentro:
    vários testes provam que uma falha "não deixa lixo" conferindo que o
    `tmp_path` ficou VAZIO (`test_seguranca_montagem`,
    `test_producao`, `test_previas_impressao`, `test_marca_de_corte_imagem`).
    Criar a pasta do programa lá dentro quebrava os seis de uma vez — a
    trava contra sujeira não pode ser ela mesma a sujeira.
    """
    programa = tmp_path_factory.mktemp("programa")
    monkeypatch.setattr(caminhos, "PASTA_PROGRAMA", programa)
    monkeypatch.setattr(caminhos, "ETIQUETAS_GERADAS", programa / "etiquetas_geradas")
    monkeypatch.setattr(caminhos, "ESTOQUE", programa / "estoque.json")
    # O endereço da hot folder do BYHX mora ao lado do módulo. Se alguém
    # criar o arquivo no repositório, a entrega ao BYHX ligaria em todo teste
    # que passa por _cuidar_do_ripado — e moveria ripado de verdade.
    monkeypatch.setattr(separar_ripados, "CAMINHO_HOT_FOLDER_BYHX", programa / "hot_folder_byhx.txt")
    return programa
