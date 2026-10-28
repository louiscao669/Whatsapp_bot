# Gold72 vs Hard66 accuracy percentages

Gold72: 71 MCQs per condition. Hard66: 65 MCQs per condition.

Hard66 grammar uses a later variant bank; comparisons are descriptive across different question sets.

## Llama 3.2 1B

| Condition | Gold72 | Hard66 |
|---|---:|---:|
| Clean | 59.2% | 46.2% |
| Omission 5% | 53.5% | 46.2% |
| Omission 10% | 56.3% | 46.2% |
| Omission 15% | 52.1% | 46.2% |
| Omission 20% | 53.5% | 41.5% |
| Omission 25% | 53.5% | 36.9% |
| Omission 30% | 53.5% | 44.6% |
| Mistranslation 5% | 52.1% | 41.5% |
| Mistranslation 10% | 50.7% | 44.6% |
| Mistranslation 15% | 50.7% | 40.0% |
| Mistranslation 20% | 46.5% | 36.9% |
| Mistranslation 25% | 47.9% | 32.3% |
| Mistranslation 30% | 36.6% | 30.8% |
| Grammar 5% | 54.9% | 46.2% |
| Grammar 10% | 54.9% | 47.7% |
| Grammar 15% | 54.9% | 46.2% |
| Grammar 20% | 54.9% | 46.2% |
| Grammar 25% | 54.9% | 46.2% |
| Grammar 30% | 54.9% | 46.2% |
| WBW | 45.1% | 32.3% |

## Qwen 2.5 1.5B

| Condition | Gold72 | Hard66 |
|---|---:|---:|
| Clean | 90.1% | 86.2% |
| Omission 5% | 85.9% | 84.6% |
| Omission 10% | 84.5% | 76.9% |
| Omission 15% | 85.9% | 72.3% |
| Omission 20% | 84.5% | 70.8% |
| Omission 25% | 80.3% | 70.8% |
| Omission 30% | 78.9% | 67.7% |
| Mistranslation 5% | 88.7% | 81.5% |
| Mistranslation 10% | 84.5% | 78.5% |
| Mistranslation 15% | 81.7% | 75.4% |
| Mistranslation 20% | 81.7% | 67.7% |
| Mistranslation 25% | 76.1% | 61.5% |
| Mistranslation 30% | 74.6% | 58.5% |
| Grammar 5% | 88.7% | 86.2% |
| Grammar 10% | 90.1% | 86.2% |
| Grammar 15% | 90.1% | 86.2% |
| Grammar 20% | 90.1% | 86.2% |
| Grammar 25% | 90.1% | 87.7% |
| Grammar 30% | 90.1% | 87.7% |
| WBW | 94.4% | 64.6% |

## Qwen3 1.7B · thinking

| Condition | Gold72 | Hard66 |
|---|---:|---:|
| Clean | 88.7% | 78.5% |
| Omission 5% | 78.9% | 76.9% |
| Omission 10% | 77.5% | 67.7% |
| Omission 15% | 71.8% | 69.2% |
| Omission 20% | 67.6% | 64.6% |
| Omission 25% | 66.2% | 60.0% |
| Omission 30% | 62.0% | 55.4% |
| Mistranslation 5% | 85.9% | 73.8% |
| Mistranslation 10% | 80.3% | 66.2% |
| Mistranslation 15% | 81.7% | 69.2% |
| Mistranslation 20% | 78.9% | 66.2% |
| Mistranslation 25% | 67.6% | 50.8% |
| Mistranslation 30% | 59.2% | 50.8% |
| Grammar 5% | 91.5% | 76.9% |
| Grammar 10% | 87.3% | 78.5% |
| Grammar 15% | 88.7% | 80.0% |
| Grammar 20% | 87.3% | 76.9% |
| Grammar 25% | 90.1% | 75.4% |
| Grammar 30% | 91.5% | 75.4% |
| WBW | 85.9% | 66.2% |

## Qwen3 1.7B · no thinking

| Condition | Gold72 | Hard66 |
|---|---:|---:|
| Clean | 88.7% | 73.8% |
| Omission 5% | 80.3% | 69.2% |
| Omission 10% | 78.9% | 66.2% |
| Omission 15% | 77.5% | 66.2% |
| Omission 20% | 70.4% | 63.1% |
| Omission 25% | 66.2% | 60.0% |
| Omission 30% | 64.8% | 56.9% |
| Mistranslation 5% | 83.1% | 69.2% |
| Mistranslation 10% | 76.1% | 64.6% |
| Mistranslation 15% | 74.6% | 60.0% |
| Mistranslation 20% | 73.2% | 60.0% |
| Mistranslation 25% | 64.8% | 49.2% |
| Mistranslation 30% | 57.7% | 50.8% |
| Grammar 5% | 88.7% | 75.4% |
| Grammar 10% | 88.7% | 75.4% |
| Grammar 15% | 87.3% | 72.3% |
| Grammar 20% | 87.3% | 73.8% |
| Grammar 25% | 87.3% | 76.9% |
| Grammar 30% | 87.3% | 76.9% |
| WBW | 73.2% | 53.8% |
