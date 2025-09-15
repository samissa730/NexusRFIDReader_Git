# Introduction 
TODO: Give a short introduction of your project. Let this section explain the objectives or the motivation behind this project. 

# Getting Started
TODO: Guide users through getting your code up and running on their own system. In this section you can talk about:
1.	Installation process
2.	Software dependencies
3.	Latest releases
4.	API references

# Build and Test

## Run the app

```bash
python main.py
```

## Run unit tests

This project uses Python's built-in `unittest` framework. Tests live in the `UnitTests` directory.

Run all tests with discovery:

```bash
python -m unittest discover -s UnitTests -p "test_*.py" -v
```

Run a single test module:

```bash
python -m unittest UnitTests.test_common -v
```

On Windows using a virtual environment created in `venv`, prefix commands with `venv\Scripts\python`:

```bash
venv\Scripts\python -m unittest discover -s UnitTests -p "test_*.py" -v
```

Notes:
- No extra testing dependencies are required; `unittest` is part of the Python standard library.
- `utils.common.get_serial()` is tested via mocks to avoid calling PowerShell/WMIC or reading real system files.

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