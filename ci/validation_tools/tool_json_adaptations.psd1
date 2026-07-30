@{
  # Human-friendly adaptation rules applied to extracted JSON files.
  # One top-level key per tool basename (without .json).
  #
  # Workflow dataset root used by adaptations:
  # - private-dataset: validation release assets from SnoozToolbox/snooz-datasets-private
  # Validation rule: private-dataset is the single source of truth.
  #
  # Tool-level keys:
  # - targetToolName: logical tool name written to metadata.toolName
  # - processingMode: optional value written to metadata.processingMode
  # - updates: list of input updates to apply in process_params.nodes
  #
  # updates[] specification:
  # - identifier: node identifier to target
  # - inputName: input name to modify on the target node
  # - value: value specification used to compute the final input value
  # - required: true/false (default true)
  #   - true: fail if the target identifier/input is not found or the value cannot be resolved
  #   - false: skip silently if identifier/input is absent or the value cannot be resolved
  #
  # value specification:
  # - kind=literal
  #   - value: fixed string value
  # - kind=workspacePath
  #   - relativePath: path relative to validation-workspaces
  # - kind=findPath
  #   - roots: list of roots to search recursively
  #   - itemType: Directory or File (default Directory)
  #   - matchRegex: regex matched against full path
  #   - pick: first or all (default first)
  #   - output: path or pythonListSingleQuoted (default path)
  # - required: true/false (default true)
  #   - true: fail fast if value/path cannot be resolved
  #   - false: allow missing value and continue (empty substitution)

  ConvertDOMINO = @{
    targetToolName = 'ConvertDOMINO'
    processingMode = 'adapted'

    # Each update defines one node, one input, and one value.
    updates = @(
      @{
        identifier = 'f2492f99-7965-4c48-9aec-7970891415f1'
        inputName = 'folders'
        required = $true
        value = @{
          kind = 'findPath'
          # In this workflow, 'private-dataset' is the validation dataset root.
          roots = @('private-dataset')
          itemType = 'Directory'
          matchRegex = '[\\/]DOMINO_FILES[\\/]subject_3$'
          # The folder is expected to be unique.
          pick = 'first'
          output = 'pythonListSingleQuoted'
          required = $true
        }
      }
      @{
        identifier = 'f2492f99-7965-4c48-9aec-7970891415f1'
        inputName = 'log_filename'
        required = $true
        value = @{
          kind = 'workspacePath'
          relativePath = 'logs/DOMINO_log.tsv'
          required = $true
        }
      }
    )
  }
}
