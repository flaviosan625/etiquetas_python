"""Prévia navegável, isolada: dados fictícios e alterações somente em memória.

Não inicia o programa, não monitora pastas e não movimenta arquivos reais.
Reutiliza a paleta do sistema e o cabeçalho de documentos existente.
"""
from pathlib import Path, PureWindowsPath
from copy import deepcopy
from html import escape
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

if sys.platform == 'win32':
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import tema
from tema import cores


def texto(pai, valor, tamanho=10, cor=None, negrito=False, **opcoes):
    return tk.Label(pai, text=valor, bg=pai.cget('bg'), fg=cor or cores.texto,
                    font=('Segoe UI', tamanho, 'bold' if negrito else 'normal'), **opcoes)


def botao(pai, rotulo, comando, principal=False):
    return tk.Button(pai, text=rotulo, command=comando, relief='flat', bd=0,
                     bg=cores.acento if principal else cores.borda,
                     fg=cores.sobre_acento if principal else cores.texto,
                     activebackground=cores.acento_claro if principal else cores.marcado,
                     activeforeground=cores.texto, font=('Segoe UI', 10),
                     padx=14, pady=8, cursor='hand2')


def cartao(pai):
    return tk.Frame(pai, bg=cores.cartao, highlightbackground=cores.borda,
                    highlightthickness=1)


def resumo_consumo(itens, precos=None):
    """Conta apenas dados fictícios; preços opcionais por m² na simulação."""
    precos = precos or {}
    materiais = dict.fromkeys(['LONA', 'ADESIVO', 'MDF', 'ACRÍLICO', 'PS'] + [i['material'] for i in itens])
    resumo = {}
    for material in materiais:
        grupo = [i for i in itens if i['material'] == material]
        previsto = sum((Decimal(str(i['area_un'])) * i['qtd'] for i in grupo), Decimal('0'))
        produzido = sum((Decimal(str(i['area_un'])) * i['qtd'] for i in grupo if i['pronto']), Decimal('0'))
        preco = precos.get(material)
        resumo[material] = dict(previsto=previsto, produzido=produzido, pendente=previsto-produzido,
                               preco=preco, custo=None if preco is None else produzido * Decimal(str(preco)))
    return resumo


def numero(valor):
    return f'{valor:.2f}'.replace('.', ',')


def pdf_custos_previa(cliente, itens, precos=None):
    """Relatório demonstrativo por cliente, atualizado pelo mesmo resumo da tela."""
    import pymupdf
    from relatorios import _nova_pagina_os, MARGEM_OS, LARGURA_OS

    pdf = pymupdf.open()
    instante = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
    caixas = []

    def nova_pagina():
        return _nova_pagina_os(pdf, escape(cliente), 'SIMULAÇÃO', 'SIMULAÇÃO', instante + ' (Brasília)',
                               caixas, rotulo='CONSUMO E CUSTO &mdash; DIRETORIA &mdash; PRÉVIA')

    pagina, y = nova_pagina()
    resumo = resumo_consumo(itens, precos)
    prontos = sum(i['pronto'] for i in itens)
    pendentes = len(itens) - prontos
    situacao = 'PRODUÇÃO CONCLUÍDA' if itens and not pendentes else 'PRODUÇÃO EM ANDAMENTO'
    linhas = []
    for nome, r in resumo.items():
        preco = 'A cadastrar' if r['preco'] is None else 'R$ ' + numero(Decimal(str(r['preco'])))
        custo = 'Aguardando preço' if r['custo'] is None else 'R$ ' + numero(r['custo'])
        if not r['previsto']:
            custo = 'Não utilizado'
        linhas.append(f'<tr><td><b>{escape(nome)}</b></td><td>{numero(r["previsto"])}</td>'
                      f'<td>{numero(r["produzido"])}</td><td>{numero(r["pendente"])}</td>'
                      f'<td>{preco}</td><td>{custo}</td></tr>')
    faltantes = [nome for nome, r in resumo.items() if r['previsto'] and r['preco'] is None]
    subtotal = sum((r['custo'] for r in resumo.values() if r['custo'] is not None), Decimal('0'))
    conhecido = any(r['preco'] is not None and r['previsto'] for r in resumo.values())
    subtotal_texto = ('R$ ' + numero(subtotal) + (' (parcial)' if faltantes else '')) if conhecido else 'Aguardando preços'
    html = f'''<h2>{situacao} · {prontos} de {len(itens)} arquivos produzidos</h2>
        <p><b>{pendentes} pendente(s).</b> Posição do cliente no momento da emissão.
        Os arquivos produzidos estão indicados como PRONTOS na demonstração.</p>
        <h2>Consumo e custo por material</h2>
        <table><tr><th>Material</th><th>Previsto<br>m²</th><th>Produzido<br>m²</th><th>Pendente<br>m²</th>
        <th>Preço / m²</th><th>Custo produzido</th></tr>{''.join(linhas)}</table>
        <p class="nota">Áreas de arte de exemplo, com as quantidades de cada peça.
        Perdas, sobras e conversões de rolos/chapas não estão incluídas nesta simulação.
        O consumo fica separado por material, sem somar m² de materiais diferentes.</p>
        <h2>Resumo financeiro</h2><table>
        <tr><td>Subtotal dos materiais produzidos com preço</td><td>{subtotal_texto}</td></tr>
        <tr><td>Tinta por máquina e cor</td><td>A apurar nesta demonstração</td></tr>
        <tr><td><b>Total de materiais + tinta</b></td><td class="pendente"><b>INCOMPLETO — aguardando valores</b></td></tr></table>
        <p class="pendente">Preços pendentes: {escape(', '.join(faltantes)) if faltantes else 'nenhum material'}.
        Tinta: aguardando apuração. Concluir a produção não completa preços ausentes.</p>
        <h2>Prestação de contas para a diretoria</h2>
        <p>Este PDF inclui o resumo financeiro, consumo previsto e produzido por material,
        situação dos trabalhos, prévias das artes e relação dos arquivos na pasta PRONTOS.</p>
        <p class="nota">DADOS FICTÍCIOS — prévia para aprovação. Preço ausente não equivale a custo zero.
        Não inclui mão de obra nem outros custos operacionais. Novas artes atualizam o total previsto;
        o produzido aumenta quando o material é concluído.</p>'''
    css = '''body {font-family:sans-serif;font-size:9pt;color:#333;margin:0;}
        h2 {font-size:11pt;color:#174d7a;margin:12pt 0 8pt;}
        p {line-height:1.4;margin:7pt 0;}
        table {border-collapse:collapse;width:100%;font-size:8.5pt;}
        td,th {padding:9pt 5pt;text-align:left;border-bottom:0.5pt solid #ddd;}
        th {background:#e6f1fb;color:#174d7a;}
        .nota {font-size:8pt;color:#666;} .pendente {color:#986014;}'''
    _, escala = pagina.insert_htmlbox(pymupdf.Rect(MARGEM_OS, y, LARGURA_OS - MARGEM_OS, 800), html, css=css)
    if escala < 1:
        pdf.close()
        raise ValueError('A prévia de custos precisa de mais espaço para manter a letra legível.')
    # Detalhamento por trabalho, com a mesma arte ilustrativa da tela.
    for obra in dict.fromkeys(i['obra'] for i in itens):
        grupo = [i for i in itens if i['obra'] == obra]
        for inicio in range(0, len(grupo), 5):
            pagina, y = nova_pagina()
            detalhes = []
            for item in grupo[inicio:inicio + 5]:
                status = 'Produzido • PRONTOS' if item['pronto'] else 'Pendente'
                area = Decimal(str(item['area_un'])) * item['qtd']
                detalhes.append(f'<tr><td style="background:#e6f1fb;color:#174d7a;width:100pt;">'
                                f'<b>{escape(item["arte"])}</b><br><span class="nota">ARTE ILUSTRATIVA</span></td>'
                                f'<td><b>{escape(item["arquivo"])}</b><br>{escape(item["material"])} · '
                                f'{item["qtd"]} un · {escape(item["medida"])}<br>{numero(area)} m² · {status}</td></tr>')
            subtotal_obra = resumo_consumo(grupo, precos)
            linhas_obra = ''.join(f'<tr><td>{escape(m)}</td><td>{numero(r["previsto"])} m² previsto</td>'
                                 f'<td>{numero(r["produzido"])} m² produzido</td></tr>'
                                 for m, r in subtotal_obra.items() if r['previsto'])
            conteudo = (f'<h2>{escape(obra)}</h2><p>{sum(i["pronto"] for i in grupo)} de {len(grupo)} arquivos produzidos</p>'
                        f'<table>{"".join(detalhes)}</table><h2>Subtotal por material deste trabalho</h2>'
                        f'<table>{linhas_obra}</table><p class="nota">DADOS FICTÍCIOS — prévia para aprovação.</p>')
            _, escala = pagina.insert_htmlbox(pymupdf.Rect(MARGEM_OS, y, LARGURA_OS-MARGEM_OS, 800), conteudo, css=css)
            if escala < 1:
                pdf.close()
                raise ValueError('Detalhamento não coube na página da prévia.')
    for indice in range(len(pdf)):
        pdf[indice].insert_text((MARGEM_OS, 818), f'PREVIA - {indice+1}/{len(pdf)}', fontsize=8)
    return pdf


class Previa(tk.Tk):
    def __init__(self):
        super().__init__()
        tema.aplicar_padroes(self)
        self.title('PRÉVIA • Material em produção — Uny CV')
        altura = min(970, self.winfo_screenheight() - 90)
        self.geometry(f'1420x{altura}+35+20')
        self.minsize(1120, 680)
        self.configure(bg=cores.fundo)
        self.iconbitmap(str(BASE / 'assets' / 'uny_cv.ico'))
        self.cliente = 'Cliente Aurora'
        self.trabalho = tk.StringVar(value='Todos os trabalhos')
        self.filtro = tk.StringVar(value='Todos')
        self.busca = tk.StringVar()
        self.aviso = tk.StringVar(value='Prévia com dados fictícios. Você pode navegar e simular a conclusão dos materiais.')
        self.dados = {}
        for cliente in ('Cliente Aurora', 'Cliente Horizonte', 'Cliente Studio'):
            self.dados[cliente] = [
                dict(arquivo='1UN LONA 3X2M PAINEL.pdf', obra='Feira de outubro', material='LONA',
                     medida='3,00 × 2,00 m', qtd=1, pronto=False, arte='BEM-VINDOS', novo=True),
                dict(arquivo='2UN ADESIVO 1X0,5M BALCAO.pdf', obra='Feira de outubro', material='ADESIVO',
                     medida='1,00 × 0,50 m', qtd=2, pronto=False, arte='CONHEÇA AS NOVIDADES', novo=False),
                dict(arquivo='1UN PS 1X2M TOTEM.pdf', obra='Feira de outubro', material='PS',
                     medida='1,00 × 2,00 m', qtd=1, pronto=True, arte='ENTRADA', novo=False),
                dict(arquivo='1UN LONA 4X1M FACHADA.pdf', obra='Campanha da loja', material='LONA',
                     medida='4,00 × 1,00 m', qtd=1, pronto=False, arte='NOVA COLEÇÃO', novo=False),
                dict(arquivo='3UN ADESIVO 0,5X0,5M VITRINE.pdf', obra='Campanha da loja', material='ADESIVO',
                     medida='0,50 × 0,50 m', qtd=3, pronto=True, arte='CHEGOU!', novo=False),
            ]
            for item, area_un in zip(self.dados[cliente], [6, 0.5, 2, 4, 0.25]):
                item['area_un'] = area_un
        self.precos_previa = {}  # Nenhum preço real presumido ou cadastrado.
        self.pastas = {nome: str(PureWindowsPath(r'\\SERVIDOR\Producao') / nome)
                       for nome in self.dados}
        self.endereco = tk.StringVar(value=self.pastas[self.cliente])
        self.marcados = {nome: set() for nome in self.dados}
        self.automatico = tk.BooleanVar(value=True)
        self.pagina = 'Material em produção'
        self.selecionado = 0
        self.montar()

    def montar(self):
        for filho in self.winfo_children():
            filho.destroy()
        faixa = tk.Frame(self, bg=cores.marcado)
        faixa.pack(fill='x')
        texto(faixa, 'PRÉVIA PARA APROVAÇÃO  •  dados fictícios', 9, cores.acento,
              negrito=True).pack(side='left', padx=20, pady=8)
        for nome in ('Tela inicial', 'Material em produção', 'CONSUMO E CUSTO'):
            botao(faixa, nome, lambda n=nome: self.ir(n), self.pagina == nome).pack(side='left', padx=4, pady=5)
        botao(faixa, 'Claro / escuro', self.trocar_tema).pack(side='right', padx=12)
        rodape = tk.Frame(self, bg=cores.fundo)
        rodape.pack(side='bottom', fill='x', padx=22, pady=9)
        texto(rodape, '', 9, cores.texto2, textvariable=self.aviso).pack(anchor='w')
        self.corpo = tk.Frame(self, bg=cores.fundo)
        self.corpo.pack(fill='both', expand=True)
        if self.pagina == 'Tela inicial':
            self.inicial()
        elif self.pagina == 'CONSUMO E CUSTO':
            self.consumo_custo()
        else:
            self.producao()

    def ir(self, nome):
        self.pagina = nome
        self.montar()

    def trocar_tema(self):
        cores.trocar('claro' if cores.escuro else 'escuro')
        tema.aplicar_padroes(self)
        self.configure(bg=cores.fundo)
        self.montar()

    def cabecalho(self, titulo, subtitulo):
        topo = tk.Frame(self.corpo, bg=cores.fundo)
        topo.pack(fill='x', padx=22, pady=(16, 12))
        placa = tema.placa_logo(topo)
        if placa:
            placa.pack(side='left', padx=(0, 14))
        titulos = tk.Frame(topo, bg=cores.fundo)
        titulos.pack(side='left')
        texto(titulos, titulo, 18, negrito=True).pack(anchor='w')
        texto(titulos, subtitulo, 10, cores.texto2).pack(anchor='w', pady=(3, 0))
        return topo

    def inicial(self):
        self.cabecalho('Gerador de etiquetas', 'Etiquetas, OS e retirada de material a partir de uma pasta de artes')
        gerar = cartao(self.corpo)
        gerar.pack(fill='x', padx=22, pady=(0, 12))
        texto(gerar, 'GERAR', 8, cores.texto2, True).pack(anchor='w', padx=16, pady=10)
        campos = tk.Frame(gerar, bg=cores.cartao)
        campos.pack(fill='x', padx=16)
        for nome, valor in [('Pasta de entrada (PDFs)', 'Pasta de artes do cliente'), ('Cliente', 'Cliente Aurora'),
                            ('Gerente operacional', ''), ('Produtor responsável', '')]:
            coluna = tk.Frame(campos, bg=cores.cartao)
            coluna.pack(side='left', fill='x', expand=True, padx=(0, 14))
            texto(coluna, nome, 9, cores.texto2).pack(anchor='w')
            campo = tk.Entry(coluna, relief='flat', font=('Segoe UI', 10), width=24)
            campo.insert(0, valor)
            campo.pack(fill='x', ipady=6, pady=5)
        botao(gerar, '▶   Processar etiquetas', lambda: None, True).pack(anchor='w', padx=16, pady=14)
        atalhos = cartao(self.corpo)
        atalhos.pack(fill='x', padx=22, pady=(0, 12))
        texto(atalhos, 'ATALHOS', 8, cores.texto2, True).pack(anchor='w', padx=16, pady=10)
        grade = tk.Frame(atalhos, bg=cores.cartao)
        grade.pack(fill='x', padx=12, pady=(0, 12))
        nomes = [('Receber artes', 'Drive, WeTransfer, pasta ou ZIP'),
                 ('Montar arte para impressão', 'encaixa as artes na bobina da máquina'),
                 ('Clientes', 'recebimento de artes por cliente'),
                 ('Controle de estoque', 'material, entradas e saídas'),
                 ('Agentes', 'o que roda sozinho'), ('Medidas de rolos e chapas', 'configuração'),
                 ('Enviar para impressão', 'seleciona e envia arquivos em lote'),
                 ('Imprimir documentos', 'etiquetas, OS e retirada do pedido'),
                 ('Material em produção', 'por cliente • prévias • produzidos • relatório')]
        for i, (nome, descricao) in enumerate(nomes):
            item = cartao(grade)
            item.grid(row=i // 3, column=i % 3, sticky='nsew', padx=4, pady=4)
            novo = nome == 'Material em produção'
            item.configure(highlightbackground=cores.acento if novo else cores.borda)
            titulo = texto(item, nome, 10, cores.acento if novo else cores.texto, True)
            titulo.pack(anchor='w', padx=12, pady=(10, 2))
            sub = texto(item, descricao, 9, cores.texto2)
            sub.pack(anchor='w', padx=12, pady=(0, 12))
            if novo:
                for w in (item, titulo, sub):
                    w.configure(cursor='hand2')
                    w.bind('<Button-1>', lambda e: self.ir('Material em produção'))
        for i in range(3):
            grade.columnconfigure(i, weight=1, uniform='atalho')
        log = cartao(self.corpo)
        log.pack(fill='both', expand=True, padx=22)
        texto(log, 'O QUE ESTÁ ACONTECENDO', 8, cores.texto2, True).pack(anchor='w', padx=16, pady=10)
        texto(log, 'Pronto para iniciar.  •  Prévia da nova posição do atalho.', 10, cores.positivo).pack(anchor='w', padx=16)

    def producao(self):
        topo = self.cabecalho('Material em produção', 'Selecione o cliente, confira a arte e registre o que já foi produzido.')
        botao(topo, 'Gerar relatório', self.relatorio).pack(side='right')
        area = tk.Frame(self.corpo, bg=cores.fundo)
        area.pack(fill='both', expand=True, padx=22)
        clientes = cartao(area)
        clientes.pack(side='left', fill='y', padx=(0, 14))
        texto(clientes, 'CLIENTES EM ANDAMENTO', 9, cores.texto2, True).pack(anchor='w', padx=14, pady=16)
        texto(clientes, f'{len(self.dados)} clientes • pastas vinculadas', 9, cores.texto2).pack(anchor='w', padx=14, pady=(0, 10))
        for nome, itens in self.dados.items():
            pendentes = sum(not i['pronto'] for i in itens)
            botao(clientes, f'{nome}\n{pendentes} pendentes · {len(itens)-pendentes} prontos',
                  lambda n=nome: self.escolher_cliente(n), nome == self.cliente).pack(fill='x', padx=10, pady=5)
        botao(clientes, '+ Vincular outra pasta', self.nova_pasta).pack(fill='x', padx=10, pady=14)
        texto(clientes, 'Cole a pasta já criada pela equipe.\nCada cliente tem sua seleção\ne seu destino PRONTOS.', 9, cores.texto2,
              justify='left').pack(side='bottom', anchor='w', padx=14, pady=18)
        principal = tk.Frame(area, bg=cores.fundo)
        principal.pack(side='left', fill='both', expand=True)
        faixa = cartao(principal)
        faixa.pack(fill='x', pady=(0, 10))
        texto(faixa, self.cliente, 15, negrito=True).pack(side='left', padx=14, pady=12)
        tk.Checkbutton(faixa, text='Atualizar lista automaticamente', variable=self.automatico,
                       bg=cores.cartao, font=('Segoe UI', 9)).pack(side='right', padx=10)
        botao(faixa, 'Atualizar agora', self.atualizar).pack(side='right', padx=8, pady=6)
        pasta = cartao(principal)
        pasta.pack(fill='x', pady=(0, 10))
        texto(pasta, 'ENDEREÇO DA PASTA DO CLIENTE', 9, cores.texto2, True).pack(anchor='w', padx=12, pady=(8, 4))
        entrada = tk.Frame(pasta, bg=cores.cartao)
        entrada.pack(fill='x', padx=12)
        botao(entrada, 'Ler pasta', self.ler_pasta, True).pack(side='right', padx=(10, 0))
        self.campo_pasta = tk.Entry(entrada, textvariable=self.endereco, font=('Segoe UI', 11),
                                   relief='flat', bg=cores.campo, fg=cores.texto,
                                   insertbackground=cores.texto, highlightthickness=1,
                                   highlightbackground=cores.borda)
        self.campo_pasta.pack(side='left', fill='x', expand=True, ipady=8)
        self.campo_pasta.bind('<Return>', lambda e: self.ler_pasta())
        texto(pasta, 'Pasta já criada por outra pessoa • cole o caminho local, de rede ou do OneDrive sincronizado.',
              9, cores.texto2).pack(anchor='w', padx=12, pady=(4, 8))
        filtros = tk.Frame(principal, bg=cores.fundo)
        filtros.pack(fill='x', pady=(0, 10))
        texto(filtros, 'Trabalho / OS', 9, cores.texto2).pack(side='left')
        obras = ttk.Combobox(filtros, textvariable=self.trabalho, state='readonly', width=22,
                            values=['Todos os trabalhos', 'Feira de outubro', 'Campanha da loja'])
        obras.pack(side='left', padx=8)
        obras.bind('<<ComboboxSelected>>', lambda e: self.preencher())
        for nome in ('Todos', 'Pendentes', 'Produzidos'):
            tk.Radiobutton(filtros, text=nome, variable=self.filtro, value=nome, command=self.preencher,
                           bg=cores.fundo, font=('Segoe UI', 9)).pack(side='left', padx=3)
        pendentes = sum(not i['pronto'] for i in self.dados[self.cliente])
        self.resumo = texto(principal, f'{len(self.dados[self.cliente])} arquivos  •  {pendentes} pendentes  •  '
                            f'{len(self.dados[self.cliente])-pendentes} produzidos  •  Atualização da lista: demonstração',
                            10, cores.texto2)
        self.resumo.pack(anchor='w', pady=(0, 10))
        lote = cartao(principal)
        lote.pack(side='bottom', fill='x', pady=(10, 0))
        self.btn_lote = botao(lote, 'Mover selecionados para PRONTOS', self.concluir, True)
        self.btn_lote.pack(side='right', padx=12, pady=12)
        selecao = tk.Frame(lote, bg=cores.cartao)
        selecao.pack(side='left', fill='both', expand=True, padx=12, pady=6)
        self.todos_marcados = tk.BooleanVar(value=False)
        self.check_todos = tk.Checkbutton(selecao, text='Marcar pendentes visíveis', variable=self.todos_marcados,
                       command=self.marcar_visiveis, bg=cores.cartao, font=('Segoe UI', 10))
        self.check_todos.pack(anchor='w')
        self.contagem = texto(selecao, '', 9, cores.texto2)
        self.contagem.pack(anchor='w')
        miolo = tk.Frame(principal, bg=cores.fundo)
        miolo.pack(fill='both', expand=True)
        tabela = cartao(miolo)
        tabela.pack(side='left', fill='both', expand=True, padx=(0, 12))
        texto(tabela, 'MARQUE O QUE JÁ FOI PRODUZIDO', 9, cores.texto2, True).pack(anchor='w', padx=12, pady=10)
        self.arvore = ttk.Treeview(tabela, columns=('marcar', 'arquivo', 'obra', 'status'), show='headings', selectmode='browse')
        for chave, titulo, largura in [('marcar', '✓', 36), ('arquivo', 'Arquivo', 250), ('obra', 'Trabalho', 115), ('status', 'Situação / pasta', 165)]:
            self.arvore.heading(chave, text=titulo)
            self.arvore.column(chave, width=largura, minwidth=36 if chave == 'marcar' else 80,
                               stretch=chave != 'marcar', anchor='center' if chave == 'marcar' else 'w')
        ttk.Style(self).configure('Treeview', rowheight=46, font=('Segoe UI', 9))
        self.arvore.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.arvore.bind('<<TreeviewSelect>>', self.selecionar)
        self.arvore.bind('<Button-1>', self.clicar_checkbox)
        self.arvore.bind('<space>', self.marcar_foco)
        self.arvore.tag_configure('pronto', foreground=cores.positivo)
        texto(tabela, '☐ / ☑ marca o lote • clicar no nome abre a prévia', 9, cores.texto2).pack(anchor='w', padx=12, pady=(0, 8))
        self.painel = cartao(miolo)
        self.painel.configure(width=322)
        self.painel.pack(side='left', fill='y')
        self.painel.pack_propagate(False)
        self.preencher()

    def escolher_cliente(self, nome):
        self.cliente = nome
        self.endereco.set(self.pastas[nome])
        self.selecionado = 0
        self.trabalho.set('Todos os trabalhos')
        self.filtro.set('Todos')
        self.montar()

    def preencher(self):
        self.arvore.delete(*self.arvore.get_children())
        ids = []
        for i, item in enumerate(self.dados[self.cliente]):
            if self.trabalho.get() != 'Todos os trabalhos' and item['obra'] != self.trabalho.get():
                continue
            if self.filtro.get() == 'Pendentes' and item['pronto']:
                continue
            if self.filtro.get() == 'Produzidos' and not item['pronto']:
                continue
            status = 'Produzido • PRONTOS' if item['pronto'] else ('NOVO · Pendente' if item['novo'] else 'Pendente')
            marca = '—' if item['pronto'] else ('☑' if i in self.marcados[self.cliente] else '☐')
            self.arvore.insert('', 'end', iid=str(i), values=(marca, item['arquivo'], item['obra'], status),
                               tags=('pronto',) if item['pronto'] else ())
            ids.append(str(i))
        if ids:
            alvo = str(self.selecionado) if str(self.selecionado) in ids else ids[0]
            self.arvore.selection_set(alvo)
            self.selecionado = int(alvo)
            self.previa_arte()
        else:
            for w in self.painel.winfo_children():
                w.destroy()
            texto(self.painel, 'Nenhum arquivo neste filtro.', 11).pack(pady=30)
        self.atualizar_lote()

    def atualizar_lote(self):
        marcados = self.marcados[self.cliente]
        quantidade = len(marcados)
        visiveis = {int(i) for i in self.arvore.get_children() if not self.dados[self.cliente][int(i)]['pronto']}
        self.todos_marcados.set(bool(visiveis) and visiveis.issubset(marcados))
        self.check_todos.configure(state='normal' if visiveis else 'disabled')
        ocultos = len(marcados - visiveis)
        complemento = f' • {ocultos} fora do filtro atual' if ocultos else ''
        self.contagem.configure(text=f'{quantidade} selecionado(s){complemento} • marcar não move o arquivo')
        self.btn_lote.configure(text=f'Mover {quantidade} selecionado(s) para PRONTOS',
                                state='normal' if quantidade else 'disabled')

    def alternar_marcado(self, indice):
        if self.dados[self.cliente][indice]['pronto']:
            return
        marcados = self.marcados[self.cliente]
        if indice in marcados:
            marcados.remove(indice)
        else:
            marcados.add(indice)
        self.arvore.set(str(indice), 'marcar', '☑' if indice in marcados else '☐')
        self.atualizar_lote()

    def clicar_checkbox(self, evento):
        linha = self.arvore.identify_row(evento.y)
        if linha and self.arvore.identify_column(evento.x) == '#1':
            self.alternar_marcado(int(linha))
            self.arvore.selection_set(linha)
            self.arvore.focus(linha)
            return 'break'

    def marcar_foco(self, evento):
        if self.arvore.selection():
            self.alternar_marcado(int(self.arvore.selection()[0]))
        return 'break'

    def marcar_visiveis(self):
        marcar = self.todos_marcados.get()
        for linha in self.arvore.get_children():
            indice = int(linha)
            if not self.dados[self.cliente][indice]['pronto']:
                if marcar:
                    self.marcados[self.cliente].add(indice)
                else:
                    self.marcados[self.cliente].discard(indice)
                self.arvore.set(linha, 'marcar', '☑' if marcar else '☐')
        self.atualizar_lote()

    def nova_pasta(self):
        self.endereco.set('')
        self.campo_pasta.focus_set()
        self.aviso.set('Cole o endereço da pasta e clique em Ler pasta. Nesta prévia, a leitura será apenas simulada.')

    def ler_pasta(self):
        endereco = self.endereco.get().strip().strip('"')
        if not endereco:
            self.aviso.set('Informe o endereço da pasta do cliente.')
            self.campo_pasta.focus_set()
            return
        if '://' in endereco:
            self.aviso.set('Use o caminho da pasta no computador ou na rede; para OneDrive, use a pasta sincronizada.')
            return
        pasta = PureWindowsPath(endereco)
        if not pasta.name:
            self.aviso.set('Informe a pasta do cliente, e não apenas a raiz da unidade.')
            return
        nome = next((n for n, p in self.pastas.items() if PureWindowsPath(p) == pasta), pasta.name)
        if nome not in self.dados:
            self.dados[nome] = deepcopy(next(iter(self.dados.values())))
            for item in self.dados[nome]:
                item['pronto'] = False
            self.marcados[nome] = set()
        self.pastas[nome] = str(pasta)
        self.aviso.set(f'SIMULAÇÃO: pasta vinculada a {nome}. Arquivos ilustrativos; nenhuma pasta real foi lida ou criada.')
        self.escolher_cliente(nome)

    def selecionar(self, evento=None):
        if self.arvore.selection():
            self.selecionado = int(self.arvore.selection()[0])
            self.previa_arte()

    def previa_arte(self):
        for w in self.painel.winfo_children():
            w.destroy()
        item = self.dados[self.cliente][self.selecionado]
        texto(self.painel, 'PRÉVIA DO MATERIAL', 9, cores.texto2, True).pack(anchor='w', padx=14, pady=8)
        arte = tk.Canvas(self.painel, width=288, height=108, bg=cores.previa, highlightthickness=0)
        arte.pack(padx=14, pady=(0, 6))
        arte.create_rectangle(12, 4, 276, 104, fill=cores.acento, outline='')
        arte.create_text(28, 22, text=self.cliente.upper(), anchor='w', fill=cores.sobre_acento, font=('Segoe UI', 10, 'bold'))
        arte.create_text(28, 56, text=item['arte'], anchor='w', width=230, fill=cores.sobre_acento, font=('Segoe UI', 16, 'bold'))
        arte.create_text(28, 91, text='ARTE ILUSTRATIVA • PRÉVIA', anchor='w', fill=cores.sobre_acento, font=('Segoe UI', 8))
        texto(self.painel, item['arquivo'], 10, negrito=True, wraplength=288, justify='left').pack(anchor='w', padx=14)
        texto(self.painel, f"{item['obra']}\n{item['material']}  •  {item['qtd']} un  •  {item['medida']}",
              9, cores.texto2, justify='left').pack(anchor='w', padx=14, pady=5)
        texto(self.painel, '✓ Produzido • em PRONTOS' if item['pronto'] else '● Pendente de produção',
              10, cores.positivo if item['pronto'] else cores.alerta).pack(anchor='w', padx=14)
        ampliar = botao(self.painel, 'Ampliar prévia', self.ampliar)
        ampliar.configure(pady=4)
        ampliar.pack(fill='x', padx=14, pady=6)
        texto(self.painel, 'Destino do lote: ' + str(PureWindowsPath(self.pastas[self.cliente]) / 'PRONTOS'),
              9, cores.texto2, wraplength=288, justify='left').pack(anchor='w', padx=14)

    def ampliar(self):
        janela = tk.Toplevel(self)
        janela.title('Prévia ampliada • arte ilustrativa')
        janela.geometry('760x440')
        item = self.dados[self.cliente][self.selecionado]
        tela = tk.Canvas(janela, bg=cores.acento, highlightthickness=0)
        tela.pack(fill='both', expand=True, padx=24, pady=24)
        tela.create_text(35, 55, text=self.cliente.upper(), anchor='w', font=('Segoe UI', 18), fill=cores.sobre_acento)
        tela.create_text(35, 160, text=item['arte'], anchor='w', font=('Segoe UI', 32, 'bold'), fill=cores.sobre_acento)
        tela.create_text(35, 330, text=item['arquivo'], anchor='w', font=('Segoe UI', 12), fill=cores.sobre_acento)

    def concluir(self):
        indices = sorted(self.marcados[self.cliente])
        if not indices:
            return
        for indice in indices:
            self.dados[self.cliente][indice]['pronto'] = True
        self.marcados[self.cliente].clear()
        self.selecionado = indices[0]
        self.filtro.set('Todos')
        self.trabalho.set('Todos os trabalhos')
        self.aviso.set(f'SIMULAÇÃO: {len(indices)} arquivo(s) → PRONTOS. CONSUMO E CUSTO atualizado para {self.cliente}. Nenhum arquivo real foi movido.')
        self.montar()

    def atualizar(self):
        self.aviso.set('Atualização simulada: artes novas entram como pendentes; os materiais produzidos continuam registrados.')
        self.montar()

    def relatorio(self):
        janela = tk.Toplevel(self)
        janela.title(f'Prévia do relatório — {self.cliente}')
        janela.geometry('830x600')
        texto(janela, f'Relatório de produção • {self.cliente}', 17, negrito=True).pack(anchor='w', padx=22, pady=18)
        texto(janela, 'Modelo ilustrativo • arquivos, prévias e situação por trabalho', 10, cores.texto2).pack(anchor='w', padx=22)
        for item in self.dados[self.cliente]:
            linha = cartao(janela)
            linha.pack(fill='x', padx=22, pady=8)
            mini = tk.Canvas(linha, width=95, height=60, bg=cores.acento, highlightthickness=0)
            mini.pack(side='left', padx=10, pady=10)
            mini.create_text(47, 30, text=item['arte'], width=88, font=('Segoe UI', 8, 'bold'), fill=cores.sobre_acento)
            texto(linha, f"{item['arquivo']}\n{item['obra']}  •  {item['material']}  •  {item['qtd']} un", 10, justify='left').pack(side='left')
            texto(linha, 'Produzido • PRONTOS' if item['pronto'] else 'Pendente', 10,
                  cores.positivo if item['pronto'] else cores.alerta).pack(side='right', padx=16)

    def consumo_custo(self):
        topo = self.cabecalho('CONSUMO E CUSTO', f'{self.cliente} • atualizado conforme os materiais entram em PRONTOS.')
        botao(topo, 'GERAR PDF', self.exportar_pdf, True).pack(side='right')
        miolo = tk.Frame(self.corpo, bg=cores.fundo)
        miolo.pack(fill='both', expand=True, padx=22)
        explicacao = cartao(miolo)
        explicacao.pack(side='left', fill='y', padx=(0, 18))
        texto(explicacao, 'SELECIONE O CLIENTE', 11, cores.acento, True).pack(anchor='w', padx=18, pady=(18, 8))
        self.cliente_custo = tk.StringVar(value=self.cliente)
        seletor = ttk.Combobox(explicacao, textvariable=self.cliente_custo, state='readonly',
                               values=list(self.dados), width=23, font=('Segoe UI', 10))
        seletor.pack(fill='x', padx=18, pady=(0, 14))
        seletor.bind('<<ComboboxSelected>>', lambda e: self.escolher_cliente(self.cliente_custo.get()))
        texto(explicacao, 'Todos os trabalhos deste cliente.', 9, cores.texto2,
              wraplength=250, justify='left').pack(anchor='w', padx=18, pady=(0, 8))
        for frase in ('1. Confira a prévia da arte.', '2. Mova o lote para PRONTOS.',
                      '3. Consumo produzido atualizado.', '4. Gere o PDF para a diretoria.'):
            texto(explicacao, frase, 10, wraplength=235, justify='left').pack(anchor='w', padx=18, pady=10)
        botao(explicacao, 'Ir para Material em produção', lambda: self.ir('Material em produção')).pack(fill='x', padx=14, pady=18)
        botao(explicacao, 'Prévia do PDF completo', self.abrir_pdf_previa).pack(fill='x', padx=14, pady=(0, 12))
        texto(explicacao, 'Sem preço: A cadastrar.\nO PDF indica valores pendentes.\nNenhum custo ausente vira zero.',
              9, cores.texto2, justify='left').pack(anchor='w', padx=18, pady=10)
        principal = tk.Frame(miolo, bg=cores.fundo)
        principal.pack(side='left', fill='both', expand=True)
        itens = self.dados[self.cliente]
        prontos = sum(i['pronto'] for i in itens)
        pendentes = len(itens) - prontos
        resumo = resumo_consumo(itens, self.precos_previa)
        faltantes = [m for m, r in resumo.items() if r['previsto'] and r['preco'] is None]
        contadores = tk.Frame(principal, bg=cores.fundo)
        contadores.pack(fill='x', pady=(0, 12))
        for valor, legenda, cor in [(f'{prontos} de {len(itens)}', 'Arquivos produzidos • PRONTOS', cores.positivo),
                                   (str(pendentes), 'Arquivos pendentes', cores.alerta),
                                   ('INCOMPLETO' if faltantes else 'MATERIAIS APURADOS', 'Custos • tinta ainda a apurar', cores.alerta)]:
            caixa = cartao(contadores)
            caixa.pack(side='left', fill='both', expand=True, padx=(0, 8))
            texto(caixa, valor, 18, cor, True).pack(anchor='w', padx=14, pady=(12, 4))
            texto(caixa, legenda, 9, cores.texto2).pack(anchor='w', padx=14, pady=(0, 12))
        faixa = cartao(principal)
        faixa.pack(fill='x', pady=(0, 12))
        status = 'PRODUÇÃO CONCLUÍDA' if itens and not pendentes else 'PRODUÇÃO EM ANDAMENTO'
        texto(faixa, status, 11, cores.positivo if not pendentes else cores.acento, True).pack(anchor='w', padx=14, pady=(10, 4))
        texto(faixa, 'O produzido considera os arquivos em PRONTOS. Novas artes aumentam o previsto.',
              10, cores.texto2).pack(anchor='w', padx=14, pady=(0, 10))
        tabela = cartao(principal)
        tabela.pack(fill='x', pady=(0, 12))
        texto(tabela, 'CONSUMO E CUSTO POR MATERIAL', 10, cores.texto2, True).pack(anchor='w', padx=14, pady=12)
        colunas = [('material', 'Material', 115), ('previsto', 'Previsto (m²)', 115),
                   ('produzido', 'Produzido (m²)', 125), ('pendente', 'Pendente (m²)', 125),
                   ('preco', 'Preço / m²', 120), ('custo', 'Custo produzido', 165)]
        self.tabela_consumo = ttk.Treeview(tabela, columns=[c[0] for c in colunas], show='headings', height=len(resumo))
        ttk.Style(self).configure('Treeview', rowheight=38, font=('Segoe UI', 9))
        for chave, rotulo, largura in colunas:
            self.tabela_consumo.heading(chave, text=rotulo)
            self.tabela_consumo.column(chave, width=largura, minwidth=80)
        for material, r in resumo.items():
            preco = 'A cadastrar' if r['preco'] is None else 'R$ ' + numero(Decimal(str(r['preco'])))
            custo = 'Aguardando preço' if r['custo'] is None else 'R$ ' + numero(r['custo'])
            if not r['previsto']:
                custo = 'Não utilizado'
            self.tabela_consumo.insert('', 'end', iid=material, values=(material, numero(r['previsto']),
                                      numero(r['produzido']), numero(r['pendente']), preco, custo))
        self.tabela_consumo.pack(fill='x', padx=12, pady=(0, 10))
        texto(tabela, 'Áreas ilustrativas das peças • sobras/perdas não incluídas • sem somar m² de materiais diferentes.',
              9, cores.texto2, wraplength=940, justify='left').pack(anchor='w', padx=14, pady=(0, 10))
        financeiro = cartao(principal)
        financeiro.pack(fill='both', expand=True)
        texto(financeiro, 'FECHAMENTO PARA A DIRETORIA', 10, cores.texto2, True).pack(anchor='w', padx=14, pady=12)
        conhecidos = [r for r in resumo.values() if r['previsto'] and r['custo'] is not None]
        parcial = 'R$ ' + numero(sum((r['custo'] for r in conhecidos), Decimal('0'))) if conhecidos else 'Aguardando preços'
        texto(financeiro, f'Subtotal conhecido de materiais: {parcial}', 11).pack(anchor='w', padx=14, pady=4)
        texto(financeiro, 'Tinta: a apurar  •  Total geral: incompleto', 11, cores.alerta).pack(anchor='w', padx=14, pady=4)
        texto(financeiro, 'PDF por cliente: resumo financeiro, consumo por material, trabalhos, artes e situação dos arquivos.',
              10, cores.texto2, wraplength=940, justify='left').pack(anchor='w', padx=14, pady=6)

    def exportar_pdf(self):
        nome = re.sub(r'[^\w .-]', '_', self.cliente)
        destino = filedialog.asksaveasfilename(parent=self, title='Salvar prévia para diretoria',
                    initialdir=str(Path(__file__).parent),
                    initialfile=f'PREVIA - CONSUMO E CUSTO - {nome}.pdf', defaultextension='.pdf',
                    filetypes=[('Documento PDF', '*.pdf')])
        if not destino:
            return
        try:
            with pdf_custos_previa(self.cliente, self.dados[self.cliente], self.precos_previa) as pdf:
                pdf.save(destino, garbage=4, deflate=True)
        except Exception as erro:
            messagebox.showerror('Não foi possível gerar o PDF', str(erro), parent=self)
            return
        self.aviso.set(f'PDF de demonstração gerado para {self.cliente}: {Path(destino).name}. Custos sem preço identificados como pendentes.')

    def abrir_pdf_previa(self):
        import pymupdf
        from PIL import Image, ImageTk
        janela = tk.Toplevel(self)
        janela.title(f'PRÉVIA DO PDF • CONSUMO E CUSTO • {self.cliente}')
        janela.geometry('890x900+100+30')
        moldura = tk.Frame(janela, bg=cores.previa)
        moldura.pack(fill='both', expand=True)
        barra = ttk.Scrollbar(moldura, orient='vertical')
        barra.pack(side='right', fill='y')
        papel = tk.Canvas(moldura, bg=cores.previa, highlightthickness=0, yscrollcommand=barra.set)
        papel.pack(fill='both', expand=True)
        janela.imagens = []
        y = 15
        with pdf_custos_previa(self.cliente, self.dados[self.cliente], self.precos_previa) as pdf:
            for pagina in pdf:
                pix = pagina.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25), alpha=False)
                imagem = ImageTk.PhotoImage(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
                janela.imagens.append(imagem)
                papel.create_image(20, y, image=imagem, anchor='nw')
                y += pix.height + 20
        papel.configure(scrollregion=(0, 0, pix.width + 40, y))
        barra.configure(command=papel.yview)
        papel.bind('<MouseWheel>', lambda e: papel.yview_scroll(-int(e.delta / 120), 'units'))


if __name__ == '__main__':
    previa = Previa()
    if '--capturas' in sys.argv:
        from PIL import ImageGrab

        def capturar():
            previa.marcados[previa.cliente].update({0, 1})
            previa.concluir()
            with pdf_custos_previa(previa.cliente, previa.dados[previa.cliente], previa.precos_previa) as pdf:
                pdf.save(Path(__file__).parent / 'PREVIA_DIRETORIA_CLIENTE_AURORA.pdf', garbage=4, deflate=True)
            telas = [('CONSUMO E CUSTO', '08_consumo_atualizado_pdf_diretoria.png')]
            previa.deiconify()
            previa.attributes('-topmost', True)

            def proxima(indice):
                if indice >= len(telas):
                    previa.attributes('-topmost', False)
                    previa.focus_force()
                    return
                pagina, arquivo = telas[indice]
                previa.ir(pagina)
                previa.update()
                previa.lift()

                def salvar():
                    x, y = previa.winfo_rootx(), previa.winfo_rooty()
                    ImageGrab.grab(bbox=(x, y, x + previa.winfo_width(), y + previa.winfo_height())).save(Path(__file__).parent / arquivo)
                    proxima(indice + 1)

                previa.after(500, salvar)

            proxima(0)

        previa.after(1000, capturar)
    previa.mainloop()
