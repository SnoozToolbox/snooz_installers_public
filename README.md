# What is this repository?

This repository is used to generate installers for the Snooz Toolbox application.

# Where does it happen?
The workflow that contains the installer jobs is located at `.github/workflows/installers_creation.yml`.

# How to run the workflow

- Go to the Actions tab.
- Select Build Binaries in the left panel.
- Click Run workflow in the top-right drop-down menu.
  - Select the jobs to run.
  - Define the source repository (default: SnoozToolbox/snooz-toolbox).
  - Define the branch (default: main).

## Validation flow strategy

The long-term plan is to keep installer creation and installer validation in separate workflows.

- The build workflow produces versioned installer artifacts.
- The validation workflow downloads a completed release candidate and runs the real Snooz Toolbox tools in headless mode.
- Validation scenarios are described in JSON files, with expected outputs stored as private gold standards when needed.
- A private dataset repository can be used for sensitive test inputs, including PSG recordings.
- Each validation run should write a full report with the tool name, tool version, execution status, and output comparison result.

The goal is to validate the shipped installer exactly as users will run it, not to rebuild the application during the validation step.

## CI validation folders and files to maintain

Validation assets are under [ci/validation_tools](ci/validation_tools).

Files to maintain:

- [ci/validation_tools/tool_json_adaptations.psd1](ci/validation_tools/tool_json_adaptations.psd1): per-tool rules used to adapt process JSON inputs for CI headless runs.
- [ci/validation_tools/tool_validations.json](ci/validation_tools/tool_validations.json): per-tool rules used to validate generated outputs against gold standards.

Note: the adaptation file used in this repository is [ci/validation_tools/tool_json_adaptations.psd1](ci/validation_tools/tool_json_adaptations.psd1) (not tool_json_adaptation.json).

## 🔐 API Token Setup

To enable GitHub Actions to build installers using this repository, configure the GitHub API token secret used by the workflow: `GH_PAT`.

---

### 1. Create a Personal Access Token (PAT)

Generate a GitHub Personal Access Token and add it to your repository secrets:

- Go to: https://github.com/settings/personal-access-tokens
- Select **Fine-grained tokens**
- Ensure access is granted to the `SnoozToolbox` organization (and SSO is authorized if required)
- Click **Generate new token**

1. Go to: **Settings → Secrets and variables → Actions → Repository secrets**
2. Click **New repository secret**
3. Name it: `GH_PAT`
4. Paste your token value

#### Required permissions (Fine-grained token):
- **Repository access**: Select the target repository (or all repositories if needed)
- **Permissions**:
  - `Contents: Read`
  - `Metadata (Required): Read`

#### Organization access (important)

If the target repositories are in the `SnoozToolbox` organization, the token owner must be allowed to access that organization and its repositories (including SSO authorization if your organization requires it). Otherwise, GitHub Actions will fail to read private repositories or release assets.

You do **not** need one token per team member for workflow runs. A single repository secret (for example `GH_PAT` or `GH_PAT_VALIDATION`) is enough for all runs in that repository. Each member only needs their own token if they must create or rotate secrets themselves.

---

### Final Setup

Once the secret is configured:

- **GH_PAT** → your GitHub token

GitHub Actions will be able to download the `fbs-pro` package and build installers successfully.

## To sign the app

To sign the app, you must have both:

- the certificate
- the matching private key

### 1. Create the private key on your Mac

- Open **Trousseaux d'acces**.
- In the menu bar, go to:
  **Trousseaux d'acces > Certificate Assistant > Request a Certificate From a Certificate Authority**
- Fill in:
  - **User Email Address**: your email
  - **Common Name**: `Snooz Developer ID Application`
  - **CA Email Address**: leave empty
  - Check **Saved to disk**
- Save the CSR file (for example: `Snooz_Developer_ID.certSigningRequest`).

### 2. Ask the Apple Developer admin to issue the certificate

- Send your CSR to the Apple Developer account admin.
- The admin must create the **Developer ID Application** certificate from this CSR.
- The admin sends you the generated `.cer` file.

### 3. Export certificate + private key as `.p12` from macOS

- Double-click `developerID_application.cer` received from the admin.
- Open **Trousseaux d'acces**.
- Go to the **Certificates** tab.
  - If everything is empty, wait a bit, or click **Systeme** and come back to **session** (it must be unlocked).
  - Confirm you can see: `DeveloperID Application: Services Appwapp inc.`
- Go to the **Mes certificats** tab.
  - Expand `DeveloperID Application: Services Appwapp inc.`
  - Confirm the private key is present (for example: `Snooz Developer ID`).
  - Right-click the certificate and select **Exporter**.
  - Format: `.p12`
  - Use a password and store that value in the GitHub secret `APPLE_DEVELOPER_ID_APP_CERT_P12_PASSWORD`.
  - Save the file (for example: `snooz_developer_id_app.p12`).

Then convert the `.p12` to base64:

```bash
base64 -i ~/Downloads/snooz_developer_id_app.p12 > ~/Downloads/snooz_developer_id_app.p12.base64
```

Use the generated base64 content as the value of the GitHub secret `APPLE_DEVELOPER_ID_APP_CERT_P12_BASE64`.

### 4. Create `APPLE_NOTARY_APP_PASSWORD`

- Go to `https://appleid.apple.com`.
- Open **Mots de passe pour app**.
- Generate a new app-specific password.
- Suggested label: `Snooz GitHub Actions`.
- Copy the generated value.
- Save it in the GitHub secret `APPLE_NOTARY_APP_PASSWORD`.

### 5. Run macOS x64 build on the self-hosted Mac mini

1. Connect to the Mac mini.
2. Open a terminal.
3. Start the GitHub Actions runner:

```bash
cd ~/Documents/actions-runner
./run.sh
```

## Full list of required secrets

The workflow uses the following GitHub repository secrets:

- `GH_PAT`: GitHub token used to check out private repositories and download release assets.
- `APPLE_DEVELOPER_ID_APP_CERT_P12_BASE64`: Base64 content of your exported `.p12` certificate file.
- `APPLE_DEVELOPER_ID_APP_CERT_P12_PASSWORD`: Password used when exporting the `.p12` file.
- `APPLE_KEYCHAIN_PASSWORD`: Password used by GitHub Actions to create/unlock the temporary macOS keychain.
- `APPLE_DEVELOPER_ID_APP_IDENTITY`: Signing identity string, for example `Developer ID Application: Services Appwapp inc. (UDE82H2SDR)`.
- `APPLE_NOTARY_APPLE_ID`: Apple ID email used for notarization.
- `APPLE_NOTARY_APP_PASSWORD`: App-specific password generated at `appleid.apple.com`.

Notes:

- `GH_PAT` is required for all builds (Windows, macOS, Linux): it is used to check out the source repository, download `fbs-pro` release assets, and publish installers to a release when release publishing is enabled.
- Apple-related secrets are required for macOS signing and notarization jobs.


