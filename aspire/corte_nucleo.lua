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

-- ================== SO O QUE ESTA SELECIONADO ======================
--
-- Por que NAO ha classificacao de aninhamento aqui dentro (08/09/2026):
-- foi tentada, pela caixa envolvente de cada vetor, e ERROU num arquivo
-- de producao. No "Mova Belo Horizonte" as 13 letras do texto caem
-- dentro da CAIXA do logo — que e uma forma varrida, com as letras no
-- vazio embaixo da curva — sem estarem dentro do logo. Resultado: 11
-- letras classificadas como furo e cortadas por dentro, 4 mm menores.
-- No "Rio de Janeiro" o mesmo codigo acertou, mas por sorte: o logo de
-- la e mais baixo e a caixa dele nao alcanca o texto.
--
-- A API do Aspire 8.5 nao expoe os pontos do vetor, so a caixa
-- (selection:GetBoundingBox). Sem os pontos nao da pra fazer o teste de
-- ponto-dentro-do-poligono, que e o unico que distingue "dentro do
-- desenho" de "dentro do retangulo do desenho".
--
-- Quem tem os pontos e o corte_dxf.py, lendo o PDF. Entao a
-- classificacao mora la, e chega aqui pronta, nas camadas do DXF. O
-- caminho da camada nomeada — o de cima, no main — e o unico que
-- garante a ordem furo-antes-do-contorno.
--
-- Sem camada nomeada, este gadget faz UM percurso com ProfileSide=0 e
-- avisa: o Aspire acerta o dentro/fora sozinho (confirmado 06/09/2026),
-- so a ORDEM e que fica por conta do acaso.

local function tem_selecao(trabalho)
   local vazia = true
   pcall(function() vazia = trabalho.Selection.IsEmpty end)
   return not vazia
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

   -- ============ SONDA: o que um VETOR sabe dizer de si? ============
   --
   -- Eu afirmei que a API so da a caixa envolvente e que por isso a
   -- classificacao teria que sair do Aspire. Mas eu nunca sondei o
   -- CadObject — a afirmacao veio de uma nota antiga, nao de teste.
   --
   -- Se aqui aparecer acesso aos PONTOS do vetor, ou uma pergunta do
   -- tipo "este ponto esta dentro de voce?", da pra classificar dentro
   -- do Aspire com a geometria de verdade, sem converter arquivo
   -- nenhum. E o que o Flavio pediu desde o comeco.
   --
   -- Nao cria, nao altera e nao apaga nada. So le, e nunca derruba a
   -- passada: tudo dentro de pcall.
   anotar("")
   anotar("=== sonda: o que um vetor sabe dizer de si ===")
   pcall(function()
      -- Junta TODOS os vetores, de todas as camadas: o primeiro objeto
      -- da primeira camada pode nao ser um vetor comum.
      local vetores = {}
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
            vetores[#vetores + 1] = objeto
         end
      end
      anotar("  vetores encontrados no trabalho: " .. #vetores)
      local amostra = vetores[1]

      if amostra == nil then
         anotar("  (nenhum vetor no trabalho pra sondar)")
         return
      end

      local nomes = {
         "Area", "Length", "Perimeter", "IsClosed", "Closed", "IsOpen",
         "NumberOfPoints", "PointCount", "NumPoints", "Count", "SpanCount",
         "NumSpans", "BoundingBox", "Bounds", "Name", "LayerName",
         "GetPoint", "GetPoints", "Points", "GetSpan", "Span", "Spans",
         "GetBoundingBox", "GetArea", "GetLength", "IsPointInside",
         "PointInside", "Contains", "ContainsPoint", "Inside",
         "GetPolyline", "ToPolyline", "GetContour", "Contours",
         "GetHeadPosition", "GetNext", "Clone", "Type", "ObjectType",
      }
      local function sondar(rotulo, alvo, lista)
         anotar("  --- " .. rotulo .. " ---")
         local viu = false
         for _, nome in ipairs(lista) do
            local ok, valor = pcall(function() return alvo[nome] end)
            if ok and valor ~= nil then
               viu = true
               local tipo = type(valor)
               if tipo == "function" then
                  -- luabind cospe a assinatura C++ de verdade quando se
                  -- chama errado. Chamar com lixo e como arrancar a
                  -- documentacao de dentro do programa.
                  local certo, erro = pcall(valor, alvo, "\1lixo\1", -987654321)
                  local texto = certo and "(aceitou lixo)" or tostring(erro):gsub("[\r\n]+", " | ")
                  anotar(string.format("    %-18s funcao: %s", nome, texto:sub(1, 160)))
               else
                  anotar(string.format("    %-18s %s = %s", nome, tipo, tostring(valor):sub(1, 70)))
               end
            end
         end
         if not viu then anotar("    (nenhum dos nomes testados respondeu)") end
      end

      sondar("CadObject", amostra, nomes)

      -- O CadObject tem GetContour() -> Contour*. E ai que mora a
      -- geometria de verdade. Se o Contour souber dizer se um ponto
      -- esta dentro dele, ou entregar os pontos, a classificacao pode
      -- acontecer aqui dentro e o PDF continua sendo o arquivo.
      --
      -- Tenta em VARIOS objetos, nao so no primeiro: o primeiro da
      -- primeira camada pode nao ser um vetor comum (grupo, bitmap,
      -- texto), e foi nil na sonda de 08/09/2026.
      local contorno, deQual, tentados, erroContour = nil, 0, 0, nil
      for i, obj in ipairs(vetores) do
         tentados = i
         local ok, r = pcall(function() return obj:GetContour() end)
         if ok and r ~= nil then
            contorno = r
            deQual = i
            break
         end
         if not ok and erroContour == nil then
            erroContour = tostring(r):gsub("[\r\n]+", " | "):sub(1, 160)
         end
         if i >= 20 then break end
      end
      anotar(string.format("  (GetContour testado em %d objeto(s); respondeu no #%d)",
                           tentados, deQual))
      if erroContour ~= nil then
         anotar("  erro tipico: " .. erroContour)
      end

      if contorno == nil then
         anotar("  --- Contour: nenhum objeto devolveu contorno ---")
      else
         sondar("Contour", contorno, {
            "Area", "GetArea", "Length", "GetLength", "Perimeter",
            "IsClosed", "Closed", "IsOpen", "IsPointInside", "PointInside",
            "Contains", "ContainsPoint", "Inside", "IsInside",
            "Count", "SpanCount", "GetSpanCount", "NumberOfSpans",
            "GetSpan", "Span", "GetPoint", "GetPoints", "Points",
            "GetStartPoint", "GetEndPoint", "StartPoint", "EndPoint",
            "GetBoundingBox", "BoundingBox", "GetHeadPosition", "GetNext",
            "IsClockwise", "Direction", "Reverse", "Clone",
        })
      end

      -- Box2D: a caixa que o proprio objeto entrega, sem passar pela
      -- selecao. Se der, some a gambiarra de selecionar-um-por-vez.
      local caixa = nil
      pcall(function() caixa = amostra:GetBoundingBox() end)
      if caixa ~= nil then
         sondar("Box2D (do proprio objeto)", caixa, {
            "BLC", "TRC", "BRC", "TLC", "Width", "Height", "XMin", "XMax",
            "YMin", "YMax", "Centre", "Center", "IsValid", "Contains", "Merge",
         })
      end
   end)

   anotar("")
   anotar("=== percursos ===")

   local interna, nomeInterna = achar_camada(trabalho, "CORTE INTERNO")
   local externa, nomeExterna = achar_camada(trabalho, "CORTE EXTERNO")
   local feitos = 0

   if interna ~= nil or externa ~= nil then
      -- O CAMINHO BOM. As camadas vieram do corte_dxf.py, que leu o PDF
      -- e classificou com os pontos do vetor na mao. Dois percursos, e o
      -- INTERNO PRIMEIRO: a ordem na lista e a ordem de usinagem.
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
      -- SEM camada nomeada. UM percurso, com ProfileSide=0: o Aspire
      -- detecta o aninhamento sozinho e corta o furo por dentro
      -- (confirmado na tela em 06/09/2026). O que ele NAO garante e a
      -- ORDEM — e nao ha como pedir isso pela API.
      --
      -- Se houver selecao, ela manda: o percurso sai so no que esta
      -- selecionado. E assim que a moldura de acrilico fica de fora.
      if tem_selecao(trabalho) then
         anotar("  sem camada nomeada — um percurso so, no que esta SELECIONADO")
      else
         anotar("  sem camada nomeada e nada selecionado — um percurso so, na chapa toda")
      end
      anotar("  o Aspire acerta dentro/fora sozinho; a ORDEM e que nao fica garantida")
      if criar_percurso("CORTE", ferramenta, LADO_FORA, p) then feitos = 1 end
   end

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
   if interna == nil and externa == nil then
      recado = recado .. "\n\nSaiu UM percurso so. O Aspire acerta o dentro/fora\n" ..
               "sozinho, mas a ORDEM (furo antes do contorno) nao esta\n" ..
               "garantida.\n\n" ..
               "Se quiser a ordem agora: selecione so os furos e clique,\n" ..
               "depois selecione so os contornos e clique de novo — sao\n" ..
               "dois percursos, na ordem em que voce criar."
   end
   MessageBox(recado)
   return true
end
