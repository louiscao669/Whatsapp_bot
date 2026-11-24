# Second rewrites of the two flagged questions

Both questions started from the original flagged English items. The writer received feedback for each item. The models, verse windows, target-review rubric, and Chinese verification recipe match the previous run. File hashes confirm the shared rewrite and review code was identical before and after this rerun.

## 1 Kings 13:26–28 · Prepared QA

**Previous**　老先知叫他的儿子们为他做什么？

**New**　他儿子们给他备好驴之后，老先知接下来做了什么？

After his sons saddled the donkey, what did the old prophet do next?

| Choice | Chinese | English |
| --- | --- | --- |
| **A (key)** | 他出去找到神人的尸体。 | He went out and found the man of God's body. |
| B | 他聚集镇上的人帮助找回神人的尸体。 | He gathered the townspeople to help recover the man of God's body. |
| C | 他出去把狮子赶离驴。 | He went out and drove the lion away from the donkey. |
| D | 他打发儿子们去寻找神人的尸体。 | He sent his sons to search for the man of God's body. |

**Review of the retained fact.** The revised question clearly asks only for the old prophet’s next action, which the original question requested and its compound answer supplied. It intentionally drops the instruction to his sons. The key uniquely matches the supported action of going and finding the body, and the stem does not reveal that answer.

## Judges 18:27–28 · Generated from scratch

**Previous**　拉亿人没有被任何人拯救的地理原因是什么？

**New**　除了居住地离西顿很远之外，拉亿人为什么没有人来帮助他们？

Besides living far from Sidon, why did the people of Laish have no one to help them?

| Choice | Chinese | English |
| --- | --- | --- |
| **A (key)** | 他们与其他社区没有联系。 | They had no connections with other communities. |
| B | 他们的邻居拒绝与但人作战。 | Their neighbors refused to fight against the Danites. |
| C | 他们的盟友正在别处打仗。 | Their allies were already fighting a war elsewhere. |
| D | 他们的使者在请求帮助之前就被俘虏了。 | Their messengers were captured before they could request help. |

**Review of the retained fact.** The revision asks only for the lack of outside ties, one of the two circumstances requested by the original question and supplied by its compound answer. The key accurately paraphrases that circumstance for the same people and rescue situation. The stem supplies the distance from Sidon as context without revealing the requested answer.

The first Chinese draft of the old-prophet answer rendered “on the road” as “beside the road.” Both automated checks accepted it. A fresh run for this item addressed the discrepancy using item-specific feedback.

## Review results

GPT-6.1 Sol generated the English stems, keys, and distractors. GPT-6 Astra accepted both English items for answerability, fidelity to the original fact, and alignment of all four options. Qwen3 8B translated them against the pilot’s clean Chinese passages and selected only the keyed option on both blind checks. The Chinese fidelity check reported no issues, and Astra passed both Chinese items for focus and alignment.
