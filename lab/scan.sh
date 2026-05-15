#!/usr/bin/env bash
# Scan the pentest lab network from the lab-scanner container.
# Output XML is saved to lab/results/ and is compatible with GraphPent's nmap parser.
#
# Usage: bash lab/scan.sh [nmap-extra-args]
#   bash lab/scan.sh                          # full scan, XML + text output
#   bash lab/scan.sh --top-ports 100          # quick scan
#   bash lab/scan.sh -p 22,80,443,3306,6379   # specific ports

set -euo pipefail

SUBNET="172.30.0.0/24"
RESULTS_DIR="$(cd "$(dirname "$0")" && pwd)/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
XML_OUT="/results/scan_${TIMESTAMP}.xml"
TXT_OUT="/results/scan_${TIMESTAMP}.txt"

mkdir -p "$RESULTS_DIR"

# Check container is running
if ! docker inspect lab-scanner &>/dev/null; then
    echo "[!] lab-scanner container not found."
    echo "    Start the lab first: docker compose -f lab/docker-compose.yml up -d --build"
    exit 1
fi

echo "[*] Scanning $SUBNET ..."
echo "[*] Results → lab/results/scan_${TIMESTAMP}.{xml,txt}"

docker exec lab-scanner nmap \
    -sV -O \
    --top-ports 1000 \
    --version-intensity 5 \
    -T4 \
    "$@" \
    "$SUBNET" \
    -oX "$XML_OUT" \
    -oN "$TXT_OUT"

echo "[+] Done. XML saved to: lab/results/scan_${TIMESTAMP}.xml"
echo ""
echo "To import into GraphPent:"
echo "  cp lab/results/scan_${TIMESTAMP}.xml data/lab_scan.xml"
echo "  # then process via the existing nmap ingestor pipeline"
