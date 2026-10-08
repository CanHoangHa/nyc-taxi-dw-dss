# Person 2: bước đầu xây dựng warehouse

Trạng thái: dimension, `fact_trip` và mart đã triển khai trên nhánh
`feature/warehouse-foundation`, dựa trên `develop` commit `d99faec`
(29/09/2026), đã cập nhật thêm commit `efc0e8a` ngày 30/09/2026.
Truy vấn OLAP và giao diện phân tích là bước tiếp theo của người 2.

Mốc kiểm tra trên máy ngày 29/09/2026: Docker và PostgreSQL chạy khỏe;
chạy lại dbt seed (265 zone), hai model staging và 22 test đều thành công.
Sau khi dựng lại staging: RAW 2.964.624, valid 2.924.187, quarantined 40.381,
rejected 56; số `trip_source_key` duy nhất trong valid là 2.924.187.

## Mục tiêu và ranh giới

Luồng của nhóm là Parquet → `raw.yellow_trip` → `staging.stg_yellow_trip_valid`
→ các bảng `dw` → `mart_zone_hour_demand` → dự báo và giao diện. Người 1 cung
cấp những chuyến xe hợp lệ, tên cột thống nhất và thông tin truy vết. Người 2
biến chúng thành mô hình phân tích và mart. Người 3 dùng mart để xây DSS.

Bước đầu của người 2 là tạo **nền tảng dbt warehouse và năm dimension**:
`dim_date`, `dim_time`, `dim_taxi_zone`, `dim_vendor`, `dim_payment_type`.
`dim_taxi_zone` đã được làm đầu tiên để kiểm tra đường đi từ seed đến schema `dw`.
Mart, truy vấn OLAP và giao diện thuộc các bước tiếp theo của Milestone 1
trong `PLAN.md`.

## Việc thực hiện, theo thứ tự

1. **Khóa đầu vào.** Chạy lại `dbt seed`, `dbt run --select staging`, `dbt test`
   theo `docs/gate_a_handoff.md`; xác nhận số dòng valid và tính duy nhất của
   `trip_source_key`. Ghi các vấn đề Gate A còn mở cho người 1; không để lỗi
   staging làm sai số lượng fact về sau.
2. **Xác định dbt schema.** Cấu hình các model warehouse thực sự được tạo ở
   `dw`, còn staging và seed vẫn ở `staging`. Kiểm tra tên schema thực tế bằng
   `dbt ls`/kết quả chạy và truy vấn PostgreSQL, vì mặc định dbt có thể ghép
   schema đích với schema tùy chỉnh.
3. **Chốt quy ước khóa và thành viên chưa biết.** Khóa dimension phải ổn định
   qua lần chạy lại và có một giá trị dự phòng cho mã thiếu/chưa nhận diện;
   ghi rõ ý nghĩa giá trị đó trong `docs/dimensional_model.md`. Giữ mã nghiệp
   vụ (`location_id`, `vendor_id`, `payment_type_id`) cùng khóa warehouse để
   đối chiếu được. Với zone, seed có mã 264 `N/A` và 265 `Outside of NYC`;
   giữ nguyên hai mã này, phân biệt với thành viên dự phòng.
4. **Triển khai dimension theo thứ tự.** `dim_taxi_zone` từ
   `taxi_zone_lookup`; `dim_date` phủ ngày pickup và dropoff thực tế (kể cả
   dropoff sang tháng/năm kế tiếp); `dim_time` dùng giờ địa phương New York
   với độ phân giải được ghi rõ trước khi tạo fact; `dim_vendor` và
   `dim_payment_type` lấy tập mã từ staging và mô tả mã nếu có nguồn đáng tin.
   Không suy diễn tên/mô tả mã chưa được chứng thực.
5. **Kiểm tra.** dbt test tính duy nhất/không null của khóa, tính duy nhất của
   mã nghiệp vụ trong từng dimension, các giá trị ngày/giờ hợp lệ, và việc
   mọi mã zone trong valid staging tìm được một thành viên. Chạy `dbt seed`,
   `dbt run --select staging warehouse` và `dbt test` hai lần để kiểm tra
   kết quả ổn định; ghi số dòng và câu lệnh tái lập.

## Điều kiện hoàn thành bước đầu

- Năm dimension tồn tại trong `dw`, với grain và quy tắc khóa được tài liệu hóa.
- Seed, staging và dimension chạy lại thành công trên dữ liệu tháng 01/2024.
- Không có mã zone của chuyến valid bị mất khi lookup; pickup và dropoff đều
  dùng cùng `dim_taxi_zone` ở bước fact tiếp theo.
- `fact_trip` dùng cách map timestamp, mã nghiệp vụ và giá trị thiếu sang khóa
  dimension được ghi rõ trong `docs/dimensional_model.md`.

Đã kiểm tra trên dữ liệu tháng 01/2024: cả năm bảng nằm trong `dw`;
`dim_date` có 33 dòng (32 ngày + dự phòng), `dim_time` 1.441,
`dim_taxi_zone` 266, `dim_vendor` 4 và `dim_payment_type` 6. Hai lần chạy
warehouse cho kết quả giống hệt nhau theo dấu vân tay toàn bộ nội dung bảng.
Toàn bộ 49 dbt tests của staging và warehouse đều đạt, bao gồm kiểm tra
coverage cho cả pickup và dropoff. Xem câu lệnh chạy trong `README.md`.

## Phối hợp và bước kế tiếp

- **Với người 1:** nếu Gate A còn sai kiểu dữ liệu, phân loại DQ hoặc thiếu
  trường canonical, đưa ví dụ dòng và kết quả kỳ vọng để sửa ở staging. Đừng
  vá cùng logic trong dimension. Hiện cần theo dõi ba trường hợp biên từng
  phát hiện: ép kiểu tràn số, số tiền âm rất nhỏ bị làm tròn, và `NaN` ở
  `trip_distance`.
- **Với người 3:** `mart_zone_hour_demand` hiện đếm số pickup valid theo ngày
  × giờ × zone. Bảng chỉ chứa ô có chuyến; tài liệu `docs/gate_b_handoff.md`
  ghi rõ cách hiểu ô 0 chuyến và tháng chưa có dữ liệu. Người 3 cần chấp nhận
  hợp đồng này trước khi đánh dấu Gate B hoàn tất.

## Bước tiếp theo đã hoàn thành: `fact_trip`

`dw.fact_trip` lấy duy nhất các dòng từ `stg_yellow_trip_valid`, nối pickup và
dropoff tới cùng bảng ngày, phút và taxi zone theo hai vai trò, cộng với vendor
và payment type. Mọi source measure canonical được giữ nguyên; `trip_count=1`
cho mỗi chuyến, còn các giá trị nguồn null vẫn là null. Khóa chuyến có chỉ mục
unique. Truy vấn reconcile theo batch kiểm tra số dòng, tổng `trip_count` và
tổng `total_amount` bằng staging. Mọi khóa ngoại được kiểm tra không null và
tồn tại trong dimension. Kết quả tháng 01/2024: 2.924.187 dòng fact;
75/75 dbt tests đạt. Cách map chi tiết ở `docs/dimensional_model.md`.

## Bước tiếp theo đã hoàn thành: demand mart

`mart.mart_zone_hour_demand` có 77.427 ô có pickup trong tháng 01/2024;
tổng `trip_count` là 2.924.187, đúng bằng fact. Toàn bộ 88/88 dbt tests
sau khi cập nhật `develop` đều đạt. Chạy mart lần hai cho cùng nội dung.
Giao diện bàn giao cho người 3 ở `docs/gate_b_handoff.md`.

Tài liệu nền: `README.md`, `PLAN.md`, `docs/data_contracts.md`,
`docs/dimensional_model.md`, `docs/gate_a_handoff.md`.
