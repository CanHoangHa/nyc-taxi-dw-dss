# NYC Taxi Data Warehouse & Decision Support System

Bài tập lớn CO4031, Nhóm 10, L02. Hệ thống xây dựng kho dữ liệu NYC Yellow Taxi, phân tích lượt đón theo thời gian và khu vực bằng OLAP, và dự báo lượt đón ngày tiếp theo để hỗ trợ chọn khu vực ưu tiên.

Luồng xử lý dùng Python để nạp tệp Parquet vào PostgreSQL. dbt dựng staging, kho dữ liệu và mart. Dashboard dùng Streamlit và mô hình dự báo dùng scikit-learn.

## 1. Chuẩn bị môi trường

Cài Python 3.11 và Docker có Compose v2. Chạy các lệnh PowerShell từ thư mục chứa README này. Nếu dùng ZIP nộp bài, đó là thư mục src/ ngoài cùng, nơi có docker-compose.yml.

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
~~~

Đổi mật khẩu mẫu trong .env rồi khởi động PostgreSQL. Nếu đã có .env, dùng lại file hiện tại.

~~~powershell
docker compose up -d --wait postgres
$env:PYTHONPATH = (Resolve-Path "src").Path
~~~

Docker tự chạy các script trong sql/ khi tạo database lần đầu. Nếu dùng database cũ, xem hướng dẫn [cập nhật schema DSS](docs/dss_refit_publication_runbook.md). Khi mở cửa sổ PowerShell mới, đặt lại PYTHONPATH như trên.

## 2. Nạp dữ liệu mẫu

Xem [hướng dẫn dữ liệu mẫu](data/README.md) để tải tệp tháng 01/2024 từ Drive. Đặt tệp tại data/raw/yellow/2024/01/yellow_tripdata_2024-01.parquet. Bảng tra cứu khu vực đã có trong src/dbt/seeds/.

~~~powershell
.\.venv\Scripts\python.exe -m taxi_dw.ingestion run --dataset yellow_taxi --year 2024 --month 1 --batch-size 10000
~~~

### Tải dữ liệu cho phần dự báo

Lệnh nạp dùng tệp cục bộ nếu đã có. Nếu thiếu, chương trình tải từ NYC TLC. Để chuẩn bị dữ liệu tháng 01–04/2024 cho phần dự báo và đánh giá trong báo cáo, chạy lệnh sau trước khi dựng kho. Tháng đã nạp thành công với cùng nội dung tệp sẽ được bỏ qua.

~~~powershell
.\.venv\Scripts\python.exe -m taxi_dw.ingestion backfill --year 2024 --start-month 1 --end-month 4
~~~

## 3. Dựng kho dữ liệu

~~~powershell
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe seed --project-dir src/dbt --profiles-dir src/dbt
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe run --project-dir src/dbt --profiles-dir src/dbt --select staging warehouse marts
.\.venv\Scripts\python.exe -m taxi_dw.staging_audit
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe test --project-dir src/dbt --profiles-dir src/dbt
~~~

staging_audit cập nhật số bản ghi hợp lệ để mart xác định tháng đã xử lý đầy đủ. Chạy lại bước này sau khi nạp thêm tháng.

## 4. Mở dashboard

~~~powershell
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
~~~

Mở địa chỉ Streamlit in ra, thường là http://localhost:8501. Với mẫu tháng 01, chọn khoảng ngày trong tháng 01/2024 ở Overview và OLAP. Tab Forecast & priorities đọc các lượt dự báo đã lưu vào PostgreSQL.

## 5. Chạy dự báo và đối chiếu báo cáo

Để chạy thử một lượt dự báo cho 01/04/2024, cần dựng mart cho đủ tháng 01–03. Lệnh train in đường dẫn artifact. Thay đường dẫn ví dụ bên dưới bằng kết quả đó.

~~~powershell
.\.venv\Scripts\python.exe -m dss.pipeline train --config configs/dss_q1.toml
.\.venv\Scripts\python.exe -m dss.pipeline forecast --artifact "artifacts/models/ten-file-thuc-te.joblib" --date 2024-04-01
~~~

Sau khi lưu dự báo, chọn Reload forecasts trong dashboard. Để đối chiếu đúng kết quả tháng 4 trong báo cáo, dùng dữ liệu tháng 01–04 và làm theo [giao thức đánh giá tháng 4](docs/dss_april_protocol.md) cùng [hướng dẫn huấn luyện lại và lưu dự báo](docs/dss_refit_publication_runbook.md). Script đánh giá yêu cầu artifact gốc được chỉ rõ trong giao thức. Artifact và dữ liệu PostgreSQL nằm ngoài Git.

## Tài liệu chi tiết

- [Thiết kế kho dữ liệu](docs/dimensional_model.md)
- [Truy vấn và thao tác OLAP](docs/olap_analytics.md)
- [Kết quả dự báo tháng 4](docs/dss_april_evaluation.md)
- [Điều phối bằng Airflow](docs/airflow_runbook.md), tùy chọn.
