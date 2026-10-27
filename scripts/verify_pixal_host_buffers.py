"""Check actual inference feature values and ownership without loading models."""
import gc
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pixal_host_buffers import copy_features_to_cpu, cat_features_on_cpu


def main():
    torch.set_num_threads(2)
    for device in ('cpu', 'cuda'):
        if device == 'cuda' and not torch.cuda.is_available():
            continue
        for dtype in (torch.float32, torch.float16, torch.bfloat16):
            source = torch.linspace(-5, 5, 2 * 3 * 17 * 13, device=device, dtype=dtype).reshape(2, 3, 17, 13)
            for tensor in (source, source.transpose(-1, -2)):
                actual = copy_features_to_cpu(tensor)
                torch.testing.assert_close(actual, tensor.cpu(), rtol=0, atol=0)
                assert actual.dtype == tensor.dtype and actual.device.type == 'cpu'
                if device == 'cuda' and dtype == torch.float32:
                    owner = actual.numpy()
                    assert actual.data_ptr() == owner.__array_interface__['data'][0]
        parts = [torch.randn(31, channels, device=device).float() for channels in (12, 24)]
        staged = [copy_features_to_cpu(part) for part in parts]
        joined = cat_features_on_cpu(staged)
        torch.testing.assert_close(joined, torch.cat(parts, dim=-1).cpu(), rtol=0, atol=0)
        # A slice must keep its NumPy owner alive until its final consumer finishes.
        view = joined[3:7, :]
        expected = view.clone()
        del joined, staged
        gc.collect()
        torch.testing.assert_close(view, expected, rtol=0, atol=0)
        print(f'{device}: exact values, dtypes, strided inputs, concatenation, ownership OK')
    print('PASS')


if __name__ == '__main__':
    main()
