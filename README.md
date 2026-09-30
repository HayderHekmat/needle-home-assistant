# Needle 3 for Home Assistant

<img src="custom_components/needle/brand/icon.png" alt="Needle 3 house-and-needle icon" width="96" height="96">

A Home Assistant integration that uses [Cactus Compute Needle 3](https://github.com/cactus-compute/needle) to interpret home-control commands locally. Needle chooses the tools to call, and Home Assistant runs them through its built-in Assist API. It can only control entities you have exposed to Assist.

Install it through HACS as an Integration. This project does not include a Home Assistant add-on.

## What you need

- Home Assistant 2026.9.0 or newer.
- A host supported by `cactus-needle` 3.0.6. The SDK supports Linux x86-64 and ARM64, including musl builds used by Home Assistant containers, and Windows/macOS for development.
- Internet access for the first model and engine download. Later requests run locally using the cached files. You do not need a Cactus API key.
- HACS to install from GitHub, or access to your Home Assistant configuration directory for manual installation.

## Install through HACS

Install this project as a HACS custom repository using [HayderHekmat/needle-home-assistant](https://github.com/HayderHekmat/needle-home-assistant). It is not listed in the default HACS catalog.

1. Open HACS in Home Assistant.
2. Open the three-dot menu in the top-right corner and select Custom repositories.
3. Enter `https://github.com/HayderHekmat/needle-home-assistant`, choose Integration, and select Add.
4. Find Needle 3 Conversation in HACS and download it.
5. Restart Home Assistant, then continue with the setup steps below.

These steps follow the [HACS custom repository instructions](https://www.hacs.xyz/docs/faq/custom_repositories/).

### Manual installation

Place the project's `custom_components/needle` directory at `/config/custom_components/needle` on your Home Assistant host. Restart Home Assistant, then follow the same setup steps as a HACS installation.

## Set up Needle in Home Assistant

1. Go to Settings > Devices & services > Add integration.
2. Search for Needle 3 Conversation and select it.
3. Choose the minimum confidence. The default is 0.8; commands below this threshold will not run.
4. Finish setup and wait for the official model and native engine to download and load.

### Allow Assist to control your entities

1. Go to Settings > Voice assistants and open the Expose tab.
2. Select the entities you want to control and expose them to Assist.

Start with the lights you plan to test. An entity that is not exposed to Assist is unavailable to Needle. See Home Assistant's [entity exposure guide](https://www.home-assistant.io/voice_control/voice_remote_expose_devices/) for the individual and bulk exposure settings.

### Choose Needle as the conversation agent

1. Under Settings > Voice assistants, edit the assistant you want to use or add an assistant.
2. Choose Needle 3 in the Conversation agent field and save the assistant.
3. Use that assistant when sending commands through Assist.

Needle handles the text of your command. For spoken commands, your assistant still needs speech-to-text and text-to-speech services. You can keep your existing choices. Home Assistant's [voice assistant setup guide](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/) explains these parts of the pipeline.

## Use Needle through Assist

Send a complete command that names the device or area you want to control. Try these with matching entities in your home:

- "turn on the kitchen light"
- "set the living room light brightness to 50 percent"
- "turn on the kitchen light and turn off the bedroom light"

Results depend on Needle's predictions and the entities and intents available in your installation. When a tool provides Home Assistant speech, Needle returns that response. Tools that query the current home context return their structured data as text.

Each request starts with fresh model context. Name the target again in your next command: follow-ups such as "turn it off" are not supported.

### Change the confidence threshold

Open the Needle integration's options under Settings > Devices & services to change the minimum confidence. The default is 0.8. A higher threshold rejects more uncertain predictions; a lower threshold accepts more of them.

If Needle asks you to rephrase, try a shorter command with an explicit device or area name. Low or missing confidence, warnings about negation or ungrounded arguments, unknown tools, and invalid arguments all cause rejection before any action runs.

### Limits to expect

- Needle handles home-control tool calls. It does not provide general chat or generate automations.
- This version uses the official model and does not support custom tuned weights.
- The integration passes your input language to Assist, but Needle's accuracy across languages is not guaranteed.
- A request can contain up to eight tool calls. They run in order and stop at the first reported tool error.

Commands are not a transaction. If one action succeeds and a later action fails, the earlier action remains applied.

## Troubleshoot rejected or delayed commands

If a command works with the built-in Home Assistant agent but not Needle, test Needle directly in Developer tools > Actions. Use YAML mode:

```yaml
action: conversation.process
data:
  agent_id: conversation.needle_3
  language: en
  text: "Turn off Main Light"
```

Use your actual conversation entity ID and an exposed device name. This command controls the device; it is not a dry run. Testing directly bypasses the assistant's "Prefer handling commands locally" setting.

"Some commands could not be verified" means the SDK withheld one or more calls. The integration will not execute them, even if you lower its confidence threshold. This response alone does not identify why the SDK withheld the call.

With local handling enabled, Home Assistant can acknowledge a delayed command before Needle processes the action when the timer expires. That later response is not shown in the original pipeline trace. Since v0.1.3, rejections and tool failures are also logged so these background failures are visible.

To capture details, open Settings > Devices & services, find Needle 3 Conversation, and choose Enable debug logging from its menu. Repeat the direct test, then disable debug logging and download the log. Look for `Needle prediction` and `Needle rejected command`.

Debug logs contain commands, tool arguments, and exposed home context, including device names. Review them for private information before sharing. The Hugging Face unauthenticated-request warning concerns download rate limits; it does not explain a rejected command.

## Downloads and local processing

During the first setup, the SDK downloads the official model and native runtime from the upstream distribution. It stores the files in its cache under the Home Assistant process's home directory. Later inference uses those cached files locally.

Model loading and inference run in an executor, outside Home Assistant's event loop. Native calls run one at a time because Needle shares its runtime state across the process. The integration disables Needle telemetry by setting `NEEDLE_TELEMETRY=0` for the Home Assistant process.

## Publish a HACS repository

These steps are for the project maintainer. Users installing an already published repository can skip this section.

1. Run `python scripts/configure_repository.py YOUR_OWNER/YOUR_REPOSITORY` to set the manifest URLs and code owner.
2. Push this project to that public GitHub repository.
3. Publish a release matching the version in the integration manifest, or let HACS use the default branch.
4. Use the repository URL in the HACS installation steps above.

Publishing the repository makes it available for installation as a custom repository. It does not add it to the default HACS catalog.

## Integration icon

The integration includes a house-and-needle icon in `custom_components/needle/brand/`, with standard and high-resolution files for light and dark themes. Home Assistant 2026.3 and newer can load these [bundled brand images](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/).

If the HACS repository list shows "icon not available", it may be the [HACS issue with bundled icons](https://github.com/hacs/integration/issues/5223). That list can still use the public icon CDN rather than the integration's local files. Adding another icon to this repository does not fix that HACS behavior.

After downloading an integration update in HACS, restart Home Assistant and reload the page to load the installed branding.

## Setup fails with a shared-library error

If the log mentions `ld-linux-x86-64.so.2` or `strtoll_l` while loading `libneedle.so`, update this integration to v0.1.2 or newer in HACS and restart Home Assistant. Earlier versions pinned a Needle SDK that could choose a glibc library inside Home Assistant's musl-based container. The updated SDK detects musl and retries with the alternate library when loading fails.

You do not need to delete the integration or its settings. On the next setup attempt, the SDK uses its updated engine cache and downloads the required files if they are missing. Setup errors now include the underlying failure message; check Settings > System > Logs if setup still fails.

References: [Needle Python implementation](https://github.com/cactus-compute/needle/blob/main/needle/__init__.py), [Home Assistant LLM API](https://developers.home-assistant.io/docs/core/llm/), [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/).
