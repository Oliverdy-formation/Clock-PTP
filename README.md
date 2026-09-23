```bash
sudo apt install linuxptp ethtool iproute2 procps python3 && ptp4l -v # LinuxPTP 4.4 minimum
sudo install -Dm644 fichier_config.txt /etc/clock-ptp/ptp4l.conf # KAIROS : domaine 127, un seul maître
sudo install -Dm644 scripts/clock_ptp.py /usr/local/lib/clock-ptp/clock_ptp.py # Lanceur
sudo install -m644 systemd/clock-ptp.example /etc/default/clock-ptp && ip -br link && sudo nano /etc/default/clock-ptp # Remplacer CHANGE_ME par l'interface
sudo install -m644 systemd/clock-ptp.service /etc/systemd/system/clock-ptp.service # Service
sudo systemctl daemon-reload && sudo systemctl start clock-ptp # Démarrer
sudo journalctl -u clock-ptp -b # Voir les erreurs
sudo systemctl enable clock-ptp # Démarrage automatique après validation sur KAIROS
```
