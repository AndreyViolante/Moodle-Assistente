<#
.SYNOPSIS
    Faz o Assistente Moodle abrir junto com o Windows.

.DESCRIPTION
    Cria um atalho na pasta Inicializar apontando pro app.py, usando o pythonw
    (que abre so a janela, sem console).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File instalar_atalho.ps1
    powershell -ExecutionPolicy Bypass -File instalar_atalho.ps1 -Remover
#>
param([switch]$Remover)

$pasta  = Split-Path -Parent $MyInvocation.MyCommand.Path
$atalho = Join-Path ([Environment]::GetFolderPath('Startup')) 'Assistente Moodle.lnk'

if ($Remover) {
    if (Test-Path $atalho) {
        Remove-Item $atalho -Force
        Write-Host "Removido: o assistente nao abre mais com o Windows." -ForegroundColor Yellow
    } else {
        Write-Host "Nao havia atalho pra remover."
    }
    return
}

$pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    Write-Host "Nao achei o pythonw. Instale o Python e marque 'Add to PATH'." -ForegroundColor Red
    exit 1
}

$app = Join-Path $pasta 'app.py'
if (-not (Test-Path $app)) {
    Write-Host "Nao achei o app.py em $pasta" -ForegroundColor Red
    exit 1
}

$s = (New-Object -ComObject WScript.Shell).CreateShortcut($atalho)
$s.TargetPath       = $pythonw
$s.Arguments        = '"' + $app + '"'
$s.WorkingDirectory = $pasta
$s.Description      = 'Assistente Moodle - abre com o Windows'
$icone = Join-Path $pasta 'icone.ico'
if (Test-Path $icone) { $s.IconLocation = $icone }
$s.Save()

Write-Host "Pronto! O assistente vai abrir junto com o Windows." -ForegroundColor Green
Write-Host "Atalho criado em: $atalho"
Write-Host "Pra desfazer: powershell -ExecutionPolicy Bypass -File instalar_atalho.ps1 -Remover"
