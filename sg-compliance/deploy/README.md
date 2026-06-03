# Deployment

## systemd service (Aliyun MY · `i-8ps6vece2dunt4ol17ku`)

The site runs as a systemd-managed Next.js production process listening on
`0.0.0.0:3000`. Logs are appended to `/var/log/sg-compliance.log`.

### One-time install

```bash
# Build first
cd /home/admin/APRI-C-Q-common-repo/sg-compliance
npm install
npm run build

# Service file
sudo touch /var/log/sg-compliance.log
sudo chown admin:admin /var/log/sg-compliance.log
sudo cp deploy/sg-compliance.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sg-compliance.service
```

### Operate

```bash
sudo systemctl status  sg-compliance
sudo systemctl restart sg-compliance      # after rebuilding
sudo systemctl stop    sg-compliance
tail -f /var/log/sg-compliance.log
```

### DeepSeek API key (Phase 3)

The `/api/chat` endpoint requires `DEEPSEEK_API_KEY`. The systemd unit reads
it from `/etc/sg-compliance/env`:

```bash
sudo mkdir -p /etc/sg-compliance
sudo tee /etc/sg-compliance/env > /dev/null <<'EOF'
DEEPSEEK_API_KEY=sk-your-real-key-here
EOF
sudo chmod 0640 /etc/sg-compliance/env
sudo chown root:admin /etc/sg-compliance/env
sudo systemctl restart sg-compliance
```

Without the key the chat page renders fine but the API returns HTTP 503
with `{"error":"missing_api_key"}`. The file is *not* in git; see
`.env.example` for the template.

### News refresh timer (Phase 2)

A systemd timer hits `/api/news/refresh` hourly to repopulate `data/news.json`.

```bash
sudo cp deploy/sg-compliance-refresh.service /etc/systemd/system/
sudo cp deploy/sg-compliance-refresh.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sg-compliance-refresh.timer

# Manual trigger / inspect
sudo systemctl start    sg-compliance-refresh.service
systemctl list-timers   sg-compliance-refresh.timer
cat /tmp/sg-compliance-refresh.json
```

Optional shared-secret guard for `/api/news/refresh`: set `NEWS_REFRESH_SECRET`
in the main service's environment, then append `?key=$SECRET` to the curl in
`sg-compliance-refresh.service`.

### Aliyun security group

The ECS security group must permit inbound TCP on port 3000 from the IPs that
need to access the site (or `0.0.0.0/0` for public review).

Public URL once SG is open: <http://47.250.10.235:3000/>
