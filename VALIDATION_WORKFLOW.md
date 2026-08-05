# Snooz Validation Workflow

## Overview

This workflow automates the validation of Snooz tools by:

1. Downloading PSG files from a private repository
2. Extracting tool definitions from the Snooz installer  
3. Adapting their JSON files to define inputs, outputs, and required parameters
4. Executing Snooz with each tool individually
5. Comparing generated outputs against a gold-standard repository
6. Recording validation results in an artifact

## Workflow Diagram

```mermaid
graph TD
    A["📥 Download PSG files<br/>from private repository"] --> B["📦 Download Snooz<br/>installer"]
    B --> C["⚙️ Install Snooz and extract<br/>tool JSON files empty form"]
    C --> D["🔧 Modify JSON files<br/>Inputs | Outputs | Parameters"]
    D --> E["▶️ Execute Snooz<br/>for each tool individually"]
    E --> F["📊 Compare outputs<br/>vs. Gold-Standard repository"]
    F --> G["✅ Save status file artifact<br/>Tool versions | Results | Comparison"]
    G --> H["📁 GitHub Artifact<br/>Adapted JSON | Logs | Summary"]
    
    style A fill:#e1f5ff,stroke:#01579b,color:#000
    style B fill:#e1f5ff,stroke:#01579b,color:#000
    style C fill:#fff3e0,stroke:#e65100,color:#000
    style D fill:#fff3e0,stroke:#e65100,color:#000
    style E fill:#f3e5f5,stroke:#4a148c,color:#000
    style F fill:#f3e5f5,stroke:#4a148c,color:#000
    style G fill:#e8f5e9,stroke:#1b5e20,color:#000
    style H fill:#e8f5e9,stroke:#1b5e20,color:#000
```

## Phases

### 🔵 Preparation Phase
- Download PSG files from private dataset repository
- Download Snooz installer release

### 🟠 Configuration Phase
- Install Snooz application
- Extract empty tool JSON files from package resources
- Modify JSON files with validation-specific inputs, outputs, and parameters

### 🟣 Execution Phase
- Execute Snooz headless mode for each configured tool
- Generate output artifacts (TSV files, logs, etc.)

### 🟢 Validation Phase
- Compare generated outputs with gold-standard reference files
- Record tool versions and comparison results
- Save comprehensive status report as GitHub artifact

## Key Features

- **CEAMS Compatibility**: JSON modifications remain compatible with future CEAMS package versions
- **Automated Testing**: Headless execution ensures consistent, reproducible results
- **Version Tracking**: Records exact tool versions and execution details
- **Output Validation**: Automated comparison against gold-standard repository
- **Artifact Recording**: Comprehensive logs and status files for audit trail

## Output Artifacts

- Adapted JSON scenario files
- Snooz process logs and execution logs
- Tool run summary (TSV format)
- Comparison results for each validated output
- Generated vs. reference file pairs
