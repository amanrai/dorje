import crypto from "node:crypto";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
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
const SIDECAR_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SIDECAR_DIR, "../..");
const HOOK_DIR = path.join(PROJECT_ROOT, "hooks");
const PI_AGENT_PROMPT = path.join(PROJECT_ROOT, "prompts", "pi_agent_system_prompt.txt");

const processStartedAtMs = Date.now();
let lastLogAtMs = processStartedAtMs;

function log(message, details = undefined) {
  const nowMs = Date.now();
  const elapsedS = ((nowMs - processStartedAtMs) / 1000).toFixed(3);
  const stepMs = nowMs - lastLogAtMs;
  lastLogAtMs = nowMs;
  const payload = details === undefined ? "" : ` ${JSON.stringify(details)}`;
  process.stderr.write(`[dorje-pi-agent +${elapsedS}s Δ${stepMs}ms] ${message}${payload}\n`);
}

function writeJson(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function fail(message) {
  return { ok: false, error: String(message) };
}

function preview(value, maxChars = 2000) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text.length <= maxChars) {
    return text;
  }
  return `${text.slice(0, maxChars)}...<truncated ${text.length - maxChars} chars>`;
}

function toolArgLog(toolName, argsJson) {
  if (toolName !== "run_python") {
    return { args_json: preview(argsJson) };
  }
  try {
    const parsed = JSON.parse(argsJson);
    return {
      args_json: preview(argsJson),
      code: typeof parsed.code === "string" ? `\n\n${parsed.code}\n` : null,
      timeout_s: parsed.timeout_s ?? null,
      cwd: parsed.cwd ?? null,
    };
  } catch (_error) {
    return { args_json: preview(argsJson) };
  }
}

function tokenUsage(value) {
  const usage = value?.usage;
  if (!usage) {
    return null;
  }
  return {
    input: usage.input,
    output: usage.output,
    cache_read: usage.cacheRead,
    cache_write: usage.cacheWrite,
    total: usage.totalTokens,
    cost_total: usage.cost?.total,
  };
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
  const template = fs.readFileSync(PI_AGENT_PROMPT, "utf8");
  return template.replace("{{ skills_text }}", skillsText || "No skills loaded.");
}

async function runHook(name, payload = {}) {
  const hookPath = path.join(HOOK_DIR, `${name}.mjs`);
  log("hook.start", { hook: name, payload });
  try {
    const stdout = await runCommand("node", [hookPath], PROJECT_ROOT, {
      DORJE_HOOK_NAME: name,
      DORJE_HOOK_PAYLOAD: JSON.stringify(payload),
    });
    log("hook.end", { hook: name, payload, output: preview(stdout) });
  } catch (error) {
    log("hook.error", { hook: name, payload, error: error instanceof Error ? error.message : String(error) });
    throw error;
  }
}

function createDorjeTool(toolSpec, cwd, logResults) {
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
      log("dorje_tool.invoke", { tool: toolSpec.name, ...toolArgLog(toolSpec.name, argsJson) });
      const stdout = await runCommand("uv", ["run", "dorje", "tools", "call", toolSpec.name, argsJson], cwd);
      if (logResults) {
        log("dorje_tool.result", { tool: toolSpec.name, result_chars: stdout.length, result_preview: preview(stdout) });
      } else {
        log("dorje_tool.result", { tool: toolSpec.name, result_chars: stdout.length });
      }
      return {
        content: [{ type: "text", text: stdout }],
        details: { tool: toolSpec.name },
      };
    },
  };
}

function runCommand(command, args, cwd, extraEnv = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: { ...process.env, ...extraEnv },
      stdio: ["ignore", "pipe", "pipe"],
    });
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
  const runId = `run_${crypto.randomUUID()}`;
  const skillUseId = `skill_${crypto.randomUUID()}`;
  log("run.start", { run_id: runId });
  const query = boundedString(request.query, "query");
  const cwd = boundedString(request.cwd || process.cwd(), "cwd");
  const skillsText = boundedString(request.skills_text || "", "skills_text");
  const tools = Array.isArray(request.tools) ? request.tools : [];
  const skillNames = Array.isArray(request.skill_names) ? request.skill_names : [];
  const logResults = request.context?.log_results === true;
  log("run.input", { run_id: runId, cwd, query_chars: query.length, skills_chars: skillsText.length, tools: tools.length, log_results: logResults });

  const agentDir = getAgentDir();
  log("resource_loader.create", { run_id: runId, agentDir });
  const resourceLoader = new DefaultResourceLoader({
    cwd,
    agentDir,
    systemPromptOverride: () => buildSystemPrompt(skillsText),
    extensionFactories: [
      (pi) => {
        pi.on("tool_call", async (event) => {
          const toolCallId = typeof event.toolCallId === "string" ? event.toolCallId : `tool_${localToolCallIndex}`;
          localToolCallIndex += 1;
          if (currentTurn !== null) {
            currentTurn.tool_calls.push({
              tool_call_id: toolCallId,
              tool: event.toolName,
              input: event.input,
            });
          }
          log("lm.tool_call", { run_id: runId, turn_id: currentTurn?.turn_id ?? null, tool_call_id: toolCallId, tool: event.toolName, input: event.input });
          await runHook("pre_tool_call", { run_id: runId, turn_id: currentTurn?.turn_id ?? null, tool_call_id: toolCallId, tool: event.toolName, input: event.input });
          return undefined;
        });
        pi.on("tool_result", async (event) => {
          if (logResults) {
            log("lm.tool_result", {
              run_id: runId,
              turn_id: currentTurn?.turn_id ?? null,
              tool_call_id: event.toolCallId,
              tool: event.toolName,
              is_error: event.isError,
              content_preview: preview(event.content),
            });
          } else {
            log("lm.tool_result", { run_id: runId, turn_id: currentTurn?.turn_id ?? null, tool_call_id: event.toolCallId, tool: event.toolName, is_error: event.isError });
          }
          await runHook("post_tool_call", { run_id: runId, turn_id: currentTurn?.turn_id ?? null, tool_call_id: event.toolCallId, tool: event.toolName, is_error: event.isError });
          return undefined;
        });
        for (const toolSpec of tools) {
          if (toolSpec && typeof toolSpec.name === "string") {
            pi.registerTool(createDorjeTool(toolSpec, cwd, logResults));
          }
        }
      },
    ],
  });
  await resourceLoader.reload();
  log("resource_loader.loaded", { run_id: runId });

  const authStorage = AuthStorage.create();
  const modelRegistry = ModelRegistry.create(authStorage);
  const toolNames = tools.map((toolSpec) => toolSpec.name).filter((name) => typeof name === "string");
  log("session.create", { run_id: runId, toolNames });
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
  log("session.created", { run_id: runId, model: created.session.model ? `${created.session.model.provider}/${created.session.model.id}` : null });
  const textParts = [];
  const toolEvents = [];
  let currentTurn = null;
  let previousTurnTools = [];
  let localTurnIndex = 0;
  let localToolCallIndex = 0;
  const unsubscribe = created.session.subscribe((event) => {
    if (event.type === "turn_start") {
      const turnIndex = typeof event.turnIndex === "number" ? event.turnIndex : localTurnIndex;
      localTurnIndex += 1;
      const reason = turnIndex === 0 ? "initial_user_query" : "after_tool_result";
      currentTurn = {
        run_id: runId,
        turn_id: `turn_${turnIndex}`,
        turn_index: turnIndex,
        reason,
        active_skills: skillNames,
        available_tools: toolNames,
        previous_tools: previousTurnTools,
        tool_calls: [],
        text_chars: 0,
      };
      log("lm.turn.start", currentTurn);
    }
    if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
      textParts.push(event.assistantMessageEvent.delta);
      if (currentTurn !== null) {
        currentTurn.text_chars += event.assistantMessageEvent.delta.length;
      }
    }
    if (event.type === "turn_end") {
      const usage = tokenUsage(event.message);
      const toolNamesThisTurn = currentTurn === null ? [] : currentTurn.tool_calls.map((call) => call.tool);
      const did = toolNamesThisTurn.length > 0 ? "tool_call" : "final_answer";
      log("lm.turn.end", {
        run_id: runId,
        turn_id: currentTurn?.turn_id ?? null,
        turn_index: currentTurn?.turn_index ?? event.turnIndex,
        reason: currentTurn?.reason ?? "unknown",
        did,
        tools: toolNamesThisTurn,
        text_chars: currentTurn?.text_chars ?? 0,
        stop_reason: event.message?.stopReason,
        tokens: usage,
      });
      previousTurnTools = toolNamesThisTurn;
      currentTurn = null;
    }
    if (event.type === "message_end" && event.message?.role === "assistant") {
      log("lm.message.end", { run_id: runId, turn_id: currentTurn?.turn_id ?? null, role: event.message.role, stop_reason: event.message.stopReason, tokens: tokenUsage(event.message) });
    }
    if (event.type === "tool_execution_start") {
      log("tool.start", { run_id: runId, turn_id: currentTurn?.turn_id ?? null, tool_call_id: event.toolCallId, tool: event.toolName, args: event.args });
      toolEvents.push({ type: "start", tool: event.toolName, args: event.args });
    }
    if (event.type === "tool_execution_end") {
      if (logResults) {
        log("tool.end", {
          run_id: runId,
          turn_id: currentTurn?.turn_id ?? null,
          tool_call_id: event.toolCallId,
          tool: event.toolName,
          is_error: event.isError,
          result_preview: preview(event.result),
        });
      } else {
        log("tool.end", { run_id: runId, turn_id: currentTurn?.turn_id ?? null, tool_call_id: event.toolCallId, tool: event.toolName, is_error: event.isError });
      }
      toolEvents.push({ type: "end", tool: event.toolName, is_error: event.isError });
    }
  });

  try {
    await runHook("pre_skill_use", { run_id: runId, skill_use_id: skillUseId, query, skills_chars: skillsText.length, skills: skillNames });
    log("prompt.start", { run_id: runId, skill_use_id: skillUseId });
    await created.session.prompt(query, { expandPromptTemplates: false });
    log("prompt.end", { run_id: runId, skill_use_id: skillUseId, output_chars: textParts.join("").length });
    await runHook("post_skill_use", { run_id: runId, skill_use_id: skillUseId, output_chars: textParts.join("").length, skills: skillNames });
    const stats = created.session.getSessionStats();
    log("session.stats", { run_id: runId, tokens: stats.tokens, cost: stats.cost, context_usage: stats.contextUsage });
    const model = created.session.model;
    return {
      ok: true,
      run_id: runId,
      skill_use_id: skillUseId,
      content: textParts.join(""),
      provider: model?.provider ?? "pi",
      model: model ? `${model.provider}/${model.id}` : null,
      tool_events: toolEvents,
      tokens: stats.tokens,
      cost: stats.cost,
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
