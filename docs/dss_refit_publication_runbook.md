# Publish RF refit Q1 vào PostgreSQL và dashboard

Thực hiện từ `D:\nyc-taxi-dw-dss`, branch `feature/publish-rf-q1-refit`, base
`develop` tại `6ca636c`. Không cần ingestion, dbt rebuild, train hoặc refit.
Đây là demo lịch sử 01/04/2024: actual April đã có, không phải forecast tương lai
chưa biết actual. April không tham gia chọn model, tham số, K hoặc rule ranking.

## Metadata

| Trường | Ý nghĩa |
|---|---|
| `train_start_date`, `train_end_date` | Selection train gốc: 29/01–29/02 |
| `validation_start_date`, `validation_end_date` | Selection validation gốc: 01–15/03 |
| `fit_kind` | `selection` cho model chưa refit; `refit` cho RF đã refit |
| `fit_start_date`, `fit_end_date` | Dữ liệu fit thực tế: 29/01–31/03 cho RF refit |
| `fit_seconds` | Thời gian fit ghi trong artifact: 337,5229522 giây; không phải thời gian publish |
| `artifact_sha256` | Định danh nội dung artifact, dùng kiểm tra và tái sử dụng run |
| `metrics_json.selection_validation` | Metrics chọn model gốc, không phải validation lại RF refit |

Các run cũ nhận mặc định `fit_kind=selection`, giữ NULL cho thông tin fit chưa
được lưu; dashboard dùng train window gốc khi fit window NULL và không bịa thời
gian fit. `metrics_json.validation` của run cũ vẫn đọc được. CHECK
`train_end_date < validation_start_date` giữ nguyên. Refit phải bao gồm selection
train/validation, forecast phải sau cả actual fit end và selection validation end.

Artifact và manifest được giữ nguyên byte. `metrics_json.experiment` bảo toàn
provenance thí nghiệm gốc, kể cả nhãn `publication: offline only` tại thời điểm
tạo artifact; nhãn đó không mô tả trạng thái DB hiện tại. Trạng thái fit hiện
tại được biểu diễn bằng các cột riêng ở trên. March đã là fit data; không gọi
March là holdout của RF refit.

## 1. Kiểm tra và migration

Kiểm tra Git, dung lượng và PostgreSQL trước khi chạy. Không xóa/recreate volume.
Backup giữ nguyên ở `D:\DockerBackups\2026-10-27\nyc_taxi_dw.dump`.

```powershell
Set-Location D:\nyc-taxi-dw-dss
git status --short --branch
Get-PSDrive D,C | Select-Object Name,Free
docker compose ps -a
# Khởi động Docker Desktop trước nếu engine chưa chạy.
docker compose start postgres
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/004_dss_actual_fit.sql'
```

`004` thêm cột, CHECK và index trong transaction, chạy lại an toàn; không cập
nhật forecast hoặc metadata selection của run cũ. Bootstrap `003` gọi cùng
`004` bằng `\ir`; lần Docker init chạy `004` kế tiếp vẫn an toàn. Database hiện
có chỉ cần chạy `004`, không cần chạy lại bootstrap hoặc rebuild DW.

## 2. Publish artifact có sẵn

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OMP_NUM_THREADS = '2'
$rfArtifact = 'artifacts/models/dss-rf-q1-refit-85dc57ba-5016-4b87-b34c-0278cb5e3ac1/model.joblib'
Get-FileHash -Algorithm SHA256 $rfArtifact
.\.venv\Scripts\python.exe -m dss.pipeline forecast --artifact $rfArtifact --date 2024-04-01
```

Local demo đã mở rộng tới đủ ngày 01–30/04/2024. Mỗi ngày dùng cùng RF
refit và lịch sử thực tế đến D−1; không train lại. Để tái tạo cả tháng trên
database đã có đủ mart tháng 3–4, dùng CLI ở trên cho từng ngày:

```powershell
1..30 | ForEach-Object {
    $forecastDay = '2024-04-{0:00}' -f $_
    .\.venv\Scripts\python.exe -m dss.pipeline forecast --artifact $rfArtifact --date $forecastDay
    if ($LASTEXITCODE -ne 0) { throw "Publication failed: $forecastDay" }
}
```

Run cùng artifact/ngày và nội dung được tái sử dụng; run cũ được giữ nguyên.
Đây là demo lịch sử, không phải dự báo thực hiện trước khi tháng 4 xảy ra.
Chọn **Reload forecasts** trên dashboard để tải danh sách ngày mới.

SHA256 phải là
`aa5c658291adb69ee3fa815681a9c4707b45cc605f08a9750c98ea92ea5f84ed`.
CLI đối chiếu checksum với manifest, metadata selection và metadata RF actual
fit trước khi publish. Manifest là bằng chứng cục bộ, không phải chữ ký số;
joblib chỉ dùng từ nguồn local đáng tin và môi trường Python/sklearn tương thích.

Pipeline đọc đủ 28 ngày lịch sử 04–31/03, kết thúc đúng D−1, kiểm tra đầy đủ
zone-hour và dự báo 24 giờ × 263 zone. Metadata cùng toàn bộ 6.312 forecast
rows được ghi trong transaction hiện có. Không dùng actual 01/04 làm feature.

Run được tái sử dụng khi cùng SHA256/ngày và metadata cùng mọi forecast cell
khớp (cho phép sai khác số thực rất nhỏ do RF đa luồng). Advisory transaction
lock theo SHA256 ngăn hai publisher tạo trùng cùng lúc. Nếu run cùng artifact/ngày
khác metadata hoặc forecast, lệnh báo lỗi để kiểm tra; không overwrite hoặc
tiếp tục tạo bản trùng. API cũ không truyền SHA256 vẫn hoạt động; muốn có cơ chế
tái sử dụng phải truyền hash đã kiểm chứng hoặc dùng CLI.

## 3. Đối soát và tests

```powershell
$offlinePredictions = 'artifacts/models/dss-rf-q1-refit-85dc57ba-5016-4b87-b34c-0278cb5e3ac1/april-2f21ebdf-3b54-4add-9612-0f88f4bfe19a/predictions.parquet'
.\.venv\Scripts\python.exe scripts/verify_dss_publication.py --artifact $rfArtifact --date 2024-04-01 --predictions $offlinePredictions
$env:RUN_DB_TESTS = '1'
$env:RUN_ANALYTICS_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
git diff --check
```

Verification script chỉ đọc: kiểm tra checksum offline, đúng latest run của UI,
6.312 unique zone-hour, 263 eligible zones, số hữu hạn/không âm, predictions RF
và D−7 so với offline. Đối chiếu tổng ranking RF/D−7 từng zone với SQL độc lập
cho `[8,9)` và `[6,10)` ở cả sáu borough. Sai khác tối đa RF chấp nhận
`atol=1e-10`, `rtol=1e-12` vì thứ tự cộng đa luồng.

Integration tests dùng transaction rollback hoặc cleanup fixture sẵn có;
không lưu run thử trong DB. Full suite có các bài train/refit trên fixture nhỏ
để kiểm tra code, không train/refit artifact Q1 thật.

## 4. Mở dashboard

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Mở <http://127.0.0.1:8501>, chọn **Dự báo & khuyến nghị → 01/04/2024 →
Manhattan**. `[8,9)` xem một giờ; `[6,10)` xem bốn giờ; end exclusive,
giờ địa phương New York. Ranking vẫn theo tổng pickup dự báo trong cùng borough.
Nhãn High/Medium/Low là chi tiết zone-hour, không quyết định thứ tự ranking.

Mỗi ngày dùng run mới nhất theo `created_at DESC, run_id DESC`; không ưu tiên
RF chỉ vì tên thuật toán. Metadata, metrics và rows của một lần render dùng
cùng run ID, không cache snapshot cũ 5 phút. Run cũ vẫn đọc được theo UUID;
ngày 16/03 vẫn hiển thị run RF chưa refit. Nếu publish run khác mới hơn cùng
ngày, UI sẽ hiển thị run đó. Không có màn hình chọn run riêng.

Phần validation ghi rõ là selection của model gốc. Kết quả April nằm trong
expander **Đánh giá lịch sử tháng 4/2024**, tách khỏi forecast đang lọc:
WAPE refit 17,87%, RF cũ 18,32%, median 18,06%, D−7 21,85%. Đây là kiểm
chứng lịch sử, không phải khoảng tin cậy hoặc đánh giá của cửa sổ đang chọn.
Ranking chỉ nhích nhẹ về pickup concentration; không chứng minh hiệu quả điều xe.
Các giá trị lịch sử này tóm tắt thí nghiệm cố định trong
[báo cáo April](dss_april_evaluation.md), không tự tính lại theo bộ lọc.

## Kết quả local 28/10/2026

- Artifact/manifest, các file trong manifest và source snapshot đã đối chiếu;
  bốn artifact cũ giữ checksum. Backup SHA256:
  `6ff5c3ae3af9e3677735765cd072b05d87e079c5435cca9931dbcf23bc596e7b`.
- Run mới: `90e17b55-0c16-44c8-8744-509dc0562dea`, 01/04/2024, 6.312 rows.
  Chạy lại CLI trả cùng run ID. Chênh lớn nhất với offline `5.6843e-14`.
- Migration chạy hai lần thành công; regression cho upgrade chạy hai lần,
  giữ metadata cũ, giữ CHECK selection, chặn NaN/Infinity và malformed hash.
- Full Python discovery bật cả `RUN_DB_TESTS=1` và `RUN_ANALYTICS_TESTS=1`:
  **140 passed, 0 skipped**, 312,517 giây. Log cuối:
  `tmp/rf-publication/full-tests-final.log`. Lượt đầu phát hiện hai subcase của
  một regression do thông báo chặn ngày legacy thay đổi; đã giữ lại thông báo
  selection validation cũ và chạy lại toàn bộ suite thành công. `compileall`
  và `git diff --check` cũng qua; cảnh báo LF/CRLF của Git không phải lỗi diff.
- Live DB AppTest: đúng run refit, 69 Manhattan zones, 276 detail rows trong
  `[6,10)` và 69 trong `[8,9)`; ngày 16/03 vẫn đọc run cũ. Đã kiểm tra trực
  quan dashboard trong browser; bố cục hiện có và các nhãn fit/selection/demo
  hiển thị đúng. Screenshot và log trong `tmp/rf-publication/` (gitignored).
- Cả bốn run cũ giữ nguyên mọi trường metadata gốc và checksum forecast;
  repository vẫn đọc đủ 6.312 rows mỗi run. DB có đúng năm run, chỉ một run
  cho SHA256 refit/ngày 01/04. Hai artifact pre-GLM và RF selection cũ đều
  load/forecast in-memory đủ 6.312 rows; artifact GLM lưu trữ vẫn bị từ chối
  theo chính sách cũ, trong khi kết quả DB của nó vẫn đọc được.
- Sau full suite: audit vẫn đúng 21 attempts, không còn schema test DSS;
  DB vẫn đúng năm run và checksum các forecast cũ không đổi. Ổ D cuối lượt
  còn khoảng 29,56 GiB; backup SHA256 đối chiếu lại vẫn giữ nguyên.
- Chưa commit/push/PR. Không sửa protocol cố định hoặc artifact thí nghiệm;
  không ingestion/rebuild/refit dữ liệu thật. Dung lượng D đầu lượt: 29,56 GiB.

## Phạm vi file thay đổi

- `src/dss/models.py`: fit window và loader kiểm chứng manifest khi publish.
- `src/dss/pipeline.py`: cho phép refit publication, kiểm tra history và metadata.
- `src/dss/persistence.py`: ghi thêm actual fit, kiểm tra ngày và tái sử dụng run.
- `src/dss/service.py`: snapshot theo một run ID.
- `src/dashboard/app.py`: nhãn fit/selection, demo và đánh giá lịch sử.
- `sql/003_create_dss_tables.sql`, `sql/004_dss_actual_fit.sql`: bootstrap và upgrade.
- `scripts/verify_dss_publication.py`: kiểm chứng offline/SQL, chỉ đọc DB.
- `tests/dss/test_publication.py`, `tests/integration/test_dss_publication.py`:
  regression publication và migration.
- `tests/dss/test_refit.py`, `tests/dss/test_service.py`,
  `tests/dss/test_dashboard_ranking.py`: ngày chặn refit, snapshot và AppTest.
- `docs/dss_april_evaluation.md`, `docs/dss_forest_zone_ranking.md`, tài liệu này:
  trạng thái publication, quy trình và giới hạn diễn giải.
