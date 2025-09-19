# Introduction 
TODO: Give a short introduction of your project. Let this section explain the objectives or the motivation behind this project. 

# Getting Started
TODO: Guide users through getting your code up and running on their own system. In this section you can talk about:
1.	Installation process
2.	Software dependencies
3.	Latest releases
4.	API references

# Build and Test
TODO: Describe and show how to build your code and run the tests. 

## Run Unit Tests

Unit tests live under the `UnitTests/` directory and use Python's built-in `unittest` framework.

1. Ensure the virtual environment is activated (optional but recommended):
   ```bash
   # Windows PowerShell
   .\venv\Scripts\Activate.ps1
   # or CMD
   .\venv\Scripts\activate.bat
   ```

2. Run all tests with discovery:
   ```bash
   python -m unittest discover -s UnitTests -p "test_*.py" -v
   ```

3. Run a single test file:
   ```bash
   python -m unittest UnitTests.test_common -v
   ```

4. Run a single test case or method:
   ```bash
   python -m unittest UnitTests.test_common.TestCommon.test_get_serial_windows_powershell -v
   ```

Notes:
- Tests mock external system calls (e.g., `subprocess`, `socket`) so they are safe to run on any OS.
- If you add new tests, place them in `UnitTests/` and name files `test_*.py`.

# Contribute
TODO: Explain how other users and developers can contribute to make your code better. 

If you want to learn more about creating good readme files then refer the following [guidelines](https://docs.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops). You can also seek inspiration from the below readme files:
- [ASP.NET Core](https://github.com/aspnet/Home)
- [Visual Studio Code](https://github.com/Microsoft/vscode)
- [Chakra Core](https://github.com/Microsoft/ChakraCore)


# NexusRFIDReader - Hello World PySide6 Example

This is a simple Python project demonstrating a PySide6 GUI application with a UI designed in Qt Designer (`.ui` file).

## Requirements
- Python 3.7+
- PySide6

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python main.py
   ```

## UI Design
- The main window UI is defined in `main.ui` and can be edited with Qt Designer.
- The application loads the UI dynamically at runtime. 

## Build and Create Installer (Windows & Linux)

You can package this application as a standalone executable for Windows and Linux using [PyInstaller](https://pyinstaller.org/). This will allow you to distribute your app without requiring users to install Python or dependencies.

### 1. Install PyInstaller

PyInstaller is already listed in `requirements.txt`. If not installed, run:

```bash
pip install pyinstaller
```

### 2. Build the Executable

#### **Windows**

Open a terminal in your project directory and run:

```bash
pyinstaller --onefile --add-data "ui/main.ui;ui" main.py
```
- `--onefile`: Creates a single executable file.
- `--add-data`: Ensures the `main.ui` file is included. On Windows, use a semicolon `;` to separate source and destination.

#### **Linux**

On Linux, use a colon `:` instead of a semicolon:

```bash
pyinstaller --onefile --add-data "ui/main.ui:ui" main.py
```

#### **Output**
- The standalone executable will be in the `dist` directory.
- You can distribute this file directly, or use an installer creator for a more polished installation experience.

### 3. (Optional) Create an Installer
- **Windows:** Use tools like [Inno Setup](https://jrsoftware.org/isinfo.php) or [NSIS](https://nsis.sourceforge.io/) to create a Windows installer from your `dist` folder.
- **Linux:** You can create a `.deb` package (for Debian/Ubuntu) using [fpm](https://fpm.readthedocs.io/en/latest/) or distribute as a tarball.

### 4. Notes
- You must build the executable on the target OS (build on Windows for Windows, on Linux for Linux).
- The `main.ui` file must be included using the `--add-data` option as shown above.
- Test the generated executable on a clean system if possible.

--- 