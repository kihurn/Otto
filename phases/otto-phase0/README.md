# Otto: Phase 0 checks

These scripts don't build Otto yet. They answer four questions on **your** PC before we write the real app:

1. Can Otto reach every brain (Gemma 4 and the other cloud models, plus local Qwen) through C0RE? Which can read screenshots?
2. Does Laya run on your GPU? How fast is it, how accurate out of the box, and does teaching it from examples help?
3. How fast and accurate is faster-whisper, on the GPU and on the processor?
4. Do Laya, Whisper and Qwen all fit in the 12 GB graphics card together?

Each check prints **PASS**, **FAIL** (with a "->" line telling you what to do) or **NOTE** (worth knowing, not a problem).

**Time:** about 10 minutes of setup, then 15–25 minutes the first time you run the checks (mostly downloads).
**Disk space:** about 10 GB (PyTorch, NVIDIA libraries, Laya and Whisper models).

---

## Step 1: Unzip

Unzip `otto-phase0.zip` somewhere easy, for example `C:\Users\<you>\Projects\otto-phase0`.

Open that folder in File Explorer, right-click on empty space and choose **Open in Terminal**. A PowerShell window opens in the right folder. Use it for every step below.

## Step 2: Make Otto's C0RE key

1. Open `http://127.0.0.1:7080/admin` in your browser, then **Keys → New key**.
2. Project: `otto`. Reach: **Private**.
3. Allow these models (or "all models" if C0RE has that option):
   - `gemma4:31b-cloud`
   - `deepseek-v4.1-flash:cloud`
   - `glm-5.3-flash:cloud`
   - `kimi-k3.1-pro:cloud`
   - `qwen3-vl:8b-instruct`
   - `qwen3-vl:4b-instruct`
4. Copy the key. **Don't paste it into chat with Claude.**

Make sure Ollama is signed in for cloud models. If they worked in your Hermes test, they already are. If not, run `ollama signin`.

## Step 3: Save the key on your PC

In PowerShell, paste these two lines. The first one asks for the key and hides what you type:

```powershell
[Environment]::SetEnvironmentVariable("OTTO_C0RE_KEY", "<your-c0re-key>", "User"); $env:OTTO_C0RE_KEY = "<your-c0re-key>"

if ($env:OTTO_C0RE_KEY) { "key is set" } else { "key is NOT set" }


[Environment]::SetEnvironmentVariable("OTTO_SPOTIFY_CLIENT_ID", "68c28eef5af2493ba46a78333ec69acd", "User"); $env:OTTO_C0RE_KEY = "68c28eef5af2493ba46a78333ec69acd"
```

Now **close PowerShell and open a new one** in the same folder (the key only shows up in new windows). Check it worked:



### Step 3b (optional): Ollama web search

This lets Otto answer up-to-date questions like "who's the president".

1. Make an API key at https://ollama.com/settings/keys
2. Save it the same way:

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_API_KEY", "<your-ollama-api-key>", "User"); $env:OLLAMA_API_KEY = "<your-ollama-api-key>"

if ($env:OLLAMA_API_KEY) { "key is set" } else { "key is NOT set" }
```

Then open a new PowerShell window again. If you skip this, the web search check just says "Skipped".

## Step 4: Install

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

It ends with a quick check that should say `GPU visible: True`. If it says `False`, see Troubleshooting below.

## Step 5: Run the checks

```powershell
.\.venv\Scripts\python.exe run_all.py
```

Close games and heavy GPU apps first. You can also run any single check on its own:

| Command | What it checks |
|---|---|
| `.\.venv\Scripts\python.exe check_c0re.py` | every model through C0RE: answers, JSON, images |
| `.\.venv\Scripts\python.exe check_laya.py --train` | Laya speed and accuracy, before and after teaching |
| `.\.venv\Scripts\python.exe check_whisper.py --mic` | Whisper speed and accuracy, plus 5 seconds of your own voice |
| `.\.venv\Scripts\python.exe check_websearch.py` | web search, then Gemma answers from the results |
| `.\.venv\Scripts\python.exe check_memory.py` | everything loaded together on the GPU |

## Step 6: Send me the results

Open `results\summary.txt` and paste its contents into the chat with Claude. It contains **no keys**: only PASS/FAIL lines, timings and memory numbers.

## While you wait: install Everything

Phase 1 will use it for file search. Get it from https://www.voidtools.com (the normal installer is fine) and let it finish indexing.

---

## Troubleshooting

| You see | What to do |
|---|---|
| `python` is not recognised | Reinstall Python from python.org and tick **"Add python.exe to PATH"**. |
| `running scripts is disabled` | Use the exact `powershell -ExecutionPolicy Bypass -File .\setup.ps1` line from step 4. |
| `GPU visible: False` | Update your NVIDIA driver (GeForce Experience / NVIDIA App → Drivers), restart the PC, then run step 4 again. |
| `invalid_key` | Redo steps 2 and 3, then open a **new** PowerShell window. |
| `model_not_allowed` | Allow that model for the otto key in the C0RE dashboard. |
| `model_not_found` on a cloud model | Run `ollama signin`, and check the model name on ollama.com. |
| `engine_offline` | Start the Ollama app on the PC. |
| `quota_or_limit` | Ollama cloud limit reached. See https://ollama.com/settings/usage and try later. |
| Whisper GPU tests fail with `cublas` / `cudnn` / `.dll` | Run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` again. |
| "Something is already using the GPU" | Close games/browsers with many tabs, or wait 5 minutes for Ollama to unload idle models. |

## What's in here

```text
otto-phase0/
├── README.md              this file
├── setup.ps1              installs everything into .venv
├── requirements.txt       the Python packages
├── run_all.py             runs every check and writes results/summary.txt
├── check_c0re.py          brains through C0RE
├── check_laya.py          Laya speed/accuracy, and teaching it
├── check_whisper.py       speech-to-text
├── check_websearch.py     Ollama web search (optional)
├── check_memory.py        everything together on the GPU
├── otto_check/            shared helper code
└── data/otto_intents_starter.csv   132 example requests labelled by area (a rough starter set)
```
