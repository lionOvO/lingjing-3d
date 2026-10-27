"""Apply the narrow GGUF flow-model placeholder allocation change."""
from pathlib import Path

path = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\models\__init__.py')
backup = path.with_name(path.name + '.bak-before-gguf-meta-20261009')
assert not backup.exists()
source = path.read_text(encoding='utf-8')
backup.write_bytes(path.read_bytes())
source = source.replace('    # Build model (skip random init for speed)\n', '''    # GGUF flow weights are assigned directly; avoid dense temporary storage.
    meta_gguf = is_gguf and config['name'] in {
        'SparseStructureFlowModel', 'SLatFlowModel', 'ElasticSLatFlowModel'
    }
    # Build model (skip random init for speed)
''', 1)
source = source.replace('        model = model_class(**final_args)\n', '''        if meta_gguf:
            with torch.device('meta'):
                model = model_class(**final_args)
                model = gguf_utils.convert_to_ggml(model)
        else:
            model = model_class(**final_args)
''', 1)
source = source.replace('    if is_gguf:\n        model = gguf_utils.convert_to_ggml(model)\n', '    if is_gguf and not meta_gguf:\n        model = gguf_utils.convert_to_ggml(model)\n', 1)
source = source.replace('    model.load_state_dict(sd, strict=False)\n', '''    if meta_gguf:
        # Match the former copy_ destination dtype for unquantized tensors.
        # Own their writable storage; quantized tensors retain the GGML loader.
        placeholders = model.state_dict()
        for key, value in sd.items():
            if key in placeholders and getattr(value, 'tensor_type', None) in {None, 0, 1}:
                plain = value.as_subclass(torch.Tensor) if type(value) is not torch.Tensor else value
                sd[key] = plain.to(dtype=placeholders[key].dtype, copy=True)
        model.load_state_dict(sd, strict=False, assign=True)
    else:
        model.load_state_dict(sd, strict=False)
''', 1)
source = source.replace('            coords = torch.meshgrid(*[torch.arange(res, device=model.rope_phases.device) for res in [model.resolution] * 3], indexing=\'ij\')', '''            rope_device = next(model.parameters()).device if meta_gguf else model.rope_phases.device
            coords = torch.meshgrid(*[torch.arange(res, device=rope_device) for res in [model.resolution] * 3], indexing='ij')''', 1)
source = source.replace('            model.rope_phases.copy_(rope_phases)', '''            if meta_gguf:
                model.rope_phases = rope_phases
            else:
                model.rope_phases.copy_(rope_phases)''', 1)
source = source.replace('    return model\n\n\n# For Pylance', '''    if meta_gguf:
        unmaterialized = [name for name, value in list(model.named_parameters()) + list(model.named_buffers()) if value.is_meta]
        if unmaterialized:
            raise RuntimeError(f"GGUF checkpoint left tensors unmaterialized: {', '.join(unmaterialized[:5])}")
    return model


# For Pylance''', 1)
assert source != backup.read_text(encoding='utf-8')
compile(source, str(path), 'exec')
path.write_text(source, encoding='utf-8')
print(path)
