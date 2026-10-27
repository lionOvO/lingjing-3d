"""Apply the low-memory MoGe checkpoint loader, preserving the installed source."""
from pathlib import Path
import shutil

TARGET = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2\moge\model\v2.py')
OLD = """        checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
        
        model_config = checkpoint['model_config']
        if model_kwargs is not None:
            model_config.update(model_kwargs)
        model = cls(**model_config)
        model.load_state_dict(checkpoint['model'], strict=False)
"""
NEW = """        # Load checkpoint-backed storage directly instead of retaining two
        # full CPU copies during construction (important on 16 GB Windows).
        checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=True, mmap=True)

        model_config = dict(checkpoint['model_config'])
        if model_kwargs is not None:
            model_config.update(model_kwargs)
        from accelerate import init_empty_weights
        # Keep small computed buffers real; only parameters are placed on meta.
        # DINOv2's stochastic-depth schedule uses CPU tensor.item() in __init__.
        with init_empty_weights(include_buffers=False):
            model = cls(**model_config)
        model.load_state_dict(checkpoint['model'], strict=False, assign=True)
        unresolved = [name for name, value in list(model.named_parameters()) + list(model.named_buffers()) if value.is_meta]
        if unresolved:
            raise RuntimeError(f'MoGe checkpoint is missing tensors: {unresolved}')
"""

if __name__ == '__main__':
    source = TARGET.read_text(encoding='utf-8')
    if NEW in source:
        print('MoGe low-memory loader already installed')
    else:
        if source.count(OLD) != 1:
            raise RuntimeError('Unexpected MoGe loader source; no file was changed')
        backup = TARGET.with_suffix('.py.before-lingjing-mmap-20261019')
        if not backup.exists():
            shutil.copy2(TARGET, backup)
        TARGET.write_text(source.replace(OLD, NEW), encoding='utf-8')
        print('Installed MoGe low-memory loader; original source backed up')
