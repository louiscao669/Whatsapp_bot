"""Run the same frozen prompts entirely on the Mac's local Ollama models."""
from __future__ import annotations

import argparse
import json
import time
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

from experiment_hard66_selectors import COMMON, OUTPUT, PROMPTS, SPLITS, prepare, read, report, save, validate

MODELS = {"qwen3_8b_local":"qwen3:8b", "gemma3_4b_local":"gemma3:4b"}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def request(route, payload=None):
    url = "http://127.0.0.1:11434/api/" + route
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=body, headers={"Content-Type":"application/json"})
    with build_opener(ProxyHandler({}), NoRedirects()).open(req, timeout=420) as res:
        return json.load(res)


def run():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models",nargs="+",choices=MODELS,default=list(MODELS))
    args=p.parse_args()
    prepare()
    local={m["name"]:m for m in request("tags")["models"]}
    for label in args.models:
        model=MODELS[label]
        if model not in local or local[model].get("remote_model") or local[model].get("remote_host"):
            raise ValueError(f"Model is not installed locally: {model}")
        for name,prompt in PROMPTS.items():
            for split in SPLITS:
                path=OUTPUT/"responses"/f"{label}__{name}__{split}.json"
                batch=read(OUTPUT/(split+"_blinded.json"))
                if path.exists():
                    validate(read(path),[r["id"] for r in batch]);continue
                scratch=OUTPUT/"local_checkpoints";scratch.mkdir(exist_ok=True)
                saved=[]
                for start in range(0,len(batch),8):
                    block=batch[start:start+8];ids=[r["id"] for r in block]
                    chunk=scratch/(path.stem+f"_{start}.json")
                    if chunk.exists():
                        saved.extend(validate(read(chunk),ids));continue
                    fields={k:{"type":"object","properties":{"score":{"type":"integer","minimum":0,"maximum":1000},
                            "why":{"type":"string"}},"required":["score","why"],"additionalProperties":False} for k in ids}
                    schema={"type":"object","properties":fields,"required":ids,"additionalProperties":False}
                    for attempt in range(3):
                        try:
                            result=request("chat",dict(model=model,stream=False,think=False,format=schema,
                                options=dict(temperature=0,seed=20261107,num_ctx=8192,num_predict=2200),
                                messages=[dict(role="system",content=prompt+"\n\n"+COMMON.split("Return JSON only:")[0]+
                                   "Return a JSON object keyed by the supplied opaque IDs, each with score and why."),
                                          dict(role="user",content=json.dumps(block,ensure_ascii=False))]))
                            obj=json.loads(result["message"]["content"])
                            rows=validate({"items":[dict(id=k,**v) for k,v in obj.items()]},ids)
                            break
                        except Exception:
                            if attempt==2:raise
                            time.sleep(2)
                    saved.extend(rows);save(chunk,{"items":rows})
                validate({"items":saved},[r["id"] for r in batch])
                save(path,dict(items=saved,model=model,model_digest=local[model]["digest"],
                               prompt=name,split=split,batch_size=8,backend="local Ollama",think=False))
                print(label,name,split,"complete",flush=True)
    report()


if __name__=="__main__":run()
