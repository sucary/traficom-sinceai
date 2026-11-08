# Traficom SinceAI risk assessment

## 1. Install

From the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e backend
cd frontend
npm install
cd ..
```

Create `frontend\.env.local` with:

```
VITE_API_URL=http://localhost:8000/api
```

For the chat, put `OPENCODE_API_URL`, `OPENCODE_API_KEY` and `OPENCODE_MODEL` in a `.env` file in the project folder.

## 2. Add the reference file

Put `Traficom_SinceAI_Frequencies_of_interest_v05112026.xlsx` in the `data` folder and close it in Excel.

Optional, used when present in `data`: the previous terrestrial issue (for example `brific3075.mdb`) and the AP30 snapshots `SPS_ALL_IFIC3083.mdb` and `30B_3083.mdb`.

## 3. Start the app

Start the backend:

```powershell
.\.venv\Scripts\python.exe backend\scripts\serve_frontend_api.py
```

In a second terminal, start the frontend:

```powershell
cd frontend
npm run dev
```

Open the address Vite prints, usually http://localhost:5173.

## 4. Run the analysis

Use either way. Both run the same calculation and show the results in the app.

**In the app:** click **Upload** in the top right, choose one or more IFIC `.mdb` files, and click **Upload and analyse**.

**From the command line:** put the IFIC files in `data` and run

```powershell
.\.venv\Scripts\python.exe -m app run ific3074.mdb brific3076.mdb
```

then reload the app. Files named `ificNNNN.mdb` are space IFICs, `brificNNNN.mdb` terrestrial. Results are written to `output\<file name>\`.
