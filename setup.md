# Ad Server Simulator — Setup Guide

Simple steps to get this project running on a new computer.

**After setup:** day-to-day use is in [`HOW-TO-USE.md`](HOW-TO-USE.md).  
**Technical details:** see [`README.md`](README.md).

---

## What you need

| Requirement | Notes |
|-------------|--------|
| **Voise Ad Server** | Must be running (usually `http://localhost:8001`) |
| **Python 3.12+** | [Download](https://www.python.org/downloads/) — tick **Add Python to PATH** on Windows |
| **Node.js 18+** | [Download LTS](https://nodejs.org/) |
| **This repo** | Clone or unzip `ad-server-sim` |

Check versions:

```bash
python --version
node --version
```

---

## Setup (one time only)

Do these steps **once** on a new machine.

### 1. Start the Ad Server

Start the Voise Ad Server the way your team normally does.  
Confirm it opens: **http://localhost:8001**

> The simulator talks *to* the ad server. It does not replace it.

### 2. Backend (Python)

Open a terminal in the project folder, then:

```bash
cd backend
python -m venv .venv
```

**Windows:**

```bash
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**Mac / Linux:**

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set your ad server login:

```
AD_SERVER_URL=http://localhost:8001
AD_SERVER_EMAIL=your-email@example.com
AD_SERVER_PASSWORD=your-password
```

Use an **admin** account (`platform_admin` or `tenant_admin`). A normal sign-up is not enough for full seeding — ask a teammate if you need your user promoted.

### 3. Dashboard (build once)

In a new terminal:

```bash
cd dashboard
npm install
npm run build
```

When this finishes, a `dashboard/dist` folder appears. You only rebuild if dashboard code changes.

---

## Run it every day

### Easiest (Windows)

1. Make sure the **Ad Server** is running on port **8001**
2. Double-click **`start.bat`** in the `ad-server-sim` folder
3. Browser opens **http://localhost:8090**
4. Leave the black window open while you work

### Mac / Linux

```bash
./start.sh
```

Or manually:

```bash
cd backend
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uvicorn app.main:app --port 8090
```

Then open **http://localhost:8090**

### Quick check

On the dashboard top-right:

- Green light = connected to the ad server
- Then: **Seed** → **Generate traffic** → **Run scenarios**

Full walkthrough: [`HOW-TO-USE.md`](HOW-TO-USE.md)

---

## Optional — Docker

If you use Docker Desktop:

```bash
cd ad-server-sim
AD_SERVER_PASSWORD=yourpass docker compose up --build
```

Open **http://localhost:8090**

The container reaches a host ad server at `host.docker.internal:8001`.

---

## Stop

- **start.bat / uvicorn:** close the window, or press **Ctrl + C**
- **Docker:** **Ctrl + C**, or `docker compose down`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` / `node` not recognized | Reinstall and add to PATH; open a **new** terminal |
| Red light / can't reach ad server | Start the ad server; check `AD_SERVER_URL` in `backend/.env` |
| “Dashboard not built” | Run `npm install` + `npm run build` in `dashboard/` |
| Seed / campaigns fail | Use an admin user in `.env` (not a normal trafficker account) |
| Port 8090 in use | Close the other app, or run: `uvicorn app.main:app --port 8091` |
| `start.bat` says not set up | Complete the **Setup (one time only)** steps above |

---

## Folder map

```
ad-server-sim/
  backend/       ← Python API (create .venv + .env here)
  dashboard/     ← Web UI (npm install + npm run build once)
  start.bat      ← Windows: start simulator
  start.sh       ← Mac/Linux: start simulator
  setup.md       ← this file
  HOW-TO-USE.md  ← how to use the dashboard
  README.md      ← full technical docs
```

---

**Done when:** `http://localhost:8090` loads the dashboard and Seed / Generate traffic works.
