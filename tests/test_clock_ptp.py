"""Linux tests with simulated clocks: never open or adjust a real PHC."""

from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('clock_ptp', ROOT / 'scripts/clock_ptp.py')
ptp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ptp)


class ConfigTests(unittest.TestCase):
    def test_shipped_profile(self):
        offset, digest = ptp.read_config(ROOT / 'fichier_config.txt')
        self.assertEqual(offset, 37)
        self.assertEqual(len(digest), 64)

    def test_reject_incompatible_or_ambiguous_profiles(self):
        original = (ROOT / 'fichier_config.txt').read_text()
        cases = [
            original.replace('clockClass              248', 'clockClass 6'),
            original.replace('serverOnly              1', 'serverOnly 0'),
            original.replace('time_stamping           hardware', 'time_stamping software'),
            original.replace('inhibit_multicast_service 0', 'inhibit_multicast_service 1'),
            original.replace('utc_offset              37', 'utc_offset invalid'),
            original + '\n[eth0]\n',
            original + '\nphc_index 1\n',
            original + '\ndomainNumber 0\n',
            original.replace('logMinDelayReqInterval  -3', 'logMinDelayReqInterval -7'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'ptp.conf'
            for candidate in cases:
                with self.subTest(candidate=candidate[-100:]):
                    config.write_text(candidate)
                    with self.assertRaises(RuntimeError):
                        ptp.read_config(config)


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.state = Path(directory) / 'initialized.json'
        boot = Path(directory) / 'boot_id'
        boot.write_text('boot-1')
        self.stack.enter_context(patch.object(ptp, 'BOOT_ID', boot))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.now = 1800000000 * ptp.NS
        self.mono = self.stack.enter_context(patch.object(ptp.time, 'monotonic_ns', return_value=10 * ptp.NS))
        self.system = self.stack.enter_context(patch.object(ptp.time, 'time_ns', return_value=self.now))
        self.read = self.stack.enter_context(patch.object(ptp.time, 'clock_gettime_ns', return_value=self.now + 37 * ptp.NS))
        self.set_clock = self.stack.enter_context(patch.object(ptp.time, 'clock_settime_ns'))
        self.signature = ['eth0', '/dev/ptp0', '/hardware/nic0', 'config-hash']

    def prepare(self):
        ptp.prepare_clock(-29, self.state, self.signature, 37)

    def test_initializes_phc_to_system_plus_tai_offset(self):
        self.prepare()
        self.set_clock.assert_called_once_with(-29, self.now + 37 * ptp.NS)
        self.assertEqual(json.loads(self.state.read_text())['boot'], 'boot-1')

    def test_restart_does_not_follow_system_clock_jump(self):
        self.prepare()
        self.set_clock.reset_mock()
        self.mono.return_value += 60 * ptp.NS
        self.read.return_value += 60 * ptp.NS
        self.system.return_value += 3600 * ptp.NS
        self.prepare()
        self.set_clock.assert_not_called()

    def test_clock_write_failure_does_not_mark_ready(self):
        self.set_clock.side_effect = PermissionError('PHC write refused')
        with self.assertRaises(PermissionError):
            self.prepare()
        self.assertFalse(self.state.exists())

    def test_readback_failure_does_not_mark_ready(self):
        self.read.return_value = self.now
        with self.assertRaisesRegex(RuntimeError, 'verification'):
            self.prepare()
        self.assertFalse(self.state.exists())

    def test_invalid_system_date_does_not_write_clock(self):
        self.system.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'Date systeme'):
            self.prepare()
        self.set_clock.assert_not_called()

    def test_config_change_refuses_reinitialization(self):
        self.prepare()
        self.set_clock.reset_mock()
        self.signature[-1] = 'changed-config'
        with self.assertRaisesRegex(RuntimeError, 'incompatible'):
            self.prepare()
        self.set_clock.assert_not_called()

    def test_wrong_boot_refuses_stale_marker(self):
        self.prepare()
        self.set_clock.reset_mock()
        ptp.BOOT_ID.write_text('boot-2')
        with self.assertRaisesRegex(RuntimeError, 'incompatible'):
            self.prepare()
        self.set_clock.assert_not_called()

    def test_phc_reset_is_not_repaired_while_restarting(self):
        self.prepare()
        self.set_clock.reset_mock()
        self.read.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'PHC reinitialisee'):
            self.prepare()
        self.set_clock.assert_not_called()

    def test_corrupt_state_is_not_replaced_by_initialization(self):
        self.state.write_text('broken json')
        with self.assertRaises(ValueError):
            self.prepare()
        self.set_clock.assert_not_called()


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.version = '4.4\n'
        self.capabilities = ('hardware-transmit\nhardware-receive\n'
                             'hardware-raw-clock\nPTP Hardware Clock: 2\n')
        self.addresses = [{'addr_info': [{'family': 'inet', 'local': '192.0.2.1'}]}]
        self.stack.enter_context(patch.object(ptp.shutil, 'which', return_value='/usr/sbin/tool'))
        self.stack.enter_context(patch.object(ptp, 'command', side_effect=self.command))
        self.carrier = self.stack.enter_context(patch.object(Path, 'read_text', return_value='1'))
        self.stack.enter_context(patch.object(Path, 'stat', return_value=type('Stat', (), {'st_mode': stat.S_IFCHR})()))
        self.process = self.stack.enter_context(patch.object(ptp.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)))

    def command(self, args):
        if args[0] == 'ptp4l':
            return self.version
        if args[0] == 'ip':
            return json.dumps(self.addresses)
        if args[0] == 'ethtool':
            return self.capabilities
        raise AssertionError(args)

    def check(self):
        return ptp.preflight('enp3s0', ROOT / 'fichier_config.txt')

    def test_hardware_clock_selected_from_ethtool(self):
        self.assertEqual(self.check()[0], Path('/dev/ptp2'))

    def test_software_timestamping_rejected(self):
        self.capabilities = 'software-transmit\nsoftware-receive\nPTP Hardware Clock: none\n'
        with self.assertRaisesRegex(RuntimeError, 'Horodatage materiel'):
            self.check()

    def test_no_phc_rejected(self):
        self.capabilities = self.capabilities.replace('Clock: 2', 'Clock: none')
        with self.assertRaisesRegex(RuntimeError, 'Aucune PHC'):
            self.check()

    def test_old_version_rejected(self):
        self.version = '3.1.1\n'
        with self.assertRaisesRegex(RuntimeError, '4.4 requis'):
            self.check()

    def test_no_link_rejected(self):
        self.carrier.return_value = '0'
        with self.assertRaisesRegex(RuntimeError, 'lien Ethernet'):
            self.check()

    def test_no_ipv4_rejected(self):
        self.addresses = [{'addr_info': []}]
        with self.assertRaisesRegex(RuntimeError, 'IPv4'):
            self.check()

    def test_existing_daemon_rejected(self):
        self.process.return_value = subprocess.CompletedProcess([], 0)
        with self.assertRaisesRegex(RuntimeError, 'deja actif'):
            self.check()

    def test_process_inspection_error_rejected(self):
        self.process.return_value = subprocess.CompletedProcess([], 2)
        with self.assertRaisesRegex(RuntimeError, 'Impossible de verifier'):
            self.check()


class LaunchTests(unittest.TestCase):
    def test_second_launcher_cannot_touch_active_clock(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            state = Path(directory)
            stack.enter_context(patch.object(ptp, 'STATE_DIR', state))
            stack.enter_context(patch.object(ptp.sys, 'argv', ['clock_ptp', 'run', '--interface', 'eth0', '--config', 'test.conf']))
            stack.enter_context(patch.object(ptp.os, 'geteuid', return_value=0))
            inspect = stack.enter_context(patch.object(ptp, 'preflight'))
            lock = stack.enter_context((state / 'launcher.lock').open('a+b'))
            ptp.fcntl.flock(lock.fileno(), ptp.fcntl.LOCK_EX | ptp.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                ptp.main()
            inspect.assert_not_called()

    def test_successful_launch_initializes_before_exec(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            state = Path(directory)
            fake_phc = state / 'fake-phc'
            fake_phc.touch()
            events = []
            stack.enter_context(patch.object(ptp, 'STATE_DIR', state))
            stack.enter_context(patch.object(ptp.sys, 'argv', ['clock_ptp', 'run', '--interface', 'eth0', '--config', '/test.conf']))
            stack.enter_context(patch.object(ptp.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(ptp, 'preflight', return_value=(fake_phc, 37, 'hash')))
            stack.enter_context(patch.object(ptp, 'prepare_clock', side_effect=lambda *args: events.append('prepare')))
            stack.enter_context(patch.object(ptp.shutil, 'which', return_value='/usr/sbin/ptp4l'))

            def execute(executable, arguments):
                self.assertEqual(events, ['prepare'])
                self.assertEqual(executable, '/usr/sbin/ptp4l')
                self.assertEqual(arguments, [executable, '-f', '/test.conf', '-i', 'eth0', '-m'])
                locks = []
                for descriptor in Path('/proc/self/fd').iterdir():
                    try:
                        if descriptor.resolve() == state / 'launcher.lock':
                            locks.append(int(descriptor.name))
                    except FileNotFoundError:
                        pass
                self.assertTrue(locks)
                self.assertTrue(all(ptp.os.get_inheritable(fd) for fd in locks))
                events.append('exec')

            stack.enter_context(patch.object(ptp.os, 'execv', side_effect=execute))
            ptp.main()
            self.assertEqual(events, ['prepare', 'exec'])

    def test_check_does_not_initialize_or_create_state(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            state = Path(directory) / 'not-created'
            stack.enter_context(patch.object(ptp, 'STATE_DIR', state))
            stack.enter_context(patch.object(ptp.sys, 'argv', ['clock_ptp', 'check', '--interface', 'eth0', '--config', 'test.conf']))
            stack.enter_context(patch.object(ptp, 'preflight', return_value=(Path('/dev/ptp0'), 37, 'hash')))
            initialize = stack.enter_context(patch.object(ptp, 'prepare_clock'))
            execute = stack.enter_context(patch.object(ptp.os, 'execv'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            ptp.main()
            initialize.assert_not_called()
            execute.assert_not_called()
            self.assertFalse(state.exists())

    def test_failed_initialization_never_starts_ptp4l(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            state = Path(directory)
            fake_phc = state / 'fake-phc'
            fake_phc.touch()
            stack.enter_context(patch.object(ptp, 'STATE_DIR', state))
            stack.enter_context(patch.object(ptp.sys, 'argv', ['clock_ptp', 'run', '--interface', 'eth0', '--config', 'test.conf']))
            stack.enter_context(patch.object(ptp.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(ptp, 'preflight', return_value=(fake_phc, 37, 'hash')))
            stack.enter_context(patch.object(ptp, 'prepare_clock', side_effect=RuntimeError('initialization failed')))
            execute = stack.enter_context(patch.object(ptp.os, 'execv'))
            with self.assertRaisesRegex(RuntimeError, 'initialization failed'):
                ptp.main()
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
