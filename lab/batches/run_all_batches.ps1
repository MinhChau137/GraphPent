# run_all_batches.ps1 — Windows PowerShell version
# Run from the project root: .\lab\batches\run_all_batches.ps1
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResultsDir = "$ScriptDir\..\results"
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

Write-Host "━━━━━━ Batch 01/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_01.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.10 172.30.1.20 172.30.1.30 172.30.1.40 172.30.1.1 -oX /results/batch_01.xml
Write-Host "  [+] Results saved to results/batch_01.xml"
docker compose -f $ScriptDir\batch_01.yml down

Write-Host "━━━━━━ Batch 02/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_02.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.50 172.30.1.51 172.30.1.52 172.30.1.53 172.30.1.54 -oX /results/batch_02.xml
Write-Host "  [+] Results saved to results/batch_02.xml"
docker compose -f $ScriptDir\batch_02.yml down

Write-Host "━━━━━━ Batch 03/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_03.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.55 172.30.1.56 172.30.1.57 172.30.1.58 172.30.1.59 -oX /results/batch_03.xml
Write-Host "  [+] Results saved to results/batch_03.xml"
docker compose -f $ScriptDir\batch_03.yml down

Write-Host "━━━━━━ Batch 04/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_04.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.60 172.30.1.61 172.30.1.62 172.30.1.63 172.30.1.64 -oX /results/batch_04.xml
Write-Host "  [+] Results saved to results/batch_04.xml"
docker compose -f $ScriptDir\batch_04.yml down

Write-Host "━━━━━━ Batch 05/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_05.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.65 172.30.1.66 172.30.1.67 172.30.1.68 172.30.1.69 -oX /results/batch_05.xml
Write-Host "  [+] Results saved to results/batch_05.xml"
docker compose -f $ScriptDir\batch_05.yml down

Write-Host "━━━━━━ Batch 06/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_06.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.70 172.30.1.71 172.30.1.72 172.30.1.73 172.30.1.74 -oX /results/batch_06.xml
Write-Host "  [+] Results saved to results/batch_06.xml"
docker compose -f $ScriptDir\batch_06.yml down

Write-Host "━━━━━━ Batch 07/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_07.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.75 172.30.1.76 172.30.1.77 172.30.1.78 172.30.1.79 -oX /results/batch_07.xml
Write-Host "  [+] Results saved to results/batch_07.xml"
docker compose -f $ScriptDir\batch_07.yml down

Write-Host "━━━━━━ Batch 08/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_08.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.80 172.30.1.81 172.30.1.82 172.30.1.83 172.30.1.84 -oX /results/batch_08.xml
Write-Host "  [+] Results saved to results/batch_08.xml"
docker compose -f $ScriptDir\batch_08.yml down

Write-Host "━━━━━━ Batch 09/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_09.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.85 172.30.1.86 172.30.1.87 172.30.1.88 172.30.1.89 -oX /results/batch_09.xml
Write-Host "  [+] Results saved to results/batch_09.xml"
docker compose -f $ScriptDir\batch_09.yml down

Write-Host "━━━━━━ Batch 10/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_10.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.90 172.30.1.91 172.30.1.92 172.30.1.93 172.30.1.94 -oX /results/batch_10.xml
Write-Host "  [+] Results saved to results/batch_10.xml"
docker compose -f $ScriptDir\batch_10.yml down

Write-Host "━━━━━━ Batch 11/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_11.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.1.95 172.30.1.96 172.30.1.97 172.30.1.98 172.30.1.99 -oX /results/batch_11.xml
Write-Host "  [+] Results saved to results/batch_11.xml"
docker compose -f $ScriptDir\batch_11.yml down

Write-Host "━━━━━━ Batch 12/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_12.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.1 172.30.2.2 172.30.2.3 172.30.2.4 172.30.2.5 -oX /results/batch_12.xml
Write-Host "  [+] Results saved to results/batch_12.xml"
docker compose -f $ScriptDir\batch_12.yml down

Write-Host "━━━━━━ Batch 13/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_13.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.6 172.30.2.7 172.30.2.8 172.30.2.9 172.30.2.10 -oX /results/batch_13.xml
Write-Host "  [+] Results saved to results/batch_13.xml"
docker compose -f $ScriptDir\batch_13.yml down

Write-Host "━━━━━━ Batch 14/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_14.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.11 172.30.2.12 172.30.2.13 172.30.2.14 172.30.2.15 -oX /results/batch_14.xml
Write-Host "  [+] Results saved to results/batch_14.xml"
docker compose -f $ScriptDir\batch_14.yml down

Write-Host "━━━━━━ Batch 15/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_15.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.16 172.30.2.17 172.30.2.18 172.30.2.19 172.30.2.20 -oX /results/batch_15.xml
Write-Host "  [+] Results saved to results/batch_15.xml"
docker compose -f $ScriptDir\batch_15.yml down

Write-Host "━━━━━━ Batch 16/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_16.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.21 172.30.2.22 172.30.2.23 172.30.2.24 172.30.2.25 -oX /results/batch_16.xml
Write-Host "  [+] Results saved to results/batch_16.xml"
docker compose -f $ScriptDir\batch_16.yml down

Write-Host "━━━━━━ Batch 17/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_17.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.26 172.30.2.27 172.30.2.28 172.30.2.29 172.30.2.30 -oX /results/batch_17.xml
Write-Host "  [+] Results saved to results/batch_17.xml"
docker compose -f $ScriptDir\batch_17.yml down

Write-Host "━━━━━━ Batch 18/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_18.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.31 172.30.2.32 172.30.2.33 172.30.2.34 172.30.2.35 -oX /results/batch_18.xml
Write-Host "  [+] Results saved to results/batch_18.xml"
docker compose -f $ScriptDir\batch_18.yml down

Write-Host "━━━━━━ Batch 19/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_19.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.36 172.30.2.37 172.30.2.38 172.30.2.39 172.30.2.40 -oX /results/batch_19.xml
Write-Host "  [+] Results saved to results/batch_19.xml"
docker compose -f $ScriptDir\batch_19.yml down

Write-Host "━━━━━━ Batch 20/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_20.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.41 172.30.2.42 172.30.2.43 172.30.2.44 172.30.2.45 -oX /results/batch_20.xml
Write-Host "  [+] Results saved to results/batch_20.xml"
docker compose -f $ScriptDir\batch_20.yml down

Write-Host "━━━━━━ Batch 21/21: 5 hosts ━━━━━━"
docker compose -f $ScriptDir\batch_21.yml up -d --build
Write-Host "  [*] Waiting for services..."
Start-Sleep -Seconds 15
Write-Host "  [*] Scanning..."
docker exec lab-scanner nmap -sV -O -p 21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,1521,3306,3389,5432,5900,6379,8080,8443,8888,27017 -T4 172.30.2.46 172.30.2.47 172.30.2.48 172.30.2.49 172.30.2.50 -oX /results/batch_21.xml
Write-Host "  [+] Results saved to results/batch_21.xml"
docker compose -f $ScriptDir\batch_21.yml down

Write-Host "━━━━━━ All batches done ━━━━━━"