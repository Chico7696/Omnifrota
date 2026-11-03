\xEF\xBB\xBF# Prepara o repo Omnifrota para produção na Azure.
# Uso (na raiz do repo clonado):  .\prepare_project.ps1
$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)

foreach ($f in @("manage.py", "requirements.txt", "omnifrota\settings.py", "omnifrota\wsgi.py")) {
    if (-not (Test-Path $f)) { throw "Arquivo '$f' não encontrado. Rode este script na raiz do repo Omnifrota." }
}

# 1) requirements.txt
$req = [System.IO.File]::ReadAllText((Resolve-Path "requirements.txt"))
$add = ""
if ($req -notmatch "(?im)^gunicorn")   { $add += "gunicorn>=23.0`n" }
if ($req -notmatch "(?im)^whitenoise") { $add += "whitenoise>=6.9`n" }
if ($add) {
    if (-not $req.EndsWith("`n")) { $add = "`n" + $add }
    [System.IO.File]::AppendAllText((Resolve-Path "requirements.txt"), $add, $utf8)
    Write-Host "requirements.txt atualizado."
} else { Write-Host "requirements.txt já tem gunicorn e whitenoise." }

# 2) settings.py
$settingsPath = (Resolve-Path "omnifrota\settings.py").Path
$settings = [System.IO.File]::ReadAllText($settingsPath)
if ($settings -match "Producao \(Azure\)") {
    Write-Host "settings.py já está preparado."
} else {
    $block = @'


# ---- Producao (Azure) ----
import os

if os.environ.get("DJANGO_SECRET_KEY"):
    SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
if "DJANGO_DEBUG" in os.environ:
    DEBUG = os.environ["DJANGO_DEBUG"] == "1"
if os.environ.get("DJANGO_ALLOWED_HOSTS"):
    ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")
if os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS"):
    CSRF_TRUSTED_ORIGINS = os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"].split(",")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if os.environ.get("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ["DB_USER"],
            "PASSWORD": os.environ["DB_PASSWORD"],
            "HOST": os.environ["DB_HOST"],
            "PORT": os.environ.get("DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                **({"ssl_mode": "REQUIRED"} if os.environ.get("DB_SSL", "1") == "1" else {}),
            },
        }
    }

_ws = "whitenoise.middleware.WhiteNoiseMiddleware"
if _ws not in MIDDLEWARE:
    MIDDLEWARE.insert(1, _ws)

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
'@
    $block = $block -replace "`r`n", "`n"
    [System.IO.File]::AppendAllText($settingsPath, $block, $utf8)
    Write-Host "settings.py atualizado."
}

# 3) .gitignore não pode excluir os modelos .joblib
if (Test-Path ".gitignore") {
    $hit = Select-String -Path ".gitignore" -Pattern "joblib" -SimpleMatch
    if ($hit) { Write-Warning ".gitignore menciona 'joblib' (linha $($hit[0].LineNumber)). Remova se os modelos precisam ir para a Azure." }
}

Write-Host "`nPronto. Próximo passo:  git add . ; git commit -m 'Add Azure deploy' ; git push origin main ; .\deploy_azure.ps1"
