[CmdletBinding()]
param(
    [string]$Container = "catastro_db_beta",
    [string]$Database = "avalix_db",
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\..\private_deploy"),
    [string]$Tag = (Get-Date -Format "yyyyMMdd"),
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$docker = Get-Command docker -ErrorAction Stop
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$artifactBase = "avalix_beta_supabase_reduced_pg15_$Tag"
$dumpPath = Join-Path $outputRoot "$artifactBase.backup"
$restoreListPath = Join-Path $outputRoot "$artifactBase.restore.list"
$containerDumpPath = "/tmp/$artifactBase.backup"

$excludedDataTables = @(
    "staging_predios",
    "appraisal_building_block",
    "appraisal_case",
    "appraisal_result",
    "appraisal_trace",
    "avaluo_auditoria",
    "avaluo_predio",
    "avaluo_construccion",
    "avaluo_unidad_ph",
    "predio_manual_data",
    "predio_superficie_override",
    "public_beta_consulta",
    "public_beta_contacto",
    "auditoria",
    "historial_geometria_predio",
    "solicitud_cambio"
)

if ((Test-Path -LiteralPath $dumpPath) -or (Test-Path -LiteralPath $restoreListPath)) {
    if (-not $Force) {
        throw "Ya existe un artefacto '$artifactBase'. Usa otro -Tag o -Force para reemplazarlo."
    }
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$running = (& $docker.Source inspect -f "{{.State.Running}}" $Container 2>$null | Out-String).Trim()
if ($running -ne "true") {
    throw "El contenedor '$Container' no esta ejecutandose."
}

$pgVersion = (& $docker.Source exec $Container pg_dump --version | Out-String).Trim()
if ($pgVersion -notmatch "PostgreSQL\) 15\.") {
    throw "Se esperaba pg_dump PostgreSQL 15 dentro del contenedor. Detectado: $pgVersion"
}

$dumpArguments = @(
    "exec",
    $Container,
    "pg_dump",
    "-U", "postgres",
    "-d", $Database,
    "--format=custom",
    "--schema=public",
    "--no-owner",
    "--no-privileges",
    "--file=$containerDumpPath"
)

foreach ($table in $excludedDataTables) {
    $dumpArguments += "--exclude-table-data=public.$table"
}

& $docker.Source @dumpArguments
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump no pudo generar el respaldo beta."
}

& $docker.Source cp "${Container}:$containerDumpPath" $dumpPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo copiar el respaldo fuera del contenedor."
}

$archiveList = @(& $docker.Source exec $Container pg_restore --list $containerDumpPath)
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo leer el contenido del respaldo beta."
}

$excludedPattern = "TABLE DATA public (" + (($excludedDataTables | ForEach-Object { [regex]::Escape($_) }) -join "|") + ") "
$unexpectedData = $archiveList | Where-Object { $_ -match $excludedPattern }
if ($unexpectedData) {
    throw "El respaldo contiene filas que debian quedar fuera de la beta."
}

# Supabase crea public previamente; estas dos entradas chocarian al restaurar.
$restoreList = $archiveList | ForEach-Object {
    if ($_ -match " SCHEMA - public " -or $_ -match " COMMENT - SCHEMA public ") {
        "; $_"
    }
    else {
        $_
    }
}
[System.IO.File]::WriteAllLines($restoreListPath, $restoreList)

$sizeMb = [math]::Round((Get-Item -LiteralPath $dumpPath).Length / 1MB, 2)
Write-Host "Respaldo beta generado correctamente."
Write-Host "Archivo: $dumpPath ($sizeMb MB)"
Write-Host "Lista de restauracion: $restoreListPath"
Write-Host "Datos excluidos: $($excludedDataTables -join ', ')"
Write-Host "Antes de restaurar en Supabase, habilita PostGIS en public y deshabilita Data API."
