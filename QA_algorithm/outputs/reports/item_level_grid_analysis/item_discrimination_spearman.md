# Per-item discrimination (Spearman of item-score vs translation-quality rank)

_Generated 2026-07-12_

For each item, rho correlates the 8 methods' **global quality rank** with the item's **score under each method** (mean of 3 answer models). High +rho = the question detects translation quality; ~0 = insensitive; negative = perverse.

**Items scored:** 201  |  with a computable rho: 192  |  degenerate (all-tie): 9

**Distribution:** strong probes (rho>0.5): 52  |  flat (-0.3..0.3): 66  |  perverse (rho<-0.3): 23

**Mean rho (computable items):** 0.254  |  **median:** 0.337


## Top 15 discriminating items

| chapter | item | ref | type | rho | mean | question |
|---|---|---|---|---|---|---|
| luke5 | uw-174409-open | Luke 5:32 | open | 0.932 | 0.542 | 主人甲说他来的目的是什么？ |
| luke5 | uw-174410-mcq | Luke 5:35 | mcq | 0.926 | 0.333 | 主人甲说他的门徒什么时候禁食？ |
| luke4 | uw-174388-mcq | __文本甲__ 4:21 | mcq | 0.901 | 0.562 | __人物己__说那天实现了什么？ |
| luke3 | uw-174370-open | 文本甲 3:16 | open | 0.83 | 0.542 | 人物丙说有人将用什么施洗？ |
| luke8 | uw-174454 | Luke 8:48 | open | 0.828 | 0.667 | 是什么治愈了那个血漏的女人？ |
| luke5 | uw-174401-open | Luke 5:5 | open | 0.825 | 0.208 | 尽管一无所获，人物02做了什么？ |
| luke4 | uw-174394-mcq | __文本甲__ 4:30 | mcq | 0.782 | 0.771 | __人物己__如何避免被人群杀害？ |
| luke8 | uw-174445-open | 文本甲 8:12 | open | 0.782 | 0.625 | 路旁的种子是谁？ |
| luke1 | uw-174316-mcq | 文本甲 1:4 | mcq | 0.756 | 0.75 | 文本甲为什么写他的记述？ |
| luke2 | uw-174361-open | 文本甲 2:46 | open | 0.756 | 0.25 | 人物己的父母在哪里找到他？ |
| luke6 | uw-174422-open | 文本甲 6:27 | open | 0.756 | 0.917 | 群体02应如何对待敌人？ |
| luke6 | uw-174424-mcq | 文本甲 6:42 | mcq | 0.756 | 0.75 | 在去除别人眼中的刺之前，我们必须做什么？ |
| luke8 | uw-174455-open | 文本甲 8:55 | open | 0.756 | 0.083 | 人物己在人物05家做了什么？ |
| luke3 | uw-174368-mcq | 文本甲 3:9 | mcq | 0.732 | 0.792 | 没有好果子的树会怎样？ |
| luke6 | uw-174427-mcq | 文本甲 6:47 | mcq | 0.732 | 0.792 | 谁像是在磐石上建房的人？ |

## Most perverse (negative rho) — worse translations scored higher

| chapter | item | ref | rho | mean | question |
|---|---|---|---|---|---|
| luke5 | uw-174402-open | Luke 5:6 | -0.012 | 0.542 | 他们放下网之后发生了什么？ |
| luke5 | uw-174410-open | Luke 5:35 | -0.014 | 0.167 | 主人甲的门徒什么时候禁食？ |
| luke1 | uw-174336-open | 文本甲 1:42 | -0.026 | 0.25 | 人物乙说谁是有福的？ |
| luke8 | uw-174444-open | 文本甲 8:11 | -0.031 | 0.896 | 在人物己的比喻中，种子是什么？ |
| luke3 | uw-174370-mcq | 文本甲 3:16 | -0.056 | 0.542 | 人物丙说有人将用什么施洗？ |
| luke6 | uw-174414-mcq | 文本甲 6:1 | -0.056 | 0.875 | 人物己的群体02在安息日摘取什么？ |
| luke1 | uw-174333-open | 文本甲 1:35 (#2) | -0.063 | 0.708 | 圣婴是谁的儿子？ |
| luke8 | uw-174448-open | 文本甲 8:15 | -0.076 | 0.562 | 好土上的种子是谁？ |
| luke7 | uw-174442-open | 文本甲 7:49 | -0.078 | 0.458 | 人们对人物己赦罪的反应是什么？ |
| luke4 | uw-174379-mcq | __文本甲__ 4:3 | -0.082 | 0.958 | 实体01挑战__人物己__将石头变成什么？ |

## Caveats

- Item score per method is the mean of 3 models -> values in {0,1/3,2/3,1}; still tie-prone, so single-item rho is noisy. Read the **distribution**, not any one item.

- Many items are near ceiling (mean_score high) -> no variance across methods -> degenerate, no rho. Those items are poor QC probes by construction.

- Quality rank is the global consensus ranking; if that ordering is noisy, item rho inherits it.

