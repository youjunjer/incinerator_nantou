# 南投焚化廠場址風險地圖模型

這個版本補上了官方來源整理出的完整敏感點名冊，並保留原本可直接在 GitHub Pages 展示的互動地圖樣本。

目前已整理的官方資料筆數：

- 學校：168
- 醫療機構：422
- 老人機構：15
- 水源地：8
- 合計：613

主要檔案：

- `index.html`：GitHub Pages 展示頁，含風險地圖樣本與官方完整資料查詢區
- `data/official_sources/nantou_sensitive_sites_full.csv`：完整敏感點 CSV
- `data/official_sources/nantou_sensitive_sites_full.json`：完整敏感點 JSON
- `scripts/build_nantou_sensitive_data.py`：從官方來源重建資料的腳本

官方來源：

- 學校：https://sso.ntct.edu.tw/NewPerson/SchoolBase.aspx
- 老人機構：https://data.nantou.gov.tw/dataset/dosa-07
- 醫療機構：https://dep.mohw.gov.tw/doma/fp-4926-54415-106.html
- 水源地：https://wsserver.moenv.gov.tw/Protect_Area_Query.aspx

注意事項：

- 官方名冊多數只提供地址，未附穩定公開座標，因此互動地圖目前仍以樣本敏感點做風險展示。
- 下方完整資料區已可搜尋、篩選與下載全部官方名冊。
- 若後續補上穩定座標，就能把完整 613 筆直接放入地圖計算與顯示。
