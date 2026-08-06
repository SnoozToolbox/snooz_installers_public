#!/usr/bin/env python3
"""
Adapt JSON configuration files by substituting $GITHUB_WORKSPACE placeholder
with the actual GitHub workspace path from the runner environment.

This enables cross-platform (Windows/macOS/Linux) validation workflows.

Usage:
    python adapt_json_paths.py --workspace-root /path/to/workspace
"""

import json
import os
import sys
import argparse
from pathlib import Path


def adapt_json_file(file_path, workspace_root):
    """
    Read JSON file, replace $GITHUB_WORKSPACE with actual path, write back.
    
    Args:
        file_path: Path to the JSON file to adapt
        workspace_root: The actual GitHub workspace root path
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace placeholder with actual workspace path
        adapted_content = content.replace('$GITHUB_WORKSPACE', workspace_root)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(adapted_content)
        
        print(f"✓ Adapted: {file_path}")
        return True
        
    except Exception as e:
        print(f"✗ Error adapting {file_path}: {e}", file=sys.stderr)
        return False


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
    
    # Get the directory containing this script
    script_dir = Path(__file__).parent
    
    # Discover all JSON files in this directory (excluding subdirectories)
    json_files = sorted([f.name for f in script_dir.glob('*.json')])
    
    if not json_files:
        print(f"⚠ No JSON files found in {script_dir}")
        return 0
    
    print(f"Adapting JSON files using workspace root: {workspace_root}\n")
    print(f"Found {len(json_files)} JSON file(s) to process:")
    for json_file in json_files:
        print(f"  - {json_file}")
    print()
    
    success_count = 0
    for json_file in json_files:
        file_path = script_dir / json_file
        if adapt_json_file(str(file_path), workspace_root):
            success_count += 1
    
    print(f"\n✓ Successfully adapted {success_count}/{len(json_files)} files")
    
    if success_count == len(json_files):
        return 0
    else:
        return 1


if __name__ == '__main__':
    sys.exit(main())
