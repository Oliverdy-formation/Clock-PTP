# Clock-PTP
Une horloge PTP sans GPS pour ton PC Linux, ton M4250 et ton KAIROS, à tester sur ton matériel.

1. Il faut LinuxPTP **4.4 minimum** et une carte réseau avec horodatage matériel PTP.
2. Branche le PC et l’interface PTP du KAIROS sur le même VLAN, sans autre horloge maître.
3. [Installe les fichiers sur le PC Linux](docs/INSTALLATION.md#installation-sur-le-mini-pc).
4. Dans `/etc/default/clock-ptp`, remplace `CHANGE_ME` par ton interface réseau, visible avec `ip -br link`.
5. Dans KAIROS, sélectionne la bonne interface PTP et le **domaine 127**.
6. Lance `sudo systemctl daemon-reload`, puis `sudo systemctl start clock-ptp` ; vérifie que KAIROS suit l’horloge du PC.
7. Si tout fonctionne : `sudo systemctl enable clock-ptp`. Sinon : `sudo journalctl -u clock-ptp -b`.
