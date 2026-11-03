# market-monitor

## Run from PowerShell

From this project folder, run the Windows command launcher:

```powershell
.\marketmonitor.cmd
```

To use the exact `marketmonitor` command in the current PowerShell window, add the project folder to PATH first:

```powershell
$env:PATH = "$PWD;$env:PATH"
marketmonitor
```

The `.cmd` launcher installs the packages in `requirements.txt` and starts the app, without requiring PowerShell script permission changes. It needs Python on PATH. Streamlit prints the local browser URL when it starts.

## Run directly with Python

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
