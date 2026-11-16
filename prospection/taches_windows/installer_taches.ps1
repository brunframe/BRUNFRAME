# BRUNFRAME — tâches planifiées Windows (à lancer UNE fois, après validation du mode --test).
#   Clic droit > Exécuter avec PowerShell, ou :
#   powershell -ExecutionPolicy Bypass -File taches_windows\installer_taches.ps1
# Pour tout retirer : powershell -ExecutionPolicy Bypass -File taches_windows\installer_taches.ps1 -Retirer

param([switch]$Retirer)

$dossier = Split-Path -Parent $PSScriptRoot          # ...\prospection
$python  = Join-Path $dossier ".venv\Scripts\python.exe"
$semaine = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

$taches = @(
  @{ Nom = "BRUNFRAME 1 Liste noire";     Script = "liste_noire.py";            Declencheur = (New-ScheduledTaskTrigger -Daily -At "06:00") },
  @{ Nom = "BRUNFRAME 2 Rafraichir";      Script = "prospects.py --rafraichir"; Declencheur = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "17:30") },
  @{ Nom = "BRUNFRAME 3 Prospects";       Script = "prospects.py";              Declencheur = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "18:00") },
  @{ Nom = "BRUNFRAME 4 Maquettes";       Script = "maquette.py";               Declencheur = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $semaine -At "06:30") },
  @{ Nom = "BRUNFRAME 5 Appels du jour";  Script = "appels_du_jour.py";         Declencheur = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $semaine -At "07:00") }
)

if ($Retirer) {
  foreach ($t in $taches) { Unregister-ScheduledTask -TaskName $t.Nom -Confirm:$false -ErrorAction SilentlyContinue; Write-Host "retirée : $($t.Nom)" }
  exit 0
}

if (-not (Test-Path $python)) { Write-Error "Python du projet introuvable : $python (voir README, étape Installation)"; exit 1 }

# StartWhenAvailable : si le PC était éteint à l'heure prévue, la tâche part dès qu'il est allumé.
$reglages = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

foreach ($t in $taches) {
  $action = New-ScheduledTaskAction -Execute $python -Argument $t.Script -WorkingDirectory $dossier
  Register-ScheduledTask -TaskName $t.Nom -Action $action -Trigger $t.Declencheur -Settings $reglages `
    -Description "BRUNFRAME prospection : $($t.Script)" -Force | Out-Null
  Write-Host "OK  $($t.Nom)  ->  $($t.Script)"
}
Write-Host ""
Write-Host "Les tâches tournent quand votre session Windows est ouverte (PC allumé, session non fermée)."
Write-Host "Journal de chaque exécution : $dossier\logs\"
