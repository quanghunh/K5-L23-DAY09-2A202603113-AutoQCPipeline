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

NAME = "second_opinion"


def _labels_with_lines(ds, stem):
    """[(số dòng gốc, lớp, (cx, cy, w, h))] của các dòng parse được và có id lớp hợp lệ (cùng tiêu chí với ds.valid_boxes)."""
    out = []
    for ln, text in ds.read_label_lines(stem) or []:
        try:
            cls, cx, cy, w, h = parse_yolo_line(text)
        except (ValueError, OverflowError):
            continue
        if 0 <= cls < len(ds.classes):
            out.append((ln, cls, (cx, cy, w, h)))
    return out


def run(ds, cfg, preds=None):
    so = cfg["second_opinion"]
    conf_min, min_area = so["conf"], so["min_area_px"]
    fp_conf, iou_missing = so["fp_conf"], so["iou_missing"]
    iou_match, iou_loose = so["iou_match"], so["iou_loose"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []
    for path in ds.image_files():
        stem = path.stem
        if stem not in preds or not ds.label_path(stem).exists():
            continue                                           # không có dự đoán hoặc chưa có file nhãn: không có gì để so
        size = ds.image_size(stem)
        if size is None:
            continue
        width, height = size
        labels = _labels_with_lines(ds, stem)
        rows = preds[stem]

        # (A) mỗi dự đoán đủ tin cậy & đủ lớn: nhãn có phủ vật đó không, đúng lớp không, box có khít không
        for cls_p, conf, cx, cy, w, h in rows:
            if conf < conf_min or (w * width) * (h * height) < min_area:
                continue
            box_p = (cx, cy, w, h)
            cands = [(iou, cls_l) for _, cls_l, box_l in labels if (iou := iou_xywh(box_p, box_l)) >= iou_missing]
            if not cands:
                issues.append(Issue(NAME, WARN, "POSSIBLE_MISSING", stem, f"model thấy lớp {cls_p} (conf {conf:.2f}) mà nhãn không có box nào khớp",
                                    extra={"conf": conf, "pred_class": cls_p}))
                continue
            same = [iou for iou, cls_l in cands if cls_l == cls_p]
            if same:
                best = max(same)
                if best < iou_loose:
                    issues.append(Issue(NAME, WARN, "POSSIBLE_LOOSE_BOX", stem, f"box cùng lớp {cls_p} nhưng IoU chỉ {best:.2f} < {iou_loose}: lỏng/lệch?",
                                        extra={"conf": conf, "iou": round(best, 4)}))
                continue                                       # có nhãn đúng lớp phủ vật này: không cờ
            best = max(iou for iou, _ in cands)                # chỉ có nhãn khác lớp
            if best >= iou_match:
                label_class = max(cands)[1]
                issues.append(Issue(NAME, WARN, "POSSIBLE_WRONG_CLASS", stem, f"model nói lớp {cls_p} (conf {conf:.2f}), nhãn ghi lớp {label_class} (IoU {best:.2f})",
                                    extra={"conf": conf, "iou": round(best, 4), "pred_class": cls_p, "label_class": label_class}))
            # IoU trong [iou_missing, iou_match): mơ hồ -> không cờ

        # (B) mỗi box nhãn: có dự đoán nào (conf >= fp_conf, KHÔNG lọc diện tích) khớp không
        ref = [r for r in rows if r[1] >= fp_conf]
        for ln, _cls_l, box_l in labels:
            best = max((iou_xywh(box_l, r[2:6]) for r in ref), default=0.0)
            if best < iou_missing:
                issues.append(Issue(NAME, WARN, "POSSIBLE_FALSE_POS", stem, f"box nhãn không khớp vật nào model thấy (IoU tốt nhất {best:.2f})", ln,
                                    {"iou": round(best, 4)}))
    return issues
