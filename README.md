# termux-mc-server

Run a Paper (Minecraft Java Edition) server on Android with Termux. Uses up to 2 GB of Java heap. No root, and the software is free.

## Requirements
- 64-bit Android device, ideally 4 GB RAM or more (6 GB+ is more comfortable)
- Termux from F-Droid or the official Termux GitHub releases
- A few GB of free storage, plus internet
- You must accept the Minecraft EULA: https://aka.ms/MinecraftEULA

## Install

    pkg update && pkg install -y git
    git clone https://github.com/Pheak-Dev/termux-mc-server
    cd termux-mc-server
    bash setup.sh

## Run
    tmux new -s mc
    ~/mcserver/start.sh

- Leave it running: press Ctrl+B, then D
- Return to it: `tmux attach -t mc`
- Show the panel link again: type `link`
- Quit: type `stop`, then press Ctrl+C

## Web panel
Starting the server prints a private link like `http://127.0.0.1:8080/#TOKEN`. Open it in a browser on the same phone. It has start/stop, the console, plugin upload/enable/disable/delete, and a `server.properties` editor.

- Anyone with the link can control your server, including installing plugins that run code. Don't share it or post screenshots of it.
- To make a new token: `rm ~/mcserver/.panel_token`, then restart the panel.
- To open it from another device on a trusted home Wi-Fi: `PANEL_LAN=1 ~/mcserver/start.sh`. It uses unencrypted HTTP. Never port-forward port 8080.
- Paper runs plugins, not Fabric or Forge mods.
- Optional auto-copy: install the Termux:API app (same source as Termux) and run `pkg install termux-api`.

## Connect
- Same phone: `127.0.0.1:25565`
- Same Wi-Fi: `PHONE_IP:25565` (find the IP in Android Wi-Fi settings)
- Over the internet: needs port forwarding or a tunnel service. This script doesn't set that up.

Players need Java Edition on the same version as the server. Bedrock and Pocket Edition can't join this setup as is.

## Update
Stop the server, back up `~/mcserver`, then run `bash setup.sh` again.
To pick a version: `MC_VERSION=26.2 bash setup.sh`.
Don't move a world back to an older version.

## Troubleshooting
- **Process killed (signal 9):** Android ran short of memory or limited background processes. Close other apps, or change `-Xmx2G` to `-Xmx1536M` and `-Xms1G` to `-Xms512M` in `panel.py`. Running setup again overwrites `panel.py`.
- **Stops with screen off:** set Termux's battery usage to Unrestricted.
- **Lag or heat:** lower `view-distance` and `max-players` in `server.properties`.

2 GB is the Java heap limit. Total memory use will be higher.
