$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = Join-Path $root "out"

if (-not (Test-Path $outDir)) {
    throw "No existe $outDir. Ejecuta primero ./build.ps1"
}

java -cp $outDir broker.BrokerServerMain --host 127.0.0.1 --port 1099 --bind BrokerService
