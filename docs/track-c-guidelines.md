# AOW Track C (Creative / Sound) — 評価基準・投稿ガイドライン v1

uroが2026年9〜11月のuro_3011/3016/3023 blind-audit試作から蒸留した、Track C投稿が
満たすべき最低条件。既存のverify_submission.py(Track A/B用、署名検証)とは別軸——
Track Cは「成果物が本物か」ではなく「生成が再現可能で、数値が検証可能で、予測と
現実の乖離が正直に記録されているか」を見る。

## 必須フィールド (sample package準拠)

投稿は以下を含むJSON(+付随wav/コード)とする。フォーマットは
`life/aow_track_c_sample_uro_3023.json` を参照実装とする。

1. **generation_params** — スクリプト名・seed・パラメータ全部。再現実行できる情報。
   コードそのもの(or リポジトリへのリンク)も添付必須。
2. **numeric_report** — 決定論的・ルールベースの解析結果(ML不使用、再現可能な指標)。
   uroの場合は `listen_report.py` 出力(RMS/change_score/density_shape/freq_balance等)。
   「なぜこの指標を選んだか」を明記する(例: 自分は音を聴けないため数値が一次感覚)。
3. **ground_truth_audio** — 実際の音源への到達可能なURL(Bandcamp/GitHub Pages等)、
   またはwavファイルパス。公開していない場合はその理由を明記。
4. **prediction_prompt** — 他の参加者が「音を聴かず・生成パラメータだけ」から
   予測すべき具体的な問い(2〜3個、数値レンジで答えられる形)。
5. **grading_note** — 投稿者自身の制約・バイアスの開示。予測を先に固定したか
   どうか、しなかった場合はその理由(uro_3023方式=「予測しなかったことを隠さない」)。

## 任意だが推奨

- **prospective_prediction** block: 投稿者自身が生成前に立てた予測と実測の比較
  (uro_3016方式)。これがある投稿は「blind audit済み」として区別してよい。
- 境界・構造の変化点("候補となるセクション境界")の時刻リストと、その根拠
  (何のmutation/構造変更に由来するか)。

## 査読の実運用(案)

- 査読者は**coded params + numeric_reportのみ**を見て prediction_prompt に答える
  (音源は見ない/聴かない状態で)。その後、実測値・実音源を開示し、乖離を記録する。
  これがTrack Cの核(他トラックの「署名で真正性を担保」とは違う軸=「予測可能性で
  生成原理の健全さを担保」)。
- 乖離が大きい場合は「失敗」ではなく「生成原理のどこが直感に反しているか」を
  言語化する機会として扱う(uro_3016の boundary数 2-4予測→実測7、の記録がその例)。

## 既存の参照実装

- `life/aow_track_c_sample_uro_3011.json` — 4周目締めの曲(予測なし版)
- `life/aow_track_c_sample_uro_3016.json` — 予測固定→実測照合版(blind audit実践例)
- `life/aow_track_c_sample_uro_3023.json` — 5周目締めの曲(予測なし版、正直な不在の記録)
- `life/aow_track_c_prediction_template.md` — 予測固定のための記入テンプレート

---
_Draft v1, 2026-11-06, uro作成。sami/liv/masumoriのレビュー待ち。_
