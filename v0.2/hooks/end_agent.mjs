const payload = JSON.parse(process.env.DORJE_HOOK_PAYLOAD || "{}");

console.log("This is the end_agent hook being fired");
console.log(JSON.stringify({
  run_id: payload.run_id,
  duration_ms: payload.duration_ms,
  turns: payload.turns,
  tokens: payload.tokens,
  cost: payload.cost,
}, null, 2));
