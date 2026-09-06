-- VECTRIC LUA SCRIPT

--require("mobdebug").start()
require "strict"

g_version = "1.0"
g_width = 1022
g_height = 653
g_html_file = "Setup_Sheet_Editor.html"

--Set options
  options = {}
  options.InputFile = ""
  options.GadgetPath = ""
  options.FileType = ""
  options.Colour = "5c5c5c"
  options.TextColour="646566"
  options.BorderColour="646566"
  options.Title = "Job Setup Sheet"
  options.Custom = ""
  options.DrawVectors = true
  options.JobNotes= true
  options.MaterialSetup = true
  options.ToolpathsSummary = true
  options.ToolpathBreakdown = true
  options.ReturnDefault = false
  options.windowWidth = g_width
  options.windowHeight = g_height 

--[[--------------------Main Function------------------------------------
|
|     Checks if job exists, checks if objects have been selected on job, sets dialog.
|
|
--]]

function main(path)
--Check Version of software is V8
local version = GetAppVersion()
  if version < 8 then
    MessageBox("Your software needs an upgrade to V8.0 before using this gadget")
    return false
  end
  --load options from registry
LoadDefaults(options)
 
 -- Display the dialog
    local displayed_dialog = -1
    while displayed_dialog == -1 do
      displayed_dialog = DisplayDialog(path,options)
    end
    
    if not displayed_dialog then 
      return false
    end
  

  
--Try to open default job setup sheet
local GLocal = GetGadgetsLocation().."\\__Setup_Sheet\\Setup_Sheet.lua"
local DefaultSheet = io.open(GLocal)
  if DefaultSheet == nil then
     MessageBox("Could not find Original Job Setup Sheet Gadget from default install, Closing")
     return false
  end
  
--Check to see if custom gadget sheet already exists
local CustomSheet = io.open(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.lua","r")
  --if it does not exist it will create a folder and open the default gadget and save to new location
  if CustomSheet == nil then
    options.Custom = "first time"
    local os = require "os"
    os.execute([[mkdir ]]..[["]]..options.GadgetPath..[[__Setup_Sheet"]])
    CustomSheet = assert(io.output(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.lua"))
    local ReadDefault = DefaultSheet:read("*all")
    CustomSheet:write(ReadDefault)
    CustomSheet:close() 
    CustomSheet = assert(io.open(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.lua"))
      -- check to see if the file you attempted to create exists
      if CustomSheet == nil then
        MessageBox("Failed to create initial custom gadget file in public documents")
      end
  end
   
--function to make changes to custom gadget
local result = ChangeSetupSheet(CustomSheet,options)

return true
  end
 
 
 function ChangeSetupSheet(CustomSheet,options)
 --read custom gadget
 local ReadCustom = CustomSheet:read("*all")
 --close custom gadget
 CustomSheet:close()
  --check to see if we have a backup of the setup sheet that now exists in the public gadgets directory if not create one before we start editing
 local backupsheet = io.open(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.backup","r")
    if backupsheet == nil then
      backupsheet = io.output(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.backup","w")
      backupsheet:write(ReadCustom)
      backupsheet:close()
    end
 backupsheet = io.open(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.backup","r")   
 local backupempty = backupsheet:read("*all")
  if backupempty == "" then
    backupsheet = io.output(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.backup","w")
    backupsheet:write(ReadCustom)
  end  
  backupsheet:close()
   
   
 --check to see if this gadget has made changes to this before by looking for
 --one of the new html IDs which get assigned by using this gadget
 local alreadycustom = string.match(ReadCustom,"%-%-%[%[Setup_Sheet_Editor.-%]%]")
    -- if the custom gadget has not been edited before it will go ahead and create the
    --necessary changes to the css and html, else it will just make the change to the
    --new logo id in the css
    if alreadycustom ~= nil then
      --already been edited, just make the new changes
      ReadCustom = ReadCustom:gsub("#newlogo{.-%}",Base64Encode(options))
      ReadCustom = ReadCustom:gsub([[<div id="title">.-</div>]],[[<div id="title">]]..options.Title..[[</div>]])
      ReadCustom = ChangeColour(ReadCustom,options)
      ReadCustom = AddRemoveSections(ReadCustom,options)
      ReadCustom = TimeDateStamp(ReadCustom,options)
    else
      --not been edited before, make css and html changes to the sheet.
      --has to make these changes as original sheet used a solid image for whole of
      --header, so converting it to be made up by pure css now except for new logo which
      --will be converted to base 64
      --------------------------------------------------------------------------------------
      --[[if we find that this is the first time this gadget has been ran but a custom setup sheet already exists, then display warning message]]
      local reverted = string.match(ReadCustom,"%-%-%[%[Reverted.-%]%]")
      if options.Custom == "" and reverted == nil then
        MessageBox("We have found an existing custom job setup sheet in the custom gadgets directory that was not created by this gadget,\n this editor will still attempt to make changes, a backup will have been created on first run of this gadget,\n if you need to revert, please use the reset to default sheet option to restore.")
      end
      local ChangedHTML = {}
      table.insert(ChangedHTML,[[#header{background-color:#5c5c5c;height:72px;width:595px;float:left;}]])
      table.insert(ChangedHTML,[[#logobg{float:right;background-color:#fff;height:62px;width:257px;border-radius:50px 0 0 0;margin-top:10px;text-align:center;box-shadow:0px 0px 6px #fff;}]])
      table.insert(ChangedHTML, Base64Encode(options))
      local found = string.match(ReadCustom,"#header{.-%}")
      if found ~= "" and found ~= nil then
        ReadCustom = ReadCustom:gsub("#header{.-%}", table.concat(ChangedHTML))
      else
        MessageBox("Unable to find header css info in original setup sheet gadget found in the program data folder, This occurs if the header has been previously changed by the user, if this is not the case please contact support")
      end
        --make html changes to encorporate new css header
        ReadCustom = ChangeHTMLHeader(ReadCustom,options)  
        ReadCustom = ChangeColour(ReadCustom,options)
        ReadCustom = AddRemoveSections(ReadCustom,options)
        ReadCustom = TimeDateStamp(ReadCustom,options)
    end
  --after successfully adding all edits now time to save, set output file
  local OutputCustom = io.output(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.lua","w")
	--write changes to file
   OutputCustom:write(ReadCustom)
	--close file
   OutputCustom:close() 
      if options.Custom ~= "" then
        --Warn that the software will need restarting to utilise new gadget
        MessageBox("The software will require a restart before changes will take effect, please save your work.")
      end
   --Gadget End
   return true
end

function TimeDateStamp(ReadCustom,options)
  --[[check to find a previous date time stamp to overwrite, else create one]]
  local os = require "os"
  local stamp = string.match(ReadCustom,"%-%-%[%[Setup_Sheet_Editor.-%]%]")
  if stamp ~= nil then
    ReadCustom = ReadCustom:gsub("%-%-%[%[Setup_Sheet_Editor.-%]%]","--[[Setup_Sheet_Editor Edited "..os.date("%x %X").."]]",1)
  else
    stamp = string.match(ReadCustom,"%-%-%[%[.-%]%]")  
    stamp = stamp.."--[[Setup_Sheet_Editor Edited "..os.date("%x %X").."]]"
    ReadCustom = ReadCustom:gsub("%-%-%[%[.-%]%]",stamp,1)
  end
  return ReadCustom
end  

function ChangeHTMLHeader(ReadCustom,options)
  --build new table to insert into GetHeader() function of setup sheet gadget
  local replace = {}
  table.insert(replace,"function GetHeader(job)")
  table.insert(replace,"local t ={}")
  table.insert(replace,"table.insert(t,[[<div id=\"header\"><div id=\"titlediv\"><div id=\"title\">]])")
  table.insert(replace,"table.insert(t,HTMLEncode(vSTR(\""..options.Title.."\")))")
  table.insert(replace,"table.insert(t,[[</div><br><div id=\"jobtitle\"><b>]])")
  table.insert(replace,"table.insert(t,job.Name)")
  table.insert(replace,"table.insert(t,[[</b></div></div>]])")
  table.insert(replace,"table.insert(t,[[<div id=\"logobg\"><div id=\"newlogo\"></div></div></div>]])")
  table.insert(replace,"local text")
  table.insert(replace,"text = table.concat(t)")
  table.insert(replace,"return text ")
  table.insert(replace,"end")
  --find original function and replace with new header html function
  local found = string.match(ReadCustom,"function GetHeader%(job%).-end")
  if found ~= "" and found ~= nil then
    ReadCustom = ReadCustom:gsub("function GetHeader%(job%).-end",table.concat(replace, '\n'))
  else
    MessageBox("Unable to alter the Getheader function, this may be due to altering the original setup sheet previous to using this gadget, if you believe this to be incorrect, please contact support")
  end
  return ReadCustom
end

function ChangeColour(ReadCustom,options)
--pick out the css for header and edit background colour just for this item
local headercol = string.match(ReadCustom,"#header{.-%}")
headercol = headercol:gsub([[background%-color:.-%;]],[[background-color:#]]..options.Colour..[[;]])
ReadCustom = ReadCustom:gsub("#header{.-%}",headercol) 
--pick out the css for footer and edit background colour just for this item   
local footercol = string.match(ReadCustom,"#footer{.-%}")
footercol = footercol:gsub([[background%-color:.-%;]],[[background-color:#]]..options.Colour..[[;]])
--look for % in css and escape to allow gsub to function
footercol = footercol:gsub([[%%]],[[%%%%]])
ReadCustom = ReadCustom:gsub("#footer{.-%}",footercol) 
--pick out the css for Text and edit background colour just for this item   
local textcol = string.match(ReadCustom,"body{.-%}")
textcol = textcol:gsub([[color:.-%;]],[[color:#]]..options.TextColour..[[;]])
ReadCustom = ReadCustom:gsub("body{.-%}",textcol) 
--pick out the css for Border and edit background colour just for this item   
local Bordercol = string.match(ReadCustom,".boxborder{.-%}")
if Bordercol ~= "" and Bordercol ~= nil then
    Bordercol = Bordercol:gsub([[#%w*]],"#"..options.BorderColour)
    ReadCustom = ReadCustom:gsub(".boxborder{.-%}",Bordercol)  
else
    MessageBox("Unable to alter the border colour information, this is likely due to the setup sheet being altered by the user before using this gadget, if you beleive this to be wrong, please contact support")
end

return ReadCustom
end

function AddRemoveSections(ReadCustom,options)
  --[[build table for loop of sections we can add and remove
      for each section we insert a table with the variable name for the section and
      the option selected by the user, true or false to include section.]]
  local ToRemove = {}
  table.insert(ToRemove,{"svg",options.DrawVectors})
  table.insert(ToRemove,{"notesbox",options.JobNotes})
  table.insert(ToRemove,{"materialbx",options.MaterialSetup})
  table.insert(ToRemove,{"summarytp",options.ToolpathsSummary})
  table.insert(ToRemove,{"toolpathbox",options.ToolpathBreakdown})
  --[[for each entry in the table it will loop over the following for loop and add or remove the section
      dependant on the users choice from the dialog]]
    for i = 1, #ToRemove do 
      --[[set string to look for in setup sheet, as each entry we add to the final set up sheet follows the same method
          we simply look for the where the gadget adds the html to the sheet and comment it out or uncomment it if we
          want to enable that section,we look for the commented out code else we will find the code and never know if it is already
          commented out or not]]
      local HTMLString = string.match(ReadCustom,"%-%-%[%[AddToArray%(HTMLTable%,"..ToRemove[i][1].."%)%]%]")
      --check if this section if true or false to add or remove from final sheet
      if ToRemove[i][2] then
          --if true to add section then next it will check the string we looked for earlier to see if it found the commented out code or not
          if HTMLString ~= nil then
            --[[if already commented out then it will uncomment the string we have already found, then look for original string in setup
                and replace with new string,else it is already active and will do nothing and carry on the loop]]
            HTMLString = HTMLString:gsub("%-*%[*%]*","")
            ReadCustom = ReadCustom:gsub("%-%-%[%[AddToArray%(HTMLTable%,"..ToRemove[i][1].."%)%]%]",HTMLString)            
          else
            HTMLString =  string.match(ReadCustom,"AddToArray%(HTMLTable%,"..ToRemove[i][1].."%)")
              if HTMLString == nil then
                MessageBox("Could not find Source for "..ToRemove[i][1].." in Job Sheet Gadget")
              end
          end
      --if false we want to remove the section we are currently working on do the following    
      else
        --check to see if htmlstring is nil which means the section is not already commented out
        if HTMLString == nil then
          --now check for the uncommented string
          HTMLString =  string.match(ReadCustom,"AddToArray%(HTMLTable%,"..ToRemove[i][1].."%)")
            --check to see if we have found the uncommented string in the gadget
            if HTMLString ~= nil then
              --if we have found the uncommented string, add comments and replace in gadget
              ReadCustom = ReadCustom:gsub("AddToArray%(HTMLTable%,"..ToRemove[i][1].."%)","--[["..HTMLString.."]]")
            else
              -- if we could still not find the section, the presumption is this has been edited outside of vectric
              MessageBox("Could not find Source for "..ToRemove[i][1].." in Job Sheet Gadget")
            end
            
        end
      end
    end    
-- return edited source
return ReadCustom  
end

function FileSize(file)
local current = file:seek()
local size = file:seek("end")
file:seek("set", current)
return size
end

function Base64Encode(options)
local infilename = options.InputFile
local FileType = options.FileType
local Output = {}
table.insert(Output,[[#newlogo{height:52px;width:165px;background-repeat:no-repeat;background-size:auto 52px;background-position: center;margin: 8px auto 0 auto;background-image: url('data:image/]])
table.insert(Output,FileType)
table.insert(Output,[[;base64,]])
local encoding = {
'A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P',
'Q','R','S','T','U','V','W','X','Y','Z','a','b','c','d','e','f',
'g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v',
'w','x','y','z','0','1','2','3','4','5','6','7','8','9','+','/'
}
-- Open the necessary files
local infile = assert(io.open(infilename, "rb"))
-- Work out the size of the input file
local remaining = FileSize(infile)
local buffer = ""

-- While we have bytes remaining encode the file
-- This isn't exactly the most efficient implementation 
while remaining > 0 do
   -- Always have at least one more byte
   local b1 = string.byte(infile:read(1), 1)
   local b2 = remaining < 2 and 0 or string.byte(infile:read(1), 1)
   local b3 = remaining < 3 and 0 or string.byte(infile:read(1), 1)
   local value = b3 + 256 * b2 + 256 * 256 * b1
   -- Unpack and lookup the encodings
   local c1 = encoding[1 + bit32.extract(value, 18, 6)]
   local c2 = encoding[1 + bit32.extract(value, 12, 6)]
   local c3 = remaining < 2 and "=" or encoding[1 + bit32.extract(value,  6, 6)]
   local c4 = remaining < 3 and "=" or encoding[1 + bit32.extract(value,  0, 6)]
   -- Append the result to the buffer and flush a line if necessary
   buffer = buffer .. c1 .. c2 .. c3 .. c4
   if buffer:len() >= 64 then
       table.insert(Output,buffer)
	   buffer = ""
   end
   -- Decrement the number of remaining bytes
   remaining = remaining - 3
end

-- Write any unflushed output
if buffer:len() > 0 then
   table.insert(Output,buffer)
end

infile:close()
table.insert(Output,[[');}]])
local newlogo = table.concat(Output)

return newlogo
end

--[[  -------------- DisplayDialog --------------------------------------------------  
|
|  Display the dialog
|
]]
function DisplayDialog(path, options)
local html_path = "file:" ..path .. "\\" .. g_html_file
local dialog = HTML_Dialog(false,html_path,options.windowWidth,options.windowHeight,"Editor")
--Add preset values
dialog:AddTextField("InputFile",options.InputFile)
dialog:AddTextField("Colour",options.Colour)
dialog:AddTextField("Title",options.Title)
dialog:AddTextField("TextColour",options.TextColour)
dialog:AddTextField("BorderColour",options.BorderColour)
dialog:AddCheckBox("DrawVectors", options.DrawVectors)
dialog:AddCheckBox("JobNotes", options.JobNotes)
dialog:AddCheckBox("MaterialSetup", options.MaterialSetup)
dialog:AddCheckBox("ToolpathsSummary", options.ToolpathsSummary)
dialog:AddCheckBox("ToolpathBreakdown", options.ToolpathBreakdown)
dialog:AddCheckBox("ReturnDefault", options.ReturnDefault)
--Set Gadget Path before html dialog is displayed for the static restore button
options.GadgetPath = GetUserGadgetsLocation().."\\"
-- Display the dialog
      local success = dialog:ShowDialog()

      if not success then 
        return false;
      end
  --load options from dialog
options.DrawVectors = dialog:GetCheckBox("DrawVectors")
options.JobNotes = dialog:GetCheckBox("JobNotes")
options.MaterialSetup = dialog:GetCheckBox("MaterialSetup")
options.ToolpathsSummary = dialog:GetCheckBox("ToolpathsSummary")
options.ToolpathBreakdown = dialog:GetCheckBox("ToolpathBreakdown")
options.InputFile = dialog:GetTextField("InputFile")
options.Colour = dialog:GetTextField("Colour")
options.Title = dialog:GetTextField("Title")
options.TextColour = dialog:GetTextField("TextColour")
options.BorderColour = dialog:GetTextField("BorderColour")
options.ReturnDefault = dialog:GetCheckBox("ReturnDefault")
options.windowWidth  = dialog.WindowWidth
options.windowHeight = dialog.WindowHeight
--save options selected for future use
SaveDefaults(options)


 --check to see if user wishes to return to default sheet 
--[[while options.ReturnDefault do
  local success = ReturnToDefault(options)
  if success then
    return false
  else
    MessageBox("Could not find back up to return to default sheet, which would have been created on first run of this gadget, please uncheck return to default option and try again.")
    Display()
  end
end]]
  --if no file was selected on change logo option show warning and reopen the html dialog
  while options.InputFile == "" do
    MessageBox("No image selected, please select an image and try again, re opening HTML Dialog")
    return -1
  end
  
  --determine the Extension of the image type that has been selected by looking for the last dot and letters in path
local extension = string.match(options.InputFile,"%.%a-$")
--Only support Jpg Png or Gif
  while extension ~= ".jpg" and extension ~= ".png" and extension ~=".gif" do
    MessageBox("incompatible image selected, please choose either a .jpg , .png or a .gif and try again")
    extension = string.match(options.InputFile,"%.%a-$")
    return -1
  end
--remove dot from extension for use in base64 string
options.FileType = extension:gsub("%.","")

return true
end

--[[function OnLuaButton_Cancel(dialog)
  HTML_Dialog:ShowDialog(0)
return true  
end]]


function OnLuaButton_ReturnDefault(dialog)
  --[[function to return the setup sheet to either the first sheet we created from the default software or the users custom gadget from first run,
  if none found we state no backups were found and return false which will reopen the dialog]]
  local backup = io.open(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.backup","r")
    if backup == nil or backup == "" then
      MessageBox("No Backup Found")
      return false
    end
  local restore = io.output(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.lua","w") 
  local readbackup = backup:read("*all")
  local stamp = string.match(readbackup,"%-%-%[%[Reverted.-%]%]")
    if stamp ~= nil and stamp ~= "" then
      readbackup = readbackup:gsub("%-%-%[%[Reverted.-%]%]","--[[Reverted "..os.date("%x %X").."]]",1)
    else
      stamp = string.match(readbackup,"%-%-%[%[.-%]%]")
      if stamp ~= "" and stamp ~= nil then
          stamp = stamp.."--[[Reverted "..os.date("%x %X").."]]"
          readbackup = readbackup:gsub("%-%-%[%[.-%]%]",stamp,1)
      end
    end
  restore:write(readbackup)
  restore:close()
  backup:close()
  backup = io.output(options.GadgetPath.."__Setup_Sheet\\Setup_Sheet.backup","w")
  backup:write("")
  backup:close()
  readbackup = nil
  MessageBox("Restore Complete")
return true
end

--[[  -------------- LoadDefaults --------------------------------------------------  
|
|  Load defaults from the registry
|
]]    
function LoadDefaults(options)
local registry = Registry("SetupSheetEditor")
options.windowWidth = registry:GetInt("WindowWidth",  g_width)
options.windowHeight = registry:GetInt("WindowHeight", g_height)
options.Colour = registry:GetString("Colour",  options.Colour)
options.TextColour = registry:GetString("TextColour",  options.TextColour)
options.BorderColour = registry:GetString("BorderColour",  options.BorderColour)
options.Title = registry:GetString("Title",  options.Title)
options.DrawVectors = registry:GetBool("DrawVectors",  options.DrawVectors)
options.JobNotes = registry:GetBool("JobNotes",  options.JobNotes)
options.MaterialSetup = registry:GetBool("MaterialSetup",  options.MaterialSetup)
options.ToolpathsSummary = registry:GetBool("ToolpathsSummary",  options.ToolpathsSummary)
options.ToolpathBreakdown = registry:GetBool("ToolpathBreakdown",  options.ToolpathBreakdown)
options.InputFile = registry:GetString("InputFile",options.InputFile)
end

--[[  -------------- SaveDefaults --------------------------------------------------  
|
| Save defaults to registry
|
]]
function SaveDefaults(options)
local registry = Registry("SetupSheetEditor")
registry:SetInt("WindowWidth",options.windowWidth)
registry:SetInt("WindowHeight",options.windowHeight)  
registry:SetString("Colour",options.Colour) 
registry:SetString("InputFile",options.InputFile)
registry:SetString("TextColour",options.TextColour) 
registry:SetString("BorderColour",options.BorderColour) 
registry:SetString("Title",options.Title) 
registry:SetBool("DrawVectors",options.DrawVectors)
registry:SetBool("JobNotes",options.JobNotes)
registry:SetBool("MaterialSetup",options.MaterialSetup)
registry:SetBool("ToolpathsSummary",options.ToolpathsSummary)
registry:SetBool("ToolpathBreakdown",options.ToolpathBreakdown)
end