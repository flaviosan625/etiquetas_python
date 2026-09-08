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
-- SEM CAMADA NOMEADA sai UM percurso só, e a ordem não fica garantida.
-- Já tentei classificar aqui dentro pela caixa envolvente de cada vetor
-- (08/09/2026) e ERROU num arquivo de produção — ver o bloco "SO O QUE
-- ESTA SELECIONADO" mais abaixo. Foi retirado.
--
-- Quem classifica é o corte_dxf.py, que lê o PDF e tem os PONTOS do
-- vetor na mão. Arraste o DXF que ele gera, não o PDF: é o DXF que traz
-- as duas camadas e, com elas, a garantia da ordem.
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

-- ============ CLASSIFICAR DENTRO DO ASPIRE, COM GEOMETRIA =========
--
-- Descoberto sondando o programa em 08/09/2026 (nao ha documentacao):
--
--   CadObject:GetContour()      -> Contour*
--   CadObject:GetBoundingBox()  -> Box2D  (.BLC .TRC .BRC .TLC .Centre)
--   Contour.Area                -> number
--   Contour.IsClosed            -> boolean
--   Contour:IsPointInside(Point2D, tolerancia) -> boolean
--
-- O IsPointInside e o teste de ponto-dentro-do-poligono feito pelo
-- PROPRIO Aspire. E ele que faltava.
--
-- A tentativa anterior usava so a caixa envolvente e ERROU num arquivo
-- de producao: no "Mova Belo Horizonte" as 13 letras do texto caem
-- dentro da CAIXA do logo — uma forma varrida, com as letras no vazio
-- embaixo da curva — sem estarem dentro do logo. Onze letras viraram
-- "furo" e sairiam cortadas por dentro, 4 mm menores. No "Rio de
-- Janeiro" o mesmo calculo acertou, mas por sorte: o logo de la e mais
-- baixo e a caixa nao alcanca o texto.
--
-- Agora a pergunta e a certa: o CENTRO de A esta dentro do CONTORNO de
-- B? Nao dentro do retangulo de B.

local TOLERANCIA_PONTO = 0.001

-- So conta como "por dentro" quem esta dentro de alguem MAIOR. Sem
-- isso, a letra 'O' e o furo dela se conteriam mutuamente: o centro da
-- caixa do 'O' cai no proprio furo, e o centro do furo cai dentro do
-- 'O'. Comparar area desempata na direcao certa — o furo e sempre
-- menor que a letra.
local function medir_vetores(vetores)
   local dados = {}
   for i, obj in ipairs(vetores) do
      local d = {obj = obj, area = 0}
      pcall(function() d.contorno = obj:GetContour() end)
      pcall(function()
         local b = obj:GetBoundingBox()
         d.centro = b.Centre
         d.x0, d.y0 = b.BLC.x, b.BLC.y
         d.x1, d.y1 = b.TRC.x, b.TRC.y
      end)
      if d.contorno ~= nil then
         pcall(function() d.area = d.contorno.Area or 0 end)
         pcall(function() d.fechado = d.contorno.IsClosed end)
      end
      dados[i] = d
   end
   return dados
end

local function centro_na_caixa(b, a)
   -- Filtro barato antes do teste caro: se o centro de A nem cai no
   -- retangulo de B, nao ha como estar dentro do contorno de B. Com
   -- 461 vetores num arquivo, isso e a diferenca entre segundos e
   -- minutos.
   if b.x0 == nil or a.centro == nil then return false end
   return a.centro.x >= b.x0 and a.centro.x <= b.x1
      and a.centro.y >= b.y0 and a.centro.y <= b.y1
end

-- Devolve duas listas de CadObject: os que cortam por dentro e os que
-- cortam por fora. Regra de paridade, a mesma do corte_dxf.py: quem
-- esta dentro de um numero IMPAR de outros e interno. Cobre o 'B' de
-- dois furos e a ilha dentro do furo.
local function classificar(vetores)
   local dados = medir_vetores(vetores)
   local dentro, fora, semGeometria = {}, {}, 0

   for i, a in ipairs(dados) do
      if a.contorno == nil or a.centro == nil then
         semGeometria = semGeometria + 1
         fora[#fora + 1] = a.obj          -- sem medida: vai por fora
      else
         local nivel = 0
         for j, b in ipairs(dados) do
            if i ~= j and b.contorno ~= nil and b.area > a.area
                     and centro_na_caixa(b, a) then
               local ok, r = pcall(function()
                  return b.contorno:IsPointInside(a.centro, TOLERANCIA_PONTO)
               end)
               if ok and r then nivel = nivel + 1 end
            end
         end
         if nivel % 2 == 1 then
            dentro[#dentro + 1] = a.obj
         else
            fora[#fora + 1] = a.obj
         end
      end
   end
   return dentro, fora, semGeometria
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

-- A selecao copiada pra uma tabela ANTES de qualquer medicao: medir
-- exige mexer na selecao, e o primeiro objeto medido destruiria a
-- original. Devolve {} quando nao ha nada selecionado.
local function selecao_atual(trabalho)
   local selecao = trabalho.Selection
   local vazia = true
   pcall(function() vazia = selecao.IsEmpty end)
   if vazia then return {} end

   local objetos = {}
   local ok = pcall(function()
      local pos = selecao:GetHeadPosition()
      while pos ~= nil do
         local a, b = selecao:GetNext(pos)
         if a == nil then break end
         objetos[#objetos + 1] = a
         pos = b
      end
   end)
   if not ok then return nil end
   return objetos
end

local function todos_os_vetores(trabalho)
   local objetos = {}
   local gerente = trabalho.LayerManager
   local posC = gerente:GetHeadPosition()
   while posC ~= nil do
      local camada
      local okC = pcall(function()
         local a, b = gerente:GetNext(posC)
         camada = a
         posC = b
      end)
      if not okC or camada == nil then break end
      local pos = camada:GetHeadPosition()
      while pos ~= nil do
         local objeto
         local okO = pcall(function()
            local a, b = camada:GetNext(pos)
            objeto = a
            pos = b
         end)
         if not okO or objeto == nil then break end
         objetos[#objetos + 1] = objeto
      end
   end
   return objetos
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

   -- ============ ONDE ESTA O ZERO, E ONDE ESTAO OS VETORES =========
   --
   -- A maquina cortou deslocada (08/09/2026): "nao esta reconhecendo o
   -- zero que fica no canto inferior esquerdo da folha".
   --
   -- O gadget NAO define o zero do trabalho — isso e o Job Setup do
   -- Aspire (posicao do datum XY). O que ele passa e o ToolpathPosData,
   -- que so diz pra onde a ferramenta VOLTA (Home) e a altura segura.
   --
   -- Entao, antes de mexer em qualquer coisa, este bloco so MOSTRA: o
   -- tamanho do material, onde esta a origem dele, e em que coordenadas
   -- os vetores realmente estao. Um PDF arrastado chega com as
   -- coordenadas da PAGINA — ja vimos vetor em X:6891mm porque a pagina
   -- tinha 4,2 metros. Se os vetores estiverem longe da origem, a
   -- maquina corta deslocado mesmo com o zero certo na mesa.
   --
   -- So le. Nao altera percurso, material nem origem.
   anotar("")
   anotar("=== onde esta o zero, e onde estao os vetores ===")
   pcall(function()
      local pos = ToolpathPosData()
      anotar(string.format("  ToolpathPosData: HomeX=%s HomeY=%s HomeZ=%s SafeZ=%s",
                           tostring(pos.HomeX), tostring(pos.HomeY),
                           tostring(pos.HomeZ), tostring(pos.SafeZ)))
   end)
   pcall(function()
      local bloco = trabalho.MaterialBlock
      if bloco == nil then
         anotar("  MaterialBlock: nao consegui obter")
         return
      end
      anotar(string.format("  material: %s x %s x %s  InMM=%s",
                           tostring(bloco.Width), tostring(bloco.Height),
                           tostring(bloco.Thickness), tostring(bloco.InMM)))
      anotar("  XYOrigin = " .. numa_linha(bloco.XYOrigin) ..
             "   ZOrigin = " .. numa_linha(bloco.ZOrigin))
   end)
   pcall(function()
      -- Onde os vetores estao de verdade. Se o canto inferior esquerdo
      -- nao for perto de (0,0), esta e a explicacao do deslocamento.
      local todos = todos_os_vetores(trabalho)
      local x0, y0, x1, y1
      for _, obj in ipairs(todos) do
         pcall(function()
            local b = obj:GetBoundingBox()
            if x0 == nil or b.BLC.x < x0 then x0 = b.BLC.x end
            if y0 == nil or b.BLC.y < y0 then y0 = b.BLC.y end
            if x1 == nil or b.TRC.x > x1 then x1 = b.TRC.x end
            if y1 == nil or b.TRC.y > y1 then y1 = b.TRC.y end
         end)
      end
      if x0 == nil then
         anotar("  (nenhum vetor pra medir)")
      else
         anotar(string.format("  vetores ocupam: X de %.1f a %.1f   Y de %.1f a %.1f",
                              x0, x1, y0, y1))
         anotar(string.format("  canto inferior esquerdo dos vetores: (%.1f , %.1f)", x0, y0))
      end
   end)

   anotar("")
   anotar("=== percursos ===")

   -- A SELECAO MANDA: havendo objeto selecionado, o percurso sai so pra
   -- ele. E assim que a moldura de acrilico e o gabarito ficam de fora
   -- sem ninguem apagar nada da chapa.
   local selecionados = selecao_atual(trabalho)
   if selecionados == nil then
      anotar("  PAREI: havia selecao e nao consegui ler quais objetos eram.")
      gravar()
      MessageBox("Voce tem objeto selecionado, mas eu nao consegui ler QUAIS sao.\n\n" ..
                 "Nao criei percurso nenhum - seguir pegaria a chapa inteira.\n\n" ..
                 "Tire a selecao e rode de novo pra cortar tudo.")
      return false
   end

   local alvos = selecionados
   if #alvos > 0 then
      anotar("  " .. #alvos .. " objeto(s) selecionado(s) — so eles viram percurso")
   else
      alvos = todos_os_vetores(trabalho)
      anotar("  nada selecionado — pegando os " .. #alvos .. " vetores do trabalho")
   end

   local feitos = 0

   if #alvos == 0 then
      anotar("  (nao ha vetor nenhum pra cortar)")
   else
      -- Classifica com a geometria do proprio Aspire (IsPointInside),
      -- nao pela caixa envolvente — ver o bloco la em cima.
      local dentro, fora, semGeo = classificar(alvos)
      anotar("  por dentro: " .. #dentro .. "   por fora: " .. #fora)
      if semGeo > 0 then
         anotar("  " .. semGeo .. " sem geometria legivel foram por fora")
      end

      -- O INTERNO PRIMEIRO. A ordem na lista e a ordem de usinagem:
      -- depois que o contorno externo fecha, a peca solta e se mexe.
      if #dentro > 0 then
         selecionar_objetos(trabalho, dentro)
         if criar_percurso("CORTE INTERNO", ferramenta, LADO_DENTRO, p) then
            feitos = feitos + 1
         end
      else
         anotar("  (nada por dentro — nenhuma peca com furo)")
      end

      if #fora > 0 then
         selecionar_objetos(trabalho, fora)
         if criar_percurso("CORTE EXTERNO", ferramenta, LADO_FORA, p) then
            feitos = feitos + 1
         end
      end
   end

   anotar("  total de percursos no trabalho: " .. tostring(ToolpathManager().Count))
   gravar()

   if feitos == 0 then
      MessageBox("Nenhum percurso criado.\n\nVeja:\n" .. DESTINO)
      return false
   end

   local recado = feitos .. " percurso(s) criado(s)."
   -- SO ASCII daqui pra baixo. O MessageBox do Aspire le a string como
   -- ANSI, entao um travessao aparece como "a-EUR-aspas" na tela — foi
   -- o que o Flavio viu em 08/09/2026. Mesma regra dos .bat do projeto.
   if feitos >= 2 then
      recado = recado .. "\n\nCORTE INTERNO primeiro, CORTE EXTERNO depois:\n" ..
               "a ordem da lista e a ordem de usinagem."
   end
   if interna == nil and externa == nil then
      recado = recado .. "\n\nO arquivo nao trazia camada nomeada, entao classifiquei\n" ..
               "pela geometria: o centro de cada vetor foi testado dentro\n" ..
               "do contorno dos outros, pelo proprio Aspire.\n\n" ..
               "Confira na tela antes de mandar pra maquina."
   end
   MessageBox(recado)
   return true
end
