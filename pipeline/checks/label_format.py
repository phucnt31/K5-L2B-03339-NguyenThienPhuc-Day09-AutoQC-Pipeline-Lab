"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    issues = []
    c_fmt = cfg["label_format"]
    overflow_tol = c_fmt["overflow_tol"]
    dup_iou_thresh = c_fmt["dup_box_iou"]
    min_box_px = c_fmt["min_box_px"]
    max_box_frac = c_fmt["max_box_frac"]
    num_classes = len(ds.classes)

    for lf in ds.label_files():
        stem = lf.stem
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue
        size = ds.image_size(stem)
        valid_boxes = []

        for line_no, text in lines:
            try:
                c, cx, cy, w, h = parse_yolo_line(text)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, "sai định dạng 5 cột", line=line_no))
                continue

            if not (0 <= c < num_classes):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} không hợp lệ", line=line_no))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"kích thước không dương: w={w}, h={h}", line=line_no))
                continue

            # Kiểm tra tràn viền ngoài khoảng [0, 1]
            x1, x2 = cx - w / 2, cx + w / 2
            y1, y2 = cy - h / 2, cy + h / 2
            overflow = max(0.0, -x1, x2 - 1.0, -y1, y2 - 1.0)
            if overflow > overflow_tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ảnh {overflow:.4f}", line=line_no,
                                    extra={"overflow": overflow}))

            # Kiểm tra trùng lặp box với dòng trước đó
            curr_box = (cx, cy, w, h)
            for prev_c, prev_box in valid_boxes:
                if c == prev_c and iou_xywh(curr_box, prev_box) > dup_iou_thresh:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                        "trùng box với dòng trước", line=line_no))
                    break
            valid_boxes.append((c, curr_box))

            # Kiểm tra kích thước nhỏ (cạnh ngắn tính theo px)
            if size is not None:
                W, H = size
                short_side_px = min(w * W, h * H)
                if short_side_px < min_box_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                        f"cạnh ngắn {short_side_px:.1f}px < {min_box_px}px", line=line_no))

            # Kiểm tra box quá lớn so với diện tích ảnh
            if w * h > max_box_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                    f"diện tích {w * h:.2f} > {max_box_frac}", line=line_no))

    return issues