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
  # - kind=privateDatasetPath
  #   - relativePath: path relative to private-dataset
  #   - output: path, list, or pythonListSingleQuoted (default path)
  #
  # Examples (final JSON produced for an input named "files"):
  # - output = 'path' produces a single string value:
  #   "files": { "name": "files", "value": "D:/.../private-dataset/inputs/file.txt", "sub_plugs": {}, "connections": {} }
  # - output = 'list' produces a native JSON array:
  #   "files": { "name": "files", "value": [ "D:/.../private-dataset/inputs/file.txt" ], "sub_plugs": {}, "connections": {} }
  # - output = 'pythonListSingleQuoted' produces a Python-list-as-string (single-quoted):
  #   "files": { "name": "files", "value": "['D:/.../private-dataset/inputs/file.txt']", "sub_plugs": {}, "connections": {} }
  # - kind=findPath
  #   - roots: list of roots to search recursively
  #   - itemType: Directory or File (default Directory)
  #   - matchRegex: regex matched against full path
  #   - pick: first or all (default first)
  #   - output: path, list, or pythonListSingleQuoted (default path)
  # - kind=pythonDictFromFileMapping
  #   - fileSpec: nested value spec that resolves a single file path
  #   - mapping: key/value map used as dictionary content for that file
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
          kind = 'privateDatasetPath'
          relativePath = 'inputs/DOMINO_FILES/subject_3'
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

  ConvertEDFbrowser = @{
    targetToolName = 'ConvertEDFbrowser'
    processingMode = 'adapted'

    updates = @(
      @{
        identifier = '663cd8ee-9ca5-4956-9a4f-82561c6adadf'
        inputName = 'files'
        required = $true
        value = @{
          kind = 'privateDatasetPath'
          relativePath = 'inputs/learn-nsrr01_annotations.txt'
          output = 'list'
          required = $true
        }
      }
      @{
        identifier = 'a42e544f-13dc-4148-93fe-6493e383c417'
        inputName = 'dictionary'
        required = $true
        value = @{
          kind = 'pythonDictFromFileMapping'
          fileSpec = @{
            kind = 'privateDatasetPath'
            relativePath = 'inputs/learn-nsrr01_annotations.txt'
            required = $true
          }
          mapping = @{
            '0' = 'stage'
            '1' = 'stage'
            '2' = 'stage'
            '3' = 'stage'
            '5' = 'stage'
            'Arousal ()' = 'expert'
            'Hypopnea' = 'expert'
            'Obstructive Apnea' = 'expert'
            'SpO2 artifact' = 'SpO2'
            'SpO2 desaturation' = 'SpO2'
            'a4' = 'spindle'
            'a7' = 'spindle'
            'art_snooz' = 'art_snooz'
            'sumo' = 'spindle'
          }
          required = $true
        }
      }
    )
  }

  ConvertXMLCompumedics = @{
    targetToolName = 'ConvertXMLCompumedics'
    processingMode = 'adapted'

    # Each update defines one node, one input, and one value.
    updates = @(
      @{
        identifier = '57d3ca1c-dd68-4405-849d-da0279c9dc9d'
        inputName = 'filename'
        required = $true
        value = @{
        kind = 'findPath'
        roots = @('private-dataset/inputs')
        itemType = 'File'
        matchRegex = '(learn-nsrr01-profusion\.xml|learn-nsrr02-profusion\.xml)$'
        pick = 'all'
        output = 'pythonListSingleQuoted'
        required = $true
        }
      }
    )
  }

}

