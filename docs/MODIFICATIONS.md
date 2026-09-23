# Modifications proposées — 23 septembre 2026

Base relue : commit `2d9c1d3`, tutoriel de mars 2025. Cette révision est destinée à une relecture puis à un essai sur le matériel réel.

## Configuration

- Multicast réactivé : l'ancien `inhibit_multicast_service 1` supprimait Announce et Sync multicast.
- Domaine 127 conservé pour le banc KAIROS indiqué par l'utilisateur.
- Qualité annoncée ramenée de classe 6 à 248 avec source oscillateur interne ; aucune précision primaire fictive.
- Priorité 1 ramenée de 1 à 128 ; un seul GM est prévu sur ce banc.
- Sync à 8/s, Announce à 1/s, délai E2E, PTPv2, UDPv4 et horodatage matériel explicites.
- Réglages télécom, gPTP et options par défaut inutiles retirés pour rendre le profil lisible.
- Sockets locaux propres à `clock-ptp`, dont un socket en lecture seule pour les diagnostics.

`serverOnly 1` est **conservé délibérément pour cette première architecture fixe**. L'audit envisageait `serverOnly 0` pour une architecture avec élection et secours. Cette variante nécessite une gestion différente de la PHC et n'est pas implémentée ici. Le lanceur refuse le changement de rôle afin d'éviter de présenter la version autonome comme une solution redondante.

## Démarrage

- Une seule interface à renseigner dans `/etc/default/clock-ptp`.
- Précontrôles des paramètres, version, IPv4, lien, PHC et horodatage matériel.
- Refus des processus PTP concurrents détectés sur ce PC dédié.
- Initialisation de la PHC depuis l'heure système + écart TAI-UTC avant de lancer `ptp4l` ; l'heure système n'est jamais réglée par ce code.
- Initialisation mémorisée dans `/run`, verrou de lancement conservé par `ptp4l`, absence de remise à l'heure automatique sur un simple redémarrage du service.
- Échec explicite si la configuration change, si l'état est corrompu ou si une discontinuité grossière de PHC est détectée au lancement.
- Unité distincte de celle de la distribution, reprise toutes les 10 secondes après échec et journaux systemd.
- Fins de ligne Linux définies par `.gitattributes`.

## Limites techniques

La date système et la stabilité du quartz restent à caractériser. Le contrôle d'époque est grossier ; il ne garantit pas UTC. Les contrôles PHC ne constituent pas un moniteur continu et n'excluent pas tous les changements matériels ou les écritures par des logiciels tiers.

La configuration ne revendique aucune certification SMPTE complète. Elle n'implémente pas les métadonnées SMPTE spécifiques, une discipline GNSS/NTP continue, un mode Dante PTPv1 ou AVB/Milan, ni un secours sans saut. Les valeurs QoS doivent encore être choisies avec le réseau.

## Vérification logicielle

Vérifications réalisées le 23 septembre 2026 :

- **23 tests réussis** sous Ubuntu/WSL avec Python 3, sans réglage d'horloge réelle.
- **Unité systemd vérifiée**, code de sortie 0. Seuls les avertissements de permissions du montage Windows sont présents ; les modes d'installation Linux sont documentés.
- **Profil lu par le vrai binaire LinuxPTP 4.4**, compilé depuis le tag officiel dans un dossier de vérification extérieur au dépôt. L'interface `ptpauditnone` a été vérifiée inexistante avant l'appel : lecture de configuration acceptée, puis arrêt attendu sur `No such device` / `failed to create a clock`, code 255. Ce résultat valide la syntaxe du profil, pas l'initialisation d'une PHC ni l'émission réseau.
- **`git diff --check` sans erreur**.

Les tests utilisent exclusivement des horloges et commandes simulées sous Linux. Ils couvrent notamment le refus d'un matériel inadapté, les échecs d'écriture/lecture d'horloge, la conservation de la PHC malgré un changement d'heure système, les états incompatibles et l'absence de lancement après échec.

L'unité doit passer `systemd-analyze verify`. Sur un répertoire Windows monté par WSL, cet outil peut signaler des permissions apparentes trop ouvertes ; les commandes `install -m 0644` du README imposent les permissions attendues sur le vrai système Linux.

Les contrôles logiciels n'exécutent pas de GM sur le réseau AV. Le verrouillage Panasonic, la précision, le comportement du pilote et les reprises physiques restent à documenter dans [QUALIFICATION.md](QUALIFICATION.md).
