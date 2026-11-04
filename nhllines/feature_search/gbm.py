"""Non-linear reference: gradient boosting on every feature, same LOSO folds."""
import numpy as np, harness as H
from sklearn.ensemble import HistGradientBoostingClassifier
ev = H.Evaluator()
for lr, leaves, it in [(0.03, 7, 200), (0.03, 15, 300), (0.01, 7, 600), (0.05, 4, 150)]:
    ll = []
    for s, Xtr, ytr, Xte, yte in ev.folds:
        if s in H.SCORED:
            m = HistGradientBoostingClassifier(learning_rate=lr, max_leaf_nodes=leaves, max_iter=it,
                                               l2_regularization=1.0, min_samples_leaf=80, random_state=0)
            ll.append(H.logloss(m.fit(Xtr, ytr).predict_proba(Xte)[:, 1], yte))
    print(f"GBM lr={lr} leaves={leaves} iters={it}: LOSO LL {np.concatenate(ll).mean():.5f}", flush=True)
