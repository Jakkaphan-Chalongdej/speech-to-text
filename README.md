# thai-meeting-transcribe — ปลั๊กอิน Claude Code ถอดเสียงประชุมภาษาไทย

ส่งไฟล์เสียงหรือวิดีโอการประชุมให้ Claude Code แล้วจะได้สองไฟล์:

- `ชื่อไฟล์.txt` เป็นข้อความถอดเสียงทั้งหมด มีเวลากำกับทุกบรรทัด เช่น `[00:12:34] ...` เพื่อเอาไปใช้ต่อได้
- `ชื่อไฟล์.summary.md` เป็นสรุปการประชุม มีประเด็นที่หารือ มติ งานที่ต้องทำ และประเด็นค้าง

การถอดเสียงทำบนเครื่องของคุณเองด้วย Whisper (faster-whisper) **เสียงประชุมไม่ถูกส่งออกไปภายนอก** ไม่ต้องใช้ API key และไม่มีค่าใช้จ่าย
(ข้อความถอดเสียงจะถูกส่งให้ Claude อ่านเพื่อทำสรุปตามปกติของ Claude Code)

ใช้ได้ทั้ง macOS และ Windows

## ติดตั้ง

พิมพ์ใน Claude Code:

```
/plugin marketplace add Jakkaphan-Chalongdej/speech-to-text
/plugin install thai-meeting-transcribe@speech-to-text
```

แค่นี้ก็ใช้ได้แล้ว ครั้งแรกที่สั่งถอดเสียง ถ้าเครื่องยังไม่มี `uv` (ตัวจัดการ Python ที่ปลั๊กอินใช้)
Claude จะขออนุญาตแล้วติดตั้งให้เอง ไม่ต้องติดตั้ง Python หรือ ffmpeg เอง

### ถ้าอยากติดตั้ง `uv` เอง (หรือ Claude ติดตั้งให้ไม่สำเร็จ)

macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

ติดตั้งเสร็จแล้วให้ปิดและเปิด Claude Code ใหม่

## วิธีใช้

พิมพ์ใน Claude Code ได้เลย เช่น

```
ถอดเสียงไฟล์ ~/Downloads/ประชุมทีม.m4a แล้วสรุปการประชุมให้หน่อย
```

หรือเรียกคำสั่งตรงๆ:

```
/thai-meeting-transcribe:transcribe-meeting ~/Downloads/ประชุมทีม.mp4
```

รองรับไฟล์ทั่วไป เช่น mp3, m4a, wav, mp4, mov, webm

## ควรรู้

- **ครั้งแรกจะช้ากว่าปกติ** เพราะต้องโหลดโมเดลขนาดประมาณ 1.6 GB
- **ความเร็ว:** Mac หรือ PC ที่ไม่มีการ์ดจอ NVIDIA ใช้เวลาประมาณ 10–20 นาทีต่อเสียง 1 ชั่วโมง โน้ตบุ๊กสเปกต่ำอาจช้ากว่านี้
  ถ้าอยากให้เร็วขึ้น บอก Claude ว่า "ใช้โมเดล medium" หรือ "small" ได้ แต่ความแม่นยำจะลดลง
- **การ์ดจอ NVIDIA (Windows):** ปลั๊กอินจะลองใช้ GPU ให้อัตโนมัติ ถ้าใช้ไม่ได้ (เช่น ยังไม่ได้ติดตั้ง CUDA 12 / cuDNN 9) จะสลับไปใช้ CPU เอง ไม่ต้องตั้งค่าอะไร
- **ถ้าถอดค้างกลางทาง** (ปิดเครื่อง หรือกดยกเลิก) สั่งใหม่ด้วยไฟล์เดิมได้เลย จะทำต่อจากจุดที่ค้างไว้
- ถ้ามีไฟล์ `.txt` ชื่อเดียวกันอยู่แล้วที่ไม่ได้สร้างจากปลั๊กอินนี้ ปลั๊กอินจะไม่เขียนทับ Claude จะถามคุณก่อน
- ไฟล์ `ชื่อไฟล์.transcribe.json` ใช้เก็บสถานะสำหรับทำต่อจากจุดค้าง ลบทิ้งได้เมื่อได้ผลที่ต้องการแล้ว
- ชื่อคนและศัพท์เฉพาะอาจถอดผิด ในสรุปมีเวลาอ้างอิงไว้ให้กลับไปฟังตรวจสอบได้

## สถานะการทดสอบ

- macOS (Apple Silicon): ทดสอบแล้วด้วยคลิปเสียงไทยสั้น และโมเดล `small` ทั้งการถอดเสียง การทำต่อจากจุดค้าง และการไม่เขียนทับไฟล์ที่มีอยู่
  (ยังไม่ได้ทดสอบโมเดลเริ่มต้น `large-v3-turbo` กับเสียงประชุมจริงยาวๆ)
- Windows: ยังไม่ได้ทดสอบบนเครื่องจริง (best effort) ถ้าเจอปัญหา แจ้งพร้อมข้อความ error ได้เลย

## สำหรับผู้พัฒนา

```
.claude-plugin/marketplace.json                    # ทำให้ repo นี้เป็น marketplace
plugins/thai-meeting-transcribe/
  .claude-plugin/plugin.json
  skills/transcribe-meeting/SKILL.md               # ขั้นตอนที่ Claude ทำตาม
  skills/transcribe-meeting/scripts/transcribe.py  # สคริปต์ถอดเสียง (รันด้วย uv run)
  skills/transcribe-meeting/references/summary-template.md
tests/test_transcribe.py
```

รันเทสต์:

```bash
uv run --no-project --python 3.12 --with pytest --with faster-whisper --with "av<19" pytest tests -q
```

ทดสอบสคริปต์ตรงๆ:

```bash
uv run plugins/thai-meeting-transcribe/skills/transcribe-meeting/scripts/transcribe.py ไฟล์เสียง.m4a --model small
```
