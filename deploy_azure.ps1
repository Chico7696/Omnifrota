\xEF\xBB\xBF# Deploy do Omnifrota na Azure (sem Docker) em camadas gratuitas:
#   App Service F1 (Linux, Python nativo) + MySQL Flexible Server B1ms (12 meses grátis em conta free).
# Uso (na raiz do repo, com tudo commitado):
#   Set-ExecutionPolicy -Scope Process Bypass
#   az login
#   .\deploy_azure.ps1
param(
    [string]$Location = "brazilsouth",     # se faltar quota/SKU, use eastus2
    [string]$Runtime  = "PYTHON:3.13",     # confira: az webapp list-runtimes --os linux
    [string]$Suffix   = (Get-Random -Minimum 10000 -Maximum 99999)
)
$ErrorActionPreference = "Stop"

function Az {
    & az @args
    if ($LASTEXITCODE -ne 0) { throw "Falha em: az $($args -join ' ')" }
}
function New-RandomString([int]$Length) {
    $chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

$RG      = "rg-omnifrota"
$Plan    = "plan-omnifrota"
$App     = "omnifrota-$Suffix"
$Mysql   = "mysql-omnifrota-$Suffix"
$DbName  = "omnifrota"
$DbUser  = "omniadmin"
$DbPass  = (New-RandomString 24) + "Aa1"
$Secret  = New-RandomString 60

# Pré-checagens
if (-not (Get-Command az  -ErrorAction SilentlyContinue)) { throw "Azure CLI não encontrado." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git não encontrado." }
if (-not (Test-Path "manage.py")) { throw "Rode na raiz do repo (onde está o manage.py)." }
if (git status --porcelain) { Write-Warning "Há alterações não commitadas. Elas NÃO irão para a Azure (o deploy usa o último commit)." }

Write-Host ">> Assinatura em uso:"
Az account show --query "{nome:name,id:id}" -o table
$ok = Read-Host "É a assinatura da conta gratuita (Free Trial)? [s/N]"
if ($ok -notmatch '^[sS]$') { Write-Host "Troque com: az account set --subscription <id>"; exit 1 }

Az group create -n $RG -l $Location -o none

Write-Host ">> MySQL Flexible Server (pode levar alguns minutos)"
Az mysql flexible-server create -g $RG -n $Mysql -l $Location `
    --admin-user $DbUser --admin-password $DbPass `
    --sku-name Standard_B1ms --tier Burstable --storage-size 32 `
    --public-access 0.0.0.0 --yes -o none
Az mysql flexible-server db create -g $RG -s $Mysql -d $DbName -o none
$DbHost = "$Mysql.mysql.database.azure.com"

Write-Host ">> App Service F1 gratuito (Linux, Python nativo)"
Az appservice plan create -g $RG -n $Plan --is-linux --sku F1 -o none
Az webapp create -g $RG -p $Plan -n $App --runtime $Runtime -o none

Az webapp config appsettings set -g $RG -n $App -o none --settings `
    "SCM_DO_BUILD_DURING_DEPLOYMENT=true" `
    "DJANGO_SECRET_KEY=$Secret" "DJANGO_DEBUG=0" `
    "DJANGO_ALLOWED_HOSTS=$App.azurewebsites.net" `
    "DJANGO_CSRF_TRUSTED_ORIGINS=https://$App.azurewebsites.net" `
    "DB_NAME=$DbName" "DB_USER=$DbUser" "DB_PASSWORD=$DbPass" `
    "DB_HOST=$DbHost" "DB_PORT=3306" "DB_SSL=1"

Az webapp config set -g $RG -n $App --startup-file "startup.sh" -o none

Write-Host ">> Enviando o código (git archive usa o último commit e respeita o .gitignore)"
Az webapp deploy -g $RG -n $App --type zip --src-path (& {
    git archive --format=zip -o deploy.zip HEAD
    if ($LASTEXITCODE -ne 0) { throw "git archive falhou" }
    (Resolve-Path "deploy.zip").Path
})
Remove-Item deploy.zip -ErrorAction SilentlyContinue

# Guarda os nomes para o redeploy
@{ rg = $RG; app = $App } | ConvertTo-Json | Set-Content ".azure-omnifrota.json"

Write-Host ""
Write-Host "Pronto: https://$App.azurewebsites.net" -ForegroundColor Green
Write-Host "Resource group: $RG | App: $App | MySQL: $Mysql"
Write-Host "Senha do banco (guarde; também está nas App Settings): $DbPass"
Write-Host "Logs:    az webapp log tail -g $RG -n $App"
Write-Host "Redeploy: .\redeploy.ps1"
