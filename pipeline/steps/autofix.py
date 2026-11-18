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

REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODE = "BOX_OUT_OF_IMAGE"


def _rec(image, line, action, before, after):
    return {"image": image, "line": line, "action": action, "before": before, "after": after}


def _names_text(names):
    return ", ".join(f"{k}: {v}" for k, v in sorted(names.items())) or "(không có)"


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]       # cảnh báo là việc của người: không đụng tới
    fixes = []

    # ---- 1) xoá ảnh (+ nhãn) bị loại. Làm TRƯỚC để các issue dòng của ảnh này bị bỏ qua êm.
    removed = set()
    for i in errors:
        if i.code not in REMOVE_CODES or i.image in removed:
            continue
        removed.add(i.image)
        img, lab = ds.image_path(i.image), ds.label_path(i.image)
        if img is None and not lab.exists():
            continue                                           # đã xoá từ trước (chạy lại): không ghi gì thêm
        before = f"{(img or lab).name} ({i.code})"
        if img is not None:
            img.unlink(missing_ok=True)
        lab.unlink(missing_ok=True)
        ds._size_cache.pop(i.image, None)
        fixes.append(_rec(i.image, None, "remove_image", before, "(đã xoá ảnh và nhãn)"))

    # ---- 2) sửa dòng nhãn: gom theo file, theo SỐ DÒNG GỐC, ghi lại MỘT lần
    todo = defaultdict(lambda: defaultdict(list))              # stem -> số dòng -> [mã lỗi]
    for i in errors:
        if (i.code in DROP_CODES or i.code == CLIP_CODE) and i.line is not None and i.image not in removed:
            todo[i.image][i.line].append(i.code)

    for stem in sorted(todo):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()   # cùng cách đếm dòng với Dataset.read_label_lines
        out, changed = [], False
        for n, text in enumerate(raw, 1):
            codes = todo[stem].get(n)
            if not codes or not text.strip():
                out.append(text)
                continue
            before = text.strip()
            if any(c in DROP_CODES for c in codes):            # dòng có 2 lỗi: xoá thắng, chỉ ghi 1 fix
                fixes.append(_rec(stem, n, "drop_line", before, "(đã xoá dòng)"))
                changed = True
                continue
            try:                                               # chỉ còn BOX_OUT_OF_IMAGE: cắt box về trong ảnh
                cls, cx, cy, w, h = parse_yolo_line(text)
            except (ValueError, OverflowError):
                out.append(text)                               # không hiểu dòng này: để nguyên, QC vòng sau sẽ báo
                continue
            left, right = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
            top, bottom = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
            nw, nh = right - left, bottom - top
            changed = True
            if nw <= 0 or nh <= 0:                             # nằm hẳn ngoài ảnh: xoá, không ghi box rỗng/âm
                fixes.append(_rec(stem, n, "drop_line", before, "(đã xoá dòng: box nằm hẳn ngoài ảnh)"))
                continue
            new = f"{cls} {(left + right) / 2:.6f} {(top + bottom) / 2:.6f} {nw:.6f} {nh:.6f}"
            out.append(new)
            fixes.append(_rec(stem, n, "clip_box", before, new))
        if changed:
            path.write_text("".join(x + "\n" for x in out), encoding="utf-8")

    # ---- 3) ảnh chưa có file nhãn: máy không bịa nhãn, không tạo file (kể cả rỗng) -> chuyển người gán
    seen = set()
    for i in errors:
        if i.code != "MISSING_LABEL_FILE" or i.image in removed or i.image in seen:
            continue
        seen.add(i.image)
        if ds.image_path(i.image) is None or ds.label_path(i.image).exists():
            continue                                           # issue cũ: ảnh đã biến mất hoặc đã có nhãn
        fixes.append(_rec(i.image, None, "needs_label", "(không có file)", "chuyển người gán"))

    # ---- 4) tên lớp trong data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        want = {k: v for k, v in enumerate(cfg["classes"])}
        current = ds.yaml_names()
        if current != want:
            data = {}
            if ds.yaml_path.exists():
                data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
                if not isinstance(data, dict):
                    data = {}
            data["names"] = list(cfg["classes"]) if isinstance(data.get("names"), list) else want   # giữ kiểu list/dict của file gốc
            ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append(_rec("data.yaml", None, "rename_classes", _names_text(current), _names_text(want)))

    return fixes
