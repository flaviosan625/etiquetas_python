-- VECTRIC LUA SCRIPT

--[[ =============================================================
|
|  Import all the DXF files in a directory and lay them out so that they
| dont overlap. This allows nesting to be easily done for a group of DXF files
|
| BrianM 01/02/2011 Remove output of log file to c:\temp\lua_filelist.txt
| BrianM 11/02/2011 Properley remove output of log file to c:\temp\lua_filelist.txt
| BrianM 15/01/2013 Update with 'strict' setting
| BrianM 19/02/2013 Update for 'VectricJob' use
|
| ===============================================================
]]

require "strict"


-- -----------  Directory to process and file filter ------------------------------
g_base_directory = ""
g_file_filter = "*.dxf"
g_process_sub_dirs = true

-- ------------ Log File Data ----------------------------------------------
g_output_log_file = true
g_log_file_name = "dxf_filelist.txt"
g_log_file_path = ""
g_log_file = nil

-- ---------------- Variable used to lay out imported vectors -------------------

g_max_items_on_row  = 3 
g_border_gap_x = 5
g_border_gap_y = 5

g_cur_row_bounds = Box2D()
g_cur_row_index = 1;
g_cur_col_index = 0;

--  --------------- settings for default job ----------------------------

g_default_job_name = "DXF Batch Layout"
g_default_job_width = 96
g_default_job_height = 48
g_default_job_thickness = 0.5
g_default_job_in_mm = false
g_default_job_origin = "BLC"
g_default_z_on_surface = true

g_job_bounds = Box2D()


--[[ ----------- DirectoryProcessor -------------------------------------------------
|
| Given a root directory and file filter, call the passed function with every file which matches the filter
|
| The do_sub_dirs flag indicates if sub-directories should be processed as well as the root directory
|
]]
function DirectoryProcessor(job, dir_name, filter, do_sub_dirs, function_ptr)

    local num_files_processed = 0;
    
    local directory_reader = DirectoryReader()
    local cur_dir_reader = DirectoryReader()

    directory_reader:BuildDirectoryList(dir_name, do_sub_dirs)
    directory_reader:SortDirs()

    local number_of_directories = directory_reader:NumberOfDirs()
       
    for i = 1, number_of_directories do

        local cur_directory = directory_reader:DirAtIndex(i)
        
        -- get contents of current directory - dont include sub-dirs, use passed filter
        cur_dir_reader:BuildDirectoryList(cur_directory.Name, false)
        cur_dir_reader:GetFiles(filter, true, false)
        
        -- call passed method for each file ...
        local num_files_in_dir = cur_dir_reader:NumberOfFiles()
        for j=1, num_files_in_dir  do
           local file_info = cur_dir_reader:FileAtIndex(j)
           if not function_ptr(job, file_info.Name) then
              return -1
           end   
           num_files_processed = num_files_processed + 1
        end   
        
        -- empty out our directory object ready for next go 
        cur_dir_reader:ClearDirs()
        cur_dir_reader:ClearFiles()
        
    end    
    
    return num_files_processed
end

--[[ ----------- CreateJob -------------------------------------------------
|
| Create a new empty job with the passed settings
|
]]
function CreateJob(
                  job_name, 
                  width, height, thickness, 
                  in_mm, 
                  job_origin, 
                  z_on_surface
                  )

   -- we fill in most of our bounds in a Box2D
   local job_bounds = Box2D()
   local blc = Point2D(0, 0)
   local trc = Point2D(width, height)
   
   -- claculate bottom left corner offset for chosen origin
   local origin_offset = Vector2D(0,0)
   if (job_origin == "BLC") then
      origin_offset:Set(0, 0)
   elseif (job_origin == "BRC") then
      origin_offset:Set(width, 0)
   elseif (job_origin == "TRC") then
      origin_offset:Set(width, height)
   elseif (job_origin == "TLC") then
      origin_offset:Set(0, height)
   elseif (job_origin == "CENTRE") then
      origin_offset:Set(width / 2, height / 2)
   elseif (job_origin == "CENTER") then
      origin_offset:Set(width / 2, height / 2)
   else
      MessageBox("Unknown XY origin specified " .. job_origin)
   end
   
   -- subtract the origin offset vector from our 'standard' corner positions to get position for corners for requested origin
   blc = blc - origin_offset;
   trc = trc - origin_offset;
   
   job_bounds:Merge(blc)
   job_bounds:Merge(trc)
 
   local success = CreateNewJob(
                                job_name,
                                job_bounds,
                                thickness,
                                in_mm,
                                z_on_surface
                                )
                    
  return success

end



--[[ ----------- ImportDxfFile -------------------------------------------------
|
| Import and then layout each file
|
| Write a succes / failure report to the output file
|
]]
function ImportDxfFile(job, filename)
   if g_output_log_file then
     g_log_file:write("Importing  " .. filename .. "\n")
   end 
   if job:ImportDxfDwg(filename) then
      if g_output_log_file then
         g_log_file:write("    Imported succesfully\n")
	  end 
      LayoutImportedVectors(job)
   else
      if g_output_log_file then
         g_log_file:write("    Import failed\n")
      end		 
   end
    
   return true
end


--[[ ----------- LayoutImportedVectors -------------------------------------------------
|
| Layout the currently selected vectors (which are assumed to have been imported)
| so that they dont overlap other vectors imported in this session
|
| Layout starts in the bottom left corner and progress along X and then Y
|
]]

function LayoutImportedVectors(job)

-- get selected vectors bounding box 
   local selection = job.Selection
   if selection.IsEmpty then
      MessageBox("LayoutImportedVectors: No vectors selected!")
      return false
   end   
   
   -- get bounding box of selection (imported vectors)
   local sel_bounds = selection:GetBoundingBox();
  
   -- calculate position for blc of imported vectors
   -- are we starting a new row?
   local blc_pos = Point2D()
   
   if g_cur_col_index >=  g_max_items_on_row then
      -- we will move up to start above currently imported data
      blc_pos = g_cur_row_bounds.TLC
      blc_pos.y = blc_pos.y + g_border_gap_y
      -- now reset bounds for this row
      g_cur_row_bounds:SetInvalid()
      g_cur_row_bounds:Merge(blc_pos);
      g_cur_row_index = g_cur_row_index + 1;
      g_cur_col_index = 1
   else
      -- we are going to place these vectors to the right of the last set (or the start of the row)
      blc_pos = g_cur_row_bounds.BRC
      blc_pos.x = blc_pos.x + g_border_gap_x
      g_cur_col_index = g_cur_col_index + 1
   end
   
   -- vector to transform blc of selection to required position
   local to_blc = blc_pos - sel_bounds.BLC
   local xform = TranslationMatrix2D(to_blc)
  
   selection:Transform(xform)
   
   -- get updated bounds for selection
   sel_bounds = selection:GetBoundingBox();
   -- and merge them into bounds for the current row
   g_cur_row_bounds:Merge(sel_bounds)
   
   
end


--[[ ----------- GetUserChoices -------------------------------------
|
| Display a dialog prompting user for options for processing
|
--]]
function GetUserChoices(job, script_path)

   -- get our default values from the registry (values used last time we were run)
   local registry = Registry("DxfFileProcessor")
   g_base_directory   = registry:GetString("BaseDirectory",  g_base_directory)
   g_process_sub_dirs = registry:GetBool  ("ProcessSubDirs", g_process_sub_dirs)
   g_output_log_file  = registry:GetBool  ("OutputLogFile",  g_output_log_file)

   g_log_file_path    = g_base_directory .. "\\" .. g_log_file_name

   -- ---------------- Variable used to lay out imported vectors -------------------
   g_max_items_on_row = registry:GetInt   ("MaxItemsOnRow",      g_max_items_on_row)
   g_border_gap_x     = registry:GetDouble("DefaultBorderGapX",  g_border_gap_x)
   g_border_gap_y     = registry:GetDouble("DefaultBorderGapY",  g_border_gap_y)

   --  --------------- settings for default job ----------------------------

   g_default_job_width     = registry:GetDouble("DefaultJobWidth",      g_default_job_width)
   g_default_job_height    = registry:GetDouble("DefaultJobHeight",     g_default_job_height)
   g_default_job_thickness = registry:GetDouble("DefaultJobThickness",  g_default_job_thickness)
   g_default_job_in_mm     = registry:GetBool  ("DefaultJobInMM",       g_default_job_in_mm)
   g_default_job_origin    = registry:GetString("DefaultJobOrigin",     g_default_job_origin)
   g_default_z_on_surface  = registry:GetBool  ("DefaultJobZOnSurface", g_default_z_on_surface)

   
   -- If we have a job open use units from that .....
   local in_mm = g_default_job_in_mm
   if job.Exists then
      in_mm = job.InMM 
   end
   -- display our dialog to get user choices

   local html_path = "file:" .. script_path .. "\\DXF_Batch_Processor.htm"
   local dialog = HTML_Dialog(true, g_DialogHtml, 700, 820, "DXF Batch Processor")
   local units_text = "inches"
   if g_default_job_in_mm then
      units_text = "mm"
   end   

   -- set the labels we display for units
   dialog:AddLabelField("Units1", units_text)
   dialog:AddLabelField("Units2", units_text)
   dialog:AddLabelField("Units3", units_text)
   dialog:AddLabelField("Units4", units_text)
   dialog:AddLabelField("Units5", units_text)
    
   --  Directory to process
   dialog:AddTextField("DirNameEdit", g_base_directory);
   dialog:AddDirectoryPicker("DirChooseButton", "DirNameEdit", true);
   dialog:AddCheckBox("ProcessSubDirsCheck", g_process_sub_dirs)

   --  Output log file
   dialog:AddCheckBox("CreateLogFileCheck", g_output_log_file )
   
   -- Layout Control 
   dialog:AddIntegerField("NumColumns", g_max_items_on_row)
   dialog:AddDoubleField("BorderGapX", g_border_gap_x)
   dialog:AddDoubleField("BorderGapY", g_border_gap_y)
    
   -- Drawing Dimensions - only used if no drawing currently open ...
   dialog:AddDoubleField("DrawingWidth", g_default_job_width)
   dialog:AddDoubleField("DrawingHeight", g_default_job_height)
   dialog:AddDoubleField("DrawingThickness", g_default_job_thickness)
    
   local units_index = 1;
   if (in_mm) then
      units_index = 2;
   end   
   dialog:AddRadioGroup("DrawingUnitsGroup", units_index)   
    -- XY origin
   local xy_origin_index = 1
   if g_default_job_origin == "TLC" then
      xy_origin_index = 1
   elseif g_default_job_origin == "TRC" then   
      xy_origin_index = 2
   elseif g_default_job_origin == "CENTER" then   
      xy_origin_index = 3
   elseif g_default_job_origin == "CENTRE" then   
      xy_origin_index = 3
   elseif g_default_job_origin == "BLC" then   
      xy_origin_index = 4
   elseif g_default_job_origin == "BRC" then   
      xy_origin_index = 5
   else
      MessageBox("Unknown XY origin for dialog " .. g_default_job_origin)
   end
   dialog:AddRadioGroup("DrawingOrigin", xy_origin_index) 
    
   -- z origin
   local z_origin_index = 1;
   if not g_default_z_on_surface then
      z_origin_index = 2
   end
   dialog:AddRadioGroup("MaterialZOrigin", z_origin_index) 
    
    
   if  not dialog:ShowDialog() then
      -- DisplayMessageBox("User canceled dialog")
      return false
   end   
   -- if we reach here, user pressed OK on form - get values
   
   --  Directory to process
   g_base_directory   = dialog:GetTextField("DirNameEdit");
   g_process_sub_dirs = dialog:GetCheckBox("ProcessSubDirsCheck")

   --  Output log file
   g_output_log_file  = dialog:GetCheckBox("CreateLogFileCheck")
   g_log_file_path    = g_base_directory .. "\\" .. g_log_file_name
   
   if g_base_directory == "" then
      MessageBox("You must choose a directory containing DXF files for this gadget to work")
	  return false;
   end
   
   -- Layout Control 
   g_max_items_on_row = dialog:GetIntegerField("NumColumns")
   g_border_gap_x     = dialog:GetDoubleField("BorderGapX")
   g_border_gap_y     = dialog:GetDoubleField("BorderGapY")
   
   if not job.Exists then
   
      -- if we reach here we don't have a job currently open so we will create one from the form settings
      g_default_job_width     = dialog:GetDoubleField("DrawingWidth")
      g_default_job_height    = dialog:GetDoubleField("DrawingHeight")
      g_default_job_thickness = dialog:GetDoubleField("DrawingThickness")
      
      units_index = dialog:GetRadioIndex("DrawingUnitsGroup")
      if units_index == 1 then
         g_default_job_in_mm = false
      elseif units_index == 2 then   
         g_default_job_in_mm = true
      else
         MessageBox("Unknown units index from dialog " .. units_index)
      end   
      xy_origin_index = dialog:GetRadioIndex("DrawingOrigin") 
      if xy_origin_index == 1 then
         g_default_job_origin =  "TLC"
      elseif xy_origin_index == 2 then   
         g_default_job_origin =  "TRC"
      elseif xy_origin_index == 3 then   
         g_default_job_origin =  "CENTRE"
      elseif xy_origin_index == 4 then   
         g_default_job_origin =  "BLC"
      elseif xy_origin_index == 5 then   
         g_default_job_origin =  "BRC"
      else
         MessageBox("Unknown XY origin index from dialog " .. xy_origin_index)
      end
      
      z_origin_index = dialog:GetRadioIndex("MaterialZOrigin") 
      if z_origin_index == 1 then
         g_default_z_on_surface = true
      elseif z_origin_index == 2 then
         g_default_z_on_surface = false
      else
         MessageBox("Unknown Z origin index from dialog " .. z_origin_index)
      end
      
      -- save job settings as default for next time ....
      registry:SetDouble("DefaultJobWidth",      g_default_job_width)
      registry:SetDouble("DefaultJobHeight",     g_default_job_height)
      registry:SetDouble("DefaultJobThickness",  g_default_job_thickness)
      registry:SetBool  ("DefaultJobInMM",       g_default_job_in_mm)
      registry:SetString("DefaultJobOrigin",     g_default_job_origin)
      registry:SetBool  ("DefaultJobZOnSurface", g_default_z_on_surface)
      end
   
   -- save layout settings as defaults for next time ....
   registry:SetString("BaseDirectory",  g_base_directory)
   registry:SetBool  ("ProcessSubDirs", g_process_sub_dirs)
   registry:SetBool  ("OutputLogFile",  g_output_log_file)

    -- log_file_path = "c:\\temp\\lua_filelist.txt"

   -- ---------------- Variable used to lay out imported vectors -------------------
   registry:SetInt   ("MaxItemsOnRow",      g_max_items_on_row)
   registry:SetDouble("DefaultBorderGapX",  g_border_gap_x)
   registry:SetDouble("DefaultBorderGapY",  g_border_gap_y)
   
   return true
end
--[[ ----------- main -------------------------------------------------
|
| Process all files in 'base_directory' which match 'file_filter'
|
|
]]
function main(script_path)
    -- display form requestiing options from user
    local job = VectricJob()

    if not GetUserChoices(job, script_path) then
       return false
    end
    

    if not job.Exists then
       DisplayMessageBox("No job loaded - creating default job")
       if not CreateJob(
                       g_default_job_name,  
                       g_default_job_width,
                       g_default_job_height, 
                       g_default_job_thickness, 
                       g_default_job_in_mm,
                       g_default_job_origin, 
                       g_default_z_on_surface
                       ) then
          DisplayMessageBox("Failed to create new drawing")
          return false
       else
          -- DisplayMessageBox("Created new job")
          job = VectricJob()
       end       
    end
    
    
    
    g_job_bounds = job:GetBounds()
    
    -- initialise bounding box for row to bottom of page
    g_cur_row_bounds:Merge(g_job_bounds.BLC)

    -- we write a list of files processed to a log file  
    
	if g_output_log_file then
       g_log_file = io.open(g_log_file_path, "w")
       if g_log_file ~= nil then
	      g_log_file:write("DXF Batch Processor\n\nFiles ...\n")
	   else
	      DisplayMessageBox("Failed to create log file\r\n\r\n" .. g_log_file_path)
          g_output_log_file = false
	   end 	
	end	

    local number_of_files = DirectoryProcessor(
	                                          job,
                                              g_base_directory, 
                                              g_file_filter, 
                                              g_process_sub_dirs, 
                                              ImportDxfFile
                                              )
    
    if g_output_log_file then
       g_log_file:write("Number of files = " .. number_of_files .. "\r\n")
	   g_log_file:close()
    end
	
    MessageBox(
              "Number of files processed = " .. number_of_files .. "\n" ..
              "\n" 
              )  
    
    
    return true    
end


g_DialogHtml = [[
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
"http://www.w3.org/TR/html4/loose.dtd">
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
<title>DXF Batch Processor</title>
<style type="text/css">
html {
	overflow: auto;
}
body {
	background-color: #efefef;
}
body, td, th {
	font-family: Arial, Helvetica, sans-serif;
	font-size: 12px;
}
.FormButton {
	font-weight: bold;
	width: 100%;
	font-family: Arial, Helvetica, sans-serif;
	font-size: 12px;
}
.h1 {
	font-size: 14px;
	font-weight: bold;
}
.h2 {
	font-size: 12px;
	font-weight: bold;
}
.ToolNameLabel {
	color: #555;
}
</style>
</head>

<body bgcolor="#efefef">

<table align="center" width="630" bgcolor="#efefef">
  <tr align="center">
    <td align="center">
	
    <img alt="" src="data:image/png;base64,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" />
  </tr>
 </table>
 

<table align="center" width="95%" border="0">

  <tr>
    <td colspan="3">This gadget loads all the DXF files from a specified directory and lays them out in a grid with user defined space between each file. This is commonly used when a number of DXF files are to be nested within the program </td>
  </tr>
  <tr><td colspan="3"><hr size="1" width="100%" /></td></tr> 

</table>

<table align="center" width="95%" border="0">
    <tr>
      <td colspan="3"><span class="DirectoryPicker">Directory to process: </span></td>
    </tr>
  <tr>
    <td height="30" colspan="3">&nbsp;&nbsp;
    <input name="DirNameEdit" type="text" id="DirNameEdit" size="55" maxlength="128">&nbsp;&nbsp;
    <input type="button" name="DirChooseButton"  id="DirChooseButton" value="Choose ..." CLASS="DirectoryPicker">
  </tr>
  <tr>
    <td colspan="3">
	    <table width="100%" border="0">
			<tr>
				<td width = "50%">
				&nbsp;&nbsp;<input type="checkbox" name="ProcessSubDirsCheck" id="ProcessSubDirsCheck" value="checkbox">
			   
				<span class="style1">      Process sub directories </span>
				</td>
				<td width = "50%">
				&nbsp;&nbsp;<input type="checkbox" name="CreateLogFileCheck" id="CreateLogFileCheck" value="checkbox">
			   
				<span class="style1">      Create log file </span>
				</td>
		
			</tr>
		</table>	
	</td>

  </tr>
  <tr>
    <td colspan="3"><table width="471" border="0">
      <tr>
        <td colspan="2"><span class="DirectoryPicker">Layout Control </span></td>
        <td width="145">&nbsp;</td>
      </tr>
      <tr>
        <td width="10">&nbsp;</td>
        <td width="302"><span class="style1">Number of drawings in a row </span></td>
        <td><input name="NumColumns" type="text" id="NumColumns" size="4" maxlength="4"></td>
      </tr>
      <tr>
        <td>&nbsp;</td>
        <td><span class="style1">Gap between drawings in X </span></td>
        <td><input name="BorderGapX" type="text" id="BorderGapX" size="8" maxlength="8"> <span id="Units1">inches</span></td>
      </tr>
      <tr>
        <td>&nbsp;</td>
        <td>Gap between rows in Y </td>
        <td><input name="BorderGapY" type="text" id="BorderGapY" size="8" maxlength="8"> <span id="Units2">inches</span></td>
      </tr>
    </table></td>
  </tr>

  <tr><td colspan="3"><hr size="1" width="100%" /></td></tr> 
  <tr>
    <td colspan="3">If no drawing is loaded when this gadget is run, a new blank drawing will be created to hold the data. The settings below control the size and origin for this new drawing.<br><br> 
    </td>
  </tr>
  <tr>
    <td colspan=3><strong>Drawing Dimensions </strong></td>
  </tr>
  <tr>
    <td colspan=3>
		<table width="100%" border="0">
		  <tr>
			<td>&nbsp;&nbsp;Drawing Width (X)</td>
			<td colspan="2"><input name="DrawingWidth" type="text" id="DrawingWidth" size="8" maxlength="8">
			  <span id="Units3">inches</span></td>
		  </tr>
		  <tr>
			<td>&nbsp;&nbsp;Drawing Height (Y) </td>
			<td colspan="2"><input name="DrawingHeight" type="text" id="DrawingHeight" size="8" maxlength="8">
			  <span id="Units4">inches</span></td>
		  </tr>
		  <tr>
			<td>&nbsp;&nbsp;Drawing Thickness (Z) </td>
			<td colspan="2"><input name="DrawingThickness" type="text" id="DrawingThickness" size="8" maxlength="8">
			  <span id="Units5">inches</span></td>
		  </tr>
        </table>
	</td>
  </tr>
  
  <tr>
    <td colspan=3>
	<table width="100%" border="0">
      <tr>
        <td width="20%">&nbsp;&nbsp;Units</td>
        <td width="80%">
		<table width="200">
      
            <td><label>
              <input type="radio" name="DrawingUnitsGroup" value="radio">
              inches</label></td>
        
            <td><label>
              <input type="radio" name="DrawingUnitsGroup" value="radio">
              mm</label></td>
      
        </table>
		</td>
      </tr>
    </table>
	</td>
    </tr>
  <tr>
    <td><strong>XY Drawing Origin</strong>&nbsp;</td>
	  <td>
      <table width="150" border="0" align="left">
        <tr>
          <td><div align="center">
              <input type="radio" name="DrawingOrigin">
          </div></td>
          <td><div align="center"><strong>----------------</strong></div></td>
          <td valign="top"><div align="center">
              <input type="radio" name="DrawingOrigin">
          </div></td>
        </tr>
        <tr>
          <td><div align="center"><strong>|</strong></div></td>
          <td><div align="center">
              <input type="radio" name="DrawingOrigin">
          </div></td>
          <td valign="top"><div align="center"><strong>|</strong></div></td>
        </tr>
        <tr>
          <td><div align="center">
              <input type="radio" name="DrawingOrigin">
          </div></td>
          <td><div align="center"><strong>----------------</strong></div></td>
          <td valign="top"><div align="center">
              <input type="radio" name="DrawingOrigin">
          </div></td>
        </tr>
      </table></td>
  </tr>

  <tr>
    <td ><strong>Z Origin&nbsp;</strong></td>
      <td>	
      <table width="298" align="left" border=0>
        <tr>
          <td><label>
            <input type="radio" name="MaterialZOrigin" value="radio">
            Z Origin on Material Surface (Top)</label></td>
        </tr>
        <tr>
          <td><label>
            <input type="radio" name="MaterialZOrigin" value="radio">
            Z Origin On Material Base (Bottom)</label></td>
        </tr>
    </table></td>
  </tr>
  <tr><td colspan="3"><hr size="1" width="100%" /></td></tr> 
    <tr><td colspan="3"><table width="100%" border="0">
      <tr>
        <td width="20%">&nbsp;</td>
        <td width="20%"><input name="ButtonOK" type="button" class="FormButton" id="ButtonOK" value="OK"></td>
        <td width="20%">&nbsp;</td>
        <td width="20%"><input name="ButtonCancel" type="button" class="FormButton" id="ButtonCancel" value="Cancel"></td>
        <td width="20%">&nbsp;</td>
      </tr>
    </table></td></tr> 

</table>

</body>
</html>

]]