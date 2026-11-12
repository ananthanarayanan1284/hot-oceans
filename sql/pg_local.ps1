# Private PostgreSQL + PostGIS database for this project (data\pgdata, port 5433, localhost only, no password).
# Uses the PostgreSQL 13 / PostGIS 3.4 programs in D:\Application; the main PostgreSQL service is not touched.
#   powershell -ExecutionPolicy Bypass -File sql\pg_local.ps1 init     # once: create the database
#   powershell -ExecutionPolicy Bypass -File sql\pg_local.ps1 start    # after a restart of the PC
#   powershell -ExecutionPolicy Bypass -File sql\pg_local.ps1 stop
#   powershell -ExecutionPolicy Bypass -File sql\pg_local.ps1 status
#   powershell -ExecutionPolicy Bypass -File sql\pg_local.ps1 psql     # open an SQL prompt
param([ValidateSet("init", "start", "stop", "status", "psql")][string]$Action = "status")
$bin = "D:\Application\bin"
$pgdata = Join-Path (Split-Path $PSScriptRoot -Parent) "data\pgdata"
$port = 5433

switch ($Action) {
    "init" {
        if (Test-Path (Join-Path $pgdata "PG_VERSION")) { "already initialised: $pgdata"; break }
        & "$bin\initdb.exe" -D $pgdata -U hot -A trust -E UTF8 --locale=C | Out-Null
        Add-Content -Path (Join-Path $pgdata "postgresql.conf") -Encoding ascii -Value "`nport = $port`nlisten_addresses = 'localhost'"
        & "$bin\pg_ctl.exe" -D $pgdata -l (Join-Path $pgdata "server.log") -w start
        & "$bin\psql.exe" -h localhost -p $port -U hot -d postgres -c "CREATE DATABASE hot_oceans"
        & "$bin\psql.exe" -h localhost -p $port -U hot -d hot_oceans -c "CREATE EXTENSION postgis" -c "SELECT postgis_full_version()"
    }
    "start"  { & "$bin\pg_ctl.exe" -D $pgdata -l (Join-Path $pgdata "server.log") -w start }
    "stop"   { & "$bin\pg_ctl.exe" -D $pgdata -w stop }
    "status" { & "$bin\pg_ctl.exe" -D $pgdata status }
    "psql"   { & "$bin\psql.exe" -h localhost -p $port -U hot -d hot_oceans }
}
