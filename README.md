Step 1: Install Python

    Go to python.org/downloads and download the latest version for Windows.

    Open the installer. CRITICAL STEP: At the very bottom of the installer window, check the box that says "Add Python to PATH" before clicking Install. If you skip this, your terminal won't recognize Python commands.

Step 2: Install Required Libraries

Python comes with built-in tools for handling XML and matching text, but we need one external library to handle the web requests to the API.

    Open your computer's Command Prompt (search "cmd" in the Windows start menu).

    Type the following command and hit Enter: pip install requests
    
    Step 3: Prepare Your Files

    Create a new folder on your computer (e.g., AnimeImporter).

    Inside that folder, create your text file and name it exactly anime_list.txt. Put one anime name per line (English, Japanese, or Chinese).

    In that same folder, create a new file named build_list.py. You can do this by creating a text document and changing the .txt extension to .py.

    Open build_list.py in a text editor (Notepad, VS Code, or Notepad++) and paste the code below.

    Step 4: Run the Script

    Open your Command Prompt.

    You need to navigate to the folder where you saved the files. Use the cd (Change Directory) command. For example, if you saved it on your desktop, type: cd Desktop\AnimeImporter

    Step 5: Run the script by typing: python build_list.py
