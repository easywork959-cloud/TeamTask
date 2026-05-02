# Team Ops Hub — Simple Backend

A lightweight multi-user backend for small trusted teams. **No login required.** Designed for setup-and-forget simplicity.

## What this does

- **Multi-user**: 2–15 teammates can edit the same data from any device
- **Per-item updates**: Two people editing different tasks won't overwrite each other
- **No accounts**: Anyone with the URL can read/write (set an API key if you need basic protection)
- **Auto-sync**: Frontend pushes changes within ~1.5s and pulls every 5s for teammates' updates
- **Persistent**: All data saved to `data.json` (or any location via `DATA_FILE` env var)

## Setup — Local (1 minute)

```bash
cd backend-simple
pip install -r requirements.txt
python app.py
```

Then in the frontend:
1. Open **Data & Sync** tab
2. Paste `http://localhost:5000` in the Backend URL field
3. (Optionally) enter your name in "Your name" field — shown in "Last edited by"
4. Click **Connect** ✓

That's it. Your teammates can connect to the same URL from their browsers.

## Setup — Render.com (free, public URL, ~5 min)

This gives you a stable HTTPS URL that anyone on your team can connect to.

1. Push the `backend-simple/` folder to GitHub
2. Go to [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint**
3. Connect your GitHub repo. Render reads `render.yaml` and:
   - Creates a free web service
   - Mounts a 1GB persistent disk for `data.json`
   - Deploys automatically (~3 min)
4. Once deployed, copy the URL (e.g., `https://team-ops-hub-xyz.onrender.com`)
5. Share the URL with your team. Each teammate:
   - Opens the frontend HTML on their device
   - Goes to **Data & Sync**, pastes the URL, enters their name, clicks Connect

**Note**: Render's free tier sleeps after 15 min idle (~30s wake-up time). For always-on, upgrade to $7/mo or use Railway/Fly.

## Adding API key protection (optional)

By default, anyone with the URL can read/write. For extra protection, uncomment the API key section in `render.yaml`:

```yaml
- key: TEAM_OPS_API_KEY
  generateValue: true   # Render auto-generates a random secret
```

After redeploying, copy the auto-generated key from Render's Environment tab and share it privately with your team. Each teammate enters both the URL **and the key** in Data & Sync.

To enable API key locally: `TEAM_OPS_API_KEY=your-secret python app.py`

## How "multi-user" works (without login)

There's no concept of "users" on the backend — anyone with access can do anything. To track **who** edited what:

- The frontend has a "Your name" field in Data & Sync
- When you save anything, the frontend sends `X-User-Name: Alice` header
- The backend stamps each item with `_updated_by: "Alice"` and `_updated_at: <timestamp>`
- Other teammates see your name in tooltips like "Last edited by Alice, 2 mins ago"

This is honor-system attribution — anyone can claim any name. It's perfect for trusted small teams; not appropriate if you need real auth (use the v2 backend with login for that).

## How conflicts are handled

The backend uses **per-item updates**, so:
- Alice editing task A and Bob editing task B at the same time → both saved cleanly ✓
- Alice and Bob editing the SAME task within ~1 second → last write wins (the later save replaces the earlier)
- For most small teams this is fine. The frontend pulls every 5s, so you'll see teammates' edits quickly.

If you need stricter conflict detection, use the v2 backend (with version-based locking).

## Deploy alternatives

### Railway.app (free, no sleep on free tier)

```bash
npm i -g @railway/cli
railway login
cd backend-simple
railway init
railway up
# Add a volume in Railway dashboard, mount at /var/data
# Set env: DATA_FILE=/var/data/data.json
```

### Fly.io (free, fast)

```bash
flyctl launch  # in backend-simple/
flyctl volumes create data --size 1
# Edit fly.toml — add:
#   [mounts]
#     source="data"
#     destination="/var/data"
#   [env]
#     DATA_FILE="/var/data/data.json"
flyctl deploy
```

### Self-host (Raspberry Pi, NAS, VPS)

Just run `python app.py` and expose port 5000. Nginx reverse proxy + Let's Encrypt for HTTPS.

## API reference

All endpoints are JSON. If `TEAM_OPS_API_KEY` is set, include `X-API-Key: <key>` header.

Optionally include `X-User-Name: <name>` header to track who edited what (frontend does this automatically).

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check + data counts (always public) |
| `GET` | `/api/data` | Full snapshot of all collections |
| `PUT` | `/api/data` | Bulk replace (for backup restore) |
| `GET` | `/api/{collection}` | List items (`team` / `projects` / `tasks`) |
| `POST` | `/api/{collection}` | Create or upsert an item by id |
| `PATCH` | `/api/{collection}/{id}` | Update specific fields of an item |
| `DELETE` | `/api/{collection}/{id}` | Delete an item by id |

### Quick test

```bash
# Health
curl http://localhost:5000/api/health

# Add a task
curl -X POST -H "Content-Type: application/json" -H "X-User-Name: Alice" \
  -d '{"id":"t1","title":"Test","status":"Todo"}' \
  http://localhost:5000/api/tasks

# Get all tasks
curl http://localhost:5000/api/tasks
```

## Backup

Two ways:
1. **From frontend**: Data & Sync → Export Backup → downloads `data.json`
2. **From server**: `cp /var/data/data.json ~/backups/team-ops-$(date +%Y%m%d).json`

Restore: Frontend → Data & Sync → Import Backup, OR `curl -X PUT` with the JSON.

## Troubleshooting

- **CORS errors** → check the frontend URL is in `ALLOWED_ORIGINS` (default `*` allows all)
- **401 Unauthorized** → API key mismatch; re-check the value
- **Data not persisting on Render free tier** → make sure persistent disk is mounted (already configured in `render.yaml`)
- **Slow first request** → Render free tier sleeps after idle; first request takes ~30s
- **Two people see different data** → both should pull (Data & Sync → Pull from Cloud) to refresh

## Want stronger auth?

Use the v2 backend (`backend-v2/` folder) which adds:
- User accounts with passwords
- JWT tokens, role-based permissions
- Real-time push (SSE) instead of polling
- Activity log
- Version-based conflict detection

That's overkill for trusted small teams. This simple backend is for when "everyone with the URL is OK to edit" is good enough.
