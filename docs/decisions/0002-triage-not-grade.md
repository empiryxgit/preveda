# 0002 Predict triage, not severity grade
Context: too few graded images to train a reliable 5-level grader. Decision: model predicts 4 classes; triage rules + clinician-owned guidelines give follow-up; grade comes only from clinician review. Consequence: no grade is ever shown as AI output.
