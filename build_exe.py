import sys
import subprocess

def install_and_run():
    # 1. Check/Install PyInstaller
    try:
        import PyInstaller
        print("PyInstaller is already installed.")
    except ImportError:
        print("PyInstaller not found. Installing via pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("Successfully installed PyInstaller.")
        except Exception as e:
            print(f"Failed to install PyInstaller: {e}")
            sys.exit(1)

    # 2. Run PyInstaller compilation
    print("\nStarting compilation using PyInstaller...")
    try:
        import PyInstaller.__main__
        PyInstaller.__main__.run([
            'main.py',
            '--name=Vedika',
            '--onefile',
            '--windowed',
            '--add-data=mascot.html;.',
            '--add-data=vedika.ico;.',
            '--icon=vedika.ico',
            '--clean'
        ])
        print("\nCompilation completed successfully!")
        print("Your standalone executable is located at: dist/Vedika.exe")
    except Exception as e:
        print(f"Error during compilation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    install_and_run()
