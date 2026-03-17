"""
CellClaw Discord Command Handlers
====================================
Parses Discord messages/slash-style commands and routes them to SSHManager.

All handlers receive a ParsedCommand and return a CommandResult.
The Agent layer calls these handlers and sends results back to Discord.

Supported command surface:
  /server add    --name <id> --host <h> --user <u> [--port <p>] [--key <path>]
  /server list
  /server use    <name>
  /server test   [name]
  /server remove <name>
  /server info   [name]

  /env list
  /env use <name>
  /env scan <name>

  /project set   <path>
  /project ls    [path]
  /project find  [path]

  /job list
  /job log       <job_id>
  /job cancel    <job_id>
  /job status    <job_id>

  /status        (session overview)
"""
