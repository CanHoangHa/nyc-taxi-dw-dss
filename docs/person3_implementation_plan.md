# Kế hoạch hiện thực Person 3 - DSS và ứng dụng dự báo

## 1. Mục đích và trạng thái

Tài liệu này là kế hoạch hiện thực chi tiết cho Person 3, dựa trên trạng thái
`origin/develop` tại commit `3e0d4cd` ngày 09/10/2026.

Phạm vi Person 3 bắt đầu tại Gate B:

```text
mart.mart_zone_hour_demand
  -> kiểm tra coverage
  -> tạo dense date-hour-zone grid
  -> feature engineering không leakage
  -> baseline và mô hình dự báo
  -> đánh giá theo thời gian
  -> demand level
  -> recommendation
  -> lưu kết quả Gate C
  -> Streamlit DSS view
```

Person 3 không sở hữu RAW ingestion, staging classification, dimensions hoặc
`fact_trip`. Các thay đổi cần thiết ở những phần này phải được thảo luận và giao
lại đúng owner thay vì để DSS phụ thuộc trực tiếp vào tầng thấp hơn.

## 2. Kết quả review đầu vào

### 2.1 Gate A - Person 1 đến Person 2

Gate A đã được hiện thực và có evidence cho January-March 2024:

- Download file Parquet theo tháng từ nguồn TLC.
- Kiểm tra filename, checksum, Parquet footer, schema và physical type.
- Nạp RAW bằng Psycopg COPY theo RecordBatch, không giữ toàn bộ file trong RAM.
- Ghi batch metadata và source lineage.
- Chạy lại cùng checksum được đánh dấu `skipped` và không tạo dữ liệu trùng.
- Checksum khác với tháng đã thành công bị từ chối an toàn.
- RAW load là transaction toàn tháng; lỗi không để lại batch RAW một phần.
- Staging chuẩn hóa tên và kiểu dữ liệu.
- Mỗi RAW row được phân loại đúng một trạng thái `valid`, `quarantined` hoặc
  `rejected`.
- `staging.stg_yellow_trip_valid` là interface chính thức cho warehouse.
- January-March đã được đối soát theo batch.

Person 3 không đọc trực tiếp Gate A. Chất lượng Gate A ảnh hưởng gián tiếp đến
forecast thông qua các chuyến hợp lệ được đưa vào warehouse.

### 2.2 Gate B - Person 2 đến Person 3

Gate B đã được hiện thực dưới dạng bảng:

```text
mart.mart_zone_hour_demand
```

Grain:

```text
New York local pickup date x pickup hour x pickup taxi zone
```

Các trường hiện có:

| Field | Type | Ý nghĩa |
|---|---|---|
| `demand_date` | `date` | Ngày đón theo giờ địa phương New York |
| `demand_hour` | `smallint` | Giờ đón từ 0 đến 23 |
| `pickup_zone_key` | `text` | Surrogate key của `dw.dim_taxi_zone` |
| `pickup_location_id` | `integer` | TLC LocationID ổn định về nghiệp vụ |
| `borough` | `text` | Borough của pickup zone |
| `zone_name` | `text` | Tên pickup zone |
| `trip_count` | `bigint` | Số chuyến hợp lệ trong grain |

Mart hiện là sparse table: chỉ tổ hợp có ít nhất một chuyến mới xuất hiện.
Trong một tháng đã nạp và build hoàn chỉnh, tổ hợp không có dòng được hiểu là
zero chuyến hợp lệ. Ngoài tháng đã nạp, không có dòng nghĩa là chưa có dữ liệu,
không phải zero.

Evidence hiện tại ghi nhận:

| Tháng | Valid/fact rows | Mart rows | Tổng `trip_count` |
|---|---:|---:|---:|
| 01/2024 | 2.924.187 | 77.427 | 2.924.187 |
| 02/2024 | 2.964.028 | 74.278 | 2.964.028 |
| 03/2024 | 3.520.696 | 88.849 | 3.520.696 |
| Tổng | 9.408.911 | 240.554 | 9.408.911 |

Gate B đủ để bắt đầu prototype DSS. Full-year data và coverage interface rõ
ràng vẫn cần được hoàn thiện trước đánh giá cuối.

## 3. Các quyết định phải khóa trước khi hiện thực

### 3.1 Forecast issue time

Định nghĩa đề xuất:

> Forecast cho toàn bộ 24 giờ của ngày D được tạo sau khi dữ liệu đến 23:59 của
> ngày D-1 đã sẵn sàng.

Hệ quả:

- Chỉ dùng dữ liệu target từ ngày D-1 trở về trước.
- Không dùng trip count của giờ trước trong chính ngày D.
- Feature theo lịch như ngày trong tuần, tháng và cuối tuần được biết trước.
- Feature thời tiết hoặc sự kiện không thuộc scope ban đầu nếu chưa có nguồn và
  contract rõ ràng.

### 3.2 Coverage policy

Person 3 chỉ được điền zero trong các tháng được xác nhận đã:

1. Nạp RAW thành công.
2. Staging/test/reconciliation thành công.
3. Rebuild warehouse và mart thành công.

Không suy luận coverage chỉ từ `min(demand_date)` và `max(demand_date)`.

Person 2 đã hiện thực interface coverage:

```text
mart.mart_demand_coverage
```

Schema tối thiểu đề xuất:

| Field | Ý nghĩa |
|---|---|
| `source_year` | Năm nguồn |
| `source_month` | Tháng nguồn |
| `coverage_start_date` | Ngày đầu tháng |
| `coverage_end_date` | Ngày cuối tháng |
| `valid_trip_count` | Số fact rows thuộc tháng |
| `mart_trip_count` | Tổng `trip_count` trong mart thuộc tháng |

View này chỉ xuất một tháng khi audit classification count, `fact_trip` và tổng
mart của tháng khớp nhau. Person 3 phải đọc view này làm bằng chứng zero-fill,
không hard-code complete months và không suy luận từ min/max của demand mart.

### 3.3 Zone policy

- Loại synthetic unknown member khỏi toàn bộ DSS dataset.
- Zone 264 (`N/A`) và 265 (`Outside of NYC`) vẫn được giữ cho reconciliation.
- Không phát recommendation điều phối taxi cho zone 264 và 265.
- Default actionable zones là TLC LocationID 1-263.
- Nếu loại thêm zone ít hoạt động, threshold phải được học chỉ từ training data
  và được tài liệu hóa.

### 3.4 Stable entity identifier

- Dùng `pickup_location_id` làm entity ID ổn định trong feature/model.
- Giữ `pickup_zone_key` để join với warehouse và ghi output.
- Không dùng thứ tự row hoặc category code phát sinh ngẫu nhiên làm zone ID.

### 3.5 Prototype và final evaluation

- January-March chỉ dùng để xây vertical slice và xác minh pipeline.
- Kết quả Q1 không được trình bày như kết quả cuối của đề tài full-year.
- Final model selection/evaluation chỉ thực hiện sau khi đủ 12 tháng và mart đã
  được rebuild/test đầy đủ.

## 4. Kiến trúc module đề xuất

```text
src/dss/
  __init__.py
  config.py
  contracts.py
  repository.py
  dense_grid.py
  features.py
  split.py
  baseline.py
  models.py
  evaluation.py
  recommendation.py
  persistence.py
  service.py
  pipeline.py

tests/dss/
  __init__.py
  fixtures.py
  test_contracts.py
  test_repository.py
  test_dense_grid.py
  test_features.py
  test_split.py
  test_baseline.py
  test_models.py
  test_evaluation.py
  test_recommendation.py
  test_persistence.py
  test_service.py
  test_pipeline.py
```

Trách nhiệm module:

| Module | Trách nhiệm |
|---|---|
| `config.py` | Đọc và validate cấu hình DSS |
| `contracts.py` | Schema, column set, type/range và grain validation |
| `repository.py` | Đọc mart/coverage bằng parameterized SQL |
| `dense_grid.py` | Chuyển sparse mart thành dense grid trong coverage hợp lệ |
| `features.py` | Calendar, lag và rolling features không leakage |
| `split.py` | Temporal train/validation/test split |
| `baseline.py` | Seasonal naive và historical median baseline |
| `models.py` | Pipeline huấn luyện và predict model ứng viên |
| `evaluation.py` | MAE, RMSE, WAPE và breakdown |
| `recommendation.py` | Demand level và recommendation rule |
| `persistence.py` | Lưu model-run metadata và forecast rows |
| `service.py` | API nội bộ cho dashboard, không chứa UI code |
| `pipeline.py` | CLI orchestration cho train/evaluate/forecast |

## 5. Dependencies cần bổ sung

Tối thiểu:

```text
pandas
numpy
scikit-learn
joblib
```

Yêu cầu:

- Pin theo compatible range trong `requirements.txt`.
- Không thêm XGBoost/LightGBM trước khi baseline và model scikit-learn đơn giản
  hoàn tất.
- Không commit `.joblib`, `.pkl` hoặc full training dataset.
- Model artifact nằm dưới `artifacts/models/`, đã được Git ignore.

## 6. P3.0 - Gate B consumer signoff

### Công việc

1. Kiểm tra chính xác tên, type và grain của mart.
2. Chấp nhận mart sparse và ghi rõ dense-grid thuộc Person 3.
3. Kiểm tra và chấp nhận `mart.mart_demand_coverage`.
4. Chốt xử lý zone 264/265.
5. Chốt forecast issue time.
6. Cập nhật `docs/gate_b_handoff.md` từ pending sang accepted sau khi các quyết
   định trên được review.
7. Cập nhật `docs/dss_design.md` với quyết định đã khóa.

### Definition of Done

- Person 3 có thể mô tả khi nào missing row là zero và khi nào là unavailable.
- Input contract không yêu cầu đọc RAW, staging hoặc `fact_trip`.
- Có test fixture phản ánh đúng mart sparse.

## 7. P3.1 - DSS scaffold và contract validator

### Công việc

- Tạo package `src/dss` và test package.
- Định nghĩa required input columns.
- Validate:
  - `demand_date` hợp lệ.
  - `demand_hour` trong 0-23.
  - `pickup_location_id` không null.
  - Sparse `trip_count` là integer và lớn hơn zero.
  - Không trùng `(date, hour, zone)`.
  - Zone key và business ID có mapping nhất quán.
- Tạo fixture nhỏ gồm:
  - Hai tháng complete.
  - Ít nhất ba zones.
  - Một số tổ hợp bị thiếu để biểu diễn zero.
  - Một unloaded month để kiểm tra không được fill zero.
  - Zone 264/265 để kiểm tra recommendation eligibility.

### Definition of Done

- Validator fail bằng thông báo rõ cho duplicate, invalid hour, negative count
  và missing column.
- Unit tests không cần PostgreSQL.

## 8. P3.2 - Repository và coverage boundary

### Public methods đề xuất

```python
class DemandRepository:
    def complete_months(self) -> list[CompleteMonth]: ...
    def zones(self) -> list[Zone]: ...
    def read_sparse_demand(self, start_date, end_date) -> DataFrame: ...

class ForecastRepository:
    def create_model_run(self, metadata) -> UUID: ...
    def save_forecasts(self, run_id, rows) -> int: ...
    def latest_run(self, forecast_date=None): ...
    def read_forecasts(self, run_id, filters=None) -> DataFrame: ...
```

### Quy tắc

- SQL parameterized, không ghép user input trực tiếp.
- Query chỉ đọc mart/coverage contract.
- Repository trả dữ liệu có schema đã validate.
- Không để SQL trùng lặp trong Streamlit page.
- Connection được inject trong test integration.

### Definition of Done

- Unit tests dùng fake/mock connection.
- Integration test được guard bằng environment flag tương tự analytics tests.
- Yêu cầu khoảng ngày ngoài coverage bị từ chối trước feature engineering.

## 9. P3.3 - Dense date-hour-zone grid

### Thuật toán

1. Nhận complete months đã được xác nhận.
2. Sinh tất cả calendar dates trong các tháng đó.
3. Cross join với 24 giờ.
4. Cross join với eligible zones.
5. Left join sparse mart theo date, hour và zone.
6. Fill `trip_count = 0` cho các tổ hợp thiếu trong coverage.
7. Giữ metadata zone ổn định.

Full-year expected scale với 263 actionable zones:

```text
366 x 24 x 263 = 2.310.192 rows
```

### Invariants

```text
row count = number of covered dates x 24 x number of eligible zones
```

```text
unique(demand_date, demand_hour, pickup_location_id)
```

```text
trip_count >= 0
```

### DST policy

Source timestamp là New York local wall-clock time nhưng không có timezone
offset. Dense grid dùng 24 slot giờ mỗi ngày:

- Spring-forward hour không có observation sẽ thành zero.
- Fall-back repeated hour đã được mart gộp vào cùng `demand_hour`.
- Hạn chế này phải được ghi trong báo cáo, không giả vờ phân biệt được hai offset
  trong giờ lặp.

### Definition of Done

- Không fill zero ngoài complete months.
- Tổng observed `trip_count` trước và sau dense-grid không đổi.
- Zone 264/265 có thể tồn tại trong reconciliation data nhưng được đánh dấu
  `is_actionable = false`.

## 10. P3.4 - Feature engineering không leakage

### Cách tổ chức series

Feature time-series được tính theo nhóm:

```text
pickup_location_id x demand_hour
```

Mỗi nhóm có một dòng mỗi ngày sau dense-grid. Cách này làm cho `shift(1)` trong
nhóm có nghĩa là cùng zone, cùng giờ của ngày trước.

### Feature bắt buộc

| Feature | Cách tính | Có sẵn lúc forecast? |
|---|---|---|
| `demand_hour` | Hour slot | Có |
| `day_of_week` | Từ forecast date | Có |
| `month` | Từ forecast date | Có |
| `day_of_month` | Từ forecast date | Có |
| `is_weekend` | Từ forecast date | Có |
| `lag_1d` | Target cùng zone-hour ngày D-1 | Có |
| `lag_2d` | Target cùng zone-hour ngày D-2 | Có |
| `lag_7d` | Target cùng zone-hour ngày D-7 | Có |
| `rolling_mean_7d` | Mean 7 ngày trước, bắt đầu từ D-1 | Có |
| `rolling_median_28d` | Median 28 ngày trước, bắt đầu từ D-1 | Có |
| `rolling_std_7d` | Std 7 ngày trước, bắt đầu từ D-1 | Có |
| `same_weekday_median_4w` | Median bốn cùng-thứ trước | Có |

Rolling feature phải tương đương:

```python
grouped_target.shift(1).rolling(window)
```

Không được tính rolling trực tiếp trên target chưa shift.

### Feature không dùng ban đầu

- Trip count của giờ trước trong chính forecast day.
- Feature xây từ drop-off của tương lai.
- Actual weather của forecast day nếu không có forecast-weather contract.
- Target encoding dùng toàn dataset.
- Statistics tính trên validation/test rồi đưa ngược vào training.

### Definition of Done

- Có unit test thay đổi target tương lai và chứng minh feature quá khứ không đổi.
- Mọi feature có cột/document mô tả thời điểm nó khả dụng.
- Rows chưa đủ history bị loại hoặc xử lý bằng policy được tài liệu hóa.

## 11. P3.5 - Temporal split và baseline

### Q1 prototype split

Sau khi bỏ warm-up history:

| Split | Khoảng ngày |
|---|---|
| Train | 08/01/2024-29/02/2024 |
| Validation | 01/03/2024-15/03/2024 |
| Test | 16/03/2024-31/03/2024 |

Q1 split chỉ dùng để xác minh pipeline.

### Full-year final split

Đề xuất ban đầu:

| Split | Khoảng ngày |
|---|---|
| Train | 01/01/2024-31/08/2024 |
| Validation | 01/09/2024-31/10/2024 |
| Test | 01/11/2024-31/12/2024 |

Ngày đầu khả dụng thực tế phụ thuộc feature window. Nếu dùng 28-day window,
training rows trước khi đủ history không được dùng.

### Baseline 1 - Seasonal naive

```text
y_hat(D, hour, zone) = y(D-7 days, hour, zone)
```

### Baseline 2 - Historical same-context median

```text
median of previous 4 matching weekday-hour observations for the same zone
```

### Definition of Done

- Không shuffle ngẫu nhiên.
- `max(train_date) < min(validation_date)`.
- `max(validation_date) < min(test_date)`.
- Baseline tạo prediction cho toàn bộ eligible evaluation rows hoặc báo rõ
  coverage bị thiếu.

## 12. P3.6 - Model experiments

### Nguyên tắc

- Baseline hoàn thành trước model ML.
- Bắt đầu bằng một model scikit-learn đơn giản.
- Chỉ dùng training để fit transformer/model.
- Chỉ dùng validation để chọn model và hyperparameter.
- Test chỉ được mở sau khi lựa chọn đã khóa.

### Candidate ban đầu

- Poisson regression cho count target và tính giải thích.
- HistGradientBoostingRegressor với non-negative post-processing.
- RandomForestRegressor chỉ khi profiling cho thấy runtime/memory phù hợp.

Không bắt buộc model phức tạp. Baseline có thể là phương án cuối nếu model ML
không cải thiện ổn định.

### Prediction post-processing

```text
predicted_trip_count = max(0, raw_prediction)
```

Giữ float cho evaluation. Chỉ round ở UI nếu cần hiển thị.

### Model metadata

- Model name và version.
- Feature contract version.
- Train/validation/test dates.
- Training row count.
- Code commit SHA.
- Hyperparameters.
- Created timestamp.

### Definition of Done

- Training reproducible bằng CLI.
- Model artifact nằm trong ignored artifact directory.
- Không có feature leakage test failure.
- Có bảng so sánh candidate với cả hai baseline.

## 13. P3.7 - Evaluation

### Metric tổng

| Metric | Vai trò |
|---|---|
| MAE | Sai số tuyệt đối dễ giải thích theo số chuyến |
| RMSE | Phạt mạnh sai số lớn ở zone-hour cao điểm |
| WAPE | Sai số tương đối tổng, ổn định hơn MAPE khi có zero |

Không dùng MAPE làm metric chính vì dense target có nhiều zero.

WAPE:

```text
sum(abs(actual - predicted)) / sum(actual)
```

Nếu tổng actual của một segment bằng zero, segment đó phải được đánh dấu không
xác định thay vì chia cho zero.

### Breakdown bắt buộc

- Theo borough.
- Theo hour.
- Weekday và weekend.
- Theo demand quantile.
- Top active zones và low-volume zones.
- Theo tháng trong validation/test.

### Model selection rule

Quy tắc phải được khóa trước test. Đề xuất:

- Candidate phải tốt hơn baseline tốt nhất trên validation WAPE.
- Không được cải thiện tổng nhưng suy giảm nghiêm trọng ở nhiều borough/hour.
- Ưu tiên model đơn giản hơn nếu cải thiện không đáng kể.

Ngưỡng phần trăm cải thiện cụ thể được quyết định sau Q1 prototype, nhưng trước
full-year final test.

### Definition of Done

- Evaluation report có baseline và model cùng một split.
- Không chọn model bằng test result.
- Có phân tích lỗi và limitation, không chỉ một metric tổng.

## 14. P3.8 - Demand level và recommendation

### Historical context

Mỗi prediction phải có:

- Historical baseline.
- Historical p50/p75 hoặc quantile tương ứng từ training history.
- Demand ratio có smoothing.

Tỷ lệ đề xuất:

```text
demand_ratio = predicted_trip_count / max(historical_baseline, 1)
```

### Rule ban đầu

| Level | Rule ban đầu |
|---|---|
| Low | Prediction dưới historical p50 |
| Medium | Prediction từ p50 đến dưới p75, hoặc ratio từ 1.0 |
| High | Prediction từ p75 và ratio ít nhất 1.15 |

Đây là rule khởi tạo, không phải threshold cuối. Threshold cuối phải được kiểm
tra trên validation và khóa trước final test.

### Recommendation text

| Level | Recommendation |
|---|---|
| Low | Không cần ưu tiên bổ sung; duy trì mức sẵn sàng thông thường |
| Medium | Theo dõi và duy trì khả năng sẵn sàng tại zone-hour này |
| High | Ưu tiên tăng khả năng sẵn sàng của taxi tại zone-hour này |

Zone không actionable nhận recommendation riêng:

```text
Không phát khuyến nghị điều phối cho zone ngoài phạm vi vận hành.
```

### Giới hạn tuyên bố

DSS hỗ trợ ưu tiên availability. Nó không:

- Tối ưu tuyến đường.
- Tính số taxi cần điều chuyển.
- Ước lượng unmet demand.
- Tính lợi nhuận.
- Khẳng định quan hệ nhân quả.

### Definition of Done

- Recommendation tách khỏi prediction code.
- Rule deterministic và có unit test boundary.
- Mỗi recommendation có explanation fields, không chỉ label.

## 15. P3.9 - Gate C persistence contract

Đề xuất bổ sung schema `dss` để tách output Python/model khỏi dbt-owned mart.

### `dss.model_run`

| Field | Ý nghĩa |
|---|---|
| `run_id` | UUID của training/forecast run |
| `model_name` | Tên approach được chọn |
| `model_version` | Version có thể truy vết |
| `feature_version` | Version feature contract |
| `recommendation_version` | Version rule |
| `train_start_date` | Ngày đầu train |
| `train_end_date` | Ngày cuối train |
| `validation_start_date` | Ngày đầu validation |
| `validation_end_date` | Ngày cuối validation |
| `created_at` | Timestamp tạo run |
| `metrics_json` | Metrics đã serialize |
| `git_commit_sha` | Commit tạo run |

### `dss.zone_hour_forecast`

| Field | Ý nghĩa |
|---|---|
| `run_id` | FK đến model run |
| `generated_at` | Thời điểm tạo prediction |
| `forecast_date` | Ngày được dự báo |
| `demand_hour` | Hour 0-23 |
| `pickup_zone_key` | Warehouse zone key |
| `pickup_location_id` | TLC LocationID |
| `borough` | Borough snapshot |
| `zone_name` | Zone-name snapshot |
| `predicted_trip_count` | Prediction không âm |
| `baseline_trip_count` | Historical baseline |
| `demand_ratio` | Prediction/baseline đã smoothing |
| `demand_level` | Low/Medium/High |
| `recommendation` | Text hỗ trợ quyết định |
| `is_actionable` | Có thuộc phạm vi recommendation không |

Unique key:

```text
(run_id, forecast_date, demand_hour, pickup_zone_key)
```

### Persistence rules

- Một run hoặc commit toàn bộ forecast rows, hoặc rollback toàn bộ.
- Rerun cùng version/date phải có idempotency policy rõ.
- Không overwrite run cũ; tạo version/run mới để audit.
- Dashboard mặc định đọc latest successful run.

### Definition of Done

- Row count forecast bằng `24 x eligible zones` cho mỗi forecast date.
- Không null key fields.
- Prediction và baseline không âm.
- Model/recommendation version có thể truy vết.

## 16. P3.10 - DSS service và Streamlit view

### Service methods đề xuất

```python
class DssService:
    def available_forecast_dates(self): ...
    def latest_run_summary(self, forecast_date): ...
    def ranked_recommendations(self, forecast_date, filters): ...
    def zone_hour_detail(self, forecast_date, zone_id): ...
    def model_metrics(self, run_id): ...
```

### UI integration

Tận dụng application của Person 2 và thêm view thứ ba:

```text
Tổng quan | OLAP | Dự báo & khuyến nghị
```

DSS view cần có:

- Forecast date selector.
- Borough/zone/hour filters.
- KPI: tổng predicted pickups, số High zone-hours, model version.
- Bảng xếp hạng zone-hour cần ưu tiên.
- Predicted demand so với historical baseline.
- Demand level và explanation.
- Model evaluation summary.
- Coverage/model freshness warning.
- Ghi rõ zone 264/265 không actionable.

### UI boundary

- Streamlit không chứa training logic.
- Streamlit không query RAW/fact trực tiếp.
- SQL nằm ở repository, business logic nằm ở service/recommendation.
- Cache key phải bao gồm run/version và filter.

### Definition of Done

- UI vẫn chạy nếu model metadata tồn tại nhưng không có forecast cho ngày chọn.
- Database/config error hiển thị thông báo, không crash stack trace cho user.
- Chart/table totals khớp forecast rows.

## 17. P3.11 - CLI và pipeline integration

### CLI đề xuất

```powershell
python -m dss.pipeline build-dataset `
  --start-date 2024-01-01 --end-date 2024-03-31

python -m dss.pipeline train `
  --config configs/dss_q1.toml

python -m dss.pipeline evaluate `
  --run-id <uuid>

python -m dss.pipeline forecast `
  --run-id <uuid> --date 2024-04-01
```

### Exit behavior

- Success trả exit code 0 và summary counts.
- Invalid coverage/contract trả nonzero trước khi training.
- Không in database password hoặc secret.
- Error message có phase và run ID khi run đã được tạo.

### Airflow handoff

Person 3 cung cấp CLI ổn định; Person 1 có thể gọi CLI sau khi bổ sung flow:

```text
ingest RAW
  -> staging
  -> staging tests/audit
  -> warehouse + mart
  -> dbt tests
  -> DSS forecast
  -> publish result
```

Không đưa training/feature logic trực tiếp vào DAG.

## 18. Test plan

### Unit tests

- Input contract thiếu cột hoặc sai type.
- Duplicate grain.
- Dense-grid row count.
- Fill zero chỉ trong coverage.
- Exclude unknown member.
- Actionable policy cho 264/265.
- Lag/rolling không đọc future target.
- Split ordering.
- Baseline output.
- Metric correctness, gồm WAPE denominator zero.
- Non-negative post-processing.
- Demand-level boundary.
- Recommendation text deterministic.
- Forecast output grain.

### Integration tests

- Repository đọc mart thật.
- Sparse-to-dense reconciliation.
- Forecast persistence transaction.
- Rerun/idempotency policy.
- DSS service đọc latest run.
- Dashboard totals khớp database.

### End-to-end test

```text
Q1 mart
  -> build dense dataset
  -> train baseline/model
  -> evaluate
  -> forecast one day
  -> persist 24 x zones rows
  -> display DSS page
```

### Required assertions

- DSS code không chứa query đến `raw.` hoặc `staging.`.
- Training code không đọc `dw.fact_trip`.
- Test dates không xuất hiện trong model fit.
- Future-target mutation không thay đổi past features.
- Tổng observed trips được giữ sau dense-grid.

## 19. Pull request breakdown

### PR P3-1 - Contract và scaffold

- Gate B consumer decisions.
- `docs/dss_design.md` update.
- Package/test scaffold.
- Input contract validator.
- Small sparse fixture.

### PR P3-2 - Repository và dense grid

- Demand repository.
- Coverage validator.
- Dense-grid builder.
- Reconciliation/unit tests.

### PR P3-3 - Features, split và baseline

- Leakage-safe features.
- Temporal split.
- Seasonal-naive/historical-median baselines.
- Baseline evaluation report cho Q1.

### PR P3-4 - Model và evaluation

- Model candidate.
- Training CLI.
- Metric breakdown.
- Model artifact metadata.

### PR P3-5 - Recommendation và Gate C

- Demand-level rules.
- Recommendation engine.
- DSS schema/persistence.
- Gate C tests/documentation.

### PR P3-6 - Dashboard và integration

- DSS service/repository.
- Streamlit forecast/recommendation view.
- End-to-end demo flow.
- User-facing error/coverage states.

Mỗi PR phải có cách chạy, test result và evidence ảnh/chụp output khi phù hợp.

## 20. Timeline từ 09/10 đến 15/11/2026

| Thời gian | Deliverable |
|---|---|
| 09-12/10 | Gate B signoff, issue time, coverage/zone policy, PR P3-1 |
| 13-18/10 | Repository, fixture, dense grid, PR P3-2 |
| 19-24/10 | Features, temporal split, baselines, PR P3-3 |
| 25-31/10 | Model candidate và evaluation framework, PR P3-4 |
| 01-05/11 | Recommendation, Gate C schema/persistence, PR P3-5 |
| 06-09/11 | Dashboard DSS và end-to-end integration, PR P3-6 |
| 10-12/11 | Full-year final run, error analysis, limitations và test fixes |
| 13-14/11 | Báo cáo, slide, demo script và rehearsal |
| 15/11 | Kiểm tra ZIP và nộp trước 23:59 |

## 21. Yêu cầu phối hợp với Person 1 và Person 2

### Yêu cầu Person 1

- Lịch hoàn tất tháng 4-12.
- Bằng chứng full-year source/audit/staging reconciliation.
- Cách chạy pipeline từ checkout sạch.
- Bổ sung hoặc hỗ trợ task Airflow cho warehouse/mart sau khi CLI flow ổn định.

### Yêu cầu Person 2

- Xác nhận Gate B contract chính thức.
- Duy trì và rebuild `mart.mart_demand_coverage` cùng demand mart.
- Rebuild/test mart sau mỗi lần thêm tháng.
- Xác nhận zone 264/265 và unknown-member policy.
- Review DSS repository không phá warehouse boundary.
- Hỗ trợ tích hợp view DSS vào application hiện tại.

### Person 3 bàn giao cho cả nhóm

- Feature contract và forecast cutoff.
- Baseline/model evaluation evidence.
- Gate C output contract.
- Recommendation rules và limitation.
- CLI train/forecast có thể orchestrate.
- DSS dashboard demo.

## 22. Rủi ro và xử lý

| Rủi ro | Tác động | Xử lý |
|---|---|---|
| Full-year data trễ | Không đủ final evaluation | Hoàn tất Q1 vertical slice sớm; đặt deadline nội bộ cho tháng 4-12 |
| Điền zero ngoài coverage | Target sai nghiêm trọng | Coverage validator fail-closed |
| Feature leakage | Metric giả tạo | Forecast cutoff, shifted features và mutation tests |
| Dense grid tốn RAM | Training chậm/OOM | Dtype tối ưu, load theo range, chỉ giữ feature cần thiết |
| Model không hơn baseline | DSS thiếu thuyết phục | Cho phép baseline là model cuối; báo cáo trung thực |
| Low-volume zones gây metric nhiễu | Kết quả không ổn định | Segment evaluation và training-only eligibility threshold |
| Threshold recommendation tùy ý | Khó bảo vệ trước giảng viên | Dùng training quantiles, validation evidence và version rule |
| Mart không được refresh sau ingestion | Dùng dữ liệu cũ | Check coverage/freshness trước mọi training/forecast |
| Dashboard gắn chặt model code | Khó test/demo | Repository-service-UI separation |

## 23. Definition of Done của Person 3

Phần Person 3 hoàn tất khi:

- [ ] Gate B được Person 3 ký nhận với sparse/coverage policy rõ ràng.
- [ ] DSS chỉ đọc contract mart/coverage, không đọc RAW/staging/fact.
- [ ] Dense grid không biến unloaded periods thành zero.
- [ ] Feature engineering có test chống leakage.
- [ ] Train/validation/test được chia theo thời gian.
- [ ] Có ít nhất hai baseline.
- [ ] Có ít nhất một model candidate được so sánh công bằng với baseline.
- [ ] Báo cáo MAE, RMSE, WAPE và breakdown theo nhóm.
- [ ] Model selection không dùng test set.
- [ ] Prediction được chuyển thành demand level và recommendation giải thích được.
- [ ] Zone 264/265 không nhận recommendation điều phối.
- [ ] Gate C output có model/recommendation version và audit metadata.
- [ ] Forecast persistence có transaction và grain test.
- [ ] Streamlit hiển thị forecast, baseline, level và recommendation.
- [ ] CLI train/evaluate/forecast chạy độc lập trước khi nối Airflow.
- [ ] Q1 vertical slice chạy end-to-end.
- [ ] Full-year final evaluation hoàn tất sau khi 12 tháng sẵn sàng.
- [ ] Tài liệu limitations và hướng phát triển được hoàn thiện.
- [ ] Có commit/PR/test evidence thể hiện đóng góp cá nhân.

## 24. Bước thực hiện ngay tiếp theo

1. Xử lý thay đổi `.gitignore` đang tồn tại trước khi chuyển branch.
2. Tạo branch từ `origin/develop`:

```powershell
git switch -c feature/dss origin/develop
```

3. Review và ký nhận `docs/gate_b_handoff.md`.
4. Thống nhất coverage interface với Person 2.
5. Chốt forecast issue time và zone policy.
6. Thực hiện PR P3-1 trước khi viết model.
7. Không bắt đầu model experiment khi dense-grid, split và baseline tests chưa
   hoàn tất.
