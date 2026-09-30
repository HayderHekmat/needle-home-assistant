# Needle 3 for Home Assistant

<img src="custom_components/needle/brand/icon.png" alt="Needle 3 house-and-cactus icon" width="96" height="96">

Needle 3 Conversation is a local Home Assistant conversation agent built on [Cactus Compute Needle 3](https://github.com/cactus-compute/needle). It turns text commands into tool calls and runs them through Home Assistant's Assist API. Install it through HACS as an **Integration**, then select it as your assistant's conversation agent. It is not a Home Assistant add-on.

Direct device control uses entities exposed to Assist. You can also expose existing Home Assistant scripts as callable tools for routines you have already configured.

This integration is experimental. Large tool catalogs can cause incorrect predictions or refusals, and inference can be slow on some hosts. Test with a small set of devices before using it for everyday control.

## What is Needle 3?

Needle 3 is a compact model designed for tool calling, structured extraction, and text embeddings. Rather than writing a chat reply, it selects functions and fills their arguments from a request. Cactus describes model variants with weights of 8-29 MB; that is the model file size, not the RAM this Home Assistant integration needs. See the [Needle project](https://github.com/cactus-compute/needle) for its architecture and deployment options.

The Home Assistant integration uses the official model for tool calling. Its current workflow is:

```text
Your command -> Needle prediction -> validation -> Assist tools -> tool response
```

Home Assistant supplies the available tools and runs the actions. When a tool provides speech, the integration returns that response. Tools that query home context return structured data as text.

## Why use Needle with Home Assistant?

- Inference runs on your Home Assistant host after the initial download. You do not need a Cactus API key.
- You can try model-based command interpretation without connecting the conversation agent to a hosted LLM service.
- One request can produce several tool calls, such as turning one light on and another off.
- Existing scripts can package a routine behind one named tool, with Home Assistant responsible for its conditions, delays, and actions.

Home Assistant's built-in conversation agent already runs locally and handles standard commands. Needle's purpose here is to add model-based tool selection, not to promise faster or more accurate control. The integration checks confidence, tool names, and argument schemas before executing Needle's predictions, but those checks do not make every prediction correct.

Needle's local inference does not make your entire voice pipeline local. Speech-to-text, text-to-speech, and device integrations still depend on the services you choose.

## What can this integration do?

| Task | Current behavior |
| --- | --- |
| Control exposed devices | Uses the tools available through Home Assistant Assist. |
| Process several commands in one request | Accepts up to eight validated Needle tool calls and executes them in order. |
| Start an existing routine | Can select an exposed script tool; model accuracy varies. |
| Run a delayed command | Uses Home Assistant's built-in delayed-command handling. See the settings below. |
| Use Needle inside an existing automation | Can receive text through the `conversation.process` action. |
| Create or edit an automation from a prompt | Not implemented. |
| Read a tool result and plan the next action | Not implemented. The integration makes one model prediction per request. |
| General chat or pronoun follow-ups | Not supported. Name the target in each request. |

## What you need

- Home Assistant 2026.9.0 or newer.
- A host supported by `cactus-needle` 3.0.6: Linux x86-64 or ARM64, including musl builds used by Home Assistant containers. Windows and macOS are also supported by the SDK for development.
- Internet access for the first model and engine download. Later inference uses cached files locally.
- HACS, or access to your Home Assistant configuration directory for manual installation.

The integration disables Needle telemetry. Your other Home Assistant services keep their own network and privacy settings.

## Install through HACS

Add [HayderHekmat/needle-home-assistant](https://github.com/HayderHekmat/needle-home-assistant) as a HACS custom repository. It is not listed in the default HACS catalog.

1. Open HACS in Home Assistant.
2. Open the three-dot menu and select **Custom repositories**.
3. Enter `https://github.com/HayderHekmat/needle-home-assistant` and choose **Integration**.
4. Select **Add**, find **Needle 3 Conversation**, and download it.
5. Restart Home Assistant.

See the [HACS custom repository instructions](https://www.hacs.xyz/docs/faq/custom_repositories/) for the installation menu.

### Manual installation

Place the project's `custom_components/needle` directory at `/config/custom_components/needle` on your Home Assistant host, then restart Home Assistant. Continue with the same setup steps below.

## Set up your assistant

1. Go to **Settings > Devices & services > Add integration**.
2. Search for **Needle 3 Conversation** and select it.
3. Leave the minimum confidence at **0.8** for your first tests.
4. Finish setup and allow the official model and native engine to download and load.
5. Go to **Settings > Voice assistants > Expose** and expose the devices you want Assist to control. Start with one light or switch.
6. Edit or add an assistant under **Settings > Voice assistants**, choose **Needle 3** as its conversation agent, and save.

Use recognizable device names and aliases. An entity not exposed to Assist is unavailable for direct control. Home Assistant's [entity exposure guide](https://www.home-assistant.io/voice_control/voice_remote_expose_devices/) covers individual and bulk settings.

For voice input, keep or configure your speech-to-text and text-to-speech services. Needle handles the command text, not audio. See Home Assistant's [voice assistant setup guide](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/).

### Prefer Home Assistant sentences

Open Needle's options under **Settings > Devices & services** and enable **Prefer Home Assistant sentences** to try the built-in sentence recognizer first. It handles matching standard commands; Needle receives requests it does not recognize. This option is off by default.

This can avoid model misrouting and inference delays for familiar commands. It also applies when a timer sends its delayed action directly to the conversation agent. A command handled this way is executed by Home Assistant's built-in agent, not by the Needle model.

The assistant's separate **Prefer handling commands locally** setting applies to the initial Assist pipeline request. Enable both settings when testing delayed commands.

## Send your first commands

Open Assist and select the assistant configured with Needle. Start with text input so you can test device control separately from speech services.

Use names that exist in your home:

- "turn on the kitchen light"
- "set the living room light brightness to 50 percent"
- "turn on the kitchen light and turn off the bedroom light"

Check the actual device state after each command. A response alone is not proof that every intended action happened.

Each Needle request starts with fresh model context. Say "turn off the kitchen light" in the next request rather than "turn it off".

### Multiple commands in one request

Needle can predict a batch of independent actions. The integration validates the entire predicted batch before starting, accepts a maximum of eight calls, and runs them in model order. It stops at the first reported tool error.

A batch is not a transaction. If the first action succeeds and the second fails, the first remains applied. For a routine with dependencies, conditions, or delays, use an existing Home Assistant script instead of relying on a model to coordinate it.

### Delayed commands

With both local sentence settings enabled, try:

```text
Turn off Main Light in 20 seconds
```

Replace "Main Light" with an exposed name from your home. Home Assistant schedules the delay, then sends the remaining command to the selected agent when the timer expires. Needle's **Prefer Home Assistant sentences** option lets that action use the built-in recognizer without waiting for model inference.

The initial "Command will be executed" response confirms scheduling, not successful device control. Check the device after the delay. See Home Assistant's [supported delayed commands](https://www.home-assistant.io/voice_control/builtin_sentences/) for examples.

## Use scripts for routines and automation

You can give Needle access to routines you have already written. Home Assistant exposes scripts as tools, so a script can contain several actions, conditions, and delays while the conversation agent only needs to select its name.

1. Create a script under **Settings > Automations & scenes > Scripts**.
2. Give it a clear name, such as "Evening lights".
3. Add a description of what it does, for example: "Turn off the kitchen light and set the living room light brightness to 30 percent."
4. Open the script's settings and expose it to **Assist** under **Voice assistants**.
5. Test the script manually, then try "Start Evening lights" through your assistant.

Add descriptions to any script input fields too. Check the Assist tool-call trace to confirm that the intended script ran. Exposing a script grants access to its configured actions, so review the whole sequence before making it available. Follow Home Assistant's [guide to exposing scripts to conversation agents](https://www.home-assistant.io/voice_control/exposing_scripts_to_llms/).

For recurring schedules or event-triggered rules, create an automation in Home Assistant. Needle does not create, save, or edit those rules. You can call the conversation agent from an existing automation using the same `conversation.process` action shown below, but direct Home Assistant actions are more predictable for a fixed routine: model requests can be rejected or delayed.

### Is Needle an agentic automation agent?

The Needle SDK supports a tool-result loop: select a tool, execute it, feed the result back, and select another action. Its [`run()` and `complete()` APIs](https://cactuscompute.com/blog/needle-python-docs) provide that capability.

This integration currently uses `complete()` once per request. It executes the resulting calls, but does not feed their results into another model turn. Multiple calls are a batch, not a continuing plan. Requests that require checking a state and then deciding what to do should be expressed as a Home Assistant script with explicit conditions.

A fuller agentic implementation would need a bounded tool-result loop and clear handling of dependent actions. Creating automations from prompts would also need a separate workflow to preview, validate, and approve the proposed rule before saving it. These are possible extensions, not features available in this release.

## Test the conversation agent directly

Open **Developer tools > Actions**, switch to YAML, and run:

```yaml
action: conversation.process
data:
  agent_id: conversation.needle_3
  language: en
  text: "Turn off Main Light"
```

Use your actual conversation entity ID and exposed device name. This performs an action; it is not a dry run. The same action can be a step in an existing Home Assistant automation.

This bypasses the pipeline's local handling setting. To test the Needle model itself, also disable **Prefer Home Assistant sentences** in Needle's options. Inspect the returned response and the device state.

## Confidence and limitations

Change the minimum confidence in Needle's options. The default is **0.8**. Raising it rejects more uncertain predictions; lowering it accepts more. The threshold applies to Needle predictions, not commands handled by the built-in sentence recognizer.

Low or missing confidence, suppressed calls, negation or grounding warnings, unknown tools, and invalid arguments cause rejection before Needle actions run. Lowering the integration's threshold does not restore calls the SDK has already suppressed.

- Large Assist tool catalogs can confuse tool selection. Native inference latency and RAM use depend on the host and request context; a small model file does not guarantee a fast or low-memory integration.
- Needle handles tool calls rather than general conversation and does not replace speech-to-text or text-to-speech.
- The integration passes the input language to Assist, but model accuracy across languages is not guaranteed.
- This release uses official weights and does not support custom tuned models.
- Tool responses may contain structured data rather than a conversational answer.

## Troubleshooting

If a command works with the built-in agent but Needle asks you to rephrase, try the exact exposed device name and test the agent directly. You can enable **Prefer Home Assistant sentences** for standard commands while keeping Needle for unmatched requests. This is a workaround for model routing errors, not a change to model accuracy.

To investigate a refusal, enable **debug logging** from the Needle integration's menu, repeat the failing command, then disable debug logging and download the capture. Look for `Needle prediction` and `Needle rejected command`. Debug logs contain commands, tool arguments, and exposed home details; review private information before sharing them in a [GitHub issue](https://github.com/HayderHekmat/needle-home-assistant/issues).

If setup fails while loading a shared library, install the latest integration release in HACS and restart Home Assistant. The Hugging Face unauthenticated-request warning concerns download rate limits; an API token is not required for normal use.
