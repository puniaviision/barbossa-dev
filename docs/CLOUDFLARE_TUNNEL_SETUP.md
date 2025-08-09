# Cloudflare Tunnel Setup Documentation

## Overview

This document details the complete setup process for bypassing CGNAT (Carrier-Grade NAT) restrictions using Cloudflare Tunnel to provide external access to services running on the homeserver. This solution was implemented on 2025-08-09 to address the inability to use traditional port forwarding due to ISP CGNAT.

## Problem Background

### CGNAT Issue
- **ISP**: Hyperoptic
- **Problem**: Router WAN IP (100.72.9.72) is in the private CGNAT range (100.64.0.0/10)
- **Public IP**: 152.37.119.234 (not directly accessible)
- **Impact**: Traditional port forwarding is impossible due to double NAT

### Services Requiring External Access
1. **Barbossa Portal** (HTTPS) - Port 8443
2. **Davy Jones Webhook** (HTTP) - Port 3001  
3. **API Service** (HTTP) - Port 80
4. **HTTPS Service** - Port 443

## Solution: Cloudflare Tunnel

Cloudflare Tunnel creates an encrypted tunnel from the server to Cloudflare's edge network, bypassing NAT restrictions entirely. Traffic flows: `Internet → Cloudflare → Tunnel → Local Services`

## Setup Process

### 1. Prerequisites
- Cloudflare account with domain added
- Domain nameservers pointing to Cloudflare
- Root/sudo access on the server

### 2. Install Cloudflared

```bash
# Add Cloudflare GPG key
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-archive-keyring.gpg >/dev/null

# Add Cloudflare repository
echo "deb [signed-by=/usr/share/keyrings/cloudflare-archive-keyring.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list

# Update and install
sudo apt-get update
sudo apt-get install -y cloudflared

# Verify installation
cloudflared --version
```

### 3. Authenticate with Cloudflare

```bash
# Login to Cloudflare (opens browser for authentication)
cloudflared tunnel login

# Certificate will be saved to ~/.cloudflared/cert.pem
# If saved elsewhere, move it:
mv ~/cert.pem ~/.cloudflared/cert.pem
chmod 600 ~/.cloudflared/cert.pem
```

### 4. Create the Tunnel

```bash
# Create a new tunnel (generates unique ID)
cloudflared tunnel create eastindia-tunnel

# This creates:
# - Tunnel ID: 5ba42edf-f4d3-47c8-a1b3-68d46ac4f0ec
# - Credentials: ~/.cloudflared/5ba42edf-f4d3-47c8-a1b3-68d46ac4f0ec.json

# List tunnels to verify
cloudflared tunnel list
```

### 5. Configure the Tunnel

Create configuration file at `/home/dappnode/.cloudflared/config.yml`:

```yaml
tunnel: 5ba42edf-f4d3-47c8-a1b3-68d46ac4f0ec
credentials-file: /home/dappnode/.cloudflared/5ba42edf-f4d3-47c8-a1b3-68d46ac4f0ec.json

ingress:
  # Barbossa Portal (HTTPS)
  - hostname: eastindiaonchaincompany.xyz
    service: https://localhost:8443
    originRequest:
      noTLSVerify: true
  
  # Davy Jones Webhook (HTTP)
  - hostname: webhook.eastindiaonchaincompany.xyz
    service: http://localhost:3001
  
  # API endpoint
  - hostname: api.eastindiaonchaincompany.xyz
    service: http://localhost:80
  
  # Catch-all rule (required)
  - service: http_status:404
```

### 6. Configure DNS Records

In Cloudflare Dashboard (dash.cloudflare.com):

1. **Remove conflicting A records** for the domain and subdomains
2. **Add CNAME records**:

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| CNAME | @ | 5ba42edf-f4d3-47c8-a1b3-68d46ac4f0ec.cfargotunnel.com | Proxied |
| CNAME | webhook | 5ba42edf-f4d3-47c8-a1b3-68d46ac4f0ec.cfargotunnel.com | Proxied |
| CNAME | api | 5ba42edf-f4d3-47c8-a1b3-68d46ac4f0ec.cfargotunnel.com | Proxied |

**Note**: The target is `<tunnel-id>.cfargotunnel.com`

### 7. Start the Tunnel Service

```bash
# Install as system service
sudo cloudflared service install

# Start the service
sudo systemctl start cloudflared

# Enable auto-start on boot
sudo systemctl enable cloudflared

# Check status
sudo systemctl status cloudflared

# View logs
sudo journalctl -u cloudflared -f
```

### Alternative: Run in tmux (for testing)

```bash
# Create tmux session
tmux new -s cloudflared-tunnel

# Run tunnel
cloudflared tunnel run eastindia-tunnel

# Detach: Ctrl+B, then D
# Reattach: tmux attach -t cloudflared-tunnel
```

## Verification

### Test External Access

```bash
# Test each service endpoint
curl -I https://eastindiaonchaincompany.xyz
curl -I https://webhook.eastindiaonchaincompany.xyz
curl -I https://api.eastindiaonchaincompany.xyz
```

### Check Tunnel Status

```bash
# View tunnel info
cloudflared tunnel info eastindia-tunnel

# Check service logs
sudo journalctl -u cloudflared --since "1 hour ago"

# Monitor tunnel metrics
cloudflared tunnel metrics eastindia-tunnel
```

## Firewall Configuration

Although Cloudflare Tunnel bypasses NAT, local firewall (UFW) should still allow the services:

```bash
# Allow required ports
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 3001/tcp
sudo ufw allow 8443/tcp

# Check status
sudo ufw status numbered
```

## Security Considerations

1. **No Exposed Ports**: Server doesn't need public IP or open ports
2. **Encrypted Tunnel**: All traffic through tunnel is encrypted
3. **Cloudflare Protection**: Benefits from Cloudflare's DDoS protection
4. **Access Control**: Can add Cloudflare Access policies if needed
5. **Origin Certificate**: For production, use Cloudflare Origin CA certificates

## Maintenance

### Update Tunnel Configuration

```bash
# Edit config
nano ~/.cloudflared/config.yml

# Restart service to apply changes
sudo systemctl restart cloudflared
```

### Add New Services

1. Add ingress rule to `config.yml`
2. Create DNS CNAME record in Cloudflare
3. Restart cloudflared service

### Remove Tunnel

```bash
# Stop service
sudo systemctl stop cloudflared
sudo systemctl disable cloudflared

# Delete tunnel
cloudflared tunnel delete eastindia-tunnel

# Remove DNS records from Cloudflare Dashboard
```

## Troubleshooting

### Tunnel Won't Start
- Check credentials file exists: `ls ~/.cloudflared/*.json`
- Verify tunnel ID in config matches credentials file
- Check service logs: `sudo journalctl -u cloudflared -n 50`

### DNS Resolution Issues
- Ensure nameservers point to Cloudflare (not registrar)
- Wait 5-10 minutes for DNS propagation
- Check with: `dig eastindiaonchaincompany.xyz`

### Connection Refused
- Verify local services are running
- Check localhost connectivity: `curl http://localhost:3001`
- Review ingress rules in config.yml

### Certificate Errors
- Use `noTLSVerify: true` for self-signed certificates
- Or install Cloudflare Origin CA certificate

## Setup Script

For automated setup, use `/home/dappnode/setup-cloudflare-tunnel.sh`:

```bash
#!/bin/bash
# Cloudflare Tunnel Setup Script
# Purpose: Bypass CGNAT restrictions for external access

set -e

echo "🚀 Setting up Cloudflare Tunnel to bypass CGNAT..."

# [Full script content available in the file]
```

## Quick Reference

### Service URLs
- **Barbossa Portal**: https://eastindiaonchaincompany.xyz
- **Webhook Service**: https://webhook.eastindiaonchaincompany.xyz  
- **API Service**: https://api.eastindiaonchaincompany.xyz

### Key Files
- **Config**: `~/.cloudflared/config.yml`
- **Credentials**: `~/.cloudflared/5ba42edf-f4d3-47c8-a1b3-68d46ac4f0ec.json`
- **Certificate**: `~/.cloudflared/cert.pem`
- **Setup Script**: `~/setup-cloudflare-tunnel.sh`

### Commands
```bash
# Service management
sudo systemctl status cloudflared
sudo systemctl restart cloudflared
sudo journalctl -u cloudflared -f

# Tunnel management
cloudflared tunnel list
cloudflared tunnel info eastindia-tunnel
cloudflared tunnel run eastindia-tunnel
```

## Related Documentation

- [Barbossa Portal Documentation](../README.md#web-portal)
- [UFW Firewall Configuration](./FIREWALL_SETUP.md)
- [Service Architecture](./SERVICES_ARCHITECTURE.md)

---

**Last Updated**: 2025-08-09
**Author**: East India Onchain Company
**Purpose**: Document CGNAT bypass solution using Cloudflare Tunnel