# Team handoff: integration contracts

## Shared agreements

- **One event envelope:** `event_id`, `session_id`, `type`, `source`, `observed_at`, `received_at`, `payload`.
- **One context manager:** only validated events update it; modules do not directly write medical facts.
- **Provenance preserved:** operator speech is `operator_report`; dispatcher speech is `dispatcher_confirmed`.
- **Calls remain independent:** an emergency UI action / manual control is not held up by an LLM, CV loop or KB retrieval.
- **Simulation-only backend:** phone destination is a server-side allowlist, not an arbitrary phone number.

## Vision teammate

Keep vision output separate from the transcript-to-call event stream. Each detection should include frame timestamp, stable per-person ID if possible, bounding-box coordinate convention, model identifier, class confidence and 33 BlazePose landmarks with visibility if used.

Landmarks are estimated keypoints; they do not reveal actual bones, breathing, pulse, consciousness or emergency cause. Do not output medical categories from CV. For a Quest example, review Meta's `PassthroughCameraAccess` and YOLOv9 reference in `knowledge-base/sources.json`.

## AI / KB teammate

Meta Unity AI Speech to Text owns microphone audio → final transcript. Deliver the code after that boundary:

```text
ExtractTranscriptFacts(finalTranscript, speakerSource) -> ProposedFacts + Unresolved
ApplyEvent(existingContext, validatedEvent) -> newContext
ComposeDispatcherSummary(context, events) -> structuredSummary
```

All functions must handle `null`/unknown state. Preserve the exact Meta STT transcript, provider ID, confidence when supplied, speaker and timestamp. A small LLM can propose structured extraction; validation must reject unsupported fields. The source comes from the capture boundary, not the LLM. Never return unrestricted clinical prose.

## Backend teammate

Suggested architecture: API Gateway → Lambda → DynamoDB plus a phone adapter. Support `POST /v1/sessions`, `POST /v1/sessions/{id}/events`, `POST /v1/sessions/{id}/calls/test`, `GET /v1/sessions/{id}`, `GET /v1/sessions/{id}/summary`.

- Confirm test-call provider: Amazon Connect, Twilio or a sandbox simulator.
- Implement server-side destination allowlist and request idempotency.
- Store events with canonical timestamps and session ID.
- Do not treat `call_requested` as `connected`.
- Never infer precise location from caller IP. Store supplied location accuracy/source.
- Maintain auth, encryption, event retention and no provider secrets in Unity.
- Decide whether audio uses a paired phone or a genuine VoIP bridge; initiating an outbound phone call alone is not an audio bridge.

## Unity integration owner

Integrate Meta's `SpeechToTextAgent`, emit only final transcripts, provide an explicit help control, collect authorized location and POST events through an HTTP adapter. A simplified Unity C# coroutine for *authorized staging endpoints*:

```csharp
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

public sealed class XrAedHttpClient : MonoBehaviour
{
    public IEnumerator PostJson(string url, string json, string bearerToken)
    {
        using var request = UnityWebRequest.Post(url, json, "application/json");
        request.timeout = 8;
        request.SetRequestHeader("Authorization", "Bearer " + bearerToken);
        yield return request.SendWebRequest();

        if (request.result != UnityWebRequest.Result.Success)
        {
            Debug.LogWarning("API request failed: " + request.responseCode);
            // Keep the call UI usable; queue/retry only under approved policy.
            yield break;
        }
        Debug.Log("API request accepted; inspect response for actual status.");
    }
}
```

This is a **code outline**, not a built app or a secure token-provisioning implementation. Replace `url` with your team's authenticated staging endpoint; no hardcoded keys or unrestricted phone destinations.

## Mandatory mini-demo

1. Press the explicit help control; verify `incident.help_requested=true` without waiting for speech.
2. Submit authorized phone/device coordinates, including accuracy, or leave location unknown.
3. Feed a final Meta STT transcript into the backend; retain its raw text and validate proposed facts.
4. Retrieve a summary that starts with help status and location.
5. Request only the allowlisted test call; Twilio reads deterministic `spoken_text`.
6. Disable fact extraction and verify help, location and the test-call path remain usable.
