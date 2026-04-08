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
