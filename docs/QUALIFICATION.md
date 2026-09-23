# Qualification sur mini-PC, M4250 et KAIROS

Ce document sert à consigner des résultats réels. Toutes les cases ci-dessous sont initialement **non testées**. Les tests unitaires ne remplissent aucune de ces cases.

## Identification du banc

| Élément | Valeur relevée |
|---|---|
| Date, opérateur et version Git | À renseigner |
| PC, distribution et noyau Linux | À renseigner |
| Modèle carte réseau, pilote, firmware | À renseigner |
| Interface et PHC détectée | À renseigner |
| Version `ptp4l -v` | À renseigner |
| Copie de la configuration active | À conserver localement |
| Source de l'heure système au démarrage, écart TAI-UTC vérifié | À renseigner |
| Modèle exact et firmware M4250 | À renseigner |
| Modèle KAIROS et version logicielle | À renseigner |
| Interface PTP KAIROS, VLAN, sous-réseau, domaine | À renseigner |
| GMC ID attendu, puis réellement observé | À renseigner |
| Autres équipements et rôles PTP | À renseigner |

## Critères à fixer avant les mesures

Définir avec les exigences des appareils : erreur temporelle admissible aux récepteurs, variation en fréquence, durée maximale d'acquisition/réacquisition et perturbations audio/vidéo acceptables. Ne pas déduire ces seuils d'un simple voyant vert ou leur attribuer arbitrairement une précision submicroseconde.

Pour mesurer une précision absolue UTC, il faut une référence indépendante caractérisée. En son absence, on peut vérifier la synchronisation relative, la continuité et le comportement AV ; pas certifier UTC. Les valeurs RMS/max d'un récepteur LinuxPTP et les mesures instrumentées n'ont pas exactement le même périmètre qu'une capture de paquets.

## Séquence

| Essai | Résultat attendu | Statut / mesures |
|---|---|---|
| Précontrôle matériel | PHC et horodatage matériel présents ; interface correcte | Non testé |
| Premier démarrage sans Internet | Date système plausible ; initialisation avant émission ; GM visible sur KAIROS | Non testé |
| Identité GM | GMC ID KAIROS égal au `clockIdentity` du PC | Non testé |
| Échanges PTP | Announce, Sync, Follow_Up et réponses aux Delay_Req cohérents dans le domaine choisi | Non testé |
| M4250 | Transit et correction PTP E2E vérifiés, multicast et QoS cohérents | Non testé |
| Charge réseau et CPU, 24–72 h | Offsets et dérive dans les limites définies ; aucun défaut AV lié à la synchro | Non testé |
| `systemctl restart clock-ptp` | Journal « PHC conservee », aucune nouvelle mise à l'heure par le lanceur ; réacquisition mesurée | Non testé |
| `stop` puis `start` du service | État dans `/run` conservé ; pas de remise à l'heure de la PHC | Non testé |
| Câble absent au démarrage puis rebranché | Reprise des tentatives, GM retrouvé sans intervention cachée | Non testé |
| Débranchement en cours d'exécution | Comportement du pilote, pertes et durée de réacquisition consignés | Non testé |
| Redémarrage complet du PC | Nouvelle initialisation ; interruption et éventuel saut mesurés | Non testé |
| Démarrage d'une autre instance sur le PC | Refus sans modification de la PHC | Non testé |
| RTC erronée / PHC réinitialisée | Refus lorsqu'un contrôle détecte l'anomalie ; pas de promesse de détection exhaustive | Non testé |

Un redémarrage complet du PC coupe le GM et peut changer son époque. Cette version n'assure ni redondance ni continuité garantie pendant ce scénario.

## Collecte

```bash
ptp4l -v
uname -r
ip -br addr
ethtool -i INTERFACE_AV
ethtool -T INTERFACE_AV
systemctl status clock-ptp --no-pager
journalctl -u clock-ptp -b --no-pager
sudo pmc -u -b 0 -d 127 -s /run/clock-ptp/ptp4lro 'GET DEFAULT_DATA_SET'
sudo pmc -u -b 0 -d 127 -s /run/clock-ptp/ptp4lro 'GET TIME_PROPERTIES_DATA_SET'
```

Adapter l'interface et le domaine. Pour une capture, installer `tcpdump` si nécessaire, puis :

```bash
sudo tcpdump -ni INTERFACE_AV -c 200 -w ptp-test.pcap 'udp port 319 or udp port 320'
```

Une capture locale contient des identifiants et adresses du réseau : la conserver avec les résultats du banc. Elle prouve des échanges, pas l'erreur effective de l'horloge KAIROS. Contrôler les séquences, le domaine, les propriétés temporelles, les timestamps et le `correctionField` avec un analyseur adapté.

Si KAIROS ne suit pas la référence, vérifier l'interface sélectionnée, le domaine, la version PTP, les propriétés de temps acceptées, les cadences et les exigences SMPTE de sa version. Ne pas transformer artificiellement `clockClass 248` en `6` pour obtenir un état verrouillé.

## Décision

Consigner le résultat : accepté pour **ce banc et ces versions**, refusé, ou diagnostic incomplet. Décrire toute limite (durée d'essai, absence de référence indépendante, mode vidéo non testé). Ne pas étendre le résultat à toutes les marques AV ou à un réseau de production différent.
