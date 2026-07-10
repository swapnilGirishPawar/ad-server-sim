# Voise Ad Simulator — Local Setup Guide

This guide walks you through installing and running the **Voise Ad Simulator** on your computer. It is written in plain language so you can follow it even if you are not very technical.

---

## What is this?

The simulator is a **testing tool** for the Voise Ad Server. It:

- Sends fake ad requests (like a real website or app would)
- Checks whether responses follow industry standards (IAB specs)
- Shows results on a **web dashboard** in your browser

You open the dashboard at: **http://localhost:8090**

---

## What you need first

Before you start, make sure you have:

| Item | What it is | Why you need it |
|------|------------|-----------------|
| **Voise Ad Server** | The main ad server project | The simulator talks to this. It should be running on your machine (usually at `http://localhost:8001`). |
| **Python 3.12 or newer** | A programming language the backend uses | To run the simulator’s server |
| **Node.js 18 or newer** | Needed to build the web dashboard | One-time build step |
| **This project folder** | The `ad-server-sim` code | Copy or clone it onto your computer |

> **Tip:** If you only received a zip file, unzip it somewhere easy to find (for example `Desktop\ad-server-sim`).

---

## Step 1 — Install Python (if you don’t have it)

1. Go to [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. Download **Python 3.12** (or newer)
3. Run the installer
4. **Important:** On the first screen, tick **“Add Python to PATH”**, then click Install
5. When done, open **Command Prompt** or **PowerShell** and type:

   ```
   python --version
   ```

   You should see something like `Python 3.12.x`. If you get an error, Python is not installed correctly — try installing again with “Add to PATH” checked.

---

## Step 2 — Install Node.js (if you don’t have it)

1. Go to [https://nodejs.org/](https://nodejs.org/)
2. Download the **LTS** version (the green “Recommended” button)
3. Run the installer (default options are fine)
4. Open a new Command Prompt or PowerShell and type:

   ```
   node --version
   ```

   You should see something like `v20.x.x` or `v18.x.x`.

---

## Step 3 — Make sure the Ad Server is running

The simulator **does not replace** the ad server. The ad server must already be running.

1. Start the Voise Ad Server the way your team normally does (often on port **8001**)
2. In your browser, try opening: **http://localhost:8001**  
   If it loads (or shows an API page), the ad server is up

If the ad server is not running, ask whoever gave you this project how to start it.

---

## Step 4 — Open the project folder in a terminal

A **terminal** (Command Prompt or PowerShell) is where you type text commands.

**On Windows:**

1. Press **Win + R**, type `cmd` or `powershell`, press Enter  
   — or search for “PowerShell” in the Start menu
2. Go to the project folder. Example (change the path to where **your** folder is):

   ```
   cd C:\Users\YourName\Desktop\ad-server-sim
   ```

3. Check you are in the right place — you should see folders named `backend` and `dashboard`:

   ```
   dir
   ```

---

## Step 5 — Set up the backend (Python)

These commands install the simulator’s server code.

1. Go into the backend folder:

   ```
   cd backend
   ```

2. Create a virtual environment (a private Python space for this project):

   **Windows:**
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```

   **Mac / Linux:**
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   After activation, your prompt may show `(.venv)` at the start — that means it worked.

3. Install required packages:

   ```
   pip install -r requirements.txt
   ```

   Wait until it finishes (may take a minute).

4. Create your settings file:

   ```
   copy .env.example .env
   ```

   **Mac / Linux:** use `cp .env.example .env` instead of `copy`.

5. Open `.env` in Notepad (or any text editor) and set your login details for the ad server:

   ```
   AD_SERVER_URL=http://localhost:8001
   AD_SERVER_EMAIL=your-email@example.com
   AD_SERVER_PASSWORD=your-password
   ```

   Use the same email and password you use for the ad server.  
   If you are unsure, ask the person who shared this project with you.

   Save the file and close the editor.

---

## Step 6 — Build the dashboard (one time)

The dashboard is the visual website you use in the browser. You only need to build it once (rebuild if the dashboard code changes).

1. Open a **second** terminal window (keep the first one open if you like)
2. Go to the dashboard folder:

   ```
   cd C:\Users\YourName\Desktop\ad-server-sim\dashboard
   ```

   (Adjust the path to match your machine.)

3. Install dashboard dependencies:

   ```
   npm install
   ```

4. Build the dashboard:

   ```
   npm run build
   ```

   When it succeeds, you will see a new `dist` folder inside `dashboard`.

---

## Step 7 — Start the simulator

1. In the terminal where you activated `.venv` and are inside the `backend` folder, run:

   ```
   uvicorn app.main:app --port 8090 --reload
   ```

2. Leave this window **open**. The simulator is running while this command is active.

3. You should see lines like `Uvicorn running on http://127.0.0.1:8090`.

---

## Step 8 — Open the dashboard in your browser

1. Open Chrome, Edge, or Firefox
2. Go to: **http://localhost:8090**
3. You should see the Voise Ad Simulator dashboard

### Quick test (recommended order on the Dashboard tab)

1. **Seed** — creates test data in the ad server  
2. **Generate traffic** — sends sample ad requests  
3. **Scenarios** — runs automated tests and shows pass/fail results  

There is also a **Publisher Ad Request** tab to send requests for a specific publisher and tag id.

---

## Optional — Run with Docker (easier if you already use Docker)

If you have **Docker Desktop** installed, you can skip Python/Node setup on your machine:

1. Open a terminal in the `ad-server-sim` folder (the one that contains `docker-compose.yml`)
2. Run:

   ```
   docker compose up --build
   ```

3. Open **http://localhost:8090** in your browser

Set your ad server password when starting:

```
AD_SERVER_PASSWORD=yourpass docker compose up --build
```

On Windows/Mac, Docker can reach an ad server on your computer at `host.docker.internal:8001` automatically.

---

## Admin account (for full seeding)

Some features need an **admin** user on the ad server (not just a regular user).

If seeding fails or campaigns cannot be created, someone with database access may need to promote your user to admin. That is usually done once on the ad server side — ask your teammate if you hit this.

For basic smoke tests, the simulator can still do a lot without full admin access.

---

## Stopping the simulator

- **Local run:** In the terminal where `uvicorn` is running, press **Ctrl + C**
- **Docker:** In the terminal where Docker is running, press **Ctrl + C**, or run `docker compose down`

---

## Troubleshooting

### “python is not recognized” or “node is not recognized”

Python or Node is not installed, or not on your PATH. Reinstall and make sure **“Add to PATH”** (Python) is enabled. Close and reopen the terminal after installing.

### “Connection refused” or dashboard cannot reach the ad server

- Check the ad server is running at **http://localhost:8001**
- Check `AD_SERVER_URL` in `backend\.env` matches that address
- Restart the simulator after changing `.env`

### Dashboard shows “Dashboard not built”

You skipped Step 6. Run `npm install` and `npm run build` inside the `dashboard` folder, then restart the simulator.

### Port 8090 already in use

Another program is using port 8090. Either close that program, or start on a different port:

```
uvicorn app.main:app --port 8091 --reload
```

Then open **http://localhost:8091** instead.

### `pip install` fails

- Make sure the virtual environment is activated (`(.venv)` in the prompt)
- Try: `python -m pip install --upgrade pip` then run `pip install -r requirements.txt` again

### Wrong email or password in `.env`

Edit `backend\.env`, fix `AD_SERVER_EMAIL` and `AD_SERVER_PASSWORD`, save, and restart the simulator.

### OpenRTB / auction tests need the fake DSP

For advanced OpenRTB tests, the ad server must be able to reach the simulator’s fake bidder at:

**http://localhost:8090/dsp/bid**

Keep the simulator running on port 8090 while testing. If you use Docker for the simulator but the ad server runs on the host, set:

```
SIM_PUBLIC_URL=http://host.docker.internal:8090
```

in your environment or `.env`.

---

## Folder cheat sheet

```
ad-server-sim/
  backend/          ← Python server (start here with uvicorn)
    .env            ← your settings (create from .env.example)
  dashboard/        ← web UI (npm install + npm run build once)
  setup.md          ← this file
  README.md         ← technical details for developers
```

---

## Need help?

If something still does not work:

1. Note the **exact error message** (copy from the terminal or browser)
2. Note which **step** you were on
3. Ask the person who shared this project — send them the error and your Python/Node versions (`python --version`, `node --version`)

---

**You are done when:** the simulator terminal is running, **http://localhost:8090** opens the dashboard, and you can run Seed → Generate traffic without errors.
