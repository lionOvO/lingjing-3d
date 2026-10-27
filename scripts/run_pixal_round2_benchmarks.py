"""Sequentially measure and audit three actual business graphs on one owned server."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--pid', required=True)
parser.add_argument('--log', type=Path, required=True)
parser.add_argument('--cases', nargs='+', choices=['person', 'robot', 'helmet'], default=['person', 'robot', 'helmet'])
parser.add_argument('--label-prefix', default='20261009-round2-core-meta-final')
parser.add_argument('--metrics-prefix', default='pixal-full-round2-core-meta')
parser.add_argument('--require-clean', action='store_true')
parser.add_argument('--save-prediction',action='store_true')
args = parser.parse_args()
cases = [('person', 'OIP_clean_1024_rgba.png', 'PixalPipeline_OIP_clean_1024_rgba_20261009-cache-fixed_API.json'),
         ('robot', 'robot.png', 'PixalPipeline_robot_20261009-cascade_API.json'),
         ('helmet', 'Helmet.png', 'PixalPipeline_Helmet_20261009-cascade_API.json')]
for category, image, workflow in cases:
    if category not in args.cases:
        continue
    label = f'{args.label_prefix}-{category}'
    print(f'START {category} {label}', flush=True)
    log_path = ROOT / f'tmp/pixal-round2-benchmark-{category}.log'
    with log_path.open('w', encoding='utf-8') as output:
        command=[sys.executable, '-u', str(ROOT / 'scripts/measure_pixal_full_pipeline.py'),
                        '--pid', args.pid, '--label', label, '--image', image,
                        '--workflow', str(ROOT / 'tmp' / workflow), '--log', str(args.log)]
        if args.save_prediction:command.append('--save-prediction')
        subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,check=True)
    manifest = ROOT / f'tmp/pixal-full-{label}-manifest.json'
    subprocess.run([sys.executable, str(ROOT / 'scripts/audit_pixal_generation.py'), str(manifest),
                    '--output', str(ROOT / f'tmp/{args.metrics_prefix}-{category}-metrics.json')], check=True)
    if args.require_clean:
        metrics = json.loads((ROOT / f'tmp/{args.metrics_prefix}-{category}-metrics.json').read_text(encoding='utf-8'))
        subprocess.run([sys.executable, str(ROOT / 'scripts/audit_pixal_mesh_quality.py'), metrics[0]['model'],
                        '--output', str(ROOT / f'tmp/{args.metrics_prefix}-{category}-quality.json'),
                        '--require-clean'], check=True)
    print(f'PASS {category}', flush=True)
print('SELECTED CASES COMPLETE; visual inspection still required.', flush=True)
