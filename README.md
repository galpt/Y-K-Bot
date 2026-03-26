# Y-K-Bot

A Py-cord bot for the Yuki / Yumemi / Kotatsu Discord server.

## Local Setup

Use Python 3.13 for this project. Python 3.14 is currently too new for the Bot's Py-cord stack and can break local startup.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

If you already created `.venv` with another Python version, remove it and recreate it with Python 3.13 before installing dependencies again.

## Architecture

The runtime entrypoint stays in `main.py`, while the implementation now lives in a modular internal package:

```text
.
├── cog/                   
├── main.py
└── requirements.txt
```

> [!NOTE]
> - Forum and role settings are read safely from `.env` through the shared config loader.
> - Don`t forget to install the package from the requirements.txt.
> - As well the right Data in `.env`.
