# Contributing to Cyctitles

Thanks for your interest! This is a small, focused project — bug reports, fixes and
polish are all welcome.

## Ways to help

- **Report a bug** — open an [issue](https://github.com/ClassicCyc/Cyctitles/issues/new/choose).
  Include the log from `%LOCALAPPDATA%\Cyctitles\cyctitles.log`.
- **Suggest a feature** — open an issue describing the use case.
- **Send a pull request** — see below.

## Development setup

Requires **Python 3.10+** (3.12 recommended) on Windows.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m pip install pytest pyinstaller==6.22.3 pyinstaller-hooks-contrib Pillow
```

Run the app:

```powershell
run_dev.bat
# or: .venv\Scripts\python.exe app.py
```

Run the tests:

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

Build the executable / installer — see the **Building the executable** section in the
[README](README.md).

## Pull request checklist

- [ ] The change is focused (one topic per PR).
- [ ] `pytest tests -q` passes.
- [ ] New behaviour is covered by a test where practical.
- [ ] No secrets, keys or personal paths are committed.
- [ ] UI strings are added to **all** languages in `cyctitles/i18n.py` (a test enforces
      that every language has the same key set).

## Code style

- Keep it simple and readable; match the surrounding code.
- No comments unless they explain *why*, not *what*.
- No new runtime dependency without a good reason (the app must stay fully offline and
  easy to freeze with PyInstaller).

## License

By contributing you agree that your work is released under the project's
[MIT License](LICENSE).
