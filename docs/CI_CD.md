# CI/CD with GitHub Actions

Two workflows live in `.github/workflows/`:

- `test.yml` — runs pytest + lint on every push and pull request
- `deploy.yml` — on push to `main`, runs tests, then SSHes into your VPS and rebuilds the container

The deploy workflow is also runnable on demand: GitHub → Actions → "Deploy" → "Run workflow" button.

## How it works

```
git push origin main
        │
        ▼
  test.yml runs    (pytest, lint, compile-check)
        │  passes
        ▼
  deploy.yml runs
   ├─ checkout repo
   ├─ load deploy SSH key
   ├─ ssh into VPS as bna user
   ├─ git pull
   ├─ scripts/secrets-fetch.sh doppler  (refresh .env from Doppler)
   ├─ docker compose up -d --build
   └─ health check
```

End to end takes ~2 minutes. Failed health checks fail the workflow loudly.

## One-time setup (3 steps, ~10 minutes)

### 1. Generate a dedicated deploy key

This is a separate SSH key from your laptop's. It's used only by GitHub Actions to log into your VPS, and it lives only in two places: GitHub Actions secrets and the VPS's `authorized_keys`.

On your laptop:

```bash
# Generate a keypair specifically for CI deploys
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/synapse_deploy -N ""

# Copy the PUBLIC half to the VPS bna user's authorized_keys
ssh-copy-id -i ~/.ssh/synapse_deploy.pub bna@<vps-ip>

# Verify it works
ssh -i ~/.ssh/synapse_deploy bna@<vps-ip> 'echo deploy-key-works'
```

Keep the private key (`~/.ssh/synapse_deploy`) safe on your laptop — you'll paste it into GitHub Actions secrets in a moment.

### 2. Add three secrets to GitHub Actions

GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**.

Add these three:

| Name | Value |
|---|---|
| `DEPLOY_SSH_KEY` | Full contents of `~/.ssh/synapse_deploy` (private key, including `-----BEGIN…` and `-----END…` lines) |
| `VPS_HOST` | Your VPS IP address (e.g., `5.161.42.123`) |
| `VPS_USER` | `bna` (the deploy user `bootstrap-vps.sh` creates) |

### 3. Optional: require approval for production deploys

If you want a "deploy gate" — push lands, tests pass, but a human has to click before it ships:

GitHub repo → **Settings → Environments → New environment** → name it `production` → tick **"Required reviewers"** → add yourself.

The deploy workflow already references `environment: production`, so this works as soon as the environment exists.

Without this, every push to `main` deploys automatically.

## Triggering deploys

Three ways:

1. **Push to main** — auto-deploys (assuming tests pass and approval, if configured, is granted).
2. **Pull request merged into main** — same as above.
3. **Manual — "Run workflow" button** — go to Actions → Deploy → click the dropdown → Run workflow. Useful if you've changed Doppler secrets and want to re-pull them without making a commit.

## What the workflow doesn't do

It does not bootstrap a fresh VPS. The first time you provision a new server, run `scripts/bootstrap-vps.sh` and `scripts/deploy.sh` manually. After that, the CI workflow handles every subsequent change.

It does not manage Doppler secrets. The workflow runs `scripts/secrets-fetch.sh doppler` on the VPS, which assumes:
- Doppler CLI is already installed on the VPS (the manual deploy installs it)
- The VPS has a saved Doppler config OR the `DOPPLER_TOKEN` env var is set

If you need to rotate the Doppler token, update it both in Doppler (regenerate) and on the VPS (`doppler configure set token <new>` as the bna user).

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `Permission denied (publickey)` in the deploy step | Public key not in VPS authorized_keys | Re-run step 1's `ssh-copy-id` |
| `Host key verification failed` | VPS host key changed (server rebuilt) | Workflow re-adds via `ssh-keyscan`; if it persists, manually trigger a re-run |
| `secrets-fetch.sh` errors with `not authenticated` | `DOPPLER_TOKEN` missing on VPS | SSH in as `bna`, run `doppler configure set token <token>` |
| Container starts then crashes | Bad code or missing secret | Check `docker compose logs` on the VPS, or read the workflow's "Health check" step output |

## Security notes

- The deploy key is **scoped to the bna user** on the VPS. It cannot escalate to root.
- The `webfactory/ssh-agent` action loads the private key into a temporary agent that only lives for the duration of the workflow run.
- Doppler secrets never appear in workflow logs — `secrets-fetch.sh` writes them straight to `.env` on the VPS.
- GitHub masks values from `secrets.*` automatically; even if you accidentally `echo $DEPLOY_SSH_KEY`, it shows as `***`.
- The deploy SSH key is one of the most powerful credentials you have. If it leaks, regenerate it (step 1) and update the GitHub secret. The old key on the VPS becomes useless once you remove it from `authorized_keys`.
