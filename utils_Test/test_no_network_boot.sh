#!/usr/bin/env bash
# Test "no SIM / no network" boot behaviour without physically removing the SIM.
# Run on the device over SSH: ./scripts/test_no_network_boot.sh [check|fallback|simulate-reboot]
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

usage() {
    echo "Usage: $0 [check|fallback|simulate-reboot]"
    echo ""
    echo "  check           Verify unit files (no reboot, no service changes)"
    echo "  fallback        Test fallback timer: stop app, run fallback, confirm app starts"
    echo "  simulate-reboot (optional) Mask network-wait-online and reboot to test no-network boot (RISKY: may lose SSH)"
    echo ""
    echo "Run without args: same as 'check'"
}

cmd="${1:-check}"

case "$cmd" in
    check)
        echo -e "${BLUE}[CHECK] Verifying configuration (no reboot, no service stop)...${NC}"
        ok=0
        if [ -f /etc/systemd/system/azure-iot.service ]; then
            if grep -q 'network-online.target' /etc/systemd/system/azure-iot.service; then
                echo -e "${RED}  FAIL: azure-iot.service still references network-online.target (will block without SIM)${NC}"
            else
                echo -e "${GREEN}  OK: azure-iot.service does not wait for network-online${NC}"
                ok=$((ok+1))
            fi
        else
            echo -e "${YELLOW}  SKIP: azure-iot.service not installed${NC}"
        fi
        if systemctl is-enabled --quiet nexusrfid-start-fallback.timer 2>/dev/null; then
            echo -e "${GREEN}  OK: nexusrfid-start-fallback.timer is enabled${NC}"
            ok=$((ok+1))
        else
            echo -e "${RED}  FAIL: nexusrfid-start-fallback.timer not enabled${NC}"
        fi
        if [ -f /etc/systemd/system/nexusrfid.service ]; then
            # Only fail if a dependency line (After/Wants/Requires) references network-online, not comments
            if grep -E '^\s*(After|Wants|Requires)=' /etc/systemd/system/nexusrfid.service | grep -q 'network-online'; then
                echo -e "${RED}  FAIL: nexusrfid.service references network-online in After/Wants/Requires${NC}"
            else
                echo -e "${GREEN}  OK: nexusrfid.service does not wait for network-online${NC}"
                ok=$((ok+1))
            fi
        fi
        echo ""
        echo -e "${BLUE}Summary: run 'fallback' to test that the app starts when the fallback runs.${NC}"
        ;;
    fallback)
        echo -e "${BLUE}[FALLBACK] Testing fallback start (app will be stopped then restarted by fallback)...${NC}"
        if [ ! -f /etc/systemd/system/nexusrfid.service ]; then
            echo -e "${RED}nexusrfid.service not found (no unit file). Install the service first.${NC}"
            exit 1
        fi
        echo "Stopping nexusrfid.service..."
        sudo systemctl stop nexusrfid.service 2>/dev/null || true
        sleep 2
        if systemctl is-active --quiet nexusrfid.service; then
            echo -e "${RED}Could not stop nexusrfid.service${NC}"
            exit 1
        fi
        echo -e "${GREEN}App stopped. Running fallback (nexusrfid-start-fallback.service)...${NC}"
        sudo systemctl start nexusrfid-start-fallback.service
        # nexusrfid has ExecStartPre (dhclient + sleep 2), so allow up to 15s for it to become active
        echo "Waiting for nexusrfid.service to become active (up to 15s)..."
        for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
            sleep 1
            if systemctl is-active --quiet nexusrfid.service; then
                echo -e "${GREEN}SUCCESS: Fallback started the app; nexusrfid.service is running.${NC}"
                exit 0
            fi
        done
        echo -e "${RED}FAIL: App did not start within 15s. Check: systemctl status nexusrfid.service${NC}"
        exit 1
        ;;
    simulate-reboot)
        echo -e "${YELLOW}[SIMULATE-REBOOT] This will mask the service that provides network-online.target and REBOOT.${NC}"
        echo -e "${YELLOW}After reboot, the system will behave like 'no network at boot' for a while.${NC}"
        echo -e "${RED}WARNING: If you have only one way to reach the device (e.g. SSH over WiFi), you may lose access until network comes up or you get physical access.${NC}"
        echo ""
        read -p "Type 'yes' to continue: " confirm
        if [ "$confirm" != "yes" ]; then
            echo "Aborted."
            exit 0
        fi
        # Mask the service that makes network-online.target active (common names)
        for svc in NetworkManager-wait-online.service systemd-networkd-wait-online.service; do
            if systemctl list-unit-files --type=service | grep -q "$svc"; then
                echo "Masking $svc so network-online.target is not reached at next boot..."
                sudo systemctl mask "$svc" 2>/dev/null || true
            fi
        done
        echo "Rebooting in 10 seconds (Ctrl+C to cancel)..."
        sleep 10
        sudo reboot
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo -e "${RED}Unknown command: $cmd${NC}"
        usage
        exit 1
        ;;
esac
