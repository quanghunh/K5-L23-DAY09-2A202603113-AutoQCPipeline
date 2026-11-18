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

NAME = "label_format"


def run(ds, cfg):
    lf = cfg["label_format"]
    tol = lf["overflow_tol"]
    min_box_px = lf["min_box_px"]
    max_box_frac = lf["max_box_frac"]
    dup_box_iou = lf["dup_box_iou"]
    n_classes = len(ds.classes)

    issues = []
    for label_path in ds.label_files():                      # đã sắp xếp theo tên -> kết quả ổn định
        stem = label_path.stem
        lines = ds.read_label_lines(stem) or []              # [(số dòng gốc, nội dung)], bỏ dòng trống
        if not lines:
            continue
        size = ds.image_size(stem)                           # None nếu không có ảnh / ảnh hỏng -> bỏ qua BOX_TINY
        kept = []                                            # (lớp, box) các dòng hợp lệ ĐÃ duyệt, để tìm box lặp

        for ln, text in lines:
            # 1) định dạng: 5 cột số. OverflowError: "inf" ở cột id lớp làm int() nổ.
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except (ValueError, OverflowError) as e:
                issues.append(Issue(NAME, ERROR, "BAD_FORMAT", stem, f"dòng không đúng 5 cột số ({e}): {text.strip()[:60]!r}", ln))
                continue

            # 2) id lớp
            if not 0 <= cls < n_classes:
                issues.append(Issue(NAME, ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls} ngoài 0..{n_classes - 1}", ln, {"class_id": cls}))
                continue

            # 3) box rỗng
            if w <= 0 or h <= 0:
                issues.append(Issue(NAME, ERROR, "BOX_ZERO", stem, f"box có rộng={w} cao={h} (phải > 0)", ln))
                continue

            # 4) tràn ảnh: mức tràn lớn nhất trong 4 mép
            overflow = max(-(cx - w / 2), (cx + w / 2) - 1, -(cy - h / 2), (cy + h / 2) - 1)
            if overflow > tol:
                issues.append(Issue(NAME, ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ra ngoài ảnh {overflow:.4f} (dung sai {tol})", ln,
                                    {"overflow": round(overflow, 6)}))

            # 5) box lặp: cùng lớp với một dòng trước đó, IoU > ngưỡng -> báo dòng SAU
            box = (cx, cy, w, h)
            for other_cls, other_box in kept:
                if other_cls == cls and iou_xywh(box, other_box) > dup_box_iou:
                    issues.append(Issue(NAME, ERROR, "DUP_BOX", stem, f"box lặp lại một box cùng lớp {cls} ở dòng trước", ln))
                    break
            kept.append((cls, box))

            # 6) cảnh báo: box quá nhỏ / quá lớn
            if size:
                short_px = min(w * size[0], h * size[1])
                if short_px < min_box_px:
                    issues.append(Issue(NAME, WARN, "BOX_TINY", stem, f"cạnh ngắn của box {short_px:.1f}px < {min_box_px}px", ln, {"short_px": round(short_px, 1)}))
            if w * h > max_box_frac:
                issues.append(Issue(NAME, WARN, "BOX_HUGE", stem, f"box phủ {w * h:.0%} diện tích ảnh (> {max_box_frac:.0%})", ln))
    return issues
