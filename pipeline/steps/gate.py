"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from collections import Counter

from ..common import ERROR, WARN

_EPS = 1e-9   # tránh sai số số thực ở biên (vd. 3/30 so với 0.1)


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    threshold = cfg["gate"]["warn_ratio_hold"]
    stems = set(image_stems)
    reviewed = set(reviewed)
    n_images = len(stems)

    # Lỗi bắt buộc: đếm TẤT CẢ (kể cả lỗi cấp dataset như data.yaml, kể cả ảnh đã duyệt)
    errors = [i for i in issues if i.severity == ERROR]
    n_errors = len(errors)

    # Cảnh báo: đếm ẢNH (không đếm issue), chỉ ảnh còn trong lô và chưa được người duyệt
    warn_images = {i.image for i in issues if i.severity == WARN and i.image in stems and i.image not in reviewed}
    n_warn = len(warn_images)
    ratio = n_warn / n_images if n_images else 0.0

    if n_errors:
        decision = "Rework"
        by_code = ", ".join(f"{c} ×{n}" for c, n in sorted(Counter(i.code for i in errors).items()))
        reasons = [f"còn {n_errors} lỗi bắt buộc ({by_code}): phải sửa trước khi phát hành; người duyệt cũng không được bỏ qua lỗi bắt buộc"]
    elif ratio >= threshold - _EPS:
        decision = "Hold"
        reasons = [f"{n_warn}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo chưa được người duyệt, ≥ ngưỡng Hold {threshold:.0%}"]
    else:
        decision = "Release"
        reasons = [f"không còn lỗi bắt buộc; {n_warn}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo, dưới ngưỡng Hold {threshold:.0%}"]

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn,
        "n_images": n_images,
        "warn_ratio": round(ratio, 4),
        "reasons": reasons,
    }
