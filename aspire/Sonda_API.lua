-- VECTRIC LUA SCRIPT
--
-- Sonda da API do Aspire 8.5 — quarta versão: atrás dos MÉTODOS.
--
-- O que já se sabe das anteriores:
--   v1 — a 8.5 tem as classes de criação de percurso (era a dúvida que
--        travava tudo)
--   v2 — a ligação é luabind, e ele responde com a assinatura C++ certa
--        quando a gente chama errado
--   v3 — os campos de ProfileParameterData: CutDepth, ProfileSide,
--        CutDirection, TabLength, TabThickness...
--
-- Falta a chamada que CRIA o percurso. Ela deve estar no gerenciador do
-- trabalho, que na v3 veio vazio porque não havia projeto aberto.
--
-- ATENÇÃO: rode com um trabalho NOVO aberto, não com produção de
-- verdade. Esta sonda não escreve no projeto, mas chama métodos com
-- argumentos inválidos de propósito pra colher a assinatura — e em
-- trabalho de cliente não se faz esse tipo de experiência.
--
-- Rode em: Gadgets -> Sonda API

local DESTINO = "C:\\Users\\flavi\\Desktop\\etiquetas_python\\aspire\\api_8_5.txt"

local NOMES = {
   -- criar e calcular percurso: o que a gente está caçando
   "CreateProfilingToolpath", "CreateProfileToolpath", "CreateToolpath",
   "CreatePocketToolpath", "CreateDrillingToolpath", "CreateVCarveToolpath",
   "CalculateToolpath", "CalculateProfileToolpath", "Calculate",
   "AddToolpath", "AddNewToolpath", "InsertToolpath", "UpdateToolpath",
   -- percorrer o que já existe
   "Count", "GetHeadPosition", "GetNext", "GetToolpath", "GetFirstToolpath",
   "GetToolpathList", "RemoveToolpath", "DeleteToolpath", "Refresh",
   -- ferramentas
   "GetTool", "FindTool", "GetToolByName", "GetToolList", "GetToolGroups",
   "LoadToolDatabase", "GetToolDatabase", "Tool", "ToolDia",
   -- salvar e pos-processar
   "SaveToolpaths", "SaveToolpath", "PostProcess", "GetPostProcessor",
   "SetPostProcessor", "AddToolpathToSave",
   -- trabalho e desenho
   "Exists", "Name", "JobParameters", "Selection", "LayerManager",
   "ToolpathManager", "Refresh2DView", "AddContoursToJob",
   "CreateJobBoundary", "GetLayerWithName", "SelectAll", "GetSelection",
}

local saida = {}
local function anotar(t) saida[#saida + 1] = t end

-- Chama com lixo. O luabind recusa e, ao recusar, imprime as formas
-- certas de chamar — que é a documentação que a Vectric tirou do ar.
local function assinatura(funcao, dono)
   local ok, erro = pcall(funcao, dono, "\1lixo\1", -987654321, {})
   if ok then return "(aceitou argumentos aleatorios — cuidado)" end
   local texto = tostring(erro)
   -- só interessa quando ele lista as candidatas
   if texto:find("candidates") or texto:find("overload") then
      return texto
   end
   return "erro: " .. texto
end

local function investigar(rotulo, objeto)
   anotar("")
   anotar("=== " .. rotulo .. " ===")
   if objeto == nil then
      anotar("  nil — nao deu pra obter")
      return
   end
   local achados = 0
   for _, nome in ipairs(NOMES) do
      local ok, valor = pcall(function() return objeto[nome] end)
      if ok and valor ~= nil then
         achados = achados + 1
         local tipo = type(valor)
         if tipo == "function" then
            anotar("  " .. nome .. "()")
            for linha in assinatura(valor, objeto):gmatch("[^\r\n]+") do
               anotar("        " .. linha)
            end
         else
            anotar(string.format("  %-26s %s = %s", nome, tipo, tostring(valor)))
         end
      end
   end
   if achados == 0 then anotar("  (nenhum dos nomes testados existe aqui)") end
end

function main(script_path)
   saida = {}
   anotar("SONDA DA API — Aspire 8.5 (v4: metodos)")

   local ok, trabalho = pcall(VectricJob)
   local existe = false
   if ok and trabalho ~= nil then
      local certo, valor = pcall(function() return trabalho.Exists end)
      existe = certo and valor == true
   end
   anotar("trabalho aberto: " .. tostring(existe))
   if not existe then
      anotar("")
      anotar("!!! SEM TRABALHO ABERTO — o gerenciador de percursos nao existe sem projeto.")
      anotar("!!! Abra um trabalho novo, desenhe um retangulo, e rode de novo.")
      MessageBox("Abra um trabalho novo no Aspire (com um retangulo desenhado)\n" ..
                 "e rode a sonda de novo.\n\nSem projeto aberto nao da pra ver\n" ..
                 "o gerenciador de percursos.")
      local arquivo = io.open(DESTINO, "w")
      if arquivo then arquivo:write(table.concat(saida, "\n")); arquivo:close() end
      return false
   end

   investigar("VectricJob (trabalho aberto)", trabalho)

   local certo, gerenciador = pcall(function() return trabalho.ToolpathManager end)
   investigar("job.ToolpathManager", certo and gerenciador or nil)

   local ok2, gerenciador2 = pcall(ToolpathManager)
   investigar("ToolpathManager() solto", ok2 and gerenciador2 or nil)

   local ok3, banco = pcall(ToolDatabase)
   investigar("ToolDatabase()", ok3 and banco or nil)

   local ok4, salvador = pcall(ToolpathSaver)
   investigar("ToolpathSaver()", ok4 and salvador or nil)

   local ok5, camadas = pcall(function() return trabalho.LayerManager end)
   investigar("job.LayerManager", ok5 and camadas or nil)

   local arquivo, erro = io.open(DESTINO, "w")
   if arquivo == nil then
      MessageBox("Nao consegui escrever em:\n" .. DESTINO .. "\n\n" .. tostring(erro))
      return false
   end
   arquivo:write(table.concat(saida, "\n"))
   arquivo:close()

   MessageBox("Sonda v4 concluida.\n\n" .. #saida .. " linhas em:\n" .. DESTINO)
   return true
end
