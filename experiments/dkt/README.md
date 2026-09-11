# Deep Knowledge Tracing Experiment

This directory contains the controlled Deep Knowledge Tracing (DKT) experiment conducted for the **Uchko** adaptive mathematics learning platform.

The experiment evaluates whether a compact recurrent sequence model can improve next-response prediction over a simple learner-history baseline and approach the performance of the XGBoost model deployed by Uchko.

DKT is included as an **offline comparative experiment**. It is not part of the deployed adaptive-learning pipeline because the final evaluation showed that XGBoost achieved better predictive performance on every reported metric.

## Research Question

The experiment addresses the following question:

> Can a compact recurrent knowledge-tracing model exploit ordered skill-response histories to improve next-response prediction, and can it match or exceed the feature-rich XGBoost predictor used by Uchko?

## Dataset and Evaluation Protocol

The experiment uses the protected **ASSISTments FoundationalASSIST** interaction data used by the rest of the Uchko modeling pipeline.

The original dataset was split at the **student level** using a fixed random seed, preventing interactions from the same learner from appearing in multiple partitions:

* training: 70%
* validation: 15%
* test: 15%
* random seed: `42`

The DKT experiment preserves the same student partitions and binary target definition used by the other Uchko predictors.

The target represents **independent success** on the current interaction. Sequential model inputs contain only information available before the response being predicted.

Because DKT requires at least one preceding interaction, the first response of each student cannot be evaluated. The matched final comparison therefore uses:

* validation students: `750`
* validation prediction pairs: `253,144`
* test students: `750`
* test prediction pairs: `253,718`

The held-out test partition was not used for checkpoint selection.

## Model

The implemented model is a compact GRU-based DKT architecture inspired by the original Deep Knowledge Tracing formulation.

Each interaction is represented as a joint **skill-response token**. The recurrent network processes the ordered interaction history and predicts correctness on the next observed skill.

Final configuration:

| Parameter               |   Value |
| ----------------------- | ------: |
| Architecture            |     GRU |
| Embedding dimension     |      64 |
| Hidden dimension        |     128 |
| GRU layers              |       1 |
| Dropout                 |    0.15 |
| Maximum sequence length |     100 |
| Batch size              |     128 |
| Optimizer               |    Adam |
| Learning rate           |   0.001 |
| Weight decay            | 0.00001 |
| Gradient clipping       |     5.0 |
| Maximum epochs          |      15 |
| Early-stopping patience |       3 |
| Random seed             |      42 |
| CPU threads             |      12 |
| Trainable parameters    | 113,881 |

The skill vocabulary contains `153` entries including the unknown-skill representation.

Sequences are divided into chunks of at most 100 prediction steps while preserving a one-event boundary overlap so that the first prediction in a new chunk retains the immediately preceding interaction.

The interaction encoding used by the implementation is:

```text
1 + 2 * skill_index + correctness
```

where correctness is the binary response associated with the interaction.

## Training

The model was trained on CPU using PyTorch.

Recorded environment:

```text
device: cpu
PyTorch: 2.14.0+cpu
threads: 12
```

Validation log loss was used for model selection. Training was allowed to continue for at most 15 epochs with patience 3.

The best checkpoint was obtained at:

```text
best epoch: 15
best validation log loss: 0.561314
```

Training can be rerun from the protected modeling environment with:

```bash
python train_dkt.py
```

The training environment must contain the original protected student-disjoint data splits and the Uchko ML artifacts expected by the script. Raw interaction data must not be copied into this repository.

## Evaluation

A saved checkpoint can be evaluated without retraining using:

```bash
python evaluate_dkt.py
```

The evaluation script:

1. restores the saved model configuration and checkpoint;
2. rebuilds the validation and test sequence datasets;
3. evaluates DKT on both partitions;
4. evaluates the history baseline on the same matched test rows;
5. evaluates the deployed XGBoost model on exactly the same matched rows; and
6. writes the aggregate metrics to `dkt_metrics.json`.

The reported metrics are:

* ROC AUC
* accuracy at threshold 0.5
* F1 score at threshold 0.5
* log loss
* Brier score

ROC AUC measures ranking performance, while log loss and Brier score are particularly relevant for Uchko because the adaptive policy directly consumes predicted probabilities.

## Final DKT Results

### Validation

| Metric      |    DKT |
| ----------- | -----: |
| ROC AUC     | 0.7556 |
| Accuracy    | 0.7110 |
| F1          | 0.7827 |
| Log loss    | 0.5613 |
| Brier score | 0.1901 |

### Matched Held-Out Test Set

All models in the following table are evaluated on the same `253,718` next-response cases from `750` held-out students.

| Model            |    ROC AUC |   Accuracy |         F1 |   Log loss |      Brier |
| ---------------- | ---------: | ---------: | ---------: | ---------: | ---------: |
| History baseline |     0.6932 |     0.6732 |     0.7602 |     0.6073 |     0.2097 |
| DKT              |     0.7620 |     0.7167 |     0.7878 |     0.5542 |     0.1872 |
| XGBoost          | **0.8125** | **0.7443** | **0.8060** | **0.5058** | **0.1692** |

DKT improves ROC AUC by approximately `0.0688` over the matched history baseline and reduces log loss by approximately `8.7%`.

This confirms that the ordered sequence of skill-response interactions contains useful predictive information.

However, the deployed XGBoost model exceeds DKT by approximately `0.0505` ROC AUC and also achieves lower log loss and Brier score.

The result therefore does **not** support replacing XGBoost with the recurrent model.

## Relation to BKT

Bayesian Knowledge Tracing remains part of the deployed Uchko system for a different purpose.

On the complete held-out test partition, BKT achieves:

| Metric      |    BKT |
| ----------- | -----: |
| ROC AUC     | 0.6850 |
| Accuracy    | 0.6772 |
| F1          | 0.7671 |
| Log loss    | 0.6105 |
| Brier score | 0.2106 |

BKT is retained because it provides an interpretable, continuously updated estimate of per-skill mastery rather than because it is the strongest next-response predictor.

The deployed Uchko architecture therefore assigns different responsibilities to the models:

* **XGBoost:** candidate success prediction;
* **BKT:** interpretable per-skill mastery tracking;
* **DKT:** controlled offline sequence-model comparison.

## Interpretation

The experiment demonstrates that using a neural sequence model does not automatically produce the strongest predictor.

DKT has access primarily to ordered skill-response histories. In contrast, Uchko's XGBoost model also uses problem identifiers, content metadata, temporal features, hint history, learner-history statistics, and skill-specific historical performance.

The two models therefore predict the same next-response target but do so from different representations of the available information.

The result should consequently be interpreted as:

> This compact GRU-based DKT configuration improves substantially over aggregate learner history, but it does not outperform Uchko's feature-rich XGBoost predictor on the same held-out next-response cases.

It should **not** be interpreted as evidence that recurrent knowledge-tracing methods are generally inferior to boosted trees.

More complex sequence architectures, richer interaction representations, or additional tuning could produce different results, but those alternatives would require a new controlled validation procedure.

## Deployment Decision

DKT was deliberately **not integrated into the production Uchko adaptive loop**.

The deployed XGBoost model:

* performs better on all reported predictive metrics;
* already integrates with Uchko's candidate-scoring pipeline;
* supports CPU inference;
* uses the same leakage-safe features used during training; and
* avoids introducing additional stateful sequence-inference complexity without demonstrated benefit.

The DKT experiment is retained because it provides a meaningful controlled comparison and documents why the deployed model was selected based on experimental evidence rather than architectural novelty.

## Reproducibility and Artifacts

The experiment uses fixed configuration values and random seed `42`.

The principal experiment outputs are:

```text
dkt_model.pt
dkt_schema.json
dkt_metrics.json
```

`dkt_metrics.json` contains the final aggregate configuration and evaluation results used in the Uchko report.

The schema records the skill vocabulary, unknown-skill representation, interaction encoding, prediction target, and model configuration required to reconstruct the model input semantics.

The final metrics were reconstructed from the saved best checkpoint after the original post-training comparison could not complete because XGBoost was temporarily unavailable in that environment. The saved checkpoint itself was not retrained for the final evaluation.

## Data Privacy

The raw FoundationalASSIST interaction data are protected project data and are intentionally excluded from this repository.

In particular, the repository must **not** contain:

* the original protected interaction CSV;
* processed interaction Parquet files;
* student-level raw interaction exports; or
* other data that would reproduce the protected source records.

Only source code, trained artifacts where appropriate, schemas, and aggregate evaluation results are retained.

Reproducing the complete experiment therefore requires authorized access to the original protected dataset and the same preprocessing pipeline used by the Uchko project.

## Project Context

This experiment accompanies:

**Uchko: A Hybrid XGBoost and Bayesian Knowledge Tracing Platform for Adaptive Mathematics Practice**

The main Uchko application remains based on the XGBoost + BKT hybrid architecture. DKT serves as an additional controlled model comparison for the project's experimental evaluation.
