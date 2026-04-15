# CAST Bot

Telegram application bot for the Central Asian Science and Technology Association.
Django + PostgreSQL + aiogram 3.

## Architecture

```
apps/
  applications/   ← models, admin, business services (one source of truth)
  bot/            ← aiogram routers, keyboards, FSM, runbot management command
cast/             ← Django settings/urls/wsgi
deploy/           ← systemd units + nginx config
```

One codebase, one database, two processes on the server:
- `cast-bot.service`  — long-polling Telegram bot
- `cast-web.service`  — Gunicorn serving Django admin for reviewers

## Design choices

- **Questions live in DB.** Admins add/edit/reorder questions through `/admin/` without a redeploy.
- **Services layer** (`applications/services.py`) holds all DB writes. Handlers stay thin; Django admin reuses the same functions.
- **One-time invites.** Approval creates a `member_limit=1` invite with a TTL, so leaked links do not bypass review.
- **FSM carries a snapshot** of the questions. Exactly one DB query per application (plus one write at submit).
- **No duplicate apps.** `telegram_id` is unique; `/start` short-circuits for pending/approved users.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill values
createdb cast_db       # or use docker postgres
python manage.py migrate
python manage.py seed_questions
python manage.py createsuperuser
python manage.py runbot          # terminal 1
python manage.py runserver       # terminal 2 (admin on /admin/)
```

## Telegram setup

1. `@BotFather` → new bot → copy token into `BOT_TOKEN`.
2. `@BotFather` → `/mybots` → your bot → *Bot Settings* → *Group Privacy* → **Turn off**.
3. Create a supergroup, enable *Topics*, add the bot as admin with rights:
   *Invite Users via Link* + *Manage Chat* + *Delete Messages*.
4. Put the group ID into `CAST_GROUP_ID` (negative number, e.g. `-1001234567890`).
5. Create an admin chat (private group with reviewers), add the bot, put the ID into `ADMIN_CHAT_ID`.

## Deploy (Ubuntu)

```bash
sudo apt install python3.11-venv postgresql nginx ufw fail2ban
sudo adduser cast && sudo -iu cast
git clone <repo> ~/cast && cd ~/cast
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env
python manage.py migrate
python manage.py seed_questions
python manage.py collectstatic --noinput

sudo cp deploy/cast-bot.service deploy/cast-web.service /etc/systemd/system/
sudo cp deploy/nginx.conf /etc/nginx/sites-available/cast
sudo ln -s /etc/nginx/sites-available/cast /etc/nginx/sites-enabled/cast
sudo systemctl daemon-reload
sudo systemctl enable --now cast-bot cast-web
sudo systemctl reload nginx
sudo certbot --nginx -d cast.your-domain.com
```

## Daily backup (cron as `cast`)

```
0 3 * * * pg_dump -Fc cast_db | gzip > ~/backups/db_$(date +\%F).sql.gz
0 4 * * * find ~/backups -mtime +30 -delete
```

## Commands

- `/start` — begin application (or report existing status)
- `/cancel` — abort current application

## Admin workflow

New applications appear in `ADMIN_CHAT_ID` with inline **Approve** / **Reject** buttons.
Or bulk-review in Django admin: `Applications → select → actions → Approve/Reject selected`.
