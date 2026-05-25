"""
RandomForest 기반 임산부 식품 추천 모델 학습

학습 데이터: backend/ml/training_recommendation_data.csv
출력: backend/ml/recommendation_model.pkl
      backend/ml/recommendation_model_meta.json

주의: 규칙 기반 기준을 바탕으로 학습한 초기 ML 추천 모델
      공식 의학 기준이 아님
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

_HERE = Path(__file__).resolve().parent
CSV_PATH = _HERE / "training_recommendation_data.csv"
MODEL_PATH = _HERE / "recommendation_model.pkl"
META_PATH = _HERE / "recommendation_model_meta.json"

FEATURE_COLUMNS = [
    "pregnancy_week",
    "trimester_encoded",
    "food_caffeine_mg",
    "food_sugar_g",
    "food_sodium_mg",
    "food_carbohydrate_g",
    "food_protein_g",
    "caffeine_missing",
    "sugar_missing",
    "sodium_missing",
    "caffeine_keyword_detected",
    "today_caffeine_mg",
    "today_sugar_g",
    "today_sodium_mg",
    "remaining_caffeine_mg",
    "remaining_sugar_g",
    "remaining_sodium_mg",
    "after_caffeine_ratio",
    "after_sugar_ratio",
    "after_sodium_ratio",
    "allergy_match",
]


def main():
    if not CSV_PATH.exists():
        print(f"❌ 학습 데이터 파일 없음: {CSV_PATH}")
        print("   먼저 python -m backend.ml.generate_training_data 를 실행하세요.")
        return

    df = pd.read_csv(CSV_PATH)
    print(f"총 데이터 수: {len(df)}")
    print(f"라벨 분포:\n{df['label'].value_counts().to_string()}")
    print()

    data_quality_warning: str | None = None
    if len(df) < 300:
        data_quality_warning = (
            "⚠️ 학습 데이터가 300개 미만입니다. "
            "현재 모델은 구조 테스트용이며 정확도를 신뢰하면 안 됩니다."
        )
        print(data_quality_warning)
        print()

    # 피처에 없는 컬럼 확인
    missing_cols = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing_cols:
        print(f"❌ CSV에 누락된 피처 컬럼: {missing_cols}")
        return

    X = df[FEATURE_COLUMNS].values
    y = df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"학습 데이터: {len(X_train)}개 / 테스트 데이터: {len(X_test)}개")
    print()

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        random_state=42,
        class_weight="balanced",   # 클래스 불균형 대응
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    print(f"테스트 정확도: {acc:.4f}")
    print()
    print("분류 보고서:")
    print(classification_report(y_test, y_pred))

    # 피처 중요도 출력
    importances = model.feature_importances_
    feat_importance = sorted(
        zip(FEATURE_COLUMNS, importances), key=lambda x: x[1], reverse=True
    )
    print("피처 중요도 (상위 10개):")
    for name, importance in feat_importance[:10]:
        print(f"  {name}: {importance:.4f}")
    print()

    # 모델 저장
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    # 메타데이터 저장
    meta = {
        "feature_columns": FEATURE_COLUMNS,
        "label_classes": list(model.classes_),
        "training_count": len(X_train),
        "test_accuracy": round(acc, 4),
        "note": "규칙 기반 기준을 바탕으로 학습한 초기 ML 추천 모델. 공식 의학 기준 아님.",
        "data_quality_warning": data_quality_warning,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"모델 저장 완료: {MODEL_PATH}")
    print(f"메타데이터 저장 완료: {META_PATH}")
    print(f"클래스 순서: {list(model.classes_)}")


if __name__ == "__main__":
    main()
