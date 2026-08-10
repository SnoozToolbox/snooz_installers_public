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

- [ci/validation_tools/tool_json_adaptations.json](ci/validation_tools/tool_json_adaptations.json): per-tool rules used to adapt process JSON inputs for CI headless runs.
  - **See [ADAPTATION_GUIDE.md](ci/validation_tools/ADAPTATION_GUIDE.md) for full documentation** on how to configure and extend JSON adaptations for new tools.
- [ci/validation_tools/tool_validations.json](ci/validation_tools/tool_validations.json): per-tool rules used to validate generated outputs against gold standards.

Note: the adaptation file used in this repository is [ci/validation_tools/tool_json_adaptations.json](ci/validation_tools/tool_json_adaptations.json) (not tool_json_adaptation.psd1).

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

### 5. Set up the self-hosted runner on the Mac mini

#### 5a. Create a new self-hosted runner

1. Go to the GitHub repository: https://github.com/SnoozToolbox/snooz_installers_public
2. Click **Settings** (top-right corner of the repo).
3. In the left sidebar, click **Actions** → **Runners**.
4. Click the **New self-hosted runner** button (green, top-right).
5. Select the following configuration:
   - **Runner image**: macOS
   - **Architecture**: x64
6. Copy the download and setup commands (they will be displayed on the screen).

#### 5b. Download and configure the runner on the Mac mini

1. Connect to the Mac mini via SSH or open a terminal on it directly.
2. Create a directory for the runner:

```bash
mkdir -p ~/Documents/actions-runner
cd ~/Documents/actions-runner
```

3. Download the runner from the GitHub instructions (replace the URL with the one from step 5a):

```bash
curl -o actions-runner-osx-x64-X.XXX.X.tar.gz -L https://github.com/actions/runner/releases/download/vX.XXX.X/actions-runner-osx-x64-X.XXX.X.tar.gz
```

4. Extract the runner:

```bash
tar xzf actions-runner-osx-x64-*.tar.gz
```

5. Configure the runner (use the token from the GitHub Actions setup page):

```bash
./config.sh --url https://github.com/SnoozToolbox/snooz_installers_public --token AAXXXXXXXXXXXXXXXXXX
```

Replace `AAXXXXXXXXXXXXXXXXXX` with the actual token provided by GitHub.

The runner will prompt you for:
- **Runner name**: Use a descriptive name (e.g., `Macmini`)
- **Work directory**: Press Enter to accept the default (`_work`)
- **Labels**: Press Enter to accept the default labels: `self-hosted`, `macOS`, `X64`

These default labels are exactly what you need. In your GitHub Actions workflow YAML, reference the runner using:
```yaml
runs-on: [self-hosted, macOS, X64]
```

#### 5c. Run the self-hosted runner

**Recommended approach: Run in interactive mode**

1. Start the runner in interactive mode:

```bash
cd ~/Documents/actions-runner
./run.sh
```

2. Keep this terminal window open. The runner should display:

```
Current runner version: '2.336.0'
Listening for Jobs
```

3. Once the runner is running and listening, it will appear as `idle` in the **Actions** → **Runners** section on GitHub, and it will be ready to execute jobs.

4. To stop the runner, press `Ctrl+C` in the terminal.

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

## Note: recommended models for common tasks

Quick reminder of which models to use for different tasks:

- **Daily work (80%)** → GPT-5 mini
- **Understanding / refactoring / documenting (20%)** → Claude Haiku 4.5
- **Complex problems (default)** → Claude Sonnet 4.6
- **Very complex / ambiguous problems** → Claude Sonnet 5
- **Final cross-check for hard problems** → GPT-5.3-Codex


