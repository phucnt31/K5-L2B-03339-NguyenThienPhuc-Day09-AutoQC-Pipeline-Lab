"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict
import yaml

from ..common import ERROR, parse_yolo_line


def fix(ds, issues, cfg):
    err_issues = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1. Đổi tên lớp trong data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in err_issues):
        if ds.yaml_path.exists():
            content = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
            before_names = str(content.get("names", ""))
            content["names"] = list(cfg["classes"])
            ds.yaml_path.write_text(yaml.safe_dump(content, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": before_names,
                "after": str(cfg["classes"]),
            })

    # 2. Xoá ảnh lỗi cửa vào (ảnh hỏng, trùng lặp, rò rỉ...)
    rem_codes = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    removed_stems = set()
    for i in err_issues:
        if i.code in rem_codes or i.code.startswith("DUP_IMAGE_"):
            stem = i.image
            if stem not in removed_stems:
                removed_stems.add(stem)
                img_p = ds.image_path(stem)
                lbl_p = ds.label_path(stem)
                if img_p and img_p.exists():
                    img_p.unlink()
                if lbl_p and lbl_p.exists():
                    lbl_p.unlink()
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "remove_image",
                    "before": str(img_p or stem),
                    "after": "(đã xoá)",
                })

    # 3. Ảnh thiếu file nhãn: chuyển người gán
    needs_label_stems = set()
    for i in err_issues:
        if i.code == "MISSING_LABEL_FILE":
            stem = i.image
            if stem not in removed_stems and stem not in needs_label_stems:
                needs_label_stems.add(stem)
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })

    # 4. Sửa các dòng nhãn lỗi
    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    img_line_issues = defaultdict(lambda: defaultdict(list))
    for i in err_issues:
        if i.image in removed_stems:
            continue
        if i.line is not None and (i.code in drop_codes or i.code == "BOX_OUT_OF_IMAGE"):
            img_line_issues[i.image][i.line].append(i.code)

    for stem, lines_dict in img_line_issues.items():
        lbl_p = ds.label_path(stem)
        if not lbl_p.exists():
            continue
        orig_lines = lbl_p.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = []
        file_fixes = []

        for idx, orig_text in enumerate(orig_lines):
            line_no = idx + 1
            if line_no not in lines_dict:
                new_lines.append(orig_text)
                continue

            codes = set(lines_dict[line_no])
            # Xoá dòng thắng clip_box nếu cùng gặp trên 1 dòng
            if codes & drop_codes:
                file_fixes.append({
                    "image": stem,
                    "line": line_no,
                    "action": "drop_line",
                    "before": orig_text,
                    "after": "(đã xoá)",
                })
            elif "BOX_OUT_OF_IMAGE" in codes:
                try:
                    c, cx, cy, w, h = parse_yolo_line(orig_text)
                    x1, x2 = cx - w / 2, cx + w / 2
                    y1, y2 = cy - h / 2, cy + h / 2
                    cx1 = max(0.0, min(1.0, x1))
                    cx2 = max(0.0, min(1.0, x2))
                    cy1 = max(0.0, min(1.0, y1))
                    cy2 = max(0.0, min(1.0, y2))
                    nw = cx2 - cx1
                    nh = cy2 - cy1
                    if nw <= 0 or nh <= 0:
                        # Box nằm hẳn ngoài ảnh -> xoá dòng
                        file_fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "drop_line",
                            "before": orig_text,
                            "after": "(đã xoá)",
                        })
                    else:
                        nx = (cx1 + cx2) / 2
                        ny = (cy1 + cy2) / 2
                        clipped_text = f"{int(c)} {nx:.6f} {ny:.6f} {nw:.6f} {nh:.6f}"
                        new_lines.append(clipped_text)
                        file_fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "clip_box",
                            "before": orig_text,
                            "after": clipped_text,
                        })
                except ValueError:
                    file_fixes.append({
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": orig_text,
                        "after": "(đã xoá)",
                    })

        if new_lines:
            lbl_p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            lbl_p.write_text("", encoding="utf-8")

        fixes.extend(file_fixes)

    return fixes