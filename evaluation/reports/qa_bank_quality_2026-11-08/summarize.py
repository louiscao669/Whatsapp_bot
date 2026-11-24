"""Summarize the frozen reader experiment and paired passage-level contrasts."""
from collections import Counter, defaultdict
import json
import random
import statistics
from compare import OUT, GRADER, MARK, OPTIONS, load, save, sig

ORDER = ("Gold72", "Prepared60", "Hard65", "Hard77")


def fraction(n, denom):
    return f"{n}/{denom} ({100*n/denom:.1f}%)"


def summarize(rows, suffix="_grade"):
    n=len(rows)
    c=sum(r["clean"+suffix]=="full" for r in rows)
    o=sum(r["omission"+suffix]=="full" for r in rows)
    slipped=sum(r["clean"+suffix]=="full" and r["omission"+suffix]!="full" for r in rows)
    return dict(n=n,blind=sum(i["prior_blind"] for i in rows),editorial=sum(i["prior_editorial"] for i in rows),
                clean=c,omission=o,drop=(c-o)/n,loss=slipped,recovery=o-(c-slipped),
                clean_partial=sum(r["clean"+suffix]=="partial" for r in rows),
                omission_partial=sum(r["omission"+suffix]=="partial" for r in rows),
                clean_abstain=sum("cannot tell from this passage" in r["clean_reply"].lower() for r in rows))


def table(cols,rows):
    return ["| "+" | ".join(cols)+" |","|"+"|".join("---" for _ in cols)+"|",
            *["| "+" | ".join(str(c).replace("|","\\|").replace("\n"," ") for c in row)+" |" for row in rows]]


def passage_interval(old,new):
    bins=defaultdict(lambda:defaultdict(lambda:[0,0,0]))
    for arm,rows in [("old",old),("new",new)]:
        for r in rows:
            b=bins[r["pid"]][arm]
            b[0]+=1
            b[1]+=int(r["clean_grade"]=="full")
            b[2]+=int(r["omission_grade"]=="full")
    pids=sorted(bins)
    def delta(draw):
        out={}
        for arm in ("old","new"):
            n,c,o=[sum(bins[p][arm][k] for p in draw) for k in range(3)]
            out[arm]=[100*c/n,100*(c-o)/n]
        return [a-b for a,b in zip(out["new"],out["old"])]
    rng=random.Random(20261108)
    trials=[delta(rng.choices(pids,k=len(pids))) for _ in range(10000)]
    original=delta(pids)
    return {metric:dict(estimate=original[j],low=sorted(r[j] for r in trials)[249],
                        high=sorted(r[j] for r in trials)[9749]) for j,metric in enumerate(["clean_pp","omission_drop_pp"])}


def main():
    manifest=load(OUT/"manifest.json")
    arms=manifest["banks"]
    blind_grades=load(OUT/"blinded_grades.json")
    used=set()
    agreement={}
    for group,rows in arms.items():
        for r in rows:
            for cond in ("clean","omission"):
                answer=load(OUT/"answers"/(r[cond]+".json"))["answer"]
                data={"question":r["q"],"key":r["key"],"reply":answer}
                k=sig([GRADER,MARK,OPTIONS,data])
                g=load(OUT/"grades"/(k+".json"))
                assert all(g[f]==v for f,v in data.items())
                r[cond+"_grade"]=g["grade"]
                r[cond+"_reply"]=answer
                r[cond+"_grade_id"]=k
                normalized=answer.strip().rstrip(".").lower()
                if normalized in ("cannot tell from this passage",r["key"].strip().rstrip(".").lower()):
                    editorial=g["grade"]
                else:
                    editorial=blind_grades[k]
                    used.add(k)
                    agreement[k]=editorial==g["grade"]
                r[cond+"_editorial_grade"]=editorial
    assert used==set(blind_grades)
    arms["Previous combined"]=arms["Gold72"]+arms["Hard65"]
    arms["New combined"]=arms["Prepared60"]+arms["Hard77"]
    totals={k:summarize(v) for k,v in arms.items()}
    review_scores={k:summarize(v,"_editorial_grade") for k,v in arms.items()}
    intervals={k:passage_interval(arms[a],arms[b]) for k,a,b in [
        ("combined","Previous combined","New combined"),("prepared","Gold72","Prepared60"),("hard","Hard65","Hard77")]}
    state={"counts":totals,"blind_rescore":review_scores,"rescore_agreement":[sum(agreement.values()),len(agreement)],"passage_intervals":intervals,"items":{g:arms[g] for g in ORDER}}
    by_id = {g:{r["id"]:r for r in rows} for g,rows in arms.items()}
    decomposition = {}
    for label,a,b in [("prepared","Gold72","Prepared60"),("hard","Hard65","Hard77")]:
        old,new=by_id[a],by_id[b]
        shared=old.keys()&new.keys()
        old_only=old.keys()-new.keys()
        new_only=new.keys()-old.keys()
        def correct(bank,ids):
            return sum(bank[k]["clean_grade"]=="full" for k in ids)
        decomposition[label] = dict(shared_count=len(shared),old_shared=correct(old,shared),new_shared=correct(new,shared),
                                    removed_count=len(old_only),removed_full=correct(old,old_only),added_count=len(new_only),added_full=correct(new,new_only))
    state["membership_decomposition"]=decomposition
    save(OUT/"results.json",state)
    lines=["# Quality of the previous and new English QA banks","",
           "The comparison uses the 60 projected prepared questions and the revised 77-item hard bank. The previous bank contains all 72 selected prepared IDs and the English source forms corresponding to the 65 active hard IDs. Both pairings contain 137 questions from ten passages. Historical membership came from the selected Gold72 schedule and the active Hard65 evaluation manifest. The prepared questions use their assigned English Berean Standard Bible text. The hard questions use their archived English generator windows. Comparisons within each family use the same source edition.","",
           "## Independent reader results","",
           "Qwen3 8B answered each exact English question using its assigned verse window. It saw neither the key nor bank identity. It also answered a separate version with one verse removed. Both conditions used the same prompt. Gemma 3 4B graded replies for meaning with the question and key, blind to bank, condition and passage. Exact matches and the standard abstention were scored directly. Each distinct input was answered once and reused everywhere it occurred. The primary score counts a fully correct answer. Partial credit is listed separately.",""]
    keys=list(ORDER)+["Previous combined","New combined"]
    lines+=table(["Bank","Clean, full credit","One verse omitted, full credit","Accuracy loss (points)","Partial on clean"],[
        [k,fraction(totals[k]["clean"],totals[k]["n"]),fraction(totals[k]["omission"],totals[k]["n"]),
         f"{totals[k]['drop']*100:.1f}",totals[k]["clean_partial"]] for k in keys])
    ci=intervals["combined"]["clean_pp"];od=intervals["combined"]["omission_drop_pp"]
    lines+=["",f"The pooled clean accuracy difference was {ci['estimate']:+.1f} percentage points (paired ten-passage bootstrap range {ci['low']:+.1f} to {ci['high']:+.1f}). The between-bank difference in accuracy loss under omission was {od['estimate']:+.1f} points (range {od['low']:+.1f} to {od['high']:+.1f}). These 95% percentile ranges resample passages in pairs across banks, using 10,000 draws. They describe variation across these passages for this reader and grader.","",
            "A fixed hash of passage ID and verse labels chose the verse to remove before any response was collected. It used neither the question nor the key, so the omitted verse sometimes left all answer evidence intact. Matching windows lost the same verse. This tests one type of information loss on English text. The two conditions did not vary translation language, grammaticality or mistranslation severity.","",
            "## Previous editorial and answerability evidence","",
            "The blind check used GPT-5. Two GPT-5.6 Sol reviews judged the question and key on their own window. Prepared questions could be straightforward factual questions. Hard questions were also expected to test a meaningful distinction. The table scores the old forms as originally selected, and the new forms exactly as finally worded and placed. The new banks were selected using these checks, so the figures measure compliance with their selection rules.",""]
    lines+=table(["Bank","Blind answerability","Passed blind and both item reviews"],[[k,fraction(totals[k]["blind"],totals[k]["n"]),fraction(totals[k]["editorial"],totals[k]["n"])] for k in keys])
    lines+=["","## Independent check of the grading","",
            f"I also scored all {len(used)} distinct replies that were neither exact key matches nor standard abstentions. I saw the question, key and reply, with bank, condition and Gemma's grade hidden. Equivalent descriptions received full credit. Partial answers and contradictions were scored separately. My scores matched Gemma on {sum(agreement.values())}/{len(used)} of these three-way decisions. Both graders are models.",""]
    lines+=table(["Bank","Clean, full credit on rescore","One verse omitted, full credit on rescore"],
                 [[k,fraction(review_scores[k]["clean"],totals[k]["n"]),fraction(review_scores[k]["omission"],totals[k]["n"])] for k in keys])
    shared_change=sum(x["new_shared"]-x["old_shared"] for x in decomposition.values())
    added_full=sum(x["added_full"] for x in decomposition.values())
    removed_full=sum(x["removed_full"] for x in decomposition.values())
    lines+=["","## What changed","","Of 51 shared prepared IDs, 19 have a revised question or key and 14 moved to a different window; some did both. Of 62 shared hard IDs, 10 have revised questions or keys. Across both families 75 question–key–window combinations are unchanged at the same ID.","",
            f"On the 113 shared IDs, the change in fully correct clean responses was {shared_change:+d}. The reader answered {added_full}/24 of the added items correctly, compared with {removed_full}/24 of the items that left the bank.","",
            "One improvement is the Judges 18:27–28 hard question. The new stem asks for the *two circumstances* that left Laish without a rescuer, matching the two-part key. A tradeoff appears in 2 Kings 6:24–26. The earlier prepared question asks why food was expensive. Its revision asks what condition existed in Samaria at the stated price. The key is easier to grade, but the causal inference is no longer required.","",
            "The Hard77 also restores Judges 17:3–4, keyed to Micah’s son as the maker of the image. The earlier Chinese pilot excluded it because the rendering says the image was made for the son and names the silversmith as its maker. This comparison concerns the English instruments; that item needs target-language resolution before returning to the same Chinese pilot. [Canonical pilot note](../../datasets/qa/tier1_hard66_canonical/t1_judg17_18.json)","",
            "## Repeated questions across the two families","",
            "I inspected every prepared/hard pairing in each combined bank sharing at least one verse. Of 90 overlapping pairs per bank, seven previous pairs and six new pairs asked for essentially the same fact. The counts cover only overlapping references. In the new bank, for example, both families ask what the practitioners did with their books in Acts 19, and both ask which duty the off-Sabbath companies were assigned in 2 Kings 11. [Pair-level review](cross_family_overlap.json)","",
            "[Every question, response, omitted verse and grade](results.json) · [Frozen model digests and protocol](manifest.json) · [Prepared comparison](../prepared110_review_2026-11-08/review.md) · [Hard revision history](../hard85_revised_bank_2026-11-07/comparison_with_original_hard66.md)",""]
    old,new=totals["Previous combined"],totals["New combined"]
    lines[2:2]=[f"**I would choose Prepared60 + Hard77 for English open-response answerability.** The independent reader earned full credit on {new['clean']}/{new['n']} intact questions versus {old['clean']}/{old['n']} previously. A second, blinded scoring pass also favored the new bank. Accuracy fell by {new['drop']*100:.1f} percentage points for the new bank and {old['drop']*100:.1f} for the previous bank when one verse was removed. The omission comparison gives no clear advantage to either bank.",""]
    (OUT/"review.md").write_text("\n".join(lines))
    print(json.dumps({"counts":totals,"intervals":intervals},indent=2))


if __name__=="__main__":main()
