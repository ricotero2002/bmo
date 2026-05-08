param(
    [string]$ComposeFile = "docker/docker-compose.yml",
    [bool]$InsertSample = $true,
    [int]$InitTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

if (Test-Path ".env") {
    Get-Content ".env" | Foreach-Object {
        if ($_ -match '^(?!#)([^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
        }
    }
}

$OciAccessKey = [Environment]::GetEnvironmentVariable("OCI_ACCESS_KEY")
$OciSecretKey = [Environment]::GetEnvironmentVariable("OCI_SECRET_KEY")
$OciNamespace = [Environment]::GetEnvironmentVariable("OCI_NAMESPACE")
$OciRegion = [Environment]::GetEnvironmentVariable("OCI_REGION")
$OciBucketName = [Environment]::GetEnvironmentVariable("OCI_BUCKET_NAME")

$OciEndpoint = "https://$OciNamespace.compat.objectstorage.$OciRegion.oraclecloud.com"

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
        "exec", "-i", "-n", "personal-ai", "deploy/spark-thrift", "--", "/opt/spark/bin/spark-sql",
        "--driver-memory", "512M",
        "--conf", "spark.sql.defaultCatalog=lakehouse",
        "--conf", "spark.sql.catalog.lakehouse=org.apache.iceberg.spark.SparkCatalog",
        "--conf", "spark.sql.catalog.lakehouse.type=rest",
        "--conf", "spark.sql.catalog.lakehouse.uri=http://iceberg-rest-svc.personal-ai.svc.cluster.local:8181",
        "--conf", "spark.sql.catalog.lakehouse.warehouse=s3://$OciBucketName/",
        "--conf", "spark.sql.catalog.lakehouse.io-impl=org.apache.iceberg.aws.s3.S3FileIO",
        "--conf", "spark.sql.catalog.lakehouse.s3.endpoint=$OciEndpoint",
        "--conf", "spark.sql.catalog.lakehouse.client.region=$OciRegion",
        "--conf", "spark.sql.catalog.lakehouse.s3.path-style-access=true",
        "--conf", "spark.sql.catalog.lakehouse.s3.access-key-id=$OciAccessKey",
        "--conf", "spark.sql.catalog.lakehouse.s3.secret-access-key=$OciSecretKey",
        "--conf", "spark.hadoop.fs.s3a.endpoint=$OciEndpoint",
        "--conf", "spark.hadoop.fs.s3a.access.key=$OciAccessKey",
        "--conf", "spark.hadoop.fs.s3a.secret.key=$OciSecretKey",
        "--conf", "spark.hadoop.fs.s3a.path.style.access=true",
        "--conf", "spark.hadoop.fs.s3a.connection.ssl.enabled=true",
        "-e", $Sql
    )

    $prevErrorAction = $ErrorActionPreference
    try {
        # spark-sql puede escribir WARN en stderr aunque el comando sea exitoso.
        # Validamos errores reales usando exit code.
        $ErrorActionPreference = "Continue"
        $output = & kubectl @args 2>&1
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
Write-Host "Verificando base de datos a traves de Kubernetes..." -ForegroundColor Cyan

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
    if ($filesOut -notmatch "s3://$OciBucketName/|\.parquet") {
        throw "No se pudo validar metadata de archivos. Salida:`n$filesOut"
    }
    Write-Host "[OK ] Metadata de archivos accesible" -ForegroundColor Green
}

Write-Host "== Smoke test finalizado correctamente ==" -ForegroundColor Yellow
