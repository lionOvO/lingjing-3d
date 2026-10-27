"""Bounded, isolated probe of NAF-sized CPU/GPU tensor allocations.

Does not start ComfyUI, change the pipeline, or submit generation tasks.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import gc
import json
import os
from pathlib import Path
import time
import weakref

GIB = 1024 ** 3
ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'tmp/memory-investigation-20261022'
DIRECTORY.mkdir(exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('--size', type=int, choices=(512, 1024), default=512)
parser.add_argument('--mode', choices=('cpu', 'gpu', 'copy'), default='copy')
parser.add_argument('--allocator', choices=('native', 'cudaMallocAsync'), default='cudaMallocAsync')
parser.add_argument('--purge-delay', type=int, default=None)
parser.add_argument('--label', default='')
parser.add_argument('--host-buffer', choices=('torch', 'numpy'), default='torch')
args = parser.parse_args()
suffix = '' if args.purge_delay is None else f'-purge{args.purge_delay}'
if args.label:
    if not args.label.replace('-', '').isalnum():
        parser.error('label must be alphanumeric or hyphenated')
    suffix += '-' + args.label
suffix += '-' + args.host_buffer
REPORT = DIRECTORY / f'{args.mode}-{args.size}-{args.allocator}{suffix}.json'
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = f'backend:{args.allocator}'
if args.purge_delay is not None:
    os.environ['MIMALLOC_PURGE_DELAY'] = str(args.purge_delay)


class PerformanceInfo(c.Structure):
    _fields_ = [('cb', w.DWORD)] + [(name, c.c_size_t) for name in (
        'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal',
        'PhysicalAvailable', 'SystemCache', 'KernelTotal', 'KernelPaged',
        'KernelNonpaged', 'PageSize')] + [(name, w.DWORD) for name in (
        'HandleCount', 'ProcessCount', 'ThreadCount')]


class ProcessMemory(c.Structure):
    _fields_ = [('cb', w.DWORD), ('PageFaultCount', w.DWORD)] + [
        (name, c.c_size_t) for name in (
            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage',
            'PrivateUsage')]


psapi = c.WinDLL('psapi', use_last_error=True)
kernel = c.WinDLL('kernel32', use_last_error=True)
kernel.GetCurrentProcess.restype = w.HANDLE
psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, c.POINTER(ProcessMemory), w.DWORD]
rows = []


def snapshot(stage):
    system = PerformanceInfo(cb=c.sizeof(PerformanceInfo))
    process = ProcessMemory(cb=c.sizeof(ProcessMemory))
    if not psapi.GetPerformanceInfo(c.byref(system), system.cb):
        raise c.WinError(c.get_last_error())
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), c.byref(process), process.cb):
        raise c.WinError(c.get_last_error())
    row = dict(stage=stage, time=time.time(),
               system_commit_bytes=system.CommitTotal * system.PageSize,
               system_limit_bytes=system.CommitLimit * system.PageSize,
               process_private_bytes=process.PrivateUsage,
               available_ram_bytes=system.PhysicalAvailable * system.PageSize)
    rows.append(row)
    if 'torch' in globals() and torch.cuda.is_initialized():
        row.update(cuda_allocated=torch.cuda.memory_allocated(), cuda_reserved=torch.cuda.memory_reserved())
    print(json.dumps(row), flush=True)
    REPORT.write_text(json.dumps(dict(settings=vars(args), rows=rows), indent=2), encoding='utf-8')
    return row


before = snapshot('before_torch_import')
if before['system_limit_bytes'] - before['system_commit_bytes'] < 6 * GIB:
    raise SystemExit('Probe skipped: less than 6 GiB commit headroom')

import torch
import numpy as np

torch.set_num_threads(2)
if args.mode != 'cpu':
    torch.cuda.init()
row = snapshot('runtime_initialized')
if row['system_limit_bytes'] - row['system_commit_bytes'] < 4 * GIB:
    raise SystemExit('Probe skipped: insufficient headroom after CUDA initialization')

for cycle in range(3):
    guard = snapshot(f'{cycle}_guard')
    if (guard['system_limit_bytes'] - guard['system_commit_bytes'] < 2 * GIB
            or guard['available_ram_bytes'] < 512 * 1024 ** 2):
        raise SystemExit('Probe stopped: memory headroom below safety threshold')
    # Installed NAF: dim=256, FP32, batch=1; shape target=512, texture target=1024.
    shape = (1, 256, args.size, args.size)
    if args.mode == 'cpu' and args.host_buffer == 'numpy':
        query = torch.from_numpy(np.ones(shape, dtype=np.float32))
    else:
        query = torch.ones(shape, device='cpu' if args.mode == 'cpu' else 'cuda', dtype=torch.float32)
    if args.mode != 'cpu':
        torch.cuda.synchronize()
    snapshot(f'{cycle}_query_allocated')
    print(json.dumps(dict(cycle=cycle, data_ptr=query.data_ptr())), flush=True)
    query_ref = weakref.ref(query)
    if args.mode == 'copy':
        if args.host_buffer == 'numpy':
            cpu = torch.from_numpy(np.empty(tuple(query.shape), dtype=np.float32))
            cpu.copy_(query, non_blocking=False)
        else:
            cpu = query.cpu()
        assert cpu.numel() * cpu.element_size() == 256 * args.size ** 2 * 4
        assert cpu[0, 0, 0, 0].item() == 1
        snapshot(f'{cycle}_query_copied_to_cpu')
        del cpu
    del query
    gc.collect()
    assert query_ref() is None, 'Tensor still referenced'
    if args.mode != 'cpu':
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
    snapshot(f'{cycle}_released')
    time.sleep(1)
    tiny = torch.ones(1)
    del tiny
    snapshot(f'{cycle}_after_delay')

snapshot('completed')
