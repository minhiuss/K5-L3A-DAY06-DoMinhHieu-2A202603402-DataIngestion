# Day 06 · Data Ingestion Engineering

## Bài làm — Đỗ Minh Hiếu (2A202603402)

**Kết quả** (chọn trên dev, theo `benchmark/questions.json` → `meta.selection_rule`): **C**

| | dev Hit@1 | dev Hit@3 | test Hit@1 | test Hit@3 | filter dev / test |
|---|---|---|---|---|---|
| A fixed 500/50 | 9/15 | 12/15 | 2/5 | 2/5 | 1/3 · 1/2 |
| B paragraph ≤800 | 11/15 | 13/15 | 3/5 | 3/5 | 2/3 · 0/2 |
| C = B + filter `platform` | 11/15 | 13/15 | 3/5 | 3/5 | 3/3 · 2/2 |

Báo cáo: [report/individual/2A202603402_DoMinhHieu.md](report/individual/2A202603402_DoMinhHieu.md) · Thông tin: [STUDENT.md](STUDENT.md)

### Setup và chạy (Windows PowerShell, từ `starter/`)

1. Tải PDF (không commit, 290 MB): URL trong [data/manifest.json](data/manifest.json) → lưu vào `starter/data/Workplace_Software_and_Skills_-_WEB_IlfJtcP.pdf`.
2. Môi trường (venv đặt ở đường ngắn vì đường dẫn torch vượt 260 ký tự của Windows):
   ```powershell
   python -m venv C:\venvs\day06
   C:\venvs\day06\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env      # sửa cổng trong DATABASE_URL thành 15433
   ```
3. Database (mở Docker Desktop trước): `docker compose -p day6_student_starter up -d --wait` rồi `python scripts/check_setup.py` → `Setup OK`. Cổng host đổi **55433 → 15433** trong `docker-compose.yml` vì Windows giữ dải 55387–55486.
4. Chạy: `python -m src.run` (model `sentence-transformers/all-MiniLM-L6-v2` tự tải lần đầu, ~90 MB; đặt khác bằng `EMBEDDING_MODEL` trong `.env`).

### Đầu ra

| File | Nội dung |
|---|---|
| `data/manifest.json` | nguồn, giấy phép, trang được tính, số ký tự từng trang |
| `benchmark/questions.json` | 20 câu (15 dev / 5 test), gold page, evidence, filter, tiêu chí chọn |
| `artifacts/experiment_log.csv` | tham số + giả thuyết + kết quả A/B/C |
| `starter/results/traces.jsonl` | top-3 của mọi câu × A/B/C: chunk ID, text, score, metadata, nhãn hit |
| `starter/results/metrics.json`, `run_log.json` | Hit@1/Hit@3 dev/test, phiên bản, thời gian, thống kê chunk, kiểm tra nạp lại |
| `starter/results/audit_*.csv`, `audit_summary.json` | nhãn tay coherence, metadata, grounding |

Code pipeline: `starter/src/` (`ingestion.py`, `chunking.py`, `embeddings.py`, `store.py`, `evaluation.py`, `run.py`). Chạy lại `run.py` không ghi đè các file nhãn tay đã có.

---

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
