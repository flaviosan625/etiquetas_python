"""Material em produção e consumo/custo reais, no tema do sistema.

I/O, miniaturas e PDF fora da thread do Tk. A seleção nunca move arquivos:
somente o botão de concluir o lote chama material_producao.mover_lote.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import config
import consumo_custo
import custos
import dimensoes
import material_producao as servico
import miniaturas
import tema
from tema import cores
from utils import sanitizar_nome_arquivo


def _texto(pai, texto='', tamanho=10, cor=None, negrito=False, **kw):
    return tk.Label(pai, text=texto, bg=pai.cget('bg'), fg=cor or cores.texto,
                    font=('Segoe UI', tamanho, 'bold' if negrito else 'normal'), **kw)


def _botao(pai, nome, acao, principal=False):
    return tk.Button(pai, text=nome, command=acao, bg=cores.acento if principal else cores.borda,
                     fg=cores.sobre_acento if principal else cores.texto, relief='flat',
                     activebackground=cores.acento_claro, padx=12, pady=7, cursor='hand2', font=('Segoe UI', 10))


def _cartao(pai):
    return tk.Frame(pai, bg=cores.cartao, highlightbackground=cores.borda, highlightthickness=1)


def ler_cliente(vinculos, cliente):
    configuracao = config.carregar_config()
    itens = []
    for vinculo in vinculos:
        if vinculo['cliente'] == cliente:
            itens.extend(servico.inventariar(vinculo, configuracao))
    return itens, configuracao, consumo_custo.calcular(itens, configuracao)


class JanelaMaterialProducao(tk.Toplevel):
    def __init__(self, pai):
        super().__init__(pai)
        self.title('Material em produção — Uny CV')
        self.geometry(f'{min(1450, self.winfo_screenwidth()-70)}x{min(920, self.winfo_screenheight()-90)}')
        self.minsize(1000, 620)
        self.configure(bg=cores.fundo)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='controle_producao')
        self.eventos = queue.Queue()
        self.fechar = False
        self.ocupado = False
        self.atualizando = False
        self.versao = 0
        self.vinculos, self.itens, self.resumo, self.configuracao = [], [], {}, {}
        self.cliente = ''
        self.marcados = {}
        self.cache = OrderedDict()
        self.chave_previa = None
        self.foto = None
        self.var_pasta = tk.StringVar()
        self.var_obra = tk.StringVar(value='Todos os trabalhos')
        self.var_filtro = tk.StringVar(value='Todos')
        self.var_busca = tk.StringVar()
        self.var_auto = tk.BooleanVar(value=True)
        self.var_status = tk.StringVar(value='Carregando clientes e pastas vinculadas…')
        self.var_todos = tk.BooleanVar(value=False)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self._montar()
        self._agendamento = self.after(100, self._eventos)
        self._auto_id = self.after(15000, self._automatico)
        self._rodar('cadastro', servico.listar_vinculos)

    def destroy(self):
        if self.fechar:
            return
        if self.ocupado:
            self.var_status.set('Aguarde a movimentação ou a geração do PDF terminar antes de fechar.')
            return
        self.fechar = True
        for identificador in (self._agendamento, self._auto_id):
            self.after_cancel(identificador)
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()

    def _rodar(self, tipo, funcao, *args, contexto=None):
        def executar():
            try:
                self.eventos.put((tipo, contexto, funcao(*args), None))
            except Exception as erro:
                self.eventos.put((tipo, contexto, None, str(erro)))
        self.executor.submit(executar)

    def _eventos(self):
        if self.fechar:
            return
        try:
            while True:
                tipo, contexto, resultado, erro = self.eventos.get_nowait()
                self._receber(tipo, contexto, resultado, erro)
        except queue.Empty:
            pass
        self._agendamento = self.after(100, self._eventos)

    def _receber(self, tipo, contexto, resultado, erro):
        if tipo == 'scan':
            self.atualizando = False
            if contexto != (self.cliente, self.versao):
                self.atualizar()
                return
        if tipo in ('mover', 'pdf', 'vincular'):
            self.ocupado = False
        if erro:
            self.var_status.set('Falha: ' + erro)
            if tipo != 'previa':
                messagebox.showerror('Material em produção', erro, parent=self)
            self._lote()
            return
        if tipo == 'cadastro':
            self.vinculos = resultado
            self._clientes()
        elif tipo == 'vincular':
            self.cliente = resultado['cliente']
            self._rodar('cadastro', servico.listar_vinculos)
        elif tipo == 'scan':
            itens, self.configuracao, self.resumo = resultado
            presentes = {i['id']: i for i in itens}
            antes = len(self.marcados)
            self.marcados = {k: v for k, v in self.marcados.items() if k in presentes
                             and presentes[k]['assinatura'] == v['assinatura'] and not presentes[k]['pronto']}
            self.itens = itens
            self._tabela()
            self._custos()
            self.var_status.set('Lista e consumo atualizados. ' + ('Seleções alteradas/removidas foram desmarcadas.' if antes != len(self.marcados) else ''))
        elif tipo == 'previa' and contexto == self.chave_previa:
            self._mostrar_previa(resultado)
        elif tipo == 'mover':
            self.marcados.clear()
            self.var_filtro.set('Todos')
            self.var_obra.set('Todos os trabalhos')
            self.var_status.set(f"{len(resultado['movidos'])} arquivo(s) movido(s) para PRONTOS. Atualizando consumo e custo…")
            if resultado['erros']:
                messagebox.showwarning('Resultado do lote', '\n'.join(f"{e['arquivo']}: {e['erro']}" for e in resultado['erros']), parent=self)
            self.atualizar()
        elif tipo == 'pdf':
            self.var_status.set('PDF gerado: ' + str(resultado))
            messagebox.showinfo('CONSUMO E CUSTO', 'PDF gerado:\n' + str(resultado), parent=self)
        self._lote()

    def _montar(self):
        topo = tk.Frame(self, bg=cores.fundo)
        topo.pack(fill='x', padx=18, pady=12)
        placa = tema.placa_logo(topo)
        if placa:
            placa.pack(side='left', padx=(0, 14))
        textos = tk.Frame(topo, bg=cores.fundo)
        textos.pack(side='left')
        _texto(textos, 'Material em produção', 18, negrito=True).pack(anchor='w')
        self.rotulo_cliente = _texto(textos, 'Pastas existentes • controle por cliente', 10, cores.texto2)
        self.rotulo_cliente.pack(anchor='w')
        _botao(topo, 'GERAR PDF', self._exportar, True).pack(side='right')
        _texto(self, '', 9, cores.texto2, textvariable=self.var_status, anchor='w', wraplength=1300).pack(side='bottom', fill='x', padx=18, pady=8)
        area = tk.Frame(self, bg=cores.fundo)
        area.pack(fill='both', expand=True, padx=18)
        lado = _cartao(area)
        lado.pack(side='left', fill='y', padx=(0, 12))
        _texto(lado, 'CLIENTES', 10, cores.texto2, True).pack(anchor='w', padx=12, pady=12)
        self.lista_clientes = tk.Listbox(lado, width=24, exportselection=False, font=('Segoe UI', 11),
                                        relief='flat', bg=cores.campo, fg=cores.texto, selectbackground=cores.marcado,
                                        selectforeground=cores.texto, activestyle='none')
        self.lista_clientes.pack(fill='both', expand=True, padx=10, pady=4)
        self.lista_clientes.bind('<<ListboxSelect>>', self._escolher_cliente)
        _botao(lado, '+ Vincular outra pasta', self._dialogo_vinculo).pack(fill='x', padx=10, pady=12)
        self.abas = ttk.Notebook(area)
        self.abas.pack(side='left', fill='both', expand=True)
        self.aba_material = tk.Frame(self.abas, bg=cores.fundo)
        self.aba_custo = tk.Frame(self.abas, bg=cores.fundo)
        self.abas.add(self.aba_material, text='Material em produção')
        self.abas.add(self.aba_custo, text='CONSUMO E CUSTO')
        pasta = _cartao(self.aba_material)
        pasta.pack(fill='x', pady=10)
        _texto(pasta, 'ENDEREÇO DA PASTA DO CLIENTE', 9, cores.texto2, True).pack(anchor='w', padx=12, pady=(8, 3))
        linha = tk.Frame(pasta, bg=cores.cartao)
        linha.pack(fill='x', padx=12, pady=(0, 10))
        _botao(linha, 'Ler pasta', self._vincular_campo, True).pack(side='right', padx=(8, 0))
        self.entrada = tk.Entry(linha, textvariable=self.var_pasta, font=('Segoe UI', 11), relief='flat', bg=cores.campo, fg=cores.texto)
        self.entrada.pack(side='left', fill='x', expand=True, ipady=8)
        self.entrada.bind('<Return>', lambda e: self._vincular_campo())
        controles = tk.Frame(self.aba_material, bg=cores.fundo)
        controles.pack(fill='x', pady=(0, 8))
        self.obras = ttk.Combobox(controles, textvariable=self.var_obra, values=['Todos os trabalhos'], state='readonly', width=22)
        self.obras.pack(side='left')
        self.obras.bind('<<ComboboxSelected>>', lambda e: self._tabela())
        for nome in ('Todos', 'Pendentes', 'Produzidos'):
            tk.Radiobutton(controles, text=nome, variable=self.var_filtro, value=nome, command=self._tabela,
                           bg=cores.fundo, font=('Segoe UI', 9)).pack(side='left')
        _botao(controles, 'Atualizar agora', self.atualizar).pack(side='right')
        tk.Checkbutton(controles, text='Automática', variable=self.var_auto, bg=cores.fundo).pack(side='right', padx=6)
        self.contagem = _texto(self.aba_material, 'Vincule uma pasta para começar.', 10, cores.texto2)
        self.contagem.pack(anchor='w', pady=(0, 8))
        lote = _cartao(self.aba_material)
        lote.pack(side='bottom', fill='x', pady=(8, 0))
        self.botao_mover = _botao(lote, 'Mover selecionados para PRONTOS', self._mover, True)
        self.botao_mover.pack(side='right', padx=10, pady=10)
        tk.Checkbutton(lote, text='Marcar pendentes visíveis', variable=self.var_todos, command=self._marcar_todos,
                       bg=cores.cartao, font=('Segoe UI', 10)).pack(anchor='w', padx=10, pady=(6, 0))
        self.rotulo_lote = _texto(lote, '', 9, cores.texto2)
        self.rotulo_lote.pack(anchor='w', padx=10, pady=(0, 6))
        miolo = tk.Frame(self.aba_material, bg=cores.fundo)
        miolo.pack(fill='both', expand=True)
        grade = _cartao(miolo)
        grade.pack(side='left', fill='both', expand=True, padx=(0, 10))
        colunas = [('marca', '✓', 36), ('arquivo', 'Arquivo', 245), ('trabalho', 'Trabalho', 125), ('status', 'Situação / pasta', 160)]
        self.tabela = ttk.Treeview(grade, columns=[c[0] for c in colunas], show='headings', selectmode='browse')
        estilo = ttk.Style(self)
        estilo.configure('Producao.Treeview', rowheight=40, font=('Segoe UI', 9))
        self.tabela.configure(style='Producao.Treeview')
        for chave, nome, largura in colunas:
            self.tabela.heading(chave, text=nome)
            self.tabela.column(chave, width=largura, minwidth=largura if chave=='marca' else 80, stretch=chave!='marca')
        rolagem = ttk.Scrollbar(grade, orient='vertical', command=self.tabela.yview)
        rolagem.pack(side='right', fill='y')
        self.tabela.configure(yscrollcommand=rolagem.set)
        self.tabela.pack(fill='both', expand=True)
        self.tabela.tag_configure('pronto', foreground=cores.positivo)
        self.tabela.bind('<<TreeviewSelect>>', self._selecionar)
        self.tabela.bind('<Button-1>', self._clique_checkbox)
        self.tabela.bind('<space>', self._espaco)
        direita = _cartao(miolo)
        direita.configure(width=285)
        direita.pack(side='right', fill='y')
        direita.pack_propagate(False)
        _texto(direita, 'PRÉVIA DO MATERIAL', 9, cores.texto2, True).pack(anchor='w', padx=10, pady=10)
        self.imagem = _texto(direita, 'Selecione um arquivo', 10, cores.texto2)
        self.imagem.pack(padx=10, pady=5)
        self.detalhe = _texto(direita, '', 9, cores.texto, wraplength=260, justify='left')
        self.detalhe.pack(anchor='w', padx=10, pady=6)
        _botao(direita, 'Ampliar prévia', self._ampliar).pack(fill='x', padx=10, pady=6)
        self.aviso_arte = _texto(direita, '', 9, cores.alerta, wraplength=260, justify='left')
        self.aviso_arte.pack(anchor='w', padx=10, pady=4)
        self.caixa_custo = tk.Frame(self.aba_custo, bg=cores.fundo)
        self.caixa_custo.pack(fill='both', expand=True)
        self._custos()

    def _clientes(self):
        nomes = sorted({v['cliente'] for v in self.vinculos}, key=str.casefold)
        self.lista_clientes.delete(0, 'end')
        for nome in nomes:
            self.lista_clientes.insert('end', nome)
        if nomes:
            self.cliente = self.cliente if self.cliente in nomes else nomes[0]
            self.lista_clientes.selection_set(nomes.index(self.cliente))
            self._carregar_cliente()
        else:
            self.var_status.set('Cole uma pasta existente ou use “Vincular outra pasta”.')

    def _escolher_cliente(self, evento=None):
        if self.ocupado:
            return
        selecionados = self.lista_clientes.curselection()
        if selecionados:
            nome = self.lista_clientes.get(selecionados[0])
            if nome != self.cliente:
                self.cliente = nome
                self._carregar_cliente()

    def _carregar_cliente(self):
        self.versao += 1
        self.marcados.clear()
        self.itens, self.resumo = [], {}
        self.chave_previa = None
        self.imagem.configure(image='', text='Selecione um arquivo')
        self.detalhe.configure(text='')
        self.aviso_arte.configure(text='')
        self.var_obra.set('Todos os trabalhos')
        self.var_filtro.set('Todos')
        meus = [v for v in self.vinculos if v['cliente'] == self.cliente]
        self.obras.configure(values=['Todos os trabalhos'] + sorted({v['trabalho'] for v in meus}))
        self.var_pasta.set(meus[0]['pasta'] if meus else '')
        self.rotulo_cliente.configure(text=self.cliente)
        self._tabela()
        self._custos()
        self.atualizar()

    def atualizar(self):
        if self.atualizando or self.ocupado or not self.cliente:
            return
        self.atualizando = True
        self.var_status.set('Atualizando arquivos, consumo e custo…')
        self._rodar('scan', ler_cliente, list(self.vinculos), self.cliente, contexto=(self.cliente, self.versao))

    def _automatico(self):
        if self.var_auto.get():
            self.atualizar()
        self._auto_id = self.after(15000, self._automatico)

    def _vincular_campo(self):
        self._vincular(self.var_pasta.get())

    def _vincular(self, pasta, cliente='', trabalho=''):
        if self.ocupado:
            return
        self.ocupado = True
        self._rodar('vincular', servico.vincular, pasta, cliente, trabalho)

    def _dialogo_vinculo(self):
        janela = tk.Toplevel(self)
        janela.title('Vincular pasta existente')
        janela.geometry('680x300')
        janela.transient(self)
        janela.grab_set()
        variaveis = []
        for rotulo in ('Endereço da pasta', 'Cliente (opcional; vazio usa o nome da pasta)', 'Trabalho (opcional)'):
            _texto(janela, rotulo, 10).pack(anchor='w', padx=16, pady=(10, 3))
            var = tk.StringVar()
            ttk.Entry(janela, textvariable=var).pack(fill='x', padx=16)
            variaveis.append(var)
        def confirmar():
            self._vincular(*(v.get() for v in variaveis))
            janela.destroy()
        _botao(janela, 'Ler pasta', confirmar, True).pack(side='right', padx=16, pady=14)
        def escolher():
            pasta = filedialog.askdirectory(parent=janela, title='Pasta de produção já existente')
            if pasta:
                variaveis[0].set(pasta)
        _botao(janela, 'Procurar pasta…', escolher).pack(side='left', padx=16, pady=14)

    def _visiveis(self):
        return [i for i in self.itens if (self.var_obra.get() == 'Todos os trabalhos' or i['trabalho'] == self.var_obra.get())
                and (self.var_filtro.get() == 'Todos' or (i['pronto'] == (self.var_filtro.get() == 'Produzidos')))]

    def _tabela(self):
        selecionado = next(iter(self.tabela.selection()), None)
        rolagem = self.tabela.yview()[0]
        self.tabela.delete(*self.tabela.get_children())
        for item in self._visiveis():
            marca = '—' if item['pronto'] else '☑' if item['id'] in self.marcados else '☐'
            self.tabela.insert('', 'end', iid=item['id'], values=(marca, item['arquivo'], item['trabalho'], item['status']),
                               tags=('pronto',) if item['pronto'] else ())
        ids = self.tabela.get_children()
        if ids:
            self.tabela.selection_set(selecionado if selecionado in ids else ids[0])
        else:
            self.chave_previa = None
            self.imagem.configure(image='', text='Nenhum arquivo neste filtro')
            self.detalhe.configure(text='')
        self.tabela.yview_moveto(rolagem)
        prontos = sum(i['pronto'] for i in self.itens)
        self.contagem.configure(text=f'{len(self.itens)} arquivos • {len(self.itens)-prontos} pendentes • {prontos} produzidos')
        for v in self.vinculos:
            if v['cliente'] == self.cliente and v['trabalho'] == self.var_obra.get():
                self.var_pasta.set(v['pasta'])
                break
        self._lote()

    def _lote(self):
        n = len(self.marcados)
        self.botao_mover.configure(text=f'Mover {n} selecionado(s) para PRONTOS', state='normal' if n and not self.ocupado else 'disabled')
        visiveis = {i['id'] for i in self._visiveis() if not i['pronto']}
        ocultos = len(set(self.marcados) - visiveis)
        self.rotulo_lote.configure(text=f'{n} selecionado(s)' + (f' • {ocultos} fora do filtro' if ocultos else '') + ' • marcar não move')
        self.var_todos.set(bool(visiveis) and visiveis.issubset(self.marcados))

    def _marcar(self, identificador):
        if self.ocupado:
            return
        item = next((i for i in self.itens if i['id'] == identificador), None)
        if not item or item['pronto']:
            return
        if identificador in self.marcados:
            del self.marcados[identificador]
        else:
            self.marcados[identificador] = dict(item)
        self.tabela.set(identificador, 'marca', '☑' if identificador in self.marcados else '☐')
        self._lote()

    def _clique_checkbox(self, evento):
        linha = self.tabela.identify_row(evento.y)
        if linha and self.tabela.identify_column(evento.x) == '#1':
            self._marcar(linha)
            self.tabela.selection_set(linha)
            return 'break'

    def _espaco(self, evento):
        if self.tabela.selection():
            self._marcar(self.tabela.selection()[0])
        return 'break'

    def _marcar_todos(self):
        marcar = self.var_todos.get()
        for item in self._visiveis():
            if not item['pronto'] and (item['id'] in self.marcados) != marcar:
                self._marcar(item['id'])
        self._lote()

    def _selecionar(self, evento=None):
        if not self.tabela.selection():
            return
        item = next((i for i in self.itens if i['id'] == self.tabela.selection()[0]), None)
        if not item:
            return
        dim = item.get('dimensao')
        medida = f'{consumo_custo.numero(dim["largura_m"])} × {consumo_custo.numero(dim["altura_m"])} m' if dim else 'Medida não identificada'
        self.detalhe.configure(text=f"{item['arquivo']}\n\n{item['trabalho']}\n{item['quantidade']} un • {medida}\n{item['status']}")
        self.aviso_arte.configure(text='\n'.join(item['avisos']))
        chave = (item['caminho'], item['assinatura'])
        if chave == self.chave_previa:
            return
        self.chave_previa = chave
        self.imagem.configure(image='', text='Carregando prévia…')
        if chave in self.cache:
            self._mostrar_previa(self.cache[chave])
        else:
            self._rodar('previa', miniaturas.de_arquivo, item['caminho'], 800, contexto=chave)

    def _mostrar_previa(self, dados):
        self.cache[self.chave_previa] = dados
        self.cache.move_to_end(self.chave_previa)
        while len(self.cache) > 30:
            self.cache.popitem(last=False)
        if not dados:
            self.imagem.configure(image='', text='Prévia indisponível neste formato')
            self.foto = None
            return
        from PIL import Image, ImageTk
        imagem = Image.open(io.BytesIO(dados)).convert('RGB')
        imagem.thumbnail((260, 155))
        self.foto = ImageTk.PhotoImage(imagem, master=self)
        self.imagem.configure(image=self.foto, text='')

    def _ampliar(self):
        dados = self.cache.get(self.chave_previa)
        if not dados:
            return
        from PIL import Image, ImageTk
        janela = tk.Toplevel(self)
        janela.title('Prévia do material')
        imagem = Image.open(io.BytesIO(dados)).convert('RGB')
        imagem.thumbnail((1000, 750))
        janela.foto = ImageTk.PhotoImage(imagem, master=janela)
        tk.Label(janela, image=janela.foto, bg=cores.previa).pack(padx=14, pady=14)

    def _mover(self):
        if not self.marcados or self.ocupado:
            return
        self.ocupado = True
        self.versao += 1  # Descartar inventário que começou antes da movimentação.
        self._lote()
        self.var_status.set('Movendo o lote para PRONTOS…')
        self._rodar('mover', servico.mover_lote, list(self.marcados.values()))

    def _custos(self):
        for filho in self.caixa_custo.winfo_children():
            filho.destroy()
        if not self.resumo:
            _texto(self.caixa_custo, 'Selecione um cliente e aguarde a leitura das pastas.', 12).pack(pady=30)
            return
        r = self.resumo
        _texto(self.caixa_custo, f'CONSUMO E CUSTO • {self.cliente}', 17, negrito=True).pack(anchor='w', padx=12, pady=14)
        estado = 'PRODUÇÃO CONCLUÍDA' if r['total_arquivos'] and not r['pendentes'] else 'PRODUÇÃO EM ANDAMENTO'
        _texto(self.caixa_custo, f"{estado} • {r['produzidos']} de {r['total_arquivos']} arquivos em PRONTOS", 11, cores.positivo).pack(anchor='w', padx=12, pady=8)
        frame = _cartao(self.caixa_custo)
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        nomes = [('material', 'Material / variante', 170), ('previsto', 'Previsto m²', 95), ('produzido', 'Produzido m²', 100),
                 ('pendente', 'Pendente m²', 100), ('consumo', 'Consumo est. m²', 120), ('preco', 'Preço / m²', 110), ('custo', 'Custo produzido', 130)]
        tabela = ttk.Treeview(frame, columns=[c[0] for c in nomes], show='headings', style='Producao.Treeview')
        barra = ttk.Scrollbar(frame, orient='vertical', command=tabela.yview)
        barra.pack(side='right', fill='y')
        tabela.configure(yscrollcommand=barra.set)
        tabela.pack(fill='both', expand=True)
        for chave, nome, largura in nomes:
            tabela.heading(chave, text=nome)
            tabela.column(chave, width=largura, minwidth=65)
        for l in r['linhas']:
            nome = l['categoria'] + ' ' + dimensoes.formatar_variante(l['variante'])
            preco = custos.formatar_reais(l['preco']) if l['preco'] is not None else 'A cadastrar'
            valor = custos.formatar_reais(l['custo']) if l['custo'] is not None else 'A apurar'
            if not l['usado']:
                valor = 'Não utilizado'
            tabela.insert('', 'end', values=(nome, *(consumo_custo.numero(l[k]) for k in ('previsto', 'produzido', 'pendente', 'consumo')), preco, valor))
        valor = custos.formatar_reais(r['total']) if r['tem_valor'] else 'Aguardando preços / apuração'
        _texto(self.caixa_custo, 'Total conhecido: ' + valor + (' • PARCIAL / INCOMPLETO' if not r['completo'] else ''),
              13, cores.alerta if not r['completo'] else cores.positivo, True).pack(anchor='w', padx=12, pady=10)
        _texto(self.caixa_custo, 'Consumo estimado = peças produzidas + sobra do rolo/chapa. Sem baixa de estoque. Tinta por perfil cadastrado.',
              9, cores.texto2, wraplength=950, justify='left').pack(anchor='w', padx=12, pady=4)
        if r['faltantes']:
            _botao(self.caixa_custo, f"Ver {len(r['faltantes'])} pendência(s) de custo", lambda: messagebox.showinfo(
                'Pendências de custo', '\n'.join(r['faltantes']), parent=self)).pack(anchor='w', padx=12, pady=10)

    def _exportar(self):
        if self.ocupado or not self.cliente:
            return
        nome = sanitizar_nome_arquivo(self.cliente)
        destino = filedialog.asksaveasfilename(parent=self, title='CONSUMO E CUSTO',
                    initialfile=f'CONSUMO E CUSTO - {nome}.pdf', defaultextension='.pdf', filetypes=[('PDF', '*.pdf')])
        if not destino:
            return
        cliente, vinculos = self.cliente, list(self.vinculos)
        self.ocupado = True
        self._lote()
        self.var_status.set('Atualizando dados e gerando PDF…')
        def exportar():
            itens, configuracao, resumo = ler_cliente(vinculos, cliente)
            return consumo_custo.gerar_pdf(destino, cliente, itens, configuracao, resumo)
        self._rodar('pdf', exportar)
