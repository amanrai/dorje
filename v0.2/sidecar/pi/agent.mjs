import { spawn } from "node:child_process";
import readline from "node:readline";
import { Type } from "@mariozechner/pi-ai";
import {
  AuthStorage,
  createAgentSession,
  DefaultResourceLoader,
  getAgentDir,
  ModelRegistry,
  SessionManager,
} from "@mariozechner/pi-coding-agent";

const MAX_TEXT_CHARS = 1_000_000;

const processStartedAtMs = Date.now();
let lastLogAtMs = processStartedAtMs;

function log(message, details = undefined) {
  const nowMs = Date.now();
  const elapsedS = ((nowMs - processStartedAtMs) / 1000).toFixed(3);
  const stepS = ((nowMs - lastLogAtMs) / 1000).toFixed(3);
  lastLogAtMs = nowMs;
  const payload = details === undefined ? "" : ` ${JSON.stringify(details)}`;
  process.stderr.write(`[dorje-pi-agent +${elapsedS}s Δ${stepS}s] ${message}${payload}\n`);
}

function writeJson(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function fail(message) {
  return { ok: false, error: String(message) };
}

function boundedString(value, name) {
  if (typeof value !== "string") {
    throw new Error(`${name} must be a string`);
  }
  if (value.length > MAX_TEXT_CHARS) {
    throw new Error(`${name} is too large`);
  }
  return value;
}

function validateRequest(request) {
  if (request === null || typeof request !== "object" || Array.isArray(request)) {
    throw new Error("request must be an object");
  }
  if (request.op !== "run" && request.op !== "health") {
    throw new Error("unknown op");
  }
}

function buildSystemPrompt(skillsText) {
  return [
    "You are Dorje, an LM-driven information retrieval agent.",
    "You may use available tools when they help satisfy the user request.",
    "Use tool results as source material. Do not invent tool results.",
    "Choose and apply relevant skills from the skill text below; the user does not need to name a skill.",
    "When you have enough information, answer the user directly in Markdown.",
    "",
    "# Available Dorje Skills",
    skillsText || "No skills loaded.",
  ].join("\n");
}

function createDorjeTool(toolSpec, cwd) {
  return {
    name: toolSpec.name,
    label: toolSpec.name,
    description: toolSpec.description || `Dorje tool: ${toolSpec.name}`,
    parameters: Type.Object({
      args_json: Type.String({
        description: "A JSON object string containing the arguments for this tool.",
      }),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, _ctx) => {
      const argsJson = boundedString(params.args_json, "args_json");
      const stdout = await runCommand("uv", ["run", "dorje", "tools", "call", toolSpec.name, argsJson], cwd);
      return {
        content: [{ type: "text", text: stdout }],
        details: { tool: toolSpec.name },
      };
    },
  };
}

function runCommand(command, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
      if (stdout.length > MAX_TEXT_CHARS) {
        child.kill();
        reject(new Error("tool stdout is too large"));
      }
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve(stdout.trimEnd());
        return;
      }
      reject(new Error(`tool command failed (${code}): ${stderr}`));
    });
  });
}

async function runAgent(request) {
  log("run.start");
  const query = boundedString(request.query, "query");
  const cwd = boundedString(request.cwd || process.cwd(), "cwd");
  const skillsText = boundedString(request.skills_text || "", "skills_text");
  const tools = Array.isArray(request.tools) ? request.tools : [];
  log("run.input", { cwd, query_chars: query.length, skills_chars: skillsText.length, tools: tools.length });

  const agentDir = getAgentDir();
  log("resource_loader.create", { agentDir });
  const resourceLoader = new DefaultResourceLoader({
    cwd,
    agentDir,
    systemPromptOverride: () => buildSystemPrompt(skillsText),
    extensionFactories: [
      (pi) => {
        for (const toolSpec of tools) {
          if (toolSpec && typeof toolSpec.name === "string") {
            pi.registerTool(createDorjeTool(toolSpec, cwd));
          }
        }
      },
    ],
  });
  await resourceLoader.reload();
  log("resource_loader.loaded");

  const authStorage = AuthStorage.create();
  const modelRegistry = ModelRegistry.create(authStorage);
  const toolNames = tools.map((toolSpec) => toolSpec.name).filter((name) => typeof name === "string");
  log("session.create", { toolNames });
  const options = {
    cwd,
    agentDir,
    resourceLoader,
    authStorage,
    modelRegistry,
    sessionManager: SessionManager.inMemory(cwd),
    tools: toolNames,
  };

  const created = await createAgentSession(options);
  log("session.created", { model: created.session.model ? `${created.session.model.provider}/${created.session.model.id}` : null });
  const textParts = [];
  const toolEvents = [];
  const unsubscribe = created.session.subscribe((event) => {
    if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
      textParts.push(event.assistantMessageEvent.delta);
    }
    if (event.type === "tool_execution_start") {
      log("tool.start", { tool: event.toolName });
      toolEvents.push({ type: "start", tool: event.toolName });
    }
    if (event.type === "tool_execution_end") {
      log("tool.end", { tool: event.toolName, is_error: event.isError });
      toolEvents.push({ type: "end", tool: event.toolName, is_error: event.isError });
    }
  });

  try {
    log("prompt.start");
    await created.session.prompt(query, { expandPromptTemplates: false });
    log("prompt.end", { output_chars: textParts.join("").length });
    const model = created.session.model;
    return {
      ok: true,
      content: textParts.join(""),
      provider: model?.provider ?? "pi",
      model: model ? `${model.provider}/${model.id}` : null,
      tool_events: toolEvents,
    };
  } finally {
    unsubscribe();
    created.session.dispose();
  }
}

async function handle(request) {
  validateRequest(request);
  if (request.op === "health") {
    return { ok: true, message: "ok", runtime: "pi" };
  }
  return await runAgent(request);
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on("line", async (line) => {
  try {
    const request = JSON.parse(line);
    const response = await handle(request);
    writeJson(response);
  } catch (error) {
    writeJson(fail(error instanceof Error ? error.message : String(error)));
  }
});
