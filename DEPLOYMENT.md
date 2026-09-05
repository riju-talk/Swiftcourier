# Deploying SwiftCourier to AWS (EC2 + RDS)

Assumes: an existing RDS Postgres instance, a domain you control, and a fresh EC2 instance.
The compose stack already runs Postgres against RDS (no `db` service) and every container
uses `restart: unless-stopped`, so once Docker itself survives a reboot the whole stack does too.

## 1. EC2 instance

* Amazon Linux 2023 or Ubuntu 22.04, `t3.small` minimum (Gunicorn + Celery workers + Redis + nginx).
* Security group inbound: `22` (your IP only), `80`, `443` from `0.0.0.0/0`. Nothing else public —
  RDS/Redis stay inside the VPC.
* Allocate an **Elastic IP** and associate it. Without one, a stop/start changes the public IP and
  breaks your DNS record.
* RDS security group: allow inbound `5432` from the EC2 instance's security group (not from the
  internet).

## 2. Install Docker

Amazon Linux 2023:
```bash
sudo dnf install -y docker
sudo systemctl enable --now docker      # `enable` is what makes it survive a reboot
sudo usermod -aG docker $USER           # log out/in once for this to take effect
DOCKER_COMPOSE_VERSION=v2.29.7
sudo curl -SL "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o /usr/libexec/docker/cli-plugins/docker-compose
sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
docker compose version
```
Ubuntu 22.04: follow https://docs.docker.com/engine/install/ubuntu/ (installs the compose plugin
too), then `sudo systemctl enable --now docker`.

`systemctl enable` is the piece that makes containers come back after an **instance reboot**, not
just a crash — `restart: unless-stopped` on its own only rehandles the Docker daemon restarting or
a container dying, it doesn't start the daemon on boot.

## 3. Get the code and configure `.env`

```bash
git clone <your-repo-url> swiftcourier && cd swiftcourier
cp .env.sample .env
```
Edit `.env` yourself (you said you'd handle this) — the fields that matter for this deploy:
* `DATABASE_*` → your RDS endpoint/creds, `DATABASE_SSLMODE=verify-full` (uses the committed
  `rds-ca-bundle.pem`, already baked into the image).
* `SECRET_KEY` → a real random value, `DEBUG=False`.
* `PRIMARY_HOST` → the exact hostname you're pointing at this box, e.g. `app.example.com`. This
  feeds `ALLOWED_HOSTS`, CSRF trusted origins, and — new — the nginx server block below. If you also
  want the bare apex or a `www.` host to work, add them explicitly to `ALLOWED_HOSTS` too (only
  `PRIMARY_HOST` itself is auto-appended).
* `TRUST_PROXY_SSL_HEADER=True` (already the default when `DEBUG=False`) — required so Django sees
  requests as HTTPS once nginx is the one terminating TLS.

## 4. Point DNS at the box

At your domain registrar / Route 53, create an **A record** for `PRIMARY_HOST` (and `www` if you're
using it) pointing at the EC2 Elastic IP. Wait for it to resolve (`dig +short app.example.com`)
before requesting a certificate — Let's Encrypt validates over the real internet.

## 5. Bring up the app (without nginx yet)

```bash
docker compose build
docker compose up -d redis web worker-fast worker-ship beat
docker compose run --rm web python manage.py createsuperuser
```
`web` is not published to the host at this point (`nginx` is the only public entrypoint, added
next) — this is expected, nothing to browse to yet.

## 6. Bootstrap the TLS certificate (one-time)

`nginx`'s config already points at `/etc/letsencrypt/live/${PRIMARY_HOST}/...`, so it refuses to
start until that cert exists. Get the first one with certbot's standalone mode, which briefly binds
port 80/443 itself (nginx isn't running yet, so this is safe):

```bash
docker run --rm -p 80:80 -p 443:443 \
  -v swiftcourier_certbot-certs:/etc/letsencrypt \
  -v swiftcourier_certbot-www:/var/www/certbot \
  certbot/certbot certonly --standalone \
  -d "$PRIMARY_HOST" \
  --email you@example.com --agree-tos --no-eff-email -n
```
(Volume names are prefixed with the compose project name — usually the directory name,
`swiftcourier`; check with `docker volume ls` if the command above says the volume doesn't exist yet,
or just run `docker compose up -d --no-start nginx` first to create the named volumes.)

## 7. Start nginx and the renewal loop

```bash
docker compose up -d nginx certbot
docker compose ps
```
Visit `https://<PRIMARY_HOST>/account/signin/` — should load over HTTPS.

The `certbot` service renews the cert via the shared webroot every 12h on its own. nginx doesn't
auto-reload when the cert file changes, so add a weekly reload to the host's crontab (cheap, safe,
no downtime):
```bash
crontab -e
# add:
0 3 * * 0 cd /path/to/swiftcourier && docker compose exec nginx nginx -s reload
```

## 8. Confirm "never shuts down"

* `restart: unless-stopped` on every service (already set) → a crashed container or a Docker daemon
  restart brings everything back without you touching it.
* `systemctl enable docker` (step 2) → an EC2 reboot brings the daemon back, which then restarts
  every container per the policy above.
* Test it once: `sudo reboot`, wait ~1 min, `docker compose ps` should show everything `Up`.

## Day-2 operations

Deploy a code change:
```bash
git pull
docker compose build
docker compose up -d --no-deps web worker-fast worker-ship beat
```
Logs: `docker compose logs -f web` (or any service name).
Migrations run automatically on `web` container start (see `docker/entrypoint.sh`).
