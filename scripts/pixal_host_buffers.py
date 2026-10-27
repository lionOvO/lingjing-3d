"""Host staging for inference features on Windows PyTorch.

NumPy owns these buffers so dropping a staged tensor returns large allocations
to the OS instead of retaining them in the installed torch CPU allocator.
No precision conversion, resampling, or change to neural features is performed.
"""
import os

import numpy as np
import torch


def _check_host_capacity(required):
    if os.name != 'nt' or required < 32 * 1024 ** 2:
        return
    import ctypes
    from ctypes import wintypes
    class PerformanceInfo(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
            'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal',
            'PhysicalAvailable', 'SystemCache', 'KernelTotal', 'KernelPaged',
            'KernelNonpaged', 'PageSize')] + [(name, wintypes.DWORD) for name in (
                'HandleCount', 'ProcessCount', 'ThreadCount')]
    info = PerformanceInfo(cb=ctypes.sizeof(PerformanceInfo))
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
        raise ctypes.WinError()
    available = (info.CommitLimit - info.CommitTotal) * info.PageSize
    print(f'[Pixal3D host buffer] commit={info.CommitTotal * info.PageSize / 2**30:.2f}/'
          f'{info.CommitLimit * info.PageSize / 2**30:.2f} GiB, copy={required / 2**20:.1f} MiB', flush=True)
    if available < required + 256 * 1024 ** 2:
        raise MemoryError('系统提交内存余量不足，已停止分配大型特征缓冲区；请释放后台内存后重试。')


def copy_features_to_cpu(source):
    if os.name != 'nt' or source.device.type == 'cpu' or source.dtype != torch.float32:
        return source.cpu()
    _check_host_capacity(source.numel() * source.element_size())
    destination = torch.from_numpy(np.empty(tuple(source.shape), dtype=np.float32))
    # A blocking copy is required before the source CUDA storage can be released.
    destination.copy_(source.detach(), non_blocking=False)
    return destination


def cat_features_on_cpu(parts, dim=-1):
    if (os.name == 'nt' and all(part.device.type == 'cpu' and part.dtype == torch.float32
                               for part in parts)):
        _check_host_capacity(sum(part.numel() * part.element_size() for part in parts))
        return torch.from_numpy(np.concatenate([part.detach().numpy() for part in parts], axis=dim))
    return torch.cat(parts, dim=dim)
