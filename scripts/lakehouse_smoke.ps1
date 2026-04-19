param(
    [string]$ComposeFile = "docker/docker-compose.yml",
    [string]$MinioUser = "lakehouse",
    [string]$MinioPassword = "lakehouse123",
    [bool]$InsertSample = $true,
    [int]$InitTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

function Run-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    Write-Host "[RUN] $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Paso fallido: $Name (exit code $LASTEXITCODE)"
    }
    Write-Host "[OK ] $Name" -ForegroundColor Green
}

function Invoke-SparkSql {
    param([Parameter(Mandatory = $true)][string]$Sql)

    $args = @(
        "exec", "bmo_lakehouse_spark", "spark-sql",
        "--driver-memory", "512M",
        "--conf", "spark.sql.defaultCatalog=lakehouse",
        "--conf", "spark.sql.catalog.lakehouse=org.apache.iceberg.spark.SparkCatalog",
        "--conf", "spark.sql.catalog.lakehouse.type=rest",
        "--conf", "spark.sql.catalog.lakehouse.uri=http://rest:8181",
        "--conf", "spark.sql.catalog.lakehouse.warehouse=s3://warehouse/",
        "--conf", "spark.sql.catalog.lakehouse.io-impl=org.apache.iceberg.aws.s3.S3FileIO",
        "--conf", "spark.sql.catalog.lakehouse.s3.endpoint=http://minio:9000",
        "--conf", "spark.sql.catalog.lakehouse.s3.path-style-access=true",
        "--conf", "spark.sql.catalog.lakehouse.s3.access-key-id=$MinioUser",
        "--conf", "spark.sql.catalog.lakehouse.s3.secret-access-key=$MinioPassword",
        "--conf", "spark.hadoop.fs.s3a.endpoint=http://minio:9000",
        "--conf", "spark.hadoop.fs.s3a.access.key=$MinioUser",
        "--conf", "spark.hadoop.fs.s3a.secret.key=$MinioPassword",
        "--conf", "spark.hadoop.fs.s3a.path.style.access=true",
        "--conf", "spark.hadoop.fs.s3a.connection.ssl.enabled=false",
        "-e", $Sql
    )

    $prevErrorAction = $ErrorActionPreference
    try {
        # spark-sql puede escribir WARN en stderr aunque el comando sea exitoso.
        # Validamos errores reales usando exit code.
        $ErrorActionPreference = "Continue"
        $output = & docker @args 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prevErrorAction
    }

    if ($exitCode -ne 0) {
        throw "Error ejecutando Spark SQL: $Sql`n$output"
    }
    return ($output | Out-String)
}

Write-Host "== Lakehouse smoke test ==" -ForegroundColor Yellow
Write-Host "Compose file: $ComposeFile"

Run-Checked -Name "Compose up" -Command {
    docker compose -f $ComposeFile up -d
}

Run-Checked -Name "Compose ps" -Command {
    docker compose -f $ComposeFile ps
}

$deadline = (Get-Date).AddSeconds($InitTimeoutSeconds)
$minioInitState = ""
do {
    $minioInitState = (& docker inspect -f "{{.State.Status}}|{{.State.ExitCode}}" bmo_lakehouse_minio_init 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo inspeccionar bmo_lakehouse_minio_init: $minioInitState"
    }

    if ($minioInitState -eq "exited|0") {
        break
    }

    if ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
    }
} while ((Get-Date) -lt $deadline)

if ($minioInitState -ne "exited|0") {
    throw "bmo_lakehouse_minio_init no finalizo en exited|0 dentro de $InitTimeoutSeconds s. Estado actual: $minioInitState"
}
Write-Host "[OK ] minio-init finalizo correctamente: $minioInitState" -ForegroundColor Green

$initLogs = (& cmd /c "docker logs bmo_lakehouse_minio_init 2>&1" | Out-String)
if ($initLogs -notmatch "Buckets bronze/silver/gold/warehouse creados") {
    throw "No se encontro confirmacion de creacion de buckets en logs de minio-init"
}
Write-Host "[OK ] Buckets base detectados en logs de minio-init" -ForegroundColor Green

$restState = (& docker inspect -f "{{.State.Status}}" bmo_lakehouse_rest 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo inspeccionar bmo_lakehouse_rest: $restState"
}
if ($restState -ne "running") {
    throw "bmo_lakehouse_rest no esta running. Estado actual: $restState"
}
Write-Host "[OK ] Iceberg REST catalog en estado running" -ForegroundColor Green

[void](Invoke-SparkSql -Sql "CREATE NAMESPACE IF NOT EXISTS lakehouse.bronze;")
[void](Invoke-SparkSql -Sql "CREATE NAMESPACE IF NOT EXISTS lakehouse.silver;")
[void](Invoke-SparkSql -Sql "CREATE NAMESPACE IF NOT EXISTS lakehouse.gold;")
[void](Invoke-SparkSql -Sql "CREATE TABLE IF NOT EXISTS lakehouse.bronze.agent_events (event_id string, event_ts timestamp, source string, payload string) USING iceberg PARTITIONED BY (days(event_ts));")
Write-Host "[OK ] Bootstrap Iceberg aplicado (namespaces + tabla base)" -ForegroundColor Green

$namespaces = Invoke-SparkSql -Sql "SHOW NAMESPACES IN lakehouse"
if ($namespaces -notmatch "bronze" -or $namespaces -notmatch "silver" -or $namespaces -notmatch "gold") {
    throw "Namespaces esperados no encontrados. Salida:`n$namespaces"
}
Write-Host "[OK ] Namespaces lakehouse.bronze/silver/gold disponibles" -ForegroundColor Green

$tables = Invoke-SparkSql -Sql "SHOW TABLES IN lakehouse.bronze"
if ($tables -notmatch "agent_events") {
    throw "Tabla lakehouse.bronze.agent_events no encontrada. Salida:`n$tables"
}
Write-Host "[OK ] Tabla lakehouse.bronze.agent_events presente" -ForegroundColor Green

if ($InsertSample) {
    $insertSql = @"
INSERT INTO lakehouse.bronze.agent_events
VALUES
  ('evt-1', current_timestamp(), 'smoke', '{"ok":true}'),
  ('evt-2', current_timestamp(), 'smoke', '{"ok":true}');
"@
    [void](Invoke-SparkSql -Sql $insertSql)
    Write-Host "[OK ] Insercion de datos de smoke" -ForegroundColor Green

    $countOut = Invoke-SparkSql -Sql "SELECT count(*) AS total_rows FROM lakehouse.bronze.agent_events"
    $countMatches = [regex]::Matches($countOut, '(?m)^\s*([0-9]+)\s*$')
    $countValue = if ($countMatches.Count -gt 0) { [int]$countMatches[$countMatches.Count - 1].Groups[1].Value } else { 0 }
    if (($countOut -notmatch "total_rows" -and $countMatches.Count -eq 0) -or $countValue -le 0) {
        throw "No se pudo validar conteo > 0 en agent_events. Salida:`n$countOut"
    }
    Write-Host "[OK ] Conteo de filas validado" -ForegroundColor Green

    $snapshotsOut = Invoke-SparkSql -Sql "SELECT committed_at, operation FROM lakehouse.bronze.agent_events.snapshots ORDER BY committed_at DESC LIMIT 5"
    if ($snapshotsOut -notmatch "append|overwrite|replace|delete") {
        throw "No se pudo validar metadata de snapshots. Salida:`n$snapshotsOut"
    }
    Write-Host "[OK ] Metadata de snapshots accesible" -ForegroundColor Green

    $filesOut = Invoke-SparkSql -Sql "SELECT file_path, record_count FROM lakehouse.bronze.agent_events.files LIMIT 5"
    if ($filesOut -notmatch "s3://warehouse/|s3a://warehouse/|\.parquet") {
        throw "No se pudo validar metadata de archivos. Salida:`n$filesOut"
    }
    Write-Host "[OK ] Metadata de archivos accesible" -ForegroundColor Green
}

Write-Host "== Smoke test finalizado correctamente ==" -ForegroundColor Yellow
