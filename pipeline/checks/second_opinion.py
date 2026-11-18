"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []
    so_cfg = cfg["second_opinion"]
    conf_thresh = so_cfg["conf"]
    min_area_px = so_cfg["min_area_px"]
    fp_conf = so_cfg["fp_conf"]
    iou_missing = so_cfg["iou_missing"]
    iou_match = so_cfg["iou_match"]
    iou_loose = so_cfg["iou_loose"]

    for img_path in ds.image_files():
        stem = img_path.stem
        if stem not in preds:
            continue
        raw_lines = ds.read_label_lines(stem)
        if raw_lines is None:
            continue

        sz = ds.image_size(stem)
        if sz is None:
            continue
        W, H = sz

        # Lấy các nhãn hợp lệ kèm số dòng gốc
        valid_label_boxes = []
        for line_no, ln in raw_lines:
            try:
                c, cx, cy, w, h = parse_yolo_line(ln)
            except ValueError:
                continue
            if 0 <= c < len(ds.classes):
                valid_label_boxes.append((line_no, c, (cx, cy, w, h)))

        all_preds = preds[stem]

        # 1. Tập dự đoán P (đã lọc conf và diện tích)
        P = []
        for p in all_preds:
            p_cls, p_conf = int(p[0]), float(p[1])
            p_box = (float(p[2]), float(p[3]), float(p[4]), float(p[5]))
            area_px = p_box[2] * W * p_box[3] * H
            if p_conf >= conf_thresh and area_px >= min_area_px:
                P.append((p_cls, p_conf, p_box))

        for p_cls, p_conf, p_box in P:
            cands = []
            for line_no, l_cls, l_box in valid_label_boxes:
                iou = iou_xywh(p_box, l_box)
                if iou >= iou_missing:
                    cands.append((l_cls, iou, line_no))

            if not cands:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy {ds.classes[p_cls]} (conf {p_conf:.2f}) nhưng không có nhãn",
                                    line=None, extra={"conf": p_conf}))
            else:
                same_class = [c for c in cands if c[0] == p_cls]
                if same_class:
                    best_same = max(same_class, key=lambda x: x[1])
                    if best_same[1] < iou_loose:
                        issues.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                                            f"box nhãn {ds.classes[p_cls]} lệch với model (IoU {best_same[1]:.2f} < {iou_loose})",
                                            line=None, extra={"iou": round(best_same[1], 4), "conf": p_conf}))
                else:
                    best_diff = max(cands, key=lambda x: x[1])
                    if best_diff[1] >= iou_match:
                        issues.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                                            f"model đoán {ds.classes[p_cls]} (conf {p_conf:.2f}), nhãn ghi {ds.classes[best_diff[0]]}",
                                            line=None, extra={"conf": p_conf, "iou": round(best_diff[1], 4)}))

        # 2. FALSE POSITIVE: nhãn không khớp dự đoán nào (lọc theo fp_conf, không lọc diện tích)
        fp_preds = [(float(p[2]), float(p[3]), float(p[4]), float(p[5]))
                    for p in all_preds if float(p[1]) >= fp_conf]
        for line_no, l_cls, l_box in valid_label_boxes:
            if not any(iou_xywh(l_box, pb) >= iou_missing for pb in fp_preds):
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"box nhãn dòng {line_no} không khớp dự đoán nào của model",
                                    line=line_no))

    return issues