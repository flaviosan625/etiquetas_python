"""Consumo e custo por cliente, derivados das pastas atuais de produção.

Reutiliza o aproveitamento de rolos/chapas e os preços por variante.
É estimativa de material e tinta: não realiza baixa no estoque.
"""
from datetime import datetime
from html import escape
import math
from pathlib import Path

import aproveitamento
import custos
import custos_tinta
import dimensoes


def _chave(categoria, variante):
    return categoria or 'NÃO IDENTIFICADO', (variante or {}).get('espessura', ''), (variante or {}).get('cor', '')


def calcular(itens, config):
    materiais = config.get('materiais', {})
    linhas, faltantes = {}, []

    def linha(cat, variante=None):
        return linhas.setdefault(_chave(cat, variante), dict(categoria=cat or 'NÃO IDENTIFICADO', variante=variante,
            previsto=0.0, produzido=0.0, pendente=0.0, consumo=0.0, sobra=0.0, custo=0.0,
            preco=custos.preco_m2(materiais, cat, variante), completo=True, usado=False, detalhes=[]))

    validos = []
    for item in itens:
        for aviso in item.get('avisos', []):
            faltantes.append(f"{item['arquivo']}: {aviso}")
        dim = item.get('dimensao')
        bom = dim and all(isinstance(dim.get(k), (float, int)) and math.isfinite(dim[k]) and dim[k] > 0
                          for k in ('largura_m', 'altura_m', 'area_m2'))
        qtd = item.get('quantidade')
        bom = bool(bom and isinstance(qtd, (int, float)) and math.isfinite(qtd) and qtd > 0)
        if bom:
            validos.append(item)
        else:
            faltantes.append(f"{item['arquivo']}: medida ou quantidade ausente/inválida")
        destinos = [(item.get('categoria'), item.get('variante'))]
        if item.get('categoria_extra'):
            destinos.append((item['categoria_extra'], None))
        for cat, variante in destinos:
            r = linha(cat, variante)
            r['usado'] = True
            if bom:
                area = dim['area_m2'] * qtd
                r['previsto'] += area
                r['produzido' if item['pronto'] else 'pendente'] += area
            else:
                r['completo'] = False
            if cat not in materiais:
                r['completo'] = False
                faltantes.append(f"Material não cadastrado: {cat or item['arquivo']}")
            if r['preco'] is None:
                r['completo'] = False
                faltantes.append(f"Preço a cadastrar: {cat or 'material não identificado'} {dimensoes.formatar_variante(variante)}".strip())

    # Não encaixar peças de trabalhos distintos como se fossem um único lote.
    grupos = {}
    for item in validos:
        if not item['pronto']:
            continue
        for cat, variante in [(item.get('categoria'), item.get('variante')),
                              (item.get('categoria_extra'), None)]:
            if cat:
                copia = dict(item, categoria=cat, variante=variante, categoria_extra=None)
                grupos.setdefault((item.get('vinculo', ''), _chave(cat, variante)), []).append(copia)
    for (_, chave), grupo in grupos.items():
        r = linhas[chave]
        try:
            info = materiais.get(grupo[0]['categoria'], {})
            if not all(math.isfinite(float(info.get(k, 0))) and float(info.get(k, 0)) > 0
                       for k in ('largura_cm', 'comprimento_cm')):
                raise ValueError('medidas do rolo/chapa não cadastradas')
            lotes = aproveitamento.consumo_por_material(grupo, materiais)
            if not lotes:
                raise ValueError('consumo não calculado')
            for lote in lotes:
                r['consumo'] += lote['area_consumida_m2']
                r['sobra'] += lote['desperdicio_m2']
                r['detalhes'].append(aproveitamento.descrever(lote))
                if r['preco'] is not None:
                    r['custo'] += lote['area_consumida_m2'] * r['preco']
        except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as erro:
            r['completo'] = False
            faltantes.append(f"{r['categoria']}: {erro}")
    for cat in materiais:
        if not any(r['categoria'] == cat for r in linhas.values()):
            linha(cat)
    for r in linhas.values():
        for campo in ('previsto', 'produzido', 'pendente', 'consumo', 'sobra', 'custo'):
            r[campo] = round(r[campo], 4)
        if r['preco'] is None or not r['completo']:
            r['custo'] = None
    produzidos = [i for i in itens if i['pronto']]
    config_tinta = config.get('centro_custos_tintas') or {}
    tinta = custos_tinta.calcular(produzidos, config_tinta)
    faltantes.extend(tinta['faltantes'])
    for item in produzidos:
        nome = item['arquivo'].upper()
        impresso = (item.get('categoria') in ('LONA', 'ADESIVO', 'DECORFLEX') or item.get('categoria_extra') == 'ADESIVO'
                    or 'IMPRESS' in nome)
        dispensada = any(t in nome for t in ('CORTE DIRETO', 'CORTEDIRETO', 'SEM IMPRESS'))
        maquina, _ = custos_tinta.maquina_da_peca(item, config_tinta)
        if impresso and not dispensada and not maquina:
            faltantes.append(f"Tinta sem perfil de consumo/preço: {item['arquivo']}")
    # Perfil de tinta presente: total parcial sempre identificado, nunca zero presumido.
    subtotal_material = sum(r['custo'] for r in linhas.values() if r['usado'] and r['custo'] is not None)
    total = subtotal_material + tinta['total']
    faltantes = list(dict.fromkeys(faltantes))
    return dict(linhas=list(linhas.values()), total_arquivos=len(itens), produzidos=len(produzidos),
                pendentes=len(itens)-len(produzidos), tintas=tinta, subtotal_material=round(subtotal_material, 2),
                total=round(total, 2), completo=not faltantes, faltantes=faltantes,
                tem_valor=any(r['produzido'] and r['custo'] is not None for r in linhas.values()) or bool(tinta['por_maquina']))


def numero(valor):
    return f'{valor:.2f}'.replace('.', ',')


def gerar_pdf(destino, cliente, itens, config, resumo=None):
    """Exporta a fotografia atual do cliente, com artes e pendências explícitas."""
    import os
    import tempfile
    import pymupdf
    import miniaturas
    from relatorios import _nova_pagina_os, MARGEM_OS, LARGURA_OS

    resumo = resumo or calcular(itens, config)
    pdf = pymupdf.open()
    quando = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    caixas = []
    css = '''body {font-family:sans-serif;font-size:8.5pt;color:#333;margin:0;}
        h2 {font-size:11pt;color:#174d7a;margin:9pt 0 7pt;} p {margin:6pt 0;line-height:1.3;}
        table {border-collapse:collapse;width:100%;font-size:8pt;}
        th,td {padding:6pt 4pt;border-bottom:0.5pt solid #ddd;text-align:left;}
        th {background:#e6f1fb;color:#174d7a;}.nota {font-size:7.5pt;color:#666;}
        .aviso {color:#986014;}'''

    def pagina_html(html, arquivo=None):
        pagina, y = _nova_pagina_os(pdf, escape(cliente), escape(config.get('ultimo_gerente', '')),
                                  escape(config.get('ultimo_produtor', '')), quando, caixas,
                                  rotulo='CONSUMO E CUSTO')
        _, escala = pagina.insert_htmlbox(pymupdf.Rect(MARGEM_OS, y, LARGURA_OS-MARGEM_OS, 795),
                                          html, css=css, archive=arquivo)
        if escala < 0.9:
            raise ValueError('O relatório não coube com tamanho legível. Reduza os nomes excessivamente longos.')

    estado = 'PRODUÇÃO CONCLUÍDA' if itens and not resumo['pendentes'] else 'PRODUÇÃO EM ANDAMENTO'
    total_txt = custos.formatar_reais(resumo['total']) if resumo['tem_valor'] else 'Aguardando preços / apuração'
    if not resumo['completo']:
        total_txt += ' — PARCIAL / INCOMPLETO'
    linhas = [r for r in resumo['linhas'] if r['usado']]
    try:
        for inicio in range(0, max(1, len(linhas)), 10):
            trechos = []
            for r in linhas[inicio:inicio+10]:
                nome = r['categoria'] + ' ' + dimensoes.formatar_variante(r['variante'])
                preco = custos.formatar_reais(r['preco']) if r['preco'] is not None else 'A cadastrar'
                custo = custos.formatar_reais(r['custo']) if r['custo'] is not None else 'A apurar'
                trechos.append(f'<tr><td>{escape(nome)}</td><td>{numero(r["previsto"])}</td>'
                               f'<td>{numero(r["produzido"])}</td><td>{numero(r["pendente"])}</td>'
                               f'<td>{numero(r["consumo"])}</td><td>{preco}</td><td>{custo}</td></tr>')
            pagina_html(f'<h2>{estado}</h2><p>{resumo["produzidos"]} de {len(itens)} arquivos produzidos '
                        f'• {resumo["pendentes"]} pendentes</p><h2>Consumo e custo por material</h2>'
                        '<table><tr><th>Material / variante</th><th>Previsto<br>m² arte</th><th>Produzido<br>m² arte</th>'
                        '<th>Pendente<br>m² arte</th><th>Consumo<br>m² est.</th><th>Preço/m²</th><th>Custo produzido</th></tr>'
                        + ''.join(trechos) + '</table><p class="nota">Consumo estimado dos produzidos: peças + sobra do aproveitamento '
                        'de rolos/chapas. Quantidade multiplicada pela área da peça. Áreas separadas por material.</p>'
                        f'<h2>Subtotal dos materiais: {custos.formatar_reais(resumo["subtotal_material"])}</h2>'
                        f'<p>Tinta estimada com perfil disponível: {custos.formatar_reais(resumo["tintas"]["total"])}</p>'
                        f'<h2>Total conhecido: {escape(total_txt)}</h2>'
                        '<p class="nota">Não inclui máquina, mão de obra, frete nem baixa de estoque. Produzido significa arquivo em PRONTOS, '
                        'não leitura automática da impressora. Novas artes podem reabrir pendências.</p>')
        for inicio in range(0, len(resumo['faltantes']), 14):
            pagina_html('<h2>Pendências para o fechamento financeiro</h2><p>Preço ausente não representa custo zero.</p><ul>'
                        + ''.join(f'<li>{escape(p)}</li>' for p in resumo['faltantes'][inicio:inicio+14]) + '</ul>')
        for maquina, dados in resumo['tintas']['por_maquina'].items():
            linhas_tinta = ''.join(f'<tr><td>{escape(c["nome"])}</td><td>{numero(c["volume_ml"])} mL</td>'
                                  f'<td>{custos.formatar_reais(c["preco_ml"])}</td><td>{custos.formatar_reais(c["valor"])}</td></tr>'
                                  for c in dados['cores'].values())
            pagina_html(f'<h2>Tinta estimada • {escape(maquina)}</h2><p>{numero(dados["area_m2"])} m² impressos</p>'
                        '<table><tr><th>Cor</th><th>Consumo</th><th>Preço/mL</th><th>Custo</th></tr>' + linhas_tinta + '</table>'
                        f'<p>Total: {custos.formatar_reais(dados["valor"])}</p><p class="nota">Estimativa por área, sem limpeza/purga. '
                        + ('Referência provisória da R5200.' if dados['referencia_provisoria'] else 'Referência do perfil cadastrado.') + '</p>')
        for inicio in range(0, len(itens), 6):
            arquivo = pymupdf.Archive()
            linhas_arte = []
            for n, item in enumerate(itens[inicio:inicio+6]):
                dados = miniaturas.de_arquivo(item['caminho'], lado=230)
                mini = 'Prévia indisponível'
                if dados:
                    nome = f'arte{n}.jpg'
                    arquivo.add((dados, nome))
                    w, h = miniaturas.encaixar(dados, 100, 65)
                    mini = f'<img src="{nome}" width="{w}" height="{h}">'
                dim = item.get('dimensao')
                medida = (f'{numero(dim["largura_m"])} × {numero(dim["altura_m"])} m' if dim else 'Medida não identificada')
                linhas_arte.append(f'<tr><td style="width:105px">{mini}</td><td><b>{escape(item["arquivo"])}</b>'
                                  f'<br>{escape(item["trabalho"])} • {escape(item["status"])}<br>'
                                  f'{item["quantidade"]} un • {medida}<br><span class="nota">{escape(item["relativo"])}</span></td></tr>')
            pagina_html('<h2>Materiais do cliente • posição na emissão</h2><table>' + ''.join(linhas_arte) + '</table>', arquivo)
        for indice in range(len(pdf)):
            pdf[indice].insert_text((MARGEM_OS, 818), f'{indice+1}/{len(pdf)}', fontsize=8)
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, temporario = tempfile.mkstemp(prefix='consumo-', suffix='.pdf', dir=destino.parent)
        os.close(fd)
        try:
            pdf.save(temporario, garbage=4, deflate=True)
            pdf.close()
            os.replace(temporario, destino)
        finally:
            Path(temporario).unlink(missing_ok=True)
        return destino
    finally:
        pdf.close()
