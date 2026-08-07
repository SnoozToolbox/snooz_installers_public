#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adapt JSON configuration files for cross-platform (Windows/macOS/Linux) validation.

Replaces $GITHUB_WORKSPACE placeholder with the actual runner workspace path,
enabling consistent path resolution across all platforms.

Usage:
    python adapt_json_paths.py --workspace-root /path/to/workspace
"""

import json
import os
import sys
import argparse
from pathlib import Path

# Force UTF-8 encoding on stdout for cross-platform compatibility (especially Windows)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def adapt_json_file(file_path, workspace_root):
    """
    Read JSON file and replace $GITHUB_WORKSPACE placeholder with actual runner path.
    
    Args:
        file_path: Path to the JSON file to adapt
        workspace_root: The actual GitHub workspace root path
        
    Returns:
        Tuple of (True/False if changes made, count of replacements)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Normalize workspace_root to forward slashes for JSON compatibility
        workspace_root_normalized = workspace_root.replace('\\', '/')
        
        # Replace $GITHUB_WORKSPACE placeholder with actual workspace path
        # Count replacements to know if file was actually changed
        adapted_content = content.replace('$GITHUB_WORKSPACE', workspace_root_normalized)
        replacement_count = content.count('$GITHUB_WORKSPACE')
        
        # Only write if something changed
        if replacement_count > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(adapted_content)
            print(f"[OK] Adapted: {file_path} ({replacement_count} replacement(s))")
            return True, replacement_count
        else:
            print(f"[SKIP] No replacements needed: {file_path}")
            return False, 0
        
    except Exception as e:
        print(f"[ERROR] Error adapting {file_path}: {e}", file=sys.stderr)
        return False, 0


def main():
    parser = argparse.ArgumentParser(
        description='Adapt JSON configuration files for cross-platform validation'
    )
    parser.add_argument(
        '--workspace-root',
        required=True,
        help='The GitHub workspace root path (usually ${{ github.workspace }})'
    )
    
    args = parser.parse_args()
    workspace_root = args.workspace_root
    
    print(f"Adapting JSON files using workspace root: {workspace_root}\n")
    
    # Directories to scan for JSON files
    directories_to_scan = [
        Path(__file__).parent,  # ci/validation_tools/
        Path(__file__).parent.parent.parent / "validation-workspaces"  # validation-workspaces/ (Linux/macOS)
    ]
    
    all_json_files = {}
    total_files = 0
    total_replacements = 0
    
    for scan_dir in directories_to_scan:
        if not scan_dir.exists():
            continue
        
        # Find all JSON files (non-recursive for config dir, recursive for validation-workspaces)
        is_validation_dir = "validation-workspaces" in str(scan_dir)
        if is_validation_dir:
            json_files = list(scan_dir.glob('**/*.json'))
        else:
            json_files = list(scan_dir.glob('*.json'))
        
        if not json_files:
            continue
        
        print(f"\n[{scan_dir.name}]")
        print(f"Found {len(json_files)} JSON file(s):")
        
        for json_file in sorted(json_files):
            relative_path = json_file.relative_to(scan_dir.parent) if is_validation_dir else json_file.name
            print(f"  - {relative_path}")
            
            changed, replacements = adapt_json_file(str(json_file), workspace_root)
            if changed:
                total_replacements += replacements
            total_files += 1
    
    if total_files == 0:
        print(f"\n[WARNING] No JSON files found in any scan directory")
        return 0
    
    print(f"\n[OK] Successfully adapted {total_files} file(s) with {total_replacements} total replacement(s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
