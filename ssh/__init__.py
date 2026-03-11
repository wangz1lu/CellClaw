"""
OmicsClaw SSH Layer
===================
Provides secure multi-user, multi-server SSH management for remote
bioinformatics execution on Linux workstations / HPC clusters.

Modules:
  models.py       - Data models (ServerConfig, UserSession, RemoteJob)
  vault.py        - Credential encryption/storage
  registry.py     - Server registration per Discord user
  connection.py   - Async SSH connection pool (asyncssh)
  executor.py     - Command execution (short + tmux background jobs)
  detector.py     - conda/mamba environment & framework detection
  transfer.py     - File download/upload/read
  manager.py      - High-level facade used by the Agent
"""
