# Secrets Management

The agent needs quite a few credentials: Anthropic API key, X tokens, Threads token, Telegram bot token, ElevenLabs, etc. This doc explains your options, ordered from simplest to most robust, and gives you a recommended setup for a solo operator.

## TL;DR recommendation

For a single-VPS solo deployment: **`.env` file with `chmod 600` on the server, never committed to git**. This is what `deploy.sh` sets up automatically.

For anything you want to version-control or share across machines: **SOPS + age** to commit encrypted secrets to the repo. See the "Tier 2" section below.

For a team or multiple environments: **Doppler** or **Infisical** (both have free tiers).

If you already use 1Password as your password manager: **`op inject`** — see Tier 2.5.

## Helper scripts

Whichever option you pick, the repo provides drop-in helpers that render `.env`
from your chosen secret store with a single command:

```bash
bash scripts/setup-env.sh                    # interactive prompts (Tier 1)
bash scripts/secrets-fetch.sh doppler        # Tier 3 - Doppler
bash scripts/secrets-fetch.sh sops           # Tier 2 - SOPS + age
bash scripts/secrets-fetch.sh 1password      # Tier 2.5 - 1Password CLI
bash scripts/secrets-fetch.sh aws            # Tier 4 - AWS Secrets Manager
```

All four write `.env` with `chmod 600` and are safe to re-run.

---

## Tier 1 — `.env` file on the server (what you have today)

**Security posture:** Good for a single VPS you control.

**How it works:**
- `.env.example` is committed to git with blank values.
- Real `.env` lives only on the server, permissions `600` so only the deploy user can read it.
- `.env` is in `.gitignore` and can never be accidentally committed.
- Docker Compose reads it automatically via `env_file: .env`.

**Pros:** Zero dependencies. Free. Fast.

**Cons:** Secrets are plaintext on disk. If someone gains shell access, game over. You can't easily rotate or audit usage.

**When to use it:** Day 1 through the first few months. Good enough until you have >1 server or >1 person.

---

## Tier 2 — SOPS + age (encrypted secrets in git)

**Security posture:** Good for solo or small team. Git-native.

**How it works:**
- You have a local age keypair (like SSH keys, but for encrypting files).
- `secrets.enc.yaml` lives in the repo, encrypted. Only holders of the age private key can decrypt it.
- On deploy, SOPS decrypts `secrets.enc.yaml` to `.env` on the server.

**One-time setup:**

```bash
# On your laptop
brew install sops age            # (or apt install on Linux)
age-keygen -o ~/.config/sops/age/keys.txt
grep 'public key' ~/.config/sops/age/keys.txt
# Copy the public key - it looks like: age1abc...xyz
```

Create `.sops.yaml` in the repo root:

```yaml
creation_rules:
  - path_regex: secrets\.enc\.yaml$
    age: age1abc...xyz   # your public key
```

Create and encrypt `secrets.enc.yaml`:

```bash
sops secrets.enc.yaml
# editor opens; paste your secrets as YAML, save.
# The file on disk is now encrypted - safe to commit.
git add .sops.yaml secrets.enc.yaml
git commit -m "Encrypted secrets"
```

On the server:

```bash
# Install SOPS + age on the server
apt install -y age
wget -O /usr/local/bin/sops https://github.com/getsops/sops/releases/latest/download/sops-...-linux.amd64
chmod +x /usr/local/bin/sops

# Copy your age PRIVATE key to the server (do this ONCE, via scp)
mkdir -p /home/bna/.config/sops/age
scp ~/.config/sops/age/keys.txt bna@server:/home/bna/.config/sops/age/keys.txt

# Decrypt into .env at deploy time
sops -d secrets.enc.yaml | yq -o dotenv > .env
chmod 600 .env
```

**Pros:**
- Secrets version-controlled with the code.
- Any teammate with the age key can decrypt.
- Rotate by editing + recommitting.
- Works with git hooks / CI.

**Cons:**
- Extra tooling (~15 min setup).
- The age private key is still a single point of failure — keep it in 1Password or a hardware key.

**When to use it:** Once you have a second machine, a CI pipeline, or want to track who changed which secret when.

---

## Tier 2.5 — 1Password CLI

If you already use 1Password as a password manager, the CLI lets you template
a `.env` without copy-pasting any secret values.

**One-time setup:**

```bash
brew install 1password-cli
op signin
op vault create breaking-news-agent
# Add API Credential items to the vault, one per service.
```

The repo ships a template at `.env.1password.tpl` that references each item
via `op://` URIs. Render it with:

```bash
bash scripts/secrets-fetch.sh 1password
# runs: op inject -i .env.1password.tpl -o .env
```

For headless servers, create a 1Password Service Account and set
`OP_SERVICE_ACCOUNT_TOKEN` instead of running `op signin`.

**Pros:** TOTP support, biometric unlock on dev machines, items reviewable in
the 1Password UI, free if you already pay for the family/team plan.
**Cons:** $3/mo per user without an existing plan. Server needs a service
account token to run unattended.

---

## Tier 3 — Cloud secret manager (Doppler / Infisical)

**Security posture:** Strong. Audit logs, rotation, granular access.

**Doppler** (https://doppler.com) — easiest UX. Free tier: 5 users, 3 projects, unlimited secrets.

```bash
# One-time
curl -Ls https://cli.doppler.com/install.sh | sh
doppler login
doppler setup   # links the repo to a Doppler project
```

In your agent: replace `docker compose up -d` with:

```bash
doppler run --project bna --config prod -- docker compose up -d
```

Doppler injects secrets as env vars — your `.env` file disappears. Rotate in the dashboard; all running pods pick up changes on restart.

**Infisical** (https://infisical.com) — open source alternative. Self-host for free, or use their cloud (free tier: 5 users, unlimited secrets).

**Pros of either:**
- Web UI for editing.
- Audit log of who accessed what.
- Webhook-based rotation.
- Works nicely with GitHub Actions / any CI.

**Cons:**
- Requires internet connectivity at deploy time to fetch secrets (usually fine).
- Vendor lock-in if cloud-hosted.

**When to use it:** When you have a second person on the team, or multiple environments (staging/prod), or you need auditability.

---

## Tier 4 — Cloud-native (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault)

**Security posture:** Enterprise-grade.

**AWS Secrets Manager**: $0.40/secret/month + $0.05/10k API calls. Integrates with IAM roles so your EC2 instance fetches secrets without credentials stored anywhere. Great if you're already on AWS.

**GCP Secret Manager**: $0.06/secret/month. Similar story on GCP.

**HashiCorp Vault**: Free (self-hosted, open source). Extremely powerful — dynamic DB credentials, PKI issuing, transit encryption. Serious operational burden to run correctly.

**When to use it:** When you're already on that cloud, or the compliance story matters (SOC 2, HIPAA).

---

## Comparison

| Option | Setup time | Cost | Audit trail | Rotation | Solo-friendly |
|---|---|---|---|---|---|
| `.env` on server | 0 min | $0 | None | Manual | Yes |
| SOPS + age | 15 min | $0 | Git log | Git commit | Yes |
| Doppler | 15 min | $0 (free tier) | Yes | Dashboard | Yes |
| Infisical | 15-60 min | $0 self-host | Yes | Dashboard | Yes |
| AWS Secrets Manager | 30 min | ~$1-5/mo | Yes | API/IAM | Overkill |
| Vault | 2+ hrs | $0 + ops | Yes | Dynamic | Overkill |

## Key hygiene rules regardless of tool

1. **Never commit `.env`.** The `.gitignore` covers this; verify with `git check-ignore .env`.
2. **Scope each key to one service.** Don't reuse your personal Anthropic key for the bot — create a separate one so you can revoke without disrupting other work.
3. **Set spend limits.** Anthropic and OpenAI both let you set monthly caps. Use them.
4. **Rotate on any suspicion of leak.** All providers have one-click rotation in their dashboards.
5. **Back up the age key** (if using SOPS) in a password manager. If you lose it, you can't decrypt.
6. **Audit logs quarterly.** Review the X / Telegram dashboards for unexpected API usage.
7. **Use separate keys per environment.** Even for a solo operator, keep dev and prod keys distinct — makes debugging safer.

## Recommended path for you specifically

Given you're solo, on a $5/mo VPS, and want to move fast:

**Week 1:** Stay on Tier 1 (`.env` on server). Just chmod 600 it. `deploy.sh` handles this.

**Month 2:** Migrate to Tier 2 (SOPS + age). Takes 15 minutes and lets you version-control secret changes. Also makes it trivial to spin up a second server.

**Month 6+:** Consider Doppler if you add a collaborator or want audit logs. Until then, SOPS is plenty.

Skip AWS Secrets Manager / Vault unless you have a specific compliance requirement. They're powerful but overkill at this scale.
