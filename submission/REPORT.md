# Báo cáo Day 09 — Nguyễn Thiên Phúc, 03339

## 1. Kết luận trước
Pipeline kết luận **Hold**. Toàn bộ 224 ảnh ở lô thô (raw) được đưa vào; sau bước 1 nhận dữ liệu, 21 ảnh bị loại (2 ảnh hỏng, 3 ảnh quá nhỏ, 8 ảnh trùng tuyệt đối, 5 ảnh rò rỉ test, 3 ảnh gần trùng), 203 ảnh được đưa vào pipeline và xuất ra dataset `clean_v1`. Lý do chính: Pipeline không còn lỗi bắt buộc nào (`n_errors = 0`), tuy nhiên sau khi mô phỏng người duyệt tối đa 80 ảnh theo ngân sách, vẫn còn 38 ảnh chứa cảnh báo nghi vấn chưa được kiểm chứng, tương đương tỉ lệ 18.72% (38/203), vượt ngưỡng Hold 10.00% theo quy định dự án tại `configs/pipeline.yaml`. Lô dữ liệu cần thêm ngân sách duyệt người trước khi chính thức phát hành.

## 2. Lỗi và phân việc
Bảng thống kê lỗi từ `02_error_list_v1` gom theo mã lỗi:

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy (autofix) | Ảnh lỗi định dạng/cắt cụt không load được pixel; máy tự động loại bỏ khỏi dataset (`remove_image`). |
| `BAD_SIZE` | 3 ảnh | Máy (autofix) | Cạnh ngắn của ảnh < 250px, không đạt chuẩn tối thiểu của mô hình; máy tự động loại bỏ (`remove_image`). |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy (autofix) | Ảnh trùng khớp mã băm MD5 từng byte với ảnh đã có; máy tự động xoá ảnh lặp để tránh bias (`remove_image`). |
| `LEAK_TEST` | 5 ảnh | Máy (autofix) | Ảnh trùng với kho dữ liệu test/val (`reference_dirs`); máy bắt buộc phải loại bỏ để chống rò rỉ dữ liệu (`remove_image`). |
| `DUP_IMAGE_NEAR` | 3 ảnh | Máy (autofix) | Ảnh biến đổi nhẹ (resize, đổi sáng) có khoảng cách pHash <= 6; máy tự động loại bỏ ảnh trùng gần đúng (`remove_image`). |
| `MISSING_LABEL_FILE` | 6 ảnh | Máy (autofix) | Ảnh chưa có file nhãn; máy không tự bịa nhãn mà ghi nhận `needs_label` và ưu tiên đẩy lên đầu hàng đợi cho người gán. |
| `BAD_CLASS_NAME` | 2 lỗi | Máy (autofix) | Tên lớp trong `data.yaml` bị viết hoa sai chuẩn (`Person`, `Bus`); máy tự động ghi lại đúng danh sách lớp chuẩn (`rename_classes`). |
| `BAD_FORMAT` | 3 dòng | Máy (autofix) | Dòng nhãn sai cú pháp (thiếu cột, giá trị `nan`); máy tự động xoá dòng hỏng (`drop_line`). |
| `BAD_CLASS_ID` | 6 dòng | Máy (autofix) | ID lớp nằm ngoài phạm vi 0..3 (ví dụ 93, 4, -1); máy tự động xoá dòng không hợp lệ (`drop_line`). |
| `BOX_ZERO` | 4 dòng | Máy (autofix) | Box có chiều rộng hoặc chiều cao <= 0; máy tự động xoá dòng (`drop_line`). |
| `DUP_BOX` | 7 dòng | Máy (autofix) | Trùng lớp và có IoU > 0.9 với một box trước đó trong cùng ảnh; máy tự động xoá box lặp xuất hiện sau (`drop_line`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (autofix) | Tọa độ box vượt khỏi lề [0, 1] quá ngưỡng 0.002; máy tự động cắt (`clip_box`) về biên ảnh, nếu nằm hẳn ngoài ảnh thì xoá (`drop_line`). |
| `POSSIBLE_WRONG_CLASS` | 18 box | Người (hàng đợi) | Model checker nghi ngờ dán nhầm lớp (car <-> truck <-> bus); máy chỉ cảnh báo vì model có thể nhầm, cần mắt người thẩm định. |
| `POSSIBLE_MISSING` | 53 box | Người (hàng đợi) | Model checker phát hiện vật thể rõ nhưng nhãn thô bỏ sót; cần người xem để bổ sung nhãn. |
| `POSSIBLE_FALSE_POS` | 29 box | Người (hàng đợi) | Box nhãn không khớp với bất kỳ dự đoán nào của model checker; cần người kiểm tra xem nhãn có bị gán ảo vào nền không. |
| `POSSIBLE_LOOSE_BOX` | 28 box | Người (hàng đợi) | Box cùng lớp nhưng IoU < 0.5 so với model checker; cần người tinh chỉnh lại viền box cho khít vật thể. |
| `EMPTY_LABEL` | 12 ảnh | Người (hàng đợi) | File nhãn rỗng; cần người phân định đây là ảnh nền (background không chứa đối tượng) hay ảnh bị bỏ quên chưa gán. |
| `BOX_TINY` | 6 dòng | Người (hàng đợi) | Cạnh ngắn < 12px; cảnh báo cho người xem xét có vi phạm hướng dẫn gán nhãn vật quá nhỏ không. |
| `BOX_HUGE` | 3 dòng | Người (hàng đợi) | Box chiếm > 95% diện tích ảnh; cảnh báo người kiểm tra xem có phải box bao trùm sai toàn cảnh không. |
| `CLASS_RARE` | 4 lớp | Người (hàng đợi) | Cảnh báo thống kê cấp dataset khi số lượng box của một lớp thấp bất thường. |

**Phân tích hàng đợi người duyệt (`05_review_queue.csv`):**
- Hàng đợi xếp các ảnh đầu hàng dựa trên tổng điểm ưu tiên (`priority`), trong đó các lỗi nghiêm trọng nhất được nhân trọng số cao: ảnh thiếu nhãn (`NEEDS_LABEL`, trọng số 10.0), ảnh vừa bị xoá dòng (`FIXED_DROP_LINE`, 2.0), nhầm lớp (`POSSIBLE_WRONG_CLASS`, 3.0 * (1 + conf)), và thiếu nhãn (`POSSIBLE_MISSING`, 2.0 * (1 + conf)). Do đó, ảnh đa lỗi nguy hiểm nhất (`img_0020` có điểm 11.524 do vừa bị drop line vừa nghi ngờ missing và wrong class) cùng 6 ảnh mất trắng nhãn (`img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0156`, `img_0167`) được đẩy lên đầu để người xử lý ngay.
- Với ngân sách 80 ảnh, người xem đã thẩm định được **94/123 lỗi ngữ nghĩa** (đạt 76.4%), trong đó xử lý được **18/18 lỗi nhầm lớp** (100%) và **51/53 lỗi thiếu nhãn** (96.2%). Các cảnh báo còn sót lại chưa kịp xem chủ yếu là lỗi box lỏng và false positive ở các ảnh có điểm ưu tiên thấp hơn.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 6 | 1.00 / 0.50 → 1.00 / 0.67 (trên DUP_IMAGE_NEAR) | Tăng recall phát hiện ảnh gần trùng (bắt thêm 2 ảnh bị đổi sáng/resize) mà không làm giảm Precision (vẫn giữ 1.00). |
| `second_opinion.conf` | 0.25 | 0.60 | WRONG_CLASS: 0.56 / 0.83 → 0.62 / 0.83<br>MISSING: 0.50 / 1.00 → 0.57 / 1.00 | Tăng Precision của Missing và Wrong Class, giảm tải báo động giả cho người duyệt, trong khi Recall lỗi bắt buộc không suy giảm. |

**Một chỗ calibration có thể đánh lừa bạn:**
- Trên tập `data/calib` (chỉ vỏn vẹn 39 ảnh), sweep cho thấy `phash_dist = 16` đạt chỉ số F1 cao nhất là `0.91` (Precision 1.00, Recall 0.83). Nhìn vào bảng sweep rất dễ bị cám dỗ chọn ngay 16.
- **Bằng chứng từ dữ liệu:** Khi thử áp dụng `phash_dist = 16` lên tập `raw` (224 ảnh) và tập tham chiếu (`data/test`, `data/gold_val`), số lượng ảnh bị cờ rò rỉ `LEAK_TEST` nhảy vọt bất thường từ 5 ảnh lên **11 ảnh**, và `DUP_IMAGE_NEAR` tăng lên 7 ảnh (tổng loại bỏ tới 26 ảnh!). Khoảng cách Hamming 16 là quá rộng trên tập dữ liệu đa dạng, dẫn đến việc nhận nhầm các ảnh chụp góc máy khác nhau thành "ảnh trùng lặp" hoặc "rò rỉ test" (False Positives). Vì hành động ở cửa vào là **xoá vĩnh viễn ảnh**, một lỗi cờ nhầm (FP) sẽ làm mất vĩnh viễn dữ liệu sạch có giá trị. Do đó, chọn `phash_dist = 6` là điểm cân bằng an toàn và thực tế hơn nhiều.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Chứng minh gate chặn đúng:**
- Chạy lệnh mô phỏng không có ngân sách duyệt: `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`.
- Kết quả thực tế: Do không có người duyệt, 6 ảnh thiếu nhãn (`MISSING_LABEL_FILE`) không được ai gán bổ sung, trở thành lỗi bắt buộc tồn đọng. Cổng gate đưa ra kết luận: `REWORK — Còn 6 lỗi bắt buộc (severity ERROR)` với mã thoát là **20**.
- Pipeline tuyệt đối **không xuất** thư mục dataset phát hành `work/exp_nb/clean_v1`. Điều này chứng minh cửa chặn hoạt động hoàn toàn chính xác theo nguyên tắc Fail-Safe: bất kỳ lô dữ liệu nào còn sót lỗi bắt buộc sẽ lập tức bị chặn đứng và từ chối xuất bản.

**(b) Hai điểm mù có bằng chứng:**
1. **Ảnh trùng lặp bị biến đổi hình học mạnh (crop sâu, xoay, lật):** Thuật toán `phash` nhạy cảm với cấu trúc bố cục toàn cục. Khi một ảnh bị crop > 50% hoặc xoay góc lớn, khoảng cách Hamming vượt xa ngưỡng 6, khiến pipeline hoàn toàn mù trước các ca trùng lặp phái sinh này.
2. **Điểm mù ngữ nghĩa chung giữa người gán và model checker:** Module `second_opinion` sử dụng model `yolo26l` để phản biện. Nếu gặp trường hợp vật thể nằm ở ranh giới mơ hồ (ví dụ xe bán tải pickup, SUV lai tải trong `img_0007`) mà cả người gán nhãn lẫn model lớn đều nhận nhầm thành `car`, hoặc model có độ tự tin < 0.6, pipeline sẽ hoàn toàn bỏ qua và không phát ra bất kỳ cảnh báo nào.
3. **Box lệch/lỏng nhẹ (IoU từ 0.5 đến 0.9):** Các box vẽ lỏng viền vừa phải (IoU >= 0.5) được máy coi là "khớp vật" nên không kích hoạt `POSSIBLE_LOOSE_BOX`, đồng thời cú pháp hợp lệ nên lọt thẳng vào tập dữ liệu mà không bị chặn.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy: Trong phiên làm việc hiện tại, môi trường máy cục bộ không có GPU và chưa kết nối runtime Colab để huấn luyện mô hình YOLOv26n. Phần kiểm tra nộp bài sử dụng cờ `--no-train` theo đúng quy định tại `SUBMISSION.md` và `check_submission.py`.

*Phân tích giả thuyết kỹ thuật nếu được huấn luyện:*
- **Kỳ vọng:** Biến thể `clean` sẽ cho kết quả mAP50 cao hơn `raw`, vì pipeline đã loại bỏ triệt để 5 ảnh rò rỉ tập test (`LEAK_TEST`), 11 ảnh trùng lặp (`DUP_IMAGE_*`), sửa 8 box tràn viền và loại bỏ các box sai định dạng.
- **Nếu chênh lệch mAP50 nằm trong độ lệch chuẩn giữa các seed:** Kết luận trung thực là chưa thể khẳng định chất lượng cải thiện vượt bậc, do hai nguyên nhân: (1) Tập test chỉ có 100 ảnh nên độ đo mAP50 có phương sai ngẫu nhiên tương đối lớn; (2) Số lượng ảnh train của tập dữ liệu khá nhỏ (~180 ảnh) và số epoch huấn luyện chỉ là 20, khiến mạng chưa khai thác hết ưu thế của nhãn sạch.

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối cùng:**
- Pipeline hiện tại kết luận: **Hold** (tỉ lệ ảnh có cảnh báo là 18.72%, cao hơn ngưỡng quy định 10.00%).
- **Hành động để chuyển thành Release:** Cần cấp thêm ngân sách người duyệt (`budget_images`) từ 80 ảnh lên khoảng 125 ảnh để đội ngũ kiểm duyệt xem xét nốt 45 ảnh nghi vấn còn lại trong hàng đợi, hoặc phân công reviewer duyệt thủ công các ảnh trong `05_review_queue.csv` và chạy lệnh với cờ `--resume-after-review`. Khi tỉ lệ cảnh báo chưa duyệt hạ xuống dưới 10%, pipeline sẽ tự động chuyển sang **Release**.

**(b) Ghi chú sử dụng AI:**
- *Prompt chính:* "Đọc docstring của 4 file (label_format, second_opinion, autofix, gate) và các file test tương ứng, viết code hoàn chỉnh thỏa mãn toàn bộ unit test TDD và quy định xử lý biên của Day 09."
- *Cách kiểm tra code AI:* Chạy lệnh `python -m pytest -q` để kiểm tra nghiêm ngặt toàn bộ 79 test cases; chạy thử nghiệm end-to-end qua `pipeline.run` và so sánh đối chiếu kết quả với các file CSV báo cáo trong `submission/reports/`.
- *Một lần AI sai:* Khi phân tích sweep calibration, ban đầu AI đề xuất chọn `phash_dist = 16` vì thấy F1 trên tập calib đạt cao nhất (0.91), nhưng khi áp dụng thực tế trên tập raw thì phát hiện `dist = 16` làm số ảnh bị nghi rò rỉ test nhảy vọt lên 11 ảnh (False Positives cao, xoá nhầm ảnh sạch). Sau đó đã được hiệu chỉnh về `phash_dist = 6`.

**(c) Phần thưởng CVAT (Tùy chọn):**
- Khi đưa ảnh từ `work/run/ds/images/` vào CVAT và áp dụng bộ lọc `width < 20`: Bộ lọc phát hiện các bounding box siêu nhỏ ở hậu cảnh (ví dụ các xe ô tô đỗ rất xa trong `img_0007` hoặc người đi bộ xa trong `img_0030`).
- Đối chiếu với pipeline: CVAT lọc theo kích thước tuyệt đối pixel (20px), trong khi pipeline dự án đặt ngưỡng cạnh ngắn < 12px cho cảnh báo `BOX_TINY`.
- Ý nghĩa thuộc tính `can_review`: Thuộc tính này được người gán nhãn thủ công đánh dấu khi gặp vật thể khó, mờ nhạt hoặc không chắc chắn về nhãn lớp. Trong hệ thống tự động hóa, thông tin này tương đương với danh sách ảnh nghi vấn được sinh ra từ module `second_opinion` và được chấm điểm ưu tiên trong hàng đợi `05_review_queue.csv`.
