"""Guard the real asset workflow against simplifying an unreconstructed grid."""
import json
import unittest
from generate_home_pine import build_workflow, ROOT


class PineWorkflowTests(unittest.TestCase):
    def test_textureless_geometry_is_reconstructed_before_simplification(self):
        graph = build_workflow('test-reference.png')
        self.assertFalse(graph['45']['inputs']['generate_texture_slat'])
        converter = graph['70']['inputs']['trimesh'][0]
        reconstruction = graph[converter]['inputs']['mesh'][0]
        self.assertEqual(graph[reconstruction]['class_type'], 'Trellis2ReconstructMeshWithQuad_GGUF')
        self.assertEqual(graph[reconstruction]['inputs']['mesh'], ['45', 0])
        self.assertEqual(graph['71']['inputs']['trimesh'], ['70', 0])
        self.assertEqual(graph['19']['inputs']['trimesh'], ['71', 0])

    def test_preserves_reference_seed_and_platform_template(self):
        path = ROOT / 'services/trellis/workflow_6gb.json'
        before = path.read_bytes()
        graph = build_workflow('test-reference.png')
        self.assertEqual(graph['6']['inputs']['image'], 'test-reference.png')
        self.assertEqual(graph['45']['inputs']['seed'], 20261027)
        self.assertEqual(graph['45']['inputs']['shape_steps'], 16)
        self.assertFalse(graph['55']['inputs']['remove_background'])
        graph['45']['inputs']['shape_steps'] = 99
        self.assertEqual(build_workflow('second.png')['45']['inputs']['shape_steps'], 16)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads(before)['45']['inputs']['pipeline_type'], '1024_cascade')


if __name__ == '__main__':
    unittest.main()
