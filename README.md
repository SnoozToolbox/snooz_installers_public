# What is this repo ?

This repository serves as a private way to generate installers for the Snooz Toolbox application.

# How do I do so ?

### Update the source code
In order to create installers, you first need to **update the source code** so that it reflects the current of Snooz.


A common way to do is to set the default [Snooz Toolbox](https://github.com/SnoozToolbox/snooz-toolbox) and/or the [Snooz CEAMS version](https://github.com/SnoozToolbox/snooz-toolbox-ceams) as upstream, depending on the installers
that you which to create.
After setting them up, fetch, cherry-pick, or merge the changes from these upstream branches to your local version of this repo. By doing so, you can be in sync with the current changes.

# Where does it happen ?
The file that holds the different jobs to create the installers is in `.github/workflows/installers_creation.yml`. 

#### To execute the workflow, you simply go into the Actions tab:

![image](https://github.com/user-attachments/assets/b3c770ae-a3b4-436b-9429-42f74fe260b5)

#### Then select the job's name by the left tree, in our case it is 'Build Binaries' as shown in the picture below.

![image](https://github.com/user-attachments/assets/c040ef5a-f594-4fdd-8a0a-5b2958651cec)

#### Finally, run the job.

![image](https://github.com/user-attachments/assets/ff7f23f9-7050-4645-92b9-7d937c984454)

## Note!

Select the desired builds: Windows, macOS, and/or Linux.
Make sure to unzip the Linux artifact before sharing, since the installer is also a ZIP file.

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

## ✅ Final Setup

Once both secrets are configured:

- **GH_PAT** → your GitHub token
- **FBS_ASSET_ID** → the release asset ID

GitHub Actions will be able to download the `fbs-pro` package and build installers successfully.
