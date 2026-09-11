---
name: aspire
description: Trabalhar no gadget de corte do Aspire 8.5 (aspire/corte_nucleo.lua) — ciclo de edição sem reinstalar nada, como sondar a API que não tem documentação pública, os números por trás das opções da tela (ProfileSide, CutDirection, RampType), e as armadilhas que já produziram peça errada. Use ao mexer em qualquer .lua da pasta aspire/, nos parâmetros de usinagem, na classificação interno/externo, ou quando o corte sair errado na fresa.
---

# Gadget de corte do Aspire 8.5

O Aspire 8.5 **não tem documentação pública de API Lua**. Tudo que este projeto sabe foi
descoberto sondando o programa ao vivo. Leia isto antes de mexer.

## O ciclo de trabalho: não reinstale nada pra testar

Os atalhos em `C:\ProgramData\Vectric\Aspire\V8.5\Gadgets` têm **três linhas e nenhuma lógica**:
declaram o material e fazem `dofile` de `aspire/corte_nucleo.lua`, no repositório.

Logo: **editar `aspire/corte_nucleo.lua` vale na hora.** O usuário clica no menu Gadgets como
sempre e já roda a versão nova. Nunca peça pra reinstalar gadget só pra testar mudança de lógica.

Reinstalar só é preciso quando muda a **lista de materiais do menu**:

```bash
.venv/Scripts/python.exe -c "import corte_parametros as c; c.gerar_gadgets(instalar=True)"
```

E depois de mexer em `corte_parametros.py`, **regere o Lua** — senão o gadget continua lendo o
valor antigo e a máquina corta com a passada errada, sem dar erro nenhum:

```bash
.venv/Scripts/python.exe -c "import corte_parametros as c; print(c.exportar_para_lua())"
```

## Como sondar a API

**O truque:** chamar um método com os argumentos errados faz o luabind imprimir a assinatura C++
de verdade.

```
GetTool()
  No matching overload found, candidates:
  Tool* GetTool(ToolDatabase const&,char const*,char const*)
```

Foi assim que tudo aqui foi descoberto. Duas técnicas que valem mais que adivinhar:

- **Ler de volta o que o usuário já montou na mão.** `aspire/Sonda_API.lua` abre um percurso que
  ele criou pela tela e lê os campos: o percurso dele *é* a tabela de conversão entre o que a tela
  mostra e o número que a API espera.
- **Pôr a sonda dentro do gadget que ele já usa.** Ele clica como sempre, e o relatório
  (`aspire/corte_resultado.txt`) traz a resposta — sem instalar nada, sem pedir passo extra.

O que já foi sondado está em `aspire/api_8_5.txt` e `aspire/api_8_5_metodos.txt`.

> **Essas notas dizem o que foi VISTO, nunca o que existe.** Nunca conclua que a API não tem algo
> porque não está ali. Já aconteceu: afirmei que o Aspire só expunha a caixa envolvente do vetor,
> a partir de nota antiga, e reescrevi todo um caminho por causa disso. Bastou sondar pra achar
> `GetContour()` e, dentro dele, `IsPointInside()` — exatamente o que eu tinha dado como
> inexistente. **Sonde antes de afirmar um limite.**

## Números já traduzidos

| tela | API |
|---|---|
| Fora / Direita | `ProfileSide = 0` |
| Dentro / Esquerda | `ProfileSide = 1` |
| Convencional | `CutDirection = 0` |
| Rampa suave | `RampType = 0` |
| Topo raso | `Tool` tipo `1` |

Com `ProfileSide = 0` o Aspire **resolve o aninhamento sozinho**: num círculo dentro de outro ele
passa por fora do externo e por dentro do interno, sem ninguém mandar.

Coleções (`SelectionList`, `ToolpathManager`, `CadLayerManager`, `CadLayer`) se percorrem com
`GetHeadPosition()` / `GetNext(pos)`.

Geometria de um vetor:

- `CadObject:GetContour()` → `Contour` — `.Area`, `.Length`, `.IsClosed`, `.IsClockwise`, `.Count`
  e **`Contour:IsPointInside(Point2D, tolerância)`**, que é o ponto-dentro-do-polígono do próprio
  Aspire.
- `CadObject:GetBoundingBox()` → `Box2D` — `.BLC`, `.TRC`, `.BRC`, `.TLC`, `.Centre`.

## Armadilhas que já quebraram de verdade

- **A primeira linha TEM que ser `-- VECTRIC LUA SCRIPT`.** Sem ela o Aspire recusa o arquivo
  inteiro, com "Script does not start with".
- **`Tool` nasce em POLEGADA.** Escreva `ferramenta.InMM = true` **antes** de qualquer número.
  Sem isso, diâmetro 4 virou 4 polegadas (101,6 mm, raio 50,8 desenhado sobre o vetor) e a passada
  de 11 teria virado 279 mm de profundidade numa chapa de 10 mm.
- **`MessageBox` do Aspire só aceita ASCII.**
- **Arquivo `.lua` gerado vai sem acento** — é lido por um Lua de 2016.
- **Nunca escreva `.lua` por heredoc do shell.** Cada camada come um nível de escape; o mesmo
  arquivo já quebrou quatro vezes assim, virando quebra de linha no meio de string. Use a
  ferramenta de escrita de arquivo e depois confira:
  ```bash
  .venv/Scripts/python.exe ferramentas/conferir_lua.py aspire/corte_nucleo.lua
  ```

## Regras de produção (do usuário, não negociáveis)

- **CORTE INTERNO antes de CORTE EXTERNO, sempre.** Quando o contorno externo fecha, a peça solta
  da chapa e começa a se mexer — furo feito depois sai torto, quando não arranca a peça. São
  **dois percursos separados**: a aba "Ordem" do formulário foi verificada e só oferece otimização
  de deslocamento, nenhuma opção sabe o que é furo e o que é contorno.
- **Classifique dentro/fora pelo NÍVEL DE ANINHAMENTO**, não pela caixa envolvente: conte quantos
  contornos de **área maior** contêm o centro do objeto; ímpar = furo. A comparação por área é o
  que desempata o 'O' e o buraco dele. Use a caixa envolvente só como pré-filtro de desempenho
  (461 vetores dariam 212 mil chamadas sem ela). Classificar *por* caixa envolvente já produziu
  corte errado: 11 letras viradas furo, peça sairia 4 mm menor.
- **Seleção manda.** Havendo objeto selecionado, só ele vira percurso.
- **Conferência de chapa é AVISO, nunca bloqueio** — acrílico vem em outras medidas, e travar aí
  gera falso positivo garantido.
- **Não converta para DXF.** O Aspire abre PDF, e o usuário recusou conversão com todas as letras:
  *"NÃO PEDI PARA GERAR OUTRO ARQUIVO, QUERO USAR O MESMO PDF ORIGINAL QUE JÁ ESTAVA NA PASTA"*.
  E nunca escreva arquivo na pasta de produção dele.
- **Pós-processador da máquina: `G code (mm)`, `.tap`.** O sintoma "a máquina não reconhece o zero
  do canto inferior esquerdo" foi isso — não era o código nem a chapa.
