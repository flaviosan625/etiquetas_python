"""Pastas existentes, inventário e conclusão manual de materiais por cliente.

Ler nunca cria nem organiza a pasta de produção. PRONTOS é a fonte do status.
O cadastro e o histórico ficam locais, fora das artes e da saída descartável.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

import caminhos
import dimensoes

EXTENSOES = {'.pdf', '.ai', '.eps', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.svg', '.cdr', '.dxf', '.psd'}
PRONTOS = {'PRONTO', 'PRONTOS'}
PREFIXOS_DOCUMENTOS = ('OS - ', 'CUSTOS - ', 'CONSUMO E CUSTO - ', 'CHECKLIST ', 'RETIRADA - ')


class ErroProducao(ValueError):
    pass


def pasta_estado():
    return caminhos.PASTA_PROGRAMA / '_controle_producao'


def _chave(pasta):
    return os.path.normcase(str(Path(pasta).resolve()))


def _link(pasta):
    return pasta.is_symlink() or (hasattr(os.path, 'isjunction') and os.path.isjunction(pasta))


def validar_pasta(endereco):
    texto = str(endereco).strip().strip('"')
    if not texto or '://' in texto:
        raise ErroProducao('Cole o caminho da pasta no computador, na rede ou no OneDrive sincronizado.')
    pasta = Path(texto)
    if not pasta.is_absolute() or not pasta.is_dir():
        raise ErroProducao('A pasta não existe ou está indisponível. Confira o caminho e a conexão.')
    if pasta.parent == pasta or pasta.name.upper() in PRONTOS:
        raise ErroProducao('Selecione a pasta de produção do cliente, acima de PRONTOS.')
    if _link(pasta):
        raise ErroProducao('Use o endereço real da pasta, sem atalho simbólico ou junção.')
    return pasta.resolve()


def _cadastro():
    caminho = pasta_estado() / 'pastas.json'
    if not caminho.exists():
        return []
    try:
        dados = json.loads(caminho.read_text(encoding='utf-8'))
        if not isinstance(dados, list) or any(not all(k in d for k in ('id', 'cliente', 'trabalho', 'pasta')) for d in dados):
            raise ValueError('estrutura inválida')
        return dados
    except (OSError, ValueError, TypeError) as erro:
        raise ErroProducao(f'Não foi possível ler o cadastro de produção: {erro}. O arquivo foi preservado.') from erro


def listar_vinculos():
    """Inclui os clientes já cadastrados, sem gravar nada no cadastro antigo."""
    import clientes
    dados = _cadastro()
    vistos = {_chave(d['pasta']) for d in dados}
    for cliente in clientes.listar():
        if cliente.pasta_producao:
            chave = _chave(cliente.pasta_producao)
            if chave not in vistos:
                dados.append(dict(id='existente:' + chave, cliente=cliente.nome,
                                  trabalho=cliente.documento, pasta=str(cliente.pasta_producao)))
                vistos.add(chave)
    return sorted(dados, key=lambda d: (d['cliente'].casefold(), d['trabalho'].casefold()))


@contextmanager
def _trava():
    pasta_estado().mkdir(parents=True, exist_ok=True)
    trava = pasta_estado() / 'alteracao.lock'
    try:
        arquivo = trava.open('x', encoding='utf-8')
    except FileExistsError as erro:
        raise ErroProducao('Há uma alteração em andamento. Aguarde e tente novamente.') from erro
    try:
        arquivo.write(str(os.getpid()))
        arquivo.close()
        yield
    finally:
        arquivo.close()
        trava.unlink(missing_ok=True)


def vincular(endereco, cliente='', trabalho=''):
    pasta = validar_pasta(endereco)
    with _trava():
        existentes = listar_vinculos()
        for d in existentes:
            outra = Path(d['pasta']).resolve()
            if _chave(outra) == _chave(pasta):
                return d
            if pasta in outra.parents or outra in pasta.parents:
                raise ErroProducao('Esta pasta se sobrepõe a outra já vinculada. Vincule cada pasta apenas uma vez.')
        nome = pasta.parent.name if pasta.name.upper() in {'PRODUCAO', 'PRODUÇÃO', 'EM PRODUÇÃO', 'EM PRODUCAO'} else pasta.name
        registro = dict(id=uuid.uuid4().hex, cliente=cliente.strip() or nome,
                        trabalho=trabalho.strip() or pasta.parent.name if pasta.name.upper() in {'PRODUCAO', 'PRODUÇÃO'} else trabalho.strip() or pasta.name,
                        pasta=str(pasta))
        dados = _cadastro() + [registro]
        destino = pasta_estado() / 'pastas.json'
        fd, temporario = tempfile.mkstemp(prefix='cadastro-', suffix='.tmp', dir=pasta_estado())
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as arq:
                json.dump(dados, arq, ensure_ascii=False, indent=2)
                arq.flush()
                os.fsync(arq.fileno())
            os.replace(temporario, destino)
        finally:
            Path(temporario).unlink(missing_ok=True)
        return registro


def inventariar(vinculo, config):
    raiz = validar_pasta(vinculo['pasta'])
    materiais = config.get('materiais', {})
    itens = []

    def falhou(erro):
        raise ErroProducao(f'Falha ao ler parte da pasta: {erro}')

    for atual, pastas, nomes in os.walk(raiz, followlinks=False, onerror=falhou):
        pai = Path(atual)
        pastas[:] = sorted(p for p in pastas if not p.startswith(('.', '_')) and not _link(pai / p))
        for nome in sorted(nomes):
            arquivo = pai / nome
            if (arquivo.suffix.lower() not in EXTENSOES or nome.startswith(('.', '_', '~'))
                    or nome.upper().startswith(PREFIXOS_DOCUMENTOS) or _link(arquivo)):
                continue
            try:
                info = arquivo.stat()
            except FileNotFoundError:
                continue  # Outra pessoa pode ter acabado de mover este arquivo.
            if not stat.S_ISREG(info.st_mode):
                continue
            relativo = arquivo.relative_to(raiz)
            pronto = any(p.upper() in PRONTOS for p in relativo.parts[:-1])
            categoria = dimensoes.identificar_categoria(nome.upper(), materiais, config.get('sinonimos_categoria', {}))[0]
            extra = dimensoes.identificar_categoria_extra(nome.upper(), materiais, config.get('materiais_compostos', {}))
            dim = dimensoes.extrair_dimensoes(nome, config.get('typos_unidade', {}))
            quantidade, declarada = dimensoes.extrair_quantidade(nome)
            variantes = materiais.get(categoria, {}).get('variantes', [])
            variante = dimensoes.identificar_variante(nome, variantes)
            avisos = []
            if not categoria:
                avisos.append('Material não identificado')
            if not dim:
                avisos.append('Medida não identificada no nome')
            if not declarada:
                avisos.append('Quantidade presumida: 1 unidade')
            if variantes and not variante:
                avisos.append('Espessura/cor não identificada')
            itens.append(dict(id=vinculo['id'] + ':' + relativo.as_posix(), vinculo=vinculo['id'],
                              cliente=vinculo['cliente'], trabalho=vinculo['trabalho'], raiz=str(raiz),
                              caminho=str(arquivo), relativo=relativo.as_posix(), arquivo=nome,
                              pronto=pronto, status='Produzido • PRONTOS' if pronto else 'Pendente',
                              categoria=categoria, categoria_extra=extra if extra != categoria else None,
                              variante=variante, quantidade=quantidade, quantidade_declarada=declarada,
                              dimensao=dict(largura_m=dim['largura_m'], altura_m=dim['altura_m'],
                                            area_m2=dim['largura_m'] * dim['altura_m']) if dim else None,
                              maquina=' '.join(relativo.parts[:-1]), avisos=avisos,
                              assinatura=(info.st_size, info.st_mtime_ns)))
    return itens


def _destino(item):
    raiz = validar_pasta(item['raiz'])
    origem = Path(item['caminho'])
    if not origem.is_absolute() or origem.resolve().parent != origem.parent.resolve() or _link(origem):
        raise ErroProducao('O arquivo deixou de ser um arquivo comum da pasta selecionada.')
    try:
        relativo = origem.relative_to(raiz)
        origem.resolve().relative_to(raiz)
    except ValueError as erro:
        raise ErroProducao('O arquivo não pertence à pasta deste trabalho.') from erro
    if '..' in relativo.parts or any(p.upper() in PRONTOS for p in relativo.parts[:-1]):
        raise ErroProducao('O arquivo já está em PRONTOS ou o caminho é inválido.')
    for pai in [origem, *origem.parents]:
        if pai == raiz:
            break
        if _link(pai):
            raise ErroProducao('Não é permitido mover por links ou junções.')
    info = origem.stat()
    if (info.st_size, info.st_mtime_ns) != tuple(item['assinatura']):
        raise ErroProducao('O arquivo mudou desde a seleção. Atualize a lista e confira a arte novamente.')
    prontas = sorted(p for p in raiz.iterdir() if p.name.upper() in PRONTOS)
    if len(prontas) > 1:
        raise ErroProducao('Há mais de uma pasta PRONTO/PRONTOS. Unifique o destino antes de mover.')
    pasta_prontos = prontas[0] if prontas else raiz / 'PRONTOS'
    destino = pasta_prontos / relativo
    for pai in [destino, *destino.parents]:
        if pai == raiz:
            break
        if _link(pai):
            raise ErroProducao('O destino usa um link ou junção. Nenhum arquivo foi movido.')
    if destino.exists():
        raise ErroProducao('Já existe um arquivo com este nome em PRONTOS. Nada será sobrescrito.')
    return origem, destino


def mover_lote(itens):
    """Não sobrescreve destinos; falhas parciais são devolvidas por arquivo."""
    movidos, erros = [], []
    if not itens:
        return dict(movidos=movidos, erros=erros)
    if len({i['cliente'] for i in itens}) != 1:
        raise ErroProducao('Selecione arquivos de um cliente por vez.')
    with _trava():
        # Abrir o histórico antes de mover impede movimento sem registro disponível.
        with (pasta_estado() / 'movimentos.jsonl').open('a', encoding='utf-8') as historico:
            for item in itens:
                try:
                    origem, destino = _destino(item)
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    evento = dict(quando=datetime.now(timezone.utc).isoformat(), cliente=item['cliente'],
                                  trabalho=item['trabalho'], origem=str(origem), destino=str(destino))
                    historico.write(json.dumps(dict(evento, evento='solicitado'), ensure_ascii=False) + '\n')
                    historico.flush()
                    os.fsync(historico.fileno())
                    if os.name == 'nt':
                        os.rename(origem, destino)  # Windows recusa destino existente, inclusive numa corrida.
                    else:
                        os.link(origem, destino)  # Criação exclusiva no mesmo volume.
                        try:
                            origem.unlink()
                        except OSError:
                            destino.unlink()
                            raise
                    movidos.append(dict(item, caminho=str(destino)))
                    historico.write(json.dumps(dict(evento, evento='concluido'), ensure_ascii=False) + '\n')
                    historico.flush()
                except (OSError, ErroProducao) as erro:
                    erros.append(dict(arquivo=item['arquivo'], erro=str(erro)))
    return dict(movidos=movidos, erros=erros)
