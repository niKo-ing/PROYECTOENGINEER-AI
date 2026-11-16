"""Entrena y evalúa el modelo de emparejamiento. Uso:

    DATABASE_URL=sqlite:///./ep3_data.db python -m ml.train [--out EP3_ITY1102/modelo]

Compara una línea base (regla de similitud), regresión logística, random forest y gradient boosting con validación
cruzada agrupada por producto, elige por F1 y evalúa en un conjunto de prueba que no vio el entrenamiento.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GridSearchCV, GroupKFold

from ml.dataset import build_pairs, split_by_product, to_matrix
from ml.features import FEATURE_NAMES

SEED = 7


def load_products() -> list[tuple[int, str, str | None]]:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.catalog import Product

    with SessionLocal() as db:
        return [(p.id, p.name, p.brand) for p in db.scalars(select(Product)) if p.name]


def metrics(y_true, y_pred, y_prob) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_true, y_prob), 4),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="EP3_ITY1102/modelo")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    products = load_products()
    pairs = build_pairs(products, seed=SEED)
    train, test = split_by_product(pairs, seed=SEED)
    X_train, y_train = to_matrix(train)
    X_test, y_test = to_matrix(test)
    groups = np.array([p.product_a for p in train])
    print(f"productos={len(products)} pares={len(pairs)} entrenamiento={len(train)} prueba={len(test)}")

    candidates = {
        "logistic_regression": (LogisticRegression(max_iter=2000, class_weight="balanced"), {"C": [0.1, 1.0, 10.0]}),
        "random_forest": (RandomForestClassifier(random_state=SEED, class_weight="balanced"), {"n_estimators": [100, 300], "max_depth": [6, 12, None]}),
        "gradient_boosting": (GradientBoostingClassifier(random_state=SEED), {"n_estimators": [100, 200], "learning_rate": [0.05, 0.1], "max_depth": [2, 3]}),
    }
    cv = GroupKFold(n_splits=5)
    report: dict = {"candidatos": {}}
    best_name, best_search = None, None
    for name, (estimator, grid) in candidates.items():
        start = time.time()
        search = GridSearchCV(estimator, grid, scoring="f1", cv=cv, n_jobs=-1)
        search.fit(X_train, y_train, groups=groups)
        report["candidatos"][name] = {"mejores_hiperparametros": search.best_params_, "f1_validacion_cruzada": round(search.best_score_, 4), "segundos": round(time.time() - start, 1)}
        print(name, report["candidatos"][name])
        if best_search is None or search.best_score_ > best_search.best_score_:
            best_name, best_search = name, search

    # Línea base: umbral sobre la similitud de caracteres, elegido en entrenamiento.
    ratio_train, ratio_test = X_train[:, 0], X_test[:, 0]
    thresholds = np.linspace(0.3, 0.95, 66)
    best_t = max(thresholds, key=lambda t: f1_score(y_train, ratio_train >= t))
    report["linea_base"] = {"regla": f"similitud_de_caracteres >= {best_t:.2f}", **metrics(y_test, (ratio_test >= best_t).astype(int), ratio_test)}

    model = best_search.best_estimator_
    prob = model.predict_proba(X_test)[:, 1]
    report["modelo_elegido"] = best_name
    report["prueba"] = metrics(y_test, (prob >= 0.5).astype(int), prob)
    per_kind = {}
    for kind in sorted({p.kind for p in test}):
        idx = [i for i, p in enumerate(test) if p.kind == kind]
        per_kind[kind] = {"n": len(idx), "aciertos": round(float(np.mean([(prob[i] >= 0.5) == bool(y_test[i]) for i in idx])), 4)}
    report["por_tipo_de_par"] = per_kind
    report["tabla_de_umbrales"] = [
        {"umbral": t, "precision": round(float(y_test[prob >= t].mean()), 3) if (prob >= t).any() else None, "cobertura_de_positivos": round(float(((prob >= t) & (y_test == 1)).sum() / y_test.sum()), 3)}
        for t in (0.5, 0.6, 0.7, 0.8, 0.9)
    ]
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        importances = np.abs(model.coef_[0])
    report["importancia_caracteristicas"] = {n: round(float(v), 4) for n, v in sorted(zip(FEATURE_NAMES, importances), key=lambda x: -x[1])}
    report["dataset"] = {"productos": len(products), "pares": len(pairs), "entrenamiento": len(train), "prueba": len(test), "positivos_prueba": int(y_test.sum()), "semilla": SEED}

    joblib.dump({"estimator": model, "version": time.strftime("%Y%m%d"), "features": FEATURE_NAMES}, out / "match_model.joblib")
    (out / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    with open(out / "pares_prueba.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["titulo_a", "titulo_b", "etiqueta", "tipo"])
        writer.writerows([[p.a, p.b, p.label, p.kind] for p in test])
    print(json.dumps({k: report[k] for k in ("modelo_elegido", "linea_base", "prueba", "por_tipo_de_par")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
