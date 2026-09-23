# Clock-PTP

Grandmaster PTP local sur un PC Linux, destiné à un **banc Panasonic KAIROS avec un switch NETGEAR M4250**. Le moteur PTP reste le projet officiel [LinuxPTP](https://www.linuxptp.org/).

Cette version prépare un mode autonome **sans GPS et sans accès Internet obligatoire**. Elle exige une carte Ethernet avec horodatage matériel et une PHC (PTP Hardware Clock). Le débit 1 Gb/s suffit pour les messages d'horloge ; il ne prouve pas la compatibilité matérielle PTP.

**État : version de laboratoire à qualifier.** Les tests logiciels ne prouvent ni la précision de la carte réseau, ni le verrouillage de KAIROS, ni une conformité complète SMPTE ST 2059-2. Le protocole d'essai est dans [docs/QUALIFICATION.md](QUALIFICATION.md).

## Fonctionnement choisi

```text
Au démarrage : heure système UTC (RTC ou heure préalablement réglée)
                          + écart TAI-UTC du fichier de configuration
                          ↓ initialisation unique
                    PHC de la carte réseau
                          ↓ ptp4l, domaine 127, UDPv4/E2E
                    M4250 en Transparent Clock
                          ↓ interface PTP choisie
                    KAIROS et autres récepteurs du même banc
```

Après initialisation, la PHC tourne sur son oscillateur interne. Le lanceur ne modifie jamais l'heure système et ne lance pas `phc2sys` ou `chronyd`. Un ajustement NTP ultérieur de l'heure système n'est pas retransmis à la PHC. Cela évite une dépendance permanente à Internet, mais **ne garantit pas l'exactitude UTC ni la stabilité à long terme**.

Le profil conserve volontairement `serverOnly 1` : **un seul GM est prévu dans ce domaine de laboratoire**. Il ne suit pas automatiquement un meilleur GM. Ne pas le raccorder à une installation possédant déjà une horloge maître sans revoir l'architecture. Deux PC autonomes ne donnent pas un secours sans saut de temps. Une variante avec élection normale devra aussi gérer la direction de synchronisation de la PHC ; changer seulement `serverOnly` n'est pas pris en charge par ce lanceur.

Le M4250 corrige le temps de transit PTPv2 en mode Transparent Clock. On ne lui demande pas de devenir « slave » comme un Boundary Clock. C'est notamment **KAIROS qui doit suivre le bon GMC ID**, sur la bonne interface et dans le même domaine.

## Fichiers

| Fichier | Rôle |
|---|---|
| `fichier_config.txt` | Configuration unique de `ptp4l`, copiée en `/etc/clock-ptp/ptp4l.conf`. |
| `scripts/clock_ptp.py` | Précontrôles, initialisation de la PHC et exécution de `ptp4l`. |
| `systemd/clock-ptp.example` | Interface et chemin de configuration, à adapter une seule fois. |
| `systemd/clock-ptp.service` | Démarrage automatique et journaux. |
| `docs/QUALIFICATION.md` | Mesures sur le PC, M4250 et KAIROS, y compris après redémarrage. |
| `docs/MODIFICATIONS.md` | Changements par rapport au tutoriel de mars 2025 et limites. |
| `tests/test_clock_ptp.py` | Tests de comportement avec horloges et commandes simulées. |

## Prérequis du PC

- Linux natif, Python 3.8 ou supérieur, systemd, **LinuxPTP 4.4 ou supérieur**.
- Interface Ethernet physique, lien actif, adresse IPv4 et PHC exposée par le pilote.
- Un seul gestionnaire de cette PHC : aucun autre `ptp4l`, `phc2sys`, `ts2phc` ou `timemaster` en parallèle. Le contrôle est volontairement global pour un mini-PC dédié.
- Date système raisonnable au démarrage, généralement fournie par la RTC. Le lanceur rejette les dates antérieures à 2024 ; ce contrôle grossier ne valide pas UTC.
- Mise en veille désactivée pendant les essais AV. Carte USB, VM, VLAN Linux ou agrégation ne sont pas qualifiés par cette version.

Sur Debian/Ubuntu, installer les outils selon la version de la distribution :

```bash
sudo apt update
sudo apt install linuxptp ethtool iproute2 procps python3
ptp4l -v
ip -br link
```

**Vérifier la version réellement installée.** Certaines distributions fournissent LinuxPTP 3.x ou 4.2 : le lanceur refusera ces versions. Utiliser un paquet maintenu contenant au moins 4.4, ou une compilation d'une version stable officielle selon la politique de la machine. Ne pas prendre automatiquement la branche de développement.

Identifier la carte (remplacer `enp3s0` dans ces commandes de diagnostic) :

```bash
ethtool -i enp3s0
ethtool -T enp3s0
ls -l /dev/ptp*
```

Il faut retrouver `hardware-transmit`, `hardware-receive`, `hardware-raw-clock` et `PTP Hardware Clock: N`. Une carte qui indique uniquement `software-*` n'est pas acceptée. Le bon fonctionnement de l'horodatage UDPv4 devra ensuite être confirmé par `ptp4l` sur le matériel.

## Installation sur le mini-PC

Effectuer cette installation sur le banc, pendant une interruption de service prévue. Les commandes suivantes **installent les fichiers mais ne démarrent pas encore le GM**. Elles supposent d'être dans le dossier du dépôt.

Avant de remplacer une ancienne installation, conserver ses fichiers et la sortie de `systemctl cat ptp4l`. Identifier tout processus d'horloge actif et son rôle. Le nouveau service porte un autre nom et n'écrase pas l'unité `ptp4l.service` de la distribution. Ne pas activer les deux ensemble.

```bash
sudo install -d -m 0755 /etc/clock-ptp /usr/local/lib/clock-ptp
sudo install -m 0644 fichier_config.txt /etc/clock-ptp/ptp4l.conf
sudo install -m 0644 scripts/clock_ptp.py /usr/local/lib/clock-ptp/clock_ptp.py
sudo install -m 0644 systemd/clock-ptp.example /etc/default/clock-ptp
sudo install -m 0644 systemd/clock-ptp.service /etc/systemd/system/clock-ptp.service
sudo nano /etc/default/clock-ptp
sudo nano /etc/clock-ptp/ptp4l.conf
```

Dans `/etc/default/clock-ptp`, remplacer `CHANGE_ME` par le vrai nom de l'interface. Lors d'une mise à jour ultérieure, sauvegarder les deux fichiers de configuration locaux et les comparer avant de les remplacer.

Relire les paramètres :

| Paramètre | Valeur livrée | À vérifier |
|---|---|---|
| `domainNumber` | `127` | Même domaine sur KAIROS et les récepteurs. Ce n'est pas le VLAN. |
| `clockClass` | `248` | Référence autonome non caractérisée ; ne pas déclarer classe 6 sans référence primaire. |
| `timeSource` | `0xA0` | Oscillateur interne. |
| `utc_offset` | `37` | Écart TAI-UTC en secondes à confirmer auprès de l'IERS avant installation ; aucun rapport avec UTC+1/UTC+2. |
| `logSyncInterval` | `-3` | 8 messages Sync/s. |
| `logAnnounceInterval` | `0` | 1 message Announce/s ; coordonner avec le profil et les récepteurs. |
| `logMinDelayReqInterval` | `-3` | Point de départ pour le banc, à vérifier sur les récepteurs. |
| `priority1`, `priority2` | `128`, `128` | Pas de priorité extrême pour masquer un conflit de GM. |
| `ptp_minor_version` | `0` | En-tête PTPv2 pour le banc historique. |
| `dscp_event`, `dscp_general` | `0`, `0` | Définir la QoS avec le switch avant qualification sous charge. |

Le lanceur accepte des ajustements limités (domaines 0–127, priorités, intervalles, QoS, timeout, description et écart UTC). Il refuse les options inconnues, les sections d'interface et les changements de rôle ou de source temporelle. Ce choix protège la cohérence entre la PHC initialisée et celle utilisée par `ptp4l`.

Les annonces restent non traçables à une référence primaire : une heure système approximative plus un écart de 37 s ne transforme pas ce PC en référence UTC certifiée. Aucun indicateur de traçabilité ou de validité UTC n'est forcé par ce lanceur.

## Précontrôle et premier lancement

Après arrêt de l'ancien service PTP identifié sur ce PC dédié, charger les paramètres locaux et lancer le contrôle en lecture seule :

```bash
. /etc/default/clock-ptp
sudo python3 /usr/local/lib/clock-ptp/clock_ptp.py check \
  --interface "$PTP_INTERFACE" --config "$PTP_CONFIG"
```

`check` ne crée aucun état, ne règle aucune horloge et n'émet pas de PTP. Il peut refuser de passer lorsqu'un service PTP fonctionne déjà ; utiliser alors les journaux et `pmc` pour observer ce service.

Après vérification de la date, du réseau de test et de l'absence d'autre GM dans le domaine :

```bash
sudo systemctl daemon-reload
sudo systemctl start clock-ptp
sudo systemctl status clock-ptp --no-pager
sudo journalctl -u clock-ptp -b --no-pager
```

Le premier lancement initialise la PHC depuis l'heure système + `utc_offset`, vérifie grossièrement la lecture puis remplace le lanceur par `ptp4l`. Les erreurs empêchent cette exécution. Un état est conservé dans `/run/clock-ptp/initialized.json`.

Un simple `restart` ne remet pas la PHC à l'heure. Le service conserve son état même après `stop/start`, et ne réinitialise normalement qu'après redémarrage complet du PC. Une configuration modifiée, un état corrompu ou une discontinuité grossière de PHC provoquent un refus. Ne pas supprimer ce fichier d'état pour contourner une erreur pendant la production : diagnostiquer puis redémarrer le PC hors production.

Le contrôle de discontinuité tolère plusieurs secondes pour détecter une réinitialisation manifeste ; **ce n'est pas un contrôle de précision AV**. Il est effectué au lancement, pas en continu. Un pilote peut aussi réinitialiser la PHC pendant l'exécution : la surveillance des récepteurs reste nécessaire.

Pour activer le démarrage automatique **après validation du premier banc** :

```bash
sudo systemctl enable clock-ptp
```

Le service réessaie toutes les 10 secondes en cas d'échec, notamment si le câble est branché tardivement. Après correction du problème, consulter les journaux et vérifier à nouveau KAIROS. `systemctl active` ne signifie pas « synchronisation validée ».

## Contrôles sur le réseau

- PC et interface PTP de KAIROS dans un VLAN/sous-réseau cohérent pour ce banc, multicast `224.0.1.129`, UDP 319 et 320 autorisés dans les deux sens.
- Sur M4250, vérifier le profil AV, la fonction PTP Transparent Clock E2E, les compteurs, la QoS et le comportement multicast. Ne pas confondre PTPv2 avec AVB/gPTP.
- Sur KAIROS, vérifier interface PTP, domaine 127, mode récepteur si disponible et GMC ID. La disponibilité exacte des menus dépend du modèle et du logiciel.
- Évaluer les flux vidéo séparément : ce guide concerne le chemin d'horloge, pas le dimensionnement des liaisons ST 2110.

Lire les datasets via le socket local **en lecture seule**, en adaptant `-d` si le domaine a changé :

```bash
sudo pmc -u -b 0 -d 127 -s /run/clock-ptp/ptp4lro 'GET DEFAULT_DATA_SET'
sudo pmc -u -b 0 -d 127 -s /run/clock-ptp/ptp4lro 'GET PARENT_DATA_SET'
sudo pmc -u -b 0 -d 127 -s /run/clock-ptp/ptp4lro 'GET PORT_DATA_SET'
sudo pmc -u -b 0 -d 127 -s /run/clock-ptp/ptp4lro 'GET TIME_PROPERTIES_DATA_SET'
```

Puis suivre [la qualification](QUALIFICATION.md). Des paquets reçus et un état MASTER ne démontrent pas la précision des appareils récepteurs.

## Arrêt et retour à l'ancienne installation

```bash
sudo systemctl disable --now clock-ptp
```

Avant de réactiver une ancienne installation : vérifier son rôle, restaurer ses paramètres sauvegardés si nécessaire et décider comment sa PHC doit être initialisée. L'arrêt du nouveau service ne rétablit pas automatiquement l'ancienne époque de la PHC. Effectuer le retour hors production, puis vérifier l'identité GM et le verrouillage des appareils.

## Vérifications du code

Sur Linux, sans matériel PTP et sans privilèges :

```bash
python3 -B -m unittest discover -s tests -v
systemd-analyze verify systemd/clock-ptp.service
```

Les tests simulent les commandes et les horloges ; aucune horloge réelle n'est réglée. Le lanceur utilise l'API Linux des horloges POSIX dynamiques et nécessite Linux (`fcntl`). WSL sert seulement aux contrôles logiciels, pas à qualifier le matériel AV.

## Références

- [LinuxPTP : prérequis ethtool](https://linuxptp.sourceforge.net/), [ptp4l](https://www.linuxptp.org/documentation/ptp4l/) et [échelles de temps PHC/UTC](https://www.linuxptp.org/documentation/phc2sys/).
- [Linux : horloges PTP matérielles](https://docs.kernel.org/driver-api/ptp.html).
- [NETGEAR M4250 : fiche technique](https://www.netgear.com/media/M4250-Datasheet_tcm148-118162.pdf).
- [Panasonic KAIROS : exemple de réglages PTP, page 85](https://pro-av.panasonic.net/manual/pdf/Kairos_guide%28DVQP2366YA%29_E.pdf), à confronter à la version installée.
- [IERS : Bulletin C et secondes intercalaires](https://www.iers.org/IERS/EN/Publications/Bulletins/bulletins.html).

Ce dépôt ne propose pas un profil universel pour Dante PTPv1, AES67 et AVB/Milan, ni une implémentation certifiée de toutes les métadonnées SMPTE.
