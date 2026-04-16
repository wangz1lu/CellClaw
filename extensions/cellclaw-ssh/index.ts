/**
 * CellClaw SSH Plugin for OpenClaw
 * 
 * Registers SSH management tools with the OpenClaw agent system.
 */

import type { Tool } from "../../../src/agents/tools.js";
import { SSHConnectionPool, getSSHConnectionPool, SSHServer } from "./src/connection-pool.js";

// Server registry
const serverRegistry = new Map<string, SSHServer>();

/**
 * Register a server for SSH operations
 */
export function registerServer(config: SSHServer): void {
  serverRegistry.set(config.name, config);
}

/**
 * Get a registered server
 */
export function getServer(name: string): SSHServer | undefined {
  return serverRegistry.get(name);
}

/**
 * List all registered servers
 */
export function listServers(): string[] {
  return Array.from(serverRegistry.keys());
}

// =============================================================================
// OpenClaw Tools - These integrate with OpenClaw's tool system
// =============================================================================

export const cellclawSshTools = {
  /**
   * ssh_register - Register a server for SSH operations
   */
  ssh_register: {
    name: "ssh_register",
    description: "Register a server for SSH operations",
    parameters: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Friendly name for the server",
        },
        host: {
          type: "string",
          description: "Server hostname or IP address",
        },
        port: {
          type: "number",
          description: "SSH port",
          default: 22,
        },
        username: {
          type: "string",
          description: "SSH username",
        },
        identityKey: {
          type: "string",
          description: "Path to SSH private key",
        },
      },
      required: ["name", "host", "username"],
    },
    handler: async (params: {
      name: string;
      host: string;
      port?: number;
      username: string;
      identityKey?: string;
    }) => {
      registerServer({
        name: params.name,
        host: params.host,
        port: params.port || 22,
        username: params.username,
        identityFile: params.identityKey,
      });

      const pool = getSSHConnectionPool();
      const server = getServer(params.name)!;
      const reachable = await pool.ping(server);

      return {
        success: true,
        server: params.name,
        host: params.host,
        reachable,
      };
    },
  } satisfies Tool,

  /**
   * ssh_exec - Execute a command on a remote server
   */
  ssh_exec: {
    name: "ssh_exec",
    description: "Execute a command on a remote server via SSH",
    parameters: {
      type: "object",
      properties: {
        server: {
          type: "string",
          description: "Server name (must be registered first)",
        },
        command: {
          type: "string",
          description: "Command to execute",
        },
        cwd: {
          type: "string",
          description: "Working directory on remote server",
        },
      },
      required: ["server", "command"],
    },
    handler: async (params: { server: string; command: string; cwd?: string }) => {
      const server = getServer(params.server);
      if (!server) {
        return {
          error: `Server '${params.server}' not found. Use ssh_register first.`,
        };
      }

      try {
        const pool = getSSHConnectionPool();
        const result = await pool.execute(server, params.command, params.cwd);

        return {
          stdout: result.stdout,
          stderr: result.stderr,
          exitCode: result.code,
          duration: `${result.duration}ms`,
        };
      } catch (error) {
        return { error: String(error) };
      }
    },
  } satisfies Tool,

  /**
   * ssh_list_servers - List all registered servers
   */
  ssh_list_servers: {
    name: "ssh_list_servers",
    description: "List all registered SSH servers",
    parameters: { type: "object", properties: {} },
    handler: async () => {
      const servers = listServers();
      if (servers.length === 0) {
        return { servers: [], message: "No servers registered" };
      }

      const pool = getSSHConnectionPool();
      const info = servers.map((name) => {
        const server = getServer(name)!;
        return {
          name,
          host: server.host,
          port: server.port,
          username: server.username,
        };
      });

      return { servers: info };
    },
  } satisfies Tool,

  /**
   * ssh_ls - List remote directory
   */
  ssh_ls: {
    name: "ssh_ls",
    description: "List contents of a remote directory",
    parameters: {
      type: "object",
      properties: {
        server: {
          type: "string",
          description: "Server name",
        },
        path: {
          type: "string",
          description: "Remote path to list",
          default: ".",
        },
      },
      required: ["server"],
    },
    handler: async (params: { server: string; path?: string }) => {
      const server = getServer(params.server);
      if (!server) {
        return { error: `Server '${params.server}' not found` };
      }

      try {
        const pool = getSSHConnectionPool();
        const result = await pool.listDirectory(server, params.path || ".");

        return {
          path: params.path || ".",
          files: result.files.map((f) => ({
            name: f.name,
            type: f.type,
            size: f.size,
            mtime: f.mtime.toISOString(),
          })),
        };
      } catch (error) {
        return { error: String(error) };
      }
    },
  } satisfies Tool,

  /**
   * ssh_ping - Test connection to server
   */
  ssh_ping: {
    name: "ssh_ping",
    description: "Test if a server is reachable via SSH",
    parameters: {
      type: "object",
      properties: {
        server: {
          type: "string",
          description: "Server name",
        },
      },
      required: ["server"],
    },
    handler: async (params: { server: string }) => {
      const server = getServer(params.server);
      if (!server) {
        return { error: `Server '${params.server}' not found` };
      }

      const pool = getSSHConnectionPool();
      const reachable = await pool.ping(server);

      return { server: params.server, reachable };
    },
  } satisfies Tool,

  /**
   * ssh_upload - Upload file to remote server
   */
  ssh_upload: {
    name: "ssh_upload",
    description: "Upload a file to remote server via scp",
    parameters: {
      type: "object",
      properties: {
        server: {
          type: "string",
          description: "Server name",
        },
        local: {
          type: "string",
          description: "Local file path",
        },
        remote: {
          type: "string",
          description: "Remote destination path",
        },
      },
      required: ["server", "local", "remote"],
    },
    handler: async (params: { server: string; local: string; remote: string }) => {
      const server = getServer(params.server);
      if (!server) {
        return { error: `Server '${params.server}' not found` };
      }

      try {
        const pool = getSSHConnectionPool();
        await pool.copyFile(server, params.local, params.remote, "upload");
        return { success: true, local: params.local, remote: params.remote };
      } catch (error) {
        return { error: String(error) };
      }
    },
  } satisfies Tool,

  /**
   * ssh_download - Download file from remote server
   */
  ssh_download: {
    name: "ssh_download",
    description: "Download a file from remote server via scp",
    parameters: {
      type: "object",
      properties: {
        server: {
          type: "string",
          description: "Server name",
        },
        remote: {
          type: "string",
          description: "Remote file path",
        },
        local: {
          type: "string",
          description: "Local destination path",
        },
      },
      required: ["server", "remote", "local"],
    },
    handler: async (params: { server: string; remote: string; local: string }) => {
      const server = getServer(params.server);
      if (!server) {
        return { error: `Server '${params.server}' not found` };
      }

      try {
        const pool = getSSHConnectionPool();
        await pool.copyFile(server, params.remote, params.local, "download");
        return { success: true, remote: params.remote, local: params.local };
      } catch (error) {
        return { error: String(error) };
      }
    },
  } satisfies Tool,
};

// Plugin metadata
export const cellclawSshPlugin = {
  id: "cellclaw-ssh",
  name: "CellClaw SSH Layer",
  description: "SSH connection management and remote command execution",
  tools: Object.values(cellclawSshTools),
};
