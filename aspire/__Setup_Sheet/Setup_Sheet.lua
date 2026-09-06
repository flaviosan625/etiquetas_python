-- VECTRIC LUA SCRIPT


--[[ =============================================================
|
| Create an HTML file with details of job and toolpaths used
| SeanM  09/03/2015 V1.1 Added Job notes, toolpath notes and toolnotes and footer with version number.
| SeanM  15/03/2015 V1.2 Updated to output tool names, changed toolpath layout, added bold headings
| BrianM 15/03/2015 V1.3 Addes support for use in trial builds when compiled
| SeanM  17/03/2015 V1.4 Removed Diameter spec from tool info, added in XY Offset 
| Sean M 16/04/2015 V1.5 If Z Zero = bootom of the block, deducted material thickness from Z1 to give reading from above material as depicted by the icon 
| ===============================================================
]]


--require("mobdebug").start()
require "strict"
svgpath = ""

vStrCount = 0

gBoundaryVectorLayerName = "xxSetupSheetBoundary"

gJobSetUpV = "Job Setup Sheet v1.5"

g_VectricGadgetSignature = "FF44DDEE668844338800111144DD44BBCCEEFF99EEAA2211225500BB44CCFF99AA9999AABBBBFFBBAAEEEEEE4466BBBB9977BBEE4422DDDD22EEBBCCCCAA9988"

--[[we suffered memory leak from vSTR so overide here ...]]
function vSTR(test_str)
   -- if vStrCount == 0 then
   --   MessageBox("Called local vStr with :" .. test_str)
   -- end
   -- vStrCount = vStrCount + 1
   return test_str
end

-- ConvertToUTF8 was only added with Version 8.009 so check correct version
function ConvertStringToUTF8(str)
   if GetBuildVersion() >= 8.009 then
      return ConvertToUTF8(str)
   end
   
   return str;
end


function main() 
  return true
end

--[[function to be called from main]]
function GenerateSetupSheet(path)

   -- to work with Trial versions we need following call (only supported from V8.012 onwards)
   if GetAppVersion() >= 8.012 then
      AllowDemoFileWrite()
   end

	--Set Job Variables
   local job = VectricJob()
   local matblock = MaterialBlock()
   local tpmanager = ToolpathManager()
   local layermanager = job.LayerManager
   local sheets = layermanager.NumberOfSheets
   local pathext
	-- check to ensure toolpaths exist if not will error message and escape
   if tpmanager.Count < 1 then
      MessageBox("No toolpaths have been created, cannot create job setup sheet without toolpaths")
      return false
   end  
	-- end of toolpath exists check
	--------------------------------------------------------------------
	-- Get toolpath and summary information to use in job sheet
	--end of 
   local summary,toolpaths = GetSummaryDetails(job,tpmanager)
	-- summary and toolpaths are tables with information about the job
	--------------------------------------------------------------------
	--[[below checks for more than sheet, if there is more than one sheet
		it amends a variable pathext which will be appended to the resulting
		jobs sheets filename, so that every sheet has a unique and related name.
		This is also one large for loop, for every sheet it will then run through 
		and collect all the data and put together a job setup sheet for each until it
		completes]]
   for s = 0, sheets-1 do
      if sheets > 1 then
         pathext = "_Sheet_"..s
      else
         pathext = ""
      end
	-- end of sheet check
	----------------------------------------------------------------------
	--[[After checking for the number of sheets in the job we next want
		to check to see if any of the toolpaths relate to the sheets on the job
		this is essential as we only want to print out or create setup sheets for
		sheets on the job that have toolpaths, else we would be left with blank setup sheets,
		this does have an issue for those that use one set of toolpaths for all sheets,
		as these toolpaths do not have sheet attachment]]
      layermanager.ActiveSheetIndex = s
      local tponsheet = false
      local tponsheetnum = 0
      for t = 1, #toolpaths do
         if toolpaths[t].tpsheet == s then
            tponsheet = true
            tponsheetnum = tponsheetnum +1
         end 
      end
		--End of toolpath on sheet check
		--------------------------------------------------------------------------
		--[[If there are toolpaths on this sheet, it will then go ahead and start building the 
			job sheet from the summary and toolpath tables and static html which is returned from 
			the AddStaticHTML function. If no toolpaths exist on this sheet, this sheet will be ignored
			and go back to the sheets for loop]]
      if tponsheet then  
			--[[HTMLTable is the table which collects the results from each section of the job sheet
				and will concatenate at the end of this process]]
         local HTMLTable
			-- fetch css from the static html
         local css = AddStaticHTML("css",sheets,s,job)
			--add css to htmltable
         HTMLTable = AddToArray(HTMLTable,css)
			--get the setup sheet header info
         local header = GetHeader(job)
			-- add header to html table
         AddToArray(HTMLTable,header)
			--[[fetch 2dvectors on current sheet and create an svg to represent what is being cut, not all vectors
				on that sheet may be for the actual toolpaths, there is no current way of determining this]]
         local svg = GetJobVectorsSVG(job,path,s,sheets)
			-- add svg to htmltable
         AddToArray(HTMLTable,svg)
			-- fetch job notes and create own section if they exist
			local notesbox = GetNotesBox(job)
			--add notes to the htmltable, if there was no notes, notesbox will be empty
			AddToArray(HTMLTable,notesbox)
			-- fetch material setup details html section, pass in summary table
         local materialbx = GetMaterialBox(summary)
			--add material html to html table
         AddToArray(HTMLTable,materialbx)
			--fetch toolpath summary details for current sheet
         local summarytp = GetSummaryBox(toolpaths,summary,s,tponsheetnum)
			-- add summary html to html table
         AddToArray(HTMLTable,summarytp)
			--[[fetch toolpaths relating to sheets, for every toolpath on the sheet it will return html
				to add to the final html table]]
         local tpboxhtml = {}
         for i = 1, #toolpaths do
            if toolpaths[i].tpsheet == s then
					table.insert(tpboxhtml,GetToolPathBox(toolpaths[i],summary,s))
            end
         end
		-- concatenate all toolpath sections from table to toolpathbox variable
		local toolpathbox = table.concat(tpboxhtml)
		-- add toolpath html to htmltable
      AddToArray(HTMLTable,toolpathbox)
		--add footer to the html with version info
		local footerbox = AddStaticHTML("footer",sheets,s,job)
			--add footer to the htmltable,
			AddToArray(HTMLTable,footerbox)
		--function to save out the html to a single jobsheet file, if more than one sheet pathext will be appended to file name
      OutputHtml(HTMLTable,path,pathext)
      end
   end
	--final step of the process is to refresh the 2dview and return true
   job:Refresh2DView()
   return true
end
 

--[[function to add contours to job whether layer created or not]]
function AddContoursToJob(contour,layername,job)
   local layer
   local object = CreateCadContour(contour)
   if type(layername) == "string" then
      layer = job.LayerManager:GetLayerWithName(layername)
   else
      layer = layername
   end
   if layer:AddObject(object,true) then
      return object
   end 
end
  
--[[creates job boundary vector for the SVG file that is created to represent the toolpaths being cut]]
function CreateJobBoundary(job)
  local matblock = MaterialBlock()
  local bounds = job:GetBounds()
  local y = Vector2D(0,1)
  local x = Vector2D(1,0)
  local BLC = bounds.BLC  
  local TLC = BLC + matblock.Height * y
  local TRC= TLC + matblock.Width * x
  local BRC = TRC + matblock.Height * -y
  local boundary = Contour(0.0)
  boundary:AppendPoint(BLC)
  boundary:LineTo(TLC)
  boundary:LineTo(TRC)
  boundary:LineTo(BRC)
  boundary:LineTo(BLC)
  AddContoursToJob(boundary, gBoundaryVectorLayerName ,job)
 
end
 

--[[builds a selection list of all vectors,creates a new boundary vector,
 uses these to create an svg file, loads the svg file back into the job,
manipulates the svg code and stores in a var, removes everything in selection
 and also removes boundary layer, put svg into own html block and return to main function]] 

function GetJobVectorsSVG(job,path,activenum,sheets)
	--create job boundary vector to add to selection of vectors on sheet
   CreateJobBoundary(job)
	-- if sheets are being used then it will add the number of the sheet the title of the job layout section
   local sheetstr
   if sheets > 1 then
      sheetstr = " Sheet "..activenum
   else
      sheetstr = ""
   end   
	--end of checking for number of sheets
	--create table to hold html
	local t = {}
   table.insert(t,[[<div class="boxborder"><div class="boxtitle">Job Layout]])
	table.insert(t,sheetstr)
	table.insert(t,[[</div><div class="boxicon layout"></div><div class="boxcontainer"><div id="vectorcenter"><p><b>Material Border</b></p>]])
	-- build selection of vectors from sheet to create SVG from
   local selection = job.Selection
   local layerm = job.LayerManager 
   local layer 
   local pos = layerm:GetHeadPosition()
   while (pos ~= nil) do 
      layer,pos = layerm:GetNext(pos)
      local object 
      local posi = layer:GetHeadPosition()
      while (posi ~= nil)do
         object,posi = layer:GetNext(posi)
         if object.ClassName == "vcCadContour" or object.ClassName ==  "vcCadObjectGroup" or object.ClassName == "vcCadPolyline" then
            if object.SheetIndex == activenum then
               selection:Add(object,true,true)
            else
               -- MessageBox(tostring(object.SheetIndex))
            end
         end
      end
   end  
   --end of building selection-----------------------------------------
	--[[exchange the path extension from html to .svg as we will be creating an
		svg file from the selection vectors and then reading it back and and editing the
		svg string]]
   svgpath = path:gsub([[.html]],[[.svg]])
	--export selection to svg file
   if not job:ExportSelectionToSvg(svgpath) then
      MessageBox(HTMLEncode(vSTR("Failed to create image representing job Vectors")))
      return false
   end
	-- end of svg export-------------------------------------------------------
	--open svg file for editing--
   local file = io.open(svgpath, "r")
	--seek to 93rd position and read all,removes the xml encoding 
   file:seek("cur",93)
   local svg = file:read("*a")
   file:close()
	--close svg file
	--search for width attributes in svg and replace with fixed width for setup sheet
   svg = svg:gsub([[width="(.-)"]],[[width="8cm"]])
	--search for height attributes in svg and replace with fixed height for setup sheet
   svg = svg:gsub([[height="(.-)"]],[[height="4cm"]])
	--[[search for stroke width, depending whether your job is in inches or mm it will vary
		so will check for either and apply custom stroke width]]
   local found = string.match(svg,"stroke%-width:%d-%.?%d-;")
   if found == [[stroke-width:0.280000;]] then
      svg = svg:gsub("stroke%-width:%d-%.?%d-;","stroke-width:1;")
   elseif found == [[stroke-width:0.010000;]] then
      svg = svg:gsub("stroke%-width:%d-%.?%d-;","stroke-width:0.03;")
   else
   end
	--set colour of vectors on svg to black or they may be the colour you set on the job
   svg = svg:gsub("stroke:#%a-%d-;","stroke:#000000")
   if svg == nil then
      MessageBox(HTMLEncode(vSTR("SVG was not created successfully, no image representing the vectors could be established")))
      return false  
   end

   --[[tidy up, remove everything from selection and delete added layer]]
   local item
   local position = selection:GetHeadPosition()
   while (position ~= nil) do 
      item,position = selection:GetNext(position)
      selection:Remove(item,true)
   end
   selection:GroupSelectionFinished()   
   local lfs = require "os"
   local deletelayer =  layerm:GetLayerWithName(gBoundaryVectorLayerName)
   layerm:RemoveLayer(layer)
   lfs.remove(svgpath) 
    --[[ end of tidy up]]
	-- add html together and add closing divs and then return html
	table.insert(t,svg)
	table.insert(t,[[</div></div></div>]])
   local svghtml = table.concat(t)
	--return html
   return svghtml
end

 
--[[ retrieve header html which starts after the <body> tag]]
function GetHeader(job)
	local t ={}
	table.insert(t,[[<div id="header"><div id="titlediv"><div id="title">]])
	table.insert(t,HTMLEncode(vSTR("Job Setup Sheet")))
	table.insert(t,[[</div><br><div id="jobtitle"><b>]])
	table.insert(t,job.Name)
	table.insert(t,[[</b></div></div></div>]])
	local text
	text = table.concat(t)
   return text  
end
 
--[[retrieve html info for toolpath that has been passed]]
function GetToolPathBox(toolpaths,summary)
	--[[check to see if tool is a vbit to, if so it will add the angle of vbit,if this is not checked a default angle of 90 will show]]
   if toolpaths.tptool ~= "V-Bit" then
      toolpaths.tpvangle = ""
   end
	--create table of html for toolpath info
   local t = {}   
   table.insert(t, [[<div class="boxborder"><div class="boxtitle">]])
   table.insert(t, HTMLEncode(vSTR("Toolpath")))
   table.insert(t, [[: ]])
   table.insert(t,ConvertStringToUTF8(toolpaths.tpname))
   table.insert(t, [[</div><div class="boxicon ]])
   table.insert(t, toolpaths.tptype)
   --start of toolpath info row
   table.insert(t, [["></div><div class="boxcontainer"><div class="box33 textleft"><div class="level"><b>]])
   table.insert(t, HTMLEncode(vSTR("Toolpath Info")))
   table.insert(t, [[</b></div></div><div class="box33 textcenter"><div class="level"> </div></div><div class="box33 textright"><div class="level"><b>]])
   table.insert(t, HTMLEncode(vSTR("Time Estimate")))
   table.insert(t, [[: </b>]]) 
   table.insert(t, toolpaths.tptime)
   table.insert(t, [[</div></div>]] )   
   table.insert(t, [[<div class="fullwidth FL">]])
   table.insert(t, HTMLEncode(vSTR("Toolpath")))
   table.insert(t,[[ ]])
   table.insert(t, HTMLEncode(vSTR("Type")))
   table.insert(t, [[: ]])
   table.insert(t, HTMLEncode(vSTR(toolpaths.tptypename)))
   table.insert(t,[[</div><div class="box33 textleft"><div class="level">]])
   table.insert(t, HTMLEncode(vSTR("Feed Rate")))
   table.insert(t, [[: ]])
   table.insert(t, toolpaths.tpfeed)
   table.insert(t, [[ ]])
   table.insert(t, toolpaths.tpfeedunit)
   table.insert(t, [[</div></div><div class="box33 textcenter"><div class="level">]])
   table.insert(t, HTMLEncode(vSTR("Plunge Rate")))
   table.insert(t, [[: ]])
   table.insert(t, toolpaths.tpplunge)
   table.insert(t, [[ ]])
   table.insert(t, toolpaths.tpfeedunit)
   table.insert(t, [[</div></div><div class="box33 textright"><div class="level">]])
   table.insert(t, vSTR("Spindle Speed"))
   table.insert(t, [[: ]])
   table.insert(t, toolpaths.tpspindle)
   table.insert(t, [[</div></div>]])
   --check if we have any toolpath notes to add
   if toolpaths.tpnotes ~= "" then
      table.insert(t,[[<div class="fullwidth FL"><b>Toolpath Notes:</b><br/>]])
      table.insert(t,toolpaths.tpnotes)
      table.insert(t,[[</div>]])
	end
  --end of toolpath notes check
   --End of toolpath info row
   --start of tool info
   table.insert(t, [[<div class="fullwidth FL"><b>]])
   table.insert(t, HTMLEncode(vSTR("Tool Info")))
   table.insert(t, [[</b></div><div class="fullwidth FL">]])
   table.insert(t, HTMLEncode(vSTR("Tool Name")))
   table.insert(t, [[: ]])
   table.insert(t, toolpaths.tptoolname)
   table.insert(t, [[</div><div class="box33 textleft"><div class="level">]])
   table.insert(t, HTMLEncode(vSTR("Tool Type")))
   table.insert(t, [[: ]])
   table.insert(t, toolpaths.tptool)
   table.insert(t, [[</div></div><div class="box33 textcenter"><div class="level">]])
   table.insert(t,[[ ]])
   table.insert(t, [[</div></div><div class="box33 textright"><div class="level">]])
   table.insert(t, HTMLEncode(vSTR("Tool Number")))
   table.insert(t, [[: ]])
   table.insert(t, toolpaths.tptoolnum )
   table.insert(t, [[</div></div>]])
   --check for tool notes
   if toolpaths.tptoolnotes ~= "" then
      table.insert(t,[[<div class="fullwidth FL"><b>Tool Notes:</b><br/>]])
      table.insert(t,toolpaths.tptoolnotes)
      table.insert(t,[[</div>]])
	end
   -- end of check for tool notes
   --end of tool info
	--finally close the two opening divs
		table.insert(t,[[</div></div>]])
	--concatenate html and return
   local text = table.concat(t)

   return text
 end
 
 --[[ retrieve notes added to the job if they exist ]]

function GetNotesBox(job) 
	--set jobnotes with job notes string
	local jobnotes = job.JobParameters:GetString("notes","")
	local text
	--check to see if job notes contains any notes, if so create job notes section
	if jobnotes ~= "" then
		local t = {}
		table.insert(t,AddStaticHTML("jobnotes"))
		table.insert(t, [[<div class="fullwidth"><p>]])
		table.insert(t,jobnotes)
		table.insert(t, [[</p></div></div></div>]])
		text = table.concat(t)
		return text
		--if empty return an empty string
	else
		text = ""
		return text
	end
end
 
 --[[retrieve html for summary box]]
function GetSummaryBox(toolpaths,summary,activenum,tpnum)
	--create table for html 
	local t = {}
   table.insert(t,AddStaticHTML("summarybox"))
	table.insert(t,[[<div class="box33 textleft"><div class="level"><b>]])
	table.insert(t, HTMLEncode(vSTR("Toolpaths")))
	table.insert(t, [[ : </b>]])
	table.insert(t, tpnum)
	table.insert(t, [[</div>]])
   for i = 1, #toolpaths do
      if toolpaths[i].tpsheet == activenum then
         table.insert(t, [[<div class="level">]])
			table.insert(t,ConvertStringToUTF8(toolpaths[i].tpname))
			table.insert(t,[[</div>]])
      end
   end
	table.insert(t,[[</div><div class="box33 textcenter"><div class="level"><b>]])
	table.insert(t,HTMLEncode(vSTR("Tool Name")))
	table.insert(t,[[: </b></div>]])
	-- check toolpaths on sheet and if the tool on the toolpath is a vbit tool
   for i = 1 , #toolpaths do
      if toolpaths[i].tpsheet == activenum then
         if toolpaths[i].tptool ~= HTMLEncode(vSTR("V-Bit")) then
            toolpaths[i].tpvangle = ""
         end
		table.insert(t,[[<div class="level">]])
		table.insert(t,toolpaths[i].tptoolname)
		table.insert(t,[[</div>]])
      end
   end
	--get the time predicted to run and then format time
   local temp = ""
   local totaltime = 0

   for i = 1,#toolpaths do
      if toolpaths[i].tpsheet == activenum then
         temp = temp ..[[<div class="level">]]..toolpaths[i].tptime..[[</div>]]
         totaltime = totaltime + toolpaths[i].tptimeraw
      end
   end
   
   totaltime = SecondsToClock(totaltime)
   table.insert(t,[[</div><div class="box33 textright"><div class="level"><b>]])
	table.insert(t,HTMLEncode(vSTR("Time Estimate")))
	table.insert(t,[[ : </b>]])
	table.insert(t,totaltime)
	table.insert(t,[[</div>]])
	table.insert(t,temp)
	table.insert(t,[[</div></div></div>]])
	--concatenate table and return string
	local text = table.concat(t)
   return text
end
  
  
--function to encode strings returned from translating vSTR
function HTMLEncode(original_string)
   local result = ""
   local length = original_string:len()
   for i = 1, length do
      local byte = original_string:byte(i, i)
      local encoded = nil
      -- Special cases
      if byte == 0x22 then
         encoded = "&quot;" -- "
      elseif byte == 0x26 then
         encoded =  "&amp;" -- &
      elseif byte == 0x3C then
         encoded = "&lt;" -- <
      elseif byte == 0x3E then
         encoded =  "&gt;" -- >
      elseif byte >= 128 then
         encoded = "&#" .. tostring(byte) .. ";"
      else
         encoded = string.char(byte)
      end
   result = result .. encoded
   end
   return result 
end
  
  
--[[retrieve html for material setup box]]
function GetMaterialBox(summary)
	local t= {}
   table.insert(t,AddStaticHTML("material"))
	table.insert(t,[[<div class="fullwidth"><p><b>]])
	table.insert(t,HTMLEncode(vSTR("Material Block")))
	table.insert(t,[[:</b></p><p class="indent">]])
	table.insert(t,HTMLEncode(vSTR("Height")))
	table.insert(t,[[(Y):]])
	table.insert(t,summary.Height)
	table.insert(t,summary.units)
	table.insert(t,[[ ]])
	table.insert(t,HTMLEncode(vSTR("Width")))
	table.insert(t,[[(X):]])
	table.insert(t,summary.Width)
	table.insert(t,summary.units)
	table.insert(t,[[ ]])
	table.insert(t,HTMLEncode(vSTR("Depth")))
	table.insert(t,[[(Z):]])
	table.insert(t,summary.Thickness)
	table.insert(t,summary.units)
	table.insert(t,[[</p></div>]])
	table.insert(t,[[<div class="fullwidth"><p><b>]])
	table.insert(t,HTMLEncode(vSTR("Home / Start Position")))
	table.insert(t,[[:</b></p><p class="indent">X:]])
	table.insert(t,summary.HomeX)
	table.insert(t,summary.units)
	table.insert(t,[[ Y:]])
	table.insert(t,summary.HomeY)
	table.insert(t,summary.units)
	table.insert(t,[[ Z:]])
	table.insert(t,summary.HomeZ)
	table.insert(t,summary.units)
	table.insert(t,[[</p></div>]])
  -- check for offset, if so insert
  if summary.OffsetX ~= summary.HomeX or summary.OffsetY ~= summary.HomeY then
      table.insert(t, [[<div class="fullwidth"><p><b>]])
      table.insert(t,HTMLEncode(vSTR("Offset Position")))
      table.insert(t,[[: </b></p><p class="indent">X:]])
      table.insert(t, summary.OffsetX)
      table.insert(t,summary.units)
      table.insert(t,[[ Y:]])
      table.insert(t, summary.OffsetY)
      table.insert(t,summary.units)
      table.insert(t,[[</p></div>]])
  end     
  table.insert(t, [[<div class="box33 textleft"><b>]])
	table.insert(t,HTMLEncode(vSTR("Datum Position")))
	table.insert(t,[[:</b><br>Z-]])
	table.insert(t,HTMLEncode(vSTR("Zero")))
	table.insert(t,[[:]])
	table.insert(t,summary.ZOrigin)
	table.insert(t,[[<div class="boxpic"><div class="]])
	table.insert(t,summary.zclass)
	table.insert(t,[[ FL"></div></div></div><div class="box33 textcenter"><br>XY: ]])
	table.insert(t,summary.XYOrigin)
	table.insert(t,[[<br><div class="boxpic"><div class="]])
	table.insert(t,summary.xyclass)
	table.insert(t,[[ FL"></div></div></div><div class="box33 textright"><br>]])
	table.insert(t,HTMLEncode(vSTR("Clearance")))
	table.insert(t,[[ Z1: ]])
	table.insert(t,summary.Z1)
	table.insert(t,summary.units)
	table.insert(t,[[<br><div class="boxpic"><div class="rapid"></div></div></div></div></div>]])
	local text = table.concat(t)
   return text
end
  

--[[converts parameter string to readable string for the toolpath type]]
function GetToolPathType(toolpath)
   local tptype
   local tptypename
   local ctype = toolpath:GetString("EditingDialog","error")  
   --[[PROFILE DATA]]
   if ctype == "uiProfileMachineForm" then
      tptype = "Profile"
      tptypename = "2D Profile Toolpath"
   --[[POCKET DATA]]
   elseif ctype == "uiPocketMachineForm" then
      tptype = "Pocket"
      tptypename = "Pocket Toolpath" 
   --[[DRILL DATA]]
   elseif ctype == "uiDrillForm" then
      tptype = "Drilling"
      tptypename = "Drilling Toolpath"
   --[[ENGRAVING DATA]]
   elseif ctype == "uiQuickEngraveDialog" then
      tptype = "Engrave"
      tptypename = "Quick Engrave"
   --[[VCARVE DATA]]
   elseif ctype == "VCarveFlatToolpathDialog" then
      tptype = "VCarve"
      tptypename = "V-Carve / Engraving Toolpath"
   --[[FLUTING DATA]]
   elseif ctype == "uiFlutingForm" then
      tptype = "Fluting"   
      tptypename = "Fluting Toolpath"
   --[[TEXTURE DATA]]   
   elseif ctype == "TextureForm" then
      tptype = "Texture"
      tptypename = "Texture Toolpath"
   --[[PRISM DATA]]
   elseif ctype == "uiBevelCarveForm" then
      tptype = "Prism"
      tptypename = "Prism Carving Toolpath"
   --[[ROUGHING DATA]]
   elseif ctype == "uiRoughMachineForm" then
      tptype = "Roughing"
      tptypename = "Rough Machining Toolpath"
   --[[FINISHING DATA]]
   elseif ctype == "uiFinishMachineForm" then
      tptype = "Finishing"
      tptypename = "Finish Machining Toolpath"
   --[[IMPORTED DATA]]
   elseif ctype == "uiImportedToolpathForm" then
     tptype = "Custom"
     tptypename = "Imported Toolpath" 
   --[[TOOLPATH MERGE DATA]]
   elseif ctype == "uiToolpathMergeForm" then
     tptype = "Merged"
     tptypename = "Create Merged Toolpath"
   end
   
   return tptype,tptypename
end

--rounds numbers to sensible amount of decimal places for job sheet purposes  
function Format(num)    
  local mult = 10^(4 or 0)
  return math.floor(num * mult + 0.5) / mult
end
   

--[[retrieves toolpath and job settings and stores in two tables, one for summary details and the other toolpath details]]
function GetSummaryDetails(job,tpmanager)
   local matblock = MaterialBlock()
   local   summary = {} 
   summary.tpcount = tpmanager.Count 
   summary.isaspire = job.IsAspire
   summary.inMM = matblock.InMM
   if summary.inMM then
      summary.units = "mm" 
   else
      summary.units = [["]]
   end
   summary.Thickness = Format(matblock.Thickness)
   summary.Height = Format(matblock.Height)
   summary.Width = Format(matblock.Width)
   summary.OffsetX = Format(matblock.ActualXYOrigin.X)
   summary.OffsetY = Format(matblock.ActualXYOrigin.Y)
   summary.XYOrigin = matblock.XYOrigin
   if summary.XYOrigin == 0 then
      summary.XYOrigin = HTMLEncode(vSTR("Bottom Left Corner"))
      summary.xyclass = "xybl"
   elseif summary.XYOrigin == 1 then
      summary.XYOrigin = HTMLEncode(vSTR("Bottom Right Corner"))
      summary.xyclass = "xybr"
   elseif summary.XYOrigin == 2 then
      summary.XYOrigin = HTMLEncode(vSTR("Top Right Corner"))
      summary.xyclass = "xytr"
   elseif summary.XYOrigin == 3 then
      summary.XYOrigin = HTMLEncode(vSTR("Top Left Corner"))
      summary.xyclass = "xytl"
   elseif summary.XYOrigin == 4 then
      summary.XYOrigin = HTMLEncode(vSTR("Center"))
      summary.xyclass = "xycenter"
   end
   summary.ZOrigin = matblock.ZOrigin
   if summary.ZOrigin == 0 then
      summary.ZOrigin = HTMLEncode(vSTR("Top of Material"))
      summary.zclass = "zztop"
   elseif summary.ZOrigin == 1 then
      summary.ZOrigin = HTMLEncode(vSTR("Center of Material"))
      summary.zclass = "zzcenter"
   elseif summary.ZOrigin == 2 then
      summary.ZOrigin = HTMLEncode(vSTR("Bottom of Material"))
      summary.zclass = "zzbot"
   end
    
   local pos = tpmanager:GetHeadPosition()
   local posdata = ToolpathPosData()
   local TPTable={}  
   local toolpath
   while pos ~= nil do
      toolpath, pos = tpmanager:GetNext(pos)
      if #TPTable < 1 then
         local posdata = ToolpathPosData()
         summary.HomeX = Format(posdata.HomeX)
         summary.HomeY = Format(posdata.HomeY)
         summary.HomeZ = Format(posdata.HomeZ)
         local SafeZ = posdata.SafeZ
            if summary.ZOrigin == HTMLEncode(vSTR("Bottom of Material")) then
                SafeZ = SafeZ - summary.Thickness
            end
         summary.Z1 = Format(SafeZ)
         summary.Z2 = Format(posdata.StartZGap)
      end   
      local tpname = toolpath.Name
      local tptype, tptypename = GetToolPathType(toolpath)
      local tptool = toolpath.Tool.ToolTypeText
      local tptoolname = toolpath.Tool.Name
		local tptoolnotes = toolpath.Tool.Notes
      local tptimeraw = toolpath:MachiningTime(false)
      local tptoolnum = toolpath.Tool.ToolNumber
      local tptoolstep = toolpath.Tool.Stepover
      local tptoolpass = toolpath.Tool.Stepdown
      local tptooldia = Format(toolpath.Tool.ToolDia)
      local tpsheet = toolpath.ActiveSheetIndex
      local tptoolinmm = toolpath.Tool.InMM
      if tptoolinmm then
         tptoolinmm = "mm" 
      else
         tptoolinmm = [["]]
      end
      local tpvangle = toolpath.Tool.VBit_Angle..[[°]]
      local tptoolrad = toolpath.Tool:TipRadius(summary.inMM)
      local tpfeed = toolpath.Tool.FeedRate
      local tpfeedunit = toolpath.Tool.RateUnitsText
      local tpplunge = toolpath.Tool.PlungeRate
      local tpspindle = toolpath.Tool.SpindleSpeed
      local tptime = SecondsToClock(tptimeraw)
		local tpnotes = toolpath.Notes
      AddToArray(TPTable,{tptoolname = tptoolname,tpnotes = tpnotes,tptypename = tptypename,tptoolnotes = tptoolnotes,tptoolrad = tptoolrad,tpname = tpname,tptool = tptool,tptooldia = tptooldia,tptime = tptime,tptimeraw = tptimeraw,tpvangle = tpvangle,tpfeed=tpfeed,tpfeedunit=tpfeedunit,tpplunge=tpplunge,tpspindle=tpspindle,tptoolnum = tptoolnum,tptoolstep = tptoolstep, tptoolpass = tptoolpass, tptype = tptype,tptoolinmm = tptoolinmm,tpsheet=tpsheet })
   end
   --return tables to main function
   return summary,TPTable

end   
  
 --[[outputs html string to file]]
 function OutputHtml(HTMLTable,path,pathext)
	--sets the full path and filename, if multi sheet appends _sheet(num)
   path = path:gsub(".html",pathext..[[.html]])  
	--insert end body and html tags to html table
	table.insert(HTMLTable,[[</body></html>]])
	--concat htmltable to string
	local htmlstring = table.concat(HTMLTable)
	--set output file path
   local outputhtml = io.output(path,"wb")
	--write html to file
   outputhtml:write(htmlstring)
	--close file
   outputhtml:close() 
 end

 --[[----------add to an array table-----------]]
 function AddToArray(array,item)
   if type(array) ~= "table" then
      array = {}
      table.insert(array,item)
      return array
   else
      table.insert(array,item)
      return array
   end
end


--[[ convert machine time to real time]]
function SecondsToClock(nSeconds)
   if nSeconds == 0 then
      return "00:00:00";
   else
      local nHours = string.format("%02.f", math.floor(nSeconds/3600));
      local nMins = string.format("%02.f", math.floor(nSeconds/60 - (nHours*60)));
      local nSecs = string.format("%02.f", math.floor(nSeconds - nHours*3600 - nMins *60));
      return nHours..":"..nMins..":"..nSecs
   end
end
 
 --[[ holds and returns strings for static html]]
function AddStaticHTML(string,sheets,s,job)
   local sheettag
     
   if string == "css" then
      if sheets > 1 then
         sheettag = "Sheet "..s 
      else
         sheettag = ""
      end
   string = [[
     <!DOCTYPE html>
<html>

<head>
<meta content="text/html; charset=utf-8" http-equiv="Content-Type"><title>]]..job.Name..[[ ]]..sheettag..[[</title>
<style>
body{height:842px;width:595px;margin-left:auto;margin-right:auto; font-family:Verdana, Geneva, Tahoma, sans-serif; font-size:12px;color:#646566;line-height:20px;}
.FR{float:right;}
.FL{float:left;}
.title{text-align:center; font-size:20px;margin-top:20px;}
.mauto{margin-left:auto;margin-right:auto;}
p{margin:0px;padding:0px;}
@media print {
    div{
        page-break-inside: avoid;
    -webkit-region-break-inside: avoid; 
    }
}
#header{height:72px;margin-bottom:10px;background-image: url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAABkAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MjE2RDIyMzY1NDVCRTQxMUIwMEVCNDM3Njk5ODBGRDciIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6QzlDQjhGRDY1REJBMTFFNEJGMDM4MkZEREZCMkNFQUEiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6QzlDQjhGRDU1REJBMTFFNEJGMDM4MkZEREZCMkNFQUEiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MjE2RDIyMzY1NDVCRTQxMUIwMEVCNDM3Njk5ODBGRDciIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MjE2RDIyMzY1NDVCRTQxMUIwMEVCNDM3Njk5ODBGRDciLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94Onht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);}
#title{float:left; font-size:24px; color:white;max-width: 290px;overflow: hidden;height: 24px;}
#titlediv{float:left;margin:15px 0 0 25px;}
 .boxborder{margin:20px 20px 0px 20px; border:1px #646566 solid; border-radius:15px 15px 15px 15px;float:left;}
.boxtitle{font-size:18px; background-color:white;float: left;position: relative;margin-top: -13px;left: 25px;}
.boxicon{float:right;width:25px; height:25px;position:relative; margin-top:-10px;}
.clock{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAABkAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDo5Rjk5RUE2RTVBOTkxMUU0QjVCNUI4MkExRDlFRDZGRCIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDo5Rjk5RUE2RjVBOTkxMUU0QjVCNUI4MkExRDlFRDZGRCI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjlGOTlFQTZDNUE5OTExRTRCNUI1QjgyQTFEOUVENkZEIiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjlGOTlFQTZENUE5OTExRTRCNUI1QjgyQTFEOUVENkZEIi8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQAAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQICAgICAgICAgICAwMDAwMDAwMDAwEBAQEBAQECAQECAgIBAgIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMD/8AAEQgAIQAhAwERAAIRAQMRAf/EAHcAAQACAgMAAAAAAAAAAAAAAAkHCAAKAgQGAQEBAQAAAAAAAAAAAAAAAAABAAIQAAEEAwABAgMFCQAAAAAAAAQCAwUGAQcIABQJEiITEZN0FVYhsdGy0jM0NxkRAAIDAAMBAQAAAAAAAAAAAAABESExQQISUXH/2gAMAwEAAhEDEQA/ANxfuXuCi8Wa9j5aRjCLvtG7kuwuqtXRTi8StrmsZZaUWYphkkgGvxz5TSX3UNOPPOutsMoW458qlINwFUPyJ3D39MSZHW/SURo30MRD2hGg6LV0mz9KrlpVJKrbk6y2ZEiRLkhmIJT9ImUkz0YZV6jDS/k81KWBDenkqf7dvUfL1N13t3m3s2ATsO4uw0cJSbPHgyFOudtlGCSxarXrVgm3QEkzKsgOpZWUwMO5lPzPtfb8WKU9KIEj4S9wKS6Aslm556CpOdN9Ya3aeTZqUS28FG24SPw0k6brA5jxDzBA6HUPPh4eJRkZxJIzzw6lZaGotYKf3RQPMia72mIKY6/90nrK+3Syx8NJ8rs2LVGg8yAUZPiVK1h2Kx16s3AOpyhLIs6VX1AyMp9JeMIyaQ0tSkqbRnGnSMq2Ohtm0RVA1HfLTZ7BFxAsFRpx86wSxQUIFktmHJQO44+S80KM4YepKWm/j/a45hCftznGM5NB/e1hv7UExxXz5TSdoURm7VuvGVeRq0laoQGxDSEfYJZIYrcMcaxJPZzGvj5bU20pCsK+FOc5xnGHtoLCpnuxU4/QNr547jiLXHFbX1xvBmGlDQYuMrklKatmiJKYr1VkwASHXrAxWY4I6KWc5jDpYkitLuMYwhOHrdA6skj/ALH1H9JI+8f/AIePkfSIP51kI7mv3Tu0qltDX409ctxZuG59BYZjIBdptDjk/Y7WHV6JL2MqMDDmbTDmlsoTkwZh0qMU2tzGcYx4O0CpjD7YpkF1jUbNpubhmntTywjsZfpo4YMsoiaGVhxqu0xa/VCNzNZmGkOGS7WXEBksenGUoj6rgxg6Q3zv7ZPJ+hqPSII/VNB2deqh9QonadypcOZZ5mYVKlSjEotsv8xZAXHZfQyKltWctNMI+bKsZVmbbKEg/veDn4Xdj/PHLsPrxIW8tob0RHR7ktHV8q4B64gpE6sj2gGSii5QuNp1zkZNZQqXnWHVjxry3mW8t5x49avgHZy/41Sf6uE+9f8A6PH0i8l/u++FAOvKzWLNTbKrWvQ2py8TOptlirJGUKSyS1IYgJsqPx+YtxTp46HxyGfifjisfWbStK3mncpx+C1IfVL9wHpjkmclYjuHkzbMxbXIyIrT+39XmSEtRrXGVl+XXGyw1YwQ7rcCYOXMOumnRL4T5+VIwQMhTKUJYTwJjTpm+6vtjflSpNS0Vxtum+bxjTIifRKuuWGs6+hbnHjmMJMlWKqWOux1cbJalugSpgMe9jGFP/28ZxeYKZLa8N8H7GpezLF2F2NaR9i9WXdl9kARl4c6A1TDGD+jdjYd4ZOI5yZzG59Gn0SUggBZWwPl36rjqpvhYKXL0WfzImeRFSuyv9Sl/iU/vR4oHhDfBn+BZvxGP5c+TJYIz4CZ5Ef/2Q==) no-repeat;
width:33px; height:33px;position:relative; margin-top:-15px;
}
.material{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDo1NDRDNTIwRjQ1OEYxMUU0OTE5NUQ3QTRBNDM5MjQ2MCIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDo1NDRDNTIxMDQ1OEYxMUU0OTE5NUQ3QTRBNDM5MjQ2MCI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjU0NEM1MjBENDU4RjExRTQ5MTk1RDdBNEE0MzkyNDYwIiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjU0NEM1MjBFNDU4RjExRTQ5MTk1RDdBNEE0MzkyNDYwIi8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAFQAsAwEiAAIRAQMRAf/EAIoAAAMBAAMAAAAAAAAAAAAAAAAEBgUBAwcBAQEBAQAAAAAAAAAAAAAAAAQDAQUQAAAEAwMHBREAAAAAAAAAAAABEQISAwQxEwUhQbFSFGQWkSKCowZRYXGhwdEyQmJyosIjM0QlJhEAAQMBBwUBAAAAAAAAAAAAAQARAlHwMXGBEjJCkaGCAzOi/9oADAMBAAIRAxEAPwDRm47i5ucR1UzIaWpoQdB4pWzD+pOmO8L3ecc19BWUs19/JfLI3GjjI0PLmOwJlaOZIydiTmulERZwBkmm1j2nET3tPukYG9p6uV9uonH0j+YwqdhjMGRFCRgVsjUA4hUbe3GLsyNdH75NPQQa45xjYb+7kxXl2sLrIV1hJ5w/B+hj3tOrUUE5sRql1UzCLg6RfRervghONIPWisTvqJzFeEFdew3u7ekvR5vKAAX7buHmieq/l4KYq24ZlOjmTzLVmsaXxNf5BmUrcMM1rJs9pasqWx3jdMboAAEDauP6ZLL6eXZ1SYTwGpXl4cze1Tq+Zyip/nth/F2JfYgVNKAAEDYfnaqgdw+lqL//2Q==) no-repeat;
width:44px;height:21px;
}
.notes{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAABkAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDoyOEYyQUUzQkMyNzAxMUU0OUJDOUI1ODAwQTVBQ0MyQyIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDoyOEYyQUUzQ0MyNzAxMUU0OUJDOUI1ODAwQTVBQ0MyQyI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjI4RjJBRTM5QzI3MDExRTQ5QkM5QjU4MDBBNUFDQzJDIiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjI4RjJBRTNBQzI3MDExRTQ5QkM5QjU4MDBBNUFDQzJDIi8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQAAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQICAgICAgICAgICAwMDAwMDAwMDAwEBAQEBAQECAQECAgIBAgIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMD/8AAEQgAGgAaAwERAAIRAQMRAf/EALEAAAICAwAAAAAAAAAAAAAAAAUHCAkDBgoBAAEFAQEAAAAAAAAAAAAAAAQCAwYHCAUBEAAABQEDBgkGDwAAAAAAAAABAgMEBQYAEQchMRI1NghBYTNjFDRUZTeBMhMVGDlSYqJDk4RVFlYXOEgJGZkRAAEBBAUGCQYPAAAAAAAAAAECABExAyFREgQFQWFx0VITgZHBMtIzFDQG8KFCQxU2seFygpKyU5OjZJTUNRYH/9oADAMBAAIRAxEAPwBW/wAk2+3vI11vmY/RUrI4sO6doTFGsaJouGhmFaDS0NT9NTLuIZEhG0Y0GLEyyDUDLOEwMdZQRMY5hEbVtjMyZeMRmiZPASlVkJtgAAZninKX0tbXh+94TccLlIAkb4otLKgkqKjTSTTRACAdW0DvaUxqH5nGDJwhE1/m4x6CABbmCUck4feDpN2fbWG/l+JGpj9K73u8ZRc/F1RScljjB1BDukXsZJxUfiI3eIronA5QKZBmBlE1NHRUTMBiHKIlMAgI2UneSVCbLvFlYLwd4Ol5mRMxTCLwgyZybsqUqgghMPhGkUjIW7Mf7C8fOwh7pn2pNQOPGntfVOud25+atYvbZtaO67yI51cebng1UdluO0e+WI+qr+NrBIhFgU9ND0OO0zMZk5xFGmxOc/T1jGUUFZoZYTmNlHTETiOcb77YU8WLf43xhJf/ACU/JM+0VUXcXA0huQHs1JyuRs1aGYyZWogUTN2IjkuvTpcxrg+pX3BYm7SJZQ8JHEvWzKjTH6upiLMyRHbf0ZUCGFygAiT7ukHKqXJpJNCmvHiy2VMlyxFIfoXrbwvKS6o7NWho96QcWp/See0z/R/K5PitpVyc3ui6BhVozRaP/uM3lyNska9TJMtYQHiSctTDipoSbjFZaHbP4540kVRRO5YOGAu0WkmyOk7ZqnASOGi6ahDGA19sqf6Jc8QwTx9iyb/JWhM+/LnS1buYUrlzVFaVJUFBKg42VWeaoFJcQ0qw6YibhYsGkBANIoIeKmYyDhQAG5wiF4ZRGZhBvAeC/wBXgI3WEueJuQ5xd8hfSZC0UueOMamyupuOg255ebmY2Jio4SOXsi/n4Ju1at0zlMdVVU7QhQKBQyFC8xswXiIBboyZk+/z03a6ylzLwsuSlKFlRJgALXIzarKEEqIc6samUPqKpPw3UfhX+YOq1eo/YPVtse7+V5u2vP65iuwn3c7JH1+zGGfztGN+j8e1wMN3xtrID9Feqv3Dbb8qfV/cXwOc0rT69ej1OXrOTlYWXA87gaG/+W2by5wzWE/Rs59Nmlgv4l0n7tnWzbYzbDlS7M9+dn+PYi79YO7/ADIwyeUGSuHp8MGuLsczDf/Z) no-repeat;
width:26px;height:26px;
}
.box33{float:left;width:33%;}
.textleft{text-align:left;}
.textcenter{text-align:center;}
.textright{text-align:right;}
.boxcontainer{margin:0px 20px 15px 20px;width:515px;float:left;text-align:center;}
.VCarve{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDpEREZFREE2RDQ1NkExMUU0QTcwOUNEQjcwREU1Qzc0OCIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDpEREZFREE2RTQ1NkExMUU0QTcwOUNEQjcwREU1Qzc0OCI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOkRERkVEQTZCNDU2QTExRTRBNzA5Q0RCNzBERTVDNzQ4IiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOkRERkVEQTZDNDU2QTExRTRBNzA5Q0RCNzBERTVDNzQ4Ii8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHoAAAMAAwEAAAAAAAAAAAAAAAAFBgECBAcBAAMBAAAAAAAAAAAAAAAAAAABAwIQAAIBAwEEBwcFAAAAAAAAAAECAwARBAUhMRIGUWFxgaEiQkGRseFiExVTFCRUFhEAAAYDAQEAAAAAAAAAAAAAAAERAhITMWHxIgP/2gAMAwEAAhEDEQA/APS9QyTBEOA2djsPUN+/uHfSvF5gnkklikhKtAwVybWNxxDhZT0fTWdRn+7ObHyrsHYPnfwpVCxGbmoouxMLC+4Ax2ufdUH/AEORoeBdrCiSlkUMWuYbyNEx4ZUF3UEEgdO2xt3Vv+a0r+ynjU5lo7pHhQn+RnOIVf1BTtkbsVacf5PRP0fGix0V2gVbZJpQoyOXebsZ2bB1CHMhuSsWUlmC+xQwvu7a43zeYsK/5DQ5GHqlw2EgPWR5vjV5RTdXwDbOiZ5X4dSypNX4HSGJf2+Mkg4WDb5iR032VTUUU/Nehn1PY//Z) no-repeat;
}
.Pocket{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDpFQ0NFNUI2RDQ1NkExMUU0QkNCMEI1QjE3Nzg2NDk4NSIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDpFQ0NFNUI2RTQ1NkExMUU0QkNCMEI1QjE3Nzg2NDk4NSI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOkVDQ0U1QjZCNDU2QTExRTRCQ0IwQjVCMTc3ODY0OTg1IiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOkVDQ0U1QjZDNDU2QTExRTRCQ0IwQjVCMTc3ODY0OTg1Ii8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHgAAAMAAwEAAAAAAAAAAAAAAAAEBgEDBQcBAQEBAQAAAAAAAAAAAAAAAAECAwQQAAEDAwEFAw0AAAAAAAAAAAECAwQAESEFMUEiEwaBkTLwUWGxwRKColMUVBUWEQABBAIDAAAAAAAAAAAAAAAAARECEkFhISIT/9oADAMBAAIRAxEAPwD0fVZYjsePl4K1qBtZKc+XbU031rIjgGdClx2zlDhb5yFJOxV2+IXHnpzXC7NcSylJ5DyxzV7gyjit8ftrIUobDa+4VzymtlY3jBKo4xp/VunT0LXHcQ8lkXeKCQUYvxJUMbK2/wBbon1j3Vx5LP3LjWnsgIcnrCXVJAB5SMuKNvRgVR/pdJ/Fb7qbyq78OwUjZmwT7/Q0tlxbukau/F95RUGXONGTewzgdlKuQOuoXiZi6mgb0Hlqt8nqq4oqpeeSY+mCd6YjS33XtUnxlRHiBHZjuXuhKcrULgeJW+qKiinrTQdr7P/Z) no-repeat;
}
.Profile{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDpGOUFGMkJDRDQ1NkExMUU0QkY1QURGRTEwNUJCRDMxOSIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDpGOUFGMkJDRTQ1NkExMUU0QkY1QURGRTEwNUJCRDMxOSI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOkY5QUYyQkNCNDU2QTExRTRCRjVBREZFMTA1QkJEMzE5IiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOkY5QUYyQkNDNDU2QTExRTRCRjVBREZFMTA1QkJEMzE5Ii8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHgAAAICAwAAAAAAAAAAAAAAAAAGBAUBAwcBAQEBAAAAAAAAAAAAAAAAAAEAAxAAAgECBAIGCwAAAAAAAAAAAQIDAAQRIRIFMQZRkSJiExRBcYEykiNDU1QVFhEAAQQBBQEAAAAAAAAAAAAAEQABAhLwQXGBoSIh/9oADAMBAAIRAxEAPwDpO53gtLcvq0EAsW44KubHPq9tLac+vBgb/brmKE5pOI9asvoPY4dVb+YrpLi4S0LBYXOudzkq28R7RY9DMcMfVWfMReG06SK0CKWZkYEaQO6TWMpuS2y2jBh93U7bebtl3LEW0wZ0Gp0z1KvSQ2Bqb+62r8lOulQRvLaxKsUcW4bu5j8RECuInOs6iBidCVf/AMlsn2T8VN5DpFIntUt1yzzZAZRZ38N9bSBkMF2mfht9PHA5YZe9VBLsl1YyCS75eliCEFn26VjGw78fzFwNdSoqemh4U19Rylnlhhul1JvGho4YV8vbRyDBlbjKSOnHKmaiinzTCUer4F//2Q==) no-repeat;
}
.Texture{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDowNjNBODkyRDQ1NkIxMUU0OENBRTk2RUQ2NzI5Q0EzOSIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDowNjNBODkyRTQ1NkIxMUU0OENBRTk2RUQ2NzI5Q0EzOSI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjA2M0E4OTJCNDU2QjExRTQ4Q0FFOTZFRDY3MjlDQTM5IiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjA2M0E4OTJDNDU2QjExRTQ4Q0FFOTZFRDY3MjlDQTM5Ii8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHQAAAICAwAAAAAAAAAAAAAAAAAGBQcCAwQBAAMBAAAAAAAAAAAAAAAAAAACAwEQAAEDAgQFAgcAAAAAAAAAAAERAgMABDFhEgUhQSITBqEjsUJTFFQVFhEAAQQCAwEAAAAAAAAAAAAAAAERAhJhEyHxIgP/2gAMAwEAAhEDEQA/ALL3C5+3h4O0Od8yKgGJQ455VF2+/XZ9uSJrple0RqhLmdLmh2GKcsHA1hvtz3GyMBIBHQ5uI0YOGbT15tWotwL3xSIrmaS9qoDPH7ZjXlqB05gtqE/otlZS0YJXkYbfyCymYx5DmB4JBOQ1EHAqEPBORrd+62r8lnrSjK111I22tnJJezo0gJ0vCvkI5HTxOa0x/wAnsn0fWt2Sq+QpF2wQ114z5XC9xs7+G9h1amxXTEcAqgBwX41wzTb/AGndG5bJI9koAkfaO7jUA06kGpOnPkKsCiiWvoI7OxU8PhF7LJupa8MjBgi7g0uMhKzPcORJT1proopvNMC+r5P/2Q==) no-repeat;
}
.Drilling{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDoxMjdFQ0I2RDQ1NkIxMUU0QUM4M0JCRjUwQzk4NzZCRSIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDoxMjdFQ0I2RTQ1NkIxMUU0QUM4M0JCRjUwQzk4NzZCRSI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjEyN0VDQjZCNDU2QjExRTRBQzgzQkJGNTBDOTg3NkJFIiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjEyN0VDQjZDNDU2QjExRTRBQzgzQkJGNTBDOTg3NkJFIi8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHEAAAMAAwAAAAAAAAAAAAAAAAAFBgEEBwEBAQEAAAAAAAAAAAAAAAAAAQADEAABAwMDAgQGAwAAAAAAAAABAgMEABEFITESUQZhgTIUQZGSE1MkVBUWEQABBAMBAAAAAAAAAAAAAAAAARFhAvESEyL/2gAMAwEAAhEDEQA/AOlZCUqO0OBstR0PgN9/IedKE9yTEZD2q4pcjpQVuygdEkDlxIF99utZzE5KS6+VJCGQePMhKTx2uT1NTIbci49x8xXm5mSc4rMVZcP2wq6FanS4V186wtddlZYNq0TVHSSwxvc0DIsqebS42lCyhXNNtU6k+Ira/usV/JR86mXmHURY+KZdU6/IIjIeVbmU7uOKt0TTr/JYT8J+qnpZnli51doEOQ7T7n4rbYnM5CKVXTHlpIIA9ICh0Gnqpc41nIMtiXPwr36iQhoQXCWgkDjqhPIWt8L10iileeATfJMdrFOTlOZjgptllPt4zbgsoK3eJHW+lU9FFXnnAet5P//Z) no-repeat;
}
.Engrave{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDoxRkM1QjA5RDQ1NkIxMUU0OTFDQUY1RDZFMTAxMjA0QiIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDoxRkM1QjA5RTQ1NkIxMUU0OTFDQUY1RDZFMTAxMjA0QiI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjFGQzVCMDlCNDU2QjExRTQ5MUNBRjVENkUxMDEyMDRCIiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjFGQzVCMDlDNDU2QjExRTQ5MUNBRjVENkUxMDEyMDRCIi8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAGMAAAMBAQAAAAAAAAAAAAAAAAAFBgEEAQEAAAAAAAAAAAAAAAAAAAAAEAACAQMDAgUFAQAAAAAAAAABAgMAEQQhEgUiFDFBYSMGUXGRMmIzEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwC9+Qcj24hw45TDNkNcuil2CL5Kqaks1l/NL4uW5WGSSJ5QWhUO6ThN2zU7te3AGmvU1qocuXHx4Xy5gLQKW3Wuw08F9TU9gQychmiOWRJELjLzFjdZEDA+1GbxhlI2gft4L60HVD8nJRXmxyyOwRXhJYFidtryKik38lZqebj9DS88MrcqM8ye0LN24BCmUDaJG6tpsP5v60yoJ3kjyr5b9zDK2CrhokiNh0WKt7KSSE7urWwrp+OSSyrlvJG4Jl/2lsHfpFgVAAGxbD738705rF8KDaKKKD//2Q==) no-repeat;
}
.Roughing{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDozMTRGNkY5RDQ1NkIxMUU0QTkwNEZGQTY5OTFGNTkzNiIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDozMTRGNkY5RTQ1NkIxMUU0QTkwNEZGQTY5OTFGNTkzNiI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjMxNEY2RjlCNDU2QjExRTRBOTA0RkZBNjk5MUY1OTM2IiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjMxNEY2RjlDNDU2QjExRTRBOTA0RkZBNjk5MUY1OTM2Ii8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHIAAAMAAwAAAAAAAAAAAAAAAAAFBgMEBwEBAQEBAAAAAAAAAAAAAAAAAQACAxAAAgECAwMKBwAAAAAAAAAAAQIDAAQRIRIxYQVRcZGh0SIyExQGQYHhklNUFREAAwEBAQAAAAAAAAAAAAAAAAERIRIC/9oADAMBAAIRAxEAPwDpfELk28IKHB2OXMMzt6PnWgvF7lQNQU7yM+oisPF7t3uDFDpaYK3kRsdIcx+MY/A/Q1PwSg3Jkhtb97gMWjtLnuwxO20h8xp5id1c36dw2lhYRcWgfAOpVjyZjto/ucJ/ZTr7KQWSyTXMfDw/mOi6bmVdgd+8yjeE1Hoqn9FZ/gj+0U9OBFRNfe2JbiLyvUiaMEMgnTCRWXwsk0BjZSOXClrcA43CNFzPeXUI2iCaNsuQ61ifoqyoqfJKif2/YxwI0iQtBGo0RRupRs8GkZg2feOAx3U4oopzkNp//9k=) no-repeat;
}
.Finishing{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDo0MDU5RDZCRDQ1NkIxMUU0OUE0MEZFRkZFODYwOUVDOSIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDo0MDU5RDZCRTQ1NkIxMUU0OUE0MEZFRkZFODYwOUVDOSI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjQwNTlENkJCNDU2QjExRTQ5QTQwRkVGRkU4NjA5RUM5IiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjQwNTlENkJDNDU2QjExRTQ5QTQwRkVGRkU4NjA5RUM5Ii8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHYAAAIDAQAAAAAAAAAAAAAAAAAGAQUHBAEBAQEAAAAAAAAAAAAAAAAAAAECEAACAQMBBQUGBwAAAAAAAAABAgMAEQQFITFREhNhgaEiBkFxkdEyklODFFQVBxcRAAICAwEBAAAAAAAAAAAAAAABESFBAhLxIv/aAAwDAQACEQMRAD8A0XW9Vh0vE60jWZmCoosWJ32APHd2Vxadq+qZadTpRld4BvzW942eFLX9i5kozcFxfoIZEHDnFr9++o0X1MuPDy39lY2bwaSWRzh1iB2KSI0cimzLsNqn+c0n9ynj8qWtMyH1XUpOnfkcCN2Hb5j3hAfCm39Fh/gR/aKdbQIUlLqHpZ8zHbGfIXJgNiI8mMcwI+krLCYypHGxpd/z9saTmkjyJYhtK40sbC35ixv8K0Oir8+Cym9PYEONEWigbHiQdOKN1KNts0jMG2+Y2Fzwq5oopXJLk//Z) no-repeat;
}
.Inlay{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDo2OUYxRTEyRDQ1NkIxMUU0QjBEM0Y5Qzc2NEZFMTBGQSIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDo2OUYxRTEyRTQ1NkIxMUU0QjBEM0Y5Qzc2NEZFMTBGQSI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjY5RjFFMTJCNDU2QjExRTRCMEQzRjlDNzY0RkUxMEZBIiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjY5RjFFMTJDNDU2QjExRTRCMEQzRjlDNzY0RkUxMEZBIi8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHgAAAMBAQAAAAAAAAAAAAAAAAAFBgMHAQADAQAAAAAAAAAAAAAAAAAAAgMBEAABAgUDAgILAAAAAAAAAAABAgMAESEEBTGBEhMGQWFRcZGhIpJTFFQVFhEAAQMEAQUBAAAAAAAAAAAAARECEgAxQQMiIVFhgRNC/9oADAMBAAIRAxEAPwDpWQulW7Q4GS1Gh8hrrsN4TO93MWb/AELwKEgCXemvp1rLmkGu0aZe9aCnHnFcWWRVWskppOk9SfDyifZfayWXS6Fg27KZMAmXMCs0pVInkqu0Glk3bHOkNWtjiXN7iw6ghScUbnwbra2J27HtaGu7G56YAqutc9Y3LSXm1cmlAlLiapIGtaH3Rr+6xX5KPbE5eJWttuxt/hdvVhhEqcUmritkw3/ksJ9E/NEfob/lfaVX5i36T0tJrjtvu62WpVjkGrxmZ4s3SahPgkGR09cL3HM5ZPB/I9v81tzlcWklkToVU5AR0KCHCcoSsZQW2VTFKVVso3EZpfCLmpjtYpyd05mOCm2Wk/b2yHBJQVq8SPTOkU8EELx+fit5T81//9k=) no-repeat;
}
.Prism{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDo4Q0Y3NTU2RDQ1NkIxMUU0QjM4MEM0Q0JFNkJCQ0MxNiIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDo4Q0Y3NTU2RTQ1NkIxMUU0QjM4MEM0Q0JFNkJCQ0MxNiI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjhDRjc1NTZCNDU2QjExRTRCMzgwQzRDQkU2QkJDQzE2IiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjhDRjc1NTZDNDU2QjExRTRCMzgwQzRDQkU2QkJDQzE2Ii8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHMAAAMBAQEAAAAAAAAAAAAAAAAFBgIEBwEAAwEAAAAAAAAAAAAAAAAAAAEDAhAAAgEDAgUDAgcAAAAAAAAAAQIDABEEEgUhMUGRBlFxE2EUMiNTVBU1FhEAAQMFAQAAAAAAAAAAAAAAAAISEwERIWHxIv/aAAwDAQACEQMRAD8A9L3DJaCIBDpdjwPoBzPHtSMeZY8Hw/eflLkDXCziwZdWm+pbgX9qx5LnxWETyfEmTIuMJeioTZ2v7X7ilmRBus5fGkx4JcFyFQkhX+JOCKQfw8B0qCl1diuCyUUbmhWx7xjsLuCvW/MWrX8ztf7lO9TeZ88qR4aEDJz3EKleSqeMhX6Kgpx/k9k/RPeiRbb7sEaXW0Jsnxry3Gdzg7hDmQEnTBlpchei3s3L3rkkzfJsL+x2V5FHOTEbXw9bDWBV7RTVHwEydJjxa255Mm8aGjiiX7fGjkFmDc5iR634VT0UU/MejPp+z//Z) no-repeat;
}
.Fluting{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDo5OUY0NjA1RDQ1NkIxMUU0QjA1MzhEMjBFQTFCQzg2OCIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDo5OUY0NjA1RTQ1NkIxMUU0QjA1MzhEMjBFQTFCQzg2OCI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjk5RjQ2MDVCNDU2QjExRTRCMDUzOEQyMEVBMUJDODY4IiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjk5RjQ2MDVDNDU2QjExRTRCMDUzOEQyMEVBMUJDODY4Ii8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQADAgICAkIDAkJDBELCgsRFQ8MDA8VGBMTFRMTGBcSFBQUFBIXFxscHhwbFyQkJyckJDUzMzM1Ozs7Ozs7Ozs7OwENCwsNDg0QDg4QFA4PDhQUEBEREBQdFBQVFBQdJRoXFxcXGiUgIx4eHiMgKCglJSgoMjIwMjI7Ozs7Ozs7Ozs7/8AAEQgAGQAZAwEiAAIRAQMRAf/EAHYAAAMBAQEAAAAAAAAAAAAAAAAFBgQCBwEAAwEAAAAAAAAAAAAAAAAAAAEDAhAAAQIDBQcCBwAAAAAAAAAAAQIDABEEITESBQZBUYGhsSITcRUyYiNTFFQWEQABBAIDAQAAAAAAAAAAAAAAARECE2ESMfEiA//aAAwDAQACEQMRAD8A9LzCpUw0MBk4o2egvv4DjCpGoahCFOOslaAoJZw2rcBvVIXAdIM2qPM8UJPxHAk7kieJXXlGIqwlbgFjY8bafmMgR0TEJ/RdlZeC8YJqjoO2s8pHHHGjMLZIDkrUiYneZbI796yr9lHOJyrQ4pprL2D9esWGEqF8j3OucBOHH8nkn2ecFktXywq4u2HE9Rp3VtM4pdDmDFa0CShuqRJYTsSFCeyy+MblVqGiw+4ZI6pLZxeSkV5Bt7iO7fvi9ghyr6CNnZM6Xw5lVOZvgUhlpP49MhwYVBV7xI3zsimggh+a8GfW+T//2Q==) no-repeat;
}
.Merged{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6Njc2NEU2RjE5NTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6RDJBMDQ5NzM1QUI4MTFFNEFFMzhENjNENzVCNDhDMDgiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6RDJBMDQ5NzI1QUI4MTFFNEFFMzhENjNENzVCNDhDMDgiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6Njc2NEU2RjE5NTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6Njc2NEU2RjE5NTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAAZABkDASIAAhEBAxEB/8QAfwABAQEBAAAAAAAAAAAAAAAABgUHBAEBAAMBAAAAAAAAAAAAAAAABAECAwUQAAICAQIEBAQHAAAAAAAAAAIDAQQFABIRIUEGUSIyFDFCUrJhcXKCEzU2EQAABAMHAwUAAAAAAAAAAAARAhIDAAETITFhcSJCBEFRcvCBoRQk/9oADAMBAAIRAxEAPwDR8xl62Jqe4fBMMyhdeuHNjWl6VrHrM6CFl8jX7iG9cufwNSXDISMkdda4iT9kCh9ZdN/x36sd6jaxe/O1xZYfIwhTi4SukuY87AGPmZPLd00X7b2xWtjZBjDewFjAREshhTxAvPI84Lx1PJ5U+I00dtubtUxSOWXyNMJkLj6ujZhgrpXjGPItIqil6zmIDlKNJw+ap5euTa+9bFTsfWcOxyi+lgTzj8NUNCuz4v3CF1bciuDCZk7zNrG3bETIyAlziFBHh+UeOmuk0W6wWoBSN/jnheGMHGYQB7n7tzo5W1g8akfLMLEwGTaUEAlPLnHzeGufHdn56nXJ1lQWUW1l7unvmHRziYkZ9Mn1+OlmN/vsl+ofsDVrXNeppPWFIac+iE2rG6HavrypUwsqpFeC1bfGzvBHCZh1axSxK2KbXkpTCiXKbChAZKIII4R0+nS7UPI/6LH/ALvtLVzVP0UL36quzdcBzSPzBtKtoe6Y/9k=) no-repeat;
}
.Custom{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6Njc2NEU2RjE5NTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6MzgyNTkyMkE1QjU1MTFFNDhGRDFBNTdDMDAxRUFBQTIiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6MzgyNTkyMjk1QjU1MTFFNDhGRDFBNTdDMDAxRUFBQTIiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6Njc2NEU2RjE5NTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6Njc2NEU2RjE5NTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAAZABkDASIAAhEBAxEB/8QAgQABAAMBAAAAAAAAAAAAAAAABgAEBwUBAAMBAAAAAAAAAAAAAAAAAAECAwUQAAICAQQBAgILAQAAAAAAAAECAwQRACESBTFRIhMGQWGBkaHBQlKSUxQVEQAABAQEBAcBAAAAAAAAAAABEQISACExE0FhIgPwUTIUgaHBQmIEJAX/2gAMAwEAAhEDEQA/AG3bd5Mknw6Ui8GiJ5FDseSpkE8f3baL2PmzvXetNTYiKJ+FeEgs1liffyBPIqoOAfz8dHv1u1bxaVI1imjyfh42fmo2G2xC7fXo5YsPbaSzZkUcEVbNiLZYY8eytXA/U3g/jtk6lvCJAEw8qRofzkJcpQglYgCSMHdUibnTngExMNK6nuKfaQs1eRXlhwtiNSTwfG43AyM+D4Or+sw6y3NTvpPUrRxdjNGsNSqoISKEYzNZ4e52Yepz9PoNaD/1qf8Aen8W0Lim01GXGcN2WzfAHDaFIrIwOUuqjT93pqjnfNVWaUVpIazztloneJeTxq4GWC7Z8H7dH+z+XO1py0f8VQW6yxhIIfIhsycTJNNnPLJz7jsNvQaf6mm3WkBnWRViH0btxTGtaL7hsIhq2fOmB4HBHqvle5VMkbssk+ec1hwQHZh4Vipyo9NJPh3PSH7m1a1NHQz4wn6O4xvu4yaXgWUf/9k=) no-repeat;
}
.boxpic{width:75px;margin-top:20px;}
.zztop{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MThFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6NENBQTZDM0E0NTkwMTFFNEE1NDVCMTQxN0M0RUQ4MEQiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6NENBQTZDMzk0NTkwMTFFNEE1NDVCMTQxN0M0RUQ4MEQiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MThFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MThFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAA3AEMDASIAAhEBAxEB/8QAfwABAAIDAQEAAAAAAAAAAAAAAAQGAgUHAwEBAQEBAQEBAAAAAAAAAAAAAAQAAwECBRAAAgEDAQUGBAcBAAAAAAAAAAECEQMFBCExQRIGUaHRkxRUYXGR0rHBIkJSchMVEQACAQUBAQEBAQAAAAAAAAAAAQIRURIDBDEiIYET/9oADAMBAAIRAxEAPwDqp56i9GxZndlugqs9DQ9U6x27VvSx2Of65P4bVsdfqeNk8IOVj3rhnNRuZSznYzylnJ8JMrnPJ72Ob4gX0TuOXNCxYo5yfGT+p6xzb4srKkxzy7SXRO5PnhYtH/arsTJ2j1TvcalLhOXMiy4ObdKm2nc5So2Y7tMYxqjeAAWENB1V1HDCwsxclCV/mam9tOTl3J/2KHZ6quZTJ3VqHzQarCdKPZSNKRRfuqum9LntLG1fTU7e23dhRTj20bT2PijmePw8dLcc1Vyf7nvp2Bemvjfy/EfR5Z6FpaUH/t45f38oWH/fT0rzdz8B6nTrj3MiU2GLCYo0yZN9XY7e5j1lj+XczXs+M7ijmTNnDWWXJJS/EtGBkpJNOpSNNDmupF9wNnksJm/PD6qYdE/mhuAANBA5czqJzl4rJ+zv+XPwC9Sbwoq+iuVpZ1dPCGzFkx4rKezv+VPwPjxOU9nf8qfgGxlZiMo3RBZiyc8RlfZajyp/aYvEZX2Wo8qf2ncZWZzKN0YaBVvR+Z0LFRpp4/IpGhxeThei5aO/FV3u3NfkXrHQnGxFTi4um5qgnnTVaoN0NflGSwAJDgAEQABEAARAAEQABEf/2Q==) no-repeat;
width:67px;height:55px; margin-left:20px;
}
.zzbot{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MThFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6NTMwNERERkM0NTkwMTFFNDg3MTdCMkJEQTEwQjRBMjYiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6NTMwNERERkI0NTkwMTFFNDg3MTdCMkJEQTEwQjRBMjYiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MThFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MThFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAA3AEMDASIAAhEBAxEB/8QAgwAAAgIDAQAAAAAAAAAAAAAAAAYCBAMFBwEBAQADAQAAAAAAAAAAAAAAAAQAAgMBEAABAwMCAgcHBQAAAAAAAAABAAIDEQQFIRIxBkFRYZGhkxRx0SJS0lQVscHxchMRAAIBBAEDBAMAAAAAAAAAAAABAhFREgQDIUEiMXGRE6GCFP/aAAwDAQACEQMRAD8A6qsdxM2CF8ruDBUrItDzTeGOKO1boX/G49mo0Ne9U5J4QcrF+OGc1G5J2c6isTs4/ocUu73HiV5u7UJ7E7jlrwsMbc4+urj3rI3NnpKWQ4r3e7rXFsTuR68LDP8Amq6VV6zujN01SYx7twTJhHk0qtuHmcpUbMebhjGNUbxCEJYQEiZXJQXl7JMHfAdGaEaAU709rlxRdt9Irs6v4E6i6ydqL5LX+9v83gfcj1NuOnwKqFQKJRC8mXvVwdfgUesg+bwK15USu4omTNmy8hLgA79U0YFwcAQapItmbpQE+4GHZACt9eHlUw2J+NDcIQhNBAuXlOPNXMTMKyFpcGOn3EPOtNm3gD/Zc8x+UkyGQktraF0jA3ewNBc6gIHAV60XZ8nFL1jX8j9XgmuKXK1SD7+3Q2BUSrv4rJkV9HP5b/conE5T7Ofyn+5GxlZl8o3RSKiVdOJyv2c/lP8ApUTiMr9lceU/6V3GVmcyjdEbAVmb7V0HFNAt2+xJNji8myZpdZztFeJjeP2TzjmPbA0PaWmnAiiTrpqtUG2GuzLaEISQ4vc4Yvl/JW0cGYuorOTU28skjInilN2wycRwr/C1fKfL/K2OuXmyyUF7dOFTtmje8MFNPgPCvYhCr4Zdsjdf0fT0y+mv6joKUFOC9QhWMAQhChAQhChAQhChD//Z) no-repeat;
width:67px;height:55px;margin-left:20px;
}
.xycenter{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6MTIxNDk1RDI0NTkwMTFFNEFERTU5NzhCNkNFMkQyMzQiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6MTIxNDk1RDE0NTkwMTFFNEFERTU5NzhCNkNFMkQyMzQiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAApADkDASIAAhEBAxEB/8QAgQAAAgIDAQAAAAAAAAAAAAAAAAQDBgIFBwEBAAMBAQAAAAAAAAAAAAAAAAABBAMCEAABAwMBBAgFBQEAAAAAAAABAAIDEQQFMdKTFFQhQVGBkRIyFWEiQoITodFSIzMGEQABAwIGAwAAAAAAAAAAAAABABECIUExoRIiUgNhBBT/2gAMAwEAAhEDEQA/AOqoQk8rfCxsnzD/AEPyxA9bzp4apEsHNkwHLC6zfksdG8xyXULHtNHNdI0EH4glY+7Yrnbfes2lRJGEkud8ziaknUk9aheyhpoaVp8CpvqPHNUj1RyyXQfdsVztvvWbSPdsVztvvWbS50QQvEvrPHNHyjlkumQXdrcgm3mjmDfV+NwdSvb5SVKtR/zWN4HHh8gpPcUkk7QPpb3BbdUvLQ7VZ2U7R1s9HZ0KrZu74y9LGmsNtVjewv8ArPd6fFbrNZDgLF0jSBNIfxw1/k7r+0dKrMb7drAxsjSAKV8w/VZexKmkXxWvrwrqNsEtPC90bhGfK8ghriK0NOg0Vat7TPS5fiL53lbEC2raeVzdOinV19KtpMR0c094UbmtOhBUtQrY9hjGUQ26hpVIOjTuAxnHZFoeKwQUkl7DT0t7yopGANLjoNVb8DjuBsGh4pPN/ZL2gnRv2hd9HXqm5wjVYd/ZpiwxlRbJCEK5RLCWGGdhjmY2Vh1Y8Bw8Cl/acVyVvumbKbQkWuyYezpT2nFclb7pmyj2nFclb7pmym0I2+EbvKVGKxYIIs4AR0giJn7JpCEBrIL3QhCE0l//2Q==) no-repeat;
width:57px;height:41px;margin-left:55px;
}
.xytl{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6MTkzMDEyOTU0NTkwMTFFNDk1MURDOTExQkJCQTA1RjEiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6MTkzMDEyOTQ0NTkwMTFFNDk1MURDOTExQkJCQTA1RjEiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAApADkDASIAAhEBAxEB/8QAiQAAAgIDAQAAAAAAAAAAAAAAAAUDBwEEBgIBAAMBAQAAAAAAAAAAAAAAAAECBAMAEAACAgEBBAYFDQAAAAAAAAABAgADBBEhQQUGMVFhEiLSgZEyU5NxocFCYoLCEyODNBUWEQAABQEHBAMAAAAAAAAAAAAAARECEgMxQYGhQiMUIWFSYnEyBP/aAAwDAQACEQMRAD8AtWYZlRS7kKqjVmOwADeZma+eMY4OQuV/Hat1uAJBKEEMAV0PR1TgStJRpY3MvCcniP8AWpb3ckr361fQCwDXXubd2muh2/PGsp/G5bFGc2S9rWKCTWG9oD7R+sdIzaoDdJuSlpL8Cyr+WnLaccUL7FeLNhKuKgboaDqg5ZeOYz4p+WQtGE5nk3hxSuziDjT839Oodag+JvXOmm8zhONyoMYFOEuygiDmPL77LgVnYNLL/wAC/T6o5ysmvExrMm06JUpY9vUB8s5MGy0tddtuuYvZ2E7vQNkSu9GoVrg9BiuU7GjUeuQPXGDJInrkaCxQuaue8PBszcurFr2GxtCepRtZvQJO9c6DlXhwrqfPceK7wVdiA7T94x6VOTyK4uphKr4sM7z6EHlFNdFKU1Du11qFUdg2SSEJeIBFk41GVS1GQgsqf2lM0ByzwQdGOR+5Z540hFOOpMQzZaVwCwct8GHRQ3xbfPD/ADnB/ct8W3zxnCDb9cgdz2zCz/OcH9y3xbfPGNdaVVrVWO6iAKqjcANAJ6hC2OlMAHT1LiCEIRgo/9k=) no-repeat;
width:57px;height:41px;margin-left:55px;
}
.xytr{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6MjQ1QzlFNUU0NTkwMTFFNEI1NEI5RTAyMjc1OEMxMTciIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6MjQ1QzlFNUQ0NTkwMTFFNEI1NEI5RTAyMjc1OEMxMTciIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAApADkDASIAAhEBAxEB/8QAhwAAAgMBAQAAAAAAAAAAAAAAAAQDBQYBBwEAAwEBAAAAAAAAAAAAAAAAAAEEAwIQAAECBAIHBgUFAAAAAAAAAAEAAhEDBAUhEjFh0pNUFQZRgZEiMhPwQaFCgtFykiMUEQABAgMGBgMAAAAAAAAAAAABABFBAhIxYXGhBBSxIkJSAxNRgSP/2gAMAwEAAhEDEQA/APVUIVX1BXmkojLlmE6oixkNIH3u7h9UpiACTBOUEkARTJutrBgayQCNI91n6o5tauNp96zaWCdKHYonMU26PbmqdqO7Jehc2tXG0+9ZtLj7zaWMc91bIytBJhMaTAagYrzsiC57fuf15c+fy5IRjHCENaW6PbmntZYzFsFsKDrW11t4Fpb5Zs0EyHg5g4iJLXZfScoj8Y6FZTp3oC22erZcIum1IaCA8giW4+r28O6JxWrW/wClMKnyQ+k91k/qpa+r5wXNGJWQuNUa+rfUDGUPJI/YPu/I4q56jr209K2mDwyZVEszRhCWPWfDBUQmU+UBr2wGAgQs9RN0j7XGnk6jgEs+WoHy084yzoc094UTmtOghSkKp0g6WrjpS2f6K01cwRlU3p1zDo/iMfBIulOcQ1gzOcQ1jR83EwAW2tlCygopdM3EtEZju15xcVtp/G81Rsl4rHUeRpaRbNwTSEIVijUU+mp6hobUSmTmgxDZjQ4A/koeU2rgqfdM2U2hItFkw8HSnKbVwVPumbKOU2rgqfdM2U2hHLcjmvS0u226U8TJdLJY9pi1zZbQQdRATKEIDQQXihCEJpL/2Q==) no-repeat;
width:57px;height:41px;margin-left:55px;
}
.xybl{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6MzkwQkNCOTk0NTkwMTFFNDlFQzJFQjg5MDQyRDdFODkiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6MzkwQkNCOTg0NTkwMTFFNDlFQzJFQjg5MDQyRDdFODkiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAApADkDASIAAhEBAxEB/8QAhAABAAIDAQAAAAAAAAAAAAAAAAQFAgMGBwEAAwEBAAAAAAAAAAAAAAAAAAEEAwIQAAEDAwEEBwYHAAAAAAAAAAEAAgMRBAUxIRIiBkFR0qMUVBZhkUKCEyOBscEycjMVEQABAwQABQUAAAAAAAAAAAABABECMVESAyFBgQQUYbEyQlL/2gAMAwEAAhEDEQA/APVURV+avzZWTiw0ml4IvYTq75RtSJABJ5JgEkAc1jLzFhoZHRSXFHsJa4BjyKjYdrWkLD1Rg/M93J2Fx7o1pcxSnupWCq8WNyu29UYPzPdydhPVGD8z3cnYXCltFil5U/yE/Fhcr0axyljkN/wkv1Pp03+FzaV0/cB1KWq3A43/AD8eyNwpNJ9yb+R+H5RsVkqnlg/DJqKVo5txxeqLk8rdeOvHyNNYYaxw9RoeN34n8lr5v53hxLp7CAjxTGhrwa733Gh3DTSjXalQbPKY+e1ikjfuMcwENcNoBGhWO+bjEdVTq7ecBHZMMJfF/dZvjWh8akm7tDpK1a3T2x0kb71MYmy2cXUR8asuWsZ4vICaQVhtaPd1F/wD9VDc+EjheHHoaCCSeoBdph8eLCxZCf7XccxHS92vu0WmjW83NIrPfsaLCslOREVqiVVl+WMJmZ4bjIW4lmg2MfUg0rXddTY4V6CrKKJkMYjjFGt0CzRIM5ZvVdSzxjllj9Xp0RERNcoiIhCIiIQv/9k=) no-repeat;
width:57px;height:41px;margin-left:55px;
}
.xybr{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAAAoAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6MzJCQUNGRjU0NTkwMTFFNEI2NzJGM0UzRDE2NzU1RUQiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6MzJCQUNGRjQ0NTkwMTFFNEI2NzJGM0UzRDE2NzU1RUQiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MTdFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz7/7gAOQWRvYmUAZMAAAAAB/9sAhAAMCAgICQgMCQkMEQsKCxEVDwwMDxUYExMVExMYFxIUFBQUEhcXGxweHBsXJCQnJyQkNTMzMzU7Ozs7Ozs7Ozs7AQ0LCw0ODRAODhAUDg8OFBQQEREQFB0UFBUUFB0lGhcXFxcaJSAjHh4eIyAoKCUlKCgyMjAyMjs7Ozs7Ozs7Ozv/wAARCAApADkDASIAAhEBAxEB/8QAhAABAAIDAQAAAAAAAAAAAAAAAAQGAgMFBwEAAwEBAAAAAAAAAAAAAAAAAAEEAgUQAAEDAwEEBwYHAQAAAAAAAAEAAgMRBAUhMUFRFIESIpJT0xaRMkITRAah0VLSM4OTBxEAAgEDAQkBAAAAAAAAAAAAAAERAhIDITFBUWGRIhMEFIH/2gAMAwEAAhEDEQA/APVURQ8rfcjZPmH8p7EQ4vOz2bUm4UvcNKXC3kS8+58faXD7dzJZHRmjnRhpbXeO08bFH9ZY3wbjus8xVt8ZJJJJJ1JO0nitLo1I/ZrnRIrXrURrJavWeM8G47rPMT1njPBuO6zzFUHMWB0S+nJy6D+bHz6l+xeftMnM6GCOVrmN65L2tApWm1rnLprk/bWN5HHh0gpPcUkk4gfC3oC6ypmvxzpdEk0UXxrbMBVfMXXOXrmtNYbasbOBf8buj3V3snLcxWEz7RhknDaMa3U1OnWpvptVViZcsYGcldUaNphfr+Cznbi1J67TWBKbm1psNT41ofGppZcn6O5H9L/yWJt7o/SXH+Mn7VLZVwZVfTxRznxqZgcZz2RaHisMFJJeB/S3pKj5GV2Otzd3VtcNgaQHuMTwBXZUloA10U7/AJ1nDkW30XyCxjJA6OfXtAj3Duqym47/AG7xY+9XdB5VV4KslMWrtmeJdERFac4IiIAIiIAwmhinifDMxskUgLXscKtc06EEFarPH2NhH8qygZbxjYyMdUCproFIRA9Y3xP5IREQI//Z) no-repeat;
width:57px;height:41px;margin-left:55px;
}
.rapid{background:url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAABkAAD/4QNtaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6MTlFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6RkJDM0Y2NUI1OUZEMTFFNDk5MUJDRTFDRDExNEQzNUQiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6RkJDM0Y2NUE1OUZEMTFFNDk5MUJDRTFDRDExNEQzNUQiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENTNSBXaW5kb3dzIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNlSUQ9InhtcC5paWQ6MTlFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6MTlFMzUxMzM4MTNBRTQxMUJCNjI5NDFERUU5OUIxNjUiLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94Onht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) no-repeat;
height:77px;width:75px;margin-left:80px;}
.layout{background-image: url(data:image/jpeg;base64,/9j/4QAYRXhpZgAASUkqAAgAAAAAAAAAAAAAAP/sABFEdWNreQABAAQAAABkAAD/4QMpaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjAtYzA2MCA2MS4xMzQ3NzcsIDIwMTAvMDIvMTItMTc6MzI6MDAgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bXA6Q3JlYXRvclRvb2w9IkFkb2JlIFBob3Rvc2hvcCBDUzUgV2luZG93cyIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDo1RTdCMTFGQjVEQzExMUU0Qjg0NEJFNjdERTZDNDE3MyIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRpZDo1RTdCMTFGQzVEQzExMUU0Qjg0NEJFNjdERTZDNDE3MyI+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjVFN0IxMUY5NURDMTExRTRCODQ0QkU2N0RFNkM0MTczIiBzdFJlZjpkb2N1bWVudElEPSJ4bXAuZGlkOjVFN0IxMUZBNURDMTExRTRCODQ0QkU2N0RFNkM0MTczIi8+IDwvcmRmOkRlc2NyaXB0aW9uPiA8L3JkZjpSREY+IDwveDp4bXBtZXRhPiA8P3hwYWNrZXQgZW5kPSJyIj8+/+4ADkFkb2JlAGTAAAAAAf/bAIQAAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQICAgICAgICAgICAwMDAwMDAwMDAwEBAQEBAQECAQECAgIBAgIDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMD/8AAEQgAGQAZAwERAAIRAQMRAf/EAGkAAAICAwAAAAAAAAAAAAAAAAAHCAkEBgoBAQEBAAAAAAAAAAAAAAAAAAABAhAAAQUBAQEBAQEAAAAAAAAABAIDBQYHAQgAEhEWEQEBAAEDBAMAAAAAAAAAAAAAAREhMQJRodESgbFS/9oADAMBAAIRAxEAPwDsJjda9Mx/pXdi9UPxDI/EmU2arVeoWy3US4Rd80EmXxjNbPNS52rWXYatnlZrLOpaWiKiJEGsWAWTIgpeHLXFyLAZB9kt0m4aQ3rfz+u2TYBO9YSzVBq7VzIWeVqVKbYkrCdJW9mzxDco5ZOxpj0JGx8Q8sdpPHxkyCFu96l9n+X15dKFZI636YkfS2ElZVIYfrviXVbNaavcLXUaJcJS+56RE4xpVnhZcLVq1sVpzyy1l/UszXFS8ifWK+LGETsRDiLlJF8wgCWWbieH0EXPSZl65WYscWuVN6uN7R5pdjpV+6zAs2VKNegMoIixDYFqglggR5dkS0KQQiSJcHBWopDD7qeBr1x3+L9JWfGSetc1q7ON0nOlSKs6y5BQq9RsqAmQkWXYOgEDn8x9x8kol9wlLzKhmkMIaaUl13rqks5Vr3lyQvLlbnRyYCrorjm5eoXJKVbuUs/NByvfReuuSgIEC5RmApGOCsfXAxiXJIVwkBtBaxx3V9CQEtfgrxk9at2w+hNu8iaHm+35tXaxouV2zD/QVRxTRXqHbIqsUHHd0i1Ba1LULRcO/wBNVNjrlkCmHZ92Fj1DtREQCLKSZR7gVlxchoAYtqXNEtPe+lt4Gb7TKF+Lbyq+cOETauTmkfutuOP+d3K6pirJ6klHBRGTkqmF9Keea6GgfXtx/M7+Uxet7eC3CumjYDvnnvytUKPqOr1TU7nrOlapv0tldmMqlEqs9WN302aGvOl1Ct03G65otv3/ALENQg4bbyVQZhYhkZHP9hpCYzbm6aCwb6KPgPgPgPg//9k=);}
#vectorcenter{margin-left:auto;margin-right:auto;width:400px;padding-top:2px;}
#jobtitle{font-size: 11px;color: white;max-width: 320px;height: 20px;overflow: hidden;margin-top: 5px;font-family:arial;}
.fullwidth{text-align:left;width:100%;}
.indent{text-indent:15px;}
#svg2{margin:2px 2px 2px 2px;}
.level{max-width: 100%;overflow: hidden;height: 20px;}
#footer{margin: 20px 0 20px 0;height: 20px;width: 100%;float: left;background-color: #5c5c5c;text-align: center;color: white;border-radius: 0 0 10px 10px;font-size: 10px;}
</style>
</head>
<body>
]]
elseif string == "summarybox" then
    string = [[<div class="boxborder"><div class="boxtitle">]]..HTMLEncode(vSTR("Toolpaths Summary"))..[[</div><div class="boxicon clock"></div>
<div class="boxcontainer">]]
elseif string == "material" then
    string = [[<div class="boxborder"><div class="boxtitle">]]..HTMLEncode(vSTR("Material Setup"))..[[</div><div class="boxicon material"></div>
<div class="boxcontainer">]]
elseif string == "jobnotes" then
    string = [[<div class="boxborder"><div class="boxtitle">]]..HTMLEncode(vSTR("Job Notes"))..[[</div><div class="boxicon notes"></div>
<div class="boxcontainer">]]
 elseif string == "footer" then
    string = [[<div id="footer">]]..gJobSetUpV..[[</div>]]
   end

   return string

end