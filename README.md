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

## 🔐 API Token and Asset ID Setup

To enable GitHub Actions to build installers using this repository, you need to configure two secrets: a **GitHub API token** and the **Asset ID** of the latest `fbs-pro` release.

---

### 1. Create a Personal Access Token (PAT)

Generate a GitHub Personal Access Token and add it to your repository secrets:

1. Go to: **Settings → Secrets and variables → Actions → Repository secrets**
2. Click **New repository secret**
3. Name it: `GH_PAT`
4. Paste your token value

#### Required permissions (Fine-grained token):
- **Repository access**: Select the target repository (or all repositories if needed)
- **Permissions**:
  - `Contents: Read`
  - `Releases: Read`

---

### 2. Retrieve the Asset ID

You need the **Asset ID** of the latest `fbs-pro` release.

Run the following command locally (replace `NEW_TOKEN` with your PAT):

```bash
curl -H "Authorization: token NEW_TOKEN" \
https://api.github.com/repos/SnoozToolbox/fbs-pro-version/releases/latest
```
This will return a JSON response. Look for the assets section:
```
"assets": [
  {
    "id": 123456789,
    "name": "fbs-pro.tar.gz"
  }
]
```
Copy the id corresponding to fbs-pro.tar.gz

### 3. Add the Asset ID as a Secret
- Go back to **Settings → Secrets and variables → Actions**
- Add another secret (e.g., FBS_ASSET_ID)
- Paste the asset ID value

### Final Setup

Once both secrets are configured:

- **GH_PAT** → your GitHub token
- **FBS_ASSET_ID** → the release asset ID

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
- `FBS_ASSET_ID`: Asset ID of `fbs-pro.tar.gz` from the latest `SnoozToolbox/fbs-pro-version` release.
- `APPLE_DEVELOPER_ID_APP_CERT_P12_BASE64`: Base64 content of your exported `.p12` certificate file.
- `APPLE_DEVELOPER_ID_APP_CERT_P12_PASSWORD`: Password used when exporting the `.p12` file.
- `APPLE_KEYCHAIN_PASSWORD`: Password used by GitHub Actions to create/unlock the temporary macOS keychain.
- `APPLE_DEVELOPER_ID_APP_IDENTITY`: Signing identity string, for example `Developer ID Application: Services Appwapp inc. (UDE82H2SDR)`.
- `APPLE_NOTARY_APPLE_ID`: Apple ID email used for notarization.
- `APPLE_NOTARY_APP_PASSWORD`: App-specific password generated at `appleid.apple.com`.

Notes:

- `GH_PAT` and `FBS_ASSET_ID` are required for all builds (Windows, macOS, Linux) because `fbs-pro` is downloaded in each job.
- Apple-related secrets are required for macOS signing and notarization jobs.


