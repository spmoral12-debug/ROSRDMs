# 🌐 ROS REDEMPTION - DEDICATED SERVER HOSTING & DEPLOYMENT GUIDE

Welcome boss! Ito ang kumpletong gabay para i-deploy ang **ROS Redemption** master server online upang makapaglaro ka kasama ang mga kaibigan mo o publiko nang hindi nakabukas ang PC mo 24/7.

---

## 1. 🖥️ Saan Pwede Mag-Host? (Recommended VPS Providers & Links)

Para maging 24/7 online ang game server mo, kailangan mo ng **VPS (Virtual Private Server)** o **Dedicated Server**. Narito ang pinaka-sulit at matatag na mga server provider:

| Provider | Recommended Plan | Presyo / Buwan | Location | Link |
| :--- | :--- | :--- | :--- | :--- |
| **Hostinger** *(Pinaka-sulit at Madaling Gamitin)* | **KVM 2** (2 vCPU, 8GB RAM, 100GB NVMe) | ~$7 - $9 / mo | Singapore / US | [Hostinger VPS](https://www.hostinger.com/vps-hosting) |
| **DigitalOcean** *(Developer Friendly & Mabilis)* | **Basic Droplet** (2 CPU, 4GB RAM) | ~$24 / mo | Singapore (SG1) / US | [DigitalOcean](https://www.digitalocean.com/products/droplets) |
| **Hetzner** *(Pinaka-mura sa Performance)* | **CPX21 / CPX31** (3-4 vCPU, 4-8GB RAM) | ~€7 - €13 / mo | Germany / US | [Hetzner Cloud](https://www.hetzner.com/cloud) |
| **Contabo** *(Sobrang Laki ng RAM sa Mababang Presyo)* | **Cloud VPS S** (4 vCPU, 8GB RAM, 50GB NVMe) | ~$6 / mo | Singapore / US / EU | [Contabo VPS](https://contabo.com/en/vps/) |
| **Vultr** *(Mababang Latency sa SEA)* | **Cloud Compute** (2 vCPU, 4GB RAM) | ~$20 / mo | Singapore / Tokyo | [Vultr](https://www.vultr.com/pricing/) |

> 💡 **Tip:** Piliin ang **Singapore (SG / Asia)** na server location kung ang karamihan sa maglalaro ay taga-Pilipinas para **sobrang baba ng Ping (15ms - 40ms)**!

---

## 2. ⚙️ Recommended Server Specifications

* **Operating System:** 
  * **Option A (Madali):** Windows Server 2022 o 2019 (May desktop interface tulad ng PC mo).
  * **Option B (Matipid):** Ubuntu 22.04 / 24.04 LTS (Linux command-line, mas mura at matipid sa RAM).
* **CPU:** 2 vCPU o higit pa
* **RAM:** 4 GB minimum (8 GB kung marami kayong sabay-sabay maglalaro)
* **Storage:** 20 GB - 50 GB SSD / NVMe
* **Bandwidth:** 1 Gbps port (Standard sa lahat ng VPS sa itaas)

---

## 3. 🔓 Network Firewall & Ports na Dapat Buksan

Sa firewall ng iyong VPS provider (Cloud Security Group / Firewall) at sa Windows/Linux firewall, buksan ang mga sumusunod na ports:

| Port | Protocol | Gamit sa Game |
| :--- | :--- | :--- |
| **19000** | **TCP & UDP** | **ROS Redemption Lobby & Game Server** |
| **19100** | **UDP** | **Battleground Combat Host** |
| **80** | **TCP** | **Update Mirror & Manifest Server** |
| **443** | **TCP** | **HTTPS Update Server** |
| **8790** | **TCP** | **Admin Web Dashboard** (`http://your-server-ip:8790/admin`) |

---

## 4. 🚀 Step-by-Step Deployment (Windows Server)

Kung **Windows Server** ang kinuha mo:
1. Kumonekta sa iyong server gamit ang **Remote Desktop Connection (RDP)** sa iyong PC (`mstsc.exe`).
2. I-copy ang buong folder na ito: `C:\DieHardROS\ROS_Redemption_Server_Package` papunta sa VPS mo (hal. sa `C:\ROS_Redemption_Server`).
3. Buksan ang `local_update\servers.json` sa VPS:
   * Palitan ang `"127.0.0.1"` ng **Public IP Address** ng iyong VPS!
4. Buksan ang `START_SERVER.bat`.
5. Makikita mo ang berdeng console na nagsasabing:
   `[local-game] 1 server(s) up (ROS-Redemption-Official:19000)`
6. **Online na ang Server mo 24/7!**

---

## 5. 🐧 Step-by-Step Deployment (Linux / Ubuntu VPS)

Kung **Ubuntu / Debian Linux** ang kinuha mo:
1. Kumonekta via SSH: `ssh root@your-server-ip`
2. I-upload ang folder gamit ang SFTP (FileZilla / WinSCP).
3. Siguraduhing may Python 3:
   ```bash
   sudo apt update && sudo apt install -y python3 python3-pip
   ```
4. I-open ang ports sa UFW firewall:
   ```bash
   sudo ufw allow 19000/tcp
   sudo ufw allow 19000/udp
   sudo ufw allow 19100/udp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw allow 8790/tcp
   sudo ufw enable
   ```
5. I-edit ang `local_update/servers.json` at ilagay ang Public IP ng iyong VPS.
6. Simulan ang server sa background gamit ang `screen` o `nohup`:
   ```bash
   chmod +x START_SERVER.sh
   screen -S ros_server ./START_SERVER.sh
   ```
   *(Pindutin ang `Ctrl + A` tapos `D` para i-detach ang screen habang tumatakbo sa background).*

---

## 6. 🎮 Paano Ikonekta ang Game Client ng mga Players?

Sa client folder ng bawat player (kasama ka):
1. Buksan ang `local_update\servers.json` at `local_update\server_list_pc.txt`.
2. Palitan ang `127.0.0.1` ng **Public IP** ng VPS mo.
3. Kapag binuksan nila ang game (`Play_ROS_Redemption.bat`), kusa na silang kokonekta sa iyong 24/7 Dedicated Server!

---

## 👑 Admin Control Panel

* URL: `http://<YOUR-SERVER-IP>:8790/admin`
* Admin Key: Makikita sa `server_data\admin_key.txt`
* Sa admin panel na ito pwede kang mag-bigay ng **Diamonds, Gold, mag-ban ng cheaters, at mag-check ng active players** online!

