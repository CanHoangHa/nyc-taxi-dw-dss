# Protocol cố định: Q1 refit → April 2024

Đóng trước khi nạp/xem actual tháng 4, ngày 27/10/2026 (Asia/Saigon).
Repo kiểm tra: feature/dss-poisson-zone-ranking, HEAD 72f4c87, working tree sạch.
Coverage thực tế chỉ có tháng 1–3; PostgreSQL được khởi động lại, không tạo volume mới.

## Thiết kế đã chọn

- Giữ Random Forest đã thắng validation Q1; không chọn lại model, tuning hay K trên April.
- Parent: artifacts/models/dss-rf-9a687651-d038-4f06-8ec2-1bbaa5946f3a.joblib.
- RF: n_estimators=64, max_depth=16, min_samples_leaf=10, max_features=0.7,
  n_jobs=2, random_state=42; feature/preprocessing giữ nguyên.
- Selection cũ: train 29/01–29/02, validation 01–15/03. March 16–31 đã xem,
  chỉ retrospective; sau refit toàn bộ March là dữ liệu fit, không còn là test.
- Fit thực tế mới: toàn bộ dense eligible zone-hour có đủ features từ
  29/01 đến 31/03/2024, gồm zero pickup. January 1–28 chỉ cung cấp lịch sử.
- Evaluation duy nhất: 01–30/04/2024, 24 giờ × toàn bộ eligible zones.
- Dự báo ngày D chỉ dùng actual đến D−1. Có thể cập nhật lag/rolling bằng
  actual April trước D; không refit hằng ngày. Không dùng actual ngày D.
- MAE, RMSE, WAPE tổng và từng borough, RF/D−7/same-weekday median 4 tuần
  trên chính xác cùng dòng. WAPE tổng là tổng sai số tuyệt đối / tổng actual;
  mẫu số bằng 0 báo undefined. Đây là eligible grid, không phải mọi RAW pickup.
- Báo thêm RF parent cố định trên cùng April rows để mô tả tác động refit;
  đây là chẩn đoán bổ sung, không dùng chọn lại model hay triển khai lại parent.
- Ranking: Manhattan, K=10, [08,09) (một giờ buổi sáng) và [06,10)
  (cửa sổ buổi sáng), mỗi case trên cả 30 ngày. Cùng universe eligible zones
  từ DW được snapshot trước khi nạp April, cùng giờ và K. Tổng dự báo theo zone;
  ties theo zone ID tăng dần, đúng K. So RF với D−7 bằng actual pickup share,
  báo từng ngày, win/tie/loss (theo số pickup nguyên), chênh lệch share điểm %
  trung bình và share gộp theo tổng pickup. Không tối ưu case theo kết quả.
- Chỉ đánh giá mức tập trung pickup quan sát được, không chứng minh hiệu quả
  điều xe, lợi nhuận hay nhu cầu chưa được phục vụ.

## Metadata và bảo toàn

Refit offline dùng artifact mới có fit window riêng; giữ selection metadata cũ.
Không tạo split giả, không sửa CHECK dss.model_run, không publish refit vào DB.
Chặn forecast trong cả fit window thực tế; chặn evaluate March như holdout.
Lưu SHA256 parent/model/protocol/source/data, snapshot nguồn và predictions.
Giữ nguyên backup, mọi artifact/run DSS cũ; không sửa RAW thủ công hoặc reload Q1.

## Kế hoạch thực hiện và xác minh

1. Kiểm tra coverage/audit/size, snapshot hashes artifact cũ và universe.
2. Viết tests refit chỉ dùng Q1, chống target/future leakage, chặn forecast trong
   fit, chặn publication metadata sai; triển khai dss.refit và script offline.
3. Refit Q1 trước khi nạp April; lưu model, provenance và checksum.
4. Downloader/validator/ingestion chỉ April; staging → audit reconciliation →
   warehouse/mart → full dbt tests. Theo dõi dung lượng khi rebuild toàn bảng.
5. Đánh giá cố định April; xuất metrics, ranking từng ngày, báo cáo dễ tái lập.
6. Chạy unittest đúng lệnh với cả hai integration flags; ghi passed/skipped thật.
   Review thay đổi; chưa commit/push/PR theo yêu cầu.

## Nhật ký

- Ban đầu D còn 55.57 GiB; database tables khoảng 11.25 GiB.
- Backup D:/DockerBackups/2026-10-27/nyc_taxi_dw.dump tồn tại, 1,458,202,037 bytes.
