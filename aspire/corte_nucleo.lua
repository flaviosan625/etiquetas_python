-- VECTRIC LUA SCRIPT
--
-- Gera os percursos de corte a partir das camadas do desenho.
--
-- O QUE ELE FAZ
--   1. acha a camada CORTE INTERNO e cria um percurso por DENTRO da linha
--   2. acha a camada CORTE EXTERNO e cria um percurso por FORA
--   3. nessa ordem, sempre
--
-- POR QUE NESSA ORDEM (regra do Flávio, 06/09/2026): assim que o
-- contorno externo fecha, a peça solta da chapa e começa a se mexer.
-- Furo feito depois disso sai torto, quando não arranca a peça. A ordem
-- dos percursos na lista é a ordem de usinagem, então criar o interno
-- primeiro é o que garante isso — e garantia aqui vale mais que
-- elegância, porque o preço do erro é a chapa.
--
-- POR QUE DOIS PERCURSOS, SE O ASPIRE JÁ SABE FAZER O DENTRO/FORA
-- SOZINHO: sabe mesmo — com ProfileSide = 0 ele detecta o aninhamento e
-- inverte o lado no contorno interno (conferido na tela em 06/09/2026).
-- Mas num percurso só não há como mandar o interno vir primeiro: a API
-- não expõe a aba "Ordem". Dois percursos custam nada e tornam a ordem
-- explícita.
--
-- SE NÃO HOUVER CAMADA NOMEADA, ele descobre sozinho (08/09/2026).
-- Percorre os vetores do trabalho, mede a caixa de cada um e separa
-- interno de externo pelo aninhamento — a mesma regra do
-- corte_dxf.py, só que aqui dentro. Assim vale pra QUALQUER formato
-- que entre no Aspire, inclusive PDF arrastado direto, que é o caso
-- dos arquivos da ASICS: camada chamada "Camada 1" e traço quase
-- preto, então nem o nome nem a cor dizem o que é corte.
--
-- Antes disso, sem camada, saía um percurso só e a ordem não ficava
-- garantida — que é justamente a única coisa que o Aspire NÃO resolve
-- sozinho.
--
-- Os valores vêm de corte_parametros.py. Números da API confirmados na
-- tela: ProfileSide 0 = Fora/Direita, 1 = Dentro/Esquerda;
-- CutDirection 0 = Convencional; RampType 0 = Suave; Tool tipo 1 = topo
-- raso.
--
-- Rode em: Gadgets -> Corte Automatico

local DESTINO = "C:/Users/flavi/Desktop/etiquetas_python/aspire/corte_resultado.txt"

-- ================== NAO SE EDITA MATERIAL AQUI ====================
-- O material vem do atalho no menu Gadgets: "Corte Automatico PVC 10",
-- "Corte Automatico MDF 9", e assim por diante. Cada um e um arquivo
-- Quem escolhe e o atalho que chamou este nucleo (ver gerar_gadgets no
-- corte_parametros.py). O padrao so existe pra nunca rodar sem material.
local MATERIAL = MATERIAL_DO_GADGET or "PVC 10"
-- Opcoes: PVC 10, PVC 20, MDF 6, MDF 9, MDF 15,
--         ACRILICO 1 2 3 4 5 6 7 8 10
-- ==================================================================

local TABELA = "C:/Users/flavi/Desktop/etiquetas_python/aspire/parametros_corte.lua"
local TIPO_TOPO_RASO = 1

local LADO_FORA = 0
local LADO_DENTRO = 1
local DIRECAO_CONVENCIONAL = 0
local RAMPA_SUAVE = 0

local saida = {}
local function anotar(t) saida[#saida + 1] = t end

local function numa_linha(valor)
   return (string.gsub(tostring(valor), "%s+", " "))
end

local function gravar()
   local arquivo = io.open(DESTINO, "w")
   if arquivo then
      arquivo:write(table.concat(saida, "\n"))
      arquivo:close()
   end
end

local function sem_acento(texto)
   local t = tostring(texto):upper()
   for de, para in pairs({["Á"]="A", ["À"]="A", ["Ã"]="A", ["Â"]="A", ["É"]="E",
                          ["Ê"]="E", ["Í"]="I", ["Ó"]="O", ["Ô"]="O", ["Õ"]="O",
                          ["Ú"]="U", ["Ç"]="C"}) do
      t = t:gsub(de, para)
   end
   return t
end

-- Le a tabela gerada pelo corte_parametros.py. Se ela nao existir ou o
-- material nao estiver cadastrado, PARA — chutar parametro de corte
-- quebra fresa.
local function carregar_parametros()
   local carregar = loadfile(TABELA)
   if carregar == nil then
      return nil, "nao achei a tabela em " .. TABELA
   end
   local ok, dados = pcall(carregar)
   if not ok or type(dados) ~= "table" then
      return nil, "tabela ilegivel: " .. tostring(dados)
   end
   local material = dados.materiais and dados.materiais[MATERIAL]
   if material == nil then
      return nil, "'" .. MATERIAL .. "' nao esta cadastrado no corte_parametros.py"
   end
   if dados.unidade ~= "mm" then
      return nil, "a tabela nao esta em mm, esta em " .. tostring(dados.unidade)
   end
   material.avanco = dados.avanco
   material.ataque = dados.ataque
   material.rotacao = dados.rotacao
   material.passo_lateral = dados.passo_lateral
   material.rampa = dados.rampa
   return material
end

local function construir_ferramenta(p)
   local ferramenta = Tool(p.ferramenta, TIPO_TOPO_RASO)
   -- ANTES de qualquer numero: sem isto a ferramenta nasce em POLEGADA
   -- (o grupo do banco se chama "Imperial Tools", nao por acaso) e o
   -- diametro 4 vira 4 polegadas = 101,6 mm, com raio de 50,8 — que foi
   -- exatamente a marcacao que o Flavio viu sobre o vetor (06/09/2026).
   -- Pior: a passada 11 viraria 279 mm de profundidade numa chapa de 10.
   ferramenta.InMM = true
   ferramenta.ToolDia = p.diametro
   ferramenta.Stepdown = p.passada
   ferramenta.Stepover = p.passo_lateral
   ferramenta.FeedRate = p.avanco
   ferramenta.PlungeRate = p.ataque
   ferramenta.SpindleSpeed = p.rotacao
   ferramenta.ToolNumber = 1
   anotar("  ferramenta: " .. numa_linha(ferramenta) ..
          " dia " .. tostring(ferramenta.ToolDia) ..
          " passada " .. tostring(ferramenta.Stepdown) ..
          " InMM " .. tostring(ferramenta.InMM))
   return ferramenta
end

-- Deixa selecionados só os vetores desta camada. Devolve quantos.
local function selecionar_camada(trabalho, camada)
   local selecao = trabalho.Selection
   selecao:Clear()
   local quantos = 0
   local posicao = camada:GetHeadPosition()
   while posicao ~= nil do
      local objeto
      local ok = pcall(function()
         local a, b = camada:GetNext(posicao)
         objeto = a
         posicao = b
      end)
      if not ok or objeto == nil then break end
      -- Os dois booleanos de Add nao estao documentados; tenta as
      -- combinacoes e fica na primeira que aceitar.
      local entrou = false
      for _, par in ipairs({{true, true}, {true, false}, {false, false}}) do
         local certo = pcall(function() selecao:Add(objeto, par[1], par[2]) end)
         if certo then
            entrou = true
            break
         end
      end
      if entrou then quantos = quantos + 1 end
   end
   return quantos
end

-- ================== CLASSIFICAR SEM DEPENDER DE CAMADA ==============
--
-- O arquivo pode chegar de qualquer jeito: PDF arrastado, DXF do nosso
-- conversor, DWG do cliente. Quando ele NAO traz camada nomeada, o
-- gadget descobre sozinho quem esta dentro de quem, usando a caixa
-- envolvente de cada vetor.
--
-- Por que a caixa e nao o teste exato de ponto: a API do Aspire 8.5 da
-- a caixa de uma selecao (selection:GetBoundingBox(), usado pelo proprio
-- DXF_Batch_Processor da Vectric), mas nao expoe os pontos do vetor. E
-- errar pro lado "interno" e SEGURO: cortar antes uma forma cercada por
-- outra esta certo nos dois casos possiveis — furo de letra, ou peca
-- pequena dentro de uma moldura. O caro e o contrario, e esse a caixa
-- nao produz.

local FOLGA_CAIXA = 0.01   -- mm, pra caixas identicas nao se conterem

-- Mede UM objeto: limpa a selecao, poe so ele, pede a caixa.
local function caixa_do_objeto(trabalho, objeto)
   local selecao = trabalho.Selection
   selecao:Clear()
   local entrou = false
   for _, par in ipairs({{true, true}, {true, false}, {false, false}}) do
      if pcall(function() selecao:Add(objeto, par[1], par[2]) end) then
         entrou = true
         break
      end
   end
   if not entrou then return nil end

   local caixa
   local ok = pcall(function()
      local b = selecao:GetBoundingBox()
      caixa = {x0 = b.BLC.x, y0 = b.BLC.y, x1 = b.BRC.x, y1 = b.TLC.y}
   end)
   if not ok or caixa == nil then return nil end
   return caixa
end

-- Os vetores que ESTAO SELECIONADOS agora, copiados pra uma tabela.
--
-- Copiar antes de mexer e obrigatorio: medir a caixa de um objeto exige
-- limpar a selecao e por so ele dentro (ver caixa_do_objeto), o que
-- destruiria a selecao original no primeiro objeto medido.
--
-- A API 8.5 nao documenta GetHeadPosition/GetNext pra SelectionList — o
-- DXF_Batch_Processor da Vectric so usa .IsEmpty e :GetBoundingBox().
-- Entao aqui e tentativa protegida: se der, o gadget passa a trabalhar
-- so no que voce escolheu; se nao der, ele diz isso no relatorio em vez
-- de fingir que deu.
local function selecao_atual(trabalho)
   local selecao = trabalho.Selection
   local vazia = true
   pcall(function() vazia = selecao.IsEmpty end)
   if vazia then return {}, "nada selecionado" end

   local objetos = {}
   local ok = pcall(function()
      local pos = selecao:GetHeadPosition()
      while pos ~= nil do
         local objeto
         local a, b = selecao:GetNext(pos)
         objeto = a
         pos = b
         if objeto == nil then break end
         objetos[#objetos + 1] = objeto
      end
   end)
   if not ok then
      return nil, "esta versao do Aspire nao deixa percorrer a selecao"
   end
   return objetos, nil
end

-- Todos os vetores do trabalho, de todas as camadas.
local function todos_os_vetores(trabalho)
   local objetos = {}
   local gerente = trabalho.LayerManager
   local posCamada = gerente:GetHeadPosition()
   while posCamada ~= nil do
      local camada
      local ok = pcall(function()
         local a, b = gerente:GetNext(posCamada)
         camada = a
         posCamada = b
      end)
      if not ok or camada == nil then break end

      local pos = camada:GetHeadPosition()
      while pos ~= nil do
         local objeto
         local certo = pcall(function()
            local a, b = camada:GetNext(pos)
            objeto = a
            pos = b
         end)
         if not certo or objeto == nil then break end
         objetos[#objetos + 1] = objeto
      end
   end
   return objetos
end

local function contem(fora, dentro)
   return fora.x0 <= dentro.x0 + FOLGA_CAIXA
      and fora.y0 <= dentro.y0 + FOLGA_CAIXA
      and fora.x1 >= dentro.x1 - FOLGA_CAIXA
      and fora.y1 >= dentro.y1 - FOLGA_CAIXA
      and ((fora.x1 - fora.x0) > (dentro.x1 - dentro.x0) + FOLGA_CAIXA
        or (fora.y1 - fora.y0) > (dentro.y1 - dentro.y0) + FOLGA_CAIXA)
end

-- Devolve duas listas: os que ficam por dentro e os que ficam por fora.
-- A regra e a mesma do corte_dxf.py: quem esta dentro de um numero IMPAR
-- de outros e interno. Cobre o 'B' de dois furos e a ilha dentro do furo.
local function classificar_por_caixa(trabalho, objetos)
   local caixas = {}
   for i, objeto in ipairs(objetos) do
      caixas[i] = caixa_do_objeto(trabalho, objeto)
   end

   local dentro, fora, semCaixa, medidasDentro = {}, {}, 0, {}
   for i, objeto in ipairs(objetos) do
      if caixas[i] == nil then
         semCaixa = semCaixa + 1
         fora[#fora + 1] = objeto          -- nao medi: vai como externo
      else
         -- for numerico, NUNCA ipairs: 'caixas' tem buraco toda vez que
         -- um vetor nao pode ser medido, e ipairs para no primeiro nil.
         -- Pararia de contar no meio e classificaria como externo peca
         -- que e furo — que e o erro caro, o que solta a peca antes da
         -- hora.
         local nivel = 0
         for j = 1, #objetos do
            local outra = caixas[j]
            if i ~= j and outra ~= nil and contem(outra, caixas[i]) then
               nivel = nivel + 1
            end
         end
         if nivel % 2 == 1 then
            dentro[#dentro + 1] = objeto
            medidasDentro[#medidasDentro + 1] = caixas[i]
         else
            fora[#fora + 1] = objeto
         end
      end
   end
   return dentro, fora, semCaixa, medidasDentro
end

local function selecionar_objetos(trabalho, objetos)
   local selecao = trabalho.Selection
   selecao:Clear()
   local quantos = 0
   for _, objeto in ipairs(objetos) do
      for _, par in ipairs({{true, true}, {true, false}, {false, false}}) do
         if pcall(function() selecao:Add(objeto, par[1], par[2]) end) then
            quantos = quantos + 1
            break
         end
      end
   end
   return quantos
end


local function criar_percurso(nome, ferramenta, lado, p)
   local rampa = RampingData()
   rampa.DoRamping = true
   rampa.RampType = RAMPA_SUAVE
   rampa.RampDistance = p.rampa

   local parametros = ProfileParameterData()
   parametros.Name = nome
   parametros.CutDepth = p.profundidade
   parametros.StartDepth = 0.0
   parametros.ProfileSide = lado
   parametros.CutDirection = DIRECAO_CONVENCIONAL
   parametros.Allowance = 0.0
   parametros.CreateSquareCorners = false

   local seletor = GeometrySelector()
   seletor.SelectClosed = true
   seletor.SelectOpen = false
   seletor.ToolDia = ferramenta.ToolDia

   local ok, resultado = pcall(function()
      return ToolpathManager():CreateProfilingToolpath(
         nome, ferramenta, parametros, rampa, LeadInOutData(),
         ToolpathPosData(), seletor, true, true)
   end)
   anotar("  '" .. nome .. "' lado=" .. lado .. " -> " ..
          (ok and ("criado " .. numa_linha(resultado)) or numa_linha(resultado)))
   return ok and resultado ~= nil
end

local function achar_camada(trabalho, pedaco)
   local gerente = trabalho.LayerManager
   local posicao = gerente:GetHeadPosition()
   while posicao ~= nil do
      local camada
      local ok = pcall(function()
         local a, b = gerente:GetNext(posicao)
         camada = a
         posicao = b
      end)
      if not ok or camada == nil then break end
      local temNome, nome = pcall(function() return camada.Name end)
      if temNome and sem_acento(nome):find(pedaco, 1, true) and camada.Count > 0 then
         return camada, nome
      end
   end
   return nil
end

function main(script_path)
   saida = {}
   anotar("CORTE AUTOMATICO")

   local trabalho = VectricJob()
   if trabalho.Exists ~= true then
      MessageBox("Abra o trabalho com os vetores de corte.")
      return false
   end

   anotar("")
   anotar("=== parametros ===")
   local p, erro = carregar_parametros()
   if p == nil then
      anotar("  PAREI: " .. erro)
      gravar()
      MessageBox("Nao consegui os parametros de corte: " .. erro)
      return false
   end
   anotar("  " .. MATERIAL .. ": " .. p.ferramenta .. " dia " .. p.diametro ..
          " passada " .. p.passada .. " profundidade " .. p.profundidade ..
          " (" .. p.passes .. " passe(s))")
   local ferramenta = construir_ferramenta(p)

   -- O ProfileParameterData tem campo de ORDEM de usinagem? A aba
   -- "Ordem" existe na tela e oferece "de dentro para fora"; se a API
   -- expuser isso, um percurso so resolveria — mas na sondagem de 81
   -- nomes eu nao testei nenhum nome de ordenacao. Testando agora.
   anotar("")
   anotar("=== o percurso tem campo de ordem? ===")
   local amostra = ProfileParameterData()
   local achou = false
   for _, nome in ipairs({"Order", "Ordering", "OrderingMethod", "SortOrder",
                          "VectorOrder", "InsideOut", "DoInsideOut", "CutOrder",
                          "MachineOrder", "SortMethod", "Sequence", "Optimise",
                          "Optimize", "OptimiseOrder", "UseVectorStartPoints",
                          "InsideFirst", "DoInsideFirst"}) do
      local ok, valor = pcall(function() return amostra[nome] end)
      if ok and valor ~= nil then
         achou = true
         anotar("  ." .. nome .. " = " .. type(valor) .. " " .. tostring(valor))
      end
   end
   if not achou then
      anotar("  nenhum — a ordem so da pra garantir com percursos separados")
   end

   anotar("")
   anotar("=== percursos ===")

   -- A SELECAO MANDA (pedido do Flavio, 08/09/2026): havendo objeto
   -- selecionado, o percurso sai so pra ele. E assim que a moldura de
   -- acrilico e o gabarito ficam de fora sem ninguem precisar apagar
   -- nada — ele seleciona o que vai cortar agora e clica.
   local selecionados, recadoSelecao = selecao_atual(trabalho)
   if recadoSelecao ~= nil then
      anotar("  selecao: " .. recadoSelecao)
   end

   -- Selecao existe mas nao deu pra percorrer: PARA. Seguir daqui
   -- pegaria TODOS os vetores da chapa — o contrario exato do que
   -- pediram, e com a fresa ja no material o estrago nao volta atras.
   if selecionados == nil then
      anotar("  PAREI: havia selecao e eu nao consegui ler quais objetos eram.")
      gravar()
      MessageBox("Voce tem objeto selecionado, mas esta versao do Aspire\n" ..
                 "nao me deixa ler QUAIS sao.\n\n" ..
                 "Nao criei percurso nenhum — seguir pegaria a chapa inteira.\n\n" ..
                 "Tire a selecao (clique num espaco vazio) e rode de novo\n" ..
                 "pra cortar tudo, ou me avise pra eu achar outro caminho.")
      return false
   end

   local interna, nomeInterna, externa, nomeExterna
   if selecionados == nil or #selecionados == 0 then
      interna, nomeInterna = achar_camada(trabalho, "CORTE INTERNO")
      externa, nomeExterna = achar_camada(trabalho, "CORTE EXTERNO")
   end
   local feitos = 0

   if selecionados ~= nil and #selecionados > 0 then
      anotar("  " .. #selecionados .. " objeto(s) selecionado(s) — so eles vao virar percurso")
      local dentro, fora, semCaixa, medidas = classificar_por_caixa(trabalho, selecionados)
      anotar("  por dentro: " .. #dentro .. "   por fora: " .. #fora)
      if semCaixa > 0 then
         anotar("  " .. semCaixa .. " vetor(es) sem caixa mensuravel foram pra externo")
      end
      for i, c in ipairs(medidas) do
         anotar(string.format("    dentro #%d: %.1f x %.1f mm",
                              i, c.x1 - c.x0, c.y1 - c.y0))
      end

      if #dentro > 0 then
         selecionar_objetos(trabalho, dentro)
         if criar_percurso("CORTE INTERNO", ferramenta, LADO_DENTRO, p) then
            feitos = feitos + 1
         end
      end
      if #fora > 0 then
         selecionar_objetos(trabalho, fora)
         if criar_percurso("CORTE EXTERNO", ferramenta, LADO_FORA, p) then
            feitos = feitos + 1
         end
      end

   elseif interna ~= nil or externa ~= nil then
      -- O INTERNO PRIMEIRO. A ordem na lista e a ordem de usinagem.
      if interna ~= nil then
         local n = selecionar_camada(trabalho, interna)
         anotar("  camada '" .. nomeInterna .. "': " .. n .. " vetores")
         if n > 0 and criar_percurso("CORTE INTERNO", ferramenta, LADO_DENTRO, p) then
            feitos = feitos + 1
         end
      else
         anotar("  (sem camada de corte interno — pode ser peca sem furo)")
      end

      if externa ~= nil then
         local n = selecionar_camada(trabalho, externa)
         anotar("  camada '" .. nomeExterna .. "': " .. n .. " vetores")
         if n > 0 and criar_percurso("CORTE EXTERNO", ferramenta, LADO_FORA, p) then
            feitos = feitos + 1
         end
      end
   else
      -- SEM camada nomeada: o gadget classifica sozinho, pela caixa de
      -- cada vetor. Vale pra qualquer formato — PDF arrastado inclusive,
      -- que e o caso da pasta de CORTES da ASICS (2026-09-08): camada
      -- chamada "Camada 1" e traco quase preto, entao nem o nome nem a
      -- cor dizem o que e corte.
      anotar("  sem camada nomeada — classificando pelo aninhamento das caixas")
      local objetos = todos_os_vetores(trabalho)
      anotar("  vetores no trabalho: " .. #objetos)

      local dentro, fora, semCaixa, medidas = classificar_por_caixa(trabalho, objetos)
      anotar("  por dentro: " .. #dentro .. "   por fora: " .. #fora)
      if semCaixa > 0 then
         anotar("  " .. semCaixa .. " vetor(es) sem caixa mensuravel foram pra externo")
      end

      -- Lista o que foi pra DENTRO, com medida. A caixa envolvente nao
      -- distingue um furo de uma peca encostada no vao de outra em L:
      -- as duas ficam "contidas". Furo de letra e pequeno; peca inteira
      -- classificada como furo salta aos olhos nesta lista — e cortar
      -- por dentro uma peca que devia ser cortada por fora a deixa
      -- menor que o desenho, na largura da fresa.
      for i, c in ipairs(medidas) do
         anotar(string.format("    dentro #%d: %.1f x %.1f mm",
                              i, c.x1 - c.x0, c.y1 - c.y0))
      end

      -- O INTERNO PRIMEIRO, pelo mesmo motivo de sempre: assim que o
      -- externo fecha, a peca solta da chapa e o furo seguinte sai torto.
      if #dentro > 0 then
         selecionar_objetos(trabalho, dentro)
         if criar_percurso("CORTE INTERNO", ferramenta, LADO_DENTRO, p) then
            feitos = feitos + 1
         end
      else
         anotar("  (nada por dentro — nenhuma peca tem furo)")
      end

      if #fora > 0 then
         selecionar_objetos(trabalho, fora)
         if criar_percurso("CORTE EXTERNO", ferramenta, LADO_FORA, p) then
            feitos = feitos + 1
         end
      end
   end

   anotar("")
   anotar("  total de percursos no trabalho: " .. tostring(ToolpathManager().Count))
   gravar()

   if feitos == 0 then
      MessageBox("Nenhum percurso criado.\n\nVeja:\n" .. DESTINO)
      return false
   end

   local recado = feitos .. " percurso(s) criado(s)."
   if feitos >= 2 then
      recado = recado .. "\n\nCORTE INTERNO primeiro, CORTE EXTERNO depois —\n" ..
               "a ordem da lista e a ordem de usinagem."
   end
   if selecionados ~= nil and #selecionados > 0 then
      recado = recado .. "\n\nSo nos " .. #selecionados .. " objeto(s) que voce\n" ..
               "tinha selecionado. O dentro/fora saiu do aninhamento —\n" ..
               "confira na tela antes de mandar pra maquina."
   elseif interna == nil and externa == nil then
      recado = recado .. "\n\nNada estava selecionado e o arquivo nao trazia\n" ..
               "camada nomeada, entao peguei TODOS os vetores e descobri\n" ..
               "o dentro/fora pelo aninhamento. Confira na tela."
   end
   MessageBox(recado)
   return true
end
