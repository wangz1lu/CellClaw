/**
 * CellClaw SSH Connection Pool
 * 
 * Manages SSH connections and provides remote command execution.
 * Built on OpenClaw's exec infrastructure.
 */

import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";

export interface SSHServer {
  name: string;
  host: string;
  port: number;
  username?: string;
  identityFile?: string;
  password?: string;
}

export interface ConnectionPoolOptions {
  maxConnectionsPerServer: number;
  connectionTimeout: number;
  maxIdleTime: number;
}

interface PooledConnection {
  id: string;
  server: SSHServer;
  lastUsed: number;
  inUse: boolean;
}

const DEFAULT_OPTIONS: ConnectionPoolOptions = {
  maxConnectionsPerServer: 3,
  connectionTimeout: 30000,
  maxIdleTime: 300000, // 5 minutes
};

export class SSHConnectionPool extends EventEmitter {
  private pools = new Map<string, PooledConnection[]>();
  private options: ConnectionPoolOptions;
  private closed = false;

  constructor(options: Partial<ConnectionPoolOptions> = {}) {
    super();
    this.options = { ...DEFAULT_OPTIONS, ...options };
  }

  /**
   * Execute a command on the remote server
   */
  async execute(server: SSHServer, command: string, cwd?: string): Promise<{
    stdout: string;
    stderr: string;
    code: number | null;
    duration: number;
  }> {
    const startTime = Date.now();
    
    const args = this.buildSSHArgs(server, cwd);
    args.push(command);

    const child = spawn("ssh", args, {
      stdio: ["pipe", "pipe", "pipe"],
    });

    return new Promise((resolve) => {
      let stdout = "";
      let stderr = "";

      child.stdout?.on("data", (data: Buffer) => {
        stdout += data.toString();
      });

      child.stderr?.on("data", (data: Buffer) => {
        stderr += data.toString();
      });

      child.on("close", (code) => {
        resolve({
          stdout,
          stderr,
          code,
          duration: Date.now() - startTime,
        });
      });

      child.on("error", (err) => {
        resolve({
          stdout: "",
          stderr: err.message,
          code: -1,
          duration: Date.now() - startTime,
        });
      });
    });
  }

  /**
   * Execute command with pseudo-terminal (for interactive commands)
   */
  async executeWithPty(
    server: SSHServer,
    command: string,
    onData: (data: string) => void,
    cwd?: string
  ): Promise<{ code: number | null }> {
    const args = [
      ...this.buildSSHArgs(server, cwd),
      "-t", // Force pseudo-terminal
      command,
    ];

    const child = spawn("ssh", args, {
      stdio: ["pipe", "pipe", "pipe"],
    });

    return new Promise((resolve) => {
      child.stdout?.on("data", (data: Buffer) => {
        onData(data.toString());
      });

      child.stderr?.on("data", (data: Buffer) => {
        onData(data.toString());
      });

      child.on("close", (code) => {
        resolve({ code });
      });

      child.on("error", () => {
        resolve({ code: -1 });
      });
    });
  }

  /**
   * Copy files using scp
   */
  async copyFile(
    server: SSHServer,
    localPath: string,
    remotePath: string,
    direction: "upload" | "download"
  ): Promise<void> {
    const args = this.buildSSHArgs(server);

    let source: string;
    let dest: string;

    if (direction === "upload") {
      source = localPath;
      dest = `${server.username || "root"}@${server.host}:${remotePath}`;
    } else {
      source = `${server.username || "root"}@${server.host}:${localPath}`;
      dest = remotePath;
    }

    return new Promise((resolve, reject) => {
      const child = spawn("scp", ["-r", ...args, source, dest], {
        stdio: ["pipe", "pipe", "pipe"],
      });

      let stderr = "";

      child.stderr?.on("data", (data: Buffer) => {
        stderr += data.toString();
      });

      child.on("close", (code) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`scp failed: ${stderr}`));
        }
      });

      child.on("error", (err) => {
        reject(err);
      });
    });
  }

  /**
   * Test connection to server
   */
  async ping(server: SSHServer): Promise<boolean> {
    try {
      const result = await this.execute(server, "echo ok");
      return result.code === 0 && result.stdout.trim() === "ok";
    } catch {
      return false;
    }
  }

  /**
   * List remote directory
   */
  async listDirectory(server: SSHServer, remotePath: string): Promise<{
    files: Array<{
      name: string;
      type: "file" | "directory" | "link";
      size: number;
      mtime: Date;
    }>;
  }> {
    const result = await this.execute(
      server,
      `ls -la "${remotePath}" 2>/dev/null | tail -n +2`
    );

    if (result.code !== 0) {
      throw new Error(`Failed to list directory: ${result.stderr}`);
    }

    const files: Array<{
      name: string;
      type: "file" | "directory" | "link";
      size: number;
      mtime: Date;
    }> = [];

    const lines = result.stdout.trim().split("\n").filter(Boolean);

    for (const line of lines) {
      const parts = line.split(/\s+/);
      if (parts.length < 8) continue;

      const typeChar = parts[0][0];
      const size = parseInt(parts[4], 10) || 0;
      const month = parts[5];
      const day = parts[6];
      const timeOrYear = parts[7];
      const name = parts.slice(8).join(" ");

      if (name === "." || name === "..") continue;

      const now = new Date();
      const year = timeOrYear.includes(":") ? now.getFullYear() : parseInt(timeOrYear, 10);
      const monthNum = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
      ].indexOf(month);
      const mtime = new Date(year, monthNum, parseInt(day, 10));

      files.push({
        name,
        type: typeChar === "d" ? "directory" : typeChar === "l" ? "link" : "file",
        size,
        mtime,
      });
    }

    return { files };
  }

  /**
   * Get pool status
   */
  getPoolStatus(server: SSHServer): { total: number; inUse: number } {
    const key = this.getServerKey(server);
    const pool = this.pools.get(key) || [];
    return {
      total: pool.length,
      inUse: pool.filter((c) => c.inUse).length,
    };
  }

  /**
   * Close all connections
   */
  async close(): Promise<void> {
    this.closed = true;
    for (const [, pool] of this.pools) {
      // SSH connections don't persist between commands, so nothing to close
    }
    this.pools.clear();
  }

  private buildSSHArgs(server: SSHServer, cwd?: string): string[] {
    const args: string[] = [];

    // SSH options for security and reliability
    args.push(
      "-o", "StrictHostKeyChecking=no",
      "-o", `ConnectTimeout=${Math.floor(this.options.connectionTimeout / 1000)}`,
      "-o", "BatchMode=yes"
    );

    if (server.port !== 22) {
      args.push("-p", String(server.port));
    }

    if (server.identityFile) {
      args.push("-i", server.identityFile);
    }

    const userHost = server.username
      ? `${server.username}@${server.host}`
      : server.host;

    // Use '--' to prevent userHost from being interpreted as an option
    args.push("--", userHost);

    return args;
  }

  private getServerKey(server: SSHServer): string {
    return `${server.username || "root"}@${server.host}:${server.port}`;
  }
}

// Singleton
let globalPool: SSHConnectionPool | null = null;

export function getSSHConnectionPool(): SSHConnectionPool {
  if (!globalPool) {
    globalPool = new SSHConnectionPool();
  }
  return globalPool;
}

// Helper to resolve SSH config from system
export async function resolveSSHConfig(host: string): Promise<{
  user?: string;
  host: string;
  port: number;
  identityFiles: string[];
}> {
  return new Promise((resolve) => {
    const child = spawn("ssh", ["-G", host], {
      stdio: ["ignore", "pipe", "ignore"],
    });

    let stdout = "";
    child.stdout?.on("data", (data: Buffer) => {
      stdout += data.toString();
    });

    child.on("close", () => {
      // Simple parse of ssh -G output
      const result: { user?: string; host: string; port: number; identityFiles: string[] } = {
        host,
        port: 22,
        identityFiles: [],
      };

      for (const line of stdout.split("\n")) {
        const [key, ...valueParts] = line.trim().split(/\s+/);
        const value = valueParts.join(" ");
        if (!key || !value) continue;

        switch (key) {
          case "hostname":
            result.host = value;
            break;
          case "user":
            result.user = value;
            break;
          case "port":
            result.port = parseInt(value, 10) || 22;
            break;
          case "identityfile":
            if (value !== "none") {
              result.identityFiles.push(value);
            }
            break;
        }
      }

      resolve(result);
    });

    child.on("error", () => {
      resolve({ host, port: 22, identityFiles: [] });
    });
  });
}
