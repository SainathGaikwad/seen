"""Scratch narration for the SEEN demo films with an open-source voice (Kokoro 82M v1.0, Apache-2.0) through sherpa-onnx.

    pip install sherpa-onnx scipy numpy
    # model: kokoro-int8-multi-lang-v1_0.tar.bz2 from github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models, unpacked
    KOKORO_DIR=/path/to/kokoro-int8-multi-lang-v1_0 python docs/film/narrate.py paypal|gitlab [speaker_id] [speed] [out_dir]

One WAV per narration block (the blocks are the paragraphs of docs/paypal_demo_script.md / docs/gitlab_demo_script.md,
spelled for a speech engine) plus durations.json; docs/film/film_*.py cut the recording to them. A human narration
works the same way: one WAV per block under the same names.
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import sherpa_onnx
from scipy.io import wavfile

FILM = sys.argv[1] if len(sys.argv) > 1 else "paypal"
SID = int(sys.argv[2]) if len(sys.argv) > 2 else 3          # 3 = af_heart
SPEED = float(sys.argv[3]) if len(sys.argv) > 3 else 0.85
OUT = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(__file__).resolve().parent.parent / f"rec_{FILM}" / "narration"
M = Path(os.environ.get("KOKORO_DIR", "kokoro-int8-multi-lang-v1_0"))

SCRIPTS = {
    "paypal": {
    "hook": "Seen finds the women cricketers whose performance most exceeds the attention they get, and publishes claim-checked stories about them in English, Hindi and Urdu. This is the money side of that newsroom: the Sponsor Desk.",
    "problem": "Federations, small newsrooms and creators in women's sport have stories, and no money loop. Sponsors want measurable, safe content. Athletes outside the big markets get neither. So we built an agent that sells verified stories, and PayPal moves the money.",
    "desk": "A sponsor types a brief: Caribbean fans, Hayley Matthews, English and Urdu, one week. The desk agent, Nemotron on Nebius, reads the catalogue, and prices a package inside policy: one to four athletes, verified languages only, the budget as a hard cap, and a price that rises with the athlete's visibility gap. Then it raises a PayPal checkout order with PayPal's Agent Toolkit. Every tool call is on screen. The agent cannot capture, pay, or move money; the sponsor does that in PayPal.",
    "payment": "The sponsor approves in PayPal checkout. On return, Seen captures the order, tags the athlete's stories \"presented by\", and sends one Payouts batch: sixty per cent to the athlete fund, thirty to the creator who made the content, ten to Seen. Sandbox money, real API calls.",
    "tip": "Fans do the same for two dollars: tip her story, PayPal, split seventy, twenty, ten, paid out.",
    "ledger": "The money ledger is an A-G Grid: every order, invoice and payout; column filters; totals that follow the filter; status badges; C S V export. And per athlete: what her story raised, and where it went.",
    "close": "Orders, Invoicing and Payouts. PayPal's Agent Toolkit for the agent's tools. Nemotron for the planning. A deterministic claim checker for every number in every story. The under-seen athlete becomes the thing worth paying for, and the money reaches her. Seen: women's cricket, correctly, paid.",
},
    "gitlab": {
    "hook": "This is Seen. It finds the eleven women cricketers whose performance most exceeds the attention they get, and writes their stories in three languages from sourced facts. A model drafts in seconds. Everything after the draft is the product, because one plausible wrong number costs a newsroom its trust.",
    "problem": "Our audience: small newsrooms, creators and federations publishing athlete statistics weekly, with no fact-checking desk. Their failure mode is not bad prose; it is a number no fact supports. So that discipline now runs on GitLab: a deterministic claim gate checks every number in every draft against the athlete's fact bundle; in the pipeline on every merge, and through a Duo agent on every merge request.",
    "blocked": "This merge request adds one sentence to Hayley Matthews' video script: she scored two hundred runs in the final. False: her tournament total is one hundred and forty-five. The pipeline runs the claim gate and goes red. The Editor-in-chief flow starts on its own: it reads the merge request, runs the gate on the branch, posts the full table; sixteen formats, three languages, one blocked: two hundred is not in any fact; and labels the request editor blocked. The planner agent files a work item with the blocked row and the two allowed fixes. The agent cannot approve or merge. The human editor sees a red pipeline, a red label, and a linked issue.",
    "verified": "The author swaps the number for a sourced fact, ten wickets, fact F four, and pushes. The editor runs again: sixteen of sixteen verified, the label flips to editor verified, the pipeline is green. Now, and only now, a person clicks merge. Main runs the rest of the lifecycle: tests, the claim gate, six governance policies, a container image, GitLab's security scans, a tagged release, and a deploy that pushes the verified commit to the hosting repository and checks the live app. Every six hours a scheduled monitor visits the demo, wakes it if it sleeps, and opens an incident if it is down.",
    "close": "Path B: Seen existed before October; the pipeline, the claim-gate command, the policies, the monitor and the Editor-in-chief flow were built for this hackathon; nine stages touched, plan to govern. Supervised autonomy: the agents run the review on their own, a person approves the outcome, and a deterministic checker, not the model, decides what is publishable. Women's cricket does not need more content. It needs to be seen. Correctly.",
},
}

OUT.mkdir(parents=True, exist_ok=True)
cfg = sherpa_onnx.OfflineTtsConfig(
    model=sherpa_onnx.OfflineTtsModelConfig(
        kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
            model=str(M / "model.int8.onnx"), voices=str(M / "voices.bin"), tokens=str(M / "tokens.txt"),
            data_dir=str(M / "espeak-ng-data"), dict_dir=str(M / "dict"),
            lexicon=f"{M / 'lexicon-us-en.txt'},{M / 'lexicon-zh.txt'}"),
        num_threads=4, debug=False, provider="cpu"),
    max_num_sentences=1)
tts = sherpa_onnx.OfflineTts(cfg)
durs = {}
for name, text in SCRIPTS[FILM].items():
    t = time.time()
    a = tts.generate(text, sid=SID, speed=SPEED)
    s = np.array(a.samples, dtype=np.float32)
    idx = np.where(np.abs(s) > 0.01)[0]                       # trim silence, keep 150 ms of air
    if len(idx):
        s = s[max(0, idx[0] - int(0.15 * a.sample_rate)): min(len(s), idx[-1] + int(0.15 * a.sample_rate))]
    wavfile.write(str(OUT / f"{name}.wav"), a.sample_rate, (np.clip(s, -1, 1) * 32767).astype(np.int16))
    durs[name] = round(len(s) / a.sample_rate, 2)
    print(f"{name:9s} {durs[name]:6.2f}s  (generated in {time.time() - t:.0f}s)", flush=True)
json.dump(durs, open(OUT / "durations.json", "w"), indent=1)
print("total", round(sum(durs.values()), 1), "s  ->", OUT)
