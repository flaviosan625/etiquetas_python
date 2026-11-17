$ErrorActionPreference = "SilentlyContinue"

# Fechar processos antigos de python do etiquetas_python
Get-Process python, pythonw | Where-Object { $_.Path -like "*etiquetas_python*" } | Stop-Process -Force

# Atualizar atalho na Área de Trabalho com pythonw.exe
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Automacao Grafica - Pro 2.0.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($shortcutPath)
$sc.TargetPath = "C:\Users\flavi\Desktop\etiquetas_python\.venv\Scripts\pythonw.exe"
$sc.Arguments = "-m ui.app"
$sc.WorkingDirectory = "C:\Users\flavi\Desktop\etiquetas_python"
$sc.Description = "Sistema Integrado de Pré-Impressão e Corte CNC - Pro 2.0"
$sc.Save()

# Iniciar aplicação com pythonw desacoplado
$proc = Start-Process -FilePath "C:\Users\flavi\Desktop\etiquetas_python\.venv\Scripts\pythonw.exe" -ArgumentList "-m ui.app" -WorkingDirectory "C:\Users\flavi\Desktop\etiquetas_python" -PassThru
Start-Sleep -Seconds 2
Write-Host "Iniciado com sucesso! PID: $($proc.Id), Exited: $($proc.HasExited)"
