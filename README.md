# 南投焚化廠場址風險地圖模型

這個 repository 用於展示「南投縣焚化廠場址選擇與敏感點健康風險」互動地圖模型。

模型重點：

- 可在地圖上點選或拖曳焚化爐候選場址。
- 場址移動後會重新估算周邊敏感點嚴重程度。
- 敏感點以南投縣全縣設施為基礎，不只名間鄉。
- 敏感點只在設定場址 10 公里範圍內顯示。
- 場址建議指數會納入敏感設施密度、最近敏感點、醫療設施、嚴重程度，以及集水區/水體鄰近性。

本機完整展示檔位於：

```text
C:\Users\user\Documents\Codex\2026-05-26\new-chat\github-demo
```

主要檔案：

- `index.html`：互動地圖展示頁
- `sensitive-sites.js`：南投縣敏感點資料
- `sensitive-sites.json`：敏感點 JSON 資料
- `data-sources.csv`：資料來源表
- `nantou-incinerator-site-risk-map.pptx`：展示簡報

資料與模型僅供政策討論、場址初篩與展示使用，不等同正式環評、流行病學因果推論或空污擴散模擬結果。
