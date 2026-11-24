# Hard66 clean-passage answerability

Report-only run with gpt-5. The blind reader saw one Chinese question and its clean Chinese verse window. The second call compared the readings with the Chinese keyed answer. Choices, prior review and historical scores were withheld from the reader.

| Set | Passed | Flagged | Unchecked |
|---|---:|---:|---:|
| Active | 63 | 2 | 0 |
| Previously excluded | 0 | 1 | 0 |

## Comparison with earlier clean MCQ results

Each active question has one response each from Gemma 3 4B, Phi-4 Mini 3.8B and Qwen 2.5 3B. Percentages measure model agreement with the MCQ key. Human accuracy was not measured.

- Flagged questions had 6/6 correct responses (100.0%).
- Passed questions had 154/189 correct responses (81.5%).

### Questions missed by all three models on clean text

- **uw-t1_2kgs6_7:6138-mcq** (7:14, 7:15, 7:16) — 百姓出去掠夺叙利亚营之前，刚发生了什么事？ Key: 侦察者回来告诉王. Answerability: pass. The passage explicitly states the scouts returned and reported to the king immediately before the people went out to plunder.
- **uw-t1_2kgs6_7:ea44-mcq** (6:29, 6:30, 6:31) — 两个妇人先吃了谁的孩子？ Key: 向王呼喊的那个妇人的孩子. Answerability: pass. “我们煮了我的儿子吃了” shows the first eaten child belonged to the speaking woman, i.e., the one addressing the king.

## Active questions for review

### uw-t1_2sam21:de9f-mcq · 21:15, 21:16, 21:17

**亚比筛击杀了谁？**

Key — 非利士人以施比·比拿

**Multiple answers** — Verse 17 says “击杀了那非利士人,” and the antecedent Philistine in v.16 is Ishbi-Benob, so “那非利士人” is accurate though less specific than the key.

- 那非利士人 — “击杀了那非利士人” Verse 17 says “击杀了那非利士人,” and the antecedent Philistine in v.16 is Ishbi-Benob, so “那非利士人” is accurate though less specific than the key.
- 以施比·比拿 — “拉法的后裔以施比·比拿 | 那非利士人” The passage names the Philistine as “以施比·比拿” (v.16), and v.17 says Abishai killed that Philistine, matching the key exactly.

> 15 非利士人再次与以色列争战，大卫和他的仆人下去与非利士人作战。但大卫疲惫不堪。
> 16 那时，拉法的后裔以施比·比拿，拿着一根重三百舍客勒的铜矛，带着一把新剑，想要杀大卫。
> 17 但洗鲁雅的儿子亚比筛来帮助大卫，击杀了那非利士人。于是大卫的众人向他起誓说：“你不可再和我们同去打仗，免得以色列的灯灭了。”

### uw-t1_judg9:0bd2-mcq · 9:50, 9:51, 9:52, 9:53

**亚比米勒来到楼门，是要做什么？**

Key — 去点火烧楼。

**Multiple answers** — The verse says “亚比米勒来到攻打楼门，准备点火烧楼,” so saying he came to attack the door answers what he came to do, though the key emphasizes the intended burning.

- 攻打楼门 — “亚比米勒来到攻打楼门” The verse says “亚比米勒来到攻打楼门，准备点火烧楼,” so saying he came to attack the door answers what he came to do, though the key emphasizes the intended burning.
- 点火烧楼 — “准备点火烧楼” Directly matches “准备点火烧楼,” which is the stated purpose in the passage and the key’s answer.

> 50 亚比米勒往底璧去，围困攻取了那城。
> 51 城中有一座坚固的楼，城里的男人、女人和首领都逃到那里，锁门上楼顶。
> 52 亚比米勒来到攻打楼门，准备点火烧楼。
> 53 有一个妇人从楼上丢下一块上磨石，打在亚比米勒头上，打破了他的头骨。


## Previously excluded questions for review

### uw-t1_judg17_18:ac64-mcq · 17:3, 17:4

**母亲说谁要用这银子制作雕像？**

Key — 她的儿子

**Missing evidence** — No supported blind reading matches the key.

- 她自己 — “我将这银子完全献给耶和华，为我儿子的缘故铸造雕像和熔铸的偶像” 在经文里她说“为我儿子的缘故…所以我现在要把银子还给你”，明确把银子还给儿子，表明是为儿子来制作，而不是她自己。

> 3 他将那一千一百舍客勒银子还给他母亲时，她说：“我将这银子完全献给耶和华，为我儿子的缘故铸造雕像和熔铸的偶像。所以我现在要把银子还给你。”
> 4 他便把银子还给他母亲，她拿出二百舍客勒银子，交给银匠，银匠铸成雕像和熔铸的偶像，放在米迦的家中。
