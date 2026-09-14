from __future__ import annotations
from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import zipfile

from mart_builder import make_share_snapshot, mart_status
from validate_snapshot import validate_snapshot

VERSION="v4.1"
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
MART=DATA/'investment_mart.sqlite'
if not mart_status(MART).get('ready'):
    raise SystemExit('ERROR: investment_mart.sqlite is not ready. Run build_marts.py first.')

stamp=datetime.now().strftime('%Y%m%d_%H%M')
out_zip=ROOT/f'investment_advisor_v4.1_COMPANY_{stamp}.zip'
include_files=[
    'app.py','dashboard_utils.py','deployment_mode.py','validate_snapshot.py','export_analytics.py','flash_trade.py','mart_builder.py',
    'kosis_cache.py','kosis_client.py','customs_pipeline.py','display_labels.py','hsk_labels.py',
    'requirements.txt','START_MAC.command','START_WINDOWS.bat','README_PORTABLE.md','README_COMPANY.md','README_DEPLOY.md'
]
include_data=[
    'export_flash_seed.csv','export_flash_cache.csv','industry_export_bridge.csv',
    'motir20_hsk_mti_mapping_2026.csv','motir20_hsk_mti_mapping_2026_full_clean.csv',
    'hsk10_display_labels_2026.csv','company_exposure.csv','company_exposure_template.csv'
]
with tempfile.TemporaryDirectory() as td:
    base=Path(td)/'investment_advisor_READY_v4.1_COMPANY'
    (base/'data').mkdir(parents=True)
    for name in include_files:
        src=ROOT/name
        if src.exists(): shutil.copy2(src,base/name)
    for name in include_data:
        src=DATA/name
        if src.exists(): shutil.copy2(src,base/'data'/name)
    make_share_snapshot(MART,base/'data'/'share_snapshot.sqlite')
    validate_snapshot(base/'data'/'share_snapshot.sqlite')
    # Portable package intentionally has no secrets.toml and no raw DB.
    (base/'.streamlit').mkdir(exist_ok=True)
    cfg=ROOT/'.streamlit'/'config.toml'
    if cfg.exists(): shutil.copy2(cfg,base/'.streamlit'/'config.toml')
    with zipfile.ZipFile(out_zip,'w',zipfile.ZIP_DEFLATED) as z:
        for p in base.rglob('*'):
            if p.is_file(): z.write(p,p.relative_to(Path(td)))
print(out_zip)
