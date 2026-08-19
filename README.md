# Gerador de Etiquetas — UNY CV

Programa que pega PDFs de uma pasta de entrada, identifica o material
de cada um pelo nome do arquivo (Lona, Adesivo, PS, MDF, PVC, Acrílico
e quaisquer outros cadastrados), monta etiquetas em folhas A4, gera um
PDF unificado com sumário, um checklist por categoria, um log de
processamento em CSV e uma Ordem de Serviço resumida.

## Instalação

1. Instale o Python 3.10+ (no Windows, marque a opção "Add python.exe
   to PATH" durante a instalação).
2. Instale as dependências:

   ```
   pip install -r requirements.txt
   ```

## Como usar

**Interface gráfica (recomendado no dia a dia):**

```
python main.py
```

Abre uma janela onde você escolhe a pasta de entrada, preenche
cliente/gerente/produtor e acompanha o processamento em tempo real. Os
campos de gerente e produtor já vêm preenchidos com o último valor
usado.

**Linha de comando** (útil para automatizar):

```
python main.py --cliente "Nome do Cliente" --gerente "Nome do Gerente" --produtor "Nome do Produtor" --pasta-entrada entrada
```

## Cadastrando rolos/chapas de medidas novas

Clique em "⚙ Configurar medidas de rolos e chapas..." na tela
principal, ou edite diretamente o `config.json` gerado na primeira
execução. Cada material tem: `tipo` (`rolo` ou `chapa`), `largura_cm`
e `comprimento_cm`. Você pode editar um material existente, adicionar
um material novo (mesmo que seja uma categoria que ainda não existia),
ou remover um que não é mais usado — tudo sem editar nenhum arquivo
`.py`.

O `config.json` também guarda:

- `sinonimos_categoria`: nomes alternativos que devem cair na mesma
  categoria (ex: "VINIL" → "ADESIVO").
- `typos_unidade`: erros de digitação comuns no lugar da unidade de
  medida (ex: "XM" → "CM"). Se aparecer um erro de digitação novo e
  recorrente, cadastre aqui.
- `ordem_unificado`: em que ordem as categorias aparecem no PDF
  unificado. Uma categoria que exista em `materiais` mas não esteja
  nessa lista ainda aparece no unificado (no final), para nunca
  "sumir" silenciosamente.

## Estrutura do projeto

```
main.py            ponto de entrada (abre a GUI ou roda via linha de comando)
gui.py              interface gráfica (tkinter)
config.py           carrega/salva o config.json
dimensoes.py         leitura de medida no nome do arquivo e cálculo de desperdício
pdf_layout.py         páginas de título e numeração de página do PDF unificado
relatorios.py         log CSV e Ordem de Serviço em PDF
processamento.py      orquestra tudo: lê os PDFs, categoriza, monta as etiquetas
config.json            configuração (materiais, sinônimos, typos, últimos usados)
tests/                 testes automatizados das partes sem dependência de arquivo
```

## Rodando os testes

```
pip install -r requirements-dev.txt
pytest
```

Os testes cobrem a extração de medida do nome do arquivo (incluindo
correção de erro de digitação e casos ambíguos), o cálculo de
desperdício, a sanitização de nome de arquivo, e o carregamento do
config.json (incluindo recuperação de um arquivo corrompido).

## O que mudou em relação à versão anterior (script único `main.py`)

- Interface gráfica opcional, sem precisar do terminal.
- Medidas de rolos/chapas e categorias de material configuráveis pela
  tela, sem editar código — inclusive para cadastrar um material
  novo no futuro.
- Lista de erros de digitação de unidade configurável (antes só
  "XM→CM" estava fixo no código).
- Cada etapa de salvamento é protegida individualmente: se uma falhar
  (por exemplo, um PDF aberto em outro programa), as demais ainda são
  geradas, e o motivo do erro fica no log — em vez do programa
  travar e perder tudo.
- Nome do cliente é validado/sanitizado antes de virar nome de
  arquivo, evitando erro com caracteres que o Windows não aceita.
- Cada execução salva numa pasta com data/hora, então rodar de novo
  para o mesmo cliente não sobrescreve o resultado anterior.
- Se o programa quebrar de forma inesperada rodando fora da GUI, a
  janela do terminal não fecha sozinha antes de dar pra ler o erro.
