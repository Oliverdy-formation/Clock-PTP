# Clock-PTP
Clock PTP for linux 

# TUTO
## Installer linux ptp
Pour installer linux ptp faites la commande suivante :

sudo apt install linuxptp

## Installer ethtool
Pour installer installer ethtool faites la commande suivante :

sudo apt install ethtool
pour vérifier la compatibilité faites la commande suivante sudo ethtool -T <interface a tester>

## Modifier le fichier ptp4l.conf
Fichier de config a modifier : sudo nano /etc/linuxptp/ptp4l.conf
Mettre le même “clock domain” sur les appareils et le fichier ptp4l.conf
Mettre la clock GM avec la priority 1. La plus basse des prio c’est 0 ou 1
Commande pour lancer la clock: sudo ptp4l -f /etc/linuxptp/ptp4l.conf -i enp50s0 -m

Pour vérifier avec le Netgear 4350
Depuis le switch regarder les paquet reçu dans “PTP Statistic” qui est dans system/management
Dans “PTP Détails” du switch regarder si il est slave