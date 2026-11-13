# Dữ liệu mẫu CO4031 – Nhóm 10 – Lớp L02

**Link Google Drive để tải dữ liệu mẫu**

<https://drive.google.com/drive/folders/1Ca045Gt2O17jTH5IH1ifB-tucfD3rOmI?usp=sharing>

## Tệp dữ liệu

- **yellow_tripdata_2024-01.parquet** chứa dữ liệu chuyến đi NYC Yellow Taxi tháng 01/2024. Đặt tệp vào thư mục data/raw/yellow/2024/01/ tính từ gốc dự án. Nếu dùng gói nộp, đường dẫn tính từ gốc gói là src/data/raw/yellow/2024/01/. Tạo thư mục này nếu chưa có.
- **taxi_zone_lookup.csv** là bảng tra cứu mã khu vực taxi. Bản dùng để chạy dự án đã có sẵn. [Tệp tra cứu trong repo](../src/dbt/seeds/taxi_zone_lookup.csv)

Dữ liệu tháng 01 dùng để chạy thử quy trình nạp, dựng kho và xem dashboard OLAP. Để tái lập kết quả dự báo và đánh giá trong báo cáo, cần dữ liệu tháng 01–04/2024. Cách nạp các tháng còn lại nằm ở bước 2. [Hướng dẫn chạy dự án](../README.md)
