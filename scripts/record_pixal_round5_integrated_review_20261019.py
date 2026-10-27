"""Record the human-visible model review after the completed final execution."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / 'tmp'
def read(name):
    return json.loads((TMP / name).read_text(encoding='utf-8'))

job = read('pixal-full-round5-final-chain-person-20261019-manifest.json')[0]
history = json.loads(Path(job['history_path']).read_text(encoding='utf-8'))
assert history['status']['completed'] and history['status']['status_str'] == 'success'
assert read('pixal-round5-preview-verified-20261019.json')['completed']
assert len(read('pixal-round5-integrated-renders-20261019.json')) == 12
for name in ('pixal-round5-visual-assessment-20261019.json', 'pixal-round5-final-installed-20261019.json'):
    source = TMP / name
    backup = source.with_name(source.stem + '-before-integrated.json')
    assert not backup.exists()
    backup.write_bytes(source.read_bytes())

review = read('pixal-round5-visual-assessment-20261019.json')
review.update(integrated_actually_viewed=True, final_prompt_id=job['prompt_id'],
              acceptance_scope='Final combined production code completed a fresh full person generation; PBR and base-color front/angle/top before-after renders were actually viewed. Robot and helmet remain saved-neural cleanup replays, not fresh NAF generations.')
review['findings'].append('Final full-run renders confirm reduced facial yellow-white bands and recovery of large hair regions lost to premature cleanup. Fine hair, eye, neck and shoulder defects remain visible.')
review['findings'].append('Final neural arrays match the intermediate prediction byte-for-byte. Exported mesh counts differ slightly from standalone replay; no claim of bitwise reproducible postprocessing is made.')
(TMP / 'pixal-round5-visual-assessment-20261019.json').write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
installed = read('pixal-round5-final-installed-20261019.json')
installed.update(validation_mode='Final combined source completed fresh full person generation and actual multi-view rendering; additionally three saved-neural cleanup cases used the same installed postprocess AST.',
                 integrated_full_generation_verified=True, final_prompt_id=job['prompt_id'])
installed['naf']['state'] = 'installed_full_generation_verified'
(TMP / 'pixal-round5-final-installed-20261019.json').write_text(json.dumps(installed, ensure_ascii=False, indent=2), encoding='utf-8')
print(job['prompt_id'])
