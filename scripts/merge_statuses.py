#!/usr/bin/env python3
import csv
from pathlib import Path
import sys

OS_FILES = {
    'Windows': 'os_status_files/tool-run-summary-windows.tsv',
    'macOS-x64': 'os_status_files/tool-run-summary-macosx64.tsv',
    'macOS-arm64': 'os_status_files/tool-run-summary-macosarm64.tsv',
    'Linux': 'os_status_files/tool-run-summary-linux.tsv',
}

OUT_DIR = Path('consolidated-results')
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / 'tool-run-summary-all-platforms.tsv'

HEADER = [
    'Tool', 'Version', 'Scenario',
    'Run Status Windows', 'Comparison Status Windows',
    'Run Status macOS-x64', 'Comparison Status macOS-x64',
    'Run Status macOS-arm64', 'Comparison Status macOS-arm64',
    'Run Status Linux', 'Comparison Status Linux',
    'Validated Files'
]


def read_tsv(path):
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline='', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        rows = list(reader)
    if not rows:
        return []
    hdr = rows[0]
    data = []
    for r in rows[1:]:
        # pad row
        if len(r) < len(hdr):
            r += [''] * (len(hdr) - len(r))
        data.append(dict(zip(hdr, r)))
    return data


def get_field(row, names):
    for n in names:
        if n in row and row[n] != '':
            return row[n]
    return ''


def main():
    # map key -> consolidated row
    store = {}

    for os_label, path in OS_FILES.items():
        rows = read_tsv(path)
        if not rows:
            print(f'Warning: no data for {os_label} (looking at {path})', file=sys.stderr)
            continue
        for r in rows:
            tool = get_field(r, ['tool_name', 'Tool', 'Tool Name'])
            version = get_field(r, ['tool_version', 'Version'])
            scenario = get_field(r, ['json_name', 'scenario', 'Scenario'])
            runstat = get_field(r, ['run_status', 'status', 'Run Status'])
            compstat = get_field(r, ['comparison_status', 'comparison', 'Comparison Status'])
            vfiles = get_field(r, ['validated_files', 'validated_files_count', 'Validated Files'])

            key = f'{tool}||{scenario}'
            if key not in store:
                store[key] = {
                    'Tool': tool,
                    'Version': version,
                    'Scenario': scenario,
                    'Run Status Windows': '', 'Comparison Status Windows': '',
                    'Run Status macOS-x64': '', 'Comparison Status macOS-x64': '',
                    'Run Status macOS-arm64': '', 'Comparison Status macOS-arm64': '',
                    'Run Status Linux': '', 'Comparison Status Linux': '',
                    'Validated Files': vfiles,
                }
            # update fields
            entry = store[key]
            if os_label == 'Windows':
                entry['Run Status Windows'] = runstat
                entry['Comparison Status Windows'] = compstat
            elif os_label == 'macOS-x64':
                entry['Run Status macOS-x64'] = runstat
                entry['Comparison Status macOS-x64'] = compstat
            elif os_label == 'macOS-arm64':
                entry['Run Status macOS-arm64'] = runstat
                entry['Comparison Status macOS-arm64'] = compstat
            elif os_label == 'Linux':
                entry['Run Status Linux'] = runstat
                entry['Comparison Status Linux'] = compstat
            # prefer non-empty validated files
            if vfiles:
                entry['Validated Files'] = vfiles

    # write output
    with OUT_PATH.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(HEADER)
        for key in sorted(store.keys()):
            e = store[key]
            row = [e.get(h, '') for h in HEADER]
            writer.writerow(row)

    print('Wrote consolidated summary to', OUT_PATH)


if __name__ == '__main__':
    main()
