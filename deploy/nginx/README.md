# VM HTTPS

HTTPS was configured on 2026-10-29 for `https://136.83.46.70`.
The expert recording page is `https://136.83.46.70/record`.
Use port 443 (no `:7860`) for browser microphone access.

VM configuration:

- `/etc/nginx/conf.d/eten-https.conf` proxies HTTPS to `127.0.0.1:7860`.
- Port 80 serves `/var/www/eten-acme/.well-known/acme-challenge/` and redirects other requests to HTTPS.
- The certificate and private key live under `/etc/letsencrypt/live/eten-platform-ip/`.
- Certbot runs from `/opt/eten-certbot/bin/certbot` (isolated environment).
- `eten-certbot-renew.timer` checks every six hours with a randomized delay.
- `/usr/local/sbin/eten-certbot-reload` validates and reloads nginx after renewal.
- Google Cloud firewall rule and instance tag `eten-web-https` allow ports 80 and 443 only on tagged VMs.
- Nginx access logging is disabled for this site to avoid logging participant links.

Check and test on the VM:

```sh
sudo nginx -t
sudo systemctl status nginx eten-certbot-renew.timer --no-pager
sudo /opt/eten-certbot/bin/certbot renew --dry-run --no-random-sleep-on-renew --run-deploy-hooks --deploy-hook /usr/local/sbin/eten-certbot-reload
```

The IP certificate is short lived, so keep the renewal timer enabled and port 80 reachable.
The current external IP is ephemeral; changing the VM IP requires updating the nginx
server name and redirect and obtaining a certificate for the new IP.
The original application listener on port 7860 remains available for compatibility;
its HTTP URL does not support microphone access.
