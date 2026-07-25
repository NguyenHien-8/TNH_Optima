# TNH Optima 1.1.0 — Run Commands

## Create a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\Release_1.1.0\requirements.txt
```

```powershell
python -m PyInstaller --clean --noconfirm .\TNH_Optima.spec
```
