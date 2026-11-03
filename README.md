# Omnifrota — kit de deploy Azure (PowerShell)

Gestão de insumos de veículos pesados (Django + MySQL + scikit-learn).

## Passo a passo
```powershell
git clone https://github.com/Chico7696/Omnifrota.git
cd Omnifrota
# extraia o kit aqui dentro (sobrescrevendo), depois:
Set-ExecutionPolicy -Scope Process Bypass
.\prepare_project.ps1
git add .
git commit -m "Add Azure deploy"
git push origin main
az login
.\deploy_azure.ps1
```

## Depois
- Logs: `az webapp log tail -g rg-omnifrota -n <app>`
- Republicar: `.\redeploy.ps1`
- Apagar tudo: `az group delete -n rg-omnifrota --yes`
