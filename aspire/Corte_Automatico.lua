-- VECTRIC LUA SCRIPT
--
-- Primeiro gerador de percurso — versão de prova.
--
-- Responde duas perguntas de uma vez:
--
-- 1) COMO SE PEGA A FERRAMENTA. O GetTool devolveu vazio em todas as
--    formas de grupo tentadas — inclusive com uma ferramenta de nome
--    exato solta na raiz de "Imperial Tools". Suspeita: ToolDatabase()
--    nasce vazio e precisa ser carregado do arquivo; existe um
--    GetToolDatabaseLocation() solto na API, que só faz sentido pra
--    isso. Se nada funcionar, pega de um percurso que já exista no
--    trabalho — vem pronta e correta do próprio programa.
--
-- 2) QUE NÚMERO É CADA OPÇÃO. A API guarda ProfileSide e CutDirection
--    como número, e o Toolpath pronto não devolve esses campos de
--    volta. Então cria com 0 e 0 e o usuário abre o percurso pra ver o
--    que acendeu. Errar aqui não é peça torta: a fresa passa do lado
--    errado da linha, a letra sai menor que o pedido e a chapa vai
--    junto.
--
-- Parâmetros de PVC 10 mm (de corte_parametros.py): fresa Topo Raso
-- (4 mm), profundidade 11 mm (10 da chapa + 1 pra cortar passante),
-- rampa suave de 10 mm.
--
-- Rode num trabalho de TESTE, com vetores fechados selecionados, e de
-- preferência no mesmo que tem o percurso "Corte 1".
--
-- Rode em: Gadgets -> Corte Automatico

local DESTINO = "C:\\Users\\flavi\\Desktop\\etiquetas_python\\aspire\\corte_resultado.txt"

local GRUPO = "Fresa 4 mm"
local FERRAMENTA = "Topo Raso (4 mm)"
local PROFUNDIDADE = 11.0
local RAMPA_MM = 10.0
local LIXO = "___nao_existe___"

local saida = {}
local function anotar(t) saida[#saida + 1] = t end

-- Mensagem de erro do luabind vem com quebra de linha no meio; no
-- relatório atrapalha mais do que ajuda.
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

local function tentar_grupos(banco)
   local grupos = {
      GRUPO, "fresa 4mm", "Imperial Tools | " .. GRUPO, "Imperial Tools|" .. GRUPO,
      "Imperial Tools\\" .. GRUPO, "Imperial Tools/" .. GRUPO, "Imperial Tools", "",
   }
   for _, grupo in ipairs(grupos) do
      local ok, ferramenta = pcall(function() return banco:GetTool(grupo, FERRAMENTA) end)
      anotar("  GetTool('" .. grupo .. "') -> " .. numa_linha(ferramenta))
      if ok and ferramenta ~= nil then return ferramenta end
   end
   return nil
end

local function investigar_banco(banco)
   anotar("")
   anotar("=== investigando o banco ===")
   anotar("  ToolDatabase() = " .. numa_linha(banco))

   local ok, caminho = pcall(GetToolDatabaseLocation)
   anotar("  GetToolDatabaseLocation() = " .. numa_linha(caminho))

   for _, nome in ipairs({"Load", "LoadDatabase", "LoadFromFile", "LoadToolDatabase",
                          "Open", "Read", "ReadFrom", "Init", "Refresh", "Reload",
                          "SetLocation", "Count", "GetCount", "GetHeadPosition",
                          "GetNext", "GetFirstTool", "GetGroup", "GetToolGroup"}) do
      local certo, valor = pcall(function() return banco[nome] end)
      if certo and valor ~= nil then
         if type(valor) == "function" then
            local passou, erro = pcall(valor, banco, LIXO, -1)
            anotar("  ." .. nome .. "() -> " ..
                   (passou and "aceitou lixo" or numa_linha(erro)))
         else
            anotar("  ." .. nome .. " = " .. type(valor) .. " " .. numa_linha(valor))
         end
      end
   end

   if ok and caminho ~= nil then
      for _, metodo in ipairs({"Load", "LoadDatabase", "LoadFromFile", "Open", "Read"}) do
         local certo, r = pcall(function() return banco[metodo](banco, caminho) end)
         if certo then
            anotar("  " .. metodo .. "(caminho) -> " .. numa_linha(r))
            local achou = tentar_grupos(banco)
            if achou ~= nil then
               anotar("  ACHOU depois de " .. metodo)
               return achou
            end
         end
      end
   end

   -- O banco se percorre, como se faz com os percursos?
   local certo, posicao = pcall(function() return banco:GetHeadPosition() end)
   if certo and posicao ~= nil then
      anotar("  -- percorrendo o banco --")
      local n = 0
      while posicao ~= nil and n < 80 do
         local item
         local passou = pcall(function()
            local a, b = banco:GetNext(posicao)
            item = a
            posicao = b
         end)
         if not passou or item == nil then break end
         n = n + 1
         local temNome, nome = pcall(function() return item.Name end)
         nome = temNome and tostring(nome) or "?"
         anotar("     " .. n .. ": " .. nome)
         if nome == FERRAMENTA then
            anotar("     ^ essa serve")
            return item
         end
      end
   else
      anotar("  (o banco nao se percorre com GetHeadPosition)")
   end
   return nil
end

-- Constroi a ferramenta do zero, com os valores do cadastro da casa.
-- O ToolDatabase() nasce vazio e nao ha como carrega-lo pelo Lua (06/09
-- /2026), mas o construtor de Tool aceita (nome, numero) — e preencher
-- os campos na mao e ate melhor: o banco tem DUAS ferramentas chamadas
-- "Topo Raso (4 mm)" dentro do mesmo grupo, entao pedir pelo nome seria
-- torcer pra vir a certa.
local function construir_ferramenta()
   anotar("")
   anotar("=== construindo a ferramenta ===")
   -- O segundo argumento e o TIPO. Descoberto que 0 = Ball Nose (ponta
   -- esferica), que nao serve: a casa corta com topo raso. Varre todos e
   -- fica com o End Mill — e so encerra quando achar, sem atalho.
   local reserva = nil
   for tipo = 0, 9 do
      local ok, ferramenta = pcall(function() return Tool(FERRAMENTA, tipo) end)
      if ok and ferramenta ~= nil then
         local descricao = numa_linha(ferramenta)
         anotar("  Tool(nome, " .. tipo .. ") -> " .. descricao)
         -- preenche com os valores da casa e confere se pegaram
         local campos = {
            ToolDia = 4.0, Stepdown = 11.0, Stepover = 2.0,
            FeedRate = 2000.0, PlungeRate = 1000.0, SpindleSpeed = 18000.0,
            ToolNumber = 1,
         }
         for campo, valor in pairs(campos) do
            pcall(function() ferramenta[campo] = valor end)
         end
         local conferencia = {}
         for campo, esperado in pairs(campos) do
            local certo, lido = pcall(function() return ferramenta[campo] end)
            conferencia[#conferencia + 1] = campo .. "=" ..
               (certo and tostring(lido) or "?") ..
               ((certo and lido == esperado) and "" or " (NAO PEGOU)")
         end
         table.sort(conferencia)
         anotar("     " .. table.concat(conferencia, "  "))
         if descricao:find("End Mill") then
            anotar("     ^ TOPO RASO: tipo " .. tipo .. " e o que a casa usa")
            return ferramenta
         end
         reserva = reserva or ferramenta
      else
         anotar("  Tool(nome, " .. tipo .. ") -> " .. numa_linha(ferramenta))
      end
   end
   anotar("  nenhum tipo veio como End Mill — seguindo com o primeiro que deu")
   return reserva
end

-- Reserva: a ferramenta de um percurso que o usuário já montou.
local function pegar_de_percurso_existente()
   local gerenciador = ToolpathManager()
   anotar("")
   anotar("=== reserva: percursos existentes (" .. tostring(gerenciador.Count) .. ") ===")
   local posicao = gerenciador:GetHeadPosition()
   while posicao ~= nil do
      local percurso
      local ok = pcall(function()
         local a, b = gerenciador:GetNext(posicao)
         percurso = a
         posicao = b
      end)
      if not ok or percurso == nil then break end
      local temFerr, ferramenta = pcall(function() return percurso.Tool end)
      if temFerr and ferramenta ~= nil then
         anotar("  peguei de '" .. tostring(percurso.Name) .. "': " ..
                tostring(ferramenta.Name) .. " (passada " ..
                tostring(ferramenta.Stepdown) .. ")")
         return ferramenta
      end
   end
   anotar("  nenhum percurso com ferramenta neste trabalho")
   return nil
end

function main(script_path)
   saida = {}
   anotar("CORTE AUTOMATICO — prova de criacao de percurso")

   local trabalho = VectricJob()
   if trabalho.Exists ~= true then
      MessageBox("Abra um trabalho de teste com vetores fechados.")
      return false
   end

   anotar("")
   anotar("=== ferramenta ===")
   local banco = ToolDatabase()
   local ferramenta = tentar_grupos(banco)
   if ferramenta == nil then ferramenta = investigar_banco(banco) end
   if ferramenta == nil then ferramenta = pegar_de_percurso_existente() end
   if ferramenta == nil then ferramenta = construir_ferramenta() end

   if ferramenta == nil then
      gravar()
      MessageBox("Nao consegui obter a ferramenta, nem do banco nem de um\n" ..
                 "percurso existente.\n\nRode no trabalho que tem o 'Corte 1'.\n\n" ..
                 "Detalhes em:\n" .. DESTINO)
      return false
   end

   anotar("  usando: " .. tostring(ferramenta.Name) ..
          " dia " .. tostring(ferramenta.ToolDia) ..
          " passada " .. tostring(ferramenta.Stepdown))

   local rampa = RampingData()
   rampa.DoRamping = true
   rampa.RampType = 0            -- suposto "Suave", a primeira opcao da tela
   rampa.RampDistance = RAMPA_MM

   local entrada = LeadInOutData()
   local posicao = ToolpathPosData()

   local seletor = GeometrySelector()
   seletor.SelectClosed = true
   seletor.SelectOpen = false
   seletor.ToolDia = ferramenta.ToolDia

   local parametros = ProfileParameterData()
   parametros.Name = "TESTE lado=0 dir=0"
   parametros.CutDepth = PROFUNDIDADE
   parametros.StartDepth = 0.0
   parametros.ProfileSide = 0
   parametros.CutDirection = 0
   parametros.Allowance = 0.0
   parametros.CreateSquareCorners = false

   local gerenciador = ToolpathManager()
   anotar("")
   anotar("=== criacao ===")
   anotar("  percursos antes: " .. tostring(gerenciador.Count))

   -- Os dois booleanos finais nao estao documentados. Tenta as quatro
   -- combinacoes e anota qual passou.
   local criado = nil
   for _, par in ipairs({{true, true}, {true, false}, {false, true}, {false, false}}) do
      local ok, resultado = pcall(function()
         return gerenciador:CreateProfilingToolpath(
            parametros.Name, ferramenta, parametros, rampa, entrada,
            posicao, seletor, par[1], par[2])
      end)
      anotar("  bools (" .. tostring(par[1]) .. ", " .. tostring(par[2]) .. ") -> " ..
             (ok and ("OK " .. numa_linha(resultado)) or numa_linha(resultado)))
      if ok and resultado ~= nil then
         criado = par
         break
      end
   end

   anotar("  percursos depois: " .. tostring(ToolpathManager().Count))
   gravar()

   if criado == nil then
      MessageBox("Nenhuma combinacao criou o percurso.\n\nVeja:\n" .. DESTINO)
      return false
   end

   MessageBox("Percurso criado.\n\n" ..
              "ABRA o percurso 'TESTE lado=0 dir=0' e me diga:\n\n" ..
              "1) em 'Usinar vetores': Fora/Direita, Dentro/Esquerda ou Sobre?\n" ..
              "2) em 'Direcao': Subida ou Convencional?\n" ..
              "3) na aba Rampas: o tipo esta em Suave?")
   return true
end
