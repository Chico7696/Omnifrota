\xEF\xBB\xBF# Republica o último commit no App Service criado pelo deploy_azure.ps1
$ErrorActionPreference = "Stop"
if (-not (Test-Path ".azure-omnifrota.json")) { throw "Arquivo .azure-omnifrota.json não encontrado. Rode antes o deploy_azure.ps1." }
$cfg = Get-Content ".azure-omnifrota.json" -Raw | ConvertFrom-Json
if (git status --porcelain) { Write-Warning "Há alterações não commitadas; elas não serão enviadas." }
git archive --format=zip -o deploy.zip HEAD
if ($LASTEXITCODE -ne 0) { throw "git archive falhou" }
az webapp deploy -g $cfg.rg -n $cfg.app --type zip --src-path (Resolve-Path "deploy.zip").Path
if ($LASTEXITCODE -ne 0) { throw "Deploy falhou" }
Remove-Item deploy.zip -ErrorAction SilentlyContinue
Write-Host "Publicado: https://$($cfg.app).azurewebsites.net" -ForegroundColor Green
