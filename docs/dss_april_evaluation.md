# RF refit Q1 và kiểm chứng tháng 4/2024

Cập nhật 28/10/2026: RF refit đã được publish cho demo lịch sử 01/04/2024,
run `90e17b55-0c16-44c8-8744-509dc0562dea` (6.312 forecast rows). Metadata
selection và actual fit được lưu riêng, giữ nguyên artifact và mọi run cũ.
Xem [migration → publish → dashboard](dss_refit_publication_runbook.md).
Các mô tả "offline" bên dưới ghi lại trạng thái tại lượt thí nghiệm ban đầu.

## Kết quả tháng mới

Train thêm toàn bộ March giúp RF cải thiện nhẹ trên April so với RF cũ: WAPE giảm **0,456 điểm phần trăm** (giảm tương đối 2,49%). RF refit tốt hơn D−7 rõ hơn, nhưng chỉ nhỉnh hơn weekday median **0,196 điểm phần trăm**. Đây là kết quả trên tháng mới, không dùng để chọn lại model.

Đánh giá gồm **189.360 dòng = 30 ngày × 24 giờ × 263 zone**, tổng **3.440.679 pickup hợp lệ trong eligible zones**. Chênh 12.512 so với 3.453.191 valid trips toàn April là các zone ngoài universe eligible. Mọi phương pháp dùng chính xác cùng các dòng.

| Phương pháp | MAE | RMSE | WAPE |
|---|---:|---:|---:|
| RF refit Q1 | 3.2465 | 10.2719 | 17.8673% |
| RF cũ | 3.3294 | 10.7215 | 18.3237% |
| D−7 | 3.9698 | 13.1152 | 21.8478% |
| Weekday median | 3.2822 | 10.8182 | 18.0636% |

Cải thiện tổng đến từ Manhattan, nơi chiếm **89,43% actual** trong tập đánh giá. WAPE refit ở Manhattan giảm từ 16,59% xuống 16,01%. Ở cả năm borough còn lại, RF refit có WAPE kém RF cũ; weekday median cũng tốt hơn RF refit ở các borough này. Vì vậy không thể kết luận train thêm giúp đồng đều mọi nơi.

Staten Island chỉ có **103 pickup trên 14.400 ô**. RF refit dự báo tổng khoảng 879 pickup, nên WAPE lên 936,96%; đây là sai số thật trên nền actual rất nhỏ, không phải lỗi tính phần trăm. MAE nhỏ ở borough ít pickup không đồng nghĩa model phù hợp vận hành.

### Chi tiết theo borough

| Borough | Phương pháp | MAE | RMSE | WAPE |
|---|---|---:|---:|---:|
| Bronx | RF refit Q1 | 0.4090 | 0.6634 | 118.52% |
| Bronx | RF cũ | 0.4030 | 0.6636 | 116.77% |
| Bronx | D−7 | 0.4403 | 0.8952 | 127.60% |
| Bronx | Weekday median | 0.3562 | 0.7194 | 103.22% |
| Brooklyn | RF refit Q1 | 0.7975 | 1.4819 | 78.36% |
| Brooklyn | RF cũ | 0.7877 | 1.4732 | 77.40% |
| Brooklyn | D−7 | 0.9098 | 1.8857 | 89.39% |
| Brooklyn | Weekday median | 0.7532 | 1.5526 | 74.01% |
| EWR | RF refit Q1 | 0.6504 | 1.1162 | 94.03% |
| EWR | RF cũ | 0.6461 | 1.1180 | 93.41% |
| EWR | D−7 | 0.7681 | 1.4371 | 111.04% |
| EWR | Weekday median | 0.6097 | 1.1978 | 88.15% |
| Manhattan | RF refit Q1 | 9.9159 | 18.7659 | 16.01% |
| Manhattan | RF cũ | 10.2734 | 19.7440 | 16.59% |
| Manhattan | D−7 | 12.2996 | 24.0632 | 19.86% |
| Manhattan | Weekday median | 10.1454 | 19.8051 | 16.38% |
| Queens | RF refit Q1 | 1.4697 | 6.9116 | 23.72% |
| Queens | RF cũ | 1.4420 | 6.7901 | 23.27% |
| Queens | D−7 | 1.7377 | 8.5387 | 28.05% |
| Queens | Weekday median | 1.4659 | 7.1673 | 23.66% |
| Staten Island | RF refit Q1 | 0.0670 | 0.1062 | 936.96% |
| Staten Island | RF cũ | 0.0625 | 0.1038 | 874.35% |
| Staten Island | D−7 | 0.0135 | 0.1208 | 188.35% |
| Staten Island | Weekday median | 0.0078 | 0.0903 | 109.71% |

### Ranking: mức tập trung pickup

Cả hai case dùng cùng **69 zone Manhattan**, đúng K=10, cùng ngày và cùng khoảng giờ. Share gộp = tổng actual trong các top K hằng ngày / tổng actual trong candidate universe; đó không phải share trung bình ngày. Trung bình chênh lệch ngày cho mỗi ngày trọng số bằng nhau. Win/tie/loss so bằng số pickup thực tế được top K bao phủ.

| Khoảng giờ | RF share gộp | D−7 share gộp | Chênh gộp (điểm %) | Chênh trung bình ngày (điểm %) | Win / tie / loss |
|---|---:|---:|---:|---:|---:|
| [08,09) | 42.3402% | 42.1909% | +0.1492 | +0.0815 | 16 / 5 / 9 |
| [06,10) | 42.4569% | 42.3912% | +0.0658 | +0.0534 | 12 / 6 / 12 |

[08,09): RF bao phủ 50.497 pickup so với D−7 50.319, trên tổng 119.265; chênh 178 pickup trong cả tháng. [06,10): 159.472 so với 159.225, trên tổng 375.609; chênh 247 pickup. Hai cửa sổ chồng nhau, không cộng các chênh lệch này thành một hiệu quả tổng.

RF chỉ nhích rất ít về pickup concentration. Case nhiều giờ có số ngày thắng bằng số ngày thua (12/12); chưa có bằng chứng RF luôn xếp hạng tốt hơn D−7. Không suy ra hiệu quả điều xe hoặc nhu cầu chưa được phục vụ, và không có kiểm định ý nghĩa thống kê trong thí nghiệm này.

Kết quả đầy đủ, gồm 60 đánh giá ngày–case với zone IDs, support và share của cả hai phương pháp, ở `ranking_daily` trong report JSON. Mỗi case có đủ 30 ngày, không chọn bỏ ngày xấu.

### Kết quả local để kiểm tra lại

- Report JSON: `artifacts/models/dss-rf-q1-refit-85dc57ba-5016-4b87-b34c-0278cb5e3ac1/april-2f21ebdf-3b54-4add-9612-0f88f4bfe19a/report.json`.
- Metrics tổng và borough: `artifacts/models/dss-rf-q1-refit-85dc57ba-5016-4b87-b34c-0278cb5e3ac1/april-2f21ebdf-3b54-4add-9612-0f88f4bfe19a/metrics.csv`.
- Predictions và features từng dòng: `artifacts/models/dss-rf-q1-refit-85dc57ba-5016-4b87-b34c-0278cb5e3ac1/april-2f21ebdf-3b54-4add-9612-0f88f4bfe19a/predictions.parquet`.
- History/actual snapshot: `artifacts/models/dss-rf-q1-refit-85dc57ba-5016-4b87-b34c-0278cb5e3ac1/april-2f21ebdf-3b54-4add-9612-0f88f4bfe19a/history-actual.parquet`.
- Log chấm điểm: `artifacts/april-evaluation.log`. File report ghi checksum inputs/outputs và evaluation source snapshot. Toàn bộ dense Q1 sau rebuild đã được đối chiếu **giống hệt** snapshot trước ingestion.

## Câu hỏi và thiết kế

Thí nghiệm kiểm tra RF đã chọn từ validation Q1 có dự báo được tháng mới sau
khi học thêm toàn bộ March hay không. Cấu hình được giữ cố định; April không
tham gia chọn model, chỉnh tham số, chọn K hoặc khoảng giờ. Chi tiết được chốt
trước khi nạp April tại [protocol](dss_april_protocol.md).

Selection cũ vẫn là train 29/01–29/02 và validation 01–15/03. Model mới fit
29/01–31/03, gồm **397.656 dòng = 63 ngày × 24 giờ × 263 zone**, với tổng
6.743.971 pickup hợp lệ. January 1–28 cung cấp lịch sử. March đã là dữ liệu fit,
không còn là test. Không refit hằng ngày trong April.

Mỗi dự báo ngày D dùng lag/rolling tính từ actual đến D−1. Vì vậy đây là kiểm
chứng day-ahead liên tiếp, có cập nhật lịch sử quan sát, không phải dự báo toàn
bộ tháng từ một thời điểm 31/03. Tests đối chiếu cách tính theo lô với forecast
từng ngày D−1 và kiểm tra thay đổi target D/future không làm đổi features D.
Thí nghiệm giả định actual hoàn chỉnh đến cuối D−1 đã sẵn có; chưa kiểm chứng
độ trễ dữ liệu/ingestion trong vận hành thực tế.

## Artifact và metadata

- Parent: `artifacts/models/dss-rf-9a687651-d038-4f06-8ec2-1bbaa5946f3a.joblib`.
- Refit: `artifacts/models/dss-rf-q1-refit-85dc57ba-5016-4b87-b34c-0278cb5e3ac1/model.joblib`.
- SHA256 refit: `aa5c658291adb69ee3fa815681a9c4707b45cc605f08a9750c98ea92ea5f84ed`.
- Fit 337,52 giây trên máy hiện tại; không phải cam kết hiệu năng.
- Cùng thư mục có manifest, Q1 parquet, universe snapshot, coverage, audit và
  snapshot source. Source lúc chạy chưa commit; HEAD 72f4c87. Mọi thay đổi về
  code đánh giá sau refit được snapshot riêng khi đánh giá.

Artifact giữ selection config/validation gốc và ghi `fit_start_date`,
`fit_end_date`, `experiment_metadata.actual_fit` riêng. RF refit là model dùng
để dự báo. Gradient boosting còn trong parent để bảo toàn lịch sử, không được
fit hay lựa chọn lại trong thí nghiệm này. Dữ liệu khuyến nghị p50/p75 được tính
lại trên cùng fit window; ranking ở đây chỉ dùng tổng dự báo, không dùng nhãn.

Tại lượt thí nghiệm ban đầu, kết quả giữ offline. `run_forecast` từ chối publish refit vào schema Gate C cũ
vì schema đó biểu diễn selection train/validation, chưa biểu diễn đúng refit.
Không sửa CHECK, không tạo split giả và không đổi dashboard. Các artifact/run
cũ được giữ nguyên và đối chiếu checksum.

## Nạp dữ liệu

April dùng downloader/validator/ingestion sẵn có, không nạp lại Q1.
Nguồn `yellow_tripdata_2024-04.parquet`: 59.133.625 bytes, 3.514.289 dòng,
SHA256 `ce37f736c7cf9e92164c850ef2b502a8f7bb590fc1804b6edbcb80293da01b89`.
Batch: `2e721e6f-16de-46fb-8f30-e6cb7477fa6a`.

Staging phân loại 3.453.191 valid, 61.028 quarantined, 70 rejected. Audit
reconciliation đã kiểm tra source = loaded = RAW = staging và tổng ba nhóm DQ
cho đủ bốn tháng trước khi ghi counts. Staging build 2/2 model thành công,
không warning/error, trên 13.069.067 dòng RAW. Logs đầy đủ nằm tại
`artifacts/april-download.log`, `april-validation.log`, `april-ingestion.log`,
`april-dbt-staging.log`, `april-staging-audit.log`.

## Xác minh thực tế của lượt chạy

- Staging: **2 passed**, 0 warn/error/skip; DW/mart: **8 passed**, 0 warn/error/skip.
- Full dbt test: **99 passed** (98 data tests, 1 unit test), **0 skipped**,
  0 warning/error, 702,18 giây. Log `artifacts/april-dbt-tests.log`; bản lưu
  run results `artifacts/april-dbt-test-results.json`.
- Full Python discovery đúng lệnh yêu cầu, bật cả `RUN_DB_TESTS=1` và
  `RUN_ANALYTICS_TESTS=1`: **129 passed, 0 skipped**, 295,594 giây.
  Log `artifacts/april-full-tests.log`. Bảy tests mới bao phủ fit window,
  future/target leakage, rolling-origin so với forecast từng ngày, thiếu ô hoặc
  thiếu cả zone, round trip artifact và chặn metadata publication sai.
- Toàn bộ dense Q1 sau rebuild giống hệt snapshot Q1 trước ingestion. Cả
  189.360 evaluation rows và 60 đánh giá ranking ngày–case có đủ support;
  mỗi case/ngày có 69 candidate zones và đúng 10 IDs mỗi phương pháp.
- SHA256 model refit, cả 4 artifact cũ, input snapshots, source snapshots và
  các output evaluation đều đã được xác minh. Evaluation source snapshot
  khớp code hiện tại; source refit gốc được giữ riêng, không thay lịch sử chạy.
- Metadata và checksum tất cả forecast của các run DSS cũ giống hệt trước
  ingestion, kể cả sau integration tests. Các fixtures đã cleanup: audit còn
  đúng **21 attempts** (20 cũ + 1 April), RAW chỉ có bốn tháng với counts
  2.964.624 / 3.007.526 / 3.582.628 / 3.514.289; không còn DB test tạm.
  Bằng chứng: `artifacts/april-final-db-verification.log` và hai file
  `artifacts/april-old-dss-before.txt`, `artifacts/april-old-dss-after.txt`.
- Backup giữ nguyên SHA256
  `6ff5c3ae3af9e3677735765cd072b05d87e079c5435cca9931dbcf23bc596e7b`.
- D từ 55,57 GiB free ban đầu xuống **29,81 GiB free** cuối lượt chạy;
  mức thấp nhất trong các lần đo là 29,81 GiB. Theo dõi khi staging,
  warehouse/mart, dbt tests và integration tests trong `artifacts/april-storage.log`.
  Không xóa volume, không compact VHDX hoặc động vào backup.
- `git diff --check` không lỗi. `.env`, RAW, artifacts, tmp và guide local
  không nằm trong tracked files. Chỉ thay source/tests/docs; **chưa commit,
  push hoặc PR**. Refit/evaluation giữ offline, không tạo run DSS mới.

## Cách tái lập

Từ repository root, sau khi PostgreSQL khỏe:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OMP_NUM_THREADS = '2'
# Chỉ tạo model mới nếu muốn chạy lại refit; không cần cho việc đọc lại kết quả.
.\.venv\Scripts\python.exe scripts/evaluate_dss_april.py refit

# Quy trình ingestion hiện có, riêng April; không backfill lại Q1.
.\.venv\Scripts\python.exe -m taxi_dw.downloader --year 2024 --month 4
.\.venv\Scripts\python.exe -m taxi_dw.source_validation --year 2024 --month 4
.\.venv\Scripts\python.exe -m taxi_dw.ingestion run --dataset yellow_taxi --year 2024 --month 4 --batch-size 10000
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe run --project-dir src/dbt --profiles-dir src/dbt --select staging
.\.venv\Scripts\python.exe -m taxi_dw.staging_audit
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe run --project-dir src/dbt --profiles-dir src/dbt --select warehouse marts
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe test --project-dir src/dbt --profiles-dir src/dbt

.\.venv\Scripts\python.exe scripts/evaluate_dss_april.py evaluate --artifact artifacts/models/dss-rf-q1-refit-85dc57ba-5016-4b87-b34c-0278cb5e3ac1/model.joblib
$env:RUN_DB_TESTS = '1'
$env:RUN_ANALYTICS_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Mỗi lần refit/evaluate tạo đường dẫn mới; evaluate model đã có không fit lại.
Nếu dùng artifact refit khác, thay đường dẫn trong lệnh. Protocol phải giữ
nguyên checksum. Khi dbt rebuild toàn bảng, cần đủ chỗ cho cả bảng cũ, bảng
mới, index, temporary files và WAL; kiểm tra ổ D giữa các mốc. RAW ingestion
tháng đã nạp đúng checksum sẽ skip, không append trùng.

## Giới hạn diễn giải

Các metrics tính trên dense grid 263 eligible zones, gồm zero demand, sau DQ;
không phải mọi chuyến RAW hoặc zone 264/265. MAE/RMSE là pickup mỗi zone-hour;
WAPE chia tổng sai số tuyệt đối cho tổng actual, không trung bình phần trăm
từng ô. So sánh RF parent cùng April rows chỉ mô tả tác động của refit, không
thay đổi quyết định model đã chốt.

Ranking đo tỷ lệ pickup thực tế tập trung trong đúng K zone được chọn trước
khi đối chiếu actual. Nó không đo lợi nhuận, thời gian chờ, số taxi cần bổ sung,
hiệu quả điều xe hoặc nhu cầu chưa được phục vụ. Chỉ một tháng mới và hai
case Manhattan được chốt trước; không có kiểm định nhân quả hay đảm bảo
tổng quát hóa sang mùa/năm khác. Universe là dimension hiện tại được snapshot,
không phải một hệ thống eligibility versioning theo lịch sử.
