# Báo cáo Day 09 — Huỳnh Nhật Quang, 2A202603113


## 1. Kết luận trước
Pipeline ra **Hold**, chưa phải Release.

Lô có 224 ảnh. Ở cửa vào pipeline loại 19 ảnh, còn 205 ảnh đi tiếp và được xuất ra `export/clean_v1`. Đây chỉ là **bản nháp** (trong `manifest.json` ghi `decision: Hold`), chưa phát hành được.

Lỗi bắt buộc thì đã hết: `07_error_list_v3` có 0 lỗi `error`. Vướng ở chỗ còn **38/205 ảnh (18,5%)** có cảnh báo mà chưa ai xem, trong khi ngưỡng Hold là 10% (tức tối đa 20 ảnh). Hàng đợi có 125 ảnh nhưng người duyệt chỉ có 80 suất, nên 45 ảnh bị bỏ lại. Số này đã giảm so với lần chạy đầu (60 ảnh, 29,3%) sau khi calibrate, nhưng vẫn chưa đủ để Release.

## 2. Lỗi và phân việc
Số liệu lấy từ `02_error_list_v1` (lúc chưa sửa gì). Lỗi ở cửa vào tính trên 224 ảnh, lỗi QC tính trên 205 ảnh.

| Mã lỗi | Số dòng / số ảnh | Ai sửa | Vì sao |
|---|---:|---|---|
| `DUP_IMAGE_EXACT` | 8 ảnh | máy (loại ảnh) | trùng y hệt từng byte, máy so là ra |
| `LEAK_TEST` | 4 ảnh | máy (loại ảnh) | trùng với ảnh test, giữ lại thì kết quả train bị đẹp giả |
| `BAD_SIZE` | 3 ảnh | máy (loại ảnh) | ảnh nhỏ quá, cạnh ngắn dưới 250px |
| `CORRUPT_IMAGE` | 2 ảnh | máy (loại ảnh) | ảnh không mở được |
| `DUP_IMAGE_NEAR` | 2 ảnh | máy (loại ảnh) | gần giống nhau theo phash |
| `BAD_CLASS_ID` | 6 dòng / 6 ảnh | máy (xoá dòng) | id lớp lạ (93, 4, 7, −1), không biết gán lại thành lớp nào nên xoá |
| `BAD_FORMAT` | 3 dòng / 3 ảnh | máy (xoá dòng) | dòng thiếu cột hoặc có `nan` |
| `BOX_ZERO` | 4 dòng / 4 ảnh | máy (xoá dòng) | box có rộng hoặc cao bằng 0 |
| `DUP_BOX` | 7 dòng / 7 ảnh | máy (xoá dòng) | box bị lặp, xoá dòng sau là an toàn |
| `BOX_OUT_OF_IMAGE` | 8 dòng / 8 ảnh | máy (cắt box vào trong ảnh) | box tràn ra ngoài 0,023–0,06, cắt lại là xong, lớp giữ nguyên |
| `BAD_CLASS_NAME` | 2 dòng / 1 file `data.yaml` | máy (ghi lại tên lớp) | `Person`, `Bus` viết hoa sai |
| `MISSING_LABEL_FILE` | 6 ảnh | **người** | không có file nhãn, máy không được tự bịa nhãn |
| `POSSIBLE_MISSING` | 53 dòng / 52 ảnh | **người** | model thấy vật mà nhãn không có, phải có người nhìn mới biết |
| `POSSIBLE_LOOSE_BOX` | 28 dòng / 24 ảnh | **người** | box có vẻ lỏng, cần người xem |
| `POSSIBLE_FALSE_POS` | 29 dòng / 27 ảnh | **người** | box nhãn không khớp vật nào model thấy |
| `POSSIBLE_WRONG_CLASS` | 18 dòng / 18 ảnh | **người** | nghi gán nhầm lớp (xe tải/xe con/bus), đây là lỗi về ý nghĩa nên máy không quyết được |

Sửa xong thì thế này: ở vòng QC đầu có 36 lỗi bắt buộc, máy sửa được 35 thay đổi trong `03_fixes.csv` (20 xoá dòng, 8 cắt box, 6 chuyển cho người gán nhãn, 1 sửa tên lớp). Còn lại 6 lỗi ở `04_error_list_v2`, toàn là ảnh thiếu file nhãn. Sau khi người duyệt (mô phỏng) gán nhãn cho 6 ảnh đó thì `07_error_list_v3` hết lỗi.

**Về hàng đợi (`05_review_queue.csv`, 125 ảnh):** điểm ưu tiên của mỗi ảnh là cộng các trọng số trong `review.weights` của những cảnh báo trên ảnh đó. Cảnh báo của `second_opinion` còn được nhân thêm `1 + conf`. Ảnh bị máy sửa được cộng thêm điểm, ảnh thiếu nhãn cộng 10. Nên ảnh nào nhiều cảnh báo nặng thì lên đầu: `img_0020` đứng nhất (11,5 điểm) vì dính cả dòng bị máy xoá, `POSSIBLE_MISSING` lẫn `POSSIBLE_WRONG_CLASS`. 6 ảnh thiếu nhãn (10 điểm mỗi ảnh) đứng ngay sau, ở vị trí 2–7, nên đều được duyệt. Số cảnh báo ít đi nhờ `conf` cao hơn nên điểm của các ảnh khác thấp xuống, ảnh thiếu nhãn vì vậy lên cao hơn lần chạy đầu (khi đó nằm ở vị trí 17–22).

80 suất là 64% hàng đợi. Có 103 ảnh dính cảnh báo ngữ nghĩa, người duyệt xem được 74 ảnh. Tính theo cảnh báo thì 94/123 cái (76%) nằm trên ảnh đã duyệt, 29 cái còn lại nằm trên ảnh không ai xem.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **4** | `DUP_IMAGE_NEAR`: 1,00 / 0,50 → 1,00 / 0,67 (`DUP_IMAGE_EXACT` giữ 1,00 / 1,00) | Mã này tự động loại ảnh, nên tôi ưu tiên precision. Calib cho precision 1,00 ở mọi giá trị nên không dùng precision để chọn được. Recall tăng từ 0,50 lên 0,67 ở giá trị 4 rồi đứng yên đến 14, nên tôi lấy số nhỏ nhất trên đoạn bằng phẳng đó: được cái lợi mà ít rủi ro gộp nhầm hai ảnh khác nhau trên dữ liệu thật. Tôi không lấy 16 (recall 0,83) vì nó sát mép 20, nơi `DUP_IMAGE_EXACT` tụt xuống 0,33. Tham số này còn dùng cho `LEAK_TEST`, nên một ảnh bị gộp nhầm là mất ảnh tốt. |
| `second_opinion.conf` | 0.25 | **0.6** | `POSSIBLE_MISSING`: 0,50 / 1,00 → 0,57 / 1,00. `POSSIBLE_WRONG_CLASS`: 0,56 / 0,83 → 0,62 / 0,83. `POSSIBLE_LOOSE_BOX`: 0,29 / 0,40 → 0,20 / 0,20 (xấu đi). `POSSIBLE_FALSE_POS`: 0,31 / 1,00 không đổi | Đây là cảnh báo để người xem, nên tôi chấp nhận precision thấp để giữ recall: bỏ sót một lỗi là lỗi đó nằm luôn trong dataset, còn cờ thừa chỉ tốn thời gian người duyệt. 0,6 là giá trị cao nhất mà `POSSIBLE_MISSING` còn giữ recall 1,00 (ở 0,7 tụt xuống 0,88, ở 0,8 xuống 0,75). Lên đến 0,6 thì precision của nó tăng 0,50 → 0,57 và `POSSIBLE_WRONG_CLASS` cũng nhỉnh lên. Cái giá phải trả là `POSSIBLE_LOOSE_BOX` kém đi (bắt 1/5 ca thay vì 2/5). Tôi chấp nhận vì mã này vốn kém ở mọi mức `conf` (F1 không vượt quá 0,46), và nó có trọng số duyệt thấp nhất trong `review.weights` (1,5 so với 3 của nhầm lớp, 2 của thiếu nhãn). Kết quả ở raw: cảnh báo ngữ nghĩa giảm rõ (hàng đợi 145 → 125 ảnh, ảnh còn cảnh báo chưa duyệt 60 → 38). |

**Một chỗ calibration có thể đánh lừa bạn:** bảng `conf` ở giá trị 0,8 trông rất đẹp với `POSSIBLE_WRONG_CLASS` (1,00 / 0,83 / F1 0,91, cao nhất bảng). Nhưng calib chỉ chèn 6 ca nhầm lớp, và con số đó đạt được chỉ vì 4 cờ sai biến mất, tức một chênh lệch rất nhỏ trên mẫu quá ít. Cùng lúc đó `POSSIBLE_MISSING` mất 2/8 ca (recall 0,75), mà thiếu nhãn là loại lỗi dễ lọt thẳng vào dataset. Ngoài ra `docs/CALIBRATION.md` nói calib chủ yếu chèn lỗi person→car còn raw nghiêng về car/truck/bus, nên số đẹp ở 0,8 chưa chắc đúng trên raw. Vì vậy tôi không chọn 0,8 dù F1 của một ô trông tốt hơn.

Với `phash_dist` thì bằng chứng nằm ở raw: đổi từ 2 sang 4 làm recall calib tăng 0,50 → 0,67, nhưng ở bước 1 trên raw số ảnh bị loại vẫn đúng 19 ảnh như trước (8 `DUP_IMAGE_EXACT`, 4 `LEAK_TEST`, 3 `BAD_SIZE`, 2 `CORRUPT_IMAGE`, 2 `DUP_IMAGE_NEAR`). Hai ảnh `DUP_IMAGE_NEAR` đó (`img_0076` giống `img_0042`, `img_0143` giống `img_0037`) có phash cách nhau 0, tôi mở ra xem thì đúng là cùng một ảnh nhưng bản sau bị thu nhỏ còn khoảng 90%. Tức là lợi ích 0,50 → 0,67 chỉ có trên calib chứ trên raw không thấy thêm ảnh nào, nên đừng đọc con số recall đó như "bắt được nhiều hơn trên dữ liệu thật". Calib cũng còn 2/6 ca near mà không ngưỡng nào ≤ 14 bắt được (FN), đó là điểm mù đã biết.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) **Gate có chặn thật.** Tôi chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`, tức là không có ai duyệt nên ảnh thiếu file nhãn cứ nằm đó. Kết quả: vòng 2 còn 6 lỗi bắt buộc, và sau vòng 3 gate kết luận **REWORK** vì còn 6 lỗi `MISSING_LABEL_FILE`, kèm câu "người duyệt cũng không được bỏ qua lỗi bắt buộc". Bước 5 in ra "KHÔNG xuất: còn lỗi bắt buộc (Rework)" nên không có dataset nào được tạo ra (thư mục `work/exp_nb` không hề được tạo ra). Mã thoát của Rework là 20 theo quy ước của pipeline. So với lần chạy thật (ngân sách 80), thì chính người duyệt là bước làm 6 ảnh thiếu nhãn được gán nhãn xong và hết lỗi bắt buộc.

(b) Mấy chỗ pipeline không làm được, tôi thấy qua báo cáo:
- **Máy không biết ai đúng, nhãn hay model.** 80 ảnh đã được thay bằng nhãn người rồi mà `07_error_list_v3` vẫn còn 28 cảnh báo ngữ nghĩa trên những ảnh đó (25/80 ảnh vẫn bị cờ). Tức là model lớn còn cãi cả nhãn người. `second_opinion` chỉ nói được là "hai bên khác nhau", chứ không nói bên nào sai, nên nó dễ báo thừa.
- **Nhãn rỗng: ảnh nền hay bị bỏ sót?** Ở v3 còn 4 ảnh file nhãn rỗng (`EMPTY_LABEL`: `img_0013`, `img_0097`, `img_0129`, `img_0192`). Máy không phân biệt được ảnh thật sự không có vật nào với ảnh bị quên gán, nên chỉ cảnh báo thôi.
- **Ngưỡng 12px của `BOX_TINY` là ranh giới cứng.** Ở v3 có 7 box bị cờ, trong đó 6 box nằm sát dưới ngưỡng (từ 10,3 đến 11,9px, ví dụ `img_0161` dòng 2–4), trong khi box 12,1px thì qua luôn không bị cờ. Chỉ chênh vài phần mười pixel mà kết quả khác hẳn.
- **Ảnh trùng bị thu nhỏ mạnh hơn.** Calib còn 2/6 ca `DUP_IMAGE_NEAR` mà phash không bắt được ở ngưỡng 4. Hai cặp trùng bắt được trên raw đều chỉ là bản thu nhỏ khoảng 90% (phash cách nhau 0), nên chưa có gì chứng minh ảnh bị cắt hay biến đổi mạnh sẽ bị bắt.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Train trên Colab (T4) với `yolo26n`, 20 epoch, 2 seed (0 và 1), cùng siêu tham số, cùng tập val 40 ảnh và tập test 100 ảnh. Chỉ khác dữ liệu train. Số liệu lấy từ `submission/results/comparison.md`:

| biến thể | #ảnh train | seed | mAP50 (TB ± độ lệch) | mAP50-95 | precision | recall |
|---|---|---|---|---|---|---|
| raw | 224 (thực tế 213) | 2 | 0,726 ± 0,000 | 0,512 ± 0,004 | 0,764 ± 0,061 | 0,649 ± 0,028 |
| clean | 205 | 2 | 0,700 ± 0,031 | 0,486 ± 0,013 | 0,714 ± 0,073 | 0,615 ± 0,018 |

Chênh mAP50 (clean − raw) = **−0,025**. Theo từng seed: raw ra 0,7256 và 0,7259, clean ra 0,6787 và 0,7219. Độ lệch giữa hai seed của clean (0,031) lớn hơn chênh −0,025 giữa hai biến thể, nên **tôi chưa kết luận được là clean tệ hơn raw**, càng không nói được pipeline làm dữ liệu xấu đi. Với 2 seed và test 100 ảnh chỉ nên đọc là "chưa thấy clean tốt hơn raw". Độ lệch ± 0,000 của raw chỉ là hai seed tình cờ giống nhau chứ không có nghĩa raw ổn định.

**`raw` thật sự train bao nhiêu ảnh?** Cột `train_images = 224` trong file kết quả chỉ là số file ảnh. Log Ultralytics ở bước 6 báo "216 images, 19 backgrounds, 11 corrupt" và dòng "Using 213 train", tức là Ultralytics **tự bỏ 11 ảnh hỏng** (ảnh `img_0010`, `img_0136` hỏng/cắt cụt, `img_0014` và `img_0022` toạ độ tràn, `img_0099` và `img_0117` giá trị âm, `img_0020`/`img_0104`/`img_0194`/`img_0199` id lớp 93/7/4/4, `img_0179` dòng sai dạng) và chỉ train trên **213 ảnh**. Vậy khoảng cách thật giữa hai biến thể là 213 so với 205 (8 ảnh), không phải 224 so với 205 (19 ảnh). Nói cách khác, raw đã được Ultralytics "dọn" một phần các lỗi nặng nhất, nên phần lợi mà pipeline mang lại bị thu hẹp lại. Ở bước 5 của notebook, số box theo lớp của raw còn có các token lớp sai (`-1`×2, `4`×2, `7`×1, `93`×1), còn clean chỉ có đúng 4 lớp 0–3 (car 102, person 576, truck 42, bus 33; raw: 122 / 537 / 32 / 35).

**Một điều tôi thấy trong log và nghĩ là quan trọng hơn cả chênh −0,025:** ở cả 4 lần train, checkpoint `best.pt` thực chất là của **epoch 1**. Điểm val của `best.pt` (0,803 / 0,801 / 0,776 / 0,793 cho raw0, raw1, clean0, clean1) gần như trùng điểm val sau epoch 1 (0,801 / 0,800 / 0,775 / 0,792), trong khi các epoch sau đều thấp hơn và dao động mạnh (ví dụ epoch 20: 0,728 / 0,705 / 0,591 / 0,666). Tức là điểm test ở trên về cơ bản là của mô hình mới tinh chỉnh khoảng 1 epoch từ trọng số pretrained, chứ không phải của 20 epoch học trên dữ liệu của tôi. Với ~200 ảnh và `optimizer=auto`, huấn luyện lâu hơn không cải thiện val mà còn làm xấu đi. Nên so sánh này đo "độ nhiễu của epoch 1" nhiều hơn là chất lượng dữ liệu, và con số −0,025 càng không đáng tin.

Theo lớp (trung bình 2 seed, AP50): truck raw 0,648 → clean 0,559 (−0,089), bus 0,695 → 0,667 (−0,028), car 0,738 → 0,749 (+0,011), person 0,822 → 0,827 (+0,005). Phần chênh lớn nhất nằm ở truck và bus, đúng hai lớp ít box nhất (42 và 33 trên khoảng 750 box), và bus của clean dao động rất mạnh giữa hai seed (0,598 so với 0,736). Tôi không đọc chênh này là "pipeline hại xe tải".

**Giả thuyết giải thích và cách kiểm:**
1. **Nhiễu do test nhỏ, ít seed và `best.pt` chọn ở epoch 1.** Cách kiểm: chạy thêm seed (5 trở lên), hoặc đổi cấu hình để training thật sự cải thiện val (ví dụ giảm learning rate, tăng epoch, hoặc dùng `last.pt`), rồi xem chênh có ổn định cùng dấu không.
2. **`raw` có thể được lợi vì còn ảnh rò rỉ test và ảnh trùng.** Raw giữ nguyên 4 ảnh `LEAK_TEST` (trùng tập test) cùng 8 ảnh `DUP_IMAGE_EXACT` và 2 `DUP_IMAGE_NEAR` (từ `01_intake.csv`), còn clean đã loại hết. Tôi chưa đo được mức thổi phồng và cũng chưa kiểm 4 ảnh rò rỉ có nằm trong 213 ảnh raw thật sự train không. Cách kiểm: train thêm raw đã bỏ đúng 4 ảnh `LEAK_TEST` rồi so lại mAP50.
3. **`clean` ít ảnh hơn và còn nhãn chưa sạch.** Pipeline kết luận Hold nên còn 38 ảnh có cảnh báo chưa ai duyệt, và "người duyệt" chỉ là mô phỏng sao chép nhãn tham chiếu, nên `clean_v1` chưa phải dữ liệu sạch hoàn toàn. Cách kiểm: so với biến thể `oracle` (nhãn người) để biết chặn trên, hoặc duyệt thêm phần hàng đợi bị bỏ lại rồi train lại.

`clean_v1` ở đây là bản **nháp**, vì kết luận của pipeline là Hold chứ chưa phát hành.

## 6. Quyết định và ghi chú AI
(a) **Quyết định cuối: Hold.** Muốn lên Release thì số ảnh còn cảnh báo chưa duyệt phải dưới 10%, tức tối đa 20 trên 205 ảnh; sau khi calibrate còn 38 (lúc đầu là 60). Phần còn lại chủ yếu là `POSSIBLE_LOOSE_BOX` (16 dòng) và `POSSIBLE_FALSE_POS` (11 dòng), đúng hai loại có precision thấp nhất trong calibration (0,20 và 0,31), nên nhiều khả năng một phần là cờ thừa, nhưng máy không tự phân biệt được. Tôi không đẩy `conf` lên 0,7 hay 0,8 chỉ để giảm số cờ, vì như đã giải thích ở mục 3 nó làm `POSSIBLE_MISSING` mất recall, tức là Release nhờ checker bị mù. Để thành Release một cách chính đáng thì cần người xem thêm nhiều ảnh hơn 80 suất, hoặc guideline của dự án chấp nhận ngưỡng cảnh báo cao hơn 10%. Tôi không đổi `warn_ratio_hold` hay `budget_images` để ép ra Release.

(b) Có dùng AI (Claude) để viết 4 module `label_format`, `gate`, `autofix`, `second_opinion`.
- **Prompt chính:** tôi nhờ AI đọc `docs/PROMPTING.md` và Bước 2 trong `GUIDE.md`, đọc nội dung hiện tại của 4 file stub cùng docstring và test, rồi viết lại đúng 4 file. Code được ghi vào repo nhưng tôi tự kiểm trước rồi mới commit.
- **Cách kiểm:** chạy `pytest` cho 4 file test của 4 module (50 test). AI còn thử thêm 9 ca ngoài test: dòng dính 2 lỗi, dòng trống giữa file, `inf` ở cột id lớp, chạy `autofix` hai lần, đúng biên 10% của gate, một ảnh có nhiều dự đoán. Sau đó tôi chạy `python -m pipeline.run` và đối chiếu với `07_error_list_v3`.
- **1 lần AI sai:** lúc đầu tôi nhờ AI vẽ 10 ảnh để xem nhãn thì nó chỉ ra 2 ảnh, rồi các ảnh sau cũng chưa chọn ngẫu nhiên và chưa có đủ cả ảnh đúng lẫn ảnh sai. Tôi phải nhắc hai lần, sau đó AI mới chọn ngẫu nhiên có cả hai loại và tôi dùng được để đối chiếu với `02_error_list_v1`.

*(Thưởng +2, tùy chọn)* CVAT: lọc `width < 20`, ảnh/số box khớp, đối chiếu `BOX_TINY` (xem docs/CVAT_FILTER.md), 1 câu về `can_review`.
