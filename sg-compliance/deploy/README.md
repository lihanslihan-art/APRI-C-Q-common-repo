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

### Aliyun security group

The ECS security group must permit inbound TCP on port 3000 from the IPs that
need to access the site (or `0.0.0.0/0` for public review).

Public URL once SG is open: <http://47.250.10.235:3000/>
