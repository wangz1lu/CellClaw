# CellClaw 🦀

> Bioinformatics AI Agent Platform — Built on OpenClaw

CellClaw is an AI-powered bioinformatics assistant that combines OpenClaw's agent framework with SSH-based remote server management for bioinformatics workflows.

## Features

- **🤖 OpenClaw Core** — AI agent with tool system, multi-channel support (Discord, Telegram, etc.)
- **🔒 SSH Layer** — Built-in SSH connection management for remote bioinformatics servers
- **🧬 Bioinformatics Ready** — Designed for managing NGS analysis, genome assembly, and more
- **⚡ Remote Execution** — Execute commands on remote servers through natural language

## Quick Start

### Installation

```bash
git clone https://github.com/wangz1lu/CellClaw.git
cd CellClaw
pnpm install
pnpm build
```

### Configuration

1. Copy the example config:
```bash
cp config.example.yaml config.yaml
```

2. Edit `config.yaml` with your settings:
```yaml
channels:
  discord:
    botToken: "your-discord-bot-token"

agents:
  model: "minimax-cn/MiniMax-M2"
  apiKey: "your-api-key"
```

3. Start:
```bash
node dist/openclaw.mjs
```

## SSH Management

CellClaw provides SSH tools for managing remote bioinformatics servers:

### Register a Server

```
Use tool: ssh_register
Parameters:
  - name: "bio-server-1"
  - host: "192.168.1.100"
  - username: "bioinfo"
  - identityKey: "/home/user/.ssh/id_rsa"
```

### Execute Commands

```
Use tool: ssh_exec
Parameters:
  - server: "bio-server-1"
  - command: "ls -la /data/fastq/"
```

### Available SSH Tools

| Tool | Description |
|------|-------------|
| `ssh_register` | Register a server for SSH operations |
| `ssh_exec` | Execute command on remote server |
| `ssh_list_servers` | List all registered servers |
| `ssh_ls` | List remote directory |
| `ssh_ping` | Test server connection |
| `ssh_upload` | Upload file to server |
| `ssh_download` | Download file from server |

## Architecture

```
CellClaw/
├── src/                    # OpenClaw core
│   ├── agents/            # Agent engine
│   ├── channels/          # Discord, Telegram, etc.
│   ├── skills/            # Skill system
│   └── ...
├── extensions/            # Extensions
│   └── cellclaw-ssh/     # 🦀 SSH Layer (our extension)
└── dist/                  # Built files
```

## Development

```bash
# Watch mode
pnpm dev

# Run tests
pnpm test

# Lint
pnpm lint
```

## SSH Extension Structure

```
extensions/cellclaw-ssh/
├── index.ts              # Plugin entry, exports tools
├── openclaw.plugin.json  # Plugin manifest
└── src/
    └── connection-pool.ts # SSH connection management
```

## License

MIT
