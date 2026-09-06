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
-- Se não houver camada nomeada, cai no modo antigo: um percurso só, com
-- os vetores selecionados. Funciona, mas sem garantia de ordem — e o
-- relatório avisa.
--
-- Os valores vêm de corte_parametros.py. Números da API confirmados na
-- tela: ProfileSide 0 = Fora/Direita, 1 = Dentro/Esquerda;
-- CutDirection 0 = Convencional; RampType 0 = Suave; Tool tipo 1 = topo
-- raso.
--
-- Rode em: Gadgets -> Corte Automatico

local DESTINO = "C:\\Users\\flavi\\Desktop\\etiquetas_python\\aspire\\corte_resultado.txt"

-- PVC 10 mm. Vai virar tabela por material quando a tela mandar qual é.
local FERRAMENTA = "Topo Raso (4 mm)"
local TIPO_TOPO_RASO = 1
local DIAMETRO = 4.0
local PASSADA = 11.0
local PASSO_LATERAL = 2.0
local AVANCO = 2000.0
local ATAQUE = 1000.0
local ROTACAO = 18000.0
local PROFUNDIDADE = 11.0        -- 10 da chapa + 1 pra cortar passante
local RAMPA_MM = 10.0

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

local function construir_ferramenta()
   local ferramenta = Tool(FERRAMENTA, TIPO_TOPO_RASO)
   ferramenta.ToolDia = DIAMETRO
   ferramenta.Stepdown = PASSADA
   ferramenta.Stepover = PASSO_LATERAL
   ferramenta.FeedRate = AVANCO
   ferramenta.PlungeRate = ATAQUE
   ferramenta.SpindleSpeed = ROTACAO
   ferramenta.ToolNumber = 1
   anotar("  ferramenta: " .. numa_linha(ferramenta) ..
          " dia " .. tostring(ferramenta.ToolDia) ..
          " passada " .. tostring(ferramenta.Stepdown))
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

local function criar_percurso(nome, ferramenta, lado)
   local rampa = RampingData()
   rampa.DoRamping = true
   rampa.RampType = RAMPA_SUAVE
   rampa.RampDistance = RAMPA_MM

   local parametros = ProfileParameterData()
   parametros.Name = nome
   parametros.CutDepth = PROFUNDIDADE
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
   anotar("=== ferramenta ===")
   local ferramenta = construir_ferramenta()

   anotar("")
   anotar("=== percursos ===")
   local interna, nomeInterna = achar_camada(trabalho, "CORTE INTERNO")
   local externa, nomeExterna = achar_camada(trabalho, "CORTE EXTERNO")
   local feitos = 0

   if interna ~= nil or externa ~= nil then
      -- O INTERNO PRIMEIRO. A ordem na lista e a ordem de usinagem.
      if interna ~= nil then
         local n = selecionar_camada(trabalho, interna)
         anotar("  camada '" .. nomeInterna .. "': " .. n .. " vetores")
         if n > 0 and criar_percurso("CORTE INTERNO", ferramenta, LADO_DENTRO) then
            feitos = feitos + 1
         end
      else
         anotar("  (sem camada de corte interno — pode ser peca sem furo)")
      end

      if externa ~= nil then
         local n = selecionar_camada(trabalho, externa)
         anotar("  camada '" .. nomeExterna .. "': " .. n .. " vetores")
         if n > 0 and criar_percurso("CORTE EXTERNO", ferramenta, LADO_FORA) then
            feitos = feitos + 1
         end
      end
   else
      anotar("  SEM CAMADA NOMEADA — um percurso so, com o que esta selecionado.")
      anotar("  O Aspire acerta o dentro/fora sozinho, mas a ORDEM nao fica garantida.")
      if criar_percurso("CORTE", ferramenta, LADO_FORA) then feitos = 1 end
   end

   anotar("")
   anotar("  total de percursos no trabalho: " .. tostring(ToolpathManager().Count))
   gravar()

   if feitos == 0 then
      MessageBox("Nenhum percurso criado.\n\nVeja:\n" .. DESTINO)
      return false
   end

   local recado = feitos .. " percurso(s) criado(s)."
   if interna ~= nil and externa ~= nil then
      recado = recado .. "\n\nCORTE INTERNO primeiro, CORTE EXTERNO depois —\n" ..
               "a ordem da lista e a ordem de usinagem."
   elseif interna == nil and externa == nil then
      recado = recado .. "\n\nATENCAO: nao havia camada CORTE INTERNO / CORTE\n" ..
               "EXTERNO, entao saiu um percurso so. A ordem nao esta garantida."
   end
   MessageBox(recado)
   return true
end
