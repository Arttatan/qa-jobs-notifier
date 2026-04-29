# QA Vacancy Telegram Notifier

This script checks vacancy sources and sends new QA jobs to Telegram.

## What it monitors

- Greenhouse job boards (configurable list)
- Remotive API
- We Work Remotely QA page
- Lever companies (configurable list)
- Jobgether (via Lever feed)
- Dynamite Jobs

It filters by QA/AQA/SDET keywords and ignores obvious non-QA roles.

## Setup

1. Install Python 3.10+
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create your config:

```bash
copy config.example.json config.json
```

4. Edit `config.json`:
- `telegram_bot_token`
- `telegram_chat_id`
- optional poll/filter settings

## First test run

```bash
python job_notifier.py --once
```

If configured correctly, you will receive messages in Telegram for new matching jobs.

## Run continuously

```bash
python job_notifier.py
```

Default polling interval is `5` minutes (configurable in `config.json`).

## Run in GitHub Actions (no need to keep PC on)

1. Push this folder to a GitHub repository.
2. In GitHub repo, open `Settings -> Secrets and variables -> Actions -> New repository secret`.
3. Add secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Workflow file is already added: `.github/workflows/qa_notifier.yml`
5. Start a manual run: `Actions -> QA Vacancy Notifier -> Run workflow`.

### Schedule

Current schedule is:
- `08:00 UTC` (09:00 Portugal in summer time)
- `17:00 UTC` (18:00 Portugal in summer time)

Note: Portugal changes UTC offset for winter/summer time. If you want exact local times all year, update cron seasonally.

## Autostart on Windows (Task Scheduler)

Create a scheduled task that runs at user logon:

Program/script:

```text
python
```

Arguments:

```text
"C:\Users\35191\Search Job\job_notifier.py"
```

Start in:

```text
C:\Users\35191\Search Job
```

## Notes

- The script stores sent jobs in `state.json` to avoid duplicate alerts.
- If vacancy publish date is missing, the script still sends it (as requested).
