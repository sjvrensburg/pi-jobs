# pi-jobs

Scheduled [pi](https://github.com/earendil-works/pi) jobs on systemd timers. One job = a gather
command, an optional one-turn prompt, a saved copy, and a delivery (Signal by default). This is
the runner, not anyone's jobs: write your own `.conf` files.

Split out of halo-prep, the author's private runbook for one box, at commit `5bec25c` on
2026-10-09, where it had replaced Hermes's cron
jobs.

## What `pi-job <name>` does

1. **Preflight.** If the job has a `PROMPT`, wait up to a minute for `HEALTH` to answer, so a
   job fired while the model server restarts does not report a model error.
2. **Gather.** Run `GATHER`; its stdout is the only data the model sees. No output = failure.
3. **Model.** `pi -p --no-session -nc -ns -np -ne -nt` from an empty temp dir, with the data
   attached. `--no-tools` makes a job read-only by construction, not by instruction; the empty
   dir keeps a stray `AGENTS.md`/`CLAUDE.md` out of the prompt. No `PROMPT` = skip the model and
   deliver the gather output.
4. **Save** to `~/.local/share/pi-jobs/<name>/<name>-<date>.md` (`PI_JOBS_OUT` overrides the
   parent dir). Not `~/Downloads`: that is where it went first, and it filled up.
5. **Deliver** with `signal-send`, or with the job's own `DELIVER` command.

**The exit code is the contract.** Every step's failure exits non-zero, so `pi-job@.service`'s
`OnFailure=` sends a notice. Two traps it avoids on purpose:

- `pi --mode json` exits 0 on a failed turn; `pi -p` exits 1 when the final stopReason is
  error/aborted, so `-p` is used.
- `pi -p` blocks forever on an open stdin. stdin is `/dev/null`, even when run by hand.

## Install

```bash
cp bin/pi-job bin/signal-send ~/.local/bin/ && chmod +x ~/.local/bin/{pi-job,signal-send}
cp systemd/pi-job@.service systemd/notify-failure@.service ~/.config/systemd/user/
mkdir -p ~/.pi/agent/jobs && cp examples/example.{conf,md} ~/.pi/agent/jobs/
cp systemd/pi-job-example.timer ~/.config/systemd/user/
systemctl --user daemon-reload
pi-job example                                   # once by hand
systemctl --user enable --now pi-job-example.timer
```

Nothing syncs a repo copy to its deployed copy; copy again after editing and `diff` to check.

## A job's `.conf`

Sourced bash, at `~/.pi/agent/jobs/<name>.conf` (`PI_JOBS_DIR` overrides the dir).

| Variable | Meaning |
|---|---|
| `GATHER` | Command whose stdout is the job's data. Required. |
| `PROMPT` | Prompt file, relative to the jobs dir. Unset = no model, deliver `GATHER`'s output. |
| `MODEL` | pi `provider/model`. Default `$PI_JOB_MODEL`, else `local-ornith/cybertiel-coder-35b-a3b`. |
| `HEALTH` | URL that must answer before the model runs. Default `$PI_JOB_HEALTH`, else `http://127.0.0.1:8092/health`. |
| `DELIVER` | Command run instead of `signal-send`, with `OUT` (saved output) and `WORK` (scratch dir) exported. Must exit non-zero on a failed delivery. |

The built-in defaults are the box this came from. On another box set `PI_JOB_MODEL` and
`PI_JOB_HEALTH` once, in a drop-in for `pi-job@.service`:

```ini
# ~/.config/systemd/user/pi-job@.service.d/model.conf
[Service]
Environment=PI_JOB_MODEL=my-provider/my-model PI_JOB_HEALTH=http://127.0.0.1:8080/health
```

`PI_JOB_EXTENSION` names one pi extension to load (pi runs with `-ne`). It defaults to
`~/.pi/agent/extensions/schema-key-order.ts` and is skipped if that file is not there; set it
empty to load none.

## signal-send

Sends through a running `signal-cli` daemon's JSON-RPC, so it does not fight the daemon for the
account's store lock. Config in `~/.config/signal-send/env`, **outside git**: it holds phone
numbers.

```bash
SIGNAL_ACCOUNT=+<number>     # the daemon's account
SIGNAL_SEND_TO=+<number>     # default recipient; the account itself = note-to-self
SIGNAL_RPC_URL=...           # optional, default http://127.0.0.1:8081/api/v1/rpc
```

`signal-send [--to N] [--attach FILE]… "text"`, or `-` to read stdin. It splits at ~7900
characters on line boundaries, retries transport errors three times, and exits non-zero unless
every recipient result is `SUCCESS`.

`notify-failure@.service` sends a failed unit's last 15 journal lines through it.

## Preference mining

`scripts/pref_log.py`, `scripts/pref_summarize.py` and `skills/preference-mining/` record what
the operator picks from offered lists (`shown`/`chosen`/`liked`/`disliked`) and turn it into
per-domain keyword weights with a 45-day half-life. Store:
`~/.local/share/pi-jobs/preferences/`.

Deploy the scripts to **`~/.pi/agent/jobs/scripts/`** and the skill to
`~/.pi/agent/skills/preference-mining/`. The scripts path is fixed: skills and gather scripts
call `pref_log.py` there by absolute path.

```bash
mkdir -p ~/.pi/agent/jobs/scripts && cp scripts/pref_*.py ~/.pi/agent/jobs/scripts/
cp -r skills/preference-mining ~/.pi/agent/skills/
```
