-- VECTRIC LUA SCRIPT
--
-- Sonda da API do Aspire 8.5 — quinta versão: os números por trás das opções.
--
-- Já se sabe criar percurso:
--   CreateProfilingToolpath(ToolpathManager&, nome, Tool*, ProfileParameterData*,
--       RampingData*, LeadInOutData*, ToolpathPosData_Base*, GeometrySelector*,
--       bool, bool)
--
-- Falta traduzir o que está escrito na tela pro que a API espera:
--   "Fora / Direita"  -> ProfileSide = ?
--   "Subida" (climb)  -> CutDirection = ?
--   rampa suave 10 mm -> quais campos de RampingData?
--
-- Em vez de adivinhar, esta sonda LÊ DE VOLTA o percurso que o usuário
-- já montou na mão. O que a tela mostra e o que o objeto guarda são a
-- mesma coisa — então o percurso dele é a tabela de conversão.
--
-- PRECISA: um trabalho aberto com PELO MENOS UM percurso de perfil já
-- criado (Fora/Direita, Subida, rampa suave 10 mm).
--
-- Não cria, não apaga e não altera percurso nenhum. Só lê.
--
-- Rode em: Gadgets -> Sonda API

local DESTINO = "C:\\Users\\flavi\\Desktop\\etiquetas_python\\aspire\\api_8_5.txt"

local saida = {}
local function anotar(t) saida[#saida + 1] = t end

local function tentar(objeto, nome)
   local ok, valor = pcall(function() return objeto[nome] end)
   if ok and valor ~= nil then return valor end
   return nil
end

local function listar(rotulo, objeto, nomes)
   anotar("")
   anotar("=== " .. rotulo .. " ===")
   if objeto == nil then
      anotar("  nil")
      return
   end
   local achou = false
   for _, nome in ipairs(nomes) do
      local valor = tentar(objeto, nome)
      if valor ~= nil then
         achou = true
         local tipo = type(valor)
         if tipo == "function" then
            local ok, erro = pcall(valor, objeto, "\1lixo\1", -987654321, {})
            local texto = ok and "(aceitou lixo)" or tostring(erro):gsub("[\r\n]+", " | ")
            anotar(string.format("  %-26s funcao: %s", nome, texto))
         else
            anotar(string.format("  %-26s %s = %s", nome, tipo, tostring(valor)))
         end
      end
   end
   if not achou then anotar("  (nenhum dos nomes testados)") end
end

local CAMPOS_RAMPA = {
   "Active", "Enabled", "DoRamping", "AddRamps", "RampType", "Type",
   "RampLength", "Length", "Distance", "RampDistance",
   "Angle", "MaxAngle", "RampAngle", "Smooth", "ZigZag", "Spiral",
   "RampOnEntry", "RampInOnly", "DoRampIn", "UseDistance", "UseAngle",
}
local CAMPOS_ENTRADA = {
   "Active", "Enabled", "DoLeadInOut", "Type", "LeadInLength", "LeadOutLength",
   "Length", "Radius", "Angle", "Distance", "Overcut", "OvercutDistance",
   "DoLeadIn", "DoLeadOut", "SpiralLeadIn",
}
local CAMPOS_POS = {
   "SafeZ", "HomeX", "HomeY", "HomeZ", "StartZGap", "XYOrigin", "ZOrigin",
}
local CAMPOS_PERCURSO = {
   "Name", "Notes", "Tool", "Visible", "Calculated", "SheetIndex",
   "ActiveSheetIndex", "MachiningTime", "GetProfileParameterData",
   "ProfileParameterData", "ParameterData", "Parameters", "GetParameters",
   "CutDepth", "StartDepth", "ProfileSide", "CutDirection",
}

function main(script_path)
   saida = {}
   anotar("SONDA DA API — Aspire 8.5 (v5: numeros por tras das opcoes da tela)")

   -- 1. os objetos novos, pra saber os campos e o padrao de fabrica
   local ok, rampa = pcall(RampingData)
   listar("RampingData (recem criado)", ok and rampa or nil, CAMPOS_RAMPA)

   local ok2, entrada = pcall(LeadInOutData)
   listar("LeadInOutData (recem criado)", ok2 and entrada or nil, CAMPOS_ENTRADA)

   local ok3, pos = pcall(ToolpathPosData)
   listar("ToolpathPosData (recem criado)", ok3 and pos or nil, CAMPOS_POS)

   -- 2. o percurso que o usuario montou na mao: a tabela de conversao
   local certo, trabalho = pcall(VectricJob)
   if not certo or trabalho == nil or tentar(trabalho, "Exists") ~= true then
      anotar("")
      anotar("!!! SEM TRABALHO ABERTO.")
      MessageBox("Abra o trabalho com o percurso de perfil ja criado\ne rode de novo.")
   else
      local gerenciador = ToolpathManager()
      local quantos = tentar(gerenciador, "Count") or 0
      anotar("")
      anotar("=== PERCURSOS NO TRABALHO: " .. tostring(quantos) .. " ===")
      if quantos == 0 then
         anotar("  Nenhum. Crie um percurso de perfil na mao (Fora/Direita, Subida,")
         anotar("  rampa suave 10 mm) e rode a sonda de novo — e dele que eu tiro")
         anotar("  os numeros que a API usa.")
         MessageBox("Nao ha percurso criado neste trabalho.\n\n" ..
                    "Crie o percurso de perfil na mao, do jeito que voce faz,\n" ..
                    "e rode a sonda de novo.")
      else
         local posicao = gerenciador:GetHeadPosition()
         local indice = 0
         while posicao ~= nil do
            local percurso
            percurso, posicao = gerenciador:GetNext(posicao)
            if percurso == nil then break end
            indice = indice + 1
            listar("percurso #" .. indice, percurso, CAMPOS_PERCURSO)

            local ferramenta = tentar(percurso, "Tool")
            listar("percurso #" .. indice .. " . Tool", ferramenta, {
               "Name", "ToolNumber", "ToolDia", "Stepdown", "Stepover",
               "ToolTypeText", "Notes", "FeedRate", "PlungeRate", "SpindleSpeed",
               "InMM", "Units",
            })
         end
      end
   end

   local arquivo, erro = io.open(DESTINO, "w")
   if arquivo == nil then
      MessageBox("Nao consegui escrever em:\n" .. DESTINO .. "\n\n" .. tostring(erro))
      return false
   end
   arquivo:write(table.concat(saida, "\n"))
   arquivo:close()
   MessageBox("Sonda v5 concluida.\n\n" .. #saida .. " linhas em:\n" .. DESTINO)
   return true
end
