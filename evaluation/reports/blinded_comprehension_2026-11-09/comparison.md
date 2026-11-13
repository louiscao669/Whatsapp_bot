# Chinese comprehension before and after pseudonymization

## Clean passages

Each reader answered all 122 Chinese questions against the corresponding unblinded and blinded Sol verse windows. The primary comparison uses the 119 pilot-eligible questions. The reader saw the window, question and four choices. Only an exact, single-option match counted as correct.

| Local reader | Original | Blinded | Difference (pp) | Lost | Gained |
|---|---:|---:|---:|---:|---:|
| qwen3:8b | 115/119 | 112/119 | -2.52 | 4 | 1 |
| gemma3:4b | 75/119 | 66/119 | -7.56 | 15 | 6 |

On 14 of Gemma's 15 newly missed items it still chose the keyed answer along with at least one distractor. Counting any selection containing the key gives 110/119 before blinding and 106/119 afterward.

One of Qwen's four newly missed items was a letter-selection error. In Acts 23:23–24 the blinded explanation correctly identifies the two centurions who received the order, but the returned letter C selects the two hundred infantrymen. D is the centurions. It is counted as a miss under the same scoring rule as the original.

qwen3:8b scored 2/3 before and 2/3 after blinding on the withheld items. gemma3:4b scored 2/3 before and 2/3 after blinding on the withheld items.

## Reading the pseudonyms

In 1 Kings 13:11 the original introduces an old prophet (一个老先知). The blinded text introduces him as 一个利德. Two verses later he is still called 先知 when he asks for his donkey. A reader must infer that 利德 and the prophet are the same person.

Another question in the same passage changes from 老先知在哪里找到神人？ to 利德在哪里找到尼伦？ Gemma originally selected only 橡树下 (‘under an oak tree’). After blinding it also selected 通往拉伦的路上 (‘on the road to the pseudonymized place’). Qwen selected only the key both times.

In Judges 17:13 有一个利未人作了我的祭司 becomes 有一个韦伦作了我的祭司. A reader can recover the keyed answer by matching the wording, even though the replacement hides the group identity that explains why the speaker expects favor.

The original 2 Samuel 21:16 uses 伊施比比诺 in the passage and 以施比·比拿 in an answer choice. Both become 塞达. Here blinding removes a spelling difference the reader had to resolve.

There were 22 eligible windows in 1 Kings 13 or Judges 17–18 containing one of the targeted role descriptions (老先知, 年老的先知, 神人, or 利未人). Eight keyed choices explicitly used one. This subgroup is descriptive and comes from two passages.

| Reader | Role-description windows, original → blinded | Other windows, original → blinded |
|---|---:|---:|
| qwen3:8b | 22/22 → 22/22 | 93/97 → 90/97 |
| gemma3:4b | 14/22 → 12/22 | 61/97 → 54/97 |

## Defect variants

Qwen answered one eligible question in each of the 180 passage–defect–dose combinations (109 distinct questions). Selection rotated through a fixed hashed order within each passage. Both versions used the same question, option order and delivered verse labels, including the usual padding for omissions. The scores below measure agreement with the clean key. A damaged passage can legitimately support a different answer or supply insufficient evidence.

| Family | Original | Blinded | Lost | Gained |
|---|---:|---:|---:|---:|
| Omission | 51/60 | 48/60 | 4 | 1 |
| Mistranslation | 52/60 | 52/60 | 1 | 1 |
| Grammar | 57/60 | 55/60 | 3 | 1 |

Across all variants the reader matched 160/180 original keys and 155/180 blinded keys. It selected the same supported options in 165/180 pairs.

## Method and scope

The clean Qwen3 8B comparison uses the archived original responses, verified against the exact requests, model digest, Ollama version and settings. Both arms used the same four-item batches and requested an explanation. The runner retries incomplete batches one item at a time. Gemma 3 4B answered both clean versions afresh, one question per request. The variant check used four-item batches with different passages. Gemma and the variant check returned option labels only. Temperature was zero. Answer keys and release labels were omitted from every model request.

The two readers give model-based evidence. Human accuracy, reading time and perceived difficulty were not measured. Questions share passages, and the variant sample repeats some questions. The item-level outcomes, paired changes and passage-resampled intervals are in results.json. Variant-level responses and sample IDs are in variants.json.
