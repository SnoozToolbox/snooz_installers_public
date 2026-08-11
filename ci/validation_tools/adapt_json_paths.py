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
    
    # Only scan validation-workspaces directory for actual scenario JSON files
    # Configuration files in ci/validation_tools/ should NOT be adapted
    validation_workspace_dir = Path(__file__).parent.parent.parent / "validation-workspaces"
    
    if not validation_workspace_dir.exists():
        print(f"[WARNING] validation-workspaces directory not found at {validation_workspace_dir}")
        print("This is expected on Windows where PowerShell handles JSON adaptation separately.")
        return 0
    
    # Find all JSON files in validation-workspaces (recursive)
    json_files = sorted(validation_workspace_dir.glob('**/*.json'))
    
    if not json_files:
        print(f"[WARNING] No JSON files found in {validation_workspace_dir}")
        return 0
    
    print(f"[validation-workspaces]")
    print(f"Found {len(json_files)} JSON scenario file(s):")
    
    total_replacements = 0
    for json_file in json_files:
        relative_path = json_file.relative_to(validation_workspace_dir.parent)
        print(f"  - {relative_path}")
        
        changed, replacements = adapt_json_file(str(json_file), workspace_root)
        if changed:
            total_replacements += replacements
    
    print(f"\n[OK] Successfully adapted {len(json_files)} scenario file(s) with {total_replacements} total replacement(s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
