# Core-Claim Grading Test Set

## Grading Prompt

Grade the generated answer against the expected answer.

  Be semantically flexible: accept paraphrases, rough grammar, anonymized names, and equivalent wording.

  But require the generated answer to contain the expected answer's core claim. Do not mark an answer correct merely because it
  mentions related passage context, a nearby event, or something true from the passage.

  First identify the required answer slot:
  - person/group
  - object/place
  - action/event
  - reason/cause
  - time
  - statement/content
  - result/outcome

  Then check whether the generated answer fills that slot with the same meaning as the expected answer.

  Scores:
  1.0 = contains the core claim required by the expected answer.
  0.5 = partially answers the right slot but is incomplete, overly broad, or missing one important element.
  0.0 = wrong slot, nearby context only, contradiction, or missing the core claim.

  Return JSON:
  {
    "score": 0.0 | 0.5 | 1.0,
    "label": "correct" | "partial" | "incorrect",
    "required_slot": "...",
    "core_claim_expected": "...",
    "core_claim_found": true | false,
    "rationale": "..."
  }

## Sample Cases

### 1. Related Context, Wrong Core Claim

Source: `evaluation/outputs/luke8/1.5b/llm_prompt_low/scores_target_llama.json`

Question: 是什么医治了流血的妇人？

Expected answer: Her faith in Person F.

Generated answer: 力量发出的。

Generated answer English: The power emitted healed the bleeding woman.

Current old grade: `1.0 correct`

Expected new grade: `0.0 incorrect`

Reason: The answer mentions related passage context, but the required reason/cause is faith/trust, not emitted power.

### 2. Wrong Slot: Action Instead Of Reason

Source: `evaluation/outputs/luke4/1.5b/llm_prompt_low/scores_target_llama.json`

Question: 人物己为何让鬼魔保持沉默？

Expected answer: Person F is the Son of Most High A.

Generated answer: 他责备他们，不许他们说。

Generated answer English: He rebuked them and told them not to speak.

Current old grade: `1.0 correct`

Expected new grade: `0.0 incorrect`

Reason: The generated answer repeats the action of silencing, but the question asks why; the required reason/content is that the demons knew his identity.

### 3. Clean Correct Paraphrase

Source: `evaluation/outputs/luke1/1.5b/llm_prompt_low/scores_target_llama.json`

Question: 文本甲为什么写他的记述？

Expected answer: To assure Recipient A of certainty.

Generated answer: 为了让收信者知道所学的确定性

Generated answer English: To let the recipient know the certainty of the learning.

Current old grade: `1.0 correct`

Expected new grade: `1.0 correct`

Reason: The generated answer directly gives the same reason/purpose.

### 4. Correct With Equivalent Action

Source: `evaluation/outputs/luke7/1.5b/llm_prompt_low/scores_target_llama.json`

Question: 角色01希望人物己怎样医治？

Expected answer: By just saying a word.

Generated answer: 对他的角色02说“做这事”，他就做。

Generated answer English: He wanted him to tell his servant to do it, and the servant would do it.

Current old grade: `1.0 correct`

Expected new grade: `1.0 correct`

Reason: Although worded differently, it captures healing by command/word without physical presence.

### 5. Nearby Context Only

Source: `evaluation/outputs/luke4/1.5b/llm_prompt_high/scores_target_llama.json`

Question: 人物01 挑战人物己做什么？

Expected answer: Turn stones into bread.

Generated answer: 被 人物01 试探了四十天。他那些日子里什么也没吃，到了最后，他感到饥饿。

Generated answer English: He was tested by Person 01 for forty days, during which he ate nothing and finally felt hungry.

Current old grade: `0.0 incorrect`

Expected new grade: `0.0 incorrect`

Reason: True nearby context, but it does not give the challenged action.

### 6. Wrong Slot: Place Instead Of Object

Source: `evaluation/outputs/luke4/1.5b/llm_prompt_high/scores_target_llama.json`

Question: 人物01 从高处给人物己 展示了什么？

Expected answer: All kingdoms of the world.

Generated answer: 地点02

Generated answer English: Place 02

Current old grade: `0.0 incorrect`

Expected new grade: `0.0 incorrect`

Reason: The answer gives the display location/source, not the object shown.

### 7. Partial: Right Group But Missing Required Result

Source: `evaluation/outputs/luke8/1.5b/llm_prompt_high/scores_target_llama.json`

Question: 好土上的种子是谁？

Expected answer: Hear, hold, produce fruit.

Generated answer: 心地善良纯洁的人

Generated answer English: People with kind and pure hearts.

Current old grade: `0.0 incorrect`

Expected new grade: `0.5 partial`

Reason: The answer points to the right kind of people, but misses the required actions/result: hearing, holding, and producing fruit.

### 8. Wrong Person

Source: `evaluation/outputs/luke1/1.5b/llm_prompt_high/scores_target_llama.json`

Question: 人物乙说谁是有福的？

Expected answer: Person D and her baby.

Generated answer: 人物戊和人物丁

Generated answer English: None

Current old grade: MCQ direct score `0.0 incorrect`

Expected new grade: `0.0 incorrect`

Reason: The answer names the wrong pair; it omits the baby.

### 9. Contradiction

Source: `evaluation/outputs/luke5/1.5b/llm_prompt_high/scores_target_llama.json`

Question: 如果新酒装在旧皮袋里会怎样？

Expected answer: Wine will burst wineskins.

Generated answer: 新酒不会把旧皮袋撑裂。

Generated answer English: The new wine will not burst the old wineskins.

Current old grade: `0.0 incorrect`

Expected new grade: `0.0 incorrect`

Reason: The generated answer directly contradicts the expected result.

### 10. Correct With Extra Context

Source: `evaluation/outputs/luke2/1.5b/llm_prompt_low/scores_target_llama.json`

Question: 群体01在地点02发现了什么？

Expected answer: Person D, Person E, and the baby.

Generated answer: 群体01在地点02找到了人物丁和人物戊及躺在物件01里的婴儿。

Generated answer English: Group 01 found Person D, Person E, and the baby lying in Object 01 at Location 02.

Current old grade: `1.0 correct`

Expected new grade: `1.0 correct`

Reason: The generated answer includes the full core answer and only adds harmless detail.
