#!/usr/bin/env python3
"""Launch a single autonomous LinuxPTP GM; never discipline CLOCK_REALTIME."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time


STATE_DIR = Path('/run/clock-ptp')
BOOT_ID = Path('/proc/sys/kernel/random/boot_id')
NS = 1_000_000_000


def command(args):
    result = subprocess.run(args, text=True, capture_output=True,
                            env={**os.environ, 'LC_ALL': 'C'}, timeout=15)
    if result.returncode:
        raise RuntimeError(f"{' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def read_config(path):
    raw = path.read_bytes()
    values = {}
    section = None
    for line in raw.decode('utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('['):
            if line != '[global]' or section is not None:
                raise RuntimeError('Une seule section [global] est permise pour ce GM mono-interface.')
            section = line
            continue
        fields = line.split(None, 1)
        if section is None or len(fields) != 2 or fields[0] in values:
            raise RuntimeError(f'Configuration mal formee ou option dupliquee : {line}')
        values[fields[0]] = fields[1]
    # Constraints required by this fixed-role, autonomous PHC architecture.
    expected = {
        'clock_type': 'OC', 'network_transport': 'UDPv4',
        'delay_mechanism': 'E2E', 'time_stamping': 'hardware',
        'twoStepFlag': '1', 'serverOnly': '1', 'clientOnly': '0',
        'BMCA': 'ptp', 'clockClass': '248', 'clockAccuracy': '0xFE',
        'offsetScaledLogVariance': '0xFFFF', 'timeSource': '0xA0',
        'free_running': '0', 'inhibit_multicast_service': '0',
        'inhibit_announce': '0', 'transportSpecific': '0',
        'ptp_minor_version': '0', 'unicast_listen': '0',
        'ptp_dst_ipv4': '224.0.1.129', 'udp_ttl': '1',
        'uds_address': '/run/clock-ptp/ptp4l',
        'uds_ro_address': '/run/clock-ptp/ptp4lro',
    }
    ranges = {
        'utc_offset': (0, 100), 'domainNumber': (0, 127),
        'priority1': (0, 255), 'priority2': (0, 255),
        'logSyncInterval': (-7, -1), 'logAnnounceInterval': (-3, 1),
        'logMinDelayReqInterval': (-7, 4), 'announceReceiptTimeout': (2, 10),
        'dscp_event': (0, 63), 'dscp_general': (0, 63),
        'tx_timestamp_timeout': (1, 1000), 'logging_level': (0, 7),
        'use_syslog': (0, 1),
    }
    unknown = values.keys() - expected.keys() - ranges.keys() - {'userDescription'}
    if unknown:
        raise RuntimeError(f'Options non prises en charge par ce lanceur : {sorted(unknown)}')
    for name, value in expected.items():
        if values.get(name) != value:
            raise RuntimeError(f'{name} doit valoir {value} pour ce lanceur autonome.')
    for name, (low, high) in ranges.items():
        value = values.get(name, '')
        if not re.fullmatch(r'-?[0-9]+', value) or not low <= int(value) <= high:
            raise RuntimeError(f'{name} doit etre un entier entre {low} et {high}.')
    sync = int(values['logSyncInterval'])
    if not sync <= int(values['logMinDelayReqInterval']) <= sync + 5:
        raise RuntimeError('logMinDelayReqInterval doit etre compris entre logSyncInterval et sa valeur + 5.')
    description = values.get('userDescription', '')
    if len(description) > 128:
        raise RuntimeError('userDescription depasse 128 caracteres.')
    return int(values['utc_offset']), hashlib.sha256(raw).hexdigest()


def ensure_no_clock_daemon():
    for name in ('ptp4l', 'phc2sys', 'ts2phc', 'timemaster'):
        result = subprocess.run(['pgrep', '-x', name], capture_output=True, timeout=5)
        if result.returncode == 0:
            raise RuntimeError(f'{name} est deja actif : identifier son role avant de lancer ce GM.')
        if result.returncode != 1:
            raise RuntimeError(f'Impossible de verifier les processus {name}.')


def preflight(interface, config):
    if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,15}', interface) or interface == 'CHANGE_ME':
        raise RuntimeError('Renseigner le vrai nom de l interface Ethernet AV.')
    offset, digest = read_config(config)
    for name in ('ptp4l', 'ethtool', 'ip', 'pgrep'):
        if not shutil.which(name):
            raise RuntimeError(f'Outil manquant : {name}')
    version = command(['ptp4l', '-v']).strip()
    match = re.match(r'(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (4, 4):
        raise RuntimeError(f'LinuxPTP >= 4.4 requis pour ce profil ; detecte : {version}')
    addresses = json.loads(command(['ip', '-j', '-4', 'addr', 'show', 'dev', interface]))
    if not addresses or not any(a.get('family') == 'inet'
                                for a in addresses[0].get('addr_info', [])):
        raise RuntimeError('Aucune adresse IPv4 sur l interface AV.')
    if (Path('/sys/class/net') / interface / 'carrier').read_text().strip() != '1':
        raise RuntimeError('Le lien Ethernet AV est absent.')
    capabilities = command(['ethtool', '-T', interface])
    for capability in ('hardware-transmit', 'hardware-receive', 'hardware-raw-clock'):
        if not re.search(r'^\s*' + capability + r'\b', capabilities, re.MULTILINE):
            raise RuntimeError(f'Horodatage materiel incomplet : {capability} absent.')
    match = re.search(r'PTP Hardware Clock:\s*(\d+)\b', capabilities)
    if not match:
        raise RuntimeError('Aucune PHC exposee par le pilote.')
    device = Path('/dev') / f'ptp{match[1]}'
    if not stat.S_ISCHR(device.stat().st_mode):
        raise RuntimeError(f'{device} n est pas un peripherique PHC.')
    ensure_no_clock_daemon()
    return device, offset, digest


def prepare_clock(clock_id, state_file, signature, offset):
    """One initialization per boot. A service restart must not step the PHC."""
    boot = BOOT_ID.read_text().strip()
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state['boot'] != boot or state['signature'] != signature:
            raise RuntimeError('Etat PHC incompatible : redemarrer le PC hors production apres verification.')
        elapsed = time.monotonic_ns() - state['monotonic_ns']
        if elapsed < 0:
            raise RuntimeError('Etat temporel incoherent : intervention hors production requise.')
        expected = state['phc_ns'] + elapsed
        # Coarse reset/drift detector only, NOT an AV precision/lock measurement.
        tolerance = min(5 * NS + elapsed // 10000, 10 * NS)
        if abs(time.clock_gettime_ns(clock_id) - expected) > tolerance:
            raise RuntimeError('PHC reinitialisee ou derive excessive : refus de la remettre a l heure en service.')
        print('PHC conservee : aucun saut d horloge au redemarrage du service.', flush=True)
        return
    now = time.time_ns()
    if now < 1704067200 * NS:  # 2024-01-01; only reject an obviously invalid RTC.
        raise RuntimeError('Date systeme manifestement invalide ; corriger avant le demarrage du GM.')
    time.clock_settime_ns(clock_id, now + offset * NS)
    phc_now = time.clock_gettime_ns(clock_id)
    if abs(phc_now - time.time_ns() - offset * NS) > NS:
        raise RuntimeError('Echec de verification de l initialisation PHC (controle grossier a 1 s).')
    state = {'boot': boot, 'signature': signature,
             'phc_ns': phc_now, 'monotonic_ns': time.monotonic_ns()}
    temporary = state_file.with_suffix('.tmp')
    temporary.write_text(json.dumps(state) + '\n')
    temporary.replace(state_file)
    print('PHC initialisee depuis le systeme + utc_offset ; precision UTC non garantie.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'run'))
    parser.add_argument('--interface', required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'run' and os.geteuid() != 0:
        raise RuntimeError('Le lancement doit etre effectue par root via le service documente.')
    # check creates no files, adjusts no clock, and sends no PTP messages.
    if args.action == 'check':
        device, offset, _ = preflight(args.interface, args.config)
        print(f'Precontroles OK : {args.interface}, {device}, utc_offset={offset}.')
        print('Precision et verrouillage KAIROS restent a mesurer sur le banc.')
        return
    STATE_DIR.mkdir(mode=0o750, parents=True, exist_ok=True)
    with (STATE_DIR / 'launcher.lock').open('a+b') as lock:
        # Kept across exec so a second launcher cannot initialize the active clock.
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.set_inheritable(lock.fileno(), True)
        device, offset, digest = preflight(args.interface, args.config)
        with device.open('r+b', buffering=0) as phc:
            # Linux FD_TO_CLOCKID from the dynamic POSIX clock API.
            clock_id = ((~phc.fileno()) << 3) | 3
            hardware = (Path('/sys/class/net') / args.interface / 'device').resolve()
            signature = [args.interface, str(device), str(hardware), digest]
            prepare_clock(clock_id, STATE_DIR / 'initialized.json', signature, offset)
        executable = shutil.which('ptp4l')
        os.execv(executable, [executable, '-f', str(args.config), '-i', args.interface, '-m'])


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f'Clock-PTP : {error}', file=sys.stderr)
        sys.exit(1)
