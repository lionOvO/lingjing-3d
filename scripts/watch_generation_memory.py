"""Record host commit during one authorized regression run; stop at low headroom."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import time
from urllib.request import build_opener, ProxyHandler, Request

parser = argparse.ArgumentParser()
parser.add_argument('--task', type=int, required=True)
parser.add_argument('--engine-pid', type=int, required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
out = root / 'tmp/memory-investigation-20261022' / (args.label + '.jsonl')


class PerformanceInfo(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
        'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal',
        'PhysicalAvailable', 'SystemCache', 'KernelTotal', 'KernelPaged',
        'KernelNonpaged', 'PageSize')] + [(name, wintypes.DWORD) for name in (
            'HandleCount', 'ProcessCount', 'ThreadCount')]


class ProcessMemory(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]


kernel = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD)
handle = kernel.OpenProcess(0x0400 | 0x0010, False, args.engine_pid)
http = build_opener(ProxyHandler({}))
start = time.monotonic()
status = None
interrupted = False
try:
    with out.open('x', encoding='utf-8') as stream:
        while time.monotonic() - start < 3600:
            info = PerformanceInfo(cb=ctypes.sizeof(PerformanceInfo))
            process = ProcessMemory(cb=ctypes.sizeof(ProcessMemory))
            if not psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
                raise ctypes.WinError()
            alive = bool(handle and psapi.GetProcessMemoryInfo(handle, ctypes.byref(process), process.cb))
            row = dict(time=time.time(), elapsed=time.monotonic() - start,
                       commit=info.CommitTotal * info.PageSize, limit=info.CommitLimit * info.PageSize,
                       available_ram=info.PhysicalAvailable * info.PageSize,
                       engine_private=process.PrivateUsage, engine_working_set=process.WorkingSetSize,
                       engine_alive=alive)
            if int(row['elapsed']) % 10 < 2:
                try:
                    with http.open(f'http://127.0.0.1:8000/api/v1/tasks/{args.task}', timeout=3) as response:
                        task = json.load(response)
                    status = task['status']
                    row.update(status=status, error=task.get('error_message'))
                except Exception as exc:
                    row['monitor_error'] = type(exc).__name__
            if row['limit'] - row['commit'] < 1024 ** 3 and not interrupted:
                try:
                    with http.open(Request('http://127.0.0.1:8188/interrupt', data=b'{}',
                                           headers={'Content-Type': 'application/json'}), timeout=3):
                        pass
                    row['guard_interrupt'] = True
                    interrupted = True
                except Exception as exc:
                    row['interrupt_error'] = type(exc).__name__
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            if int(row['elapsed']) % 30 < 2 or status in ('completed', 'failed'):
                print(json.dumps(row, ensure_ascii=False), flush=True)
            if status in ('completed', 'failed'):
                break
            time.sleep(2)
finally:
    if handle:
        kernel.CloseHandle(handle)
