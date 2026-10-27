"""ComfyUI must write into the directory mounted by the generation adapter."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import local_comfy


class ComfyOutputTests(unittest.TestCase):
    def test_existing_engine_with_wrong_directory_is_rejected(self):
        with TemporaryDirectory() as root:
            config = {'root': root, 'output_directory': str(Path(root) / 'shared-output')}
            with self.assertRaisesRegex(RuntimeError, '输出目录与本项目不一致'):
                local_comfy.validate_output_directory({'system': {'argv': ['main.py']}}, config)

    def test_existing_engine_with_matching_directory_is_reused(self):
        with TemporaryDirectory() as root:
            output = str(Path(root) / 'shared-output')
            config = {'root': root, 'output_directory': output}
            for argv in (['main.py', '--output-directory', output],
                         ['main.py', '--output-directory=' + output]):
                local_comfy.validate_output_directory({'system': {'argv': argv}}, config)

    def test_unverifiable_engine_is_not_accepted(self):
        with self.assertRaisesRegex(RuntimeError, '无法核验'):
            local_comfy.validate_output_directory({}, {'root': '.', 'output_directory': '/shared'})

    def test_start_passes_shared_output_to_engine_and_creates_directory(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'main.py').touch()
            python = root / 'python.exe'
            python.touch()
            compiler = root / 'Lib/site-packages/triton/backends/nvidia/bin/ptxas.exe'
            compiler.parent.mkdir(parents=True)
            compiler.touch()
            output = root / 'shared-output'
            config = dict(root=str(root), python=str(python), url='http://127.0.0.1:8188',
                          output_directory=str(output))
            response = Mock()
            response.status = 200
            response.read.return_value = json.dumps({'devices': [], 'system': {
                'argv': ['main.py', '--output-directory', str(output)]}}).encode()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            http = Mock()
            http.open.side_effect = [OSError('not running'), response]
            with patch.object(local_comfy, 'build_opener', return_value=http), \
                    patch('socket.socket') as socket, \
                    patch.object(local_comfy.subprocess, 'Popen') as start:
                socket.return_value.__enter__.return_value.connect_ex.return_value = 1
                start.return_value.pid = 123
                local_comfy.ensure_comfy(config, root / 'runtime')
            command = start.call_args.args[0]
            self.assertEqual(command[command.index('--output-directory') + 1], str(output))
            self.assertIn('--lowvram', command)
            self.assertTrue(output.is_dir())


if __name__ == '__main__':
    unittest.main()
