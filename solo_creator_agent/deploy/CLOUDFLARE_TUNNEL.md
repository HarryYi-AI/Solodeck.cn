# Cloudflare Tunnel for api.solodeck.cn

Your DNS shows `api.solodeck.cn` → **Tunnel `solodeck-api`** (not a direct VPS A record).

When the tunnel connector is offline or points to the wrong port, browsers see **HTTP 530** and the chat UI shows:

```text
Unexpected token '<', "<!doctype "... is not valid JSON
```

That means Cloudflare returned an HTML error page instead of FastAPI JSON.

## Architecture

```text
www.solodeck.cn  → Cloudflare Pages (frontend)
/api/* on www    → Pages Function → https://api.solodeck.cn
api.solodeck.cn  → Cloudflare Tunnel → http://127.0.0.1:8787 (FastAPI on VPS)
```

Both **cloudflared** and **uvicorn** must run on the VPS.

## 1. Start FastAPI on the VPS

```bash
cd /path/to/heikesong
git pull origin main
pip install -r solo_creator_agent/requirements.txt
export PYTHONPATH=$(pwd)

# test
python3 -m uvicorn solo_creator_agent.api_spa:app --host 127.0.0.1 --port 8787
curl http://127.0.0.1:8787/api/health
```

Use systemd: `solo_creator_agent/deploy/solodeck-api.service`

## 2. Cloudflare Tunnel public hostname

In [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks → Tunnels** → `solodeck-api`:

| Field | Value |
|-------|--------|
| Public hostname | `api.solodeck.cn` |
| Service type | HTTP |
| URL | `http://127.0.0.1:8787` |

Save and ensure tunnel status is **Healthy** (green).

## 3. Run cloudflared on the VPS (no sudo)

Installed to `~/bin/cloudflared` or `/workspace/ylj/bin/cloudflared`.

Get **TUNNEL_TOKEN** from Cloudflare Zero Trust → **Networks → Tunnels → solodeck-api → Configure → Install connector** (copy the token from the install command).

```bash
cd /path/to/heikesong
bash solo_creator_agent/deploy/start-solodeck-api.sh

export TUNNEL_TOKEN='paste-token-here'
bash solo_creator_agent/deploy/start-cloudflared.sh
```

Or manually:

```bash
cloudflared tunnel run --token <YOUR_TUNNEL_TOKEN>
```

**Without cloudflared**, `api.solodeck.cn` returns **Error 1033** even if FastAPI is running locally.

### With sudo (optional, survives reboot)

```bash
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

## 4. Verify

```bash
# on VPS
curl http://127.0.0.1:8787/api/health

# from anywhere
curl https://api.solodeck.cn/api/health
curl -X POST https://www.solodeck.cn/api/v4/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"测试"}'
```

Expected health response:

```json
{"ok":true,"service":"SoloDeck Skill API"}
```

## 5. Common failures

| Symptom | Cause | Fix |
|---------|--------|-----|
| HTTP 530 | Tunnel down or wrong origin URL | Start `cloudflared`; set service to `127.0.0.1:8787` |
| Connection refused locally | FastAPI not running | Start uvicorn / `solodeck-api` service |
| 502 | Wrong port (e.g. 8501 Streamlit) | Tunnel must target **8787**, not Streamlit |
| Chat JSON parse error | Same as 530 (HTML error page) | Fix tunnel + API first |

## Alternative: drop tunnel, use A record

If you prefer not to use Tunnel:

1. Cloudflare DNS: delete tunnel record for `api`
2. Add **A** record: `api` → VPS public IP (proxied OK)
3. Nginx on VPS: `solo_creator_agent/deploy/nginx-api-solodeck.conf` → port 8787

Tunnel is optional; A record + nginx also works.
