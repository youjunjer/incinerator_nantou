from __future__ import annotations

import csv
import io
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd


USER_AGENT = "codex-nantou-sensitive-data/1.0"
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "official_sources"
GEOCODE_CACHE_PATH = OUT_DIR / "geocode_cache_google_maps.json"


def fetch_bytes(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch_text(url: str, encoding: str = "utf-8", *, headers: dict[str, str] | None = None) -> str:
    return fetch_bytes(url, headers=headers).decode(encoding, errors="ignore")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return re.sub(r"\s+", " ", text)


def load_geocode_cache() -> dict[str, dict[str, object]]:
    if GEOCODE_CACHE_PATH.exists():
        return json.loads(GEOCODE_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_geocode_cache(cache: dict[str, dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GEOCODE_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def geocode_query(query: str, cache: dict[str, dict[str, object]]) -> tuple[float | None, float | None, str]:
    query = clean_text(query)
    if not query:
        return None, None, ""

    cached = cache.get(query)
    if cached is not None:
        return cached.get("latitude"), cached.get("longitude"), clean_text(cached.get("method"))

    url = "https://www.google.com/search?" + urllib.parse.urlencode(
        {
            "tbm": "map",
            "hl": "zh-TW",
            "gl": "tw",
            "q": query,
        }
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )

    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read().decode("utf-8", errors="ignore").removeprefix(")]}'\n")
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2 * (attempt + 1))
    else:
        cache[query] = {"latitude": None, "longitude": None, "method": f"error:{type(last_error).__name__}"}
        return None, None, clean_text(cache[query]["method"])

    coord_match = re.search(r"\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]", payload)
    if coord_match:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(2))
        cache[query] = {"latitude": lat, "longitude": lon, "method": "google_maps_result"}
        return lat, lon, "google_maps_result"

    data = json.loads(payload)
    if data and len(data) > 1 and data[1] and data[1][0]:
        center = data[1][0]
        lat = round(float(center[2]), 7)
        lon = round(float(center[1]), 7)
        cache[query] = {"latitude": lat, "longitude": lon, "method": "google_maps_center"}
        return lat, lon, "google_maps_center"

    cache[query] = {"latitude": None, "longitude": None, "method": "no_match"}
    return None, None, "no_match"


def geocode_dataframe(df: pd.DataFrame, query_builder) -> pd.DataFrame:
    cache = load_geocode_cache()
    latitudes: list[float | None] = []
    longitudes: list[float | None] = []
    methods: list[str] = []

    for index, row in df.iterrows():
        query = query_builder(row)
        lat, lon, method = geocode_query(query, cache)
        latitudes.append(lat)
        longitudes.append(lon)
        methods.append(method)
        if (index + 1) % 25 == 0:
            save_geocode_cache(cache)
            time.sleep(0.3)

    save_geocode_cache(cache)
    geocoded_df = df.copy()
    geocoded_df["latitude"] = latitudes
    geocoded_df["longitude"] = longitudes
    geocoded_df["geocode_method"] = methods
    return geocoded_df


def parse_schools() -> pd.DataFrame:
    page_html = fetch_text("https://sso.ntct.edu.tw/NewPerson/SchoolBase.aspx", encoding="utf-8")
    tables = pd.read_html(io.StringIO(page_html), attrs={"id": "GridView1"})
    if not tables:
        raise RuntimeError("Unable to locate Nantou school table.")
    school_df = tables[0].copy()
    school_df.columns = [
        "township",
        "name",
        "principal",
        "address",
        "phone",
        "class_count",
        "student_count",
        "teacher_count",
        "kindergarten_class_count",
        "kindergarten_teacher_count",
        "school_year",
    ]
    school_df["address"] = school_df["address"].str.replace(r"^\[\d+\]", "", regex=True)
    school_df = school_df.apply(lambda col: col.map(clean_text))
    school_df["category"] = "school"
    school_df["source_url"] = "https://sso.ntct.edu.tw/NewPerson/SchoolBase.aspx"
    school_df["source_name"] = "南投縣學校基本資料"
    school_df = geocode_dataframe(school_df, lambda row: f"{row['name']} {row['address']}")
    return school_df[
        [
            "category",
            "name",
            "township",
            "address",
            "phone",
            "principal",
            "class_count",
            "student_count",
            "teacher_count",
            "kindergarten_class_count",
            "kindergarten_teacher_count",
            "school_year",
            "latitude",
            "longitude",
            "geocode_method",
            "source_name",
            "source_url",
        ]
    ]


def parse_eldercare() -> pd.DataFrame:
    csv_text = fetch_text(
        "https://data.nantou.gov.tw/dataset/aebc920f-e512-47c0-bf49-8b679ee8d1d8/resource/4452f43d-e24c-4f9b-a432-29dc6262dd17/download/dosa072.csv",
        encoding="utf-8-sig",
    )
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    records: list[dict[str, str]] = []
    for row in rows:
        normalized = {clean_text(k): clean_text(v) for k, v in row.items()}
        records.append(
            {
                "category": "eldercare",
                "name": normalized.get("機構名稱", ""),
                "ownership": normalized.get("公立/私立", ""),
                "address": normalized.get("機構地址", ""),
                "phone": normalized.get("電話", ""),
                "principal": normalized.get("負責人", ""),
                "service_type": normalized.get("收容對象(安養/養護/長照)", ""),
                "approved_capacity": normalized.get("核定收容人數", ""),
                "bed_count": normalized.get("床位數", ""),
                "license_date": normalized.get("立案日期", ""),
                "source_name": "南投縣老人機構名冊",
                "source_url": "https://data.nantou.gov.tw/dataset/dosa-07",
            }
        )
    eldercare_df = pd.DataFrame.from_records(records)
    eldercare_df = geocode_dataframe(eldercare_df, lambda row: f"{row['name']} {row['address']}")
    return eldercare_df


def parse_ods_first_sheet(url: str) -> pd.DataFrame:
    ns = {
        "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    }
    ods_bytes = fetch_bytes(url)
    with zipfile.ZipFile(io.BytesIO(ods_bytes)) as zf:
        root = ET.fromstring(zf.read("content.xml"))
    spreadsheet = root.find("office:body", ns).find("office:spreadsheet", ns)
    table = spreadsheet.find("table:table", ns)
    rows: list[list[str]] = []
    for row in table.findall("table:table-row", ns):
        expanded: list[str] = []
        for cell in row.findall("table:table-cell", ns):
            repeat = int(cell.attrib.get(f"{{{ns['table']}}}number-columns-repeated", "1"))
            text = "".join((p.text or "") for p in cell.findall(".//text:p", ns))
            expanded.extend([clean_text(text)] * repeat)
        while expanded and expanded[-1] == "":
            expanded.pop()
        if any(expanded):
            rows.append(expanded)

    header = rows[0]
    data_rows = []
    for row in rows[1:]:
        padded = row[: len(header)] + [""] * max(0, len(header) - len(row))
        data_rows.append(padded[: len(header)])
    return pd.DataFrame(data_rows, columns=header)


def parse_medical() -> pd.DataFrame:
    ods_url = "https://www.mohw.gov.tw/dl-96581-66dbb751-f83a-416a-a998-893222e20fef.html"
    medical_df = parse_ods_first_sheet(ods_url)
    medical_df = medical_df[medical_df["縣市區名"].str.startswith("南投縣", na=False)].copy()
    medical_df.rename(
        columns={
            "機構代碼": "institution_code",
            "機構名稱": "name",
            "電話": "phone",
            "縣市區名": "district",
            "地址": "address",
            "科別": "departments",
        },
        inplace=True,
    )
    medical_df["category"] = "medical"
    medical_df["source_name"] = "醫療機構與人員基本資料"
    medical_df["source_url"] = "https://dep.mohw.gov.tw/doma/fp-4926-54415-106.html"
    medical_df["address"] = medical_df["address"].map(clean_text)
    medical_df["name"] = medical_df["name"].map(clean_text)
    medical_df["phone"] = medical_df["phone"].map(clean_text)
    medical_df["district"] = medical_df["district"].map(clean_text)
    medical_df["departments"] = medical_df["departments"].map(clean_text)
    medical_df = geocode_dataframe(medical_df, lambda row: f"{row['name']} {row['address']}")
    return medical_df[
        [
            "category",
            "institution_code",
            "name",
            "district",
            "address",
            "phone",
            "departments",
            "latitude",
            "longitude",
            "geocode_method",
            "source_name",
            "source_url",
        ]
    ]


def parse_kml_centroid(url: str) -> tuple[float | None, float | None]:
    kml_text = fetch_text(url, encoding="utf-8")
    coords = re.findall(r"(-?\d+\.\d+),(-?\d+\.\d+)", kml_text)
    if not coords:
        return None, None
    lon_values = [float(lon) for lon, _ in coords]
    lat_values = [float(lat) for _, lat in coords]
    return round(sum(lat_values) / len(lat_values), 6), round(sum(lon_values) / len(lon_values), 6)


def parse_water_sources() -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for wdata_num in range(26, 34):
        payload = json.dumps({"StrWDataNum": str(wdata_num), "Strptype": "1"}).encode("utf-8")
        req = urllib.request.Request(
            "https://wsserver.moenv.gov.tw/Gmap/getdatatable.asmx/Get_DWPolygon",
            data=payload,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        item = json.loads(data["d"])[0]
        lat, lon = parse_kml_centroid(item["URL"])
        records.append(
            {
                "category": "water_source",
                "name": item["Protect_Area_Name"],
                "admit": item["Admit"],
                "stream_domain": item["Stream_Domain"],
                "water_class": item["Water_Class"],
                "measure_area_hectare": item["Measure_Area"],
                "announce_date_roc": item["Announce_Date"],
                "kml_url": item["URL"],
                "document_pdf_url": item["TEXTURL"],
                "illustration_url": item["JPGpageUrl"],
                "latitude": lat,
                "longitude": lon,
                "geocode_method": "kml_centroid" if lat is not None and lon is not None else "",
                "source_name": "全國飲用水水源水質保護區地理資訊網",
                "source_url": "https://wsserver.moenv.gov.tw/Protect_Area_Query.aspx",
            }
        )
    water_df = pd.DataFrame.from_records(records)
    missing_mask = water_df["latitude"].isna() | water_df["longitude"].isna()
    if missing_mask.any():
        geocoded_water = geocode_dataframe(
            water_df.loc[missing_mask].copy(),
            lambda row: f"{row['name']} {row['stream_domain']} 飲用水水源水質保護區 南投縣",
        )
        water_df.loc[missing_mask, "latitude"] = geocoded_water["latitude"].values
        water_df.loc[missing_mask, "longitude"] = geocoded_water["longitude"].values
        water_df.loc[missing_mask, "geocode_method"] = geocoded_water["geocode_method"].values
    return water_df


def write_outputs(df: pd.DataFrame, basename: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / f"{basename}.csv", index=False, encoding="utf-8-sig")
    (OUT_DIR / f"{basename}.json").write_text(
        df.to_json(orient="records", force_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_summary(datasets: dict[str, pd.DataFrame]) -> None:
    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "counts": {name: int(len(df)) for name, df in datasets.items()},
        "sources": {
            "schools": "https://sso.ntct.edu.tw/NewPerson/SchoolBase.aspx",
            "eldercare": "https://data.nantou.gov.tw/dataset/dosa-07",
            "medical": "https://dep.mohw.gov.tw/doma/fp-4926-54415-106.html",
            "water_sources": "https://wsserver.moenv.gov.tw/Protect_Area_Query.aspx",
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    schools = parse_schools()
    eldercare = parse_eldercare()
    medical = parse_medical()
    water_sources = parse_water_sources()

    write_outputs(schools, "nantou_schools")
    write_outputs(eldercare, "nantou_eldercare")
    write_outputs(medical, "nantou_medical_institutions")
    write_outputs(water_sources, "nantou_water_sources")

    combined = pd.concat(
        [
            water_sources,
            schools,
            eldercare,
            medical,
        ],
        ignore_index=True,
        sort=False,
    )
    write_outputs(combined, "nantou_sensitive_sites_full")
    build_summary(
        {
            "schools": schools,
            "eldercare": eldercare,
            "medical": medical,
            "water_sources": water_sources,
            "combined": combined,
        }
    )


if __name__ == "__main__":
    main()
