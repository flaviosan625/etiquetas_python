# Sistema de Produção — Uny CV

Sistema de produção da **Uny CV / Unyco Cenografia** (estandes, cenografia e comunicação visual em
grande formato). Começou como gerador de etiquetas e hoje cobre quatro frentes, todas ligadas pela
mesma ideia: **o nome do arquivo já diz o que é** — quantidade, material e medida saem dali, e
alimentam tudo o mais.

### 1. Etiquetas, OS e checklist

Lê os PDFs de uma pasta de entrada, identifica o material de cada um pelo nome (Lona, Adesivo, PS,
MDF, PVC, Acrílico e quaisquer outros cadastrados), monta etiquetas em folhas A4 e gera o PDF
unificado com sumário, um checklist por categoria, o log de processamento em CSV e a Ordem de
Serviço resumida.

### 2. Envio para as impressoras

Organiza a pasta de produção de cada cliente e manda os arquivos prontos para a fila da máquina
certa. Do outro lado, um vigia entrega na *hot folder* do RIP — sem nunca deixar o RIP ver arquivo
pela metade, e girando 90° o que for mais largo que a bobina, para economizar material.

Máquinas atendidas: **Mimaki UJV 100** (1,48 m), **Mimaki SWJ320A** (3,20 m) e **DOCAN R5200**
(5,00 m). A máquina é sugerida pelo material, nunca pela largura.

### 3. Comprovação do que foi produzido

Cada arquivo entregue à impressão vira uma linha num registro permanente, e todo dia sai um PDF com
o que passou em cada máquina: hora, quantidade, material, medida e m². Existe porque na instalação
— às vezes em outro estado — aparece a conversa de *"vocês não imprimiram tanto material"*, e agora
há documento para responder.

### 4. Corte na fresa CNC

Guarda os parâmetros de usinagem por material e espessura (fresa, passada, profundidade) e os
exporta para um gadget Lua que roda dentro do **Aspire**: um clique cria os percursos de corte
interno e externo, na ordem certa, direto no desenho aberto.

---

## Instalação

1. Instale o Python 3.10+ (no Windows, marque "Add python.exe to PATH").
2. Instale as dependências:

   ```
   pip install -r requirements.txt
   ```

O projeto usa uma `.venv` própria. O `abrir_gerador.bat` já a utiliza quando existe — **use sempre
ele ou a `.venv`**, porque o Python do sistema não tem as dependências e alguns recursos
(impressão, conversão via Illustrator) somem em silêncio.

## Como usar

**Interface gráfica (o dia a dia):**

```
python main.py
```

Abre a janela onde você escolhe a pasta de entrada, preenche cliente/gerente/produtor e acompanha o
processamento. Gerente e produtor já vêm preenchidos com o último valor usado. É por ela também que
se manda arquivo para a fila das impressoras.

**Linha de comando** (para automatizar):

```
python main.py --cliente "Nome do Cliente" --gerente "Nome" --produtor "Nome" --pasta-entrada entrada
```

**O vigia das hot folders** (o que roda sozinho, de minuto em minuto, pelo Agendador de Tarefas):

```
python -m rasterlink_hotfolder --uma-vez              # posto do RIP (UJV e SWJ)
python -m rasterlink_hotfolder --uma-vez --posto sai  # posto da DOCAN
```

## As duas máquinas

O vigia roda em dois PCs diferentes, com o mesmo arquivo, separados por **posto**:

| posto | máquinas | onde roda |
|---|---|---|
| `rip` | UJV 100, SWJ320A | PC do RIP, em `C:\RasterLink` |
| `sai` | DOCAN | PC principal, direto desta pasta |

Sem `--posto` ele assume o posto do RIP — é o que faz a tarefa antiga daquela máquina continuar
funcionando sem alteração nenhuma.

**Atualizar o PC do RIP:** copie o `rasterlink_hotfolder.py` para a pasta de deploy no OneDrive e
rode lá o `maquina_rip/atualizar.bat`. Ele confere se o arquivo que chegou já é o novo **antes** de
copiar, copia, e verifica que pegou. Não mexe na tarefa agendada — trocar o arquivo basta.

## Cadastrando rolos, chapas e materiais

Clique em "⚙ Configurar medidas de rolos e chapas..." na tela principal, ou edite o `config.json`.
Cada material tem `tipo` (`rolo` ou `chapa`), `largura_cm` e `comprimento_cm`. Dá para editar,
acrescentar um material novo ou remover um que saiu de linha — sem tocar em nenhum `.py`.

O `config.json` guarda também:

- `sinonimos_categoria` — nomes alternativos que caem na mesma categoria (ex: "VINIL" → "ADESIVO").
- `typos_unidade` — erros de digitação no lugar da unidade (ex: "XM" → "CM"). Aparecendo um novo e
  recorrente, cadastre aqui.
- `ordem_unificado` — em que ordem as categorias aparecem no PDF unificado. Categoria que exista em
  `materiais` mas não esteja nessa lista ainda aparece (no fim), para nunca sumir em silêncio.

## Parâmetros de corte da fresa

Ficam em `corte_parametros.py`, que é a **fonte única**: fresa, passada, profundidade e ordem de
usinagem. Depois de mexer neles é preciso regerar o que o Aspire lê:

```
python -c "import corte_parametros as c; print(c.exportar_para_lua())"
python -c "import corte_parametros as c; c.gerar_gadgets(instalar=True)"
```

Editar o `.lua` na mão não adianta — a próxima exportação apaga. E a ordem **CORTE INTERNO antes de
CORTE EXTERNO** não é estética: quando o contorno externo fecha, a peça solta da chapa, e furo feito
depois disso sai torto.

## Rodando os testes

```
pip install -r requirements-dev.txt
pytest
```

São cerca de 500 testes. Além da leitura de medida no nome, do cálculo de desperdício e do
`config.json`, eles cobrem o vigia das hot folders ponta a ponta, o relatório de produção, o
controle de estoque e — porque os dois já quebraram na mão do usuário — a codificação dos scripts
de instalação (`.ps1` precisa de BOM, `.bat` precisa ser ASCII puro).

## Mapa dos arquivos

```
main.py / gui.py              entrada do programa e interface (tkinter)
processamento.py              núcleo: lê os PDFs, categoriza, monta as etiquetas
dimensoes.py                  lê medida e quantidade do nome do arquivo; calcula desperdício
config.py / config.json       materiais, sinônimos, typos, últimos valores usados
relatorios.py / pdf_layout.py log CSV, Ordem de Serviço, páginas de título
producao.py                   organiza a pasta PRODUCAO de cada cliente
envio_impressao.py            manda da pasta de produção para a fila das máquinas
rasterlink_hotfolder.py       o vigia: entrega na hot folder do RIP e registra
relatorio_producao.py         PDF diário do que passou nas máquinas
estoque.py                    catálogo, movimentos e saldo de material
corte_parametros.py           parâmetros de usinagem (fonte única)
aspire/corte_nucleo.lua       gadget que cria os percursos dentro do Aspire
maquina_rip/ maquina_sai/     instaladores das tarefas agendadas de cada posto
tests/                        os testes
```

Para o mapa mais fundo — arquitetura, decisões e as armadilhas de plataforma que já custaram
material — veja o `CLAUDE.md`.
