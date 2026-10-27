"""Focused checks for port allocation, isolation, and the frontend API connection."""
import json
import socket
import unittest
from unittest.mock import Mock, patch

import start_local as launcher


class LauncherTests(unittest.TestCase):
    def test_occupied_port_is_skipped_without_closing_its_listener(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            occupied = listener.getsockname()[1]
            if occupied == 65535:
                self.skipTest('No higher TCP port')
            chosen = launcher.choose_port(occupied, '127.0.0.1')
            self.assertGreater(chosen, occupied)
            self.assertFalse(launcher.available(occupied, '127.0.0.1'))

    def test_frontend_port_is_excluded_from_backend_candidates(self):
        with patch.object(launcher, 'available', return_value=True):
            self.assertEqual(launcher.choose_port(8000, '127.0.0.1', {8000}), 8001)

    def test_exhausted_port_range_fails_clearly(self):
        with patch.object(launcher, 'available', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '端口均不可用'):
                launcher.choose_port(65535, '127.0.0.1')

    def test_compose_uses_workspace_specific_project(self):
        docker = launcher.Docker('docker.exe')
        self.assertEqual(docker.compose[docker.compose.index('--project-name') + 1], launcher.PROJECT)
        self.assertTrue(launcher.PROJECT.startswith('lingjing-') or launcher.PROJECT == launcher.CONFIG.get('project'))

    def test_foreign_containers_are_rejected(self):
        docker = launcher.Docker('docker.exe')
        row = {'Config': {'Labels': {'com.docker.compose.project.working_dir': 'C:/another-project'}}}
        docker.capture = Mock(side_effect=[Mock(stdout='foreign-id'), Mock(stdout=json.dumps([row]))])
        with self.assertRaisesRegex(RuntimeError, '属于另一个目录'):
            docker.containers()

    def test_existing_running_port_is_reused(self):
        row = {'Config': {'Labels': {'com.docker.compose.service': 'api'}},
               'State': {'Running': True}, 'NetworkSettings': {'Ports': {
                   '8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8012'}]}}}
        self.assertEqual(launcher.running_port([row], 'api', 8000), 8012)
        self.assertIsNone(launcher.running_port([row], 'frontend', 8080))
        row['State']['Running'] = False
        self.assertIsNone(launcher.running_port([row], 'api', 8000))

    def responses(self, proxy_status=401):
        return [(200, b'{"status":"ok"}'),
                (200, b'{"info":{"title":"AI 3D Digital Human API"}}'),
                (200, '<title>灵境造物</title>'.encode()),
                (401, b'{"detail":"Not authenticated"}'),
                (proxy_status, b'{"detail":"Not authenticated"}')]

    def test_unauthenticated_proxy_response_counts_as_connected(self):
        with patch.object(launcher, 'request', side_effect=self.responses()) as request:
            launcher.verify_services('http://127.0.0.1:8089', 'http://127.0.0.1:8012')
        self.assertEqual(request.call_args_list[-1].args[0], 'http://127.0.0.1:8089/api/v1/auth/me')

    def test_broken_proxy_is_not_reported_as_success(self):
        with patch.object(launcher, 'request', side_effect=self.responses(502)):
            with self.assertRaisesRegex(RuntimeError, '代理检查未通过'):
                launcher.verify_services('http://frontend', 'http://api')


if __name__ == '__main__':
    unittest.main()
