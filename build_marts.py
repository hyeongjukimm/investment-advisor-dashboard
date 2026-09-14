from pathlib import Path
from mart_builder import build_analysis_mart, mart_status

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
raw=DATA/'investment_advisor.sqlite'
mart=DATA/'investment_mart.sqlite'
tax=DATA/'motir20_hsk_mti_mapping_2026_full_clean.csv'
kosis=DATA/'kosis_cycle_cache.csv'
bridge=DATA/'industry_export_bridge.csv'
if not raw.exists():
    raise SystemExit('ERROR: data/investment_advisor.sqlite not found. Run MIGRATE_FROM_V3_2 first or build the raw DB.')
print('Building compact v4.1 analysis mart...')
result=build_analysis_mart(raw,mart,tax,kosis,bridge)
for k,v in result.items(): print(f'{k}: {v}')
print('status:',mart_status(mart))
