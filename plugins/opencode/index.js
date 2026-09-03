/**
 * The same three shakedown hooks, as an opencode plugin.
 *
 * opencode has no JSON hook manifest: a plugin is a module whose exported
 * function returns hook callbacks. So where the other two plugins are a
 * few manifest lines pointing at `scripts/shakedown_hooks.py`, this file
 * is that pointer written in JavaScript. Every decision stays in the
 * script; this bridge only moves payloads in and messages out.
 *
 * The moments map like this:
 *
 * - `SessionStart` becomes the `event` hook on `session.created`.
 * - `PreToolUse` on Bash becomes `tool.execute.before` on `bash`. A block
 *   is a thrown Error: opencode shows the message to the model and the
 *   command never runs, which is exit 2 by other means.
 * - `PostToolUse` on Write|Edit becomes `tool.execute.after` on `write`
 *   and `edit`. There is no `additionalContext` here; appending to
 *   `output.output` is how a plugin puts words in front of the model, so
 *   the warning lands at the end of the tool result.
 *
 * A `systemMessage` becomes a TUI toast. A headless opencode has no TUI
 * to show one on, so a failed toast is swallowed rather than becoming a
 * crashed hook.
 */

import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import { fileURLToPath } from "node:url"

const SCRIPT = fileURLToPath(new URL("./scripts/shakedown_hooks.py", import.meta.url))
const BLOCK = 2

/**
 * Run one hook of the shared script, harness event on stdin.
 *
 * The script promises to never wedge a session, and this bridge keeps
 * that promise too: no python3, a dead pipe, or a hang all resolve to an
 * allowing verdict instead of an exception the harness has to guess at.
 */
function consult(hook, payload, cwd) {
  return new Promise((resolve) => {
    const allow = { code: 0, out: "", err: "" }
    // A mangled install has no script, and python3 answers a missing
    // file with exit 2 — the block code. Without this check that install
    // would refuse every shell command in the session.
    if (!existsSync(SCRIPT)) {
      resolve(allow)
      return
    }
    let child
    try {
      child = spawn("python3", [SCRIPT, hook], { cwd, timeout: 30_000 })
    } catch {
      resolve(allow)
      return
    }
    let out = ""
    let err = ""
    child.stdout.setEncoding("utf8")
    child.stderr.setEncoding("utf8")
    child.stdout.on("data", (data) => (out += data))
    child.stderr.on("data", (data) => (err += data))
    child.on("error", () => resolve(allow))
    child.on("close", (code) => resolve({ code: code ?? 0, out, err }))
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(payload))
  })
}

/**
 * Split an allowing verdict into its two audiences.
 *
 * On a tool event the script answers in JSON — `systemMessage` for the
 * operator, `additionalContext` for the model. At session start it speaks
 * plainly, so a line that does not parse is already the message.
 */
function spoken(out) {
  const said = out.trim()
  if (!said) return { operator: "", model: "" }
  try {
    const parsed = JSON.parse(said)
    const context = parsed.hookSpecificOutput ? parsed.hookSpecificOutput.additionalContext : ""
    return {
      operator: typeof parsed.systemMessage === "string" ? parsed.systemMessage : "",
      model: typeof context === "string" ? context : "",
    }
  } catch {
    return { operator: said, model: "" }
  }
}

export const ShakedownPlugin = async ({ client, directory }) => {
  const toast = async (message) => {
    try {
      await client.tui.showToast({ body: { message, variant: "warning" } })
    } catch {
      // Headless server: there is no TUI to show it on.
    }
  }

  return {
    event: async ({ event }) => {
      if (event.type !== "session.created") return
      // Subagent sessions carry a parentID. The parent already heard
      // this, and a toast per subagent is how a hook earns being off.
      if (event.properties?.info?.parentID) return
      // The tool arms answer a missing script with silence, on purpose:
      // blocking would refuse every command. This is the one place that
      // silence gets a voice, or a mangled install stays dead forever.
      if (!existsSync(SCRIPT)) {
        await toast(
          "shakedown: the plugin's vendored script is missing, so its hooks " +
            "are off. Reinstall the plugin.",
        )
        return
      }
      const done = await consult("session-start", {}, directory)
      if (done.out.trim()) await toast(done.out.trim())
    },

    "tool.execute.before": async (input, output) => {
      if (input.tool !== "bash") return
      const command = String(output.args?.command ?? "")
      const done = await consult("before-bash", { tool_input: { command } }, directory)
      if (done.code === BLOCK) {
        throw new Error(done.err.trim() || "shakedown: this run cannot measure anything.")
      }
      const { operator } = spoken(done.out)
      if (operator) await toast(operator)
    },

    "tool.execute.after": async (input, output) => {
      if (input.tool !== "write" && input.tool !== "edit") return
      const filePath = String(input.args?.filePath ?? "")
      if (!filePath) return
      const done = await consult("after-write", { tool_input: { file_path: filePath } }, directory)
      const { operator, model } = spoken(done.out)
      if (model) output.output += `\n\n${model}`
      if (operator) await toast(operator)
    },
  }
}
