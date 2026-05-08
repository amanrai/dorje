import readline from "node:readline";
import { getModel } from "@mariozechner/pi-ai";
import {
  AuthStorage,
  createAgentSession,
  ModelRegistry,
  SessionManager,
} from "@mariozechner/pi-coding-agent";

const MAX_PROMPT_CHARS = 200_000;
const MAX_CONTEXT_CHARS = 1_000_000;

let sessionState = null;

function writeJson(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function fail(message) {
  return { ok: false, error: String(message) };
}

function assertString(value, name) {
  if (typeof value !== "string") {
    throw new Error(`${name} must be a string`);
  }
}

function optionalString(value, name) {
  if (value === null || value === undefined) {
    return null;
  }
  assertString(value, name);
  return value;
}

function boundedString(value, name, maxChars) {
  assertString(value, name);
  if (value.length > maxChars) {
    throw new Error(`${name} is too large`);
  }
  return value;
}

function encodePrompt(request) {
  const prompt = boundedString(request.prompt, "prompt", MAX_PROMPT_CHARS);
  const output = request.output === "json" ? "json" : "text";
  const context = request.context ?? {};
  const contextText = JSON.stringify(context);
  if (contextText.length > MAX_CONTEXT_CHARS) {
    throw new Error("context is too large");
  }
  const system = optionalString(request.system, "system");
  const outputInstruction = output === "json"
    ? "Return only valid JSON. Do not wrap it in Markdown."
    : "Return plain text.";
  const parts = [];
  if (system !== null && system.length > 0) {
    parts.push(`System instruction:\n${system}`);
  }
  parts.push(`Task:\n${prompt}`);
  parts.push(`Context JSON:\n${contextText}`);
  parts.push(outputInstruction);
  return parts.join("\n\n");
}

async function getSession(modelName) {
  if (sessionState !== null && sessionState.modelName === modelName) {
    return sessionState;
  }
  if (sessionState !== null) {
    sessionState.session.dispose();
    sessionState = null;
  }

  const authStorage = AuthStorage.create();
  const modelRegistry = ModelRegistry.create(authStorage);
  let model = undefined;

  if (modelName !== null && modelName !== undefined && modelName !== "") {
    const slash = modelName.indexOf("/");
    if (slash > 0) {
      const provider = modelName.slice(0, slash);
      const id = modelName.slice(slash + 1);
      model = modelRegistry.find(provider, id) ?? getModel(provider, id);
    } else {
      const available = await modelRegistry.getAvailable();
      model = available.find((candidate) => candidate.id === modelName);
    }
    if (model === undefined) {
      throw new Error(`model not found or unavailable: ${modelName}`);
    }
  }

  const options = {
    authStorage,
    modelRegistry,
    sessionManager: SessionManager.inMemory(),
  };
  if (model !== undefined) {
    options.model = model;
  }

  const created = await createAgentSession(options);
  const textParts = [];
  const unsubscribe = created.session.subscribe((event) => {
    if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
      textParts.push(event.assistantMessageEvent.delta);
    }
  });

  sessionState = {
    session: created.session,
    unsubscribe,
    textParts,
    modelName: modelName ?? null,
  };
  return sessionState;
}

async function complete(request) {
  const modelName = optionalString(request.model, "model");
  const state = await getSession(modelName);
  state.textParts.length = 0;
  const prompt = encodePrompt(request);
  await state.session.prompt(prompt, { expandPromptTemplates: false });
  const text = state.textParts.join("");
  const model = state.session.model;
  return {
    ok: true,
    text,
    provider: model?.provider ?? "pi",
    model: model ? `${model.provider}/${model.id}` : modelName,
  };
}

async function health() {
  const state = await getSession(null);
  const model = state.session.model;
  return {
    ok: true,
    message: "ok",
    provider: model?.provider ?? "pi",
    model: model ? `${model.provider}/${model.id}` : null,
  };
}

async function handle(request) {
  if (request === null || typeof request !== "object" || Array.isArray(request)) {
    return fail("request must be an object");
  }
  if (request.op === "health") {
    return await health();
  }
  if (request.op === "complete") {
    return await complete(request);
  }
  return fail("unknown op");
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

process.on("SIGTERM", () => {
  if (sessionState !== null) {
    sessionState.unsubscribe();
    sessionState.session.dispose();
  }
  process.exit(0);
});
