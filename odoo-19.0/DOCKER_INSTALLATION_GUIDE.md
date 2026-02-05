# 🐳 Odoo 19.0 Docker Installation Guide

This guide provides step-by-step instructions to deploy your Odoo 19.0 project on an Ubuntu VM using Docker.

## 📋 Prerequisites

Before starting, ensure your Ubuntu VM has Docker and Docker Compose installed.

### Install Docker (if not installed)
```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```
*Note: You may need to log out and back in for group changes to take effect.*

---

## 🚀 Deployment Steps

### 1. Transfer Files to Ubuntu VM
Transfer your Odoo project folder to the Ubuntu VM using `scp`, `rsync`, or Git.

```bash
# Example using SCP
scp -r odoo-19.0 user@your-vm-ip:~/
```

### 2. Navigate to Project Directory
```bash
cd ~/odoo-19.0/odoo-19.0
```

### 3. Set Permissions for Entrypoint Script
Ensure the `entrypoint.sh` script is executable on the host:
```bash
chmod +x entrypoint.sh
```

### 4. Build and Start Containers
Run the following command to build the Odoo image and start the PostgreSQL database.

```bash
docker-compose up -d --build
```

### 5. Verify the Deployment
Check if the containers are running:
```bash
docker-compose ps
```

Check the logs to ensure Odoo started correctly:
```bash
docker-compose logs -f odoo
```

---

## 🔑 Accessing Odoo

Once the containers are running, you can access Odoo in your browser:

- **Main URL**: `http://your-vm-ip:8069`
- **Secret Apps Access**: `http://your-vm-ip:8069/action-39`

---

## 📂 Configuration Details

### File Structure in Docker
- **Project Root**: `/opt/odoo`
- **Configuration**: `/etc/odoo/odoo.conf`
- **PostgreSQL Data**: Persistent volume `odoo-db-data`

### Custom Addons
Your custom addons are located in `/opt/odoo/custom_addons`. Any changes made to the files on the host will be reflected in the container due to volume mounting.

---

## 🛠️ Common Commands

| Action | Command |
|--------|---------|
| Start Services | `docker-compose up -d` |
| Stop Services | `docker-compose down` |
| View Logs | `docker-compose logs -f odoo` |
| Restart Odoo | `docker-compose restart odoo` |
| Update Modules | `docker-compose exec odoo python3 odoo-bin -u all -d YOUR_DB --stop-after-init` |
| Access Shell | `docker-compose exec odoo bash` |

---

## ⚠️ Troubleshooting

### Database Connection Issues
If Odoo fails to connect to the database, ensure the `db` container is healthy:
```bash
docker-compose logs db
```

### Permission Denied (e.g. entrypoint.sh)
If you see an error like `exec: "/opt/odoo/entrypoint.sh": permission denied`, run:
```bash
chmod +x entrypoint.sh
```
This is required because the file is mounted from your VM host, and its permissions must allow execution.

If you encounter other permission issues with volumes:
```bash
sudo chown -R $USER:$USER .
chmod -R 755 .
```

### Port 8069 Already in Use
If port 8069 is blocked, you can change the mapping in `docker-compose.yml`:
```yaml
ports:
  - "8080:8069"  # Maps VM port 8080 to Odoo container port 8069
```
