import sys
import subprocess
import os

def install_and_run():
    # 1. Check/Install PyInstaller
    try:
        import PyInstaller
        print("PyInstaller already installed.")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Install google-genai if missing
    try:
        import google.genai
        print("google-genai already installed.")
    except ImportError:
        print("Installing google-genai...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-genai"])

    # 3. Run PyInstaller
    print("\nBuilding Vedika.exe with PyInstaller...")
    try:
        import PyInstaller.__main__
        args = [
            'main.py',
            '--name=Vedika',
            '--onefile',
            '--windowed',
            # Bundle all HTML/env assets
            '--add-data=mascot.html;.',
            '--add-data=onboarding.html;.',
            '--add-data=.env;.',
            '--add-data=vedika.ico;.',
            '--add-data=vedika_memory.json;.',
            '--icon=vedika.ico',
            # Hidden imports for PyQt5 WebEngine
            '--hidden-import=PyQt5',
            '--hidden-import=PyQt5.QtWebEngineWidgets',
            '--hidden-import=PyQt5.QtWebEngine',
            '--hidden-import=google.genai',
            '--hidden-import=pyttsx3',
            '--hidden-import=speech_recognition',
            '--collect-all=PyQt5',
            '--clean',
        ]
        # Add vedika.txt if it exists
        if os.path.exists('vedika.txt'):
            args.append('--add-data=vedika.txt;.')

        PyInstaller.__main__.run(args)
        print("\n✅ Build complete!")
        print("📦 Executable: dist/Vedika.exe")
        print("\n⚠️  Note: Users need to allow browser access on first launch.")
    except Exception as e:
        print(f"Build error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    install_and_run()
